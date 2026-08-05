"""Integration tests for activity API endpoints."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.library import Library
from app.models.task_event import TaskEvent
from app.models.enums import TaskType, TaskStatus
from app.schemas.activity import (
    ActivitySnapshotResponse,
    ActivityHistoryResponse,
    ActiveTask,
    QueuedTask,
    CompletedTask,
    ActivityCounts,
    TaskEventHistoryItem,
    ClearHistoryResponse,
)


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis key manager."""
    manager = Mock()
    manager.get_active_task_members.return_value = []
    manager.get_activity_progress.return_value = None
    manager.get_scan_queue_length.return_value = 0
    manager.subscribe_activity_events.return_value = Mock()
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
def mock_task_event():
    """Create a mock task event."""
    event = Mock(spec=TaskEvent)
    event.id = 42
    event.task_type = "scan"
    event.library_id = 1
    event.library_slug = "test-library"
    event.description = "Scan import folder"
    event.status = "completed"
    event.started_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    event.completed_at = datetime(2024, 1, 15, 10, 35, 32, tzinfo=timezone.utc)
    event.duration_seconds = 332
    event.metadata_ = {"items_total": 150}
    return event


class TestActivitySnapshotResponseSchema:
    """Tests for activity snapshot response schema."""

    def test_activity_snapshot_response_schema(self):
        """Test activity snapshot response matches expected schema."""
        response = ActivitySnapshotResponse(
            active_tasks=[],
            queued_tasks=[],
            recent_completions=[],
            counts=ActivityCounts(active=0, queued=0, recent=0),
        )

        assert response.active_tasks == []
        assert response.queued_tasks == []
        assert response.recent_completions == []
        assert response.counts.active == 0

    def test_active_task_schema(self):
        """Test active task schema."""
        started_at = datetime.now(timezone.utc)
        task = ActiveTask(
            event_id=42,
            task_type=TaskType.SCAN,
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
            status=TaskStatus.RUNNING,
            started_at=started_at,
            elapsed_seconds=60,
            progress_percent=50.0,
            metadata={"items_total": 100},
        )

        assert task.event_id == 42
        assert task.task_type == TaskType.SCAN
        assert task.progress_percent == 50.0

    def test_queued_task_schema(self):
        """Test queued task schema."""
        queued_at = datetime.now(timezone.utc)
        task = QueuedTask(
            task_type=TaskType.SCAN,
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
            queue_position=1,
            queued_at=queued_at,
        )

        assert task.queue_position == 1
        assert task.task_type == TaskType.SCAN

    def test_completed_task_schema(self):
        """Test completed task schema."""
        started_at = datetime.now(timezone.utc)
        completed_at = datetime.now(timezone.utc)
        task = CompletedTask(
            event_id=42,
            task_type=TaskType.SCAN,
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
            status=TaskStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=60,
            metadata={},
        )

        assert task.event_id == 42
        assert task.status == TaskStatus.COMPLETED


class TestActivityHistoryResponseSchema:
    """Tests for activity history response schema."""

    def test_activity_history_response_schema(self):
        """Test activity history response matches expected schema."""
        response = ActivityHistoryResponse(
            items=[],
            total=0,
            skip=0,
            limit=20,
        )

        assert response.items == []
        assert response.total == 0
        assert response.skip == 0
        assert response.limit == 20

    def test_task_event_history_item_schema(self):
        """Test task event history item schema."""
        started_at = datetime.now(timezone.utc)
        item = TaskEventHistoryItem(
            id=42,
            task_type=TaskType.SCAN,
            library_id=1,
            library_slug="test-library",
            description="Scan import folder",
            status=TaskStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            duration_seconds=60,
            metadata={},
        )

        assert item.id == 42
        assert item.task_type == TaskType.SCAN
        assert item.status == TaskStatus.COMPLETED


