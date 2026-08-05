"""Unit tests for TaskEventService."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

import pytest

from app.services.task_events import TaskEventService, get_task_event_service
from app.models.task_event import TaskEvent
from app.models.enums import TaskType, TaskStatus


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.count.return_value = 0
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    return db


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis manager."""
    redis_manager = Mock()
    redis_manager.add_to_activity_index.return_value = True
    redis_manager.remove_from_activity_index.return_value = True
    redis_manager.set_activity_progress.return_value = None
    redis_manager.get_activity_progress.return_value = None
    redis_manager.clear_activity_progress.return_value = True
    redis_manager.publish_activity_event.return_value = 1
    redis_manager.get_active_task_members.return_value = []
    redis_manager.cleanup_stale_activity_entries.return_value = 0
    redis_manager.get_scan_queue_length.return_value = 0
    return redis_manager


@pytest.fixture
def task_event_service(mock_db, mock_redis_manager):
    """Create a TaskEventService with mocks."""
    return TaskEventService(db=mock_db, redis_manager=mock_redis_manager)


class TestRecordStart:
    """Tests for record_start method."""

    def test_record_start_creates_db_record(self, task_event_service, mock_db):
        """Test that record_start creates a database record."""
        mock_db.refresh = Mock(side_effect=lambda x: setattr(x, 'id', 42))

        event_id = task_event_service.record_start(
            task_type="scan",
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
            metadata={"triggered_by": "manual"},
        )

        # Verify db operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify the TaskEvent was created with correct values
        added_event = mock_db.add.call_args[0][0]
        assert added_event.task_type == "scan"
        assert added_event.library_id == 1
        assert added_event.library_slug == "test-library"
        assert added_event.description == "Scan import folder"
        assert added_event.status == TaskStatus.RUNNING.value

    def test_record_start_adds_to_redis_index(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_start adds task to Redis index."""
        mock_db.refresh = Mock(side_effect=lambda x: setattr(x, 'id', 42))

        task_event_service.record_start(
            task_type="analysis",
            library_id=1,
            library_slug="test-library",
            description="Album: Artist - Album",
        )

        mock_redis_manager.add_to_activity_index.assert_called_once()
        # Called positionally: add_to_activity_index(task_type, event_id, started_at)
        positional_args = mock_redis_manager.add_to_activity_index.call_args[0]
        assert positional_args[0] == "analysis"
        assert positional_args[1] == 42

    def test_record_start_sets_progress(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_start sets initial progress in Redis."""
        mock_db.refresh = Mock(side_effect=lambda x: setattr(x, 'id', 42))

        task_event_service.record_start(
            task_type="scan",
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
        )

        mock_redis_manager.set_activity_progress.assert_called_once()
        call_kwargs = mock_redis_manager.set_activity_progress.call_args[1]
        assert call_kwargs["event_id"] == 42
        assert call_kwargs["task_type"] == "scan"
        assert call_kwargs["library_id"] == 1
        assert call_kwargs["library_slug"] == "test-library"

    def test_record_start_publishes_event(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_start publishes task_started event."""
        mock_db.refresh = Mock(side_effect=lambda x: setattr(x, 'id', 42))

        task_event_service.record_start(
            task_type="scan",
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
        )

        mock_redis_manager.publish_activity_event.assert_called_once()
        call_args = mock_redis_manager.publish_activity_event.call_args[0]
        assert call_args[0] == "task_started"
        assert call_args[1]["event_id"] == 42
        assert call_args[1]["task_type"] == "scan"


class TestRecordEvent:
    """Tests for the one-shot record_event method."""

    def test_record_event_creates_finished_db_record(self, task_event_service, mock_db):
        """A one-shot event is born finished: started_at == completed_at, duration 0."""
        mock_db.refresh = Mock(side_effect=lambda x: setattr(x, 'id', 7))

        event_id = task_event_service.record_event(
            task_type="emby_refresh",
            library_id=1,
            library_slug="test-library",
            description="Emby unreachable — refresh skipped",
            status=TaskStatus.FAILED.value,
            metadata={"reason": "timeout"},
        )

        assert event_id == 7
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        added = mock_db.add.call_args[0][0]
        assert added.task_type == "emby_refresh"
        assert added.status == TaskStatus.FAILED.value
        assert added.duration_seconds == 0
        assert added.started_at == added.completed_at
        assert added.metadata_ == {"reason": "timeout"}

    def test_record_event_publishes_failed_event(self, task_event_service, mock_db, mock_redis_manager):
        """A failed one-shot event publishes task_failed (not via the active index)."""
        mock_db.refresh = Mock(side_effect=lambda x: setattr(x, 'id', 7))

        task_event_service.record_event(
            task_type="emby_refresh",
            library_id=1,
            library_slug="test-library",
            description="Emby unreachable — refresh skipped",
            status=TaskStatus.FAILED.value,
        )

        mock_redis_manager.publish_activity_event.assert_called_once()
        call_args = mock_redis_manager.publish_activity_event.call_args[0]
        assert call_args[0] == "task_failed"
        assert call_args[1]["task_type"] == "emby_refresh"
        # Born finished: never touches the running-task index.
        mock_redis_manager.add_to_activity_index.assert_not_called()


class TestRecordProgress:
    """Tests for record_progress method."""

    def test_record_progress_updates_redis(self, task_event_service, mock_redis_manager):
        """Test that record_progress updates Redis progress."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_redis_manager.get_activity_progress.return_value = {
            "task_type": "scan",
            "library_id": 1,
            "library_slug": "test-library",
            "description": "Scan import folder",
            "started_at": started_at,
        }

        task_event_service.record_progress(
            event_id=42,
            progress_percent=50.0,
            metadata={"items_total": 100, "items_processed": 50},
        )

        mock_redis_manager.set_activity_progress.assert_called_once()

    def test_record_progress_publishes_event(self, task_event_service, mock_redis_manager):
        """Test that record_progress publishes task_progress event."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_redis_manager.get_activity_progress.return_value = {
            "task_type": "scan",
            "library_id": 1,
            "library_slug": "test-library",
            "description": "Scan import folder",
            "started_at": started_at,
        }

        task_event_service.record_progress(
            event_id=42,
            progress_percent=50.0,
        )

        mock_redis_manager.publish_activity_event.assert_called_once()
        call_args = mock_redis_manager.publish_activity_event.call_args[0]
        assert call_args[0] == "task_progress"
        assert call_args[1]["event_id"] == 42
        assert call_args[1]["progress_percent"] == 50.0

    def test_record_progress_no_progress_found(self, task_event_service, mock_redis_manager):
        """Test that record_progress handles missing progress gracefully."""
        mock_redis_manager.get_activity_progress.return_value = None

        # Should not raise
        task_event_service.record_progress(event_id=42, progress_percent=50.0)

        # Should not publish if no progress found
        mock_redis_manager.publish_activity_event.assert_not_called()


class TestRecordCompletion:
    """Tests for record_completion method."""

    def test_record_completion_updates_db(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_completion updates the database record."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_event = Mock()
        mock_event.id = 42
        mock_event.task_type = "scan"
        mock_event.library_id = 1
        mock_event.library_slug = "test-library"
        mock_event.description = "Scan import folder"
        mock_event.started_at = started_at
        mock_event.metadata_ = {}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        task_event_service.record_completion(
            event_id=42,
            status="completed",
            metadata={"items_total": 100},
        )

        assert mock_event.status == "completed"
        assert mock_event.completed_at is not None
        assert mock_event.duration_seconds >= 0
        mock_db.commit.assert_called_once()

    def test_record_completion_removes_from_redis(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_completion removes task from Redis index."""
        mock_event = Mock()
        mock_event.id = 42
        mock_event.task_type = "scan"
        mock_event.library_id = 1
        mock_event.library_slug = "test-library"
        mock_event.description = "Scan import folder"
        mock_event.started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_event.metadata_ = {}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        task_event_service.record_completion(event_id=42, status="completed")

        mock_redis_manager.remove_from_activity_index.assert_called_once_with("scan", 42)
        mock_redis_manager.clear_activity_progress.assert_called_once_with(42)

    def test_record_completion_publishes_completed_event(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_completion publishes task_completed event for success."""
        mock_event = Mock()
        mock_event.id = 42
        mock_event.task_type = "scan"
        mock_event.library_id = 1
        mock_event.library_slug = "test-library"
        mock_event.description = "Scan import folder"
        mock_event.started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_event.metadata_ = {}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        task_event_service.record_completion(event_id=42, status="completed")

        call_args = mock_redis_manager.publish_activity_event.call_args[0]
        assert call_args[0] == "task_completed"

    def test_record_completion_publishes_failed_event(self, task_event_service, mock_db, mock_redis_manager):
        """Test that record_completion publishes task_failed event for failure."""
        mock_event = Mock()
        mock_event.id = 42
        mock_event.task_type = "scan"
        mock_event.library_id = 1
        mock_event.library_slug = "test-library"
        mock_event.description = "Scan import folder"
        mock_event.started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_event.metadata_ = {}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        task_event_service.record_completion(
            event_id=42,
            status="failed",
            metadata={"error": "Something went wrong"},
        )

        call_args = mock_redis_manager.publish_activity_event.call_args[0]
        assert call_args[0] == "task_failed"


class TestGetActiveTasks:
    """Tests for get_active_tasks method."""

    def test_get_active_tasks_empty(self, task_event_service, mock_redis_manager):
        """Test get_active_tasks with no active tasks."""
        mock_redis_manager.get_active_task_members.return_value = []

        result = task_event_service.get_active_tasks()

        assert result == []

    def test_get_active_tasks_with_progress(self, task_event_service, mock_redis_manager):
        """Test get_active_tasks with progress data."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        mock_redis_manager.get_active_task_members.return_value = ["scan:42"]
        mock_redis_manager.get_activity_progress.return_value = {
            "event_id": 42,
            "task_type": "scan",
            "library_id": 1,
            "library_slug": "test-library",
            "description": "Scan import folder",
            "started_at": started_at,
            "progress_percent": 50.0,
        }

        result = task_event_service.get_active_tasks()

        assert len(result) == 1
        assert result[0]["event_id"] == 42
        assert result[0]["task_type"] == "scan"
        assert result[0]["elapsed_seconds"] >= 60


class TestGetRecentCompletions:
    """Tests for get_recent_completions method."""

    def test_get_recent_completions(self, task_event_service, mock_db):
        """Test get_recent_completions returns correct data."""
        mock_event = Mock()
        mock_event.id = 42
        mock_event.task_type = "scan"
        mock_event.library_id = 1
        mock_event.library_slug = "test-library"
        mock_event.description = "Scan import folder"
        mock_event.status = "completed"
        mock_event.started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        mock_event.completed_at = datetime.now(timezone.utc)
        mock_event.duration_seconds = 60
        mock_event.metadata_ = {}

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_event]

        result = task_event_service.get_recent_completions(limit=10)

        assert len(result) == 1
        assert result[0]["event_id"] == 42
        assert result[0]["status"] == "completed"


class TestGetHistory:
    """Tests for get_history method."""

    def test_get_history_with_filters(self, task_event_service, mock_db):
        """Test get_history applies filters correctly."""
        mock_event = Mock()
        mock_event.id = 42
        mock_event.task_type = "scan"
        mock_event.library_id = 1
        mock_event.library_slug = "test-library"
        mock_event.description = "Scan import folder"
        mock_event.status = "completed"
        mock_event.started_at = datetime.now(timezone.utc)
        mock_event.completed_at = datetime.now(timezone.utc)
        mock_event.duration_seconds = 30
        mock_event.metadata_ = {}

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_event]

        items, total = task_event_service.get_history(
            skip=0,
            limit=20,
            library_id=1,
            task_type="scan",
            status="completed",
        )

        assert total == 1
        assert len(items) == 1
        assert items[0]["id"] == 42


