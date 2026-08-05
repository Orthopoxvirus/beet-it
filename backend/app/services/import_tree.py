"""Service for browsing and building import folder tree structures."""

import logging
import os
import re
from typing import Dict, List, Optional, Set

from app.schemas.import_tree import ImportFolderNode
from app.services.scanner.scanner_service import is_audio_filename

logger = logging.getLogger(__name__)

# Multi-disc detection pattern matching beets' heuristic
# Matches patterns like "Album Disc 1", "Album CD2", "Album disc 1" — and the
# bare "Disc 1" / "CD2" folder names of a folder-per-disc rip (empty prefix),
# which beets' own heuristic also treats as disc folders.
MULTI_DISC_PATTERN = re.compile(r"^(.*?)\s*(?:disc|cd)\s*(\d+)", re.IGNORECASE)


def detect_multi_disc(folder_names: List[str]) -> Dict[str, List[str]]:
    """Group folder names by multi-disc prefix.

    This implements beets' heuristic for detecting multi-disc albums.
    Folders that match patterns like "Album Disc 1", "Album CD 2" are
    grouped by their shared prefix.

    Args:
        folder_names: List of folder names to analyze.

    Returns:
        Dictionary mapping prefixes to lists of matching folder names.
        Only includes groups with 2 or more matches (qualifying as multi-disc).
    """
    groups: Dict[str, List[str]] = {}

    for name in folder_names:
        match = MULTI_DISC_PATTERN.match(name)
        if match:
            prefix = match.group(1).strip()
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(name)

    # Only return groups with 2+ matches (true multi-disc albums)
    return {k: v for k, v in groups.items() if len(v) >= 2}


class ImportTreeService:
    """Service for building import folder tree structures.

    This service scans a library's import folder and builds a hierarchical
    tree structure with album detection and multi-disc identification.

    Security:
    - Only returns folders within the library's configured import_path
    - Excludes hidden folders (starting with '.')
    - Sorts folders alphabetically for consistent display
    """

    def __init__(self):
        """Initialize the import tree service."""
        pass

    def build_import_tree(
        self, import_path: str
    ) -> List[ImportFolderNode]:
        """Build the complete import folder tree.

        Args:
            import_path: Absolute path to the library's import folder.

        Returns:
            List of top-level ImportFolderNode objects representing the tree.

        Raises:
            FileNotFoundError: If the import path doesn't exist.
            PermissionError: If access to the directory is denied.
            OSError: For other filesystem errors.
        """
        if not os.path.exists(import_path):
            return []

        if not os.path.isdir(import_path):
            logger.warning(f"Import path is not a directory: {import_path}")
            return []

        return self._scan_directory(import_path, import_path)

    def _scan_directory(
        self, base_path: str, current_path: str
    ) -> List[ImportFolderNode]:
        """Recursively scan a directory and build folder nodes.

        Args:
            base_path: The root import path (for calculating relative paths).
            current_path: The current directory being scanned.

        Returns:
            List of ImportFolderNode objects for the current directory.
        """
        nodes: List[ImportFolderNode] = []

        try:
            entries = sorted(os.listdir(current_path))
        except PermissionError as e:
            logger.warning(f"Permission denied scanning {current_path}: {e}")
            raise
        except OSError as e:
            logger.error(f"Error scanning {current_path}: {e}")
            raise

        # Filter to directories only, excluding hidden folders
        subdirs = []
        for entry in entries:
            if entry.startswith("."):
                continue  # Skip hidden folders

            entry_path = os.path.join(current_path, entry)

            # Handle symlinks safely - only follow if they stay within import path
            if os.path.islink(entry_path):
                try:
                    resolved = os.path.realpath(entry_path)
                    # Normalize both paths for comparison
                    resolved_normalized = os.path.normpath(resolved)
                    base_normalized = os.path.normpath(base_path)

                    # Skip symlinks that point outside the import path
                    if not resolved_normalized.startswith(base_normalized + os.sep) and \
                       resolved_normalized != base_normalized:
                        logger.debug(f"Skipping symlink outside import path: {entry_path}")
                        continue

                    # Check if resolved target is a directory
                    if not os.path.isdir(resolved):
                        continue
                except OSError:
                    # Skip broken symlinks
                    continue
            elif not os.path.isdir(entry_path):
                continue

            subdirs.append(entry)

        # Detect multi-disc albums among children
        multi_disc_groups = detect_multi_disc(subdirs)
        multi_disc_folders: Set[str] = set()
        for folders in multi_disc_groups.values():
            multi_disc_folders.update(folders)

        # Build nodes for each subdirectory
        for subdir in subdirs:
            subdir_path = os.path.join(current_path, subdir)
            relative_path = os.path.relpath(subdir_path, base_path)

            # Recursively scan children
            children = self._scan_directory(base_path, subdir_path)
            has_subfolders = len(children) > 0
            has_audio = self._has_audio_files(subdir_path)

            # Suppress leftover husk folders: a folder with neither audio
            # files nor (surviving) subfolders is dead weight — e.g. an artist
            # directory left behind after its last album was deleted (possibly
            # with a stray cover.jpg / .DS_Store the cleanup couldn't rmdir),
            # or a parent whose children were themselves all husks. Showing it
            # would surface a phantom album. (Issue #65.)
            if not has_subfolders and not has_audio:
                continue

            # Determine if this is an album folder
            # An album folder is either:
            # 1. A leaf folder (no subdirectories) that holds audio directly -
            #    unless it's a disc folder in a multi-disc set
            # 2. A parent of multi-disc folders

            # Check if this folder is a multi-disc parent
            child_names = [child.name for child in children]
            is_multi_disc_parent = bool(detect_multi_disc(child_names))

            # Determine is_album status
            if subdir in multi_disc_folders:
                # This is a disc folder in a multi-disc set - NOT an album
                is_album = False
            elif is_multi_disc_parent:
                # This is a multi-disc parent - IS an album
                is_album = True
            elif not has_subfolders:
                # Leaf folder - an album only if it actually holds audio.
                # Audio-less leaves were already suppressed above, so has_audio
                # is True here; the expression stays defensive against future
                # changes to the suppression rule.
                is_album = has_audio
            else:
                # Has subdirectories but not multi-disc - NOT an album
                is_album = False

            node = ImportFolderNode(
                name=subdir,
                path=relative_path,
                is_album=is_album,
                is_multi_disc_parent=is_multi_disc_parent,
                children=children,
                has_subfolders=has_subfolders,
            )
            nodes.append(node)

        return nodes

    def _has_audio_files(self, dir_path: str) -> bool:
        """Return True if `dir_path` directly contains at least one audio file.

        Non-recursive: only the directory's own files are considered, since
        audio in subfolders is represented by those subfolders being children.
        Used to tell a real album folder apart from an empty/stray-file husk.
        """
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if entry.is_file() and is_audio_filename(entry.name):
                        return True
        except OSError as e:
            logger.warning(f"Error checking audio files in {dir_path}: {e}")
        return False
