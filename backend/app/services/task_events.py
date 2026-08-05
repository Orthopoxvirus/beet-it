"""Service for recording and querying task events.

This service manages the lifecycle of task events, providing both
permanent storage in PostgreSQL and real-time tracking in Redis.
It serves as the core of the Activity Monitor feature.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import SessionLocal
from app.models.task_event import TaskEvent
from app.models.enums import TaskType, TaskStatus
from app.services.redis_keys import RedisKeyManager, get_redis_key_manager
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TaskEventService:
    """Service for managing task event lifecycle and queries."""

    def __init__(
        self,
        db: Optional[Session] = None,
        redis_manager: Optional[RedisKeyManager] = None,
    ):
        """Initialize the service.

        Args:
            db: Optional database session. Creates one if not provided.
            redis_manager: Optional Redis manager. Creates one if not provided.
        """
        self._db = db
        self._redis_manager = redis_manager
        self._owns_db = db is None

    @property
    def db(self) -> Session:
        """Get the database session."""
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    @property
    def redis_manager(self) -> RedisKeyManager:
        """Get the Redis manager."""
        if self._redis_manager is None:
            self._redis_manager = get_redis_key_manager(settings.redis_url)
        return self._redis_manager

    def close(self) -> None:
        """Close the database session if we own it."""
        if self._owns_db and self._db is not None:
            self._db.close()
            self._db = None

    def record_start(
        self,
        task_type: str,
        library_id: int,
        library_slug: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record a task start event.

        Creates database record, adds to Redis active index,
        and publishes task_started event.

        Args:
            task_type: Type of task (scan, analysis, tag_write, import)
            library_id: Library ID
            library_slug: Library slug (denormalized)
            description: Human-readable description
            metadata: Optional task-specific metadata

        Returns:
            The event_id for later completion recording
        """
        started_at = datetime.now(timezone.utc)

        # Create database record
        task_event = TaskEvent(
            task_type=task_type,
            library_id=library_id,
            library_slug=library_slug,
            description=description,
            status=TaskStatus.RUNNING.value,
            started_at=started_at,
            metadata_=metadata or {},
        )
        self.db.add(task_event)
        self.db.commit()
        self.db.refresh(task_event)

        event_id = task_event.id

        logger.info(
            f"Task event {event_id} started: {task_type} for library {library_slug}"
        )

        # Add to Redis active index
        self.redis_manager.add_to_activity_index(task_type, event_id, started_at)

        # Set initial progress in Redis
        self.redis_manager.set_activity_progress(
            event_id=event_id,
            task_type=task_type,
            library_id=library_id,
            library_slug=library_slug,
            description=description,
            started_at=started_at,
        )

        # Publish task_started event
        self.redis_manager.publish_activity_event(
            "task_started",
            {
                "event_id": event_id,
                "task_type": task_type,
                "library_id": library_id,
                "library_slug": library_slug,
                "description": description,
                "started_at": started_at.isoformat(),
                "metadata": metadata or {},
            },
        )

        return event_id

    def record_progress(
        self,
        event_id: int,
        progress_percent: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record task progress update.

        Updates Redis progress hash and publishes task_progress event.
        Does NOT update database (progress is ephemeral).

        Args:
            event_id: The event ID from record_start
            progress_percent: Optional progress percentage
            metadata: Updated metadata (merged with existing)
        """
        # Get existing progress
        progress = self.redis_manager.get_activity_progress(event_id)
        if not progress:
            logger.warning(f"No progress found for event {event_id}")
            return

        # Calculate elapsed time
        started_at = progress.get("started_at")
        elapsed_seconds = 0
        if started_at:
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at)
            elapsed_seconds = int((datetime.now(timezone.utc) - started_at).total_seconds())

        # Update progress in Redis
        if progress_percent is not None:
            self.redis_manager.set_activity_progress(
                event_id=event_id,
                task_type=progress.get("task_type", ""),
                library_id=progress.get("library_id", 0),
                library_slug=progress.get("library_slug", ""),
                description=progress.get("description", ""),
                started_at=started_at if isinstance(started_at, datetime) else datetime.fromisoformat(started_at),
                progress_percent=progress_percent,
                items_total=metadata.get("items_total") if metadata else None,
                items_processed=metadata.get("items_processed") if metadata else None,
                current_file=metadata.get("current_file") if metadata else None,
            )

        # Publish progress event
        event_data = {
            "event_id": event_id,
            "task_type": progress.get("task_type"),
            "progress_percent": progress_percent,
            "elapsed_seconds": elapsed_seconds,
            "metadata": metadata or {},
        }
        self.redis_manager.publish_activity_event("task_progress", event_data)

    def record_completion(
        self,
        event_id: int,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record task completion (success or failure).

        Updates database record with completion details,
        removes from Redis active index, clears progress hash,
        and publishes task_completed or task_failed event.

        Args:
            event_id: The event ID from record_start
            status: Final status ("completed" or "failed")
            metadata: Final metadata (error details for failures)
        """
        completed_at = datetime.now(timezone.utc)

        # Get the task event from database
        task_event = self.db.query(TaskEvent).filter(TaskEvent.id == event_id).first()
        if not task_event:
            logger.warning(f"Task event {event_id} not found for completion")
            return

        # Calculate duration
        duration_seconds = int((completed_at - task_event.started_at).total_seconds())

        # Update database record
        task_event.status = status
        task_event.completed_at = completed_at
        task_event.duration_seconds = duration_seconds
        if metadata:
            existing_metadata = task_event.metadata_ or {}
            existing_metadata.update(metadata)
            task_event.metadata_ = existing_metadata
        self.db.commit()

        logger.info(
            f"Task event {event_id} {status}: {task_event.task_type} "
            f"for library {task_event.library_slug} in {duration_seconds}s"
        )

        # Remove from Redis active index
        self.redis_manager.remove_from_activity_index(task_event.task_type, event_id)

        # Clear progress hash
        self.redis_manager.clear_activity_progress(event_id)

        # Publish completion event
        event_type = "task_completed" if status == TaskStatus.COMPLETED.value else "task_failed"
        self.redis_manager.publish_activity_event(
            event_type,
            {
                "event_id": event_id,
                "task_type": task_event.task_type,
                "library_id": task_event.library_id,
                "library_slug": task_event.library_slug,
                "description": task_event.description,
                "status": status,
                "started_at": task_event.started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "metadata": task_event.metadata_ or {},
            },
        )

    def record_event(
        self,
        task_type: str,
        library_id: int,
        library_slug: str,
        description: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record a one-shot, point-in-time task event.

        Unlike :meth:`record_start` / :meth:`record_completion` (which model a
        task that runs over time), this writes a single already-finished
        ``TaskEvent`` — ``started_at == completed_at``, duration 0 — and
        publishes one activity event. Use it for instantaneous notifications
        that should still show up in the persistent activity history, e.g. a
        skipped Emby refresh.

        Args:
            task_type: Type of task (see :class:`TaskType`).
            library_id: Library ID.
            library_slug: Library slug (denormalized for display).
            description: Human-readable, user-facing message.
            status: Final status ("completed" or "failed").
            metadata: Optional task-specific metadata.

        Returns:
            The event_id of the recorded event.
        """
        now = datetime.now(timezone.utc)

        task_event = TaskEvent(
            task_type=task_type,
            library_id=library_id,
            library_slug=library_slug,
            description=description,
            status=status,
            started_at=now,
            completed_at=now,
            duration_seconds=0,
            metadata_=metadata or {},
        )
        self.db.add(task_event)
        self.db.commit()
        self.db.refresh(task_event)

        event_id = task_event.id

        logger.info(
            f"Task event {event_id} recorded ({status}): {task_type} "
            f"for library {library_slug}"
        )

        # Publish so live SSE subscribers see it immediately. No active-index
        # bookkeeping — the event is born finished.
        event_type = (
            "task_completed" if status == TaskStatus.COMPLETED.value else "task_failed"
        )
        self.redis_manager.publish_activity_event(
            event_type,
            {
                "event_id": event_id,
                "task_type": task_type,
                "library_id": library_id,
                "library_slug": library_slug,
                "description": description,
                "status": status,
                "started_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "duration_seconds": 0,
                "metadata": metadata or {},
            },
        )

        return event_id

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get all currently active tasks.

        Reads from Redis active index and progress hashes.
        Enriches with elapsed time calculation.

        Returns:
            List of active task dicts
        """
        # Get active task members from sorted set
        members = self.redis_manager.get_active_task_members()
        active_tasks = []

        now = datetime.now(timezone.utc)

        for member in members:
            try:
                task_type, event_id_str = member.split(":", 1)
                event_id = int(event_id_str)

                # Get progress details from Redis
                progress = self.redis_manager.get_activity_progress(event_id)
                if progress:
                    started_at = progress.get("started_at")
                    if isinstance(started_at, datetime):
                        elapsed_seconds = int((now - started_at).total_seconds())
                    else:
                        elapsed_seconds = 0

                    active_tasks.append({
                        "event_id": event_id,
                        "task_type": progress.get("task_type", task_type),
                        "library_id": progress.get("library_id"),
                        "library_slug": progress.get("library_slug", ""),
                        "description": progress.get("description", ""),
                        "status": TaskStatus.RUNNING.value,
                        "started_at": started_at,
                        "elapsed_seconds": elapsed_seconds,
                        "progress_percent": progress.get("progress_percent"),
                        "metadata": {
                            k: v for k, v in progress.items()
                            if k in ("items_total", "items_processed", "current_file")
                        },
                    })
            except (ValueError, TypeError) as e:
                logger.warning(f"Error parsing active task member {member}: {e}")
                continue

        return active_tasks

    def get_queued_tasks(self) -> List[Dict[str, Any]]:
        """Get all queued tasks awaiting execution.

        Reads from existing scan queue Redis keys and
        analysis queue (if add-analysis-queue is implemented).

        Returns:
            List of queued task dicts with queue_position
        """
        queued_tasks = []

        # Get all libraries from database to check their scan queues
        from app.models.library import Library
        libraries = self.db.query(Library).all()

        for library in libraries:
            # Check scan queue length
            queue_length = self.redis_manager.get_scan_queue_length(library.id)
            if queue_length > 0:
                # Peek at queued items
                for position in range(queue_length):
                    queued_tasks.append({
                        "task_type": TaskType.SCAN.value,
                        "library_id": library.id,
                        "library_slug": library.slug,
                        "description": "Scan import folder",
                        "queue_position": position + 1,
                        "queued_at": datetime.now(timezone.utc),  # Approximation
                    })

        # Sort by queue position
        queued_tasks.sort(key=lambda x: x["queue_position"])

        return queued_tasks

    def get_recent_completions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent completed tasks from database.

        Args:
            limit: Maximum number of completions to return

        Returns:
            List of completed task dicts ordered by completed_at desc
        """
        events = (
            self.db.query(TaskEvent)
            .filter(TaskEvent.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]))
            .order_by(desc(TaskEvent.completed_at))
            .limit(limit)
            .all()
        )

        return [
            {
                "event_id": event.id,
                "task_type": event.task_type,
                "library_id": event.library_id,
                "library_slug": event.library_slug,
                "description": event.description,
                "status": event.status,
                "started_at": event.started_at,
                "completed_at": event.completed_at,
                "duration_seconds": event.duration_seconds,
                "metadata": event.metadata_ or {},
            }
            for event in events
        ]

    def get_history(
        self,
        skip: int = 0,
        limit: int = 20,
        library_id: Optional[int] = None,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get paginated task history with filters.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            library_id: Filter by library ID
            task_type: Filter by task type
            status: Filter by status

        Returns:
            Tuple of (items list, total count)
        """
        query = self.db.query(TaskEvent)

        # Apply filters
        if library_id is not None:
            query = query.filter(TaskEvent.library_id == library_id)
        if task_type is not None:
            query = query.filter(TaskEvent.task_type == task_type)
        if status is not None:
            query = query.filter(TaskEvent.status == status)

        # Get total count
        total = query.count()

        # Get items with pagination
        events = (
            query
            .order_by(desc(TaskEvent.started_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

        items = [
            {
                "id": event.id,
                "task_type": event.task_type,
                "library_id": event.library_id,
                "library_slug": event.library_slug,
                "description": event.description,
                "status": event.status,
                "started_at": event.started_at,
                "completed_at": event.completed_at,
                "duration_seconds": event.duration_seconds,
                "metadata": event.metadata_ or {},
            }
            for event in events
        ]

        return items, total

    def clear_history(
        self,
        library_id: Optional[int] = None,
        task_type: Optional[str] = None,
    ) -> int:
        """Clear task history records, excluding running tasks.

        Permanently deletes task_events records matching the provided filters.
        Running tasks are always excluded to prevent corrupting active task state.

        Args:
            library_id: Optional library ID to filter deletion.
            task_type: Optional task type to filter deletion.

        Returns:
            Number of records deleted.
        """
        from sqlalchemy import and_

        # Build query with filters - always exclude running tasks
        query = self.db.query(TaskEvent).filter(
            TaskEvent.status != TaskStatus.RUNNING.value
        )

        if library_id is not None:
            query = query.filter(TaskEvent.library_id == library_id)

        if task_type is not None:
            query = query.filter(TaskEvent.task_type == task_type)

        # Get count before deletion
        deleted_count = query.count()

        # Delete matching records
        query.delete(synchronize_session=False)
        self.db.commit()

        logger.info(f"Cleared {deleted_count} task history records")

        return deleted_count

    def cleanup_stale_entries(self, max_age_seconds: int = 7200) -> int:
        """Remove stale entries from Redis active index.

        Also marks orphaned database events (status=running, older than max_age_seconds)
        as failed for data consistency.

        Args:
            max_age_seconds: Maximum age before considering stale (default 2 hours)

        Returns:
            Number of entries removed
        """
        # Clean up Redis entries
        removed_count = self.redis_manager.cleanup_stale_activity_entries(max_age_seconds)

        # Also mark orphaned DB events as failed
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)

        candidates = (
            self.db.query(TaskEvent)
            .filter(
                TaskEvent.status == TaskStatus.RUNNING.value,
                TaskEvent.started_at < cutoff_dt,
            )
            .all()
        )

        # A long-running task that still publishes progress keeps its Redis
        # progress hash alive (TTL refreshed on every update) — old but alive
        # is not orphaned. Only events without fresh progress are crash debris.
        orphaned_events = [
            event for event in candidates
            if not self.redis_manager.get_activity_progress(event.id)
        ]

        for event in orphaned_events:
            event.status = TaskStatus.FAILED.value
            event.completed_at = datetime.now(timezone.utc)
            event.duration_seconds = int((event.completed_at - event.started_at).total_seconds())
            if event.metadata_ is None:
                event.metadata_ = {}
            event.metadata_["error"] = "Task orphaned (worker crash recovery)"

        if orphaned_events:
            self.db.commit()
            logger.info(f"Marked {len(orphaned_events)} orphaned task events as failed")

        return removed_count + len(orphaned_events)


def get_task_event_service(
    db: Optional[Session] = None,
    redis_manager: Optional[RedisKeyManager] = None,
) -> TaskEventService:
    """Create a TaskEventService instance.

    Args:
        db: Optional database session.
        redis_manager: Optional Redis manager.

    Returns:
        Configured TaskEventService instance.
    """
    return TaskEventService(db=db, redis_manager=redis_manager)
