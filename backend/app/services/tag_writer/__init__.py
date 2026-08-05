"""Audio tag writer module.

This module provides format-agnostic tag writing capabilities for
audio files. It supports MP3 (ID3v2.4), FLAC (Vorbis comments),
OGG Vorbis (Vorbis comments), and M4A/MP4 (atoms).

Usage:
    from app.services.tag_writer import get_tag_writer_registry

    registry = get_tag_writer_registry()

    # Write tags to a file
    result = registry.write_tags("/path/to/song.mp3", {
        "album": "Greatest Hits",
        "artist": "The Band",
        "title": "Awesome Song",
        "track_number": "5/12",
    })

    if result.success:
        print(f"Tags written: {result.tags_written}")
    else:
        print(f"Error: {result.error}")
"""

from .base import TagHandler, TagWriteResult
from .registry import TagWriterRegistry, BatchWriteResult, get_tag_writer_registry
from .exceptions import (
    TagWriterError,
    UnsupportedFormatError,
    CorruptedFileError,
    FileLockedError,
    WriteError,
)
from .mappings import (
    CanonicalTag,
    CANONICAL_TAGS,
    FORMAT_MAPPINGS,
    SUPPORTED_EXTENSIONS,
)
from .mp3_handler import MP3TagHandler
from .flac_handler import FLACTagHandler
from .ogg_handler import OGGTagHandler
from .m4a_handler import M4ATagHandler

__all__ = [
    # Base classes
    "TagHandler",
    "TagWriteResult",
    # Registry
    "TagWriterRegistry",
    "BatchWriteResult",
    "get_tag_writer_registry",
    # Exceptions
    "TagWriterError",
    "UnsupportedFormatError",
    "CorruptedFileError",
    "FileLockedError",
    "WriteError",
    # Mappings
    "CanonicalTag",
    "CANONICAL_TAGS",
    "FORMAT_MAPPINGS",
    "SUPPORTED_EXTENSIONS",
    # Handlers
    "MP3TagHandler",
    "FLACTagHandler",
    "OGGTagHandler",
    "M4ATagHandler",
]
