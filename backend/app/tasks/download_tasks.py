"""Celery tasks for the Download Center: pack gathered albums, expire old zips."""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from app.celery_app import celery_app
from app.config import get_settings
from app.database import SessionLocal
from app.models.download_job import DownloadJob
from app.models.enums import TaskStatus, TaskType
from app.models.library import Library
from app.services.beets_library_service import BeetsLibraryService
from app.services.download_service import pack_selection_to_zip
from app.services.redis_keys import get_redis_key_manager, RedisKeyManager
from app.services.task_events import get_task_event_service

logger = logging.getLogger(__name__)
settings = get_settings()

# How long a finished archive is kept before the cleanup task removes it.
DOWNLOAD_RETENTION_DAYS = 7


def get_db():
    return SessionLocal()


def get_redis_manager() -> RedisKeyManager:
    return get_redis_key_manager(settings.redis_url)


def _zip_filename(job: DownloadJob) -> str:
    """Stable, collision-free archive name for a job."""
    return f"{job.library_slug}-download-{job.id}.zip"


def _remove_quietly(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError as exc:  # pragma: no cover - best-effort cleanup
        logger.warning("Could not remove download archive %s: %s", path, exc)


@celery_app.task(bind=True, name="download_tasks.pack_download_job", soft_time_limit=3000, time_limit=3300)
def pack_download_job(self, job_id: int) -> Dict[str, Any]:
    """Pack a queued DownloadJob's albums into one ZIP and mark it completed.

    Progress is committed to the job row per album (so the Download Center shows
    live counts) and also published as activity_monitor task_progress events.
    """
    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    activity_event_id = None

    try:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            logger.error("pack_download_job: job %s not found", job_id)
            return {"status": "failed", "error": "job not found"}

        library = db.query(Library).filter(Library.id == job.library_id).first()
        if not library or not library.database_path:
            job.status = TaskStatus.FAILED.value
            job.error = "Library or beets database not available"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "failed", "error": job.error}

        n_albums = len(job.album_ids or [])
        n_tracks = len(job.track_ids or [])
        unit = "album" if n_tracks == 0 else ("track" if n_albums == 0 else "item")
        activity_event_id = task_event_service.record_start(
            task_type=TaskType.DOWNLOAD.value,
            library_id=library.id,
            library_slug=library.slug,
            description=f"Packing {job.album_count} {unit}(s)",
            metadata={"job_id": job.id, "album_count": job.album_count},
        )

        filename = _zip_filename(job)
        dest_path = os.path.join(settings.downloads_path, filename)
        job.status = "packing"
        job.task_event_id = activity_event_id
        job.processed_count = 0
        # Record the destination up front so a crash mid-pack still leaves the
        # partial archive tracked (cleanup/delete remove it via zip_path).
        job.filename = filename
        job.zip_path = dest_path
        db.commit()

        beets_service = BeetsLibraryService()

        def progress_cb(processed: int, total: int, label: str) -> None:
            # Commit DB progress so the Download Center's job list reflects it,
            # then publish the ephemeral SSE progress event.
            job.processed_count = processed
            db.commit()
            percent = (processed / total * 100.0) if total else 100.0
            task_event_service.record_progress(
                event_id=activity_event_id,
                progress_percent=percent,
                metadata={
                    "items_total": total,
                    "items_processed": processed,
                    "current_file": label,
                },
            )

        size_bytes, packed_albums = pack_selection_to_zip(
            beets_service=beets_service,
            db_path=library.database_path,
            library_path=library.library_path,
            album_ids=list(job.album_ids or []),
            track_ids=list(job.track_ids or []),
            dest_path=dest_path,
            progress_cb=progress_cb,
        )

        job.status = TaskStatus.COMPLETED.value
        job.zip_path = dest_path
        job.filename = filename
        job.size_bytes = size_bytes
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        task_event_service.record_completion(
            event_id=activity_event_id,
            status=TaskStatus.COMPLETED.value,
            metadata={"job_id": job.id, "size_bytes": size_bytes, "albums": packed_albums},
        )
        logger.info("Download job %s completed: %s bytes, %s albums", job.id, size_bytes, packed_albums)
        return {"status": "completed", "size_bytes": size_bytes}

    except Exception as exc:  # noqa: BLE001 - record any failure on the job
        logger.exception("Download job %s failed", job_id)
        try:
            job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.status = TaskStatus.FAILED.value
                job.error = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:  # pragma: no cover
            db.rollback()
        if activity_event_id:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status=TaskStatus.FAILED.value,
                metadata={"error": str(exc)},
            )
        return {"status": "failed", "error": str(exc)}

    finally:
        task_event_service.close()
        db.close()


@celery_app.task(bind=True, name="download_tasks.cleanup_expired_downloads")
def cleanup_expired_downloads(self) -> Dict[str, Any]:
    """Delete download jobs (and their archives) past their retention window."""
    db = get_db()
    removed = 0
    try:
        now = datetime.now(timezone.utc)
        expired = (
            db.query(DownloadJob)
            .filter(DownloadJob.expires_at.isnot(None), DownloadJob.expires_at < now)
            .all()
        )
        for job in expired:
            _remove_quietly(job.zip_path)
            db.delete(job)
            removed += 1
        db.commit()
        if removed:
            logger.info("Cleaned up %s expired download job(s)", removed)
        return {"status": "completed", "removed_count": removed}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("cleanup_expired_downloads failed: %s", exc)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
