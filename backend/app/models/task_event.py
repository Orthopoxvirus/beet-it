"""TaskEvent model for permanent task history storage."""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# JSONB on PostgreSQL, plain JSON on other dialects (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB, "postgresql")


class TaskEvent(Base):
    """Model representing a task execution event.

    Stores permanent history of all background task executions,
    surviving Redis flushes and server restarts.
    """

    __tablename__ = "task_events"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Task identification
    task_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Task type: scan, analysis, tag_write, import"
    )

    # Library reference (nullable for orphan preservation)
    library_id = Column(
        Integer,
        ForeignKey("libraries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Library ID, null if library was deleted"
    )

    # Denormalized library slug for display after deletion
    library_slug = Column(
        String(255),
        nullable=False,
        comment="Library slug, preserved for display even after library deletion"
    )

    # Task description
    description = Column(
        Text,
        nullable=False,
        comment="Human-readable task description"
    )

    # Status tracking
    status = Column(
        String(20),
        nullable=False,
        default="running",
        index=True,
        comment="Task status: running, completed, failed"
    )

    # Timestamps
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="When the task started execution"
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="When the task completed (null if still running)"
    )

    # Duration (computed on completion)
    duration_seconds = Column(
        Integer,
        nullable=True,
        comment="Task duration in seconds (null if still running)"
    )

    # Flexible metadata storage
    metadata_ = Column(
        "metadata",
        JSONType,
        nullable=True,
        server_default="{}",
        comment="Task-specific metadata (progress details, error info, etc.)"
    )

    # Relationships
    library = relationship("Library", back_populates="task_events")

    # Composite indexes for common queries
    __table_args__ = (
        Index('ix_task_events_library_type', 'library_id', 'task_type'),
        Index('ix_task_events_status_started', 'status', 'started_at'),
    )
