"""API routes for batch tag editor operations."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.library import Library
from app.models.import_scan import ImportScan
from app.models.import_item import ImportItem
from app.schemas.batch_tag import (
    BatchPreviewRequest,
    BatchPreviewResponse,
    BatchUpdateRequest,
    BatchUpdateResponse,
    ItemPreview,
    PreviewWarning,
    PreviewError,
    ItemResult,
    ItemError,
    SSEBatchStarted,
    SSEItemProgress,
    SSEBatchCompleted,
    SSEBatchFailed,
)
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batch-tag"])


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


def item_to_dict(item: ImportItem, import_path: Optional[str] = None) -> Dict[str, Any]:
    """Convert an ImportItem model to a dictionary for transformation engine.

    The ``path`` key holds the item's folder relative to ``import_path`` (the
    library import directory), without the filename — the ``path`` regex source.
    """
    return {
        "id": item.id,
        "item_type": item.item_type,
        "path": relative_source_path(item.directory, import_path),
        "directory": item.directory,
        "filename": item.filename,
        "album": item.album,
        "album_artist": item.album_artist,
        "artist": item.artist,
        "title": item.title,
        "track_number": str(item.track_number) if item.track_number is not None else None,
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


@router.post(
    "/libraries/{slug}/import-items/preview",
    response_model=BatchPreviewResponse,
)
def preview_tag_transformations(
    slug: str,
    request: BatchPreviewRequest,
    db: Session = Depends(get_db),
):
    """Preview tag transformations without persisting changes.

    Returns computed preview values for each item based on the provided
    transformation rules.
    """
    library = get_library_by_slug(db, slug)

    # Convert API rules to transformation engine rules
    try:
        transform_rules = [convert_api_rule_to_transform_rule(rule) for rule in request.rules]
    except RegexPatternError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_REGEX"},
        )

    # Get items from database
    items_db = (
        db.query(ImportItem)
        .filter(
            ImportItem.library_id == library.id,
            ImportItem.id.in_(request.item_ids),
        )
        .all()
    )

    # Build lookup for found items
    items_by_id = {item.id: item for item in items_db}
    found_ids = set(items_by_id.keys())
    requested_ids = set(request.item_ids)

    # Track errors for items not found
    errors: List[PreviewError] = []
    for item_id in requested_ids - found_ids:
        errors.append(
            PreviewError(
                item_id=item_id,
                code="ITEM_NOT_FOUND",
                message=f"Import item with ID {item_id} not found",
            )
        )

    # Convert items to dictionaries for transformation engine
    items_data = [item_to_dict(item, library.import_path) for item in items_db]

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

    return BatchPreviewResponse(
        previews=previews,
        errors=errors,
    )


@router.post(
    "/libraries/{slug}/import-items/batch-update",
    response_model=BatchUpdateResponse,
)
async def batch_update_tags(
    slug: str,
    request: BatchUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Apply tag changes to items and write to audio files.

    If the client requests SSE (Accept: text/event-stream), returns a stream
    of progress events. Otherwise, returns a JSON response after completion.
    """
    library = get_library_by_slug(db, slug)

    # Check if client wants SSE
    accept_header = http_request.headers.get("accept", "")
    use_sse = "text/event-stream" in accept_header

    # Convert API rules to transformation engine rules
    try:
        transform_rules = [convert_api_rule_to_transform_rule(rule) for rule in request.rules]
    except RegexPatternError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_REGEX"},
        )

    # Get items from database
    items_db = (
        db.query(ImportItem)
        .filter(
            ImportItem.library_id == library.id,
            ImportItem.id.in_(request.item_ids),
        )
        .all()
    )

    # Build lookup for found items
    items_by_id = {item.id: item for item in items_db}

    # Convert items to dictionaries for transformation engine
    items_data = [item_to_dict(item, library.import_path) for item in items_db]

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

    if use_sse:
        return await _batch_update_sse(
            db, library, items_by_id, changes_by_id, request.item_ids
        )
    else:
        return await _batch_update_json(
            db, library, items_by_id, changes_by_id, request.item_ids
        )


