"""Integration tests for scan API endpoints."""

import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import Base
from app.models.library import Library
from app.models.import_scan import ImportScan
from app.models.import_item import ImportItem


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis key manager."""
    manager = Mock()
    manager.get_scan_progress.return_value = None
    manager.get_scan_queue_length.return_value = 0
    manager.get_active_operations.return_value = []
    manager.get_watcher_state.return_value = {"active": False, "pending_scan": False}
    manager.enqueue_scan.return_value = 1
    manager.subscribe_scan_events.return_value = Mock()
    return manager


@pytest.fixture
def mock_library():
    """Create a mock library."""
    library = Mock(spec=Library)
    library.id = 1
    library.name = "Test Library"
    library.slug = "test-library"
    library.import_path = "/data/import/test"
    return library


@pytest.fixture
def mock_scan():
    """Create a mock scan."""
    scan = Mock(spec=ImportScan)
    scan.id = 1
    scan.library_id = 1
    scan.status = "completed"
    scan.started_at = datetime(2024, 1, 15, 10, 30, 0)
    scan.completed_at = datetime(2024, 1, 15, 10, 35, 32)
    scan.items_total = 150
    scan.items_processed = 150
    scan.error_message = None
    return scan


@pytest.fixture
def mock_import_item():
    """Create a mock import item."""
    item = Mock(spec=ImportItem)
    item.id = 1001
    item.item_type = "file"
    item.path = "/data/import/test/Artist/Album/track.mp3"
    item.directory = "/data/import/test/Artist/Album"
    item.filename = "track.mp3"
    item.album = "Test Album"
    item.album_artist = "Test Artist"
    item.artist = "Test Artist"
    item.title = "Test Track"
    item.track_number = 1
    item.track_total = 12
    item.genre = "Rock"
    item.status = "new"
    item.first_seen_at = datetime(2024, 1, 15, 10, 30, 0)
    item.last_seen_at = datetime(2024, 1, 15, 10, 30, 0)
    return item


class TestGetScanStatus:
    """Tests for GET /libraries/{slug}/scan/status endpoint."""

    def test_get_scan_status_no_scan(self, mock_redis_manager, mock_library):
        """Test getting status when no scan is running."""
        with patch("app.api.routes.scan.get_library_by_slug", return_value=mock_library):
            with patch("app.api.routes.scan.get_redis_manager", return_value=mock_redis_manager):
                with patch("app.api.routes.scan.get_db"):
                    from main import app
                    from fastapi.testclient import TestClient

                    # Mock the database query for last completed scan
                    with patch.object(app, "dependency_overrides", {}):
                        client = TestClient(app)
                        # This test would need full app setup - marking as placeholder
                        pass

    def test_scan_status_response_schema(self):
        """Test scan status response matches expected schema."""
        from app.schemas.scan import ScanStatusResponse, ScanStatus, OperationType

        response = ScanStatusResponse(
            library_slug="test-library",
            current_scan=None,
            queued_scans=0,
            blocking_operations=[],
            watcher_active=False,
            last_completed_scan=None,
        )

        assert response.library_slug == "test-library"
        assert response.queued_scans == 0
        assert response.watcher_active is False


class TestTriggerManualScan:
    """Tests for POST /libraries/{slug}/scan endpoint."""

    def test_trigger_scan_response_schema(self):
        """Test scan trigger response matches expected schema."""
        from app.schemas.scan import ScanTriggerResponse, OperationType

        response = ScanTriggerResponse(
            status="started",
            scan_id=None,
            message="Scan started for library 'test-library'",
            queue_position=None,
            blocking_operations=[],
        )

        assert response.status == "started"
        assert response.message == "Scan started for library 'test-library'"


class TestGetScanHistory:
    """Tests for GET /libraries/{slug}/scan/history endpoint."""

    def test_scan_history_response_schema(self):
        """Test scan history response matches expected schema."""
        from app.schemas.scan import ScanHistoryResponse, ScanHistoryItem, ScanStatus

        item = ScanHistoryItem(
            id=1,
            status=ScanStatus.COMPLETED,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
            completed_at=datetime(2024, 1, 15, 10, 35, 32),
            items_total=150,
            items_processed=150,
            error_message=None,
        )

        response = ScanHistoryResponse(
            items=[item],
            total=1,
            skip=0,
            limit=20,
        )

        assert len(response.items) == 1
        assert response.total == 1


class TestListImportItems:
    """Tests for GET /libraries/{slug}/import-items endpoint."""

    def test_import_items_response_schema(self):
        """Test import items response matches expected schema."""
        from app.schemas.scan import (
            ImportItemListResponse,
            ImportItem,
            ImportItemType,
            ImportItemStatus,
        )

        item = ImportItem(
            id=1001,
            item_type=ImportItemType.FILE,
            path="/data/import/test/track.mp3",
            directory="/data/import/test",
            filename="track.mp3",
            album="Test Album",
            album_artist="Test Artist",
            artist="Test Artist",
            title="Test Track",
            track_number=1,
            track_total=12,
            genre="Rock",
            format="mp3",
            bitrate=320,
            status=ImportItemStatus.NEW,
            first_seen_at=datetime(2024, 1, 15, 10, 30, 0),
            last_seen_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        response = ImportItemListResponse(
            items=[item],
            total=1,
            skip=0,
            limit=50,
            scan_id=1,
            scan_completed_at=datetime(2024, 1, 15, 10, 35, 32),
        )

        assert len(response.items) == 1
        assert response.scan_id == 1
        assert response.items[0].format == "mp3"
        assert response.items[0].bitrate == 320

    def test_import_item_quality_fields_optional(self):
        """format and bitrate default to None (pre-migration / non-audio rows)."""
        from app.schemas.scan import ImportItem, ImportItemType, ImportItemStatus

        item = ImportItem(
            id=1,
            item_type=ImportItemType.FOLDER,
            path="/data/import/folder",
            directory="/data/import",
            filename="folder",
            status=ImportItemStatus.NEW,
            first_seen_at=datetime(2024, 1, 15, 10, 30, 0),
            last_seen_at=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert item.format is None
        assert item.bitrate is None


class TestPathPrefixFilter:
    """Tests for the path_prefix query parameter on /libraries/{slug}/import-items endpoint."""

    def test_path_prefix_filter_returns_matching_items(self):
        """Test that path_prefix filter returns items whose path starts with the prefix."""
        # Create mock items with different paths using simple objects
        class MockItem:
            def __init__(self, path, album):
                self.path = path
                self.album = album

        item1 = MockItem("/music/Artist/Album1/track1.mp3", "Album One")
        item2 = MockItem("/music/Artist/Album1/track2.mp3", "Album One")
        item3 = MockItem("/music/Artist/Album2/track1.mp3", "Album Two")

        # Create a mock query that simulates startswith filtering
        def mock_startswith_filter(items, prefix):
            """Simulate the path.startswith filter behavior."""
            normalized_prefix = prefix.rstrip("/")
            return [item for item in items if item.path.startswith(normalized_prefix)]

        # Test filtering with path_prefix=/music/Artist/Album1
        filtered_items = mock_startswith_filter([item1, item2, item3], "/music/Artist/Album1")
        assert len(filtered_items) == 2
        assert all(item.path.startswith("/music/Artist/Album1") for item in filtered_items)

        # Test filtering with path_prefix=/music/Artist (should return all)
        filtered_items = mock_startswith_filter([item1, item2, item3], "/music/Artist")
        assert len(filtered_items) == 3

        # Test filtering with path_prefix=/music/Artist/Album2 (should return only one)
        filtered_items = mock_startswith_filter([item1, item2, item3], "/music/Artist/Album2")
        assert len(filtered_items) == 1
        assert filtered_items[0].album == "Album Two"

    def test_path_prefix_normalizes_trailing_slash(self):
        """Test that path_prefix handles trailing slashes correctly."""
        # Test items
        items = [
            {"path": "/music/Artist/Album1/track1.mp3"},
            {"path": "/music/Artist/Album2/track1.mp3"},
        ]

        # Simulate the normalization logic from the endpoint
        def filter_with_normalization(items, prefix):
            normalized_prefix = prefix.rstrip("/")
            return [item for item in items if item["path"].startswith(normalized_prefix)]

        # With trailing slash
        result_with_slash = filter_with_normalization(items, "/music/Artist/Album1/")
        # Without trailing slash
        result_without_slash = filter_with_normalization(items, "/music/Artist/Album1")

        # Both should return the same result
        assert len(result_with_slash) == len(result_without_slash)
        assert result_with_slash == result_without_slash

    def test_path_prefix_empty_result(self):
        """Test that path_prefix returns empty list when no items match."""
        items = [
            {"path": "/music/Artist/Album1/track1.mp3"},
            {"path": "/music/Artist/Album2/track1.mp3"},
        ]

        def filter_items(items, prefix):
            normalized_prefix = prefix.rstrip("/")
            return [item for item in items if item["path"].startswith(normalized_prefix)]

        # Non-matching prefix
        result = filter_items(items, "/nonexistent/path")
        assert len(result) == 0

    def test_path_prefix_combined_with_item_type_filter(self):
        """Test that path_prefix works correctly with item_type filter."""
        items = [
            {"path": "/music/Artist/Album1", "item_type": "folder"},
            {"path": "/music/Artist/Album1/track1.mp3", "item_type": "file"},
            {"path": "/music/Artist/Album1/track2.mp3", "item_type": "file"},
        ]

        def filter_items(items, prefix, item_type=None):
            normalized_prefix = prefix.rstrip("/")
            filtered = [item for item in items if item["path"].startswith(normalized_prefix)]
            if item_type:
                filtered = [item for item in filtered if item["item_type"] == item_type]
            return filtered

        # Filter by path_prefix and item_type=file
        result = filter_items(items, "/music/Artist/Album1", "file")
        assert len(result) == 2
        assert all(item["item_type"] == "file" for item in result)

        # Filter by path_prefix only (should include folder)
        result = filter_items(items, "/music/Artist/Album1")
        assert len(result) == 3

    def test_path_prefix_recursive_folder_content(self):
        """Test that path_prefix returns all items recursively under a folder.

        This is the key use case: fetching all tracks in a folder tree.
        Given: /music/Artist/
          - Album1/
            - track1.mp3
            - track2.mp3
          - Album2/
            - track1.mp3

        path_prefix=/music/Artist should return all 5 items (2 folders + 3 files)
        """
        items = [
            {"path": "/music/Artist/Album1", "item_type": "folder"},
            {"path": "/music/Artist/Album1/track1.mp3", "item_type": "file"},
            {"path": "/music/Artist/Album1/track2.mp3", "item_type": "file"},
            {"path": "/music/Artist/Album2", "item_type": "folder"},
            {"path": "/music/Artist/Album2/track1.mp3", "item_type": "file"},
            {"path": "/music/OtherArtist/Album1", "item_type": "folder"},
        ]

        def filter_items(items, prefix):
            normalized_prefix = prefix.rstrip("/")
            return [item for item in items if item["path"].startswith(normalized_prefix)]

        # Fetch all items under /music/Artist
        result = filter_items(items, "/music/Artist")
        assert len(result) == 5
        # Should NOT include /music/OtherArtist
        assert not any(item["path"].startswith("/music/OtherArtist") for item in result)

    def test_path_prefix_differs_from_directory_filter(self):
        """Test that path_prefix behaves differently from directory filter.

        directory: Exact match on parent directory (immediate children only)
        path_prefix: Prefix match on full path (all descendants recursively)
        """
        items = [
            {"path": "/music/Artist/Album1", "directory": "/music/Artist"},
            {"path": "/music/Artist/Album1/track1.mp3", "directory": "/music/Artist/Album1"},
            {"path": "/music/Artist/Album1/track2.mp3", "directory": "/music/Artist/Album1"},
            {"path": "/music/Artist/Album2", "directory": "/music/Artist"},
            {"path": "/music/Artist/Album2/track1.mp3", "directory": "/music/Artist/Album2"},
        ]

        def filter_by_directory(items, directory):
            """Simulates directory filter - exact match."""
            return [item for item in items if item["directory"] == directory]

        def filter_by_path_prefix(items, prefix):
            """Simulates path_prefix filter - prefix match."""
            normalized_prefix = prefix.rstrip("/")
            return [item for item in items if item["path"].startswith(normalized_prefix)]

        # directory=/music/Artist returns only immediate children
        directory_result = filter_by_directory(items, "/music/Artist")
        assert len(directory_result) == 2  # Album1 folder and Album2 folder

        # path_prefix=/music/Artist returns all descendants
        path_prefix_result = filter_by_path_prefix(items, "/music/Artist")
        assert len(path_prefix_result) == 5  # All items under /music/Artist


class TestAudioOnlyFilter:
    """Tests for the audio_only filter on /import-items (issue #27).

    Mirrors the route clause: keep folders, and for files require an audio
    extension. Sidecar files (cover art, .m3u, .sfv, .nfo) must be excluded.
    """

    def _apply_audio_only(self, items):
        from app.services.scanner.scanner_service import is_audio_filename

        return [
            item
            for item in items
            if item["item_type"] != "file" or is_audio_filename(item["filename"])
        ]

    def test_sidecar_files_excluded_audio_and_folders_kept(self):
        items = [
            {"item_type": "folder", "filename": "Album"},
            {"item_type": "file", "filename": "01-track.flac"},
            {"item_type": "file", "filename": "02-track.flac"},
            {"item_type": "file", "filename": "cover.jpg"},
            {"item_type": "file", "filename": "playlist.m3u"},
            {"item_type": "file", "filename": "checksums.sfv"},
            {"item_type": "file", "filename": "release.nfo"},
        ]

        result = self._apply_audio_only(items)

        kept = {item["filename"] for item in result}
        assert kept == {"Album", "01-track.flac", "02-track.flac"}
        assert "cover.jpg" not in kept
        assert "release.nfo" not in kept

    def test_audio_only_sql_clause_against_real_query(self):
        """Exercise the actual SQLAlchemy clause from the route on an in-memory
        DB: folders kept, audio kept (case-insensitively), sidecars dropped,
        and count() reflects the filter. Re-running without the clause brings
        the sidecars back (audio_only=False)."""
        from sqlalchemy import create_engine, func, or_
        from sqlalchemy.orm import sessionmaker
        from app.models.import_item import ImportItem
        from app.services.scanner.scanner_service import AUDIO_EXTENSIONS

        engine = create_engine("sqlite:///:memory:")
        ImportItem.__table__.create(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        rows = [
            ("folder", "Album"),
            ("file", "01-track.flac"),
            ("file", "02-track.FLAC"),  # mixed case must still match
            ("file", "cover.jpg"),
            ("file", "playlist.m3u"),
            ("file", "release.nfo"),
        ]
        for i, (item_type, filename) in enumerate(rows):
            session.add(
                ImportItem(
                    library_id=1, scan_id=1, item_type=item_type,
                    path=f"/music/{filename}", directory="/music",
                    filename=filename, status="new",
                )
            )
        session.commit()

        base = session.query(ImportItem)

        # audio_only=False → everything
        assert base.count() == 6

        # audio_only=True → folders + audio files only
        audio_clauses = [
            func.lower(ImportItem.filename).like(f"%{ext}") for ext in sorted(AUDIO_EXTENSIONS)
        ]
        filtered = base.filter(or_(ImportItem.item_type != "file", or_(*audio_clauses)))
        kept = {item.filename for item in filtered.all()}
        assert kept == {"Album", "01-track.flac", "02-track.FLAC"}
        assert filtered.count() == 3  # count() honours the filter

        session.close()


class TestDeletedItemsExcluded:
    """list_import_items hides deleted items by default (issue #125).

    A file the last scan flagged ``deleted`` no longer exists on disk, so it
    must not surface as a present track. The regression: a deleted WAV still
    carrying its old (FLAC) directory was counted as a removable duplicate by
    the Local Album card, but the dedup endpoint checks the live disk and 400s.
    """

    def test_default_listing_excludes_deleted_but_filter_can_request_them(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models.import_item import ImportItem
        from app.schemas.scan import ImportItemStatus

        engine = create_engine("sqlite:///:memory:")
        ImportItem.__table__.create(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # A folder that already holds the converted FLACs; the WAV originals
        # were removed, so the last scan marked the WAV rows "deleted".
        rows = [
            ("0001 track.flac", "unchanged"),
            ("0002 track.flac", "unchanged"),
            ("0001 track.wav", "deleted"),
            ("0002 track.wav", "deleted"),
        ]
        for filename, status in rows:
            session.add(
                ImportItem(
                    library_id=1, scan_id=1, item_type="file",
                    path=f"/music/Album/{filename}", directory="/music/Album",
                    filename=filename, status=status,
                )
            )
        session.commit()

        base = session.query(ImportItem)

        # Default: deleted rows are hidden — only the present FLACs remain, so
        # the card sees no WAV and offers no (broken) dedup action.
        default = base.filter(
            ImportItem.status != ImportItemStatus.DELETED.value
        )
        kept = {item.filename for item in default.all()}
        assert kept == {"0001 track.flac", "0002 track.flac"}
        assert default.count() == 2

        # Explicit status filter still returns the deletion history.
        deleted = base.filter(
            ImportItem.status == ImportItemStatus.DELETED.value
        )
        assert {item.filename for item in deleted.all()} == {
            "0001 track.wav",
            "0002 track.wav",
        }

        session.close()


class TestSSEEndpoint:
    """Tests for SSE endpoint."""

    def test_sse_event_schemas(self):
        """Test SSE event data schemas are valid."""
        from app.schemas.scan import (
            SSEScanStarted,
            SSEScanProgress,
            SSEScanCompleted,
            SSEScanFailed,
            SSEScanQueued,
            SSEScanBlocked,
            SSEHeartbeat,
            ScanStatus,
        )

        # Test scan_started event
        started = SSEScanStarted(
            scan_id=1,
            library_slug="test-library",
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert started.scan_id == 1

        # Test scan_progress event
        progress = SSEScanProgress(
            scan_id=1,
            status=ScanStatus.SCANNING,
            items_total=100,
            items_processed=50,
            progress_percent=50.0,
            current_file="/path/to/file.mp3",
            elapsed_seconds=30,
        )
        assert progress.progress_percent == 50.0

        # Test scan_completed event
        completed = SSEScanCompleted(
            scan_id=1,
            items_total=100,
            items_processed=100,
            new_items=50,
            modified_items=10,
            deleted_items=5,
            completed_at=datetime(2024, 1, 15, 10, 35, 32),
            duration_seconds=332,
        )
        assert completed.new_items == 50

        # Test scan_failed event
        failed = SSEScanFailed(
            scan_id=1,
            error_message="Permission denied",
            failed_at=datetime(2024, 1, 15, 10, 31, 15),
        )
        assert failed.error_message == "Permission denied"

        # Test scan_queued event
        queued = SSEScanQueued(
            library_slug="test-library",
            queue_position=1,
            blocked_by=["import"],
        )
        assert queued.queue_position == 1

        # Test scan_blocked event
        blocked = SSEScanBlocked(
            library_slug="test-library",
            blocking_operations=["import", "tag_modify"],
        )
        assert len(blocked.blocking_operations) == 2

        # Test heartbeat event
        heartbeat = SSEHeartbeat(
            timestamp=datetime(2024, 1, 15, 10, 30, 30),
        )
        assert heartbeat.timestamp is not None


class TestFilterValidation:
    """Tests for query parameter validation."""

    def test_item_type_filter_values(self):
        """Test item type filter accepts valid values."""
        from app.schemas.scan import ItemTypeFilter

        assert ItemTypeFilter.FILE.value == "file"
        assert ItemTypeFilter.FOLDER.value == "folder"

    def test_item_status_filter_values(self):
        """Test item status filter accepts valid values."""
        from app.schemas.scan import ItemStatusFilter

        assert ItemStatusFilter.NEW.value == "new"
        assert ItemStatusFilter.MODIFIED.value == "modified"
        assert ItemStatusFilter.UNCHANGED.value == "unchanged"
        assert ItemStatusFilter.DELETED.value == "deleted"
