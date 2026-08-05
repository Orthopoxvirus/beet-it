"""Celery tasks for import folder scanning and watcher management."""

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Generator

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.database import SessionLocal
from app.models.library import Library
from app.models.import_scan import ImportScan
from app.models.import_item import ImportItem
from app.services.redis_keys import RedisKeyManager, get_redis_key_manager
from app.services.scanner.scanner_service import ScannerService, ScannedItem
from app.services.task_events import get_task_event_service

logger = logging.getLogger(__name__)
settings = get_settings()


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def get_redis_manager() -> RedisKeyManager:
    """Get a Redis key manager instance."""
    return get_redis_key_manager(settings.redis_url)


@contextmanager
def operation_lock(
    library_id: int,
    operation_type: str,
    redis_manager: Optional[RedisKeyManager] = None,
) -> Generator[None, None, None]:
    """Context manager for operation locking.

    Usage:
        with operation_lock(library_id, "import"):
            # Do import operations
            pass

    Args:
        library_id: The library ID.
        operation_type: Type of operation (import, tag_modify, move, delete).
        redis_manager: Optional Redis manager (creates one if not provided).
    """
    if redis_manager is None:
        redis_manager = get_redis_manager()

    try:
        redis_manager.acquire_operation_lock(library_id, operation_type)
        logger.debug(f"Acquired {operation_type} lock for library {library_id}")
        yield
    finally:
        redis_manager.release_operation_lock(library_id, operation_type)
        logger.debug(f"Released {operation_type} lock for library {library_id}")


@celery_app.task(bind=True, name="scan_tasks.trigger_scan")
def trigger_scan(self, library_id: int, triggered_by: str = "watcher") -> Dict[str, Any]:
    """Trigger a scan after debounce expires.

    This task is called when the debounce timer expires. It checks if a scan
    can be started and either starts it immediately or queues it.

    Args:
        library_id: The library ID.
        triggered_by: What triggered the scan (watcher, manual).

    Returns:
        Dict with status information.
    """
    redis_manager = get_redis_manager()

    # Check if debounce is still active (another change came in)
    if redis_manager.check_debounce(library_id):
        remaining_ttl = redis_manager.get_debounce_ttl(library_id)
        logger.info(
            f"Scan trigger for library {library_id} deferred - "
            f"debounce still active ({remaining_ttl}s remaining)"
        )
        return {
            "status": "deferred",
            "message": "Debounce still active",
            "remaining_seconds": remaining_ttl,
        }

    # Clear pending scan flag
    redis_manager.set_watcher_state(library_id, active=True, pending_scan=False)

    # Check for blocking operations
    blocking_ops = redis_manager.get_active_operations(library_id)
    if blocking_ops:
        # Queue the scan
        queue_position = redis_manager.enqueue_scan(library_id, triggered_by)
        logger.info(
            f"Scan queued for library {library_id} (position {queue_position}), "
            f"blocked by: {blocking_ops}"
        )

        # Publish blocked event
        redis_manager.publish_scan_event(
            library_id,
            "scan_blocked",
            {
                "library_id": library_id,
                "blocking_operations": blocking_ops,
                "queue_position": queue_position,
            },
        )

        return {
            "status": "queued",
            "queue_position": queue_position,
            "blocking_operations": blocking_ops,
        }

    # Check if a scan is already running
    progress = redis_manager.get_scan_progress(library_id)
    if progress and progress.get("status") in ("scanning", "extracting_metadata"):
        # Queue the scan
        queue_position = redis_manager.enqueue_scan(library_id, triggered_by)
        logger.info(
            f"Scan queued for library {library_id} (position {queue_position}), "
            "another scan is running"
        )
        return {
            "status": "queued",
            "queue_position": queue_position,
        }

    # Start the scan
    execute_scan.delay(library_id, triggered_by)

    return {
        "status": "started",
        "message": f"Scan started for library {library_id}",
    }


