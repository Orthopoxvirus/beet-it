"""Integration tests for import-folder operations: per-track audio streaming
and per-folder deletion (issue #44)."""

import asyncio
import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.database import get_db
from app.models.import_item import ImportItem


@pytest.fixture
def import_tree():
    """A real import folder with one album subfolder and a fake audio file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import_path = os.path.join(tmpdir, "import")
        album_dir = os.path.join(import_path, "Artist", "Album")
        os.makedirs(album_dir)
        track_path = os.path.join(album_dir, "track.mp3")
        with open(track_path, "wb") as f:
            # Minimal fake MP3 payload — content doesn't matter for streaming.
            f.write(bytes([0xFF, 0xFB, 0x90, 0x00] + [0x00] * 1020))
        yield {
            "import_path": import_path,
            "album_dir": album_dir,
            "track_path": track_path,
        }


@pytest.fixture
def mock_library(import_tree):
    library = Mock()
    library.id = 1
    library.slug = "test-library"
    library.name = "Test Library"
    library.import_path = import_tree["import_path"]
    return library


@pytest.fixture
def mock_redis_manager():
    manager = Mock()
    manager.get_scan_progress.return_value = None
    manager.invalidate_import_tree_cache.return_value = True
    return manager


@pytest.fixture
def mock_db_session():
    session = Mock(spec=Session)
    return session


@pytest.fixture
def client(mock_db_session):
    def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _audio_item(track_path: str) -> Mock:
    item = Mock(spec=ImportItem)
    item.id = 1001
    item.item_type = "file"
    item.path = track_path
    return item


class TestStreamImportItemAudio:
    """GET /libraries/{slug}/import-items/{item_id}/audio"""

    def test_streams_full_file(self, client, mock_library, mock_db_session, import_tree):
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            _audio_item(import_tree["track_path"])
        )
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ):
            resp = client.get("/api/libraries/test-library/import-items/1001/audio")

        assert resp.status_code == 200
        assert resp.headers["accept-ranges"] == "bytes"
        assert resp.headers["content-type"] == "audio/mpeg"
        assert len(resp.content) == os.path.getsize(import_tree["track_path"])

    def test_range_request_returns_partial(
        self, client, mock_library, mock_db_session, import_tree
    ):
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            _audio_item(import_tree["track_path"])
        )
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ):
            resp = client.get(
                "/api/libraries/test-library/import-items/1001/audio",
                headers={"Range": "bytes=0-9"},
            )

        assert resp.status_code == 206
        assert resp.headers["content-range"].endswith(
            f"/{os.path.getsize(import_tree['track_path'])}"
        )
        assert len(resp.content) == 10

    def test_unknown_item_returns_404(self, client, mock_library, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ):
            resp = client.get("/api/libraries/test-library/import-items/999/audio")
        assert resp.status_code == 404

    def test_item_outside_import_path_is_rejected(
        self, client, mock_library, mock_db_session, import_tree
    ):
        # An item whose path escapes the import root (e.g. stale/poisoned row).
        outside = os.path.join(
            os.path.dirname(import_tree["import_path"]), "secret.mp3"
        )
        with open(outside, "wb") as f:
            f.write(b"\xff\xfb\x90\x00")
        item = _audio_item(outside)
        mock_db_session.query.return_value.filter.return_value.first.return_value = item
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ):
            resp = client.get("/api/libraries/test-library/import-items/1001/audio")
        assert resp.status_code == 404

    def test_releases_db_session_before_streaming(
        self, client, mock_library, mock_db_session, import_tree
    ):
        """The session must be released before the body streams — otherwise
        every open playback pins a pool connection "idle in transaction" and
        a handful of listeners exhausts the pool."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            _audio_item(import_tree["track_path"])
        )
        events = []
        mock_db_session.close.side_effect = lambda: events.append("db.close")

        def tracking_iter_file(path, start=None, end=None):
            events.append("first_chunk")
            yield b"\xff\xfb\x90\x00"

        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch("app.api.routes.scan.iter_file", tracking_iter_file):
            resp = client.get("/api/libraries/test-library/import-items/1001/audio")

        assert resp.status_code == 200
        # Dependency teardown closes the session too, but only after the body
        # finished — the fix requires the close to come before the first chunk.
        assert events.index("db.close") < events.index("first_chunk")


