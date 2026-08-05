"""ImportScan model for tracking scan execution history."""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ImportScan(Base):
    """Model representing a scan of a library's import folder."""

    __tablename__ = "import_scans"

    id = Column(Integer, primary_key=True, index=True)
    library_id = Column(Integer, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued")  # queued, scanning, extracting_metadata, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    items_total = Column(Integer, nullable=True, default=0)
    items_processed = Column(Integer, nullable=True, default=0)
    error_message = Column(Text, nullable=True)

    # Relationships
    library = relationship("Library", back_populates="import_scans")
    import_items = relationship("ImportItem", back_populates="scan", cascade="all, delete-orphan")
