"""API routes for import folder scanning operations."""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.library import Library
from app.models.import_scan import ImportScan
from app.models.import_item import ImportItem
from app.services.scanner.scanner_service import AUDIO_EXTENSIONS
from app.schemas.scan import (
    ScanStatusResponse,
    ScanTriggerResponse,
    ScanHistoryResponse,
    ScanHistoryItem,
    ScanInfo,
    ImportItemListResponse,
    ImportFolderDeleteResponse,
    ImportItem as ImportItemSchema,
    ScanStatus,
    OperationType,
    ImportItemType,
    ImportItemStatus,
    ItemTypeFilter,
    ItemStatusFilter,
)
from app.services.redis_keys import get_redis_key_manager
from app.tasks.scan_tasks import execute_scan
from app.api.libraries import (
    AUDIO_MIME_TYPES,
    iter_file,
    parse_range_header,
    validate_path_in_library,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["scan"])


def get_library_by_slug(db: Session, slug: str) -> Library:
    """Get a library by its slug, raising 404 if not found."""
    library = db.query(Library).filter(Library.slug == slug).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    return library


def get_redis_manager():
    """Get a Redis key manager instance."""
    return get_redis_key_manager(settings.redis_url)


@router.get("/libraries/{slug}/scan/status", response_model=ScanStatusResponse)
def get_scan_status(slug: str, db: Session = Depends(get_db)):
    """Get the current scan status for a library.

    Returns information about:
    - Current running scan (if any)
    - Number of queued scans
    - Blocking operations
    - Watcher status
    - Last completed scan
    """
    library = get_library_by_slug(db, slug)
    redis_manager = get_redis_manager()

    # Get current scan progress from Redis
    progress = redis_manager.get_scan_progress(library.id)

    current_scan = None
    if progress:
        # Get scan from database
        scan = db.query(ImportScan).filter(ImportScan.id == progress["scan_id"]).first()
        if scan and scan.status in ("scanning", "extracting_metadata", "queued"):
            progress_percent = None
            if progress["items_total"] > 0:
                progress_percent = round(
                    progress["items_processed"] / progress["items_total"] * 100, 1
                )

            current_scan = ScanInfo(
                id=scan.id,
                status=ScanStatus(progress["status"]),
                started_at=scan.started_at,
                completed_at=scan.completed_at,
                items_total=progress["items_total"],
                items_processed=progress["items_processed"],
                progress_percent=progress_percent,
                current_file=progress.get("current_file"),
                error_message=scan.error_message,
            )

    # Get queued scans count
    queued_scans = redis_manager.get_scan_queue_length(library.id)

    # Get blocking operations
    blocking_ops = redis_manager.get_active_operations(library.id)
    blocking_operations = [
        OperationType(op) for op in blocking_ops if op in OperationType.__members__.values()
    ]

    # Check if watcher is active
    watcher_state = redis_manager.get_watcher_state(library.id)
    watcher_active = watcher_state.get("active", False) if watcher_state else False

    # Get last completed scan
    last_scan = (
        db.query(ImportScan)
        .filter(
            ImportScan.library_id == library.id,
            ImportScan.status == "completed",
        )
        .order_by(ImportScan.completed_at.desc())
        .first()
    )

    last_completed_scan = None
    if last_scan:
        last_completed_scan = ScanInfo(
            id=last_scan.id,
            status=ScanStatus.COMPLETED,
            started_at=last_scan.started_at,
            completed_at=last_scan.completed_at,
            items_total=last_scan.items_total or 0,
            items_processed=last_scan.items_processed or 0,
            error_message=last_scan.error_message,
        )

    return ScanStatusResponse(
        library_slug=library.slug,
        current_scan=current_scan,
        queued_scans=queued_scans,
        blocking_operations=blocking_operations,
        watcher_active=watcher_active,
        last_completed_scan=last_completed_scan,
    )


