"""Custom exceptions for the tag writer module."""


class TagWriterError(Exception):
    """Base exception for tag writer errors."""

    def __init__(self, message: str, file_path: str | None = None):
        super().__init__(message)
        self.file_path = file_path


class UnsupportedFormatError(TagWriterError):
    """Raised when an audio file format is not supported for tag writing."""

    def __init__(self, message: str, file_path: str | None = None, format: str | None = None):
        super().__init__(message, file_path)
        self.format = format


class CorruptedFileError(TagWriterError):
    """Raised when an audio file is corrupted or cannot be parsed."""

    pass


class FileLockedError(TagWriterError):
    """Raised when a file is locked by another process."""

    pass


class WriteError(TagWriterError):
    """Raised when an unexpected error occurs while writing tags."""

    pass
