"""Pydantic schemas for import scan API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ScanStatus(str, Enum):
    """Possible states for a scan operation."""
    QUEUED = "queued"
    SCANNING = "scanning"
    EXTRACTING_METADATA = "extracting_metadata"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationType(str, Enum):
    """Types of operations that can block scans."""
    IMPORT = "import"
    TAG_MODIFY = "tag_modify"
    MOVE = "move"
    DELETE = "delete"


class ImportItemType(str, Enum):
    """Type of discovered import item."""
    FILE = "file"
    FOLDER = "folder"


class ImportItemStatus(str, Enum):
    """Status of an import item relative to previous scan."""
    NEW = "new"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"
    DELETED = "deleted"


class ItemTypeFilter(str, Enum):
    """Filter values for import item type."""
    FILE = "file"
    FOLDER = "folder"


class ItemStatusFilter(str, Enum):
    """Filter values for import item status."""
    NEW = "new"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"
    DELETED = "deleted"


# Response schemas


class ScanInfo(BaseModel):
    """Information about a scan operation."""
    id: int = Field(..., description="Unique scan identifier")
    status: ScanStatus = Field(..., description="Current scan status")
    started_at: Optional[datetime] = Field(None, description="When the scan started")
    completed_at: Optional[datetime] = Field(None, description="When the scan completed")
    items_total: int = Field(0, ge=0, description="Total items to process")
    items_processed: int = Field(0, ge=0, description="Items processed so far")
    progress_percent: Optional[float] = Field(
        None, ge=0, le=100, description="Progress as percentage"
    )
    current_file: Optional[str] = Field(None, description="Currently processing file path")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        from_attributes = True


class ScanStatusResponse(BaseModel):
    """Response for GET /scan/status endpoint."""
    library_slug: str = Field(..., description="Library identifier")
    current_scan: Optional[ScanInfo] = Field(None, description="Currently running scan")
    queued_scans: int = Field(0, ge=0, description="Number of scans in queue")
    blocking_operations: List[OperationType] = Field(
        default_factory=list, description="Operations blocking scan start"
    )
    watcher_active: bool = Field(False, description="Whether filesystem watcher is running")
    last_completed_scan: Optional[ScanInfo] = Field(
        None, description="Most recent completed scan"
    )


class ScanTriggerResponse(BaseModel):
    """Response for POST /scan endpoint."""
    status: str = Field(..., description="One of: started, queued, blocked")
    scan_id: Optional[int] = Field(None, description="Scan ID if started")
    message: str = Field(..., description="Human-readable status message")
    queue_position: Optional[int] = Field(None, ge=1, description="Position in queue if queued")
    blocking_operations: List[OperationType] = Field(
        default_factory=list, description="Operations blocking the scan"
    )


class ScanHistoryItem(BaseModel):
    """A single scan in the history list."""
    id: int = Field(..., description="Unique scan identifier")
    status: ScanStatus = Field(..., description="Final scan status")
    started_at: Optional[datetime] = Field(None, description="When the scan started")
    completed_at: Optional[datetime] = Field(None, description="When the scan completed")
    items_total: int = Field(0, ge=0, description="Total items discovered")
    items_processed: int = Field(0, ge=0, description="Items successfully processed")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        from_attributes = True


class ScanHistoryResponse(BaseModel):
    """Response for GET /scan/history endpoint."""
    items: List[ScanHistoryItem] = Field(..., description="List of past scans")
    total: int = Field(..., ge=0, description="Total number of scans in history")
    skip: int = Field(..., ge=0, description="Number of records skipped")
    limit: int = Field(..., ge=1, description="Maximum records returned")


class ImportItem(BaseModel):
    """A file or folder discovered during scan."""
    id: int = Field(..., description="Unique item identifier")
    item_type: ImportItemType = Field(..., description="Whether this is a file or folder")
    path: str = Field(..., description="Full path to the item")
    directory: Optional[str] = Field(None, description="Parent directory path")
    filename: Optional[str] = Field(None, description="File or folder name")

    # Audio metadata (null for folders and non-audio files)
    album: Optional[str] = Field(None, description="Album name from audio tags")
    album_artist: Optional[str] = Field(None, description="Album artist from audio tags")
    artist: Optional[str] = Field(None, description="Track artist from audio tags")
    title: Optional[str] = Field(None, description="Track title from audio tags")
    track_number: Optional[int] = Field(None, ge=1, description="Track number from audio tags")
    track_total: Optional[int] = Field(None, ge=1, description="Total tracks in album from audio tags")
    genre: Optional[str] = Field(None, description="Genre from audio tags")
    format: Optional[str] = Field(None, description="Container format, e.g. 'mp3', 'flac'")
    bitrate: Optional[int] = Field(None, ge=1, description="Bitrate in kbps")

    # Change tracking
    status: ImportItemStatus = Field(..., description="Status relative to previous scan")
    first_seen_at: datetime = Field(..., description="When item was first discovered")
    last_seen_at: datetime = Field(..., description="When item was last seen in a scan")

    class Config:
        from_attributes = True


class ImportItemListResponse(BaseModel):
    """Response for GET /import-items endpoint."""
    items: List[ImportItem] = Field(..., description="List of discovered items")
    total: int = Field(..., ge=0, description="Total items matching filters")
    skip: int = Field(..., ge=0, description="Number of records skipped")
    limit: int = Field(..., ge=1, description="Maximum records returned")
    scan_id: Optional[int] = Field(None, description="ID of the scan these items are from")
    scan_completed_at: Optional[datetime] = Field(
        None, description="When the source scan completed"
    )


class ImportFolderDeleteResponse(BaseModel):
    """Response for DELETE /import-folder endpoint."""
    status: str = Field("deleted", description="Outcome of the delete operation")
    path: str = Field(..., description="Relative path of the deleted folder")
    items_removed: int = Field(
        ..., ge=0, description="Number of import items purged from the database"
    )


# SSE Event Data Schemas


class SSEScanStarted(BaseModel):
    """Data for scan_started SSE event."""
    scan_id: int
    library_slug: str
    started_at: datetime


class SSEScanProgress(BaseModel):
    """Data for scan_progress SSE event."""
    scan_id: int
    status: ScanStatus
    items_total: int
    items_processed: int
    progress_percent: float
    current_file: Optional[str] = None
    elapsed_seconds: int


class SSEScanCompleted(BaseModel):
    """Data for scan_completed SSE event."""
    scan_id: int
    status: str = "completed"
    items_total: int
    items_processed: int
    new_items: int
    modified_items: int
    deleted_items: int
    completed_at: datetime
    duration_seconds: int


class SSEScanFailed(BaseModel):
    """Data for scan_failed SSE event."""
    scan_id: int
    status: str = "failed"
    error_message: str
    failed_at: datetime


class SSEScanQueued(BaseModel):
    """Data for scan_queued SSE event."""
    library_slug: str
    queue_position: int
    blocked_by: List[str] = Field(default_factory=list)


class SSEScanBlocked(BaseModel):
    """Data for scan_blocked SSE event."""
    library_slug: str
    blocking_operations: List[str]


class SSEHeartbeat(BaseModel):
    """Data for heartbeat SSE event."""
    timestamp: datetime
