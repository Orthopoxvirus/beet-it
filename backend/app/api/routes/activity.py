"""API routes for activity monitor operations."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.activity import (
    ActivitySnapshotResponse,
    ActivityHistoryResponse,
    ActiveTask,
    QueuedTask,
    CompletedTask,
    ActivityCounts,
    TaskEventHistoryItem,
    TaskType,
    TaskStatus,
    ClearHistoryResponse,
)
from app.services.task_events import get_task_event_service
from app.services.redis_keys import get_redis_key_manager

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/activity", tags=["activity"])


def get_redis_manager():
    """Get a Redis key manager instance."""
    return get_redis_key_manager(settings.redis_url)


@router.get("", response_model=ActivitySnapshotResponse)
def get_activity_snapshot(db: Session = Depends(get_db)):
    """Get a snapshot of current activity.

    Returns information about:
    - Currently running tasks
    - Queued tasks awaiting execution
    - Last 10 completed tasks
    - Summary counts
    """
    task_service = get_task_event_service(db=db)

    try:
        # Get active tasks from Redis
        active_tasks_data = task_service.get_active_tasks()
        active_tasks = [
            ActiveTask(
                event_id=task["event_id"],
                task_type=TaskType(task["task_type"]),
                library_id=task.get("library_id"),
                library_slug=task.get("library_slug", ""),
                description=task.get("description", ""),
                status=TaskStatus(task["status"]),
                started_at=task["started_at"] if isinstance(task["started_at"], datetime) else datetime.fromisoformat(str(task["started_at"])),
                elapsed_seconds=task.get("elapsed_seconds", 0),
                progress_percent=task.get("progress_percent"),
                metadata=task.get("metadata", {}),
            )
            for task in active_tasks_data
        ]

        # Get queued tasks
        queued_tasks_data = task_service.get_queued_tasks()
        queued_tasks = [
            QueuedTask(
                task_type=TaskType(task["task_type"]),
                library_id=task.get("library_id"),
                library_slug=task.get("library_slug", ""),
                description=task.get("description", ""),
                queue_position=task["queue_position"],
                queued_at=task["queued_at"] if isinstance(task["queued_at"], datetime) else datetime.fromisoformat(str(task["queued_at"])),
            )
            for task in queued_tasks_data
        ]

        # Get recent completions
        recent_data = task_service.get_recent_completions(limit=10)
        recent_completions = [
            CompletedTask(
                event_id=task["event_id"],
                task_type=TaskType(task["task_type"]),
                library_id=task.get("library_id"),
                library_slug=task.get("library_slug", ""),
                description=task.get("description", ""),
                status=TaskStatus(task["status"]),
                started_at=task["started_at"],
                completed_at=task["completed_at"],
                duration_seconds=task.get("duration_seconds", 0),
                metadata=task.get("metadata", {}),
            )
            for task in recent_data
        ]

        counts = ActivityCounts(
            active=len(active_tasks),
            queued=len(queued_tasks),
            recent=len(recent_completions),
        )

        return ActivitySnapshotResponse(
            active_tasks=active_tasks,
            queued_tasks=queued_tasks,
            recent_completions=recent_completions,
            counts=counts,
        )

    finally:
        task_service.close()


@router.get("/stream")
async def get_activity_stream():
    """Server-Sent Events endpoint for real-time activity updates.

    This endpoint streams task lifecycle events including:
    - task_started: When a task begins
    - task_progress: Periodic progress updates
    - task_completed: When a task finishes successfully
    - task_failed: When a task fails
    - heartbeat: Keep-alive every 30 seconds
    """
    redis_manager = get_redis_manager()

    async def event_generator():
        """Generate SSE events from Redis pub/sub."""
        pubsub = redis_manager.subscribe_activity_events()
        last_heartbeat = datetime.now(timezone.utc)

        try:
            while True:
                # Non-blocking check - avoid blocking the async event loop
                message = pubsub.get_message()

                if message and message["type"] == "message":
                    try:
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        event_data = json.loads(data)

                        event_type = event_data.get("event", "message")
                        event_payload = event_data.get("data", event_data)

                        yield f"event: {event_type}\ndata: {json.dumps(event_payload)}\n\n"
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Error processing SSE message: {e}")

                # Send heartbeat every 30 seconds
                now = datetime.now(timezone.utc)
                if (now - last_heartbeat).total_seconds() >= 30:
                    heartbeat_data = {"timestamp": now.isoformat()}
                    yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"
                    last_heartbeat = now

                # Small delay to prevent tight loop
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.debug("Activity SSE connection closed")
        finally:
            pubsub.unsubscribe()
            pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/history", response_model=ActivityHistoryResponse)
def get_activity_history(
    skip: int = Query(0, ge=0, description="Number of records to skip (offset)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return (max: 100)"),
    library_id: Optional[int] = Query(None, description="Filter by library ID"),
    task_type: Optional[TaskType] = Query(None, description="Filter by task type"),
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """Get paginated task history with optional filters.

    Returns a paginated list of past task events, ordered by most recent first.
    Supports filtering by library, task type, and status.
    """
    task_service = get_task_event_service(db=db)

    try:
        # Convert enums to strings for service
        task_type_str = task_type.value if task_type else None
        status_str = status.value if status else None

        items_data, total = task_service.get_history(
            skip=skip,
            limit=limit,
            library_id=library_id,
            task_type=task_type_str,
            status=status_str,
        )

        items = [
            TaskEventHistoryItem(
                id=item["id"],
                task_type=TaskType(item["task_type"]),
                library_id=item.get("library_id"),
                library_slug=item.get("library_slug", ""),
                description=item.get("description", ""),
                status=TaskStatus(item["status"]),
                started_at=item["started_at"],
                completed_at=item.get("completed_at"),
                duration_seconds=item.get("duration_seconds"),
                metadata=item.get("metadata", {}),
            )
            for item in items_data
        ]

        return ActivityHistoryResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
        )

    finally:
        task_service.close()


@router.delete(
    "/history",
    response_model=ClearHistoryResponse,
    summary="Clear activity history",
    description="Permanently deletes task history records. Running tasks are excluded.",
)
def clear_activity_history(
    library_id: Optional[int] = Query(
        default=None,
        ge=1,
        description="Filter deletion to specific library ID"
    ),
    task_type: Optional[TaskType] = Query(
        default=None,
        description="Filter deletion to specific task type"
    ),
    db: Session = Depends(get_db),
) -> ClearHistoryResponse:
    """Clear activity history records.

    Permanently deletes task_events records matching the provided filters.
    Running tasks are always excluded from deletion.

    Returns:
        ClearHistoryResponse with the count of deleted records.
    """
    task_service = get_task_event_service(db=db)

    try:
        # Convert enum to string for service
        task_type_str = task_type.value if task_type else None

        deleted_count = task_service.clear_history(
            library_id=library_id,
            task_type=task_type_str,
        )

        return ClearHistoryResponse(deleted_count=deleted_count)

    finally:
        task_service.close()