@celery_app.task(bind=True, name="scan_tasks.execute_scan")
def execute_scan(self, library_id: int, triggered_by: str = "manual") -> Dict[str, Any]:
    """Execute a scan of the library's import folder.

    This task performs the actual scanning work:
    1. Creates a scan record
    2. Walks the filesystem
    3. Extracts metadata
    4. Updates the database
    5. Reports progress via Redis pub/sub

    Args:
        library_id: The library ID.
        triggered_by: What triggered the scan.

    Returns:
        Dict with scan results.
    """
    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    activity_event_id = None

    try:
        # Get the library
        library = db.query(Library).filter(Library.id == library_id).first()
        if not library:
            logger.error(f"Library {library_id} not found")
            return {"status": "error", "message": "Library not found"}

        if not library.import_path:
            logger.error(f"Library {library_id} has no import path configured")
            return {"status": "error", "message": "No import path configured"}

        # Create scan record
        scan = ImportScan(
            library_id=library_id,
            status="scanning",
            started_at=datetime.now(timezone.utc),
            items_total=0,
            items_processed=0,
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        logger.info(f"Starting scan {scan.id} for library {library_id}")

        # Record task start for activity monitor
        activity_event_id = task_event_service.record_start(
            task_type="scan",
            library_id=library_id,
            library_slug=library.slug,
            description="Scan import folder",
            metadata={"scan_id": scan.id, "triggered_by": triggered_by},
        )

        # Initialize progress in Redis
        redis_manager.set_scan_progress(
            library_id,
            scan.id,
            "scanning",
            started_at=scan.started_at,
        )

        # Publish scan started event
        redis_manager.publish_scan_event(
            library_id,
            "scan_started",
            {
                "scan_id": scan.id,
                "library_id": library_id,
                "library_slug": library.slug,
                "started_at": scan.started_at.isoformat(),
            },
        )

        # Initialize scanner
        scanner = ScannerService(
            batch_size=100,
            timeout_seconds=settings.scan_timeout_seconds if hasattr(settings, 'scan_timeout_seconds') else 3600,
        )

        # Get previous items for change detection
        previous_items = {}
        prev_scan = (
            db.query(ImportScan)
            .filter(
                ImportScan.library_id == library_id,
                ImportScan.status == "completed",
                ImportScan.id != scan.id,
            )
            .order_by(ImportScan.completed_at.desc())
            .first()
        )
        if prev_scan:
            prev_items_query = db.query(ImportItem).filter(
                ImportItem.scan_id == prev_scan.id
            )
            for item in prev_items_query:
                previous_items[item.path] = {
                    "item_type": item.item_type,
                    "metadata": {
                        "album": item.album,
                        "album_artist": item.album_artist,
                        "artist": item.artist,
                        "title": item.title,
                        "track_number": item.track_number,
                        "genre": item.genre,
                    }
                    if item.item_type == "file"
                    else None,
                }

        # Scan the import folder
        current_items: Dict[str, ScannedItem] = {}
        items_processed = 0
        items_total = 0

        def progress_callback(processed: int, total: int, current_file: str) -> None:
            nonlocal items_processed, items_total
            items_processed = processed
            items_total = total

            # Update database
            scan.items_processed = processed
            scan.items_total = total
            db.commit()

            # Update Redis progress
            progress_percent = (processed / total * 100) if total > 0 else 0
            redis_manager.set_scan_progress(
                library_id,
                scan.id,
                "scanning",
                items_total=total,
                items_processed=processed,
                current_file=current_file,
                started_at=scan.started_at,
            )

            # Publish progress event
            elapsed = (datetime.now(timezone.utc) - scan.started_at).total_seconds()
            redis_manager.publish_scan_event(
                library_id,
                "scan_progress",
                {
                    "scan_id": scan.id,
                    "status": "scanning",
                    "items_total": total,
                    "items_processed": processed,
                    "progress_percent": round(progress_percent, 1),
                    "current_file": current_file,
                    "elapsed_seconds": int(elapsed),
                },
            )

            # Update activity monitor progress
            if activity_event_id:
                task_event_service.record_progress(
                    event_id=activity_event_id,
                    progress_percent=round(progress_percent, 1),
                    metadata={
                        "items_total": total,
                        "items_processed": processed,
                        "current_file": current_file,
                    },
                )

        # Perform the scan
        for item in scanner.scan_directory(library.import_path, progress_callback):
            current_items[item.path] = item

        # Update status to extracting metadata
        scan.status = "extracting_metadata"
        db.commit()

        redis_manager.set_scan_progress(
            library_id,
            scan.id,
            "extracting_metadata",
            items_total=items_total,
            items_processed=items_processed,
            started_at=scan.started_at,
        )

        # Detect changes
        new_paths, modified_paths, unchanged_paths, deleted_paths = scanner.detect_changes(
            current_items, previous_items
        )

        # Save items to database
        now = datetime.now(timezone.utc)
        new_items_count = 0
        modified_items_count = 0
        deleted_items_count = len(deleted_paths)

        for path, scanned_item in current_items.items():
            # Determine status
            if path in new_paths:
                status = "new"
                new_items_count += 1
            elif path in modified_paths:
                status = "modified"
                modified_items_count += 1
            else:
                status = "unchanged"

            # Check if item exists
            existing = (
                db.query(ImportItem)
                .filter(
                    ImportItem.library_id == library_id,
                    ImportItem.path == path,
                )
                .first()
            )

            if existing:
                # Update existing item
                existing.scan_id = scan.id
                existing.status = status
                existing.last_seen_at = now
                if scanned_item.metadata:
                    existing.album = scanned_item.metadata.album
                    existing.album_artist = scanned_item.metadata.album_artist
                    existing.artist = scanned_item.metadata.artist
                    existing.title = scanned_item.metadata.title
                    existing.track_number = scanned_item.metadata.track_number
                    existing.genre = scanned_item.metadata.genre
                    existing.format = scanned_item.metadata.format
                    existing.bitrate = scanned_item.metadata.bitrate
            else:
                # Create new item
                import_item = ImportItem(
                    library_id=library_id,
                    scan_id=scan.id,
                    item_type=scanned_item.item_type,
                    path=scanned_item.path,
                    directory=scanned_item.directory,
                    filename=scanned_item.filename,
                    status=status,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                if scanned_item.metadata:
                    import_item.album = scanned_item.metadata.album
                    import_item.album_artist = scanned_item.metadata.album_artist
                    import_item.artist = scanned_item.metadata.artist
                    import_item.title = scanned_item.metadata.title
                    import_item.track_number = scanned_item.metadata.track_number
                    import_item.genre = scanned_item.metadata.genre
                    import_item.format = scanned_item.metadata.format
                    import_item.bitrate = scanned_item.metadata.bitrate
                db.add(import_item)

        # Mark deleted items
        for path in deleted_paths:
            deleted_item = (
                db.query(ImportItem)
                .filter(
                    ImportItem.library_id == library_id,
                    ImportItem.path == path,
                )
                .first()
            )
            if deleted_item:
                deleted_item.scan_id = scan.id
                deleted_item.status = "deleted"
                deleted_item.last_seen_at = now

        # Update scan record
        scan.status = "completed"
        scan.completed_at = datetime.now(timezone.utc)
        scan.items_total = len(current_items)
        scan.items_processed = len(current_items)
        db.commit()

        # Clear Redis progress
        redis_manager.clear_scan_progress(library_id)

        # Invalidate import tree cache so next request reflects new files
        redis_manager.invalidate_import_tree_cache(library_id)

        # Publish completed event
        duration = (scan.completed_at - scan.started_at).total_seconds()
        redis_manager.publish_scan_event(
            library_id,
            "scan_completed",
            {
                "scan_id": scan.id,
                "status": "completed",
                "items_total": scan.items_total,
                "items_processed": scan.items_processed,
                "new_items": new_items_count,
                "modified_items": modified_items_count,
                "deleted_items": deleted_items_count,
                "completed_at": scan.completed_at.isoformat(),
                "duration_seconds": int(duration),
            },
        )

        logger.info(
            f"Scan {scan.id} completed for library {library_id}: "
            f"{new_items_count} new, {modified_items_count} modified, "
            f"{deleted_items_count} deleted"
        )

        # Record completion for activity monitor
        if activity_event_id:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed",
                metadata={
                    "scan_id": scan.id,
                    "items_total": scan.items_total,
                    "new_items": new_items_count,
                    "modified_items": modified_items_count,
                    "deleted_items": deleted_items_count,
                },
            )

        # Check for queued scans
        _process_scan_queue(library_id, redis_manager)

        # Check if auto-analyze is enabled and trigger analysis for newly discovered albums
        try:
            _trigger_auto_analyze_if_enabled(db, library_id, library.import_path, redis_manager)
        except Exception as auto_analyze_error:
            logger.error(f"Auto-analyze trigger failed for library {library_id}: {auto_analyze_error}")

        return {
            "status": "completed",
            "scan_id": scan.id,
            "items_total": scan.items_total,
            "new_items": new_items_count,
            "modified_items": modified_items_count,
            "deleted_items": deleted_items_count,
            "duration_seconds": int(duration),
        }

    except Exception as e:
        logger.error(f"Scan failed for library {library_id}: {e}")

        # Update scan record if it exists
        try:
            if "scan" in locals() and scan.id:
                scan.status = "failed"
                scan.completed_at = datetime.now(timezone.utc)
                scan.error_message = str(e)
                db.commit()

                # Publish failed event
                redis_manager.publish_scan_event(
                    library_id,
                    "scan_failed",
                    {
                        "scan_id": scan.id,
                        "status": "failed",
                        "error_message": str(e),
                        "failed_at": scan.completed_at.isoformat(),
                    },
                )
        except Exception as db_error:
            logger.error(f"Failed to update scan status: {db_error}")

        # Record failure for activity monitor
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"error": str(e)},
                )
            except Exception as activity_error:
                logger.error(f"Failed to record activity completion: {activity_error}")

        # Clear Redis progress
        redis_manager.clear_scan_progress(library_id)

        # Process queued scans even on failure
        _process_scan_queue(library_id, redis_manager)

        return {
            "status": "failed",
            "error": str(e),
        }

    finally:
        db.close()


