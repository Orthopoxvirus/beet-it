"""Canonical tag names and format-specific mappings for audio tag writing.

This module defines the standard tag names used throughout the application
and provides mappings to format-specific tag identifiers for each supported
audio format.
"""

from enum import Enum
from typing import Dict


class CanonicalTag(str, Enum):
    """Canonical tag names used throughout the application."""

    ALBUM = "album"
    ALBUM_ARTIST = "album_artist"
    ARTIST = "artist"
    TITLE = "title"
    GENRE = "genre"
    TRACK_NUMBER = "track_number"
    DISC_NUMBER = "disc_number"


# List of all canonical tag names
CANONICAL_TAGS = [tag.value for tag in CanonicalTag]

# MP3/ID3v2.4 tag frame mappings
MP3_TAG_MAPPING: Dict[str, str] = {
    CanonicalTag.ALBUM.value: "TALB",
    CanonicalTag.ALBUM_ARTIST.value: "TPE2",
    CanonicalTag.ARTIST.value: "TPE1",
    CanonicalTag.TITLE.value: "TIT2",
    CanonicalTag.GENRE.value: "TCON",
    CanonicalTag.TRACK_NUMBER.value: "TRCK",
    CanonicalTag.DISC_NUMBER.value: "TPOS",
}

# FLAC/Vorbis comment tag mappings
FLAC_TAG_MAPPING: Dict[str, str] = {
    CanonicalTag.ALBUM.value: "ALBUM",
    CanonicalTag.ALBUM_ARTIST.value: "ALBUMARTIST",
    CanonicalTag.ARTIST.value: "ARTIST",
    CanonicalTag.TITLE.value: "TITLE",
    CanonicalTag.GENRE.value: "GENRE",
    CanonicalTag.TRACK_NUMBER.value: "TRACKNUMBER",
    CanonicalTag.DISC_NUMBER.value: "DISCNUMBER",
}

# OGG Vorbis uses the same Vorbis comments as FLAC
OGG_TAG_MAPPING: Dict[str, str] = FLAC_TAG_MAPPING.copy()

# Vorbis-comment fields that `mediafile` (which beets' `beet update` uses to
# read tags) resolves from several alias keys in priority order, returning the
# first non-empty one. If we write only the canonical key, a pre-existing
# higher-priority alias — e.g. "ALBUM ARTIST" (with a space), as written by
# Picard/foobar — shadows our value on read-back, so the edit silently reverts.
# To avoid that, the FLAC/OGG handlers write (and, on clear, delete) EVERY key
# listed here. Fields absent from this map have a single Vorbis key and need no
# special handling. Keep these lists in sync with mediafile's StorageStyle
# declarations (see mediafile.MediaFile.albumartist).
VORBIS_ALIAS_KEYS: Dict[str, list[str]] = {
    CanonicalTag.ALBUM_ARTIST.value: ["ALBUM ARTIST", "ALBUM_ARTIST", "ALBUMARTIST"],
}

# M4A/MP4 atom tag mappings
M4A_TAG_MAPPING: Dict[str, str] = {
    CanonicalTag.ALBUM.value: "\xa9alb",
    CanonicalTag.ALBUM_ARTIST.value: "aART",
    CanonicalTag.ARTIST.value: "\xa9ART",
    CanonicalTag.TITLE.value: "\xa9nam",
    CanonicalTag.GENRE.value: "\xa9gen",
    # Note: track_number and disc_number use special tuple format in MP4
    CanonicalTag.TRACK_NUMBER.value: "trkn",
    CanonicalTag.DISC_NUMBER.value: "disk",
}

# All format mappings indexed by format name
FORMAT_MAPPINGS: Dict[str, Dict[str, str]] = {
    "mp3": MP3_TAG_MAPPING,
    "flac": FLAC_TAG_MAPPING,
    "ogg": OGG_TAG_MAPPING,
    "m4a": M4A_TAG_MAPPING,
    "mp4": M4A_TAG_MAPPING,  # M4A and MP4 use the same format
    "aac": M4A_TAG_MAPPING,  # AAC in MP4 container
}

# File extension to format mapping
EXTENSION_TO_FORMAT: Dict[str, str] = {
    ".mp3": "mp3",
    ".flac": "flac",
    ".ogg": "ogg",
    ".oga": "ogg",
    ".m4a": "m4a",
    ".mp4": "mp4",
    ".aac": "aac",
}

# Supported audio file extensions
SUPPORTED_EXTENSIONS = set(EXTENSION_TO_FORMAT.keys())
