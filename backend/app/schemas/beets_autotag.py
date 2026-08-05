"""Pydantic schemas for beets autotag candidate analysis API endpoints."""

import os
import re
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


# Link validation regex patterns for supported providers
LINK_PATTERNS = {
    # Deezer album URL
    "deezer": re.compile(
        r'^https?://(www\.)?deezer\.com/(us/|fr/|[a-z]{2}/)?album/(\d+)',
        re.IGNORECASE
    ),
    # Spotify album URL
    "spotify": re.compile(
        r'^https?://open\.spotify\.com/(intl-[a-z]{2}/)?album/([a-zA-Z0-9]+)',
        re.IGNORECASE
    ),
    # Discogs release URL — optional locale segment like /de/, /fr/ (i18n)
    "discogs_release": re.compile(
        r'^https?://(?:www\.)?discogs\.com/(?:[a-z]{2}/)?release/(\d+)',
        re.IGNORECASE
    ),
    # Discogs master URL — optional locale segment
    "discogs_master": re.compile(
        r'^https?://(?:www\.)?discogs\.com/(?:[a-z]{2}/)?master/(\d+)',
        re.IGNORECASE
    ),
    # MusicBrainz release URL
    "musicbrainz_url": re.compile(
        r'^https?://(www\.)?musicbrainz\.org/release/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
        re.IGNORECASE
    ),
    # MusicBrainz release ID (UUID only)
    "musicbrainz_uuid": re.compile(
        r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
        re.IGNORECASE
    ),
}


class AnalyzeAlbumRequest(BaseModel):
    """Request body for triggering beets candidate analysis."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    album_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Path to the album folder to analyze. Can be absolute or relative to import folder.",
    )

    force_reanalyze: bool = Field(
        default=False,
        description="If True, bypass cached results and run a fresh MusicBrainz analysis.",
    )

    @field_validator("album_path")
    @classmethod
    def validate_album_path(cls, v: str) -> str:
        """Validate album path format and prevent path traversal."""
        # Strip whitespace
        v = v.strip()

        if not v:
            raise ValueError("Album path cannot be empty")

        # Check for null bytes (security)
        if "\x00" in v:
            raise ValueError("Album path contains invalid characters")

        # Normalize path to detect traversal attempts
        # Note: Full traversal validation happens in the endpoint with library context
        normalized = os.path.normpath(v)

        # Reject paths that try to escape using ..
        if normalized.startswith("..") or "/../" in v or v.endswith("/.."):
            raise ValueError("Album path cannot contain parent directory references")

        return v


class LocalTrackInfo(BaseModel):
    """Information about a local track in the album folder."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    path: str = Field(..., description="Full absolute path to the track file")
    title: Optional[str] = Field(
        None, description="Track title extracted from audio tags (may be None if not tagged)"
    )
    track_num: Optional[int] = Field(None, ge=1, description="Track number from audio tags")
    length: Optional[float] = Field(None, ge=0, description="Track duration in seconds")
    disc: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "Disc number from audio tags, or inferred from a 'CD 01' / 'Disc 2' "
            "subfolder for folder-per-disc rips"
        ),
    )


