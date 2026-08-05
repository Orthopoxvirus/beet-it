"""API routes for library items batch edit operations."""

import logging
import math
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.library import Library
from app.schemas.library_items import (
    LibraryItemResponse,
    LibraryItemsListResponse,
    LibraryItemsPreviewRequest,
    LibraryItemsPreviewResponse,
    LibraryItemsBatchUpdateRequest,
    LibraryItemsBatchUpdateResponse,
    BatchUpdateStatusResponse,
    AlbumUpdateStatus,
    AlbumSummary,
    LibraryAlbumsResponse,
    FileWritesStatus,
)
from app.schemas.library_tree import LibraryFolderNode, LibraryTreeResponse
from app.schemas.batch_tag import (
    ItemPreview,
    PreviewWarning,
    PreviewError,
    ItemResult,
    ItemError,
)
from app.services.beets_library_service import BeetsLibraryService, LibraryItemData
from app.services.transformations import (
    TransformationEngine,
    RegexPatternError,
    FixedRule as TransformFixedRule,
    RegexRule as TransformRegexRule,
    SequenceRule as TransformSequenceRule,
    ExplicitRule as TransformExplicitRule,
    TagName as TransformTagName,
    SourceField as TransformSourceField,
    relative_source_path,
)
from app.services.tag_writer import get_tag_writer_registry
from app.services.redis_keys import get_redis_key_manager
from app.services.task_events import get_task_event_service
from app.config import get_settings
from app.tasks.beets_tasks import beets_update_albums

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["library-items"])


def get_library_by_slug(db: Session, slug: str) -> Library:
    """Get a library by its slug, raising 404 if not found."""
    library = db.query(Library).filter(Library.slug == slug).first()
    if not library:
        raise HTTPException(
            status_code=404,
            detail="Library not found",
            headers={"X-Error-Code": "LIBRARY_NOT_FOUND"},
        )
    return library


def library_item_to_dict(
    item: LibraryItemData, library_root: Optional[str] = None
) -> Dict[str, Any]:
    """Convert a LibraryItemData to a dictionary for transformation engine.

    The ``path`` key holds the item's folder relative to ``library_root`` (the
    library root directory), without the filename — the ``path`` regex source.
    """
    return {
        "id": item.id,
        "item_type": "track",
        "path": relative_source_path(item.directory, library_root),
        "directory": item.directory,
        "filename": item.filename,
        "album": item.album,
        "album_artist": item.album_artist,
        "artist": item.artist,
        "title": item.title,
        "track_number": str(item.track_number) if item.track_number is not None else None,
        "disc_number": str(item.disc_number) if item.disc_number is not None else None,
        "genre": item.genre,
    }


def convert_api_rule_to_transform_rule(rule):
    """Convert API schema rule to transformation engine rule."""
    if rule.mode == "fixed":
        return TransformFixedRule(
            tag=TransformTagName(rule.tag.value),
            mode="fixed",
            value=rule.value,
        )
    elif rule.mode == "regex":
        return TransformRegexRule(
            tag=TransformTagName(rule.tag.value),
            mode="regex",
            source_field=TransformSourceField(rule.source_field.value),
            pattern=rule.pattern,
            replacement=rule.replacement,
        )
    elif rule.mode == "sequence":
        return TransformSequenceRule(
            tag=TransformTagName.TRACK_NUMBER,
            mode="sequence",
            start=rule.start,
            per_directory=rule.per_directory,
        )
    elif rule.mode == "explicit":
        return TransformExplicitRule(
            tag=TransformTagName(rule.tag.value),
            mode="explicit",
            values=rule.values,
        )
    else:
        raise ValueError(f"Unknown rule mode: {rule.mode}")