@router.get("/libraries/{slug}/scan/progress")
async def get_scan_progress_sse(slug: str, db: Session = Depends(get_db)):
    """Server-Sent Events endpoint for real-time scan progress updates.

    This endpoint streams scan progress events including:
    - scan_started: When a scan begins
    - scan_progress: Periodic progress updates
    - scan_completed: When a scan finishes successfully
    - scan_failed: When a scan fails
    - scan_queued: When a scan is queued
    - scan_blocked: When a scan is blocked by operations
    - heartbeat: Keep-alive every 30 seconds
    """
    library = get_library_by_slug(db, slug)
    library_id, library_slug = library.id, library.slug
    # SSE connections stay open indefinitely, but the request-scoped session
    # is only released when the response finishes — release it now so every
    # open stream doesn't pin a pool connection "idle in transaction".
    db.close()
    redis_manager = get_redis_manager()

    async def event_generator():
        """Generate SSE events from Redis pub/sub."""
        pubsub = redis_manager.subscribe_scan_events(library_id)
        last_heartbeat = datetime.now(timezone.utc)

        try:
            # Send initial state only if a scan is actually running
            progress = redis_manager.get_scan_progress(library_id)
            if progress and progress.get("status") in ("scanning", "extracting_metadata"):
                initial_event = {
                    "scan_id": progress["scan_id"],
                    "status": progress["status"],
                    "items_total": progress["items_total"],
                    "items_processed": progress["items_processed"],
                    "progress_percent": round(
                        progress["items_processed"] / progress["items_total"] * 100, 1
                    )
                    if progress["items_total"] > 0
                    else 0,
                    "current_file": progress.get("current_file"),
                }
                yield f"event: scan_progress\ndata: {json.dumps(initial_event)}\n\n"

            while True:
                # Non-blocking check — avoid blocking the async event loop
                message = pubsub.get_message()

                if message and message["type"] == "message":
                    try:
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        event_data = json.loads(data)

                        event_type = event_data.get("event", "message")
                        event_payload = event_data.get("data", event_data)

                        yield f"event: {event_type}\ndata: {json.dumps(event_payload)}\n\n"
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Error processing SSE message: {e}")

                # Send heartbeat every 30 seconds
                now = datetime.now(timezone.utc)
                if (now - last_heartbeat).total_seconds() >= 30:
                    heartbeat_data = {"timestamp": now.isoformat()}
                    yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"
                    last_heartbeat = now

                # Small delay to prevent tight loop
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.debug(f"SSE connection closed for library {library_slug}")
        finally:
            pubsub.unsubscribe()
            pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/libraries/{slug}/scan", response_model=ScanTriggerResponse, status_code=202)
def trigger_manual_scan(slug: str, db: Session = Depends(get_db)):
    """Manually trigger a scan of the library's import folder.

    The scan will be queued if:
    - Another scan is currently running
    - Blocking operations (import, tag_modify, etc.) are in progress

    Returns 202 Accepted with status information.
    """
    library = get_library_by_slug(db, slug)
    redis_manager = get_redis_manager()

    # Check if import path is configured
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no import path configured",
        )

    # Check if a scan is already queued
    queued_count = redis_manager.get_scan_queue_length(library.id)
    progress = redis_manager.get_scan_progress(library.id)

    if queued_count > 0:
        raise HTTPException(
            status_code=409,
            detail="A scan is already queued for this library",
        )

    # Check for blocking operations
    blocking_ops = redis_manager.get_active_operations(library.id)

    # Check if a scan is already running
    if progress and progress.get("status") in ("scanning", "extracting_metadata"):
        # Queue the scan
        queue_position = redis_manager.enqueue_scan(library.id, "manual")
        return ScanTriggerResponse(
            status="queued",
            scan_id=None,
            message=f"Scan queued for library '{library.slug}'. Position in queue: {queue_position}",
            queue_position=queue_position,
            blocking_operations=[],
        )

    if blocking_ops:
        # Queue the scan (blocked by operations)
        queue_position = redis_manager.enqueue_scan(library.id, "manual")
        return ScanTriggerResponse(
            status="blocked",
            scan_id=None,
            message="Scan queued but blocked by running operations",
            queue_position=queue_position,
            blocking_operations=[
                OperationType(op) for op in blocking_ops if op in OperationType.__members__.values()
            ],
        )

    # Start the scan immediately
    execute_scan.delay(library.id, "manual")

    # Get the scan ID from the most recent scan record
    # Note: The scan ID won't be immediately available since it's created async
    return ScanTriggerResponse(
        status="started",
        scan_id=None,  # Scan ID will be available via SSE/status endpoint
        message=f"Scan started for library '{library.slug}'",
        queue_position=None,
        blocking_operations=[],
    )