def _process_scan_queue(library_id: int, redis_manager: RedisKeyManager) -> None:
    """Process the next scan in the queue if available.

    Args:
        library_id: The library ID.
        redis_manager: Redis key manager.
    """
    # Check for queued scans
    queued = redis_manager.dequeue_scan(library_id)
    if queued:
        logger.info(f"Processing queued scan for library {library_id}")
        trigger_scan.delay(library_id, queued.get("triggered_by", "queued"))


def _trigger_auto_analyze_if_enabled(
    db: Session,
    library_id: int,
    import_path: str,
    redis_manager: RedisKeyManager,
) -> None:
    """Trigger auto-analyze for newly discovered albums if setting is enabled.

    Args:
        db: Database session.
        library_id: The library ID.
        import_path: The library's import path.
        redis_manager: Redis key manager.
    """
    from app.models.user_settings import UserSettings
    from app.services.import_tree import ImportTreeService
    from app.tasks.beets_tasks import analyze_album_task, drain_analysis_queue
    import uuid as uuid_module

    # Check if auto-analyze is enabled for this library
    user_settings = db.query(UserSettings).first()
    if not user_settings:
        return

    auto_analyze_settings = user_settings.preferences.get("auto_analyze_settings", {})
    if not auto_analyze_settings.get(str(library_id), False):
        return

    logger.info(f"Auto-analyze enabled for library {library_id}, enqueueing albums")

    # Collect all album paths from the import tree
    tree_service = ImportTreeService()
    tree = tree_service.build_import_tree(import_path)

    album_paths = []

    def collect_albums(nodes):
        for node in nodes:
            abs_path = os.path.join(import_path, node.path)
            if node.is_album:
                album_paths.append(abs_path)
            if node.children:
                collect_albums(node.children)

    collect_albums(tree)

    if not album_paths:
        logger.info(f"No album folders found in import path for library {library_id}")
        return

    concurrency_cap = settings.max_concurrent_analyses_per_library
    enqueued = 0
    dispatched = 0
    skipped = 0

    for album_path in album_paths:
        # Check if already in queue or active
        is_queued, _, is_active = redis_manager.is_album_in_queue_or_active(library_id, album_path)
        if is_queued or is_active:
            skipped += 1
            continue

        # Check if cached
        cached_result = redis_manager.get_beets_album_result(library_id, album_path)
        if cached_result is not None:
            skipped += 1
            continue

        # Check concurrency cap
        active_count = redis_manager.get_active_analysis_count(library_id)
        job_id = str(uuid_module.uuid4())

        if active_count < concurrency_cap:
            # Dispatch immediately
            try:
                from datetime import datetime, timezone as tz
                redis_manager.register_active_analysis(library_id, job_id, album_path)
                redis_manager.set_beets_analysis_result(
                    job_id,
                    status="analyzing",
                    started_at=datetime.now(tz.utc),
                )
                analyze_album_task.delay(
                    library_id=library_id,
                    album_path=album_path,
                    job_id=job_id,
                )
                dispatched += 1
            except Exception as e:
                redis_manager.unregister_active_analysis(library_id, job_id)
                logger.warning(f"Failed to dispatch auto-analysis for {album_path}: {e}")
                redis_manager.enqueue_album_analysis(library_id, album_path)
                enqueued += 1
        else:
            # Enqueue
            redis_manager.enqueue_album_analysis(library_id, album_path)
            enqueued += 1

    logger.info(
        f"Auto-analyze for library {library_id}: {dispatched} dispatched, "
        f"{enqueued} enqueued, {skipped} skipped"
    )


