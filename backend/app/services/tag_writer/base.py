"""Abstract base class for audio tag handlers.

This module defines the TagHandler interface that all format-specific
handlers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .mappings import VORBIS_ALIAS_KEYS


@dataclass
class TagWriteResult:
    """Result of a tag write operation."""

    success: bool
    file_path: str
    tags_written: Dict[str, str]
    error: Optional[str] = None
    error_code: Optional[str] = None


class TagHandler(ABC):
    """Abstract base class for audio tag handlers.

    Each audio format (MP3, FLAC, OGG, M4A) has its own handler that
    implements this interface. The handler is responsible for reading
    and writing tags in the format-specific way.
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Return the set of file extensions this handler supports.

        Returns:
            Set of lowercase file extensions (e.g., {'.mp3'}).
        """
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return the name of the audio format this handler supports.

        Returns:
            Format name string (e.g., 'mp3', 'flac').
        """
        pass

    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """Check if this handler can handle the given file.

        Args:
            file_path: Path to the audio file.

        Returns:
            True if this handler can handle the file, False otherwise.
        """
        pass

    @abstractmethod
    def read_tags(self, file_path: str) -> Dict[str, Optional[str]]:
        """Read tags from an audio file.

        Args:
            file_path: Path to the audio file.

        Returns:
            Dictionary mapping canonical tag names to their values.
            Values may be None if the tag is not present.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be read.
            CorruptedFileError: If the file is corrupted or invalid.
        """
        pass

    @abstractmethod
    def write_tags(self, file_path: str, tags: Dict[str, str]) -> TagWriteResult:
        """Write tags to an audio file.

        This method preserves existing tags that are not being modified.
        Setting a tag to an empty string removes it from the file.

        Args:
            file_path: Path to the audio file.
            tags: Dictionary mapping canonical tag names to their new values.
                  Only tags present in this dictionary will be modified.
                  Empty string values will remove the tag.

        Returns:
            TagWriteResult indicating success or failure with details.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be written.
            CorruptedFileError: If the file is corrupted or invalid.
        """
        pass

    def _apply_vorbis_tag(
        self,
        audio: Any,
        canonical_tag: str,
        vorbis_key: str,
        value: str,
        tags_written: Dict[str, str],
    ) -> None:
        """Set or clear a Vorbis comment across every alias key mediafile reads.

        Used by the FLAC and OGG handlers. ``mediafile`` (the reader beets uses
        during ``beet update``) resolves some fields — notably ``album_artist`` —
        from several alias keys in priority order and returns the first non-empty
        one. Writing only the canonical key lets a stale, higher-priority alias
        (e.g. ``"ALBUM ARTIST"`` with a space) shadow our value on read-back, so
        the edit silently reverts. Writing/clearing every alias in
        ``VORBIS_ALIAS_KEYS`` keeps the read-back consistent. Fields without
        aliases fall back to the single canonical ``vorbis_key``.

        ``audio`` is a mutagen ``FLAC``/``OggVorbis`` object; an empty ``value``
        clears the field. ``tags_written`` is mutated in place to record the
        change (omitted on a clear that found nothing to remove).
        """
        keys = VORBIS_ALIAS_KEYS.get(canonical_tag, [vorbis_key])

        if value == "":
            removed = False
            for key in keys:
                if audio.tags and key in audio.tags:
                    del audio.tags[key]
                    removed = True
            if removed:
                tags_written[canonical_tag] = ""
            return

        for key in keys:
            audio[key] = value
        tags_written[canonical_tag] = value

    def _normalize_track_number(self, value: str) -> tuple[Optional[int], Optional[int]]:
        """Parse track number value which may include total (e.g., '5/12').

        Args:
            value: Track number string, possibly with total.

        Returns:
            Tuple of (track_number, total) where either may be None.
        """
        if not value or not value.strip():
            return None, None

        value = value.strip()

        if "/" in value:
            parts = value.split("/", 1)
            try:
                track_num = int(parts[0].strip()) if parts[0].strip() else None
                total = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
                return track_num, total
            except ValueError:
                return None, None

        try:
            return int(value), None
        except ValueError:
            return None, None