@router.get("/libraries/{slug}/scan/history", response_model=ScanHistoryResponse)
def get_scan_history(
    slug: str,
    skip: int = Query(0, ge=0, description="Number of records to skip (offset)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return (max: 100)"),
    db: Session = Depends(get_db),
):
    """Get scan history for a library.

    Returns a paginated list of past scans, ordered by most recent first.
    """
    library = get_library_by_slug(db, slug)

    # Get total count
    total = db.query(ImportScan).filter(ImportScan.library_id == library.id).count()

    # Get scans with pagination
    scans = (
        db.query(ImportScan)
        .filter(ImportScan.library_id == library.id)
        .order_by(ImportScan.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        ScanHistoryItem(
            id=scan.id,
            status=ScanStatus(scan.status),
            started_at=scan.started_at,
            completed_at=scan.completed_at,
            items_total=scan.items_total or 0,
            items_processed=scan.items_processed or 0,
            error_message=scan.error_message,
        )
        for scan in scans
    ]

    return ScanHistoryResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/libraries/{slug}/import-items", response_model=ImportItemListResponse)
def list_import_items(
    slug: str,
    skip: int = Query(0, ge=0, description="Number of records to skip (offset)"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return (max: 500)"),
    item_type: Optional[ItemTypeFilter] = Query(None, description="Filter by type: file or folder"),
    status: Optional[ItemStatusFilter] = Query(None, description="Filter by status"),
    directory: Optional[str] = Query(None, description="Filter by parent directory path"),
    path_prefix: Optional[str] = Query(
        None,
        description="Filter items where path starts with this prefix (enables recursive folder content fetching)",
    ),
    search: Optional[str] = Query(None, description="Search in filename, album, artist, or title"),
    audio_only: bool = Query(
        True,
        description="When true (default), exclude non-audio sidecar files "
        "(cover art, .m3u, .sfv, .nfo, …); folders are always kept.",
    ),
    db: Session = Depends(get_db),
):
    """List import items discovered during the most recent completed scan.

    Supports filtering by item type, status, directory, path_prefix, search, and
    audio_only. With audio_only (the default) only audio files and folders are
    returned, so sidecar/metadata files never surface as importable tracks.
    """
    library = get_library_by_slug(db, slug)

    # Get the most recent completed scan
    last_scan = (
        db.query(ImportScan)
        .filter(
            ImportScan.library_id == library.id,
            ImportScan.status == "completed",
        )
        .order_by(ImportScan.completed_at.desc())
        .first()
    )

    if not last_scan:
        return ImportItemListResponse(
            items=[],
            total=0,
            skip=skip,
            limit=limit,
            scan_id=None,
            scan_completed_at=None,
        )

    # Build query
    query = db.query(ImportItem).filter(ImportItem.scan_id == last_scan.id)

    # Apply filters
    if item_type:
        query = query.filter(ImportItem.item_type == item_type.value)

    if status:
        query = query.filter(ImportItem.status == status.value)
    else:
        # By default, hide items the last scan marked "deleted": those files
        # no longer exist on disk, so surfacing them as present tracks is
        # wrong (issue #125 — a deleted WAV still sharing a folder with its
        # FLAC was counted as a removable duplicate, but the dedup endpoint
        # checks the live disk and 400s). An explicit ?status=deleted still
        # returns them for callers that want the deletion history.
        query = query.filter(ImportItem.status != ImportItemStatus.DELETED.value)

    if directory:
        query = query.filter(ImportItem.directory == directory)

    if path_prefix:
        # Normalize path_prefix by removing trailing slash for consistent matching
        normalized_prefix = path_prefix.rstrip("/")
        # Convert relative path to absolute by prepending library's import_path
        absolute_prefix = f"{library.import_path.rstrip('/')}/{normalized_prefix}"
        query = query.filter(ImportItem.path.startswith(absolute_prefix))

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (ImportItem.filename.ilike(search_pattern))
            | (ImportItem.album.ilike(search_pattern))
            | (ImportItem.artist.ilike(search_pattern))
            | (ImportItem.title.ilike(search_pattern))
        )

    if audio_only:
        # Keep folders; for files require an audio extension. The scanner records
        # every file (incl. cover art / playlists / checksums), but the Prepare
        # view must only ever treat audio files as tracks. Done in SQL so the
        # total/pagination stay correct. Filtering by filename keeps this working
        # for libraries scanned before this change, with no migration needed.
        audio_clauses = [
            func.lower(ImportItem.filename).like(f"%{ext}") for ext in sorted(AUDIO_EXTENSIONS)
        ]
        query = query.filter(
            or_(ImportItem.item_type != "file", or_(*audio_clauses))
        )

    # Get total count
    total = query.count()

    # Get items with pagination
    items_db = query.offset(skip).limit(limit).all()

    items = [
        ImportItemSchema(
            id=item.id,
            item_type=ImportItemType(item.item_type),
            path=item.path,
            directory=item.directory,
            filename=item.filename,
            album=item.album,
            album_artist=item.album_artist,
            artist=item.artist,
            title=item.title,
            track_number=item.track_number,
            track_total=item.track_total,
            genre=item.genre,
            format=item.format,
            bitrate=item.bitrate,
            status=ImportItemStatus(item.status),
            first_seen_at=item.first_seen_at,
            last_seen_at=item.last_seen_at,
        )
        for item in items_db
    ]

    return ImportItemListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        scan_id=last_scan.id,
        scan_completed_at=last_scan.completed_at,
    )