class TestScanProgressSSE:
    """GET /libraries/{slug}/scan/progress"""

    def test_releases_db_session_before_streaming(
        self, client, mock_library, mock_db_session, mock_redis_manager
    ):
        """SSE connections stay open indefinitely; the request-scoped session
        must be released up front or every open stream holds a pool slot."""
        events = []
        mock_db_session.close.side_effect = lambda: events.append("db.close")

        def get_message():
            events.append("get_message")
            # End the otherwise-infinite SSE loop after the first poll.
            raise asyncio.CancelledError()

        pubsub = Mock()
        pubsub.get_message.side_effect = get_message
        mock_redis_manager.subscribe_scan_events.return_value = pubsub
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch(
            "app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager
        ):
            resp = client.get("/api/libraries/test-library/scan/progress")

        assert resp.status_code == 200
        assert events.index("db.close") < events.index("get_message")


class TestDeleteImportFolder:
    """DELETE /libraries/{slug}/import-folder"""

    def _expect_delete_count(self, mock_db_session, count):
        mock_db_session.query.return_value.filter.return_value.delete.return_value = count

    def test_deletes_folder_and_purges_items(
        self, client, mock_library, mock_db_session, mock_redis_manager, import_tree
    ):
        self._expect_delete_count(mock_db_session, 3)
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch(
            "app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager
        ):
            resp = client.delete(
                "/api/libraries/test-library/import-folder",
                params={"path": "Artist/Album"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["path"] == "Artist/Album"
        assert body["items_removed"] == 3
        # Folder is actually gone from disk.
        assert not os.path.exists(import_tree["album_dir"])
        # Parent folder remains.
        assert os.path.isdir(os.path.dirname(import_tree["album_dir"]))
        mock_db_session.commit.assert_called_once()
        mock_redis_manager.invalidate_import_tree_cache.assert_called_once_with(1)

    def test_path_traversal_is_rejected_and_nothing_deleted(
        self, client, mock_library, mock_db_session, mock_redis_manager, import_tree
    ):
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch(
            "app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager
        ):
            resp = client.delete(
                "/api/libraries/test-library/import-folder",
                params={"path": "../../etc"},
            )

        assert resp.status_code == 400
        # The real album folder must be untouched.
        assert os.path.isdir(import_tree["album_dir"])
        mock_db_session.commit.assert_not_called()

    def test_empty_path_is_rejected(
        self, client, mock_library, mock_db_session, mock_redis_manager
    ):
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch(
            "app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager
        ):
            resp = client.delete(
                "/api/libraries/test-library/import-folder",
                params={"path": "   "},
            )
        assert resp.status_code == 400

    def test_missing_folder_returns_404(
        self, client, mock_library, mock_db_session, mock_redis_manager
    ):
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch(
            "app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager
        ):
            resp = client.delete(
                "/api/libraries/test-library/import-folder",
                params={"path": "Artist/Does Not Exist"},
            )
        assert resp.status_code == 404

    def test_refused_while_scan_running(
        self, client, mock_library, mock_db_session, mock_redis_manager, import_tree
    ):
        mock_redis_manager.get_scan_progress.return_value = {"scan_id": 7}
        running_scan = Mock()
        running_scan.status = "scanning"
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            running_scan
        )
        with patch(
            "app.api.routes.scan.get_library_by_slug", return_value=mock_library
        ), patch(
            "app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager
        ):
            resp = client.delete(
                "/api/libraries/test-library/import-folder",
                params={"path": "Artist/Album"},
            )

        assert resp.status_code == 409
        # Folder must survive a refused delete.
        assert os.path.isdir(import_tree["album_dir"])