class LocalAlbumInfo(BaseModel):
    """Information about the local album detected from audio files."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    path: str = Field(..., description="Full absolute path to the album folder")
    artist: Optional[str] = Field(
        None, description="Album artist detected from audio tags (consensus or first track)"
    )
    album: Optional[str] = Field(None, description="Album name detected from audio tags")
    metadata_source: str = Field(
        "tags",
        description=(
            "Where artist/album came from: 'tags' (embedded tags), 'folder' "
            "(parsed from the folder name because tags were empty) or 'mixed' "
            "(one of each). Folder-derived values are low-confidence hints."
        ),
    )
    dominant_format: Optional[str] = Field(
        None,
        description=(
            "Most common container format across the album's tracks "
            "(e.g. 'FLAC', 'MP3'); None if no audio files were read"
        ),
    )
    has_wav: bool = Field(
        False, description="Whether the album folder contains any .wav files"
    )
    has_flac: bool = Field(
        False, description="Whether the album folder contains any .flac files"
    )
    duplicate_wav_count: int = Field(
        0,
        ge=0,
        description=(
            "Number of .wav files that have a same-basename .flac sibling in the "
            "same directory (i.e. duplicates the dedup action would remove)"
        ),
    )
    has_wma: bool = Field(
        False, description="Whether the album folder contains any .wma files"
    )
    wma_recommended_target: Optional[str] = Field(
        None,
        description=(
            "Smart-default convert target for the album's WMA files ('mp3' or "
            "'flac'), chosen from the highest WMA bitrate; None if no WMA"
        ),
    )
    tracks: List[LocalTrackInfo] = Field(
        default_factory=list, description="List of tracks found in the album folder"
    )


class MetadataChange(BaseModel):
    """A proposed change to a metadata field."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    field: str = Field(
        ..., description="Name of the metadata field (e.g., 'artist', 'album', 'year', 'genre')"
    )
    from_value: Optional[str] = Field(
        None, description="Current value in local file (None if field not set)"
    )
    to_value: Optional[str] = Field(
        None, description="Proposed new value from candidate (None if field would be cleared)"
    )


class TrackChange(BaseModel):
    """Per-track comparison row: local file vs. matched candidate track.

    Emitted for every mapped track (not only renamed ones) so the UI can show
    durations and the source filename alongside any title change.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    index: int = Field(..., ge=1, description="Track number (1-indexed)")
    disc: Optional[int] = Field(
        None, ge=1, description="Disc (medium) number, if the release is multi-disc"
    )
    local_title: Optional[str] = Field(None, description="Current track title from local file")
    candidate_title: Optional[str] = Field(
        None, description="Proposed track title from candidate"
    )
    local_length: Optional[float] = Field(
        None, ge=0, description="Local track duration in seconds"
    )
    candidate_length: Optional[float] = Field(
        None, ge=0, description="Candidate track duration in seconds"
    )
    local_path: Optional[str] = Field(
        None, description="Absolute path of the local audio file"
    )


class CandidateTrack(BaseModel):
    """A track from a candidate album match."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    index: int = Field(
        ..., ge=1, description="Track number in the candidate album (1-indexed)"
    )
    disc: Optional[int] = Field(
        None,
        ge=1,
        description="Disc (medium) number this track belongs to; None/1 for "
        "single-disc releases. Preserves the per-disc grouping so multi-disc "
        "imports keep each track on the right CD instead of collapsing the "
        "repeating per-disc track numbers.",
    )
    title: str = Field(..., description="Track title from the candidate source")
    length: Optional[float] = Field(
        None, ge=0, description="Track duration in seconds (if available from source)"
    )
    local_title: Optional[str] = Field(
        None,
        description="Title of the local file paired to this candidate track "
        "(None if there is no local counterpart, i.e. a new track)",
    )
    local_path: Optional[str] = Field(
        None,
        description="Absolute path of the local file paired to this candidate track "
        "(None if there is no local counterpart)",
    )
    changes: List[MetadataChange] = Field(
        default_factory=list,
        description="List of metadata changes for this track compared to local file",
    )


