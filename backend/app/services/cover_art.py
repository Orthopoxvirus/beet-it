"""Materialise a beets-recognised cover-art file for an album folder.

beet-it's import and move pipelines don't run beets' ``fetchart`` / ``embedart``
plugins, so nothing automatically writes a folder cover or sets ``artpath``.
Albums therefore land with their cover in one of three states:

* under a non-standard filename beets discovery can't see — most commonly the
  scene-release ``00-<release-name>.jpg`` artwork;
* only embedded in the audio tags, with no image file on disk;
* genuinely absent.

This module turns the first two into a discoverable ``albumart.*`` (or whatever
``art_filename`` the library configures), so the stored ``artpath`` can point at
a real file and every view — the album grid *and* the detail page — renders the
same art instead of the grid falling back to a placeholder.

The functions here are pure filesystem helpers (no DB, no beets models), which
keeps them straightforward to unit-test.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

# Image file extensions treated as cover-art candidates. Mirrors
# ``BeetsLibraryService.COVER_ART_EXTENSIONS`` — keep the two in sync.
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# Filename stems beets' folder discovery recognises. Mirrors
# ``BeetsLibraryService.COVER_ART_FILENAMES``.
RECOGNISED_COVER_STEMS = ("cover", "albumart", "folder", "front")

# Scene releases name their cover ``00-<release>.jpg`` (the track-zero
# convention). Matches a leading ``00`` followed by a separator.
_SCENE_ART_RE = re.compile(r"^00[-_. ]", re.IGNORECASE)

# Audio extensions whose embedded art we'll consider extracting. Kept local so
# this module stays a dependency-free leaf (no import of the tag-writer maps).
_AUDIO_EXTS = (
    ".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".opus",
    ".wav", ".wma", ".aac", ".alac", ".ape", ".wv",
)


def get_art_filename(config_path: Optional[str]) -> str:
    """Get the configured cover-art basename (``art_filename``) from beets config.

    Args:
        config_path: Path to beets config file.

    Returns:
        The configured ``art_filename`` (e.g. ``"albumart"``), defaulting to
        ``"albumart"`` when unset or unreadable.
    """
    default = "albumart"
    if not config_path or not os.path.exists(config_path):
        return default
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
        art = config.get("art_filename")
        return art if isinstance(art, str) and art else default
    except Exception as e:  # noqa: BLE001 - config read is best-effort
        logger.warning(f"Error reading art_filename from beets config: {e}")
        return default


def _list_dir(folder: str) -> List[str]:
    try:
        return sorted(os.listdir(folder))
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return []


def _images_in(folder: str) -> List[str]:
    return [n for n in _list_dir(folder) if os.path.splitext(n)[1].lower() in IMAGE_EXTS]


def recognised_cover_in(folder: str) -> Optional[str]:
    """Absolute path to an existing beets-recognised cover file in *folder*."""
    for name in _images_in(folder):
        stem = os.path.splitext(name)[0].lower()
        if stem in RECOGNISED_COVER_STEMS:
            return os.path.join(folder, name)
    return None


def find_normalizable_cover(folder: str) -> Optional[str]:
    """Pick the single obvious cover candidate in *folder* to promote.

    Conservative by design: a lone scene ``00-*`` image wins; otherwise the
    candidate is taken only when the folder holds exactly one stray image.
    Returns None for an empty folder, an ambiguous one (several non-scene
    images), or any file already named like a recognised cover.
    """
    images = [
        n for n in _images_in(folder)
        if os.path.splitext(n)[0].lower() not in RECOGNISED_COVER_STEMS
    ]
    if not images:
        return None
    scene = [n for n in images if _SCENE_ART_RE.match(n)]
    if len(scene) == 1:
        return os.path.join(folder, scene[0])
    if len(images) == 1:
        return os.path.join(folder, images[0])
    logger.info(
        "cover_art: %d ambiguous candidate image(s) in %s; not normalising",
        len(images), folder,
    )
    return None


def detect_image_ext(data: bytes) -> Optional[str]:
    """Best-effort image extension from magic bytes, or None if unrecognised."""
    if not data:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def read_embedded_art(audio_path: str) -> Optional[bytes]:
    """Return the front-cover image bytes embedded in *audio_path*, or None."""
    try:
        from mediafile import MediaFile
    except ImportError as exc:  # pragma: no cover - mediafile ships with beets
        logger.warning("cover_art: mediafile unavailable, cannot extract art: %s", exc)
        return None
    try:
        return MediaFile(audio_path).art or None
    except Exception as exc:
        logger.debug("cover_art: could not read embedded art from %s: %s", audio_path, exc)
        return None


def _audio_in(folder: str) -> List[str]:
    return [
        os.path.join(folder, n) for n in _list_dir(folder)
        if os.path.splitext(n)[1].lower() in _AUDIO_EXTS
    ]


def ensure_album_cover(
    album_folder: str,
    art_filename: str = "albumart",
    *,
    source_folder: Optional[str] = None,
    audio_files: Optional[List[str]] = None,
) -> Optional[str]:
    """Ensure *album_folder* holds a beets-recognised cover file.

    Returns the absolute path of the cover (existing or newly created), or
    None when the album has no art anywhere. Resolution order, stopping at the
    first hit:

    1. A recognised cover already in *album_folder* — left untouched.
    2. A normalizable candidate (scene ``00-*`` or a single stray image), first
       in *album_folder* then in *source_folder*, copied to
       ``<art_filename><ext>``.
    3. Embedded front-cover art from the first audio track that has any,
       written to ``<art_filename><ext>``.

    Never overwrites an existing recognised cover (step 1 short-circuits). New
    files are *copied*, leaving the source image intact. *source_folder* serves
    the import path, where only audio is moved into *album_folder* and the
    cover image still sits in the original folder. *audio_files* (absolute
    paths) drives embedded extraction; when omitted it's derived from
    *album_folder*.
    """
    if not album_folder or not os.path.isdir(album_folder):
        return None

    # 1. Already discoverable — don't touch it.
    existing = recognised_cover_in(album_folder)
    if existing:
        return existing

    # 2. Promote an unambiguous candidate, preferring the album folder, then
    #    the (import) source folder.
    candidate = find_normalizable_cover(album_folder)
    if candidate is None and source_folder:
        candidate = find_normalizable_cover(source_folder)
    if candidate:
        ext = os.path.splitext(candidate)[1].lower()
        if ext not in IMAGE_EXTS:
            ext = ".jpg"
        dest = os.path.join(album_folder, f"{art_filename}{ext}")
        try:
            if os.path.abspath(candidate) != os.path.abspath(dest):
                # Copy via a temp file + rename so a concurrent reader never
                # sees a half-written cover.
                tmp = dest + ".tmp"
                shutil.copy2(candidate, tmp)
                os.replace(tmp, dest)
            logger.info("cover_art: promoted %s -> %s", candidate, dest)
            return dest
        except OSError as exc:
            logger.warning("cover_art: failed copying %s -> %s: %s", candidate, dest, exc)

    # 3. Extract embedded art from the first track that carries any.
    for audio in (audio_files if audio_files is not None else _audio_in(album_folder)):
        data = read_embedded_art(audio)
        if not data:
            continue
        ext = detect_image_ext(data) or ".jpg"
        dest = os.path.join(album_folder, f"{art_filename}{ext}")
        try:
            tmp = dest + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            logger.info("cover_art: extracted embedded art %s -> %s", audio, dest)
            return dest
        except OSError as exc:
            logger.warning("cover_art: failed writing extracted art %s: %s", dest, exc)
            return None
    return None
