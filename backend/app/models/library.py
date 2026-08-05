from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Library(Base):
    """Model representing a beets music library."""

    __tablename__ = "libraries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    path = Column(String(500), nullable=False)
    config_path = Column(String(500), nullable=True)
    database_path = Column(String(500), nullable=True)
    library_path = Column(String(500), nullable=True)
    import_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships for import scanning
    import_scans = relationship("ImportScan", back_populates="library", cascade="all, delete-orphan")
    import_items = relationship("ImportItem", back_populates="library", cascade="all, delete-orphan")

    # Relationship for task events (activity monitor)
    task_events = relationship(
        "TaskEvent",
        back_populates="library",
        passive_deletes=True  # Let database handle SET NULL
    )

    # Download Center jobs — cascade-deleted with the library (derived artifacts)
    download_jobs = relationship(
        "DownloadJob",
        back_populates="library",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
