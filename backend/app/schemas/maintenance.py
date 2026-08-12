"""Schemas for the library Maintenance feature (issue #147).

Covers the missing-cover table, the online cover-art search, and the beets
``unimported`` (stray file) detection + cleanup actions. These mirror the
snake_case album-family schemas (see ``schemas/album.py``) so the frontend
reads the same wire shape as the rest of the album endpoints.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MissingCoverAlbum(BaseModel):
    album_id: int
    title: str
    artist: str
    # True when the album folder itself is gone from disk (ghost entry) —
    # cover search is pointless; the UI offers a DB-only removal instead.
    folder_missing: bool = False


class MissingCoverResponse(BaseModel):
    items: list[MissingCoverAlbum]
    total: int


class CoverSearchResult(BaseModel):
    url: str
    source: str
    width: Optional[int] = None
    height: Optional[int] = None


class CoverSearchResponse(BaseModel):
    query: str
    results: list[CoverSearchResult]


class PluginStatus(BaseModel):
    plugin: str
    enabled: bool


class StrayFile(BaseModel):
    path: str
    name: str
    size: int
    # True for image files — the UI offers a preview and use-as-cover.
    is_image: bool = False


class StrayGroup(BaseModel):
    folder: str
    relative_folder: str
    files: list[StrayFile]
    total_size: int
    # True when no file in this folder is tracked by beets — i.e. the whole
    # folder is a stray album, safe to move/delete wholesale.
    fully_untracked: bool
    # The single album living in this folder (None when untracked or when the
    # folder mixes several albums). Lets the UI show the album's current cover
    # next to stray images and offer use-as-cover.
    album_id: Optional[int] = None
    # mtime of that album's active cover, as a cache-buster for the cover URL.
    # None when the album has no cover yet.
    cover_version: Optional[int] = None


class UnimportedResponse(BaseModel):
    enabled: bool
    groups: list[StrayGroup]
    total_files: int


class StrayAction(str, Enum):
    delete = "delete"
    move_to_import = "move_to_import"


class StrayActionRequest(BaseModel):
    paths: list[str]
    action: StrayAction


class StrayActionResult(BaseModel):
    path: str
    status: str  # "deleted" | "moved" | "skipped" | "error"
    detail: Optional[str] = None
    relocated_to: Optional[str] = None


class StrayActionResponse(BaseModel):
    results: list[StrayActionResult]


class UseAsCoverRequest(BaseModel):
    """Promote a stray image file to the album cover of its folder."""

    path: str


class UseAsCoverResponse(BaseModel):
    status: str  # "cover_set"
    album_id: int
    cover_path: str


# --- BPM backfill (autobpm) ---


class BpmBackfillInfoResponse(BaseModel):
    """Pre-flight info for the maintenance page."""

    missing_count: int = Field(..., description="Tracks without a usable bpm tag")
    estimated_seconds: int = Field(
        0, description="Expected wall-clock duration of a full backfill"
    )
    workers: int = Field(1, description="Parallel analysis subprocesses that would be used")


class BpmBackfillStartResponse(BaseModel):
    job_id: str
    status: str = "queued"
    total: int


class BpmBackfillStatusResponse(BaseModel):
    """Current/last backfill job state for a library.

    ``status`` is one of: idle, queued, running, completed,
    completed_with_errors, cancelled, failed.
    """

    status: str
    total: int = 0
    processed: int = 0
    failed: int = 0
    job_id: Optional[str] = None
    error: Optional[str] = None
    updated_at: Optional[str] = None
    eta_seconds: Optional[int] = Field(
        None, description="Estimated seconds until the job finishes (measured rate)"
    )
    workers: Optional[int] = Field(None, description="Parallel analysis subprocesses in use")
