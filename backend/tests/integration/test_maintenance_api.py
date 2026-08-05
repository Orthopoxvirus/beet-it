"""Integration tests for the Maintenance API endpoints (issues #147, #156)."""
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.database import get_db


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as tmp:
        music = os.path.join(tmp, "music")
        imp = os.path.join(tmp, "import")
        os.makedirs(music)
        os.makedirs(imp)

        # tracked album (no cover) + a stray file
        tracked = os.path.join(music, "real", "t.mp3")
        os.makedirs(os.path.dirname(tracked))
        with open(tracked, "wb") as f:
            f.write(b"\xff\xfb\x90\x00")
        stray = os.path.join(music, "stray", "song.mp3")
        os.makedirs(os.path.dirname(stray))
        with open(stray, "wb") as f:
            f.write(b"\xff\xfb\x90\x00")

        db_path = os.path.join(tmp, "library.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, "
            "albumartist TEXT, artpath BLOB, mb_albumid TEXT)"
        )
        cur.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB)"
        )
        cur.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (1,'R','Art',NULL)"
        )
        cur.execute(
            "INSERT INTO items (id, album_id, path) VALUES (1, 1, ?)",
            (tracked.encode(),),
        )
        conn.commit()
        conn.close()

        config_path = os.path.join(tmp, "config.yaml")
        with open(config_path, "w") as f:
            f.write(f"directory: {music}\nlibrary: {db_path}\nplugins:\n  - fetchart\n")

        yield {
            "music": music,
            "import": imp,
            "db_path": db_path,
            "config_path": config_path,
            "tracked": tracked,
            "stray": stray,
        }


@pytest.fixture
def client(temp_env):
    library = Mock()
    library.id = 1
    library.slug = "test-library"
    library.name = "Test Library"
    library.database_path = temp_env["db_path"]
    library.library_path = temp_env["music"]
    library.import_path = temp_env["import"]
    library.config_path = temp_env["config_path"]

    session = Mock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = library

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_missing_cover_lists_album(client):
    resp = client.get("/api/v1/libraries/test-library/maintenance/missing-cover")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["album_id"] == 1


def test_unimported_disabled_shows_flag(client):
    resp = client.get("/api/v1/libraries/test-library/maintenance/unimported")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["groups"] == []


def test_stray_action_deletes_file(client, temp_env):
    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/unimported/action",
        json={"paths": [temp_env["stray"]], "action": "delete"},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["status"] == "deleted"
    assert not os.path.exists(temp_env["stray"])


def test_stray_action_skips_tracked_file(client, temp_env):
    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/unimported/action",
        json={"paths": [temp_env["tracked"]], "action": "delete"},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["status"] == "skipped"
    assert os.path.exists(temp_env["tracked"])


def test_enable_plugin_rejects_unknown(client):
    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/plugins/evil/enable"
    )
    assert resp.status_code == 400


# --- BPM backfill endpoints (issue #156) ------------------------------------