async def _batch_update_sse(
    db: Session,
    library: Library,
    items_by_id: Dict[int, ImportItem],
    changes_by_id: Dict[int, Dict[str, str]],
    item_ids: List[int],
) -> StreamingResponse:
    """Execute batch update with SSE progress reporting."""

    async def event_generator():
        started_at = datetime.utcnow()
        total_items = len(item_ids)
        items_succeeded = 0
        items_failed = 0
        items_processed = 0

        # Send batch_started event
        started_event = SSEBatchStarted(
            total_items=total_items,
            started_at=started_at,
        )
        yield f"event: batch_started\ndata: {started_event.model_dump_json()}\n\n"

        tag_writer = get_tag_writer_registry()

        try:
            # Phase 1: Database updates (single transaction)
            for item_id in item_ids:
                item = items_by_id.get(item_id)
                changes = changes_by_id.get(item_id, {})

                if item and changes:
                    # Update database fields
                    for tag_name, value in changes.items():
                        if hasattr(item, tag_name):
                            if tag_name == "track_number":
                                # Handle track_number as integer
                                if value == "":
                                    setattr(item, tag_name, None)
                                else:
                                    try:
                                        # Parse "5/12" format if present
                                        if "/" in value:
                                            value = value.split("/")[0]
                                        setattr(item, tag_name, int(value))
                                    except ValueError:
                                        pass
                            else:
                                # Empty string clears the tag
                                if value == "":
                                    setattr(item, tag_name, None)
                                else:
                                    setattr(item, tag_name, value)

            # Commit all database changes
            db.commit()

            # Phase 2: File writes (one at a time)
            for item_id in item_ids:
                item = items_by_id.get(item_id)
                changes = changes_by_id.get(item_id, {})
                items_processed += 1

                if not item:
                    # Item not found
                    items_failed += 1
                    progress_event = SSEItemProgress(
                        item_id=item_id,
                        status="failed",
                        items_processed=items_processed,
                        items_total=total_items,
                        progress_percent=round(items_processed / total_items * 100, 1),
                        error=ItemError(
                            code="ITEM_NOT_FOUND",
                            message=f"Import item with ID {item_id} not found",
                        ),
                    )
                    yield f"event: item_progress\ndata: {progress_event.model_dump_json()}\n\n"
                    continue

                if not changes:
                    # No changes for this item
                    items_succeeded += 1
                    progress_event = SSEItemProgress(
                        item_id=item_id,
                        status="success",
                        items_processed=items_processed,
                        items_total=total_items,
                        progress_percent=round(items_processed / total_items * 100, 1),
                    )
                    yield f"event: item_progress\ndata: {progress_event.model_dump_json()}\n\n"
                    continue

                # Write tags to file
                result = tag_writer.write_tags(item.path, changes)

                if result.success:
                    items_succeeded += 1
                    progress_event = SSEItemProgress(
                        item_id=item_id,
                        status="success",
                        items_processed=items_processed,
                        items_total=total_items,
                        progress_percent=round(items_processed / total_items * 100, 1),
                    )
                else:
                    items_failed += 1
                    progress_event = SSEItemProgress(
                        item_id=item_id,
                        status="failed",
                        items_processed=items_processed,
                        items_total=total_items,
                        progress_percent=round(items_processed / total_items * 100, 1),
                        error=ItemError(
                            code=result.error_code or "WRITE_ERROR",
                            message=result.error or "Unknown error",
                            file_path=item.path,
                        ),
                    )

                yield f"event: item_progress\ndata: {progress_event.model_dump_json()}\n\n"

                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.01)

            # Send batch_completed event
            completed_at = datetime.utcnow()
            duration = int((completed_at - started_at).total_seconds())
            completed_event = SSEBatchCompleted(
                items_total=total_items,
                items_succeeded=items_succeeded,
                items_failed=items_failed,
                completed_at=completed_at,
                duration_seconds=duration,
            )
            yield f"event: batch_completed\ndata: {completed_event.model_dump_json()}\n\n"

        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            db.rollback()

            failed_event = SSEBatchFailed(
                error_code="DATABASE_ERROR",
                message=str(e),
                failed_at=datetime.utcnow(),
            )
            yield f"event: batch_failed\ndata: {failed_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _batch_update_json(
    db: Session,
    library: Library,
    items_by_id: Dict[int, ImportItem],
    changes_by_id: Dict[int, Dict[str, str]],
    item_ids: List[int],
) -> BatchUpdateResponse:
    """Execute batch update and return JSON response."""
    started_at = datetime.utcnow()
    total_items = len(item_ids)
    items_succeeded = 0
    items_failed = 0
    results: List[ItemResult] = []

    tag_writer = get_tag_writer_registry()

    try:
        # Phase 1: Database updates (single transaction)
        for item_id in item_ids:
            item = items_by_id.get(item_id)
            changes = changes_by_id.get(item_id, {})

            if item and changes:
                # Update database fields
                for tag_name, value in changes.items():
                    if hasattr(item, tag_name):
                        if tag_name == "track_number":
                            # Handle track_number as integer
                            if value == "":
                                setattr(item, tag_name, None)
                            else:
                                try:
                                    # Parse "5/12" format if present
                                    if "/" in value:
                                        value = value.split("/")[0]
                                    setattr(item, tag_name, int(value))
                                except ValueError:
                                    pass
                        else:
                            # Empty string clears the tag
                            if value == "":
                                setattr(item, tag_name, None)
                            else:
                                setattr(item, tag_name, value)

        # Commit all database changes
        db.commit()

        # Phase 2: File writes (one at a time)
        for item_id in item_ids:
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
                            message=f"Import item with ID {item_id} not found",
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
            result = tag_writer.write_tags(item.path, changes)

            if result.success:
                items_succeeded += 1
                results.append(
                    ItemResult(
                        item_id=item_id,
                        status="success",
                        changes_applied=result.tags_written,
                    )
                )
            else:
                items_failed += 1
                results.append(
                    ItemResult(
                        item_id=item_id,
                        status="failed",
                        error=ItemError(
                            code=result.error_code or "WRITE_ERROR",
                            message=result.error or "Unknown error",
                            file_path=item.path,
                        ),
                    )
                )

    except Exception as e:
        logger.error(f"Batch update failed: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Batch update failed: {e}",
            headers={"X-Error-Code": "DATABASE_ERROR"},
        )

    completed_at = datetime.utcnow()
    duration = int((completed_at - started_at).total_seconds())

    return BatchUpdateResponse(
        status="completed",
        items_total=total_items,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        results=results,
    )