class TestActivitySnapshotEndpoint:
    """Tests for GET /api/v1/activity endpoint."""

    def test_activity_snapshot_empty(self):
        """Test activity snapshot when no tasks are active."""
        mock_task_service = Mock()
        mock_task_service.get_active_tasks.return_value = []
        mock_task_service.get_queued_tasks.return_value = []
        mock_task_service.get_recent_completions.return_value = []
        mock_task_service.close = Mock()

        with patch("app.api.routes.activity.get_task_event_service", return_value=mock_task_service):
            from app.api.routes.activity import get_activity_snapshot
            from unittest.mock import MagicMock
            mock_db = MagicMock()

            response = get_activity_snapshot(db=mock_db)

            assert response.counts.active == 0
            assert response.counts.queued == 0
            assert response.counts.recent == 0

    def test_activity_snapshot_with_active_task(self):
        """Test activity snapshot with an active task."""
        started_at = datetime.now(timezone.utc)
        mock_task_service = Mock()
        mock_task_service.get_active_tasks.return_value = [
            {
                "event_id": 42,
                "task_type": "scan",
                "library_id": 1,
                "library_slug": "test-library",
                "description": "Scan import folder",
                "status": "running",
                "started_at": started_at,
                "elapsed_seconds": 60,
                "progress_percent": 50.0,
                "metadata": {},
            }
        ]
        mock_task_service.get_queued_tasks.return_value = []
        mock_task_service.get_recent_completions.return_value = []
        mock_task_service.close = Mock()

        with patch("app.api.routes.activity.get_task_event_service", return_value=mock_task_service):
            from app.api.routes.activity import get_activity_snapshot
            from unittest.mock import MagicMock
            mock_db = MagicMock()

            response = get_activity_snapshot(db=mock_db)

            assert response.counts.active == 1
            assert len(response.active_tasks) == 1
            assert response.active_tasks[0].event_id == 42


class TestActivityHistoryEndpoint:
    """Tests for GET /api/v1/activity/history endpoint."""

    def test_activity_history_empty(self):
        """Test activity history when no events exist."""
        mock_task_service = Mock()
        mock_task_service.get_history.return_value = ([], 0)
        mock_task_service.close = Mock()

        with patch("app.api.routes.activity.get_task_event_service", return_value=mock_task_service):
            from app.api.routes.activity import get_activity_history
            from unittest.mock import MagicMock
            mock_db = MagicMock()

            response = get_activity_history(
                skip=0,
                limit=20,
                library_id=None,
                task_type=None,
                status=None,
                db=mock_db,
            )

            assert response.total == 0
            assert len(response.items) == 0

    def test_activity_history_with_filters(self):
        """Test activity history with filters applied."""
        started_at = datetime.now(timezone.utc)
        completed_at = datetime.now(timezone.utc)
        mock_task_service = Mock()
        mock_task_service.get_history.return_value = (
            [
                {
                    "id": 42,
                    "task_type": "scan",
                    "library_id": 1,
                    "library_slug": "test-library",
                    "description": "Scan import folder",
                    "status": "completed",
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_seconds": 60,
                    "metadata": {},
                }
            ],
            1,
        )
        mock_task_service.close = Mock()

        with patch("app.api.routes.activity.get_task_event_service", return_value=mock_task_service):
            from app.api.routes.activity import get_activity_history
            from app.schemas.activity import TaskType, TaskStatus
            from unittest.mock import MagicMock
            mock_db = MagicMock()

            response = get_activity_history(
                skip=0,
                limit=20,
                library_id=1,
                task_type=TaskType.SCAN,
                status=TaskStatus.COMPLETED,
                db=mock_db,
            )

            assert response.total == 1
            assert len(response.items) == 1
            assert response.items[0].id == 42

            # Verify service was called with correct filters
            mock_task_service.get_history.assert_called_once_with(
                skip=0,
                limit=20,
                library_id=1,
                task_type="scan",
                status="completed",
            )


class TestTaskTypeEnum:
    """Tests for TaskType enum."""

    def test_task_type_values(self):
        """Test TaskType enum has expected values."""
        assert TaskType.SCAN.value == "scan"
        assert TaskType.ANALYSIS.value == "analysis"
        assert TaskType.TAG_WRITE.value == "tag_write"
        assert TaskType.IMPORT.value == "import"


