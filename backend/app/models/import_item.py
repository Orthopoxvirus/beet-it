"""ImportItem model for tracking discovered files and folders during import scans."""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ImportItem(Base):
    """Model representing a file or folder discovered during an import folder scan."""

    __tablename__ = "import_items"

    id = Column(Integer, primary_key=True, index=True)
    library_id = Column(Integer, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True)
    scan_id = Column(Integer, ForeignKey("import_scans.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type = Column(String(10), nullable=False)  # 'file' or 'folder'
    path = Column(String(1000), nullable=False)
    directory = Column(String(1000), nullable=True)
    filename = Column(String(255), nullable=True)

    # Audio metadata (NULL for folders and non-audio files)
    album = Column(String(255), nullable=True)
    album_artist = Column(String(255), nullable=True)
    artist = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    track_number = Column(Integer, nullable=True)
    track_total = Column(Integer, nullable=True)
    genre = Column(String(100), nullable=True)

    # Audio quality (NULL for folders, non-audio files, and pre-migration rows)
    format = Column(String(20), nullable=True)  # Container format, e.g. 'mp3', 'flac'
    bitrate = Column(Integer, nullable=True)  # Bitrate in kbps

    # Change tracking
    status = Column(String(20), nullable=False, default="new")  # new, modified, unchanged, deleted
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Unique constraint on (library_id, path)
    __table_args__ = (
        UniqueConstraint("library_id", "path", name="uq_import_items_library_path"),
    )

    # Relationships
    library = relationship("Library", back_populates="import_items")
    scan = relationship("ImportScan", back_populates="import_items")