@celery_app.task(bind=True, name="scan_tasks.start_watcher_for_library")
def start_watcher_for_library(self, library_id: int) -> Dict[str, Any]:
    """Start a watcher for a library's import folder.

    This task uses the global WatcherService singleton to ensure watchers
    persist beyond task execution. The singleton is initialized during
    worker startup via celery signals.

    Args:
        library_id: The library ID.

    Returns:
        Dict with status information.
    """
    from app.services.watcher import get_watcher_service

    db = get_db()

    try:
        # Check if watchers are enabled
        if hasattr(settings, 'enable_import_watchers') and not settings.enable_import_watchers:
            return {"status": "disabled", "message": "Import watchers are disabled"}

        # Get the global watcher service singleton
        watcher_service = get_watcher_service()
        if watcher_service is None:
            logger.error("WatcherService singleton not initialized")
            return {"status": "error", "message": "WatcherService not initialized"}

        # Get the library
        library = db.query(Library).filter(Library.id == library_id).first()
        if not library:
            return {"status": "error", "message": "Library not found"}

        if not library.import_path:
            return {"status": "error", "message": "No import path configured"}

        # Start the watcher using the singleton
        # The singleton already has the scan trigger callback configured
        success = watcher_service.start_watcher(library_id, library.import_path)

        if success:
            logger.info(f"Started watcher for library {library_id}")
            return {"status": "started", "library_id": library_id}
        else:
            return {"status": "error", "message": "Failed to start watcher"}

    except Exception as e:
        logger.error(f"Failed to start watcher for library {library_id}: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(bind=True, name="scan_tasks.stop_watcher_for_library")
def stop_watcher_for_library(self, library_id: int) -> Dict[str, Any]:
    """Stop a watcher for a library.

    This task uses the global WatcherService singleton to stop watchers.

    Args:
        library_id: The library ID.

    Returns:
        Dict with status information.
    """
    from app.services.watcher import get_watcher_service

    redis_manager = get_redis_manager()

    try:
        # Get the global watcher service singleton
        watcher_service = get_watcher_service()
        if watcher_service is None:
            # If singleton isn't initialized, just clean up Redis state
            logger.warning("WatcherService singleton not initialized during stop_watcher")
            redis_manager.cleanup_library_keys(library_id)
            return {"status": "not_running", "message": "WatcherService not initialized"}

        success = watcher_service.stop_watcher(library_id)

        # Clean up Redis state
        redis_manager.cleanup_library_keys(library_id)

        if success:
            logger.info(f"Stopped watcher for library {library_id}")
            return {"status": "stopped", "library_id": library_id}
        else:
            return {"status": "not_running", "message": "Watcher was not running"}

    except Exception as e:
        logger.error(f"Failed to stop watcher for library {library_id}: {e}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="scan_tasks.check_watcher_health")
def check_watcher_health(self) -> Dict[str, Any]:
    """Periodic task to check watcher health and restart stale watchers.

    This task checks the health of watchers using the global singleton
    and restarts any that have become stale.

    Returns:
        Dict with health check results.
    """
    from app.services.watcher import get_watcher_service

    db = get_db()
    redis_manager = get_redis_manager()

    try:
        # Check if watchers are enabled
        if hasattr(settings, 'enable_import_watchers') and not settings.enable_import_watchers:
            return {"status": "disabled"}

        # Get the global watcher service singleton
        watcher_service = get_watcher_service()
        if watcher_service is None:
            logger.warning("WatcherService singleton not initialized during health check")
            return {"status": "error", "message": "WatcherService not initialized"}

        # Get all libraries with import paths
        libraries = db.query(Library).filter(Library.import_path.isnot(None)).all()

        results = {
            "checked": 0,
            "healthy": 0,
            "restarted": 0,
            "failed": 0,
        }

        for library in libraries:
            results["checked"] += 1

            # Check if watcher should be running
            state = redis_manager.get_watcher_state(library.id)

            if state and state.get("active"):
                # Check health using the singleton's method
                if watcher_service.check_health(library.id):
                    results["healthy"] += 1
                else:
                    # Watcher is stale, restart it directly using singleton
                    logger.warning(
                        f"Watcher for library {library.id} is stale, restarting"
                    )
                    try:
                        # Restart directly using singleton for immediate effect
                        watcher_service.stop_watcher(library.id)
                        success = watcher_service.start_watcher(library.id, library.import_path)
                        if success:
                            results["restarted"] += 1
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        logger.error(
                            f"Failed to restart watcher for library {library.id}: {e}"
                        )
                        results["failed"] += 1

        logger.info(
            f"Watcher health check: {results['healthy']} healthy, "
            f"{results['restarted']} restarted, {results['failed']} failed"
        )

        return results

    except Exception as e:
        logger.error(f"Watcher health check failed: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(bind=True, name="scan_tasks.resume_watchers")
def resume_watchers(self) -> Dict[str, Any]:
    """Resume watchers for all libraries on startup.

    This task is automatically called when the Celery worker starts
    (via the worker_ready signal in celery_app.py). It uses the global
    WatcherService singleton to start watchers directly.

    Returns:
        Dict with resume results.
    """
    from app.services.watcher import get_watcher_service

    db = get_db()

    try:
        # Check if watchers are enabled
        if hasattr(settings, 'enable_import_watchers') and not settings.enable_import_watchers:
            logger.info("Import watchers are disabled by configuration")
            return {"status": "disabled"}

        # Get the global watcher service singleton
        watcher_service = get_watcher_service()
        if watcher_service is None:
            logger.error("WatcherService singleton not initialized during resume_watchers")
            return {"status": "error", "message": "WatcherService not initialized"}

        # Get all libraries with import paths
        libraries = db.query(Library).filter(Library.import_path.isnot(None)).all()

        results = {
            "total": len(libraries),
            "started": 0,
            "skipped": 0,
            "failed": 0,
        }

        for library in libraries:
            # Start watcher directly using the singleton for immediate effect
            try:
                success = watcher_service.start_watcher(library.id, library.import_path)
                if success:
                    results["started"] += 1
                    logger.info(f"Resumed watcher for library {library.id}")
                else:
                    results["failed"] += 1
                    logger.warning(f"Failed to resume watcher for library {library.id}")
            except Exception as e:
                logger.error(
                    f"Failed to resume watcher for library {library.id}: {e}"
                )
                results["failed"] += 1

        logger.info(
            f"Resumed watchers: {results['started']} started, "
            f"{results['failed']} failed out of {results['total']} total"
        )

        return results

    except Exception as e:
        logger.error(f"Failed to resume watchers: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


# Configure Celery Beat schedule
celery_app.conf.beat_schedule = {
    "check-watcher-health": {
        "task": "scan_tasks.check_watcher_health",
        "schedule": 60.0,  # Every minute
    },
    "cleanup-stale-activity-entries": {
        "task": "maintenance.cleanup_stale_activity_entries",
        "schedule": 900.0,  # Every 15 minutes
    },
    "resume-stalled-bpm-backfills": {
        "task": "maintenance.resume_stalled_bpm_backfills",
        "schedule": 900.0,  # Every 15 minutes — revive backfills killed mid-link (deploys/crashes)
    },
    "cleanup-expired-downloads": {
        "task": "download_tasks.cleanup_expired_downloads",
        "schedule": 86400.0,  # Daily — remove download archives past their 7-day retention
    },
}