@router.get(
    "/libraries/{slug}/library-items",
    response_model=LibraryItemsListResponse,
)
def get_library_items(
    slug: str,
    album: Optional[str] = Query(None, description="Filter by album title"),
    album_id: Optional[List[int]] = Query(
        None,
        description=(
            "Filter by album ID. Repeat to filter by multiple albums "
            "(`?album_id=1&album_id=2`). Preferred over the legacy `album` "
            "name filter."
        ),
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(100, ge=1, le=50000, description="Items per page (max: 50000)"),
    page_size: Optional[int] = Query(None, ge=1, le=50000, description="Alias of per_page (max: 50000)"),
    db: Session = Depends(get_db),
):
    """Query library items (tracks) from the beets database.

    Returns paginated list of tracks, optionally filtered by album.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no database configured",
            headers={"X-Error-Code": "NO_DATABASE"},
        )

    beets_service = BeetsLibraryService()

    # page_size takes precedence when both provided (it's the more explicit alias).
    if page_size is not None:
        per_page = page_size

    try:
        items, total = beets_service.get_library_items(
            db_path=library.database_path,
            album=album,
            album_id=album_id,
            page=page,
            per_page=per_page,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Beets database not found",
            headers={"X-Error-Code": "DATABASE_NOT_FOUND"},
        )
    except Exception as e:
        logger.error(f"Error querying library items: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query library items: {e}",
            headers={"X-Error-Code": "DATABASE_ERROR"},
        )

    # Convert to response models
    response_items = [
        LibraryItemResponse(
            id=item.id,
            path=item.path,
            filename=item.filename,
            directory=item.directory,
            item_type="track",
            album=item.album,
            album_artist=item.album_artist,
            artist=item.artist,
            title=item.title,
            track_number=item.track_number,
            disc_number=item.disc_number,
            genre=item.genre,
            year=item.year,
            format=item.format,
            bitrate=item.bitrate,
            album_id=item.album_id,
        )
        for item in items
    ]

    total_pages = math.ceil(total / per_page) if total > 0 else 0

    return LibraryItemsListResponse(
        items=response_items,
        total=total,
        page=page,
        per_page=per_page,
        page_size=per_page,
        total_pages=total_pages,
        album_filter=album,
    )


@router.get(
    "/libraries/{slug}/library-tree",
    response_model=LibraryTreeResponse,
)
def get_library_tree(slug: str, db: Session = Depends(get_db)):
    """Get a nested folder tree of the library's on-disk layout.

    Derived from the `items.path` column of the beets SQLite DB — the tree
    reflects exactly how beets wrote the music to disk. Used by the
    batch-edit page to let users select a whole folder worth of albums at
    once.

    Empty libraries return a root node with no children and no album_ids.
    """
    library = db.query(Library).filter(Library.slug == slug).first()
    if not library:
        raise HTTPException(
            status_code=404,
            detail="Library not found",
            headers={"X-Error-Code": "LIBRARY_NOT_FOUND"},
        )

    if not library.database_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no database configured",
            headers={"X-Error-Code": "NO_DATABASE"},
        )
    if not library.library_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no library path configured",
            headers={"X-Error-Code": "NO_LIBRARY_PATH"},
        )

    beets_service = BeetsLibraryService()
    try:
        tree = beets_service.get_library_tree(
            db_path=library.database_path,
            library_root=library.library_path,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Beets database not found",
            headers={"X-Error-Code": "DATABASE_NOT_FOUND"},
        )
    except Exception as e:
        logger.error(f"Error building library tree: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build library tree: {e}",
            headers={"X-Error-Code": "DATABASE_ERROR"},
        )

    return LibraryTreeResponse(
        library_path=tree["library_path"],
        root=LibraryFolderNode(**tree["root"]),
    )


@router.get(
    "/libraries/{slug}/library-items/albums",
    response_model=LibraryAlbumsResponse,
)
def get_library_albums_for_picker(
    slug: str,
    db: Session = Depends(get_db),
):
    """Get list of albums for the album picker.

    Returns a list of all albums with their ID, title, artist, and track count.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no database configured",
            headers={"X-Error-Code": "NO_DATABASE"},
        )

    beets_service = BeetsLibraryService()

    try:
        albums = beets_service.get_albums_for_picker(
            db_path=library.database_path,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Beets database not found",
            headers={"X-Error-Code": "DATABASE_NOT_FOUND"},
        )
    except Exception as e:
        logger.error(f"Error querying albums: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query albums: {e}",
            headers={"X-Error-Code": "DATABASE_ERROR"},
        )

    # Convert to response models
    response_albums = [
        AlbumSummary(
            id=album["id"],
            title=album["title"],
            artist=album["artist"],
            track_count=album["track_count"],
        )
        for album in albums
    ]

    return LibraryAlbumsResponse(
        albums=response_albums,
        total=len(response_albums),
    )