class Candidate(BaseModel):
    """A candidate album match from beets autotag."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    source: str = Field(
        ..., description="Source of the candidate (e.g., 'MusicBrainz', 'Discogs')"
    )
    source_id: Optional[str] = Field(
        None, description="Unique identifier from the source (e.g., MusicBrainz release ID)"
    )
    similarity: float = Field(
        ..., ge=0.0, le=1.0, description="Match similarity score from 0.0 to 1.0 (higher is better)"
    )
    artist: str = Field(..., description="Album artist name from the candidate")
    album: str = Field(..., description="Album title from the candidate")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="Release year of the album")
    label: Optional[str] = Field(None, description="Record label (if available)")
    country: Optional[str] = Field(
        None, description="Release country code (e.g., 'US', 'UK', 'JP')"
    )
    media: Optional[str] = Field(
        None, description="Media format (e.g., 'CD', 'Vinyl', 'Digital Media')"
    )
    tracks: List[CandidateTrack] = Field(
        default_factory=list, description="List of tracks in the candidate album"
    )
    changes: List[MetadataChange] = Field(
        default_factory=list, description="Album-level metadata changes (artist, album, year, etc.)"
    )
    track_changes: List[TrackChange] = Field(
        default_factory=list, description="Summary of track title changes for quick display"
    )
    is_manual: bool = Field(
        default=False,
        description="True if this candidate was manually added via external link"
    )
    cover_url: Optional[str] = Field(
        None,
        description=(
            "Remote cover-art URL from the source (Deezer/Discogs/etc.), if any. "
            "Persisted as the album's art on import when no local cover is found."
        ),
    )


class AnalyzeAlbumResponse(BaseModel):
    """Response from the beets candidate analysis endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    album_path: str = Field(
        ..., description="The album path that was analyzed (as provided in request)"
    )
    local_album: LocalAlbumInfo = Field(
        ..., description="Information about the local album detected from files"
    )
    candidates: List[Candidate] = Field(
        default_factory=list, description="List of candidate matches, sorted by similarity (highest first)"
    )
    manual_candidates: List[Candidate] = Field(
        default_factory=list,
        description="List of manually added candidates (max one per provider)"
    )
    analyzed_at: datetime = Field(
        ..., description="Timestamp when the analysis was performed (ISO 8601 format)"
    )


class AnalyzeJobResponse(BaseModel):
    """Response when starting an async analysis job (modified for queue support)."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    job_id: str = Field(..., description="Unique job ID for tracking the analysis")
    album_path: str = Field(..., description="The album path being analyzed")
    status: Literal["analyzing", "queued", "completed"] = Field(
        ...,
        description="Status: 'analyzing' if dispatched, 'queued' if waiting, 'completed' if cached"
    )
    queue_position: Optional[int] = Field(
        None,
        ge=1,
        description="Position in queue (1-indexed), only present when status is 'queued'"
    )
    message: str = Field(..., description="Human-readable status message")


class AnalyzeStatusResponse(BaseModel):
    """Response containing the status and results of an analysis job."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    job_id: str = Field(..., description="The job ID")
    status: str = Field(
        ..., description="Status: analyzing, completed, or failed"
    )
    started_at: Optional[datetime] = Field(
        None, description="When the analysis started"
    )
    completed_at: Optional[datetime] = Field(
        None, description="When the analysis completed"
    )
    result: Optional[AnalyzeAlbumResponse] = Field(
        None, description="Analysis result (only present when status is 'completed')"
    )
    error: Optional[dict] = Field(
        None, description="Error information (only present when status is 'failed')"
    )


class ConvertAudioRequest(BaseModel):
    """Request to convert an album folder's audio files to a target format.

    Generalises the WAV→FLAC path: ``source_format`` selects which files to
    convert (lossless WAV or usually-lossy WMA) and ``target_format`` the
    encoder (lossless FLAC or MP3 V0).
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    album_path: str = Field(
        ..., description="Path to the album folder (relative to import root or absolute)"
    )
    source_format: Literal["wav", "wma"] = Field(
        ..., description="Which source files to convert"
    )
    target_format: Literal["flac", "mp3"] = Field(
        ..., description="Encode target: 'flac' (lossless) or 'mp3' (V0)"
    )
    delete_originals: bool = Field(
        False,
        description="Delete each source file after its target is written and verified",
    )


class DedupeWavRequest(BaseModel):
    """Request to remove duplicate WAV files (those with a FLAC twin) from a folder."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    album_path: str = Field(
        ..., description="Path to the album folder (relative to import root or absolute)"
    )