@router.get("/libraries/{slug}/import-items/{item_id}/audio")
def stream_import_item_audio(
    slug: str,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Stream the audio file for a discovered import item.

    Supports HTTP Range requests so the browser's <audio> element can seek.
    The file is read straight from the import folder on disk; the item only
    carries metadata, so the audio is served from ``ImportItem.path``.

    Security:
    - The item must belong to this library.
    - The resolved path must stay within the library's ``import_path``
      (path-traversal / symlink-escape guard).
    """
    library = get_library_by_slug(db, slug)

    if not library.import_path:
        raise HTTPException(status_code=404, detail="Audio file not available")

    item = (
        db.query(ImportItem)
        .filter(ImportItem.id == item_id, ImportItem.library_id == library.id)
        .first()
    )
    if item is None or item.item_type != "file":
        raise HTTPException(status_code=404, detail="Import item not found")

    absolute_path = item.path or ""
    if not absolute_path or not os.path.exists(absolute_path):
        raise HTTPException(status_code=404, detail="Audio file not available")

    # Path-traversal guard: the file must live inside the import folder.
    if not validate_path_in_library(absolute_path, library.import_path):
        logger.warning(f"Path traversal attempt on import audio: {absolute_path}")
        raise HTTPException(status_code=404, detail="Audio file not available")

    # Streaming outlives this handler; release the DB connection now so it
    # doesn't sit "idle in transaction" for the whole playback.
    db.close()

    file_size = os.path.getsize(absolute_path)
    _, ext = os.path.splitext(absolute_path.lower())
    media_type = AUDIO_MIME_TYPES.get(ext, "application/octet-stream")

    range_header = request.headers.get("range")
    range_spec = parse_range_header(range_header, file_size) if range_header else None

    if range_spec:
        start, end = range_spec
        content_length = end - start + 1
        headers = {
            "Content-Type": media_type,
            "Content-Length": str(content_length),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        }
        return StreamingResponse(
            iter_file(absolute_path, start, end),
            status_code=206,
            headers=headers,
            media_type=media_type,
        )

    headers = {
        "Content-Type": media_type,
        "Content-Length": str(file_size),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }
    return StreamingResponse(
        iter_file(absolute_path),
        status_code=200,
        headers=headers,
        media_type=media_type,
    )


@router.delete(
    "/libraries/{slug}/import-folder",
    response_model=ImportFolderDeleteResponse,
)
def delete_import_folder(
    slug: str,
    path: str = Query(..., description="Folder path relative to the library import root"),
    db: Session = Depends(get_db),
):
    """Delete a folder from the library's import area.

    Removes the folder (recursively) from disk **and** purges every matching
    ``ImportItem`` row so the folder disappears from beet-it entirely. The
    import-tree cache is invalidated afterwards.

    Security:
    - ``path`` is interpreted relative to the library's ``import_path``; the
      resolved absolute path must stay inside it (path-traversal guard).
    - The operation is refused while a scan is in progress for this library,
      since the scan would be reading the same tree.
    """
    library = get_library_by_slug(db, slug)

    if not library.import_path:
        raise HTTPException(status_code=404, detail="Library has no import path configured")

    # Reject empty / root-targeting paths outright — deleting the import root
    # itself is never the intent and would wipe the whole import area.
    normalized_rel = path.strip().strip("/")
    if not normalized_rel:
        raise HTTPException(status_code=400, detail="A folder path is required")

    import_root = library.import_path.rstrip("/")
    absolute_path = os.path.normpath(os.path.join(import_root, normalized_rel))

    # Path-traversal guard: the target must be strictly inside the import root.
    if not validate_path_in_library(absolute_path, import_root) or os.path.realpath(
        absolute_path
    ) == os.path.realpath(import_root):
        logger.warning(f"Rejected import-folder delete outside root: {absolute_path}")
        raise HTTPException(status_code=400, detail="Invalid folder path")

    if not os.path.isdir(absolute_path):
        raise HTTPException(status_code=404, detail="Folder not found")

    # Refuse while a scan is running — it walks the same tree.
    redis_manager = get_redis_manager()
    progress = redis_manager.get_scan_progress(library.id)
    if progress:
        scan = db.query(ImportScan).filter(ImportScan.id == progress["scan_id"]).first()
        if scan and scan.status in ("scanning", "extracting_metadata", "queued"):
            raise HTTPException(
                status_code=409,
                detail="A scan is currently running; try again once it finishes",
            )

    # Remove from disk first; if this fails we leave the DB untouched.
    try:
        shutil.rmtree(absolute_path)
    except OSError as e:
        logger.error(f"Failed to delete import folder {absolute_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Unable to delete folder: {str(e)}")

    # Purge matching import items: the folder itself plus everything under it.
    prefix = absolute_path.rstrip("/") + os.sep
    items_removed = (
        db.query(ImportItem)
        .filter(
            ImportItem.library_id == library.id,
            or_(
                ImportItem.path == absolute_path,
                ImportItem.path.startswith(prefix),
            ),
        )
        .delete(synchronize_session=False)
    )
    db.commit()

    # Invalidate the cached folder tree so the UI reflects the deletion.
    redis_manager.invalidate_import_tree_cache(library.id)

    return ImportFolderDeleteResponse(
        status="deleted",
        path=normalized_rel,
        items_removed=items_removed,
    )