@router.post(
    "/libraries/{slug}/library-items/preview",
    response_model=LibraryItemsPreviewResponse,
)
def preview_library_item_transformations(
    slug: str,
    request: LibraryItemsPreviewRequest,
    db: Session = Depends(get_db),
):
    """Preview tag transformations on library items without applying changes.

    Returns computed preview values for each item based on the provided
    transformation rules.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no database configured",
            headers={"X-Error-Code": "NO_DATABASE"},
        )

    # Convert API rules to transformation engine rules
    try:
        transform_rules = [convert_api_rule_to_transform_rule(rule) for rule in request.rules]
    except RegexPatternError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_REGEX"},
        )

    beets_service = BeetsLibraryService()

    # Get items from beets database
    try:
        items = beets_service.get_items_by_ids(
            db_path=library.database_path,
            item_ids=request.item_ids,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Beets database not found",
            headers={"X-Error-Code": "DATABASE_NOT_FOUND"},
        )
    except Exception as e:
        logger.error(f"Error querying library items: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query library items: {e}",
            headers={"X-Error-Code": "DATABASE_ERROR"},
        )

    # Build lookup for found items
    items_by_id = {item.id: item for item in items}
    found_ids = set(items_by_id.keys())
    requested_ids = set(request.item_ids)

    # Track errors for items not found
    errors: List[PreviewError] = []
    for item_id in requested_ids - found_ids:
        errors.append(
            PreviewError(
                item_id=item_id,
                code="ITEM_NOT_FOUND",
                message=f"Library item with ID {item_id} not found",
            )
        )

    # Convert items to dictionaries for transformation engine
    items_data = [library_item_to_dict(item, library.library_path) for item in items]

    # Create transformation engine and compute previews
    try:
        engine = TransformationEngine(transform_rules)
        result = engine.compute_previews(items_data)
    except RegexPatternError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_REGEX"},
        )

    # Convert transformation results to API response format
    previews: List[ItemPreview] = []
    for item_result in result.previews:
        warnings = [
            PreviewWarning(
                tag=w.tag,
                code=w.code,
                message=w.message,
            )
            for w in item_result.warnings
        ]
        previews.append(
            ItemPreview(
                item_id=item_result.item_id,
                changes=item_result.changes,
                warnings=warnings,
            )
        )

    # Add transformation errors to errors list
    for error in result.errors:
        errors.append(
            PreviewError(
                item_id=error.item_id,
                code=error.code,
                message=error.message,
            )
        )

    return LibraryItemsPreviewResponse(
        previews=previews,
        errors=errors,
    )


@router.post(
    "/libraries/{slug}/library-items/batch-update",
    response_model=LibraryItemsBatchUpdateResponse,
)
async def batch_update_library_items(
    slug: str,
    request: LibraryItemsBatchUpdateRequest,
    db: Session = Depends(get_db),
):
    """Apply tag changes to library items and trigger beets database sync.

    This endpoint:
    1. Captures original album tags for affected items
    2. Writes tag changes to audio files
    3. Enqueues Celery tasks to run `beet update -a '<album>'` for each affected album
    4. Returns a job ID for tracking sync status
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no database configured",
            headers={"X-Error-Code": "NO_DATABASE"},
        )

    # Convert API rules to transformation engine rules
    try:
        transform_rules = [convert_api_rule_to_transform_rule(rule) for rule in request.rules]
    except RegexPatternError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_REGEX"},
        )

    beets_service = BeetsLibraryService()
    redis_manager = get_redis_key_manager(settings.redis_url)
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)

    # Step 1: Get items from beets database
    try:
        items = beets_service.get_items_by_ids(
            db_path=library.database_path,
            item_ids=request.item_ids,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Beets database not found",
            headers={"X-Error-Code": "DATABASE_NOT_FOUND"},
        )
    except Exception as e:
        logger.error(f"Error querying library items: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query library items: {e}",
            headers={"X-Error-Code": "DATABASE_ERROR"},
        )

    # Build lookup for found items
    items_by_id = {item.id: item for item in items}

    # Step 2: Capture original album tags BEFORE any changes
    original_albums = {item.id: item.album for item in items}
    unique_albums = set(original_albums.values())

    # Convert items to dictionaries for transformation engine
    items_data = [library_item_to_dict(item, library.library_path) for item in items]

    # Create transformation engine and compute changes
    try:
        engine = TransformationEngine(transform_rules)
        transform_result = engine.compute_previews(items_data)
    except RegexPatternError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_REGEX"},
        )

    # Build changes map by item_id
    changes_by_id: Dict[int, Dict[str, str]] = {}
    for preview in transform_result.previews:
        if preview.changes:
            changes_by_id[preview.item_id] = preview.changes

    # Step 3: Write tags to files
    started_at = datetime.utcnow()
    tag_writer = get_tag_writer_registry()
    results: List[ItemResult] = []
    items_succeeded = 0
    items_failed = 0

    # The lscr.io/linuxserver/beets image stores item paths relative to the
    # library `directory:`. Resolve to absolute before
    # handing them to the tag writer — `write_tags` opens the path with
    # mediafile, which would otherwise look in the backend container's CWD
    # and fail with "no such file" for every item. Standard beets installs
    # store absolute paths and pass through unchanged.
    library_root = (library.library_path or "").rstrip("/")

    def _resolve_path(stored: str) -> str:
        if not stored:
            return stored
        if os.path.isabs(stored):
            return stored
        if not library_root:
            return stored
        return os.path.join(library_root, stored)

    for item_id in request.item_ids:
        item = items_by_id.get(item_id)
        changes = changes_by_id.get(item_id, {})

        if not item:
            # Item not found
            items_failed += 1
            results.append(
                ItemResult(
                    item_id=item_id,
                    status="failed",
                    error=ItemError(
                        code="ITEM_NOT_FOUND",
                        message=f"Library item with ID {item_id} not found",
                    ),
                )
            )
            continue

        if not changes:
            # No changes for this item
            items_succeeded += 1
            results.append(
                ItemResult(
                    item_id=item_id,
                    status="success",
                    changes_applied={},
                )
            )
            continue

        # Write tags to file
        absolute_path = _resolve_path(item.path)
        write_result = tag_writer.write_tags(absolute_path, changes)

        if write_result.success:
            items_succeeded += 1
            results.append(
                ItemResult(
                    item_id=item_id,
                    status="success",
                    changes_applied=write_result.tags_written,
                )
            )
        else:
            items_failed += 1
            results.append(
                ItemResult(
                    item_id=item_id,
                    status="failed",
                    error=ItemError(
                        code=write_result.error_code or "WRITE_ERROR",
                        message=write_result.error or "Unknown error",
                        file_path=absolute_path,
                    ),
                )
            )

    # Step 3b: Force-clear DB columns for fields the user explicitly emptied.
    #
    # `beet update -a 'album'` only PUSHES file tags into the DB — it does
    # NOT clear DB fields when a tag is missing from the file. So when the
    # user clears a tag (file atom gets deleted by the tag writer), the
    # subsequent `beet update` reads the file, sees no tag, and leaves the
    # old DB value in place. Without this step, an "empty fixed value" rule
    # (the canonical "clear this tag" UX) silently no-ops at the DB layer
    # even though the preview correctly showed `old → (empty)`.
    #
    # We close the gap by writing empty directly into the items table for
    # exactly the rows that succeeded above, scoped to a whitelist of
    # canonical-tag → DB-column pairs.
    _ITEM_COLUMN_BY_CANONICAL: Dict[str, str] = {
        "artist": "artist",
        "album_artist": "albumartist",
        "album": "album",
        "title": "title",
        "genre": "genres",
    }
    succeeded_ids = {r.item_id for r in results if r.status == "success"}
    clears_by_column: Dict[str, List[int]] = {}
    for item_id in succeeded_ids:
        for canonical_tag, value in changes_by_id.get(item_id, {}).items():
            if value != "":
                continue
            column = _ITEM_COLUMN_BY_CANONICAL.get(canonical_tag)
            if column is None:
                continue
            clears_by_column.setdefault(column, []).append(item_id)

    if clears_by_column:
        try:
            connection = sqlite3.connect(library.database_path)
            try:
                for column, ids in clears_by_column.items():
                    placeholders = ",".join("?" * len(ids))
                    # column is from the hardcoded whitelist above; ids are
                    # ints from the items_by_id lookup — both safe to format.
                    connection.execute(
                        f"UPDATE items SET {column} = '' WHERE id IN ({placeholders})",
                        ids,
                    )
                connection.commit()
            finally:
                connection.close()
            logger.info(
                f"Cleared DB columns directly for {len(clears_by_column)} "
                f"field(s): {sorted(clears_by_column.keys())}"
            )
        except Exception as clear_error:
            logger.error(
                f"Failed to clear DB columns after batch update: {clear_error}"
            )

    completed_at = datetime.utcnow()
    duration = int((completed_at - started_at).total_seconds())

    # Step 4: Generate job ID and enqueue beets update tasks
    job_id = str(uuid.uuid4())

    # Only enqueue beets update if we had any successful writes
    albums_to_sync = list(unique_albums) if items_succeeded > 0 else []

    if albums_to_sync:
        # Record activity for the batch update sync
        activity_event_id = task_event_service.record_start(
            task_type="batch_edit_sync",
            library_id=library.id,
            library_slug=library.slug,
            description=f"Syncing {len(albums_to_sync)} album(s) to beets database",
            metadata={
                "job_id": job_id,
                "albums": albums_to_sync,
                "items_updated": items_succeeded,
            },
        )

        # Initialize job status in Redis with file_writes data
        redis_manager.set_batch_update_status(
            job_id=job_id,
            library_id=library.id,
            status="pending",
            albums=albums_to_sync,
            started_at=datetime.utcnow(),
            file_writes={
                "total": len(request.item_ids),
                "succeeded": items_succeeded,
                "failed": items_failed,
            },
        )

        # Enqueue Celery task for beets update
        beets_update_albums.delay(
            job_id=job_id,
            library_id=library.id,
            albums=albums_to_sync,
            config_path=library.config_path,
            activity_event_id=activity_event_id,
        )

    # Determine overall status
    if items_failed == 0:
        status = "pending_sync" if albums_to_sync else "completed"
    elif items_succeeded == 0:
        status = "completed"  # All failed, nothing to sync
    else:
        status = "partial"

    return LibraryItemsBatchUpdateResponse(
        status=status,
        job_id=job_id,
        items_total=len(request.item_ids),
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        results=results,
        albums_to_sync=albums_to_sync,
    )


