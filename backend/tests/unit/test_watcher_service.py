"""Unit tests for WatcherService."""

import os
import tempfile
import threading
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.watcher.watcher_service import (
    WatcherService,
    ImportFolderEventHandler,
)


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis key manager."""
    manager = Mock()
    manager.has_blocking_operations.return_value = False
    manager.set_watcher_state.return_value = None
    manager.set_heartbeat.return_value = None
    manager.check_heartbeat.return_value = True
    manager.clear_heartbeat.return_value = True
    manager.get_watcher_state.return_value = {"active": True, "pending_scan": False}
    return manager


@pytest.fixture
def watcher_service(mock_redis_manager):
    """Create a WatcherService with mock Redis."""
    return WatcherService(
        redis_manager=mock_redis_manager,
        debounce_seconds=30,
        heartbeat_interval=10,
    )


class TestImportFolderEventHandler:
    """Tests for ImportFolderEventHandler."""

    def test_is_ignored_file_hidden(self):
        """Test that hidden files are ignored."""
        handler = ImportFolderEventHandler(
            library_id=1,
            redis_manager=Mock(),
        )

        assert handler._is_ignored_file("/path/.hidden") is True
        assert handler._is_ignored_file("/path/.DS_Store") is True

    def test_is_ignored_file_temp(self):
        """Test that temp files are ignored."""
        handler = ImportFolderEventHandler(
            library_id=1,
            redis_manager=Mock(),
        )

        assert handler._is_ignored_file("/path/file.tmp") is True
        assert handler._is_ignored_file("/path/file.part") is True
        assert handler._is_ignored_file("/path/file.crdownload") is True
        assert handler._is_ignored_file("/path/file~") is True
        assert handler._is_ignored_file("/path/~$document.docx") is True

    def test_is_ignored_file_normal(self):
        """Test that normal files are not ignored."""
        handler = ImportFolderEventHandler(
            library_id=1,
            redis_manager=Mock(),
        )

        assert handler._is_ignored_file("/path/song.mp3") is False
        assert handler._is_ignored_file("/path/album.flac") is False

    def test_should_process_event_no_blocking(self):
        """Test event processing when no blocking operations."""
        mock_redis = Mock()
        mock_redis.has_blocking_operations.return_value = False

        handler = ImportFolderEventHandler(
            library_id=1,
            redis_manager=mock_redis,
        )

        assert handler._should_process_event() is True

    def test_should_process_event_with_blocking(self):
        """Test event processing when blocking operations present."""
        mock_redis = Mock()
        mock_redis.has_blocking_operations.return_value = True

        handler = ImportFolderEventHandler(
            library_id=1,
            redis_manager=mock_redis,
        )

        assert handler._should_process_event() is False


class TestWatcherService:
    """Tests for WatcherService."""

    def test_start_watcher_invalid_path(self, watcher_service):
        """Test starting watcher with invalid path."""
        result = watcher_service.start_watcher(1, "/nonexistent/path")

        assert result is False

    def test_start_watcher_valid_path(self, watcher_service):
        """Test starting watcher with valid path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = watcher_service.start_watcher(1, tmpdir)

            assert result is True
            assert watcher_service.is_watching(1) is True

            # Cleanup
            watcher_service.stop_watcher(1)

    def test_start_watcher_already_watching(self, watcher_service):
        """Test starting watcher when already watching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher_service.start_watcher(1, tmpdir)
            result = watcher_service.start_watcher(1, tmpdir)

            assert result is True  # Should return True even if already watching

            # Cleanup
            watcher_service.stop_watcher(1)

    def test_stop_watcher(self, watcher_service):
        """Test stopping a watcher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher_service.start_watcher(1, tmpdir)
            result = watcher_service.stop_watcher(1)

            assert result is True
            assert watcher_service.is_watching(1) is False

    def test_stop_watcher_not_running(self, watcher_service):
        """Test stopping a watcher that's not running."""
        result = watcher_service.stop_watcher(999)

        assert result is False

    def test_is_watching(self, watcher_service):
        """Test checking if library is being watched."""
        assert watcher_service.is_watching(1) is False

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher_service.start_watcher(1, tmpdir)
            assert watcher_service.is_watching(1) is True

            watcher_service.stop_watcher(1)
            assert watcher_service.is_watching(1) is False

    def test_get_watched_libraries(self, watcher_service):
        """Test getting list of watched libraries."""
        assert watcher_service.get_watched_libraries() == []

        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                watcher_service.start_watcher(1, tmpdir1)
                watcher_service.start_watcher(2, tmpdir2)

                watched = watcher_service.get_watched_libraries()
                assert 1 in watched
                assert 2 in watched

                # Cleanup
                watcher_service.stop_all()

    def test_stop_all(self, watcher_service):
        """Test stopping all watchers."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                watcher_service.start_watcher(1, tmpdir1)
                watcher_service.start_watcher(2, tmpdir2)

                watcher_service.stop_all()

                assert watcher_service.get_watched_libraries() == []

    def test_check_health_healthy(self, watcher_service, mock_redis_manager):
        """Test health check when watcher is healthy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher_service.start_watcher(1, tmpdir)

            result = watcher_service.check_health(1)

            assert result is True

            # Cleanup
            watcher_service.stop_watcher(1)

    def test_check_health_not_running(self, watcher_service):
        """Test health check when watcher is not running."""
        result = watcher_service.check_health(999)

        assert result is False

    def test_set_scan_trigger_callback(self, watcher_service):
        """Test setting scan trigger callback."""
        callback = Mock()

        watcher_service.set_scan_trigger_callback(callback)

        assert watcher_service._on_scan_trigger == callback


class TestWatcherServiceDebounce:
    """Tests for debounce behavior in WatcherService."""

    def test_on_change_detected_new_debounce(self, watcher_service, mock_redis_manager):
        """Test change detection starts new debounce."""
        mock_redis_manager.set_debounce.return_value = True

        watcher_service._on_change_detected(1)

        mock_redis_manager.set_debounce.assert_called_once_with(1, 30)

    def test_on_change_detected_refresh_debounce(self, watcher_service, mock_redis_manager):
        """Test change detection refreshes existing debounce."""
        mock_redis_manager.set_debounce.return_value = False

        watcher_service._on_change_detected(1)

        mock_redis_manager.set_debounce.assert_called_once()
        mock_redis_manager.refresh_debounce.assert_called_once_with(1, 30)
