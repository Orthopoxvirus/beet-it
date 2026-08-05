"""Pydantic schemas for beets import action API endpoints."""

import os
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


# Type aliases
ImportJobStatus = Literal["pending", "in_progress", "completed", "failed"]
ImportState = Literal["pending", "in_progress", "done"]
ImportMode = Literal["copy", "move"]


class ImportCandidateTrack(BaseModel):
    """Track metadata from the selected candidate."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    index: int = Field(..., ge=1, description="Track number (1-indexed)")
    title: str = Field(..., min_length=1, description="Track title")
    length: Optional[float] = Field(None, ge=0, description="Track duration in seconds")
    disc: Optional[int] = Field(
        None,
        ge=1,
        description="Disc (medium) number this track belongs to; None/1 for "
        "single-disc releases.",
    )
    local_path: Optional[str] = Field(
        None,
        description="Absolute path of the local file beets paired to this "
        "candidate track. Used at import time to apply each track's metadata to "
        "the correct file (multi-disc safe).",
    )


class ImportCandidate(BaseModel):
    """Selected candidate metadata to apply during import."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    source: str = Field(
        ...,
        min_length=1,
        description="Source of the candidate (e.g., 'MusicBrainz', 'Discogs')"
    )
    source_id: Optional[str] = Field(
        None,
        description="Unique identifier from the source"
    )
    artist: str = Field(..., min_length=1, description="Album artist name")
    album: str = Field(..., min_length=1, description="Album title")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="Release year")
    cover_url: Optional[str] = Field(
        None,
        description="Remote cover-art URL to persist as the album's art on import",
    )
    tracks: List[ImportCandidateTrack] = Field(
        ...,
        min_length=1,
        description="Track list with metadata"
    )


class ImportAlbumRequest(BaseModel):
    """Request body for starting an import job."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    album_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Path to the album folder"
    )
    candidate: Optional[ImportCandidate] = Field(
        None,
        description=(
            "Selected candidate metadata to apply. Required unless importAsIs "
            "is true, in which case it must be omitted."
        ),
    )
    import_as_is: bool = Field(
        False,
        description=(
            "When true, import the album without a candidate: keep the files' "
            "existing tags untouched and derive library metadata from them."
        ),
    )
    replace_existing: bool = Field(
        False,
        description=(
            "When true, bypass the 'already in library' check. Set this after "
            "the user confirmed an upgrade in response to an ALBUM_ALREADY_EXISTS "
            "409 error."
        ),
    )

    @model_validator(mode="after")
    def validate_candidate_presence(self) -> "ImportAlbumRequest":
        """Enforce the candidate/import-as-is contract.

        A normal import needs exactly one candidate to apply; an as-is import
        carries no candidate (metadata is read from the files instead).
        """
        if self.import_as_is:
            if self.candidate is not None:
                raise ValueError(
                    "candidate must be omitted when importAsIs is true"
                )
        elif self.candidate is None:
            raise ValueError(
                "candidate is required unless importAsIs is true"
            )
        return self

    @field_validator("album_path")
    @classmethod
    def validate_album_path(cls, v: str) -> str:
        """Validate album path format and prevent path traversal."""
        v = v.strip()
        if not v:
            raise ValueError("Album path cannot be empty")
        if "\x00" in v:
            raise ValueError("Album path contains invalid characters")
        normalized = os.path.normpath(v)
        if normalized.startswith("..") or "/../" in v or v.endswith("/.."):
            raise ValueError("Album path cannot contain parent directory references")
        return v


class AlbumQualityStats(BaseModel):
    """Format / quality / size summary of an album.

    Used on both sides of the upgrade-vs-cancel dialog so the user can compare
    what's already in the library against what a re-import would replace it with.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    track_count: int = Field(0, description="Number of audio tracks")
    total_bytes: int = Field(0, description="Sum of audio file sizes in bytes")
    total_duration_seconds: float = Field(
        0.0, description="Sum of track durations in seconds"
    )
    dominant_format: Optional[str] = Field(
        None, description="Most common format across tracks (e.g. FLAC, MP3)"
    )
    avg_bitrate_kbps: Optional[int] = Field(
        None,
        description="Duration-weighted average bitrate in kbps, or None if unknown",
    )


