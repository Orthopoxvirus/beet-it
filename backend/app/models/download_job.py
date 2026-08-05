"""DownloadJob model for the multi-album Download Center.

A download job bundles a user-selected set of albums ("gathered" across the
app) into a single ZIP archive, packed asynchronously by a Celery worker. The
row tracks packing progress and the on-disk location of the finished archive so
the Download Center page can show status, offer the file, and delete it.
"""

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    Text,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# JSONB on PostgreSQL, plain JSON on other dialects (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB, "postgresql")


class DownloadJob(Base):
    """A queued/packing/finished multi-album ZIP download."""

    __tablename__ = "download_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Library reference. Jobs are scoped to one library; deleting the library
    # cascades its jobs away (the archives are disposable derived artifacts).
    library_id = Column(
        Integer,
        ForeignKey("libraries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized slug so the row is self-describing in logs / API responses.
    library_slug = Column(String(255), nullable=False)

    # pending -> packing -> completed | failed
    status = Column(String(20), nullable=False, default="pending", index=True)

    # The album IDs (beets album ids) requested for this archive.
    album_ids = Column(JSONType, nullable=False)
    # Track-based jobs (e.g. BPM-range download): beets item ids packed flat
    # as "Artist - Title.ext". When set, album_ids is empty and album_count /
    # processed_count count tracks instead of albums.
    track_ids = Column(JSONType, nullable=True)
    album_count = Column(Integer, nullable=False, default=0)
    # Albums actually packed so far — committed per album for live progress.
    processed_count = Column(Integer, nullable=False, default=0)

    # User-facing archive filename and the absolute on-disk path (internal).
    filename = Column(String(512), nullable=True)
    zip_path = Column(String(1024), nullable=True)
    # Final archive size in bytes. BigInteger: archives can exceed 2 GiB.
    size_bytes = Column(BigInteger, nullable=True)

    # Failure detail, surfaced to the user when status == "failed".
    error = Column(Text, nullable=True)

    # Links to the activity-monitor TaskEvent so the Download Center can
    # correlate SSE progress events to this job.
    task_event_id = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # created_at + retention window. Cleanup deletes the row + archive past this.
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    library = relationship("Library", back_populates="download_jobs")

    __table_args__ = (
        Index("ix_download_jobs_library_status", "library_id", "status"),
    )
