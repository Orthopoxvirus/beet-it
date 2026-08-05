"""Service for browsing and managing filesystem directories."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.schemas.beets_config import FilesystemEntry, FilesystemBrowseResponse

logger = logging.getLogger(__name__)


# Allowed paths that can be browsed and where directories can be created
ALLOWED_PATHS = [
    "/data/libraries",
    "/data/import",
    "/data/upload",
    "/data/databases",
    "/config",
]


class FilesystemService:
    """Service for filesystem browsing and directory management.

    This service provides secure access to the filesystem, restricted to
    specific allowed paths to prevent unauthorized access.

    Handles:
    - Browsing directories within allowed mount points
    - Creating new directories
    - Validating paths are within allowed boundaries
    """

    def __init__(self, allowed_paths: Optional[list[str]] = None):
        """Initialize the filesystem service.

        Args:
            allowed_paths: List of allowed base paths. Defaults to ALLOWED_PATHS.
        """
        self.allowed_paths = allowed_paths or ALLOWED_PATHS

    def validate_path(self, path: str) -> bool:
        """Check if a path is within allowed mount boundaries.

        Args:
            path: The path to validate.

        Returns:
            True if the path is within allowed boundaries, False otherwise.
        """
        # Normalize the path to handle .. and other tricks
        normalized_path = os.path.normpath(path)

        # Special case: root path shows allowed roots
        if normalized_path == "/":
            return True

        # Check if the path starts with any allowed path
        for allowed in self.allowed_paths:
            # Normalize allowed path as well
            normalized_allowed = os.path.normpath(allowed)
            if normalized_path == normalized_allowed or normalized_path.startswith(
                normalized_allowed + os.sep
            ):
                return True

        return False

    def get_parent_path(self, path: str) -> Optional[str]:
        """Get the parent directory of a path.

        Returns None if at root or if parent would be outside allowed paths.

        Args:
            path: The current path.

        Returns:
            Parent path or None if at root.
        """
        normalized_path = os.path.normpath(path)

        if normalized_path == "/":
            return None

        parent = os.path.dirname(normalized_path)

        # Check if parent is still within allowed paths or is root
        if parent == "/" or self.validate_path(parent):
            return parent

        # If parent is outside allowed paths, return root
        return "/"

    def browse_directory(self, path: str = "/") -> FilesystemBrowseResponse:
        """List directories at the specified path.

        Args:
            path: Directory path to browse. Defaults to root.

        Returns:
            FilesystemBrowseResponse with directory entries.

        Raises:
            PermissionError: If the path is outside allowed boundaries.
            FileNotFoundError: If the directory doesn't exist.
            ValueError: If the path format is invalid.
        """
        normalized_path = os.path.normpath(path)

        # Validate path is within allowed boundaries
        if not self.validate_path(normalized_path):
            raise PermissionError(f"Access denied: Path is outside allowed mount boundaries")

        # Handle root path specially - show allowed roots
        if normalized_path == "/":
            return self._browse_virtual_root()

        # Check if directory exists
        if not os.path.exists(normalized_path):
            raise FileNotFoundError(f"Directory not found: {normalized_path}")

        if not os.path.isdir(normalized_path):
            raise ValueError(f"Path is not a directory: {normalized_path}")

        entries = []
        try:
            for entry_name in sorted(os.listdir(normalized_path)):
                entry_path = os.path.join(normalized_path, entry_name)
                entry = self._create_entry(entry_name, entry_path)
                if entry:
                    entries.append(entry)
        except PermissionError as e:
            logger.error(f"Permission error browsing {normalized_path}: {e}")
            raise PermissionError(f"Permission denied accessing directory")

        parent = self.get_parent_path(normalized_path)

        return FilesystemBrowseResponse(path=normalized_path, parent=parent, entries=entries)

    def _browse_virtual_root(self) -> FilesystemBrowseResponse:
        """Return a virtual root showing allowed mount points.

        Returns:
            FilesystemBrowseResponse with allowed root directories.
        """
        entries = []

        # Group allowed paths by their top-level parent
        top_level_dirs = set()
        for allowed_path in self.allowed_paths:
            parts = allowed_path.strip("/").split("/")
            if parts:
                top_level_dirs.add("/" + parts[0])

        # Create entries for each top-level directory
        for dir_path in sorted(top_level_dirs):
            if os.path.exists(dir_path):
                entry = FilesystemEntry(
                    name=os.path.basename(dir_path),
                    path=dir_path,
                    type="directory",
                )
                entries.append(entry)

        return FilesystemBrowseResponse(path="/", parent=None, entries=entries)

    def _create_entry(self, name: str, path: str) -> Optional[FilesystemEntry]:
        """Create a FilesystemEntry for a given path.

        Args:
            name: The entry name.
            path: The full path to the entry.

        Returns:
            FilesystemEntry or None if the entry should be hidden.
        """
        try:
            stat_info = os.stat(path)
            is_dir = os.path.isdir(path)

            # Get modification time
            mtime = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc)
            modified = mtime.isoformat()

            return FilesystemEntry(
                name=name,
                path=path,
                type="directory" if is_dir else "file",
                size=None if is_dir else stat_info.st_size,
                modified=modified,
            )
        except (OSError, PermissionError) as e:
            logger.debug(f"Could not stat {path}: {e}")
            return None

    def create_directory(self, parent_path: str, name: str) -> FilesystemEntry:
        """Create a new directory within allowed mount boundaries.

        Args:
            parent_path: Parent directory path.
            name: Name of the new directory to create.

        Returns:
            FilesystemEntry for the created directory.

        Raises:
            PermissionError: If the path is outside allowed boundaries.
            ValueError: If the directory name is invalid.
            FileExistsError: If the directory already exists.
            OSError: If directory creation fails.
        """
        normalized_parent = os.path.normpath(parent_path)

        # Validate parent path
        if not self.validate_path(normalized_parent):
            raise PermissionError("Access denied: Path is outside allowed mount boundaries")

        # Validate directory name
        if not name:
            raise ValueError("Directory name cannot be empty")

        if "/" in name or "\\" in name:
            raise ValueError("Directory name cannot contain path separators")

        if name in (".", ".."):
            raise ValueError("Invalid directory name")

        # Check for invalid filesystem characters
        invalid_chars = '<>:"|?*\x00'
        if any(c in name for c in invalid_chars):
            raise ValueError(
                f"Directory name contains invalid characters: {invalid_chars}"
            )

        # Build full path
        new_path = os.path.join(normalized_parent, name)

        # Check if directory already exists
        if os.path.exists(new_path):
            raise FileExistsError(f"Directory already exists: {new_path}")

        # Create the directory with permissions 775
        try:
            os.makedirs(new_path, mode=0o775, exist_ok=False)
            logger.info(f"Created directory: {new_path}")
        except OSError as e:
            logger.error(f"Failed to create directory {new_path}: {e}")
            raise

        # Return entry for the created directory
        return self._create_entry(name, new_path) or FilesystemEntry(
            name=name, path=new_path, type="directory"
        )