def _add_bpm_column(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE items ADD COLUMN bpm REAL")
    conn.execute("UPDATE items SET bpm = NULL")
    conn.commit()
    conn.close()


def test_bpm_info_counts_missing(client, temp_env):
    _add_bpm_column(temp_env["db_path"])
    resp = client.get("/api/v1/libraries/test-library/maintenance/bpm")
    assert resp.status_code == 200
    assert resp.json()["missing_count"] == 1


def test_bpm_backfill_start_queues_task(client, temp_env):
    _add_bpm_column(temp_env["db_path"])
    fake_redis = MagicMock()
    fake_redis.get_bpm_backfill_status.return_value = None
    fake_redis.get_bpm_track_seconds.return_value = None
    with patch("app.api.maintenance.get_redis_key_manager", return_value=fake_redis), \
         patch("app.tasks.maintenance.bpm_backfill.delay") as delay:
        resp = client.post("/api/v1/libraries/test-library/maintenance/bpm/backfill")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["total"] == 1
    delay.assert_called_once()
    fake_redis.set_bpm_backfill_status.assert_called_once()
    fake_redis.clear_bpm_backfill_cancel.assert_called_once()
    # a new job must not inherit exclusions or status fields of the last one
    fake_redis.clear_bpm_failed_items.assert_called_once()
    fake_redis.clear_bpm_backfill_status.assert_called_once()


def test_bpm_backfill_start_conflicts_when_running(client, temp_env):
    _add_bpm_column(temp_env["db_path"])
    fake_redis = MagicMock()
    fake_redis.get_bpm_backfill_status.return_value = {"status": "running"}
    with patch("app.api.maintenance.get_redis_key_manager", return_value=fake_redis):
        resp = client.post("/api/v1/libraries/test-library/maintenance/bpm/backfill")
    assert resp.status_code == 409


def test_bpm_backfill_status_idle_without_job(client):
    fake_redis = MagicMock()
    fake_redis.get_bpm_backfill_status.return_value = None
    with patch("app.api.maintenance.get_redis_key_manager", return_value=fake_redis):
        resp = client.get(
            "/api/v1/libraries/test-library/maintenance/bpm/backfill/status"
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_bpm_backfill_status_reports_progress(client):
    fake_redis = MagicMock()
    fake_redis.get_bpm_backfill_status.return_value = {
        "status": "running",
        "total": 10,
        "processed": 4,
        "failed": 1,
        "job_id": "abc",
    }
    with patch("app.api.maintenance.get_redis_key_manager", return_value=fake_redis):
        resp = client.get(
            "/api/v1/libraries/test-library/maintenance/bpm/backfill/status"
        )
    body = resp.json()
    assert body["status"] == "running"
    assert body["processed"] == 4
    assert body["failed"] == 1


def test_bpm_backfill_cancel_requires_active_job(client):
    fake_redis = MagicMock()
    fake_redis.get_bpm_backfill_status.return_value = {"status": "completed"}
    with patch("app.api.maintenance.get_redis_key_manager", return_value=fake_redis):
        resp = client.post(
            "/api/v1/libraries/test-library/maintenance/bpm/backfill/cancel"
        )
    assert resp.status_code == 409


def test_bpm_backfill_cancel_sets_flag(client):
    fake_redis = MagicMock()
    fake_redis.get_bpm_backfill_status.return_value = {"status": "running"}
    with patch("app.api.maintenance.get_redis_key_manager", return_value=fake_redis):
        resp = client.post(
            "/api/v1/libraries/test-library/maintenance/bpm/backfill/cancel"
        )
    assert resp.status_code == 202
    fake_redis.request_bpm_backfill_cancel.assert_called_once_with(1)


def test_unimported_excludes_active_cover(client, temp_env):
    # The cover the album actively serves (here via folder discovery, since
    # artpath is NULL) must not be listed as a stray file.
    cover = os.path.join(temp_env["music"], "real", "albumart.jpg")
    with open(cover, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0")

    with patch(
        "app.services.maintenance_service.is_plugin_enabled", return_value=True
    ), patch(
        "app.services.maintenance_service._run_unimported",
        return_value=[cover, temp_env["stray"]],
    ):
        resp = client.get("/api/v1/libraries/test-library/maintenance/unimported")

    assert resp.status_code == 200
    data = resp.json()
    listed = [f["path"] for g in data["groups"] for f in g["files"]]
    assert temp_env["stray"] in listed
    assert cover not in listed


def test_stray_action_skips_active_cover(client, temp_env):
    cover = os.path.join(temp_env["music"], "real", "albumart.jpg")
    with open(cover, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0")

    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/unimported/action",
        json={"paths": [cover], "action": "delete"},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["status"] == "skipped"
    assert os.path.exists(cover)


JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def test_unimported_groups_carry_album_and_cover_info(client, temp_env):
    cover = os.path.join(temp_env["music"], "real", "albumart.jpg")
    with open(cover, "wb") as f:
        f.write(JPEG_MAGIC)
    stray_img = os.path.join(temp_env["music"], "real", "00-big.jpg")
    with open(stray_img, "wb") as f:
        f.write(JPEG_MAGIC)

    with patch(
        "app.services.maintenance_service.is_plugin_enabled", return_value=True
    ), patch(
        "app.services.maintenance_service._run_unimported",
        return_value=[stray_img, temp_env["stray"]],
    ):
        resp = client.get("/api/v1/libraries/test-library/maintenance/unimported")

    assert resp.status_code == 200
    groups = {g["folder"]: g for g in resp.json()["groups"]}
    tracked_group = groups[os.path.join(temp_env["music"], "real")]
    assert tracked_group["album_id"] == 1
    assert tracked_group["cover_version"] is not None
    assert tracked_group["files"][0]["is_image"] is True
    untracked_group = groups[os.path.dirname(temp_env["stray"])]
    assert untracked_group["album_id"] is None
    assert untracked_group["files"][0]["is_image"] is False


def test_preview_serves_stray_image(client, temp_env):
    stray_img = os.path.join(temp_env["music"], "real", "00-big.jpg")
    with open(stray_img, "wb") as f:
        f.write(JPEG_MAGIC)
    resp = client.get(
        "/api/v1/libraries/test-library/maintenance/unimported/preview",
        params={"path": stray_img},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == JPEG_MAGIC


def test_preview_rejects_path_outside_root(client, temp_env):
    resp = client.get(
        "/api/v1/libraries/test-library/maintenance/unimported/preview",
        params={"path": "/etc/passwd"},
    )
    assert resp.status_code == 400


def test_preview_rejects_non_image(client, temp_env):
    resp = client.get(
        "/api/v1/libraries/test-library/maintenance/unimported/preview",
        params={"path": temp_env["tracked"]},
    )
    assert resp.status_code == 400


def test_use_as_cover_promotes_stray_and_replaces_existing(client, temp_env):
    old_cover = os.path.join(temp_env["music"], "real", "cover.png")
    with open(old_cover, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    stray_img = os.path.join(temp_env["music"], "real", "00-big.jpg")
    with open(stray_img, "wb") as f:
        f.write(JPEG_MAGIC)

    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/unimported/use-as-cover",
        json={"path": stray_img},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cover_set"
    assert data["album_id"] == 1

    # Default art_filename is "albumart"; the promoted file replaces every
    # other cover variant and the source is consumed.
    new_cover = os.path.join(temp_env["music"], "real", "albumart.jpg")
    assert data["cover_path"] == new_cover
    assert os.path.exists(new_cover)
    assert not os.path.exists(old_cover)
    assert not os.path.exists(stray_img)

    conn = sqlite3.connect(temp_env["db_path"])
    row = conn.execute("SELECT artpath FROM albums WHERE id = 1").fetchone()
    conn.close()
    assert row[0].decode() == new_cover


def test_use_as_cover_rejects_untracked_folder(client, temp_env):
    stray_img = os.path.join(temp_env["music"], "stray", "art.jpg")
    with open(stray_img, "wb") as f:
        f.write(JPEG_MAGIC)
    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/unimported/use-as-cover",
        json={"path": stray_img},
    )
    assert resp.status_code == 400
    assert "tracked album" in resp.json()["detail"]


def test_use_as_cover_rejects_non_image(client, temp_env):
    resp = client.post(
        "/api/v1/libraries/test-library/maintenance/unimported/use-as-cover",
        json={"path": temp_env["tracked"]},
    )
    assert resp.status_code == 400