@router.get(
    "/libraries/{slug}/batch-update-status/{job_id}",
    response_model=BatchUpdateStatusResponse,
)
def get_batch_update_status(
    slug: str,
    job_id: str,
    db: Session = Depends(get_db),
):
    """Check the status of a batch update job.

    Returns the status of beets database synchronization for each album.
    """
    library = get_library_by_slug(db, slug)
    redis_manager = get_redis_key_manager(settings.redis_url)

    status_data = redis_manager.get_batch_update_status(job_id)

    if status_data is None:
        raise HTTPException(
            status_code=404,
            detail="Batch update job not found",
            headers={"X-Error-Code": "JOB_NOT_FOUND"},
        )

    # Verify job belongs to this library
    if status_data.get("library_id") != library.id:
        raise HTTPException(
            status_code=404,
            detail="Batch update job not found",
            headers={"X-Error-Code": "JOB_NOT_FOUND"},
        )

    # Build album status list (now called beets_updates in response)
    beets_updates = []
    for album_data in status_data.get("albums", []):
        beets_updates.append(
            AlbumUpdateStatus(
                album=album_data.get("album", ""),
                status=album_data.get("status", "pending"),
                error=album_data.get("error"),
            )
        )

    # Build file_writes status if available
    file_writes = None
    file_writes_data = status_data.get("file_writes")
    if file_writes_data:
        file_writes = FileWritesStatus(
            total=file_writes_data.get("total", 0),
            succeeded=file_writes_data.get("succeeded", 0),
            failed=file_writes_data.get("failed", 0),
        )

    return BatchUpdateStatusResponse(
        job_id=job_id,
        status=status_data.get("status", "pending"),
        started_at=status_data.get("started_at"),
        completed_at=status_data.get("completed_at"),
        file_writes=file_writes,
        beets_updates=beets_updates,
        error=status_data.get("error"),
    )
