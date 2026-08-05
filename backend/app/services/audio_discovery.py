"""Shared audio-file discovery for album folders.

Single source of truth for "which audio files does this album folder hold"
so the analyze side (beets_autotag_service), the import validation
(beets_import_service) and the import task (beets_tasks) all agree. A
multi-disc rip keeps its tracks in ``CD 01/`` / ``Disc 2/`` subfolders, so
discovery must walk the tree — a top-level-only listing sees zero audio and
fails the album with "No audio files found" (issue #180).
"""

import os
from typing import List, Optional

from app.services.import_tree import MULTI_DISC_PATTERN
from app.services.tag_writer.mappings import SUPPORTED_EXTENSIONS


def find_audio_files(album_path: str) -> List[str]:
    """Return all audio files under an album folder, including disc subfolders.

    Walks the folder recursively so a multi-disc parent (``Album/Disc 1/``,
    ``Album/Disc 2/``) yields its audio too. Hidden directories are skipped.

    Args:
        album_path: Path to the album folder.

    Returns:
        Sorted list of absolute paths to audio files.
    """
    audio_files = []
    for root, dirs, files in os.walk(album_path):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in files:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                audio_files.append(os.path.join(root, f))
    return sorted(audio_files)


def has_audio_files(album_path: str) -> bool:
    """Return True if the folder tree holds at least one audio file.

    Same traversal rules as :func:`find_audio_files`, but stops at the first
    hit so validation of large folders stays cheap.
    """
    for root, dirs, files in os.walk(album_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                return True
    return False


def infer_disc_number(audio_file: str, album_path: str) -> Optional[int]:
    """Infer a disc number from an audio file's disc subfolder, if any.

    A file directly in the album folder has no folder-derived disc. A file in
    a subfolder gets a disc number only when that subfolder's name matches the
    multi-disc pattern (``Disc N`` / ``CDN`` / ``Album CD N``); other
    subfolders (e.g. ``Bonus/``) yield ``None``.
    """
    parent = os.path.dirname(os.path.normpath(audio_file))
    if os.path.normpath(parent) != os.path.normpath(album_path):
        match = MULTI_DISC_PATTERN.match(os.path.basename(parent))
        if match:
            return int(match.group(2))
    return None
