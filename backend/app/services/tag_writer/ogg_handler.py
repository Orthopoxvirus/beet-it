"""OGG Vorbis tag handler implementation."""

import logging
import os
from typing import Dict, Optional

from mutagen.oggvorbis import OggVorbis, OggVorbisHeaderError

from .base import TagHandler, TagWriteResult
from .exceptions import CorruptedFileError
from .mappings import OGG_TAG_MAPPING, CanonicalTag

logger = logging.getLogger(__name__)

# Reverse mapping from Vorbis comment to canonical tag
VORBIS_TO_CANONICAL = {v: k for k, v in OGG_TAG_MAPPING.items()}


class OGGTagHandler(TagHandler):
    """Handler for OGG Vorbis files using Vorbis comments.

    OGG files use the same Vorbis comment format as FLAC, so the
    implementation is very similar to the FLAC handler.
    """

    @property
    def supported_extensions(self) -> set[str]:
        return {".ogg", ".oga"}

    @property
    def format_name(self) -> str:
        return "ogg"

    def can_handle(self, file_path: str) -> bool:
        """Check if this handler can handle the given file."""
        _, ext = os.path.splitext(file_path.lower())
        return ext in self.supported_extensions

    def read_tags(self, file_path: str) -> Dict[str, Optional[str]]:
        """Read Vorbis comments from an OGG file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        tags: Dict[str, Optional[str]] = {tag: None for tag in OGG_TAG_MAPPING.keys()}

        try:
            try:
                audio = OggVorbis(file_path)
            except OggVorbisHeaderError as e:
                raise CorruptedFileError(
                    f"Invalid OGG file: {file_path}",
                    file_path=file_path,
                )

            # Read Vorbis comments
            if audio.tags:
                for vorbis_key, canonical in VORBIS_TO_CANONICAL.items():
                    value = audio.tags.get(vorbis_key)
                    if value:
                        # Vorbis comments are lists
                        tags[canonical] = str(value[0]) if value else None

            return tags

        except CorruptedFileError:
            raise
        except Exception as e:
            logger.error(f"Error reading OGG tags from {file_path}: {e}")
            raise CorruptedFileError(f"Failed to read OGG tags: {e}", file_path=file_path)

    def write_tags(self, file_path: str, tags: Dict[str, str]) -> TagWriteResult:
        """Write Vorbis comments to an OGG file."""
        if not os.path.exists(file_path):
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"File not found: {file_path}",
                error_code="FILE_NOT_FOUND",
            )

        try:
            try:
                audio = OggVorbis(file_path)
            except OggVorbisHeaderError:
                return TagWriteResult(
                    success=False,
                    file_path=file_path,
                    tags_written={},
                    error=f"Invalid OGG file: {file_path}",
                    error_code="CORRUPTED_FILE",
                )

            tags_written: Dict[str, str] = {}

            for canonical_tag, value in tags.items():
                vorbis_key = OGG_TAG_MAPPING.get(canonical_tag)
                if not vorbis_key:
                    logger.warning(f"Unknown canonical tag: {canonical_tag}")
                    continue

                # Normalize track/disc numbers before writing (Vorbis comments
                # store them as strings); skip the field on an invalid value.
                if value and canonical_tag in (
                    CanonicalTag.TRACK_NUMBER.value,
                    CanonicalTag.DISC_NUMBER.value,
                ):
                    track_num, total = self._normalize_track_number(value)
                    if track_num is None:
                        continue
                    value = f"{track_num}/{total}" if total is not None else str(track_num)

                # Set/clear across every alias key mediafile reads so a stale
                # alias (e.g. "ALBUM ARTIST") can't shadow the new value.
                self._apply_vorbis_tag(audio, canonical_tag, vorbis_key, value, tags_written)

            # Save the file
            audio.save()

            return TagWriteResult(
                success=True,
                file_path=file_path,
                tags_written=tags_written,
            )

        except PermissionError as e:
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"Permission denied: {file_path}",
                error_code="PERMISSION_DENIED",
            )

        except Exception as e:
            logger.error(f"Error writing OGG tags to {file_path}: {e}")
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"Failed to write tags: {e}",
                error_code="WRITE_ERROR",
            )
