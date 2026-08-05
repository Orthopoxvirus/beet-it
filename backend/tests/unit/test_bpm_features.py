"""Unit tests for the BPM feature set (issue #156).

Covers the beets-library BPM queries, the flat track ZIP packer used by the
BPM-range download, and the autobpm chunk runner's command construction.
"""

import os
import sqlite3
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.beets_library_service import BeetsLibraryService
from app.services.download_service import pack_tracks_to_zip
from app.tasks.maintenance import _autobpm_error_snippet, _run_autobpm_chunk


@pytest.fixture
def beets_service():
    return BeetsLibraryService()


@pytest.fixture
def bpm_library():
    """A beets DB with tracks across the BPM spectrum.

    id | title       | bpm   | on disk
    1  | NoBpmNull   | NULL  | yes
    2  | NoBpmZero   | 0     | yes
    3  | Slow        | 78    | yes
    4  | Run         | 155   | yes
    5  | Run2        | 160   | yes
    6  | Double      | 310   | yes
    7  | Fast        | 200   | yes
    8  | Ghost       | 152   | no (file missing)
    9  | Singleton   | 151   | yes (no album row)
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "library.db")
        music = os.path.join(tmp, "music")
        os.makedirs(music)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, albumartist TEXT, artpath BLOB)"
        )
        cur.execute(
            """CREATE TABLE items (
                id INTEGER PRIMARY KEY, album_id INTEGER, title TEXT, artist TEXT,
                album TEXT, track INTEGER, disc INTEGER, length REAL, format TEXT,
                bitrate INTEGER, samplerate INTEGER, channels INTEGER, path BLOB,
                mb_trackid TEXT, bpm REAL
            )"""
        )
        cur.execute("INSERT INTO albums VALUES (1, 'Album', 'Artist', NULL)")

        rows = [
            (1, 1, "NoBpmNull", None, True),
            (2, 1, "NoBpmZero", 0, True),
            (3, 1, "Slow", 78, True),
            (4, 1, "Run", 155, True),
            (5, 1, "Run2", 160, True),
            (6, 1, "Double", 310, True),
            (7, 1, "Fast", 200, True),
            (8, 1, "Ghost", 152, False),
            (9, None, "Singleton", 151, True),
        ]
        for item_id, album_id, title, bpm, on_disk in rows:
            path = os.path.join(music, f"{title}.mp3")
            if on_disk:
                with open(path, "wb") as f:
                    f.write(b"x" * 10)
            cur.execute(
                "INSERT INTO items (id, album_id, title, artist, album, track, disc, "
                "length, format, bitrate, samplerate, channels, path, bpm) "
                "VALUES (?, ?, ?, 'Artist', 'Album', 1, 1, 60.0, 'mp3', 320, 44100, 2, ?, ?)",
                (item_id, album_id, title, path.encode(), bpm),
            )
        conn.commit()
        conn.close()
        yield {"db_path": db_path, "music": music}


class TestGetItemIdsMissingBpm:
    def test_finds_null_and_zero(self, beets_service, bpm_library):
        ids = beets_service.get_item_ids_missing_bpm(bpm_library["db_path"])
        assert ids == [1, 2]

    def test_missing_db_raises(self, beets_service):
        with pytest.raises(FileNotFoundError):
            beets_service.get_item_ids_missing_bpm("/nope/library.db")


class TestCountItemsWithBpm:
    """Post-chunk verification: beets exits 0 even when tracks fail, so the
    backfill counts what actually landed in the DB."""

    def test_counts_only_stored_bpm(self, beets_service, bpm_library):
        # ids 1+2 have no bpm, 3+4 do
        count = beets_service.count_items_with_bpm(bpm_library["db_path"], [1, 2, 3, 4])
        assert count == 2

    def test_empty_input(self, beets_service, bpm_library):
        assert beets_service.count_items_with_bpm(bpm_library["db_path"], []) == 0


class TestAutobpmErrorSnippet:
    def test_prefers_autobpm_line(self):
        result = MagicMock(
            returncode=0,
            stderr=(
                "----> resampy = lazy.load(\"resampy\")\n"
                "autobpm: Failed to load /music/a.flac: No module named 'resampy'\n"
                "\n"
                "----> resampy = lazy.load(\"resampy\")\n"
            ),
        )
        snippet = _autobpm_error_snippet(result)
        assert snippet.startswith("autobpm: Failed to load")

    def test_falls_back_to_returncode(self):
        result = MagicMock(returncode=2, stderr="")
        assert _autobpm_error_snippet(result) == "beets exited with code 2"


class TestSearchLibraryTitlesBpmFilter:
    """BPM semantics of the titles search (replaced get_track_ids_by_bpm_range)."""

    @staticmethod
    def _ids(beets_service, db_path, **kw):
        return {r["id"] for r in beets_service.search_library_title_ids(db_path, **kw)}

    def test_plain_range(self, beets_service, bpm_library):
        ids = self._ids(beets_service, bpm_library["db_path"], bpm_min=150, bpm_max=160)
        # 155, 160, 152 (file missing but still tagged), 151 — not 78/200/310.
        assert ids == {4, 5, 8, 9}

    def test_half_double_octave_errors(self, beets_service, bpm_library):
        ids = self._ids(
            beets_service, bpm_library["db_path"],
            bpm_min=150, bpm_max=160, include_half_double=True,
        )
        # adds Slow (78 ∈ 75-80) and Double (310 ∈ 300-320).
        assert ids == {3, 4, 5, 6, 8, 9}

    def test_untagged_items_never_match(self, beets_service, bpm_library):
        ids = self._ids(
            beets_service, bpm_library["db_path"],
            bpm_min=0.5, bpm_max=1000, include_half_double=True,
        )
        assert 1 not in ids and 2 not in ids

    def test_search_combines_with_bpm(self, beets_service, bpm_library):
        rows, total = beets_service.search_library_titles(
            bpm_library["db_path"], search="Run", bpm_min=150, bpm_max=160
        )
        assert total == 2
        assert {r["title"] for r in rows} == {"Run", "Run2"}
        assert all(r["bpm"] in (155, 160) for r in rows)

    def test_search_matches_singletons_without_album_row(self, beets_service, bpm_library):
        rows, total = beets_service.search_library_titles(
            bpm_library["db_path"], search="Singleton"
        )
        assert total == 1
        assert rows[0]["id"] == 9
        assert rows[0]["album"] == ""

    def test_pagination(self, beets_service, bpm_library):
        rows, total = beets_service.search_library_titles(
            bpm_library["db_path"], page=1, per_page=4
        )
        assert total == 9
        assert len(rows) == 4


class TestGetTracksByIds:
    def test_order_follows_input_and_unknown_skipped(self, beets_service, bpm_library):
        tracks = beets_service.get_tracks_by_ids(
            bpm_library["db_path"], [5, 999, 4], library_root=bpm_library["music"]
        )
        assert [t.id for t in tracks] == [5, 4]
        assert tracks[0].title == "Run2"
        assert tracks[0].file_size > 0

    def test_singleton_without_album_row(self, beets_service, bpm_library):
        tracks = beets_service.get_tracks_by_ids(bpm_library["db_path"], [9])
        assert len(tracks) == 1
        assert tracks[0].album == "Album"  # falls back to the item's own album tag

    def test_empty_input(self, beets_service, bpm_library):
        assert beets_service.get_tracks_by_ids(bpm_library["db_path"], []) == []


class TestPackTracksToZip:
    def test_flat_artist_title_arcnames(self, beets_service, bpm_library):
        with tempfile.TemporaryDirectory() as out:
            dest = os.path.join(out, "bpm.zip")
            size, packed = pack_tracks_to_zip(
                beets_service=beets_service,
                db_path=bpm_library["db_path"],
                library_path=bpm_library["music"],
                track_ids=[4, 5],
                dest_path=dest,
            )
            assert packed == 2
            assert size > 0
            with zipfile.ZipFile(dest) as zf:
                names = sorted(zf.namelist())
            assert names == ["Artist - Run.mp3", "Artist - Run2.mp3"]

    def test_missing_file_skipped_and_progress_reported(self, beets_service, bpm_library):
        calls = []
        with tempfile.TemporaryDirectory() as out:
            dest = os.path.join(out, "bpm.zip")
            _, packed = pack_tracks_to_zip(
                beets_service=beets_service,
                db_path=bpm_library["db_path"],
                library_path=bpm_library["music"],
                track_ids=[4, 8],
                dest_path=dest,
                progress_cb=lambda p, t, label: calls.append((p, t)),
            )
            assert packed == 1  # Ghost's file is missing
            assert calls[-1] == (2, 2)

    def test_arcname_collision_gets_suffix(self, beets_service, bpm_library):
        # Same track twice: identical "Artist - Title.ext" arcnames must not
        # collide — the second entry gets a " (2)" suffix, nothing is dropped.
        with tempfile.TemporaryDirectory() as out:
            dest = os.path.join(out, "bpm.zip")
            _, packed = pack_tracks_to_zip(
                beets_service=beets_service,
                db_path=bpm_library["db_path"],
                library_path=bpm_library["music"],
                track_ids=[4, 4],
                dest_path=dest,
            )
            assert packed == 2
            with zipfile.ZipFile(dest) as zf:
                assert sorted(zf.namelist()) == [
                    "Artist - Run (2).mp3",
                    "Artist - Run.mp3",
                ]

    def test_nothing_packed_raises_and_removes_archive(self, beets_service, bpm_library):
        with tempfile.TemporaryDirectory() as out:
            dest = os.path.join(out, "bpm.zip")
            with pytest.raises(ValueError):
                pack_tracks_to_zip(
                    beets_service=beets_service,
                    db_path=bpm_library["db_path"],
                    library_path=bpm_library["music"],
                    track_ids=[8],  # only the missing-file track
                    dest_path=dest,
                )
            assert not os.path.exists(dest)


class TestRunAutobpmChunk:
    def test_command_shape(self):
        with patch("app.tasks.maintenance.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            _run_autobpm_chunk("/config/lib.yaml", [7, 9])
            cmd = run.call_args[0][0]
        assert cmd[:5] == ["python", "-m", "beets", "-c", "/config/lib.yaml"]
        assert "--plugins" in cmd and "autobpm" in cmd
        # comma must be a standalone argv token for beets to OR the ids
        assert cmd[-3:] == ["id:7", ",", "id:9"]

    def test_no_config_path(self):
        with patch("app.tasks.maintenance.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            _run_autobpm_chunk(None, [1])
            cmd = run.call_args[0][0]
        assert "-c" not in cmd


class TestBpmWorkers:
    def test_setting_override(self):
        from app.tasks import maintenance as m
        with patch.object(m.settings, "bpm_analysis_workers", 4):
            assert m.bpm_workers() == 4

    def test_auto_half_of_visible_cores(self):
        from app.tasks import maintenance as m
        with patch.object(m.settings, "bpm_analysis_workers", 0), \
             patch.object(m.os, "sched_getaffinity", return_value=set(range(20)), create=True):
            assert m.bpm_workers() == 10

    def test_auto_minimum_one(self):
        from app.tasks import maintenance as m
        with patch.object(m.settings, "bpm_analysis_workers", 0), \
             patch.object(m.os, "sched_getaffinity", return_value={0}, create=True):
            assert m.bpm_workers() == 1


class TestEstimateBackfillSeconds:
    def test_uses_measured_rate(self):
        from app.tasks import maintenance as m
        fake_redis = MagicMock()
        fake_redis.get_bpm_track_seconds.return_value = 0.5
        assert m.estimate_backfill_seconds(fake_redis, 1, 100) == 50

    def test_falls_back_to_default_over_workers(self):
        from app.tasks import maintenance as m
        fake_redis = MagicMock()
        fake_redis.get_bpm_track_seconds.return_value = None
        with patch.object(m, "bpm_workers", return_value=4):
            assert m.estimate_backfill_seconds(fake_redis, 1, 100) == int(
                100 * m.BPM_DEFAULT_TRACK_SECONDS / 4
            )

    def test_zero_missing(self):
        from app.tasks import maintenance as m
        assert m.estimate_backfill_seconds(MagicMock(), 1, 0) == 0

    def test_redis_failure_is_cosmetic(self):
        from app.tasks import maintenance as m
        fake_redis = MagicMock()
        fake_redis.get_bpm_track_seconds.side_effect = ConnectionError("down")
        with patch.object(m, "bpm_workers", return_value=2):
            assert m.estimate_backfill_seconds(fake_redis, 1, 10) > 0


class TestGetItemIdsWithBpm:
    def test_returns_only_stored(self, beets_service, bpm_library):
        ids = beets_service.get_item_ids_with_bpm(bpm_library["db_path"], [1, 2, 3, 4])
        assert ids == {3, 4}

    def test_empty_input(self, beets_service, bpm_library):
        assert beets_service.get_item_ids_with_bpm(bpm_library["db_path"], []) == set()


def _fake_link_env(m, missing_ids, stored_side_effect=None, cancelled=False, state=None):
    """Common mocks for driving one bpm_backfill link."""
    from datetime import datetime

    lib = MagicMock()
    lib.id = 1
    lib.slug = "lib"
    lib.database_path = "/data/db"
    lib.config_path = "/config/lib.yaml"
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = lib

    fake_redis = MagicMock()
    fake_redis.acquire_bpm_link_lock.return_value = True
    fake_redis.is_bpm_backfill_cancelled.return_value = cancelled
    fake_redis.get_bpm_failed_items.return_value = set()
    fake_redis.get_bpm_backfill_status.return_value = state
    # default: items reach the attempt cap immediately (give-up on first try)
    fake_redis.incr_bpm_attempts.side_effect = (
        lambda lid, ids, **kw: {i: m.BPM_MAX_ITEM_ATTEMPTS for i in ids}
    )

    fake_beets = MagicMock()
    # first call: link work list; second call: end-of-link remaining check
    fake_beets.get_item_ids_missing_bpm.side_effect = missing_ids
    fake_beets.get_item_ids_with_bpm.side_effect = (
        stored_side_effect or (lambda db, chunk: set(chunk))
    )

    fake_events = MagicMock()
    fake_events.record_start.return_value = 42
    return lib, fake_db, fake_redis, fake_beets, fake_events


class TestBpmBackfillChaining:
    def test_completes_when_all_stored(self):
        from app.tasks import maintenance as m

        _, fake_db, fake_redis, fake_beets, fake_events = _fake_link_env(
            m, missing_ids=[[1, 2, 3], []]
        )
        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=fake_events), \
             patch.object(m, "BeetsLibraryService", return_value=fake_beets), \
             patch.object(m, "_run_autobpm_chunk", return_value=MagicMock(returncode=0, stderr="")), \
             patch.object(m.bpm_backfill, "apply_async") as apply_async:
            result = m.bpm_backfill(library_id=1, job_id="job-1")

        assert result["status"] == "completed"
        assert result["processed"] == 3
        apply_async.assert_not_called()
        # measured rate persisted for the next pre-flight estimate
        fake_redis.set_bpm_track_seconds.assert_called_once()
        last_publish = fake_redis.set_bpm_backfill_status.call_args.kwargs
        assert last_publish["status"] == "completed"
        fake_redis.release_bpm_link_lock.assert_called_once()

    def test_requeues_next_link_when_budget_exhausted(self):
        from app.tasks import maintenance as m

        _, fake_db, fake_redis, fake_beets, fake_events = _fake_link_env(
            m, missing_ids=[[1, 2, 3], [1, 2, 3]]
        )
        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=fake_events), \
             patch.object(m, "BeetsLibraryService", return_value=fake_beets), \
             patch.object(m, "BPM_LINK_MAX_SECONDS", 0), \
             patch.object(m.bpm_backfill, "apply_async") as apply_async:
            result = m.bpm_backfill(library_id=1, job_id="job-1")

        assert result["status"] == "chained"
        apply_async.assert_called_once()
        assert apply_async.call_args.kwargs["kwargs"] == {"library_id": 1, "job_id": "job-1"}
        last_publish = fake_redis.set_bpm_backfill_status.call_args.kwargs
        assert last_publish["status"] == "running"

    def test_failed_items_are_excluded_and_terminal(self):
        from app.tasks import maintenance as m

        # nothing ever stores: all items must land in the exclusion set and
        # the job must still terminate (completed_with_errors), not loop
        _, fake_db, fake_redis, fake_beets, fake_events = _fake_link_env(
            m,
            missing_ids=[[1, 2], [1, 2]],
            stored_side_effect=lambda db, chunk: set(),
        )
        excluded = set()
        fake_redis.add_bpm_failed_items.side_effect = lambda lid, ids, **kw: excluded.update(ids)
        fake_redis.get_bpm_failed_items.side_effect = lambda lid: set(excluded)

        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=fake_events), \
             patch.object(m, "BeetsLibraryService", return_value=fake_beets), \
             patch.object(m, "_run_autobpm_chunk", return_value=MagicMock(returncode=0, stderr="autobpm: Failed to load x: boom")), \
             patch.object(m.bpm_backfill, "apply_async") as apply_async:
            result = m.bpm_backfill(library_id=1, job_id="job-1")

        assert result["status"] == "completed_with_errors"
        assert result["failed"] == 2
        assert excluded == {1, 2}
        apply_async.assert_not_called()

    def test_duplicate_link_skips(self):
        from app.tasks import maintenance as m

        fake_redis = MagicMock()
        fake_redis.acquire_bpm_link_lock.return_value = False
        with patch.object(m, "SessionLocal", return_value=MagicMock()), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=MagicMock()):
            result = m.bpm_backfill(library_id=1, job_id="job-1")
        assert result["status"] == "duplicate_link_skipped"
        fake_redis.set_bpm_backfill_status.assert_not_called()

    def test_cancel_finalizes_and_clears_flag(self):
        from app.tasks import maintenance as m

        _, fake_db, fake_redis, fake_beets, fake_events = _fake_link_env(
            m, missing_ids=[[1], []], cancelled=True
        )
        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=fake_events), \
             patch.object(m, "BeetsLibraryService", return_value=fake_beets), \
             patch.object(m.bpm_backfill, "apply_async") as apply_async:
            result = m.bpm_backfill(library_id=1, job_id="job-1")

        assert result["status"] == "cancelled"
        fake_redis.clear_bpm_backfill_cancel.assert_called_once()
        apply_async.assert_not_called()

    def test_later_link_continues_counters(self):
        from app.tasks import maintenance as m

        state = {
            "job_id": "job-1", "status": "running", "total": 10,
            "processed": 7, "failed": 0, "active_seconds": 40.0, "event_id": 42,
        }
        _, fake_db, fake_redis, fake_beets, fake_events = _fake_link_env(
            m, missing_ids=[[8, 9, 10], []], state=state
        )
        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=fake_events), \
             patch.object(m, "BeetsLibraryService", return_value=fake_beets), \
             patch.object(m, "_run_autobpm_chunk", return_value=MagicMock(returncode=0, stderr="")), \
             patch.object(m.bpm_backfill, "apply_async"):
            result = m.bpm_backfill(library_id=1, job_id="job-1")

        assert result["status"] == "completed"
        assert result["processed"] == 10
        assert result["total"] == 10
        # continued job must not open a second activity event
        fake_events.record_start.assert_not_called()


class TestResumeStalledBpmBackfills:
    def _run(self, m, status_dict, age_seconds):
        from datetime import datetime, timedelta, timezone

        lib = MagicMock()
        lib.id = 1
        fake_db = MagicMock()
        fake_db.query.return_value.all.return_value = [lib]
        fake_redis = MagicMock()
        if status_dict is not None:
            status_dict = dict(status_dict)
            status_dict["updated_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
            ).isoformat()
        fake_redis.get_bpm_backfill_status.return_value = status_dict
        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m.bpm_backfill, "delay") as delay:
            result = m.resume_stalled_bpm_backfills()
        return result, delay

    def test_resumes_stale_running_job(self):
        from app.tasks import maintenance as m
        result, delay = self._run(
            m, {"status": "running", "job_id": "j1", "total": 10, "processed": 2, "failed": 0},
            m.BPM_RESUME_STALE_SECONDS + 60,
        )
        delay.assert_called_once_with(library_id=1, job_id="j1")
        assert result["resumed"] == [1]

    def test_ignores_fresh_job(self):
        from app.tasks import maintenance as m
        _, delay = self._run(
            m, {"status": "running", "job_id": "j1", "total": 10, "processed": 2, "failed": 0}, 60
        )
        delay.assert_not_called()

    def test_ignores_terminal_job(self):
        from app.tasks import maintenance as m
        _, delay = self._run(
            m, {"status": "completed", "job_id": "j1", "total": 10, "processed": 10, "failed": 0},
            m.BPM_RESUME_STALE_SECONDS + 60,
        )
        delay.assert_not_called()


class TestBpmCrashRetries:
    def test_first_failure_retries_instead_of_excluding(self):
        from app.tasks import maintenance as m

        # chunk "crashes" (nothing stored) but items are on attempt 1 of 3:
        # nothing may be excluded, the chain must continue via a next link.
        _, fake_db, fake_redis, fake_beets, fake_events = _fake_link_env(
            m,
            missing_ids=[[1, 2], [1, 2]],
            stored_side_effect=lambda db, chunk: set(),
        )
        fake_redis.incr_bpm_attempts.side_effect = lambda lid, ids, **kw: {i: 1 for i in ids}

        with patch.object(m, "SessionLocal", return_value=fake_db), \
             patch.object(m, "get_redis_key_manager", return_value=fake_redis), \
             patch.object(m, "get_task_event_service", return_value=fake_events), \
             patch.object(m, "BeetsLibraryService", return_value=fake_beets), \
             patch.object(m, "_run_autobpm_chunk", return_value=MagicMock(returncode=-11, stderr="")), \
             patch.object(m.bpm_backfill, "apply_async") as apply_async:
            result = m.bpm_backfill(library_id=1, job_id="job-1")

        assert result["status"] == "chained"
        assert result["failed"] == 0
        fake_redis.add_bpm_failed_items.assert_not_called()
        apply_async.assert_called_once()


class TestAutobpmSubprocessEnv:
    def test_math_libs_pinned_to_one_thread(self):
        from app.tasks import maintenance as m
        env = m._autobpm_env()
        for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            assert env[var] == "1"
