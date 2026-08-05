"""M4A/MP4 atoms tag handler implementation."""

import logging
import os
from typing import Dict, Optional

from mutagen.mp4 import MP4, MP4StreamInfoError

from .base import TagHandler, TagWriteResult
from .exceptions import CorruptedFileError
from .mappings import M4A_TAG_MAPPING, CanonicalTag

logger = logging.getLogger(__name__)

# Reverse mapping from MP4 atom to canonical tag
MP4_TO_CANONICAL = {v: k for k, v in M4A_TAG_MAPPING.items()}


class M4ATagHandler(TagHandler):
    """Handler for M4A/MP4/AAC files using MP4 atoms.

    M4A files use a different tagging system than MP3 and OGG.
    Track and disc numbers are stored as tuples (number, total).
    """

    @property
    def supported_extensions(self) -> set[str]:
        return {".m4a", ".mp4", ".aac"}

    @property
    def format_name(self) -> str:
        return "m4a"

    def can_handle(self, file_path: str) -> bool:
        """Check if this handler can handle the given file."""
        _, ext = os.path.splitext(file_path.lower())
        return ext in self.supported_extensions

    def read_tags(self, file_path: str) -> Dict[str, Optional[str]]:
        """Read MP4 atoms from an M4A/MP4 file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        tags: Dict[str, Optional[str]] = {tag: None for tag in M4A_TAG_MAPPING.keys()}

        try:
            try:
                audio = MP4(file_path)
            except MP4StreamInfoError as e:
                raise CorruptedFileError(
                    f"Invalid M4A/MP4 file: {file_path}",
                    file_path=file_path,
                )

            if not audio.tags:
                return tags

            # Read standard text atoms
            for atom_key, canonical in MP4_TO_CANONICAL.items():
                if canonical in (
                    CanonicalTag.TRACK_NUMBER.value,
                    CanonicalTag.DISC_NUMBER.value,
                ):
                    # Handle track/disc numbers separately
                    continue

                value = audio.tags.get(atom_key)
                if value:
                    if isinstance(value, list) and value:
                        tags[canonical] = str(value[0])
                    else:
                        tags[canonical] = str(value)

            # Handle track number (trkn) - stored as [(track, total)]
            trkn = audio.tags.get("trkn")
            if trkn and isinstance(trkn, list) and len(trkn) > 0:
                track_tuple = trkn[0]
                if isinstance(track_tuple, tuple) and len(track_tuple) >= 1:
                    track_num = track_tuple[0]
                    total = track_tuple[1] if len(track_tuple) > 1 else None
                    if total and total > 0:
                        tags[CanonicalTag.TRACK_NUMBER.value] = f"{track_num}/{total}"
                    elif track_num:
                        tags[CanonicalTag.TRACK_NUMBER.value] = str(track_num)

            # Handle disc number (disk) - stored as [(disc, total)]
            disk = audio.tags.get("disk")
            if disk and isinstance(disk, list) and len(disk) > 0:
                disc_tuple = disk[0]
                if isinstance(disc_tuple, tuple) and len(disc_tuple) >= 1:
                    disc_num = disc_tuple[0]
                    total = disc_tuple[1] if len(disc_tuple) > 1 else None
                    if total and total > 0:
                        tags[CanonicalTag.DISC_NUMBER.value] = f"{disc_num}/{total}"
                    elif disc_num:
                        tags[CanonicalTag.DISC_NUMBER.value] = str(disc_num)

            return tags

        except CorruptedFileError:
            raise
        except Exception as e:
            logger.error(f"Error reading M4A tags from {file_path}: {e}")
            raise CorruptedFileError(f"Failed to read M4A tags: {e}", file_path=file_path)

    def write_tags(self, file_path: str, tags: Dict[str, str]) -> TagWriteResult:
        """Write MP4 atoms to an M4A/MP4 file."""
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
                audio = MP4(file_path)
            except MP4StreamInfoError:
                return TagWriteResult(
                    success=False,
                    file_path=file_path,
                    tags_written={},
                    error=f"Invalid M4A/MP4 file: {file_path}",
                    error_code="CORRUPTED_FILE",
                )

            # Create tags if they don't exist
            if audio.tags is None:
                audio.add_tags()

            tags_written: Dict[str, str] = {}

            for canonical_tag, value in tags.items():
                atom_key = M4A_TAG_MAPPING.get(canonical_tag)
                if not atom_key:
                    logger.warning(f"Unknown canonical tag: {canonical_tag}")
                    continue

                # Remove the tag if value is empty
                if value == "":
                    if atom_key in audio.tags:
                        del audio.tags[atom_key]
                        tags_written[canonical_tag] = ""
                    continue

                # Handle track number
                if canonical_tag == CanonicalTag.TRACK_NUMBER.value:
                    track_num, total = self._normalize_track_number(value)
                    if track_num is not None:
                        # MP4 stores as tuple (track, total)
                        audio.tags["trkn"] = [(track_num, total or 0)]
                        if total:
                            tags_written[canonical_tag] = f"{track_num}/{total}"
                        else:
                            tags_written[canonical_tag] = str(track_num)
                    continue

                # Handle disc number
                if canonical_tag == CanonicalTag.DISC_NUMBER.value:
                    disc_num, total = self._normalize_track_number(value)
                    if disc_num is not None:
                        # MP4 stores as tuple (disc, total)
                        audio.tags["disk"] = [(disc_num, total or 0)]
                        if total:
                            tags_written[canonical_tag] = f"{disc_num}/{total}"
                        else:
                            tags_written[canonical_tag] = str(disc_num)
                    continue

                # Set standard text atom
                audio.tags[atom_key] = [value]
                tags_written[canonical_tag] = value

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
            logger.error(f"Error writing M4A tags to {file_path}: {e}")
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"Failed to write tags: {e}",
                error_code="WRITE_ERROR",
            )
