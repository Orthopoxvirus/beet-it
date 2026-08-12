"""Library Maintenance API — missing cover art + stray (unimported) files.

See issue #147. Endpoints are library-scoped under the same ``/libraries``
prefix as the rest of the library API and reuse its helpers/dependencies.
"""
import logging
import mimetypes
import sqlite3
import subprocess
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.config import get_config_service
from app.api.libraries import get_beets_library_service, get_library_by_slug
from app.database import get_db
from app.schemas.maintenance import (
    BpmBackfillInfoResponse,
    BpmBackfillStartResponse,
    BpmBackfillStatusResponse,
    CoverSearchResponse,
    CoverSearchResult,
    MissingCoverAlbum,
    MissingCoverResponse,
    PluginStatus,
    StrayActionRequest,
    StrayActionResponse,
    StrayActionResult,
    StrayGroup,
    UnimportedResponse,
    UseAsCoverRequest,
    UseAsCoverResponse,
)
from app.config import get_settings
from app.services import cover_search_service, maintenance_service
from app.services.cover_art import get_art_filename
from app.services.redis_keys import get_redis_key_manager
from app.services.beets_config_service import BeetsConfigService
from app.services.beets_library_service import BeetsLibraryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["maintenance"])


@router.get("/{slug}/maintenance/missing-cover", response_model=MissingCoverResponse)
def list_missing_cover(
    slug: str,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """List albums whose cover art is missing on disk."""
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library has no database_path configured")
    try:
        items = maintenance_service.list_albums_missing_cover(
            beets_service, library.database_path, library.library_path
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Library beets database is missing on disk")
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise HTTPException(status_code=500, detail=f"Library beets database error: {e}")
    return MissingCoverResponse(
        items=[MissingCoverAlbum(**item) for item in items], total=len(items)
    )


@router.get(
    "/{slug}/albums/{album_id}/cover/search", response_model=CoverSearchResponse
)
async def search_album_cover(
    slug: str,
    album_id: int,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Search public sources for cover art candidates for an album."""
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library has no database_path configured")
    try:
        album = beets_service.get_album_by_id(
            library.database_path, album_id, library_root=library.library_path
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Library beets database is missing on disk")
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise HTTPException(status_code=500, detail=f"Library beets database error: {e}")
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    # Echo the actual free-text term used against iTunes/Deezer (album only,
    # issue #210), not artist+album.
    query = album.title.strip()
    results = await cover_search_service.search_cover_art(
        album=album.title, mb_albumid=album.mb_albumid
    )
    return CoverSearchResponse(
        query=query, results=[CoverSearchResult(**r) for r in results]
    )


@router.get("/{slug}/maintenance/unimported", response_model=UnimportedResponse)
def list_unimported(
    slug: str,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
    config_service: BeetsConfigService = Depends(get_config_service),
):
    """List stray files beets does not track (requires the unimported plugin)."""
    library = get_library_by_slug(db, slug)
    if not library.database_path or not library.library_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no database_path or library_path configured",
        )
    try:
        data = maintenance_service.get_unimported(beets_service, config_service, library)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Library beets database is missing on disk")
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail=f"Stray scan timed out: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return UnimportedResponse(
        enabled=data["enabled"],
        total_files=data["total_files"],
        groups=[StrayGroup(**g) for g in data["groups"]],
    )


@router.post(
    "/{slug}/maintenance/plugins/{plugin}/enable", response_model=PluginStatus
)
def enable_plugin(
    slug: str,
    plugin: str,
    db: Session = Depends(get_db),
    config_service: BeetsConfigService = Depends(get_config_service),
):
    """Enable a supported beets plugin (allowlisted) for the library."""
    library = get_library_by_slug(db, slug)
    try:
        plugins = maintenance_service.enable_plugin(
            config_service, library.config_path, plugin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write beets config: {e}")
    return PluginStatus(plugin=plugin, enabled=plugin in plugins)


@router.post(
    "/{slug}/maintenance/unimported/action", response_model=StrayActionResponse
)
def act_on_unimported(
    slug: str,
    request: StrayActionRequest,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Delete or move-to-import a set of stray files."""
    library = get_library_by_slug(db, slug)
    if not library.database_path or not library.library_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no database_path or library_path configured",
        )
    try:
        results = maintenance_service.act_on_strays(
            beets_service, library, request.paths, request.action.value
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StrayActionResponse(results=[StrayActionResult(**r) for r in results])


@router.get("/{slug}/maintenance/unimported/preview")
def preview_stray_image(
    slug: str,
    path: str,
    db: Session = Depends(get_db),
):
    """Serve a stray image file so the UI can preview it as a cover candidate.

    Guarded like the stray actions: the path must resolve strictly inside the
    library root and carry valid image magic bytes.
    """
    library = get_library_by_slug(db, slug)
    try:
        real_path = maintenance_service.resolve_stray_image(library, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    media_type, _ = mimetypes.guess_type(real_path)
    return FileResponse(
        path=real_path,
        media_type=media_type or "application/octet-stream",
        # Strays come and go as the user cleans up — don't let the browser
        # pin a stale preview.
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/{slug}/maintenance/unimported/use-as-cover",
    response_model=UseAsCoverResponse,
)
def use_stray_as_cover(
    slug: str,
    request: UseAsCoverRequest,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Promote a stray image to its album's cover art (replacing any current
    cover) and drop the now-redundant source file."""
    library = get_library_by_slug(db, slug)
    if not library.database_path or not library.library_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no database_path or library_path configured",
        )
    try:
        result = maintenance_service.use_stray_as_cover(
            beets_service,
            library,
            request.path,
            art_filename=get_art_filename(library.config_path),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise HTTPException(status_code=500, detail=f"Library beets database error: {e}")

    # Best-effort cache update — the DB artpath is authoritative.
    try:
        redis_manager = get_redis_key_manager(get_settings().redis_url)
        redis_manager.set_discovered_cover_art(
            library.database_path, result["album_id"], result["cover_path"]
        )
    except Exception as e:  # noqa: BLE001 - cache only
        logger.warning("Could not update cover cache after promotion: %s", e)

    return UseAsCoverResponse(status="cover_set", **result)


# --- BPM backfill (autobpm) -------------------------------------------------


@router.get("/{slug}/maintenance/bpm", response_model=BpmBackfillInfoResponse)
def bpm_info(
    slug: str,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """How many tracks still lack a bpm tag, and how long a full backfill
    would run (measured rate of the last finished job, or a default)."""
    from app.tasks.maintenance import bpm_workers, estimate_backfill_seconds

    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library database path not configured")
    missing = beets_service.get_item_ids_missing_bpm(library.database_path)
    redis_manager = get_redis_key_manager(get_settings().redis_url)
    return BpmBackfillInfoResponse(
        missing_count=len(missing),
        estimated_seconds=estimate_backfill_seconds(redis_manager, library.id, len(missing)),
        workers=bpm_workers(),
    )


@router.post(
    "/{slug}/maintenance/bpm/backfill",
    response_model=BpmBackfillStartResponse,
    status_code=202,
)
def start_bpm_backfill(
    slug: str,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Kick off the chained autobpm backfill for all tracks without bpm."""
    from app.tasks.maintenance import bpm_backfill, bpm_workers, estimate_backfill_seconds

    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library database path not configured")

    redis_manager = get_redis_key_manager(get_settings().redis_url)
    current = redis_manager.get_bpm_backfill_status(library.id)
    if current and current.get("status") in ("queued", "running"):
        raise HTTPException(status_code=409, detail="A BPM backfill is already running for this library")

    missing = beets_service.get_item_ids_missing_bpm(library.database_path)
    job_id = str(uuid.uuid4())
    # Reset all per-job state of a previous run (cancel flag, failed-item
    # exclusions, the status hash), then mark queued before dispatch so an
    # immediate status poll never reads the stale old state.
    estimated = estimate_backfill_seconds(redis_manager, library.id, len(missing))
    redis_manager.clear_bpm_backfill_cancel(library.id)
    redis_manager.clear_bpm_failed_items(library.id)
    redis_manager.clear_bpm_attempts(library.id)
    redis_manager.clear_bpm_backfill_status(library.id)
    redis_manager.set_bpm_backfill_status(
        library.id,
        status="queued",
        total=len(missing),
        job_id=job_id,
        eta_seconds=estimated,
        workers=bpm_workers(),
    )
    bpm_backfill.delay(library_id=library.id, job_id=job_id)
    return BpmBackfillStartResponse(job_id=job_id, total=len(missing))


@router.get("/{slug}/maintenance/bpm/backfill/status", response_model=BpmBackfillStatusResponse)
def bpm_backfill_status(slug: str, db: Session = Depends(get_db)):
    """Poll the current/last backfill state (idle when none ran recently)."""
    library = get_library_by_slug(db, slug)
    redis_manager = get_redis_key_manager(get_settings().redis_url)
    status = redis_manager.get_bpm_backfill_status(library.id)
    if not status:
        return BpmBackfillStatusResponse(status="idle")
    return BpmBackfillStatusResponse(**status)


@router.post("/{slug}/maintenance/bpm/backfill/cancel", status_code=202)
def cancel_bpm_backfill(slug: str, db: Session = Depends(get_db)):
    """Request cancellation; the task stops at the next chunk boundary."""
    library = get_library_by_slug(db, slug)
    redis_manager = get_redis_key_manager(get_settings().redis_url)
    current = redis_manager.get_bpm_backfill_status(library.id)
    if not current or current.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="No BPM backfill is currently running")
    redis_manager.request_bpm_backfill_cancel(library.id)
    return {"status": "cancel_requested"}
