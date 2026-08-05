"""Post-import cleanup of the import drop-zone.

After a successful ``move`` import, beets relocates only the **audio** files
into the library. Everything else the release shipped with — artwork, ``.nfo``,
``.m3u``, ``.sfv`` and friends — plus the now audio-empty release folders are
left sitting in ``/data/import/<slug>/``. The scanner keeps counting those
leftovers as import items, so a fully-imported library still looks like it has
hundreds of pending items.

This module removes that junk, but only ever **inside the drop-zone** and never
at the cost of an album's only cover:

* Sidecar files (``.nfo``, ``.m3u`` …) are deleted unconditionally.
* A loose folder image is deleted only when the imported album already has a
  cover (a cover file in the library album folder, or embedded art). When it
  has none, the best loose image is *promoted* into the library album folder as
  ``<art_filename>.<ext>`` first, so the only artwork is preserved rather than
  dropped.
* The release folder and any now-empty parents are pruned, stopping at — and
  never removing — the library's import root.

Every filesystem op is guarded so a cleanup hiccup can never undo an import that
already succeeded; callers treat the returned :class:`CleanupResult` as
best-effort bookkeeping.
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from app.services.beets_library_service import BeetsLibraryService
from app.services.tag_writer.mappings import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# Junk text/metadata sidecars beets leaves next to the audio. Safe to delete
# from the drop-zone unconditionally once the audio has been imported out.
IMPORT_SIDECAR_EXTENSIONS = frozenset(
    {".nfo", ".m3u", ".m3u8", ".sfv", ".srr", ".txt", ".cue", ".log", ".url", ".diz"}
)

# Image extensions considered candidate cover art in the drop-zone.
COVER_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif"}
)

# Preference order when choosing which loose image to promote as the cover.
# Scene-named images (e.g. ``00-release.jpg``) match none of these and fall
# back to the largest-file heuristic.
_PROMOTE_NAME_PRIORITY = ("cover", "albumart", "folder", "front")

# Keys under ``UserSettings.preferences`` where cleanup config lives.
#   preferences["import_cleanup"]               -> global defaults
#   preferences["import_cleanup_by_library"]    -> {str(library_id): override}
# A per-library override is a partial dict; missing keys fall back to the
# global default, and missing global keys fall back to the baked-in defaults.
PREF_GLOBAL_KEY = "import_cleanup"
PREF_LIBRARY_KEY = "import_cleanup_by_library"


@dataclass(frozen=True)
class ImportCleanupConfig:
    """Resolved, per-library drop-zone cleanup configuration.

    Built by :func:`resolve_import_cleanup_config` from the user settings, with
    a per-library override layered over global defaults. ``enabled`` is the
    master toggle; the rest tune what cleanup is allowed to touch.
    """

    enabled: bool = True
    sidecar_extensions: frozenset = IMPORT_SIDECAR_EXTENSIONS
    delete_redundant_images: bool = True
    promote_orphan_cover: bool = True


# Baked-in defaults — the source of truth when nothing is configured.
DEFAULT_IMPORT_CLEANUP_CONFIG = ImportCleanupConfig()


def _normalize_extensions(values: Optional[Iterable[str]]) -> frozenset:
    """Normalize a user-supplied extension list to ``{".ext", …}``.

    Lowercases, trims whitespace, ensures a leading dot, and drops blanks so a
    sloppily-entered allowlist (``"NFO"``, ``" .m3u "``) still matches. A
    non-list value (incl. a bare string, which would otherwise iterate into
    single characters) yields the empty set rather than garbage.
    """
    if not isinstance(values, (list, tuple, set, frozenset)):
        return frozenset()
    out = set()
    for raw in values:
        ext = str(raw).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        out.add(ext)
    return frozenset(out)


def _overlay_config(target: dict, block: Optional[dict]) -> None:
    """Layer a (partial) settings block over ``target`` in place.

    Only recognised keys are copied, so stray keys in the JSONB blob can't
    poison the resolved config. ``None`` values are treated as "unset".
    """
    if not isinstance(block, dict):
        return
    if block.get("enabled") is not None:
        target["enabled"] = bool(block["enabled"])
    sidecars = block.get("sidecar_extensions")
    if isinstance(sidecars, (list, tuple, set, frozenset)):
        target["sidecar_extensions"] = sidecars
    if block.get("delete_redundant_images") is not None:
        target["delete_redundant_images"] = bool(block["delete_redundant_images"])
    if block.get("promote_orphan_cover") is not None:
        target["promote_orphan_cover"] = bool(block["promote_orphan_cover"])


def resolve_import_cleanup_config(
    preferences: Optional[dict], library_id: int
) -> ImportCleanupConfig:
    """Resolve the effective cleanup config for a library.

    Precedence (lowest → highest): baked-in defaults, the global
    ``import_cleanup`` block, then the per-library override under
    ``import_cleanup_by_library[str(library_id)]``.

    Args:
        preferences: ``UserSettings.preferences`` dict (or None when there is
            no settings row yet — then the baked-in defaults apply).
        library_id: The library whose override should win.

    Returns:
        A fully-populated :class:`ImportCleanupConfig`.
    """
    preferences = preferences if isinstance(preferences, dict) else {}
    resolved = {
        "enabled": DEFAULT_IMPORT_CLEANUP_CONFIG.enabled,
        "sidecar_extensions": sorted(IMPORT_SIDECAR_EXTENSIONS),
        "delete_redundant_images": DEFAULT_IMPORT_CLEANUP_CONFIG.delete_redundant_images,
        "promote_orphan_cover": DEFAULT_IMPORT_CLEANUP_CONFIG.promote_orphan_cover,
    }

    _overlay_config(resolved, preferences.get(PREF_GLOBAL_KEY))
    per_library = preferences.get(PREF_LIBRARY_KEY)
    if not isinstance(per_library, dict):
        per_library = {}
    _overlay_config(resolved, per_library.get(str(library_id)))

    return ImportCleanupConfig(
        enabled=bool(resolved["enabled"]),
        sidecar_extensions=_normalize_extensions(resolved["sidecar_extensions"]),
        delete_redundant_images=bool(resolved["delete_redundant_images"]),
        promote_orphan_cover=bool(resolved["promote_orphan_cover"]),
    )


@dataclass
class CleanupResult:
    """Outcome of a drop-zone cleanup, for activity logging and item purging."""

    files_removed: List[str] = field(default_factory=list)
    """Sidecar and redundant-image files deleted from the drop-zone."""

    folders_pruned: List[str] = field(default_factory=list)
    """Now-empty folders removed (the release folder and empty parents)."""

    images_promoted: List[str] = field(default_factory=list)
    """Loose images moved into the library album folder as the cover."""

    images_kept: List[str] = field(default_factory=list)
    """Images left in place (couldn't promote / nothing else to fall back on)."""

    skipped_reason: Optional[str] = None
    """Set when the whole cleanup was skipped (e.g. unsafe path)."""

    @property
    def changed(self) -> bool:
        return bool(
            self.files_removed
            or self.folders_pruned
            or self.images_promoted
        )

    @property
    def affected_paths(self) -> List[str]:
        """Every path that no longer exists in the drop-zone after cleanup."""
        return list(self.files_removed) + list(self.folders_pruned)


def cleanup_import_drop_zone(
    album_path: str,
    destination_path: str,
    import_root: Optional[str],
    art_filename: str = "albumart",
    delete_sidecars: bool = True,
    sidecar_extensions: Iterable[str] = IMPORT_SIDECAR_EXTENSIONS,
    delete_redundant_images: bool = True,
    promote_orphan_cover: bool = True,
) -> CleanupResult:
    """Clean the drop-zone folder of a just-imported album.

    Args:
        album_path: The release folder in the drop-zone the audio was imported
            *from* (its audio is already gone after a move import).
        destination_path: The album folder in the **library** the audio landed
            in — used to decide whether the album already has a cover.
        import_root: The library's import drop-zone root. Cleanup refuses to
            touch anything outside it; ``None`` skips cleanup entirely.
        art_filename: beets' ``art_filename`` (cover basename). A promoted
            image is written as ``<art_filename>.<ext>``.
        delete_sidecars: When false, sidecars are left in place (images and
            empty-folder pruning still run).
        sidecar_extensions: The extensions deleted as junk sidecars. Defaults
            to :data:`IMPORT_SIDECAR_EXTENSIONS`; a per-library override can
            narrow or widen it.
        delete_redundant_images: When false, loose images are never deleted
            (and never promoted) — they're all kept in place.
        promote_orphan_cover: When the album has no cover and this is true, the
            best loose image is promoted into the library folder as the cover;
            when false, an uncovered album's loose images are simply kept.

    Returns:
        A :class:`CleanupResult` describing what changed. Never raises for the
        expected filesystem errors — they are logged and surfaced via the
        result instead, so an import that already succeeded is never undone.
    """
    result = CleanupResult()

    # --- Safety: only ever operate strictly inside the drop-zone root. --------
    if not import_root:
        result.skipped_reason = "no import root configured"
        return result
    if not album_path or not os.path.isdir(album_path):
        result.skipped_reason = "album folder no longer present"
        return result
    if not _is_within(album_path, import_root) or _same_path(album_path, import_root):
        # Never delete outside the drop-zone, and never the root itself.
        logger.warning(
            "Refusing drop-zone cleanup for path outside import root: %s (root=%s)",
            album_path,
            import_root,
        )
        result.skipped_reason = "album path outside import root"
        return result

    # --- 1. Delete junk sidecars (whitelisted extensions only). ---------------
    top_level = _safe_listdir(album_path)
    allowed_sidecars = _normalize_extensions(sidecar_extensions)
    if delete_sidecars and allowed_sidecars:
        for name in top_level:
            full = os.path.join(album_path, name)
            if os.path.isfile(full) and _ext(name) in allowed_sidecars:
                if _remove_file(full):
                    result.files_removed.append(full)

    # --- 2. Handle loose images (delete only when redundant). -----------------
    images = [
        os.path.join(album_path, name)
        for name in top_level
        if _ext(name) in COVER_IMAGE_EXTENSIONS
        and os.path.isfile(os.path.join(album_path, name))
    ]
    if images:
        _handle_images(
            images,
            destination_path,
            art_filename,
            result,
            delete_redundant_images=delete_redundant_images,
            promote_orphan_cover=promote_orphan_cover,
        )

    # --- 3. Prune the release folder and now-empty parents. -------------------
    result.folders_pruned.extend(prune_empty_drop_zone_folders(album_path, import_root))

    return result


def _handle_images(
    images: List[str],
    destination_path: str,
    art_filename: str,
    result: CleanupResult,
    delete_redundant_images: bool = True,
    promote_orphan_cover: bool = True,
) -> None:
    """Delete redundant images; promote the best one when there's no cover."""
    if not delete_redundant_images:
        # Image cleanup disabled — leave every loose image untouched.
        result.images_kept.extend(images)
        return

    if _album_has_cover(destination_path, art_filename):
        # The imported album already has a cover — every loose image is
        # redundant and safe to delete.
        for img in images:
            if _remove_file(img):
                result.files_removed.append(img)
        return

    if not promote_orphan_cover:
        # No cover and promotion disabled — never drop the only artwork.
        result.images_kept.extend(images)
        return

    # No cover yet. The loose image(s) may be the album's only artwork — promote
    # the best candidate into the library folder, *then* the rest are redundant.
    best = _pick_promotable_image(images)
    promoted = _promote_image(best, destination_path, art_filename) if best else None

    if not promoted:
        # Couldn't promote (no destination, copy failed, …). Keep the artwork
        # rather than silently dropping the only cover.
        result.images_kept.extend(images)
        return

    result.images_promoted.append(promoted)
    for img in images:
        if img == best:
            continue
        if _remove_file(img):
            result.files_removed.append(img)


def prune_empty_drop_zone_folders(
    album_path: str, import_root: Optional[str]
) -> List[str]:
    """Remove ``album_path`` if empty, then walk up removing empty parents.

    Stops at (and never removes) the import root. Mirrors the original
    move-mode cleanup so disabling the feature flag keeps that behaviour.
    """
    pruned: List[str] = []
    if not import_root:
        return pruned

    root = os.path.abspath(import_root.rstrip("/"))

    # Remove the release folder itself if it's now empty.
    try:
        if os.path.isdir(album_path) and not os.listdir(album_path):
            os.rmdir(album_path)
            pruned.append(os.path.abspath(album_path))
            logger.info("Removed empty album folder: %s", album_path)
    except OSError as exc:
        logger.debug("Could not remove album folder %s: %s", album_path, exc)

    # Walk up, removing now-empty parents (e.g. an artist folder whose albums
    # have all been imported out). Stop at — never remove — the import root.
    parent = os.path.dirname(os.path.abspath(album_path))
    while parent and parent != root and parent.startswith(root + os.sep):
        try:
            if not os.listdir(parent):
                os.rmdir(parent)
                pruned.append(parent)
                logger.info("Removed empty parent folder: %s", parent)
                parent = os.path.dirname(parent)
            else:
                break
        except OSError:
            break

    return pruned


# ---------------------------------------------------------------------------
# Cover detection
# ---------------------------------------------------------------------------


def _album_has_cover(destination_path: str, art_filename: str) -> bool:
    """True if the imported album already has a usable cover.

    A cover counts as present when the library album folder holds a cover file
    (a standard ``cover/albumart/folder/front`` name or the configured
    ``art_filename``), or when any of its audio files carries embedded art.

    A non-null beets ``artpath`` would also count, but beet-it imports leave it
    null and any real artpath points at a file in this same folder — which the
    folder check already covers — so it needs no separate lookup here.
    """
    if not destination_path or not os.path.isdir(destination_path):
        return False

    if _folder_cover_file(destination_path, art_filename):
        return True

    for audio in _audio_files_in(destination_path):
        if _file_has_embedded_art(audio):
            return True

    return False


def _folder_cover_file(folder: str, art_filename: str) -> Optional[str]:
    """Return a cover file present in ``folder``, or None.

    Reuses beets-library cover-name discovery (single source of truth for the
    standard names) and additionally honours a custom configured
    ``art_filename``.
    """
    found = BeetsLibraryService().discover_cover_art(folder)
    if found:
        return found

    # Honour a custom art_filename not covered by the standard names.
    art_base = (art_filename or "albumart").lower()
    try:
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            if stem.lower() == art_base and ext.lower() in COVER_IMAGE_EXTENSIONS:
                return os.path.join(folder, name)
    except OSError:
        return None
    return None


def _file_has_embedded_art(path: str) -> bool:
    """True if an audio file carries embedded cover art (mutagen-based)."""
    try:
        import mutagen

        audio = mutagen.File(path)
        if audio is None:
            return False

        # FLAC / others expose .pictures directly.
        if getattr(audio, "pictures", None):
            return True

        tags = getattr(audio, "tags", None)
        if not tags:
            return False

        # MP3 / ID3 — APIC frames.
        getall = getattr(tags, "getall", None)
        if callable(getall):
            try:
                if getall("APIC"):
                    return True
            except Exception:  # noqa: BLE001 - defensive; tag layout varies
                pass

        # MP4 / M4A — 'covr' atom; Vorbis/Opus — base64 picture block.
        try:
            if "covr" in tags or "metadata_block_picture" in tags:
                return True
        except TypeError:
            pass

        return False
    except Exception as exc:  # noqa: BLE001 - never let art detection break cleanup
        logger.debug("Embedded-art check failed for %s: %s", path, exc)
        return False


# ---------------------------------------------------------------------------
# Image promotion
# ---------------------------------------------------------------------------


def _pick_promotable_image(images: List[str]) -> Optional[str]:
    """Choose the most cover-like loose image to promote.

    Prefers a recognised cover filename; otherwise falls back to the largest
    file (scene-named art like ``00-release.jpg`` tends to be the full cover).
    """
    if not images:
        return None

    def rank(path: str):
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        for idx, name in enumerate(_PROMOTE_NAME_PRIORITY):
            if stem == name or stem.startswith(name):
                return (0, idx, -_safe_size(path))
        return (1, 0, -_safe_size(path))

    return sorted(images, key=rank)[0]


def _promote_image(
    image_path: str, destination_path: str, art_filename: str
) -> Optional[str]:
    """Move ``image_path`` into the library album folder as the cover.

    Returns the destination path on success, or None if it couldn't be placed
    (missing destination, name collision, IO error). The source is *moved* so
    it also leaves the drop-zone.
    """
    if not destination_path or not os.path.isdir(destination_path):
        return None
    if not os.path.isfile(image_path):
        return None

    ext = _ext(image_path) or ".jpg"
    base = (art_filename or "albumart")
    dest = os.path.join(destination_path, f"{base}{ext}")
    if os.path.exists(dest):
        # Something is already there; don't clobber it. The album effectively
        # has a cover, so the caller's redundant-delete path is appropriate —
        # signal "kept it where it is" by reporting failure to promote.
        return None

    try:
        shutil.move(image_path, dest)
    except OSError as exc:
        logger.warning(
            "Failed to promote cover %s -> %s: %s", image_path, dest, exc
        )
        return None

    logger.info("Promoted loose import image to album cover: %s", dest)
    return dest


# ---------------------------------------------------------------------------
# Small filesystem helpers
# ---------------------------------------------------------------------------


def _audio_files_in(folder: str) -> List[str]:
    out: List[str] = []
    for name in _safe_listdir(folder):
        full = os.path.join(folder, name)
        if os.path.isfile(full) and _ext(name) in SUPPORTED_EXTENSIONS:
            out.append(full)
    return out


def _safe_listdir(folder: str) -> List[str]:
    try:
        return os.listdir(folder)
    except OSError:
        return []


def _remove_file(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except OSError as exc:
        logger.warning("Could not delete %s: %s", path, exc)
        return False


def _safe_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _is_within(child: str, root: str) -> bool:
    try:
        rc = os.path.realpath(child)
        rr = os.path.realpath(root)
        return rc == rr or rc.startswith(rr + os.sep)
    except (OSError, ValueError):
        return False


def _same_path(a: str, b: str) -> bool:
    try:
        return os.path.realpath(a) == os.path.realpath(b.rstrip("/"))
    except (OSError, ValueError):
        return False