class AudioOpJobResponse(BaseModel):
    """Response when starting an async WAV convert / dedup job."""

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, alias_generator=to_camel
    )

    job_id: str = Field(..., description="Unique job ID for tracking the operation")
    album_path: str = Field(..., description="The album path being operated on")
    status: Literal["queued", "running"] = Field(
        ...,
        description=(
            "Job status on enqueue: 'queued' until a worker picks it up, at "
            "which point the task flips it to 'running'"
        ),
    )
    message: str = Field(..., description="Human-readable status message")


class AudioOpStatusResponse(BaseModel):
    """Status + result of an async WAV convert / dedup job."""

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, alias_generator=to_camel
    )

    job_id: str = Field(..., description="The job ID")
    status: str = Field(..., description="queued, running, completed, or failed")
    started_at: Optional[datetime] = Field(None, description="When the op started")
    completed_at: Optional[datetime] = Field(None, description="When the op finished")
    result: Optional[dict] = Field(
        None,
        description=(
            "Per-file counts (converted/skipped/failed/deleted or removed/failed) "
            "present when status is 'completed'"
        ),
    )
    error: Optional[str] = Field(
        None, description="Error message, present when status is 'failed'"
    )


class ErrorResponse(BaseModel):
    """Standard error response format for beets autotag API."""

    detail: str = Field(..., description="Human-readable error message")
    error_code: Optional[str] = Field(
        None, description="Machine-readable error code for programmatic handling"
    )


# Error code constants
class BeetsAutotagErrorCodes:
    """Error codes for beets autotag API."""

    # Existing codes
    INVALID_ALBUM_PATH = "INVALID_ALBUM_PATH"
    PATH_OUTSIDE_IMPORT = "PATH_OUTSIDE_IMPORT"
    NO_IMPORT_PATH = "NO_IMPORT_PATH"
    LIBRARY_NOT_FOUND = "LIBRARY_NOT_FOUND"
    ALBUM_NOT_FOUND = "ALBUM_NOT_FOUND"
    NO_AUDIO_FILES = "NO_AUDIO_FILES"
    ANALYSIS_TIMEOUT = "ANALYSIS_TIMEOUT"
    BEETS_ERROR = "BEETS_ERROR"
    MUSICBRAINZ_ERROR = "MUSICBRAINZ_ERROR"
    TOO_MANY_PATHS = "TOO_MANY_PATHS"
    INVALID_PATH = "INVALID_PATH"
    CACHE_CHECK_ERROR = "CACHE_CHECK_ERROR"

    # New codes for manual candidates
    INVALID_LINK = "INVALID_LINK"
    RELEASE_NOT_FOUND = "RELEASE_NOT_FOUND"
    PLUGIN_NOT_AVAILABLE = "PLUGIN_NOT_AVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RESOLUTION_TIMEOUT = "RESOLUTION_TIMEOUT"

    # New codes for queue
    ALREADY_QUEUED = "ALREADY_QUEUED"
    ALREADY_ANALYZING = "ALREADY_ANALYZING"

    # New codes for WAV convert / dedup
    AUDIO_OP_IN_PROGRESS = "AUDIO_OP_IN_PROGRESS"
    NO_WAV_FILES = "NO_WAV_FILES"
    NO_DUPLICATE_WAVS = "NO_DUPLICATE_WAVS"
    AUDIO_OP_NOT_FOUND = "AUDIO_OP_NOT_FOUND"
    # Generalised audio convert (WAV/WMA → FLAC/MP3)
    NO_SOURCE_FILES = "NO_SOURCE_FILES"


