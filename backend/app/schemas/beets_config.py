"""Pydantic schemas for beets configuration management."""

from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator

# beets accepts yes/no/ask for `import.resume` (per
# https://beets.readthedocs.io/en/stable/reference/config.html#resume).
# "ask" is commonly written by the CLI's interactive importer after a failure,
# so our schema must round-trip it without validation errors.
ResumeValue = Union[bool, Literal["yes", "no", "ask"]]


# ============================================================================
# Default Values Constants
# ============================================================================

DEFAULT_PLUGINS = [
    "web",
    "fetchart",
    "embedart",
    "convert",
    "scrub",
    "replaygain",
    "lastgenre",
    "chroma",
    "musicbrainz",
    "discogs",
    "deezer",
    "spotify",
    "permissions",
    "inline",
]

# On a multi-disc release track numbers repeat per disc, so a template keyed
# on $track alone collides (disc 1's "01 - Title" and disc 2's "01 - Title"
# render the same path) and beets overwrites one disc's files with the
# other's. The %if{$multidisc,$disc-} prefix disambiguates multi-disc
# releases while leaving single-disc paths byte-identical; $multidisc comes
# from the bundled `inline` plugin via DEFAULT_ITEM_FIELDS below (the recipe
# from the beets FAQ).
DEFAULT_PATH_TEMPLATES = {
    "default": "$albumartist/$album%aunique{}/%if{$multidisc,$disc-}$track - $title",
    "singleton": "Singles/$artist - $title",
    "comp": "Compilations/$album%aunique{}/%if{$multidisc,$disc-}$track - $title",
    "albumtype_soundtrack": "Soundtracks/$album/%if{$multidisc,$disc-}$track $title",
}

# Computed item fields for the `inline` plugin (beets config key
# `item_fields`).
DEFAULT_ITEM_FIELDS = {
    "multidisc": "1 if disctotal > 1 else 0",
}

DEFAULT_REPLACE_RULES = [
    {"pattern": r"^\.", "replacement": "_"},
    {"pattern": r"[\x00-\x1f]", "replacement": "_"},
    {"pattern": r'[<>:"\?\*\|]', "replacement": "_"},
    {"pattern": r"[\xE8-\xEB]", "replacement": "e"},
    {"pattern": r"[\xEC-\xEF]", "replacement": "i"},
    {"pattern": r"[\xE2-\xE6]", "replacement": "a"},
    {"pattern": r"[\xF2-\xF6]", "replacement": "o"},
    {"pattern": r"[\xF8]", "replacement": "o"},
    {"pattern": r"\.$", "replacement": "_"},
    {"pattern": r"\s+$", "replacement": ""},
]

DEFAULT_CONVERT_SETTINGS = {
    "auto": False,
    "ffmpeg": "/usr/bin/ffmpeg",
    "opts": "-ab 320k -ac 2 -ar 48000",
    "max_bitrate": 320,
    "threads": 1,
}

DEFAULT_PLUGIN_SETTINGS = {
    "lastgenre": {"auto": True, "source": "album"},
    "embedart": {"auto": True},
    "fetchart": {"auto": True},
    "replaygain": {"auto": False},
    "scrub": {"auto": True},
    "permissions": {"file": 664, "dir": 775},
    "match": {"strong_rec_thresh": 0.04},
    "emby": {"host": "", "port": 8096, "userid": "", "apikey": ""},
    "discogs": {"user_token": ""},
}


# ============================================================================
# Plugin-Specific Config Schemas
# ============================================================================


class ImportConfig(BaseModel):
    """Import strategy settings for how beets handles incoming music files."""

    write: bool = Field(default=True, description="Write metadata to files")
    copy: bool = Field(default=True, description="Copy files to library")
    move: bool = Field(default=False, description="Move files to library")
    resume: ResumeValue = Field(
        default=True,
        description='Resume interrupted imports: true/false or "yes"/"no"/"ask"',
    )
    incremental: bool = Field(default=False, description="Skip already-imported directories")

    @field_validator("resume", mode="before")
    @classmethod
    def _coerce_resume(cls, v):
        # PyYAML parses `yes`/`no` as booleans already; pass those through.
        # Beets' own importer can also write the literal string "ask", which we
        # preserve so round-tripping a user's existing config doesn't destroy it.
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in ("yes", "true"):
                return True
            if lowered in ("no", "false"):
                return False
            if lowered == "ask":
                return "ask"
        raise ValueError(
            f"resume must be a boolean or one of 'yes'/'no'/'ask'; got {v!r}"
        )
    quiet_fallback: str = Field(
        default="skip", description='Fallback action when quiet: "skip" | "asis"'
    )
    timid: bool = Field(default=False, description="Always confirm before auto-tagging")
    log: Optional[str] = Field(default=None, description="Path to import log file")


