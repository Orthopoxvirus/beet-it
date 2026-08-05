"""Library maintenance operations (issue #147).

Two areas:

* **missing cover art** — albums beets tracks that have no usable cover on disk;
* **unimported / stray files** — files inside the beets library directory that
  beets does not track, surfaced via the beets ``unimported`` plugin, with
  move-to-import / delete cleanup actions.

All filesystem mutations are guarded to stay strictly inside the library root
and to never touch a path beets still tracks.
"""
import logging
import os
import shutil
import subprocess
from typing import Optional

from app.services.beets_config_service import BeetsConfigService
from app.services.beets_library_service import BeetsLibraryService

logger = logging.getLogger(__name__)

UNIMPORTED_PLUGIN = "unimported"
# Stray files with these extensions are offered as cover-art candidates.
STRAY_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
# Only plugins we explicitly support may be toggled through the API — this is an
# allowlist so the enable endpoint can't be used to inject arbitrary plugins.
ENABLEABLE_PLUGINS = {UNIMPORTED_PLUGIN}
_UNIMPORTED_TIMEOUT = 180


# ---------------------------------------------------------------------------
# Missing cover art
# ---------------------------------------------------------------------------
def list_albums_missing_cover(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_root: Optional[str],
) -> list[dict]:
    """Return albums whose cover art is missing on disk.

    An album counts as missing when its stored ``artpath`` points at a file
    that no longer exists *and* no cover file can be discovered in its folder
    (the same fallback the cover endpoint serves).
    """
    albums, _ = beets_service.get_albums(
        db_path, skip=0, limit=1_000_000, library_root=library_root
    )
    missing: list[dict] = []
    for album in albums:
        resolved = beets_service._resolve_against_root(
            album.cover_art_path, library_root
        )
        if resolved and os.path.exists(resolved):
            continue
        # No usable stored artpath — fall back to folder discovery before
        # declaring it missing, matching what GET /cover actually serves.
        discovered = beets_service.get_album_cover_path_with_fallback(
            db_path, album.id, library_root=library_root
        )
        if discovered and os.path.exists(discovered):
            continue
        missing.append(
            {"album_id": album.id, "title": album.title, "artist": album.artist}
        )
    return missing


# ---------------------------------------------------------------------------
# Plugin enablement
# ---------------------------------------------------------------------------
def is_plugin_enabled(
    config_service: BeetsConfigService, config_path: Optional[str], plugin: str
) -> bool:
    if not config_path or not os.path.exists(config_path):
        return False
    try:
        cfg = config_service.parse_yaml_config(config_path)
    except Exception as e:  # noqa: BLE001 - a broken config is not "enabled"
        logger.warning("Could not parse beets config %s: %s", config_path, e)
        return False
    return plugin in set(cfg.plugins)


def enable_plugin(
    config_service: BeetsConfigService, config_path: Optional[str], plugin: str
) -> list[str]:
    if plugin not in ENABLEABLE_PLUGINS:
        raise ValueError(f"Plugin '{plugin}' cannot be enabled through this endpoint")
    if not config_path:
        raise ValueError("Library has no beets config path configured")
    cfg = config_service.parse_yaml_config(config_path)
    if plugin not in cfg.plugins:
        cfg.plugins = [*cfg.plugins, plugin]
        config_service.save_config(config_path, cfg)
    return cfg.plugins


