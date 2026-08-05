"""Derive the ``path`` regex source field for the transformation engine.

The ``path`` source exposes an item's folder location relative to a root
directory (the import folder for import items, the library root for library
items), without the filename. This lets users write regex rules against the
directory structure (e.g. ``Artist/Album``) rather than the absolute path.
"""

import os
from typing import Optional


def relative_source_path(directory: Optional[str], root: Optional[str]) -> str:
    """Folder path of an item relative to ``root``, without the filename.

    Returns a ``/``-separated path with no leading/trailing slash. Returns an
    empty string when the directory is missing, equal to the root (top-level
    items), escapes the root, or when no root is available — an empty source
    surfaces the engine's EMPTY_SOURCE warning rather than leaking an absolute
    filesystem path into a tag.

    Args:
        directory: Absolute directory containing the item.
        root: Root directory to make ``directory`` relative to.

    Returns:
        The relative folder path, or an empty string.
    """
    if not directory or not root:
        return ""

    try:
        rel = os.path.relpath(directory, root)
    except ValueError:
        # e.g. paths on different drives (Windows) — not relativizable.
        return ""

    if rel == "." or rel == os.curdir or rel.startswith(".."):
        return ""

    return rel.replace(os.sep, "/")