def detect_provider(link: str) -> Optional[str]:
    """Detect the provider from a link and return its name.

    Args:
        link: The link or ID to check.

    Returns:
        Provider name ('deezer', 'spotify', 'discogs', 'musicbrainz') or None if not recognized.
    """
    link = link.strip()
    if not link:
        return None

    if LINK_PATTERNS["deezer"].match(link):
        return "deezer"
    if LINK_PATTERNS["spotify"].match(link):
        return "spotify"
    if LINK_PATTERNS["discogs_release"].match(link) or LINK_PATTERNS["discogs_master"].match(link):
        return "discogs"
    if LINK_PATTERNS["musicbrainz_url"].match(link) or LINK_PATTERNS["musicbrainz_uuid"].match(link):
        return "musicbrainz"

    return None


def extract_id_from_link(link: str, provider: str) -> Optional[str]:
    """Extract the ID from a link for a given provider.

    Args:
        link: The link to extract the ID from.
        provider: The provider name.

    Returns:
        The extracted ID, or None if extraction failed.
    """
    link = link.strip()

    if provider == "deezer":
        match = LINK_PATTERNS["deezer"].match(link)
        if match:
            return match.group(3)  # The album ID

    elif provider == "spotify":
        match = LINK_PATTERNS["spotify"].match(link)
        if match:
            return match.group(2)  # The album ID

    elif provider == "discogs":
        match = LINK_PATTERNS["discogs_release"].match(link)
        if match:
            return match.group(1)  # The release ID
        match = LINK_PATTERNS["discogs_master"].match(link)
        if match:
            return match.group(1)  # The master ID

    elif provider == "musicbrainz":
        match = LINK_PATTERNS["musicbrainz_url"].match(link)
        if match:
            return match.group(2)  # The UUID
        match = LINK_PATTERNS["musicbrainz_uuid"].match(link)
        if match:
            return link.strip()  # The link itself is the UUID

    return None


class ManualCandidateRequest(BaseModel):
    """Request body for adding a manual candidate via external link."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    album_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Path to the album folder for metadata comparison context"
    )

    link: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="External service URL or MusicBrainz release ID"
    )

    @field_validator("album_path")
    @classmethod
    def validate_album_path(cls, v: str) -> str:
        """Validate album path format and prevent path traversal."""
        v = v.strip()

        if not v:
            raise ValueError("Album path cannot be empty")

        # Check for null bytes (security)
        if "\x00" in v:
            raise ValueError("Album path contains invalid characters")

        # Normalize path to detect traversal attempts
        normalized = os.path.normpath(v)

        # Reject paths that try to escape using ..
        if normalized.startswith("..") or "/../" in v or v.endswith("/.."):
            raise ValueError("Album path cannot contain parent directory references")

        return v

    @field_validator("link")
    @classmethod
    def validate_link_format(cls, v: str) -> str:
        """Validate that link matches a supported provider format."""
        v = v.strip()

        if not v:
            raise ValueError("Link cannot be empty")

        # Check against supported patterns
        provider = detect_provider(v)
        if provider is None:
            raise ValueError(
                "Link must be a valid URL from Deezer, Spotify, Discogs, MusicBrainz, "
                "or a MusicBrainz release UUID"
            )

        return v


class ManualCandidateResponse(BaseModel):
    """Response containing the resolved manual candidate."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    candidate: Candidate = Field(
        ...,
        description="The resolved candidate with isManual=true"
    )

    provider: str = Field(
        ...,
        description="Provider name: 'deezer', 'spotify', 'discogs', or 'musicbrainz'"
    )


class CacheStatusResponse(BaseModel):
    """Response from the bulk cache status check endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    cache_status: dict[str, bool] = Field(
        ...,
        description="Map of album path to cache status (true if cached, false otherwise)"
    )
    paths_checked: int = Field(
        ...,
        ge=0,
        description="Number of paths that were checked"
    )
    paths_cached: int = Field(
        ...,
        ge=0,
        description="Number of paths that have cached results"
    )


# --- Analysis Queue Schemas ---


class QueuedItem(BaseModel):
    """An album waiting in the analysis queue."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    album_path: str = Field(..., description="Full path to the album folder")
    position: int = Field(..., ge=1, description="Position in queue (1-indexed)")
    queued_at: datetime = Field(..., description="When the album was added to the queue")