class ExistingAlbumInfo(BaseModel):
    """Details about an album that already exists in the beets library."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    album_id: int = Field(..., description="Existing album ID in beets DB")
    artist: str = Field(..., description="Existing album's artist")
    album: str = Field(..., description="Existing album's title")
    match_reason: str = Field(
        ...,
        description=(
            "How the duplicate was detected: 'mb_albumid' for a MusicBrainz ID "
            "match, or 'artist_album' for an album-artist+title match."
        ),
    )
    stats: Optional[AlbumQualityStats] = Field(
        None,
        description=(
            "Format / quality / size summary of the existing album. May be "
            "None if stats could not be computed (e.g. files missing)."
        ),
    )


class IncomingAlbumInfo(BaseModel):
    """Format / quality / size summary of the import being considered.

    Sent alongside ExistingAlbumInfo on an ALBUM_ALREADY_EXISTS 409 so the UI
    can render a side-by-side comparison.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    stats: Optional[AlbumQualityStats] = Field(
        None,
        description="Quality summary of the incoming files, or None if unreadable.",
    )


class ImportJobResponse(BaseModel):
    """Response when creating an import job."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    job_id: str = Field(..., description="UUID identifying the import job")
    status: Literal["pending"] = Field(..., description="Initial status")
    album_path: str = Field(..., description="The album path being imported")
    message: str = Field(..., description="Human-readable status message")


class ImportJobError(BaseModel):
    """Error details for a failed import job."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")


class ImportJobStatusResponse(BaseModel):
    """Response for import job status polling."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    job_id: str = Field(..., description="UUID of the import job")
    status: ImportJobStatus = Field(
        ..., description="Current job status"
    )
    album_path: str = Field(..., description="The album path being imported")
    started_at: Optional[datetime] = Field(
        None, description="When the task started processing"
    )
    completed_at: Optional[datetime] = Field(
        None, description="When the job completed"
    )
    destination_path: Optional[str] = Field(
        None, description="Final path in beets library (on success)"
    )
    error: Optional[ImportJobError] = Field(
        None, description="Error details (on failure)"
    )


class AlbumImportState(BaseModel):
    """Import state for a single album."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    state: ImportState = Field(
        ..., description="Current import state"
    )
    job_id: Optional[str] = Field(None, description="Job ID (in_progress only)")
    started_at: Optional[datetime] = Field(None, description="Start time (in_progress only)")
    completed_at: Optional[datetime] = Field(None, description="Completion time (done only)")
    destination_path: Optional[str] = Field(None, description="Library path (done only)")


class ImportStatusCounts(BaseModel):
    """Summary counts by state."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    pending: int = Field(..., ge=0, description="Albums awaiting import")
    in_progress: int = Field(..., ge=0, description="Albums being imported")
    done: int = Field(..., ge=0, description="Successfully imported albums")


class BulkImportStatusResponse(BaseModel):
    """Response for bulk import status endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    albums: Dict[str, AlbumImportState] = Field(
        ..., description="Map of album paths to import states"
    )
    counts: ImportStatusCounts = Field(..., description="Summary counts")
    import_mode: ImportMode = Field(
        ..., description="Library import mode"
    )


# Error code constants
class ImportErrorCodes:
    """Error codes specific to import operations."""

    # Request validation errors (400)
    INVALID_ALBUM_PATH = "INVALID_ALBUM_PATH"
    PATH_OUTSIDE_IMPORT = "PATH_OUTSIDE_IMPORT"
    ALBUM_NOT_FOUND = "ALBUM_NOT_FOUND"
    NO_AUDIO_FILES = "NO_AUDIO_FILES"
    INVALID_CANDIDATE = "INVALID_CANDIDATE"
    TRACK_COUNT_MISMATCH = "TRACK_COUNT_MISMATCH"

    # Resource not found errors (404)
    LIBRARY_NOT_FOUND = "LIBRARY_NOT_FOUND"
    NO_IMPORT_PATH = "NO_IMPORT_PATH"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"

    # Conflict errors (409)
    IMPORT_IN_PROGRESS = "IMPORT_IN_PROGRESS"
    ALBUM_ALREADY_EXISTS = "ALBUM_ALREADY_EXISTS"

    # Task execution errors (stored in job error field)
    TAG_WRITE_FAILED = "TAG_WRITE_FAILED"
    FILE_COPY_FAILED = "FILE_COPY_FAILED"
    FILE_MOVE_FAILED = "FILE_MOVE_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    BEETS_ERROR = "BEETS_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DISK_FULL = "DISK_FULL"
