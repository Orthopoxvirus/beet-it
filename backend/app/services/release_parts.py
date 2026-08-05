"""Multi-part release detection for import-as-is jobs.

A multi-part release (an audiobook "Komplettlesung" / box set) ships several
logical albums in one drop-zone folder — either as one subfolder per part, or
flat with a per-part filename prefix (``01 - Die Gefährten - 00001 - …``).
Importing such a release as a single album collapses every part into one
library folder named after the first part (issue #190), so the import task
splits the release into parts and imports each as its own album.

Detection is deliberately conservative: when in doubt, the release stays a
single album — a wrongly-merged import is fixable by hand, a wrongly-split
music album pollutes the library with one-track fragments.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.import_tree import MULTI_DISC_PATTERN

# Leading part prefix on a flat multi-part release: ``NN - <part name> - <rest>``.
# The part name is matched non-greedily up to the next separator; that keeps the
# grouping key stable even when the rest of the filename varies per chapter.
PART_PREFIX_PATTERN = re.compile(r"^(?P<num>\d{1,2})\s*-\s*(?P<name>.+?)\s*-\s*\S")

# A flat prefix group must hold at least this many files to count as a part —
# a normal music album's ``NN - Title`` tracks form groups of one each.
MIN_FILES_PER_PREFIX_PART = 2

# Sanity ceiling: more groups than this is track numbering, not a part scheme.
MAX_PARTS = 25


@dataclass
class ReleasePart:
    """One logical album within a release.

    ``name`` is a human-readable hint (subfolder name or ``NN - <part name>``
    prefix) used for logging and album-title disambiguation; ``None`` for a
    single-part release. ``root`` is the folder disc-subfolder inference runs
    against (the part's subfolder when the release ships one per part).
    """

    name: Optional[str]
    root: str
    files: List[str] = field(default_factory=list)


def split_release_parts(audio_files: List[str], album_path: str) -> List[ReleasePart]:
    """Split a release's audio files into logical album parts.

    Tries subfolder grouping first (the release ships one folder per part),
    then the flat ``NN - <name> - `` filename-prefix scheme. Disc subfolders
    (``CD 1`` / ``Disc 2``) are *not* parts — they stay one multi-disc album.
    Falls back to a single part covering everything when no scheme applies.

    Args:
        audio_files: All audio files of the release (absolute paths).
        album_path: The release folder being imported.

    Returns:
        List of :class:`ReleasePart`, length 1 when the release is not
        recognisably multi-part.
    """
    single = [ReleasePart(name=None, root=album_path, files=list(audio_files))]
    parts = _split_by_subfolder(audio_files, album_path) or _split_by_filename_prefix(
        audio_files, album_path
    )
    return parts or single


def _split_by_subfolder(
    audio_files: List[str], album_path: str
) -> Optional[List[ReleasePart]]:
    """Group by top-level subfolder when the release ships one per part.

    Applies only when *all* audio lives in subfolders, at least two exist, and
    none is a disc folder — ``Album/CD 1``, ``Album/Disc 2`` is a multi-disc
    single album, not a multi-part release.
    """
    norm_root = os.path.normpath(album_path)
    groups: Dict[str, List[str]] = {}
    for f in audio_files:
        rel = os.path.relpath(os.path.normpath(f), norm_root)
        if rel.startswith(".."):
            return None
        top = rel.split(os.sep)[0]
        if top == rel:
            # Audio directly in the release root — layout is flat or mixed.
            return None
        groups.setdefault(top, []).append(f)

    if not 2 <= len(groups) <= MAX_PARTS:
        return None
    if any(MULTI_DISC_PATTERN.match(name) for name in groups):
        return None

    return [
        ReleasePart(name=name, root=os.path.join(album_path, name), files=sorted(files))
        for name, files in sorted(groups.items())
    ]


def _split_by_filename_prefix(
    audio_files: List[str], album_path: str
) -> Optional[List[ReleasePart]]:
    """Group a flat release by its leading ``NN - <part name> - `` prefix.

    Every file must match, at least two distinct parts with distinct part
    numbers must emerge, and every part needs at least
    :data:`MIN_FILES_PER_PREFIX_PART` files — otherwise this is a normal
    ``NN - Title`` track listing and the release stays one album.
    """
    norm_root = os.path.normpath(album_path)
    groups: Dict[Tuple[int, str], List[str]] = {}
    display_names: Dict[Tuple[int, str], str] = {}
    for f in audio_files:
        if os.path.dirname(os.path.normpath(f)) != norm_root:
            # Prefix scheme only applies to fully flat releases.
            return None
        base = os.path.splitext(os.path.basename(f))[0]
        match = PART_PREFIX_PATTERN.match(base)
        if not match:
            return None
        name = re.sub(r"\s+", " ", match.group("name")).strip()
        if not re.search(r"[^\W\d_]", name):
            # Purely numeric "part name" (e.g. ``01 - 02 - Title``) is a
            # disc/track numbering scheme, not a part title.
            return None
        key = (int(match.group("num")), name.casefold())
        groups.setdefault(key, []).append(f)
        display_names.setdefault(key, f"{match.group('num')} - {name}")

    if not 2 <= len(groups) <= MAX_PARTS:
        return None
    if any(len(files) < MIN_FILES_PER_PREFIX_PART for files in groups.values()):
        return None
    part_numbers = [num for num, _ in groups]
    if len(set(part_numbers)) != len(part_numbers):
        return None
    if len({name for _, name in groups}) == 1:
        # Same "part name" under every number (``01 - Album - Track``,
        # ``02 - Album - Track``): the number marks a disc, not a part.
        return None

    return [
        ReleasePart(name=display_names[key], root=album_path, files=sorted(groups[key]))
        for key in sorted(groups)
    ]


def disambiguate_part_albums(
    part_metas: List[Dict[str, Any]], parts: List[ReleasePart]
) -> None:
    """Suffix the part name onto album titles that collide across parts.

    Per-part metadata comes from the files' own tags, which normally already
    distinguish the parts. When tags are missing or uniform, several parts
    resolve to the same artist+album — they would share one destination folder
    and produce duplicate album rows, silently re-collapsing the split. Mutates
    ``part_metas`` in place.
    """
    counts = Counter(
        (meta["artist"].casefold(), meta["album"].casefold()) for meta in part_metas
    )
    for i, (meta, part) in enumerate(zip(part_metas, parts)):
        if counts[(meta["artist"].casefold(), meta["album"].casefold())] > 1:
            suffix = part.name or f"Teil {i + 1}"
            meta["album"] = f"{meta['album']} - {suffix}"