class TestTaskStatusEnum:
    """Tests for TaskStatus enum."""

    def test_task_status_values(self):
        """Test TaskStatus enum has expected values."""
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestClearHistoryResponseSchema:
    """Tests for clear history response schema."""

    def test_clear_history_response_schema(self):
        """Test clear history response matches expected schema."""
        response = ClearHistoryResponse(deleted_count=42)

        assert response.deleted_count == 42

    def test_clear_history_response_zero_count(self):
        """Test clear history response with zero count."""
        response = ClearHistoryResponse(deleted_count=0)

        assert response.deleted_count == 0


class TestClearActivityHistoryService:
    """Tests for clear activity history service integration."""

    def test_clear_history_all_records(self):
        """Test clearing all activity history via service."""
        from app.services.task_events import TaskEventService

        mock_db = Mock()
        mock_redis = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 25
        mock_query.delete.return_value = 25

        service = TaskEventService(db=mock_db, redis_manager=mock_redis)
        result = service.clear_history()

        assert result == 25
        mock_query.delete.assert_called_once_with(synchronize_session=False)

    def test_clear_history_by_library_id(self):
        """Test clearing activity history filtered by library_id."""
        from app.services.task_events import TaskEventService

        mock_db = Mock()
        mock_redis = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 10
        mock_query.delete.return_value = 10

        service = TaskEventService(db=mock_db, redis_manager=mock_redis)
        result = service.clear_history(library_id=123)

        assert result == 10
        # Filter called twice: status != running, library_id
        assert mock_query.filter.call_count == 2

    def test_clear_history_by_task_type(self):
        """Test clearing activity history filtered by task_type."""
        from app.services.task_events import TaskEventService

        mock_db = Mock()
        mock_redis = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 15
        mock_query.delete.return_value = 15

        service = TaskEventService(db=mock_db, redis_manager=mock_redis)
        result = service.clear_history(task_type="scan")

        assert result == 15
        # Filter called twice: status != running, task_type
        assert mock_query.filter.call_count == 2

    def test_clear_history_by_multiple_filters(self):
        """Test clearing activity history with multiple filters."""
        from app.services.task_events import TaskEventService

        mock_db = Mock()
        mock_redis = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5
        mock_query.delete.return_value = 5

        service = TaskEventService(db=mock_db, redis_manager=mock_redis)
        result = service.clear_history(library_id=123, task_type="analysis")

        assert result == 5
        # Filter called three times: status != running, library_id, task_type
        assert mock_query.filter.call_count == 3

    def test_clear_history_no_matches(self):
        """Test clearing activity history when no records match."""
        from app.services.task_events import TaskEventService

        mock_db = Mock()
        mock_redis = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.delete.return_value = 0

        service = TaskEventService(db=mock_db, redis_manager=mock_redis)
        result = service.clear_history(library_id=999)

        assert result == 0

    def test_clear_history_commits_transaction(self):
        """Test that clearing activity history commits the transaction."""
        from app.services.task_events import TaskEventService

        mock_db = Mock()
        mock_redis = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 3
        mock_query.delete.return_value = 3

        service = TaskEventService(db=mock_db, redis_manager=mock_redis)
        service.clear_history()

        mock_db.commit.assert_called_once()


class TestTaskTypeSingleSource:
    """The activity schemas must accept every task type the workers record.

    A stale enum copy in schemas/activity.py once 500'd /activity for every
    value added only to models.enums (cleanup, bpm_backfill).
    """

    def test_schema_tasktype_is_models_tasktype(self):
        from app.models import enums
        from app.schemas import activity

        assert activity.TaskType is enums.TaskType
        assert activity.TaskStatus is enums.TaskStatus

    def test_all_recorded_task_types_parse(self):
        from app.models.enums import TaskType
        from app.schemas.activity import TaskType as SchemaTaskType

        for task_type in TaskType:
            assert SchemaTaskType(task_type.value) is task_type