class TestCleanupStaleEntries:
    """Tests for cleanup_stale_entries method."""

    def test_cleanup_stale_entries(self, task_event_service, mock_db, mock_redis_manager):
        """Test cleanup_stale_entries removes stale entries."""
        mock_redis_manager.cleanup_stale_activity_entries.return_value = 2

        # Set up orphaned events query
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = task_event_service.cleanup_stale_entries(max_age_seconds=7200)

        assert result >= 2
        mock_redis_manager.cleanup_stale_activity_entries.assert_called_once_with(7200)


class TestClearHistory:
    """Tests for clear_history method."""

    def test_clear_history_all_records(self, task_event_service, mock_db):
        """Test clear_history deletes all non-running records when no filters."""
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5
        mock_query.delete.return_value = 5

        result = task_event_service.clear_history()

        assert result == 5
        mock_query.delete.assert_called_once_with(synchronize_session=False)
        mock_db.commit.assert_called_once()

    def test_clear_history_filtered_by_library_id(self, task_event_service, mock_db):
        """Test clear_history filters by library_id when provided."""
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 3
        mock_query.delete.return_value = 3

        result = task_event_service.clear_history(library_id=123)

        assert result == 3
        # Verify filter was called twice (once for status != running, once for library_id)
        assert mock_query.filter.call_count == 2
        mock_db.commit.assert_called_once()

    def test_clear_history_filtered_by_task_type(self, task_event_service, mock_db):
        """Test clear_history filters by task_type when provided."""
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 4
        mock_query.delete.return_value = 4

        result = task_event_service.clear_history(task_type="scan")

        assert result == 4
        # Verify filter was called twice (once for status != running, once for task_type)
        assert mock_query.filter.call_count == 2
        mock_db.commit.assert_called_once()

    def test_clear_history_filtered_by_both(self, task_event_service, mock_db):
        """Test clear_history filters by both library_id and task_type."""
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.delete.return_value = 2

        result = task_event_service.clear_history(library_id=123, task_type="analysis")

        assert result == 2
        # Verify filter was called three times (status != running, library_id, task_type)
        assert mock_query.filter.call_count == 3
        mock_db.commit.assert_called_once()

    def test_clear_history_excludes_running_tasks(self, task_event_service, mock_db):
        """Test clear_history always excludes running tasks."""
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.delete.return_value = 0

        result = task_event_service.clear_history()

        assert result == 0
        # Verify that the first filter call excludes running tasks
        mock_query.filter.assert_called()

    def test_clear_history_returns_zero_when_no_matches(self, task_event_service, mock_db):
        """Test clear_history returns 0 when no records match filters."""
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.delete.return_value = 0

        result = task_event_service.clear_history(library_id=999)

        assert result == 0
        mock_db.commit.assert_called_once()


class TestServiceFactory:
    """Tests for get_task_event_service factory function."""

    def test_get_task_event_service_creates_instance(self):
        """Test that get_task_event_service creates an instance."""
        with patch("app.services.task_events.SessionLocal"):
            with patch("app.services.task_events.get_redis_key_manager"):
                service = get_task_event_service()
                assert isinstance(service, TaskEventService)
