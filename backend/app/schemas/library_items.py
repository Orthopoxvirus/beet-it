"""Pydantic schemas for library items batch edit API.

This module defines the request and response schemas for library item
queries and batch edit operations.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.batch_tag import (
    TransformationRule,
    ItemPreview,
    PreviewError,
    ItemResult,
)


# ============================================================================
# Library Item Response Schemas
# ============================================================================


class LibraryItemResponse(BaseModel):
    """Response model for a single library item (track)."""

    id: int = Field(..., description="Beets item ID")
    path: str = Field(..., description="Absolute file path")
    filename: str = Field(..., description="File name without path")
    directory: str = Field(..., description="Parent directory path")
    item_type: Literal["track"] = Field("track", description="Item type (always track)")

    # Standard metadata fields
    album: Optional[str] = Field(None, description="Album name")
    album_artist: Optional[str] = Field(None, description="Album artist")
    artist: Optional[str] = Field(None, description="Track artist")
    title: Optional[str] = Field(None, description="Track title")
    track_number: Optional[int] = Field(None, description="Track number")
    disc_number: Optional[int] = Field(None, description="Disc number")
    genre: Optional[str] = Field(None, description="Genre")
    year: Optional[int] = Field(None, description="Year")

    # File/quality facts (surfaced in the batch-edit album header row)
    format: Optional[str] = Field(None, description="Audio format / container, e.g. FLAC, MP3")
    bitrate: Optional[int] = Field(None, description="Bitrate in bits per second")

    # Album association
    album_id: int = Field(..., description="Beets album ID")


class LibraryItemsListResponse(BaseModel):
    """Paginated response for library items query."""

    items: List[LibraryItemResponse] = Field(..., description="List of library items")
    total: int = Field(..., ge=0, description="Total number of items matching query")
    page: int = Field(..., ge=1, description="Current page number")
    per_page: int = Field(..., ge=1, description="Items per page")
    page_size: int = Field(..., ge=1, description="Items per page (alias of per_page)")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    album_filter: Optional[str] = Field(None, description="Current album filter applied")


class AlbumSummary(BaseModel):
    """Summary of an album for the album picker."""

    id: int = Field(..., description="Beets album ID")
    title: str = Field(..., description="Album title")
    artist: str = Field(..., description="Album artist")
    track_count: int = Field(..., ge=0, description="Number of tracks in the album")


class LibraryAlbumsResponse(BaseModel):
    """Response for library albums query."""

    albums: List[AlbumSummary] = Field(..., description="List of album summaries")
    total: int = Field(..., ge=0, description="Total number of albums")


# ============================================================================
# Preview Request/Response Schemas
# ============================================================================


class LibraryItemsPreviewRequest(BaseModel):
    """Request body for previewing tag transformations on library items."""

    item_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="List of beets item IDs to preview transformations for",
    )
    rules: List[TransformationRule] = Field(
        ...,
        min_length=1,
        description="List of transformation rules to apply",
    )


class LibraryItemsPreviewResponse(BaseModel):
    """Response body for library items preview endpoint."""

    previews: List[ItemPreview] = Field(
        ...,
        description="Preview results for each successfully processed item",
    )
    errors: List[PreviewError] = Field(
        default_factory=list,
        description="Errors for items that couldn't be previewed",
    )


# ============================================================================
# Batch Update Request/Response Schemas
# ============================================================================


class LibraryItemsBatchUpdateRequest(BaseModel):
    """Request body for applying tag transformations to library items."""

    item_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="List of beets item IDs to update",
    )
    rules: List[TransformationRule] = Field(
        ...,
        min_length=1,
        description="List of transformation rules to apply",
    )


class AlbumUpdateStatus(BaseModel):
    """Status of beets update for a single album."""

    album: str = Field(..., description="Original album name (before edits)")
    status: Literal["pending", "syncing", "success", "failed"] = Field(
        ..., description="Update status"
    )
    error: Optional[str] = Field(None, description="Error message if failed")


class FileWritesStatus(BaseModel):
    """Status of file write operations in a batch update."""

    total: int = Field(..., ge=0, description="Total files to write")
    succeeded: int = Field(..., ge=0, description="Files successfully written")
    failed: int = Field(..., ge=0, description="Files that failed to write")


class LibraryItemsBatchUpdateResponse(BaseModel):
    """Response body for library items batch update endpoint."""

    status: Literal["completed", "partial", "pending_sync"] = Field(
        ..., description="Overall batch operation status"
    )
    job_id: str = Field(..., description="Job ID for tracking beets update status")
    items_total: int = Field(..., ge=0, description="Total items in batch")
    items_succeeded: int = Field(..., ge=0, description="Items successfully updated")
    items_failed: int = Field(..., ge=0, description="Items that failed to update")
    started_at: datetime = Field(..., description="When the batch operation started")
    completed_at: Optional[datetime] = Field(
        None, description="When file writes completed"
    )
    duration_seconds: Optional[int] = Field(
        None, ge=0, description="Duration of file writes in seconds"
    )
    results: List[ItemResult] = Field(..., description="Results for each item")
    albums_to_sync: List[str] = Field(
        default_factory=list,
        description="List of original album names that need beets update",
    )


# ============================================================================
# Batch Update Status Schemas
# ============================================================================


class BatchUpdateStatusResponse(BaseModel):
    """Response body for batch update status endpoint."""

    job_id: str = Field(..., description="Job ID")
    # "partial" is the terminal state when some albums synced and some
    # failed — the sync task writes it as its final status; omitting it here
    # made the status endpoint 500 on exactly the jobs that needed attention.
    status: Literal["pending", "running", "completed", "partial", "failed"] = Field(
        ..., description="Overall job status"
    )
    started_at: Optional[datetime] = Field(None, description="When the job started")
    completed_at: Optional[datetime] = Field(None, description="When the job completed")
    file_writes: Optional[FileWritesStatus] = Field(
        None, description="Status of file write operations"
    )
    beets_updates: List[AlbumUpdateStatus] = Field(
        default_factory=list,
        description="Status for each album being synchronized",
    )
    error: Optional[str] = Field(
        None, description="Error message if entire job failed"
    )
