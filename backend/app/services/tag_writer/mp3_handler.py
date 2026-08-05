"""MP3/ID3v2.4 tag handler implementation."""

import logging
import os
from typing import Dict, Optional

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.id3._frames import (
    TALB,
    TIT2,
    TPE1,
    TPE2,
    TCON,
    TRCK,
    TPOS,
)

from .base import TagHandler, TagWriteResult
from .exceptions import CorruptedFileError, WriteError
from .mappings import MP3_TAG_MAPPING, CanonicalTag

logger = logging.getLogger(__name__)

# Reverse mapping from ID3 frame to canonical tag
ID3_TO_CANONICAL = {v: k for k, v in MP3_TAG_MAPPING.items()}

# Frame classes for each tag type
FRAME_CLASSES = {
    "TALB": TALB,
    "TIT2": TIT2,
    "TPE1": TPE1,
    "TPE2": TPE2,
    "TCON": TCON,
    "TRCK": TRCK,
    "TPOS": TPOS,
}


class MP3TagHandler(TagHandler):
    """Handler for MP3 files using ID3v2.4 tags."""

    @property
    def supported_extensions(self) -> set[str]:
        return {".mp3"}

    @property
    def format_name(self) -> str:
        return "mp3"

    def can_handle(self, file_path: str) -> bool:
        """Check if this handler can handle the given file."""
        _, ext = os.path.splitext(file_path.lower())
        return ext in self.supported_extensions

    def read_tags(self, file_path: str) -> Dict[str, Optional[str]]:
        """Read ID3 tags from an MP3 file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        tags: Dict[str, Optional[str]] = {tag: None for tag in MP3_TAG_MAPPING.keys()}

        try:
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                # No ID3 tags present
                return tags

            # Read text frames
            for frame_id, canonical in ID3_TO_CANONICAL.items():
                frame = audio.get(frame_id)
                if frame:
                    # Handle TRCK and TPOS which may have "num/total" format
                    if frame_id in ("TRCK", "TPOS"):
                        # Return the full value including total if present
                        text = str(frame.text[0]) if frame.text else None
                        tags[canonical] = text
                    else:
                        tags[canonical] = str(frame.text[0]) if frame.text else None

            return tags

        except Exception as e:
            logger.error(f"Error reading ID3 tags from {file_path}: {e}")
            raise CorruptedFileError(f"Failed to read ID3 tags: {e}", file_path=file_path)

    def write_tags(self, file_path: str, tags: Dict[str, str]) -> TagWriteResult:
        """Write ID3v2.4 tags to an MP3 file."""
        if not os.path.exists(file_path):
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"File not found: {file_path}",
                error_code="FILE_NOT_FOUND",
            )

        try:
            # Try to load existing tags, create new if none exist
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                audio = ID3()

            tags_written: Dict[str, str] = {}

            for canonical_tag, value in tags.items():
                frame_id = MP3_TAG_MAPPING.get(canonical_tag)
                if not frame_id:
                    logger.warning(f"Unknown canonical tag: {canonical_tag}")
                    continue

                # Remove the tag if value is empty
                if value == "":
                    if frame_id in audio:
                        del audio[frame_id]
                        tags_written[canonical_tag] = ""
                    continue

                # Get the frame class
                frame_class = FRAME_CLASSES.get(frame_id)
                if not frame_class:
                    logger.warning(f"No frame class for: {frame_id}")
                    continue

                # Handle track/disc numbers which may include total
                if canonical_tag in (
                    CanonicalTag.TRACK_NUMBER.value,
                    CanonicalTag.DISC_NUMBER.value,
                ):
                    track_num, total = self._normalize_track_number(value)
                    if track_num is not None:
                        if total is not None:
                            value = f"{track_num}/{total}"
                        else:
                            value = str(track_num)
                    else:
                        # Invalid track number, skip
                        continue

                # Create and add the frame (encoding=3 is UTF-8)
                audio[frame_id] = frame_class(encoding=3, text=[value])
                tags_written[canonical_tag] = value

            # Save with ID3v2.4
            audio.save(file_path, v2_version=4)

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
            logger.error(f"Error writing ID3 tags to {file_path}: {e}")
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"Failed to write tags: {e}",
                error_code="WRITE_ERROR",
            )