class PathsConfig(BaseModel):
    """Path template settings defining how music files are organized in the library."""

    default: str = Field(
        default=DEFAULT_PATH_TEMPLATES["default"], description="Default path template for albums"
    )
    singleton: str = Field(
        default=DEFAULT_PATH_TEMPLATES["singleton"],
        description="Path template for non-album tracks",
    )
    comp: str = Field(
        default=DEFAULT_PATH_TEMPLATES["comp"], description="Path template for compilations"
    )
    albumtype_soundtrack: str = Field(
        default=DEFAULT_PATH_TEMPLATES["albumtype_soundtrack"],
        description="Path template for soundtracks",
    )


class ConvertConfig(BaseModel):
    """Convert plugin settings for transcoding audio files."""

    auto: bool = Field(default=False, description="Automatically convert on import")
    ffmpeg: str = Field(default="/usr/bin/ffmpeg", description="Path to ffmpeg binary")
    opts: str = Field(default="-ab 320k -ac 2 -ar 48000", description="FFmpeg output options")
    max_bitrate: int = Field(default=320, description="Maximum bitrate in kbps")
    threads: int = Field(default=1, description="Number of conversion threads")


class LastgenreConfig(BaseModel):
    """Lastgenre plugin settings for automatic genre tagging."""

    auto: bool = Field(default=True, description="Automatically fetch genres on import")
    source: str = Field(default="album", description='Genre source: "album" | "track"')


class EmbedartConfig(BaseModel):
    """Embedart plugin settings for embedding album art."""

    auto: bool = Field(default=True, description="Automatically embed art on import")


class FetchartConfig(BaseModel):
    """Fetchart plugin settings for downloading album art."""

    auto: bool = Field(default=True, description="Automatically fetch art on import")


class ReplaygainConfig(BaseModel):
    """Replaygain plugin settings for volume normalization."""

    auto: bool = Field(default=False, description="Automatically calculate replaygain on import")


class ScrubConfig(BaseModel):
    """Scrub plugin settings for cleaning metadata."""

    auto: bool = Field(default=True, description="Automatically scrub metadata on import")


class ReplaceRule(BaseModel):
    """A single replace rule for path sanitization."""

    pattern: str = Field(..., description="Regex pattern to match")
    replacement: str = Field(..., description="Replacement string")


class EmbyConfig(BaseModel):
    """Emby plugin settings for media server integration."""

    host: str = Field(default="", description="Emby server hostname")
    port: int = Field(default=8096, description="Emby server port")
    userid: str = Field(default="", description="Emby user ID")
    apikey: str = Field(default="", description="Emby API key")


class DiscogsConfig(BaseModel):
    """Discogs plugin settings for metadata fetching."""

    user_token: str = Field(default="", description="Discogs personal access token")


class PermissionsConfig(BaseModel):
    """Permissions plugin settings for file/directory permissions (read-only in UI)."""

    file: int = Field(default=664, description="File permissions in octal")
    dir: int = Field(default=775, description="Directory permissions in octal")


class MatchConfig(BaseModel):
    """Autotagger match settings for controlling tag matching strictness."""

    strong_rec_thresh: float = Field(
        default=0.04, ge=0, le=1, description="Strong recommendation threshold 0-1"
    )


# ============================================================================
# Main Config Schema
# ============================================================================