# ---------------------------------------------------------------------------
# Unimported (stray) detection
# ---------------------------------------------------------------------------
def _run_unimported(config_path: str) -> list[str]:
    cmd = ["python", "-m", "beets", "-c", config_path, "unimported"]
    logger.info("Running beets unimported: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_UNIMPORTED_TIMEOUT
        )
    except FileNotFoundError as e:
        # A missing interpreter/beets is distinct from a missing beets DB; don't
        # let it surface as the DB-missing message.
        raise RuntimeError(f"beets command not available: {e}")
    if result.returncode != 0:
        raise RuntimeError(
            f"beets unimported failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _active_covers_by_album(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_root: Optional[str],
) -> dict[int, str]:
    """The cover file each album actually serves, resolved on disk.

    Cover art is not a beets *item*, so the ``unimported`` plugin reports
    every cover file as stray — including the one the album grid is showing.
    This map (stored ``artpath`` if it exists, else the same folder-discovery
    fallback GET /cover uses) lets callers exclude the active cover from
    stray listings and protect it from stray-cleanup actions.
    """
    covers: dict[int, str] = {}
    try:
        albums, _ = beets_service.get_albums(
            db_path, skip=0, limit=1_000_000, library_root=library_root
        )
    except Exception as e:  # noqa: BLE001 - never let this break stray listing
        logger.warning("Could not enumerate albums for cover exclusion: %s", e)
        return covers
    for album in albums:
        resolved = beets_service._resolve_against_root(
            album.cover_art_path, library_root
        )
        if resolved and os.path.exists(resolved):
            covers[album.id] = os.path.normpath(resolved)
            continue
        discovered = beets_service.get_album_cover_path_with_fallback(
            db_path, album.id, library_root=library_root
        )
        if discovered:
            covers[album.id] = os.path.normpath(discovered)
    return covers


def _normalize_in_root(path: str, library_root: Optional[str]) -> Optional[str]:
    """Resolve a (possibly relative) path and confirm it is inside the root."""
    norm = os.path.normpath(path)
    if not os.path.isabs(norm) and library_root:
        norm = os.path.normpath(os.path.join(library_root, norm))
    if library_root and not (
        norm == library_root or norm.startswith(library_root + os.sep)
    ):
        return None
    return norm


