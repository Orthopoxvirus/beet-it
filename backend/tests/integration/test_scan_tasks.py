"""Integration tests for scan Celery tasks."""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.tasks.scan_tasks import (
    trigger_scan,
    execute_scan,
    operation_lock,
)


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis key manager."""
    with patch("app.tasks.scan_tasks.get_redis_manager") as mock_get:
        manager = Mock()
        manager.check_debounce.return_value = False
        manager.set_watcher_state.return_value = None
        manager.get_active_operations.return_value = []
        manager.get_scan_progress.return_value = None
        manager.set_scan_progress.return_value = None
        manager.clear_scan_progress.return_value = True
        manager.publish_scan_event.return_value = 1
        manager.enqueue_scan.return_value = 1
        manager.dequeue_scan.return_value = None
        mock_get.return_value = manager
        yield manager


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    with patch("app.tasks.scan_tasks.get_db") as mock_get:
        session = Mock()
        mock_get.return_value = session
        yield session


class TestOperationLock:
    """Tests for operation lock context manager."""

    def test_operation_lock_acquire_and_release(self, mock_redis_manager):
        """Test operation lock acquires and releases correctly."""
        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            with operation_lock(1, "import", mock_redis_manager):
                mock_redis_manager.acquire_operation_lock.assert_called_once_with(1, "import")

            mock_redis_manager.release_operation_lock.assert_called_once_with(1, "import")

    def test_operation_lock_releases_on_exception(self, mock_redis_manager):
        """Test operation lock releases even on exception."""
        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            try:
                with operation_lock(1, "import", mock_redis_manager):
                    raise ValueError("Test error")
            except ValueError:
                pass

            mock_redis_manager.release_operation_lock.assert_called_once_with(1, "import")


class TestTriggerScan:
    """Tests for trigger_scan task."""

    def test_trigger_scan_debounce_active(self, mock_redis_manager):
        """Test trigger_scan defers when debounce is active."""
        mock_redis_manager.check_debounce.return_value = True
        mock_redis_manager.get_debounce_ttl.return_value = 15

        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            result = trigger_scan(library_id=1, triggered_by="watcher")

        assert result["status"] == "deferred"
        assert "remaining_seconds" in result

    def test_trigger_scan_blocked_by_operations(self, mock_redis_manager):
        """Test trigger_scan queues when blocked by operations."""
        mock_redis_manager.check_debounce.return_value = False
        mock_redis_manager.get_active_operations.return_value = ["import"]
        mock_redis_manager.enqueue_scan.return_value = 1

        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            result = trigger_scan(library_id=1, triggered_by="watcher")

        assert result["status"] == "queued"
        assert result["queue_position"] == 1
        assert "import" in result["blocking_operations"]

    def test_trigger_scan_starts_scan(self, mock_redis_manager):
        """Test trigger_scan starts scan when not blocked."""
        mock_redis_manager.check_debounce.return_value = False
        mock_redis_manager.get_active_operations.return_value = []
        mock_redis_manager.get_scan_progress.return_value = None

        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            with patch("app.tasks.scan_tasks.execute_scan.delay") as mock_execute:
                result = trigger_scan(library_id=1, triggered_by="watcher")

        assert result["status"] == "started"
        mock_execute.assert_called_once_with(1, "watcher")


class TestExecuteScan:
    """Tests for execute_scan task."""

    def test_execute_scan_library_not_found(self, mock_redis_manager, mock_db_session):
        """Test execute_scan handles missing library."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            with patch("app.tasks.scan_tasks.get_db", return_value=mock_db_session):
                result = execute_scan(library_id=999, triggered_by="manual")

        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_execute_scan_no_import_path(self, mock_redis_manager, mock_db_session):
        """Test execute_scan handles missing import path."""
        mock_library = Mock()
        mock_library.id = 1
        mock_library.import_path = None
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_library

        with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
            with patch("app.tasks.scan_tasks.get_db", return_value=mock_db_session):
                result = execute_scan(library_id=1, triggered_by="manual")

        assert result["status"] == "error"
        assert "import path" in result["message"].lower()

    def test_execute_scan_success(self, mock_redis_manager, mock_db_session):
        """Test execute_scan completes successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test.mp3")
            with open(test_file, "w") as f:
                f.write("test")

            # Setup mock library
            mock_library = Mock()
            mock_library.id = 1
            mock_library.slug = "test-library"
            mock_library.import_path = tmpdir

            # Setup mock scan
            mock_scan = Mock()
            mock_scan.id = 1
            mock_scan.started_at = datetime.now(timezone.utc)
            mock_scan.status = "scanning"
            mock_scan.items_total = 0
            mock_scan.items_processed = 0
            mock_scan.error_message = None

            # Setup mock queries
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_library
            mock_db_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
            mock_db_session.add.return_value = None
            mock_db_session.commit.return_value = None
            mock_db_session.refresh.side_effect = lambda x: setattr(x, 'id', 1) if not hasattr(x, 'id') or x.id is None else None

            # Return None explicitly so the post-scan queue check does not try
            # to dispatch a Celery task with a Mock-shaped payload.
            mock_redis_manager.dequeue_scan.return_value = None
            # Also required so TaskEventService.record_progress can compute an elapsed
            # time (without a payload the Mock .get() path returns sub-Mocks and
            # datetime arithmetic fails).
            mock_redis_manager.get_activity_progress.return_value = None

            # Stub task_event_service so activity recording is a no-op in this test.
            mock_task_event_service = Mock()
            mock_task_event_service.record_start.return_value = None

            with patch("app.tasks.scan_tasks.get_redis_manager", return_value=mock_redis_manager):
                with patch("app.tasks.scan_tasks.get_db", return_value=mock_db_session):
                    with patch(
                        "app.tasks.scan_tasks.get_task_event_service",
                        return_value=mock_task_event_service,
                    ):
                        with patch("app.tasks.scan_tasks.ImportScan") as MockScan:
                            MockScan.return_value = mock_scan

                            result = execute_scan(library_id=1, triggered_by="manual")

            # Verify scan was completed
            assert mock_scan.status == "completed"
            mock_redis_manager.publish_scan_event.assert_called()


class TestScanQueueProcessing:
    """Tests for scan queue processing."""

    def test_process_scan_queue_empty(self, mock_redis_manager):
        """Test processing empty queue does nothing."""
        mock_redis_manager.dequeue_scan.return_value = None

        from app.tasks.scan_tasks import _process_scan_queue

        with patch("app.tasks.scan_tasks.trigger_scan.delay") as mock_trigger:
            _process_scan_queue(1, mock_redis_manager)

        mock_trigger.assert_not_called()

    def test_process_scan_queue_with_item(self, mock_redis_manager):
        """Test processing queue with item triggers scan."""
        mock_redis_manager.dequeue_scan.return_value = {
            "triggered_by": "manual",
            "queued_at": "2024-01-01T00:00:00",
        }

        from app.tasks.scan_tasks import _process_scan_queue

        with patch("app.tasks.scan_tasks.trigger_scan.delay") as mock_trigger:
            _process_scan_queue(1, mock_redis_manager)

        mock_trigger.assert_called_once_with(1, "manual")
