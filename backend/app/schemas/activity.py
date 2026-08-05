"""Pydantic schemas for activity monitor API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Single source of truth for task enums. A stale copy here once 500'd
# /activity for every task_type added only to models.enums (cleanup,
# bpm_backfill).
from app.models.enums import TaskStatus, TaskType


# Request Schemas


class ActivityHistoryParams(BaseModel):
    """Query parameters for the history endpoint."""
    skip: int = Field(default=0, ge=0, description="Number of records to skip")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum records to return")
    library_id: Optional[int] = Field(default=None, description="Filter by library ID")
    task_type: Optional[TaskType] = Field(default=None, description="Filter by task type")
    status: Optional[TaskStatus] = Field(default=None, description="Filter by status")


# Response Schemas


class ActiveTask(BaseModel):
    """An actively running task."""
    event_id: int = Field(..., description="Task event ID from database")
    task_type: TaskType = Field(..., description="Type of task")
    library_id: Optional[int] = Field(None, description="Library ID (null if library deleted)")
    library_slug: str = Field(..., description="Library slug (denormalized for display)")
    description: str = Field(..., description="Human-readable task description")
    status: TaskStatus = Field(..., description="Current status (always 'running' for active)")
    started_at: datetime = Field(..., description="When the task started")
    elapsed_seconds: int = Field(..., ge=0, description="Seconds since task started")
    progress_percent: Optional[float] = Field(
        None, ge=0, le=100, description="Progress percentage (if available)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Task-specific metadata"
    )

    class Config:
        from_attributes = True


class QueuedTask(BaseModel):
    """A task waiting in the queue."""
    task_type: TaskType = Field(..., description="Type of task")
    library_id: Optional[int] = Field(None, description="Library ID")
    library_slug: str = Field(..., description="Library slug")
    description: str = Field(..., description="Human-readable task description")
    queue_position: int = Field(..., ge=1, description="Position in queue (1-indexed)")
    queued_at: datetime = Field(..., description="When the task was queued")

    class Config:
        from_attributes = True


class CompletedTask(BaseModel):
    """A recently completed task."""
    event_id: int = Field(..., description="Task event ID from database")
    task_type: TaskType = Field(..., description="Type of task")
    library_id: Optional[int] = Field(None, description="Library ID (null if library deleted)")
    library_slug: str = Field(..., description="Library slug (denormalized for display)")
    description: str = Field(..., description="Human-readable task description")
    status: TaskStatus = Field(..., description="Final status (completed or failed)")
    started_at: datetime = Field(..., description="When the task started")
    completed_at: datetime = Field(..., description="When the task completed")
    duration_seconds: int = Field(..., ge=0, description="Task duration in seconds")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Task-specific metadata"
    )

    class Config:
        from_attributes = True


class ActivityCounts(BaseModel):
    """Counts of tasks in each category."""
    active: int = Field(..., ge=0, description="Number of active tasks")
    queued: int = Field(..., ge=0, description="Number of queued tasks")
    recent: int = Field(..., ge=0, description="Number of recent completions returned")


class ActivitySnapshotResponse(BaseModel):
    """Response for GET /api/v1/activity snapshot endpoint."""
    active_tasks: List[ActiveTask] = Field(
        default_factory=list, description="Currently running tasks"
    )
    queued_tasks: List[QueuedTask] = Field(
        default_factory=list, description="Tasks awaiting execution"
    )
    recent_completions: List[CompletedTask] = Field(
        default_factory=list, description="Last 10 completed tasks"
    )
    counts: ActivityCounts = Field(..., description="Summary counts")


class TaskEventHistoryItem(BaseModel):
    """A task event in the history list."""
    id: int = Field(..., description="Task event ID")
    task_type: TaskType = Field(..., description="Type of task")
    library_id: Optional[int] = Field(None, description="Library ID (null if deleted)")
    library_slug: str = Field(..., description="Library slug (preserved for display)")
    description: str = Field(..., description="Human-readable task description")
    status: TaskStatus = Field(..., description="Task status")
    started_at: datetime = Field(..., description="When the task started")
    completed_at: Optional[datetime] = Field(None, description="When the task completed")
    duration_seconds: Optional[int] = Field(None, ge=0, description="Task duration")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Task-specific metadata"
    )

    class Config:
        from_attributes = True


class ActivityHistoryResponse(BaseModel):
    """Response for GET /api/v1/activity/history endpoint."""
    items: List[TaskEventHistoryItem] = Field(..., description="List of task events")
    total: int = Field(..., ge=0, description="Total matching records")
    skip: int = Field(..., ge=0, description="Number of records skipped")
    limit: int = Field(..., ge=1, description="Maximum records returned")


class ClearHistoryResponse(BaseModel):
    """Response for DELETE /api/v1/activity/history endpoint."""
    deleted_count: int = Field(
        ...,
        ge=0,
        description="Number of task event records deleted"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "deleted_count": 42
            }
        }


# SSE Event Schemas


class SSETaskStarted(BaseModel):
    """Data for task_started SSE event."""
    event_id: int
    task_type: TaskType
    library_id: Optional[int]
    library_slug: str
    description: str
    started_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SSETaskProgress(BaseModel):
    """Data for task_progress SSE event."""
    event_id: int
    task_type: TaskType
    progress_percent: Optional[float] = None
    elapsed_seconds: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SSETaskCompleted(BaseModel):
    """Data for task_completed SSE event."""
    event_id: int
    task_type: TaskType
    library_id: Optional[int]
    library_slug: str
    description: str
    status: str = "completed"
    started_at: datetime
    completed_at: datetime
    duration_seconds: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SSETaskFailed(BaseModel):
    """Data for task_failed SSE event."""
    event_id: int
    task_type: TaskType
    library_id: Optional[int]
    library_slug: str
    description: str
    status: str = "failed"
    started_at: datetime
    completed_at: datetime
    duration_seconds: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SSEHeartbeat(BaseModel):
    """Data for heartbeat SSE event."""
    timestamp: datetime
