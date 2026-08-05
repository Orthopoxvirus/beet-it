"""Pydantic schemas for the Download Center API.

Wire convention follows the album/activity area: snake_case field names,
``from_attributes`` for ORM serialization.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DownloadQueueRequest(BaseModel):
    """Request body to queue a new download of albums and/or single titles."""

    album_ids: List[int] = Field(default=[], description="beets album IDs to pack as folders")
    track_ids: List[int] = Field(
        default=[],
        description='beets item IDs to pack flat as "Artist - Title.ext"',
    )


class DownloadJobResponse(BaseModel):
    """A download job's public state."""

    id: int
    library_slug: str
    status: str  # pending | packing | completed | failed
    album_count: int
    processed_count: int
    size_bytes: Optional[int] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DownloadJobListResponse(BaseModel):
    """A library's download jobs, newest first."""

    items: List[DownloadJobResponse]
    total: int


class AlbumSizeResponse(BaseModel):
    """Total on-disk size of an album's tracks, for the gathering bar."""

    size_bytes: int
    track_count: int