class BeetsConfigSchema(BaseModel):
    """The complete beets configuration structure representing all configurable settings."""

    directory: str = Field(..., description="Path to organized music library")
    library: str = Field(..., description="Path to beets SQLite database file")
    art_filename: str = Field(default="albumart", description="Filename for embedded artwork")
    threaded: bool = Field(default=True, description="Enable threaded operations")
    original_date: bool = Field(default=False, description="Use original release date")
    per_disc_numbering: bool = Field(default=False, description="Number tracks per disc")
    plugins: list[str] = Field(default_factory=lambda: DEFAULT_PLUGINS.copy())
    item_fields: dict[str, str] = Field(
        default_factory=lambda: DEFAULT_ITEM_FIELDS.copy(),
        description="Computed fields for the inline plugin (e.g. multidisc)",
    )
    import_: ImportConfig = Field(default_factory=ImportConfig, alias="import")
    paths: PathsConfig = Field(default_factory=PathsConfig)
    convert: ConvertConfig = Field(default_factory=ConvertConfig)
    lastgenre: LastgenreConfig = Field(default_factory=LastgenreConfig)
    embedart: EmbedartConfig = Field(default_factory=EmbedartConfig)
    fetchart: FetchartConfig = Field(default_factory=FetchartConfig)
    replaygain: ReplaygainConfig = Field(default_factory=ReplaygainConfig)
    scrub: ScrubConfig = Field(default_factory=ScrubConfig)
    replace: list[ReplaceRule] = Field(
        default_factory=lambda: [ReplaceRule(**r) for r in DEFAULT_REPLACE_RULES]
    )
    emby: EmbyConfig = Field(default_factory=EmbyConfig)
    discogs: DiscogsConfig = Field(default_factory=DiscogsConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    match: MatchConfig = Field(default_factory=MatchConfig)

    model_config = {
        "populate_by_name": True,
    }


# ============================================================================
# API Request/Response Schemas
# ============================================================================


class EmbyTestRequest(BaseModel):
    """Request body for testing Emby server connection."""

    host: str = Field(..., description="Emby server hostname or IP")
    port: int = Field(..., description="Emby server port")
    userid: str = Field(..., description="Emby user ID")
    apikey: str = Field(..., description="Emby API key")


class EmbyTestResponse(BaseModel):
    """Response for Emby connection test."""

    success: bool = Field(..., description="Whether connection was successful")
    message: str = Field(..., description="Success or error message")
    server_name: Optional[str] = Field(default=None, description="Emby server name (on success)")
    server_version: Optional[str] = Field(
        default=None, description="Emby server version (on success)"
    )


class EmbyRefreshResponse(BaseModel):
    """Result of a post-import Emby library refresh.

    A refresh is a best-effort side effect — an unreachable Emby must never
    fail the import. ``skipped`` distinguishes "Emby not configured" (nothing
    to do) from an actual refresh failure (``success=False, skipped=False``).
    """

    success: bool = Field(..., description="Whether the refresh was triggered")
    message: str = Field(..., description="Success, skip or error message")
    skipped: bool = Field(
        default=False, description="True when Emby is not configured (no host/API key)"
    )


class FilesystemEntry(BaseModel):
    """A single filesystem entry (file or directory)."""

    name: str = Field(..., description="Entry name")
    path: str = Field(..., description="Full absolute path")
    type: str = Field(..., description='Entry type: "directory" | "file"')
    size: Optional[int] = Field(default=None, description="File size in bytes (files only)")
    modified: Optional[str] = Field(
        default=None, description="ISO 8601 modification timestamp"
    )


class FilesystemBrowseResponse(BaseModel):
    """Response for filesystem browse operations."""

    path: str = Field(..., description="Current directory path")
    parent: Optional[str] = Field(
        default=None, description="Parent directory path (null if at root)"
    )
    entries: list[FilesystemEntry] = Field(..., description="List of directory entries")


class FilesystemCreateRequest(BaseModel):
    """Request body for creating a new directory."""

    path: str = Field(..., description="Parent directory path")
    name: str = Field(..., description="Name of new directory to create")


class FilesystemCreateResponse(BaseModel):
    """Response for directory creation."""

    success: bool = Field(..., description="Whether creation was successful")
    path: str = Field(..., description="Full path to created directory")


class ErrorResponse(BaseModel):
    """Standard error response format."""

    detail: str = Field(..., description="Human-readable error message")
    code: Optional[str] = Field(
        default=None, description="Optional error code for programmatic handling"
    )