def get_unimported(
    beets_service: BeetsLibraryService,
    config_service: BeetsConfigService,
    library,
) -> dict:
    """Return stray (unimported) files grouped by folder.

    When the ``unimported`` plugin is not enabled for the library the response
    carries ``enabled=False`` and no groups, so the UI can offer to enable it.
    """
    if not is_plugin_enabled(config_service, library.config_path, UNIMPORTED_PLUGIN):
        return {"enabled": False, "groups": [], "total_files": 0}

    library_root = (
        os.path.normpath(library.library_path).rstrip(os.sep)
        if library.library_path
        else None
    )
    raw_paths = _run_unimported(library.config_path)
    dir_albums = beets_service.get_tracked_dir_albums(
        library.database_path, library_root
    )
    covers_by_album = _active_covers_by_album(
        beets_service, library.database_path, library_root
    )
    active_covers = set(covers_by_album.values())

    groups: dict[str, dict] = {}
    total_files = 0
    for raw in raw_paths:
        path = _normalize_in_root(raw, library_root)
        if not path or not os.path.isfile(path):
            continue
        # An album's active cover is doing its job — it isn't a stray file.
        if path in active_covers:
            continue
        folder = os.path.dirname(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        group = groups.setdefault(
            folder, {"folder": folder, "files": [], "total_size": 0}
        )
        ext = os.path.splitext(path)[1].lower()
        group["files"].append(
            {
                "path": path,
                "name": os.path.basename(path),
                "size": size,
                "is_image": ext in STRAY_IMAGE_EXTS,
            }
        )
        group["total_size"] += size
        total_files += 1

    out_groups = []
    for folder, group in sorted(groups.items()):
        relative_folder = (
            os.path.relpath(folder, library_root) if library_root else folder
        )
        # The album owning this folder (None for untracked or mixed folders)
        # plus its current cover's mtime, so the UI can show the existing art
        # next to stray images and offer use-as-cover.
        album_id = dir_albums.get(folder)
        cover_version: Optional[int] = None
        if album_id is not None:
            cover_path = covers_by_album.get(album_id)
            if cover_path:
                try:
                    cover_version = int(os.path.getmtime(cover_path))
                except OSError:
                    cover_version = None
        out_groups.append(
            {
                "folder": folder,
                "relative_folder": relative_folder,
                "files": group["files"],
                "total_size": group["total_size"],
                "fully_untracked": folder not in dir_albums,
                "album_id": album_id,
                "cover_version": cover_version,
            }
        )
    return {"enabled": True, "groups": out_groups, "total_files": total_files}


# ---------------------------------------------------------------------------
# Stray cleanup actions
# ---------------------------------------------------------------------------
def _prune_empty_parents(start_path: str, library_root: str) -> None:
    """Remove now-empty parent dirs above a removed/moved stray file."""
    root = os.path.normpath(library_root).rstrip(os.sep)
    real_root = os.path.realpath(root)
    try:
        parent = os.path.dirname(start_path)
        while parent and parent != root and parent.startswith(root + os.sep):
            if os.path.islink(parent):
                break
            real_parent = os.path.realpath(parent)
            if real_parent == real_root or not real_parent.startswith(
                real_root + os.sep
            ):
                break
            if os.listdir(parent):
                break
            os.rmdir(parent)
            parent = os.path.dirname(parent)
    except OSError as e:
        logger.warning("Error pruning empty parents above %s: %s", start_path, e)


def act_on_strays(
    beets_service: BeetsLibraryService,
    library,
    paths: list[str],
    action: str,
) -> list[dict]:
    """Delete or move-to-import a set of stray files, with per-path results.

    Two guards protect against data loss: every path must resolve strictly
    inside the library root, and no path that beets still tracks is ever
    touched (it is reported ``skipped`` instead).
    """
    if not library.library_path:
        raise ValueError("Library has no library_path configured")
    library_root = os.path.normpath(library.library_path).rstrip(os.sep)
    real_root = os.path.realpath(library_root)

    import_root: Optional[str] = None
    if action == "move_to_import":
        if not library.import_path:
            raise ValueError(
                "Library has no import_path configured; cannot move to import"
            )
        import_root = os.path.normpath(library.import_path).rstrip(os.sep)

    tracked = beets_service.get_tracked_item_paths(
        library.database_path, library_root
    )
    # Compare on fully symlink-resolved paths: the destructive ops below follow
    # symlinks, so a directory symlink could otherwise alias a tracked file past
    # a string-only guard and have us delete/move beets-owned audio.
    tracked_real = {os.path.realpath(p) for p in tracked}
    # Each album's active cover art is equally off-limits — it isn't a beets
    # item, so the tracked-paths guard alone wouldn't protect it.
    active_covers = set(
        _active_covers_by_album(
            beets_service, library.database_path, library_root
        ).values()
    )
    active_covers_real = {os.path.realpath(p) for p in active_covers}

    results: list[dict] = []
    for raw in paths:
        norm = os.path.normpath(raw)
        if not os.path.isabs(norm):
            norm = os.path.normpath(os.path.join(library_root, norm))
        real_path = os.path.realpath(norm)

        # Guard 1: the resolved target must sit strictly inside the library root.
        if not real_path.startswith(real_root + os.sep):
            results.append(
                {
                    "path": raw,
                    "status": "error",
                    "detail": "Path resolves outside the library root",
                }
            )
            continue
        # Guard 2: never touch a file beets still tracks (checked on the resolved
        # path so a symlinked alias can't slip a tracked file through).
        if real_path in tracked_real or norm in tracked:
            results.append(
                {"path": raw, "status": "skipped", "detail": "Path is tracked by beets"}
            )
            continue
        # Guard 3: never remove the cover an album is actively serving.
        if real_path in active_covers_real or norm in active_covers:
            results.append(
                {
                    "path": raw,
                    "status": "skipped",
                    "detail": "Path is an album's active cover art",
                }
            )
            continue
        if not os.path.isfile(real_path):
            results.append(
                {"path": raw, "status": "skipped", "detail": "File no longer exists"}
            )
            continue

        # Operate on the resolved path so the action targets the real file, not a
        # symlink alias.
        try:
            if action == "delete":
                os.remove(real_path)
                _prune_empty_parents(real_path, library_root)
                results.append({"path": raw, "status": "deleted"})
            else:
                relative = os.path.relpath(real_path, library_root)
                dest = os.path.join(import_root, relative)
                if os.path.exists(dest):
                    results.append(
                        {
                            "path": raw,
                            "status": "skipped",
                            "detail": "Destination already exists in import",
                        }
                    )
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(real_path, dest)
                _prune_empty_parents(real_path, library_root)
                results.append({"path": raw, "status": "moved", "relocated_to": dest})
        except OSError as e:
            logger.error("Stray %s of %s failed: %s", action, real_path, e)
            results.append({"path": raw, "status": "error", "detail": str(e)})
    return results


# ---------------------------------------------------------------------------
# Stray images as cover art
# ---------------------------------------------------------------------------
def resolve_stray_image(library, path: str) -> str:
    """Validate *path* as a servable stray image inside the library root.

    Guards: the library must have a root, the symlink-resolved path must sit
    strictly inside it, the file must exist and carry an image extension and
    image magic bytes. Returns the resolved absolute path.

    Raises ValueError with a human-readable reason otherwise.
    """
    from app.services.cover_download import validate_image_format

    if not library.library_path:
        raise ValueError("Library has no library_path configured")
    library_root = os.path.normpath(library.library_path).rstrip(os.sep)
    real_root = os.path.realpath(library_root)

    norm = os.path.normpath(path)
    if not os.path.isabs(norm):
        norm = os.path.normpath(os.path.join(library_root, norm))
    real_path = os.path.realpath(norm)
    if not real_path.startswith(real_root + os.sep):
        raise ValueError("Path resolves outside the library root")
    if not os.path.isfile(real_path):
        raise ValueError("File does not exist")
    if os.path.splitext(real_path)[1].lower() not in STRAY_IMAGE_EXTS:
        raise ValueError("Not an image file")
    try:
        with open(real_path, "rb") as f:
            head = f.read(16)
    except OSError as e:
        raise ValueError(f"Cannot read file: {e}")
    if not validate_image_format(head):
        raise ValueError("File is not a valid image (JPEG, PNG, GIF, WebP)")
    return real_path


def use_stray_as_cover(
    beets_service: BeetsLibraryService,
    library,
    path: str,
    art_filename: str,
) -> dict:
    """Promote a stray image to the album cover of the folder's album.

    Reads the stray image, writes it as ``<art_filename><ext>`` via the
    shared atomic writer (which also removes other cover variants), points
    the beets ``artpath`` at it, and removes the now-redundant source file.
    The existing cover, if any, is overwritten — that is the point.

    Returns ``{"album_id", "cover_path"}``. Raises ValueError on any guard
    failure (path outside root, not an image, folder not a single tracked
    album, file too large).
    """
    from app.services.cover_download import (
        MAX_COVER_ART_SIZE,
        validate_image_format,
        write_cover_file,
    )

    real_path = resolve_stray_image(library, path)
    library_root = os.path.normpath(library.library_path).rstrip(os.sep)

    folder = os.path.dirname(real_path)
    dir_albums = beets_service.get_tracked_dir_albums(
        library.database_path, library_root
    )
    album_id = dir_albums.get(folder)
    if album_id is None:
        raise ValueError(
            "Folder is not a single tracked album — cannot attach a cover"
        )

    if os.path.getsize(real_path) > MAX_COVER_ART_SIZE:
        raise ValueError("Image too large (max 10 MB)")
    with open(real_path, "rb") as f:
        content = f.read()
    mime_type = validate_image_format(content)
    if not mime_type:
        raise ValueError("File is not a valid image (JPEG, PNG, GIF, WebP)")

    cover_path = write_cover_file(folder, content, mime_type, stem=art_filename)

    # The source is now duplicated as the cover file — drop it (unless the
    # stray already *was* the target name and got overwritten in place).
    if os.path.abspath(real_path) != os.path.abspath(cover_path):
        try:
            os.unlink(real_path)
        except OSError as e:
            logger.warning("Could not remove promoted stray %s: %s", real_path, e)

    beets_service.update_album_artpath(library.database_path, album_id, cover_path)
    logger.info(
        "Promoted stray %s to cover %s for album %s", real_path, cover_path, album_id
    )
    return {"album_id": album_id, "cover_path": cover_path}
