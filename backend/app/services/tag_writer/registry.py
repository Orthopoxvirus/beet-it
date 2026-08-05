"""Tag writer registry for format detection and handler selection."""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from .base import TagHandler, TagWriteResult
from .exceptions import UnsupportedFormatError
from .mp3_handler import MP3TagHandler
from .flac_handler import FLACTagHandler
from .ogg_handler import OGGTagHandler
from .m4a_handler import M4ATagHandler
from .mappings import EXTENSION_TO_FORMAT, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


@dataclass
class BatchWriteResult:
    """Result of a batch write operation."""

    total: int
    succeeded: int
    failed: int
    results: List[TagWriteResult]


class TagWriterRegistry:
    """Registry for audio tag handlers.

    The registry maintains a list of format-specific handlers and
    provides methods to select the appropriate handler for a file
    based on its extension.
    """

    def __init__(self):
        """Initialize the registry with default handlers."""
        self._handlers: List[TagHandler] = []
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register the default set of format handlers."""
        self.register_handler(MP3TagHandler())
        self.register_handler(FLACTagHandler())
        self.register_handler(OGGTagHandler())
        self.register_handler(M4ATagHandler())

    def register_handler(self, handler: TagHandler):
        """Register a new tag handler.

        Args:
            handler: The handler to register.
        """
        self._handlers.append(handler)
        logger.debug(
            f"Registered handler {handler.__class__.__name__} "
            f"for extensions: {handler.supported_extensions}"
        )

    def get_handler(self, file_path: str) -> Optional[TagHandler]:
        """Get the appropriate handler for a file.

        Args:
            file_path: Path to the audio file.

        Returns:
            The handler for the file, or None if no handler is found.
        """
        for handler in self._handlers:
            if handler.can_handle(file_path):
                return handler
        return None

    def is_supported(self, file_path: str) -> bool:
        """Check if a file format is supported.

        Args:
            file_path: Path to the audio file.

        Returns:
            True if the format is supported, False otherwise.
        """
        return self.get_handler(file_path) is not None

    def get_format(self, file_path: str) -> Optional[str]:
        """Get the format name for a file.

        Args:
            file_path: Path to the audio file.

        Returns:
            The format name (e.g., 'mp3', 'flac'), or None if unsupported.
        """
        _, ext = os.path.splitext(file_path.lower())
        return EXTENSION_TO_FORMAT.get(ext)

    def read_tags(self, file_path: str) -> Dict[str, Optional[str]]:
        """Read tags from an audio file.

        Args:
            file_path: Path to the audio file.

        Returns:
            Dictionary of canonical tag names to values.

        Raises:
            UnsupportedFormatError: If the format is not supported.
            FileNotFoundError: If the file does not exist.
            CorruptedFileError: If the file is corrupted.
        """
        handler = self.get_handler(file_path)
        if not handler:
            _, ext = os.path.splitext(file_path.lower())
            raise UnsupportedFormatError(
                f"Unsupported audio format: {ext}",
                file_path=file_path,
                format=ext,
            )

        return handler.read_tags(file_path)

    def write_tags(self, file_path: str, tags: Dict[str, str]) -> TagWriteResult:
        """Write tags to an audio file.

        Args:
            file_path: Path to the audio file.
            tags: Dictionary of canonical tag names to values.

        Returns:
            TagWriteResult indicating success or failure.
        """
        handler = self.get_handler(file_path)
        if not handler:
            _, ext = os.path.splitext(file_path.lower())
            return TagWriteResult(
                success=False,
                file_path=file_path,
                tags_written={},
                error=f"Unsupported audio format: {ext}",
                error_code="UNSUPPORTED_FORMAT",
            )

        return handler.write_tags(file_path, tags)

    def batch_write(
        self,
        file_tags: List[tuple[str, Dict[str, str]]],
    ) -> BatchWriteResult:
        """Write tags to multiple files.

        Processes files sequentially and continues on individual failures.

        Args:
            file_tags: List of (file_path, tags) tuples.

        Returns:
            BatchWriteResult with success/failure counts and per-file results.
        """
        results: List[TagWriteResult] = []
        succeeded = 0
        failed = 0

        for file_path, tags in file_tags:
            result = self.write_tags(file_path, tags)
            results.append(result)

            if result.success:
                succeeded += 1
            else:
                failed += 1
                logger.warning(
                    f"Failed to write tags to {file_path}: {result.error}"
                )

        return BatchWriteResult(
            total=len(file_tags),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )


# Singleton instance for convenience
_default_registry: Optional[TagWriterRegistry] = None


def get_tag_writer_registry() -> TagWriterRegistry:
    """Get the default tag writer registry singleton.

    Returns:
        The default TagWriterRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = TagWriterRegistry()
    return _default_registry
