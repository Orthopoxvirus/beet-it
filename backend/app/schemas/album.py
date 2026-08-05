"""Pydantic schemas for album-related API responses."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from typing import List, Optional


class AlbumResponse(BaseModel):
    """Response body for a single album."""

    id: int  # Album ID from beets database
    title: str  # Album title (from beets 'album' column)
    artist: str  # Album artist (from beets 'albumartist' column)
    cover_art_path: Optional[str] = None  # Cover art file path (from beets 'artpath' column)
    cover_version: Optional[int] = None  # Cover file mtime; cache-buster for the cover URL

    class Config:
        from_attributes = True


class AlbumListResponse(BaseModel):
    """Response body for listing albums with pagination."""

    items: List[AlbumResponse]  # Array of album objects
    total: int  # Total number of albums in the library
    skip: int  # Number of records skipped
    limit: int  # Maximum number of records returned


class AlbumLettersResponse(BaseModel):
    """Response body for album starting letters.

    Returns the unique starting letters of album titles in the library.
    Letters A-Z are returned as uppercase, sorted alphabetically.
    Albums starting with numbers or special characters are grouped under '#'.
    """

    letters: List[str] = []  # Array of letters (A-Z) and '#' that have at least one album


class AlbumDetailResponse(BaseModel):
    """Response body for detailed album information."""

    id: int  # Beets album ID
    title: str  # Album title
    artist: str  # Album artist
    year: Optional[int] = None  # Release year
    genre: Optional[str] = None  # Genre
    label: Optional[str] = None  # Record label
    total_tracks: int  # Number of tracks in album
    total_duration: float  # Total duration in seconds
    cover_art_path: Optional[str] = None  # Path to cover art file (internal)
    cover_version: Optional[int] = None  # Cover file mtime; cache-buster for the cover URL
    disc_count: int  # Number of discs
    added: Optional[datetime] = None  # ISO 8601 timestamp when added to library
    album_type: Optional[str] = None  # Album type (album, single, ep, etc.)
    mb_albumid: Optional[str] = None  # MusicBrainz album ID
    # Aggregate audio quality from tracks (dominant values)
    format: Optional[str] = None  # Audio format (e.g. MP3, FLAC)
    bitrate: Optional[int] = None  # Bitrate in bits/second
    sample_rate: Optional[int] = None  # Sample rate in Hz
    bit_depth: Optional[int] = None  # Bit depth (lossless formats only)
    channels: Optional[int] = None  # Channel count

    class Config:
        from_attributes = True


class TrackResponse(BaseModel):
    """Response body for track metadata."""

    id: int  # Beets item (track) ID
    title: str  # Track title
    artist: str  # Track artist
    album: str  # Album title
    album_id: int  # Parent album ID
    track_number: int  # Track number on disc
    disc_number: int  # Disc number
    duration: float  # Duration in seconds
    format: str  # Audio format (mp3, flac, etc.)
    bitrate: int  # Bitrate in kbps
    sample_rate: int  # Sample rate in Hz
    channels: int  # Number of audio channels
    file_size: int  # File size in bytes
    mb_trackid: Optional[str] = None  # MusicBrainz track ID

    class Config:
        from_attributes = True


class TrackListResponse(BaseModel):
    """Response body for listing tracks."""

    items: List[TrackResponse]  # Array of track objects
    total: int  # Total number of tracks


class CoverUploadResponse(BaseModel):
    """Response returned after successful cover art upload or URL download."""

    status: str = "success"  # Always "success" for 200 responses
    album_id: int  # Album ID that was updated
    cover_path: str  # Path to the saved cover art file
    message: str  # Human-readable success message


class CoverUrlRequest(BaseModel):
    """Request body for downloading cover art from a URL."""

    url: str  # URL to download cover art from


class MoveAlbumRequest(BaseModel):
    """Request body for moving an album to a different library."""

    target_library_slug: str  # Slug of the destination library


class MoveAlbumResponse(BaseModel):
    """Response body for a queued album-move job."""

    status: str = "queued"  # Always "queued" for 202 responses
    job_id: str  # Unique ID for the move job (use to query status)
    task_event_id: Optional[int] = None  # Activity-monitor event ID, if recorded
    source_library_slug: str
    target_library_slug: str
    album_id: int  # Source album ID (the target ID is unknown until the task completes)


class ConvertAlbumWavRequest(BaseModel):
    """Request body for converting an imported album's WAVs to FLAC in place."""

    # Removing the WAVs is the point of the conversion (the album *becomes* a
    # FLAC album); keeping them leaves untracked files in the library folder,
    # so deletion is the default and keeping is the opt-out.
    delete_originals: bool = True


class ConvertAlbumWavResponse(BaseModel):
    """Response body for a queued in-place WAV→FLAC conversion job."""

    status: str = "queued"  # Always "queued" for 202 responses
    job_id: str  # Audio-op job ID (poll /beets/audio-op/{job_id}/status)
    album_id: int
    wav_track_count: int  # Number of WAV tracks that will be converted
    message: str


class DeleteAlbumMode(str, Enum):
    """How to dispose of an album's files when removing it from a library.

    The beets DB rows are removed in every mode; the mode only decides what
    happens to the audio files on disk. ``detach`` is the escape hatch for
    duplicate rows that share one folder: the file modes refuse a shared
    folder (mixed-folder guard), so row-only removal is the only way to
    clear such a duplicate.
    """

    delete_files = "delete_files"  # erase the album folder from disk
    move_to_import = "move_to_import"  # move the album folder back to the import staging area
    detach = "detach"  # remove only the beets DB rows; never touch disk


class DeleteAlbumResponse(BaseModel):
    """Response body for a synchronous album deletion."""

    status: str = "deleted"
    album_id: int
    mode: DeleteAlbumMode
    files_deleted: bool  # True when the folder was erased from disk
    relocated_to: Optional[str] = None  # Destination folder when moved to import