class ActiveItem(BaseModel):
    """An album currently being analyzed."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    album_path: str = Field(..., description="Full path to the album folder")
    job_id: str = Field(..., description="The job ID for this analysis")
    started_at: Optional[datetime] = Field(None, description="When the analysis started")


class AnalyzeQueueResponse(BaseModel):
    """Response for the analyze-queue endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    queue_depth: int = Field(..., ge=0, description="Number of albums waiting in queue")
    active_count: int = Field(..., ge=0, description="Number of analyses currently running")
    max_concurrent: int = Field(..., ge=1, description="Maximum concurrent analyses allowed")
    queued_items: List[QueuedItem] = Field(
        default_factory=list,
        description="Albums waiting in the queue with positions"
    )
    active_items: List[ActiveItem] = Field(
        default_factory=list,
        description="Albums currently being analyzed"
    )


class AnalyzeFolderRequest(BaseModel):
    """Request body for bulk analysis of import folder."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    force: bool = Field(
        default=False,
        description="If True, re-analyze albums even if cached results exist"
    )


class AnalyzeFolderResponse(BaseModel):
    """Response for the analyze-folder bulk endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    enqueued: int = Field(..., ge=0, description="Albums added to the queue")
    dispatched: int = Field(..., ge=0, description="Albums dispatched immediately")
    already_cached: int = Field(..., ge=0, description="Albums skipped (cached)")
    already_queued: int = Field(..., ge=0, description="Albums skipped (already in queue)")
    total: int = Field(..., ge=0, description="Total album folders examined")
    message: str = Field(..., description="Human-readable summary")


class AutoAnalyzeSettingRequest(BaseModel):
    """Request body for updating auto-analyze setting."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    auto_analyze_after_scan: bool = Field(
        ...,
        description="Whether to auto-analyze albums after scan completes"
    )


class AutoAnalyzeSettingResponse(BaseModel):
    """Response for auto-analyze setting endpoints."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    auto_analyze_after_scan: bool = Field(
        ...,
        description="Current value of auto-analyze setting"
    )
    message: Optional[str] = Field(
        None,
        description="Human-readable confirmation (only on PUT)"
    )


class ImportCleanupSettingRequest(BaseModel):
    """Request body for the per-library import-cleanup override.

    All fields are optional: only the ones provided are written to the
    library's override; the rest keep inheriting the global / default value.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    enabled: Optional[bool] = Field(
        None,
        description="Master toggle: clean the drop-zone after a move-import"
    )
    sidecar_extensions: Optional[List[str]] = Field(
        None,
        description="Extensions deleted as junk sidecars (e.g. ['.nfo', '.m3u'])"
    )
    delete_redundant_images: Optional[bool] = Field(
        None,
        description="Delete loose images when the album already has a cover"
    )
    promote_orphan_cover: Optional[bool] = Field(
        None,
        description="Promote the only loose image to album cover when none exists"
    )


class ImportCleanupSettingResponse(BaseModel):
    """Effective import-cleanup config for a library (defaults + override)."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    enabled: bool = Field(..., description="Effective master toggle")
    sidecar_extensions: List[str] = Field(
        ..., description="Effective sidecar extension allowlist (sorted)"
    )
    delete_redundant_images: bool = Field(
        ..., description="Effective redundant-image deletion toggle"
    )
    promote_orphan_cover: bool = Field(
        ..., description="Effective orphan-cover promotion toggle"
    )
    overridden: bool = Field(
        ...,
        description="True when this library has a stored override (vs inherited)"
    )
    message: Optional[str] = Field(
        None,
        description="Human-readable confirmation (only on PUT)"
    )
