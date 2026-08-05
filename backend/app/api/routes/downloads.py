"""API routes for the Download Center — queue, list, fetch and delete jobs."""

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.libraries import get_library_by_slug
from app.database import get_db
from app.models.download_job import DownloadJob
from app.schemas.download import (
    DownloadJobListResponse,
    DownloadJobResponse,
    DownloadQueueRequest,
)
from app.tasks.download_tasks import DOWNLOAD_RETENTION_DAYS, pack_download_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["downloads"])


@router.post("/{slug}/downloads", response_model=DownloadJobResponse, status_code=201)
def queue_download(
    slug: str,
    request: DownloadQueueRequest,
    db: Session = Depends(get_db),
):
    """Queue a download of albums and/or single titles, kick off async packing.

    Albums pack as folders, titles pack flat as "Artist - Title.ext"; a mixed
    request lands both in the same archive.
    """
    library = get_library_by_slug(db, slug)

    # Deduplicate while preserving the user's order.
    album_ids = list(dict.fromkeys(request.album_ids))
    track_ids = list(dict.fromkeys(request.track_ids))
    if not album_ids and not track_ids:
        raise HTTPException(status_code=400, detail="Nothing to download: no albums or titles given")

    now = datetime.now(timezone.utc)
    job = DownloadJob(
        library_id=library.id,
        library_slug=library.slug,
        status="pending",
        album_ids=album_ids,
        track_ids=track_ids,
        # album_count is the progress denominator: one unit per album + per title.
        album_count=len(album_ids) + len(track_ids),
        processed_count=0,
        created_at=now,
        expires_at=now + timedelta(days=DOWNLOAD_RETENTION_DAYS),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    pack_download_job.delay(job.id)
    return job


@router.get("/{slug}/downloads", response_model=DownloadJobListResponse)
def list_downloads(slug: str, db: Session = Depends(get_db)):
    """List a library's download jobs, newest first."""
    library = get_library_by_slug(db, slug)
    jobs = (
        db.query(DownloadJob)
        .filter(DownloadJob.library_id == library.id)
        .order_by(DownloadJob.created_at.desc())
        .all()
    )
    return DownloadJobListResponse(items=jobs, total=len(jobs))


@router.get("/{slug}/downloads/{job_id}/file")
def download_zip(slug: str, job_id: int, db: Session = Depends(get_db)):
    """Serve a finished archive as a file download."""
    library = get_library_by_slug(db, slug)
    job = (
        db.query(DownloadJob)
        .filter(DownloadJob.id == job_id, DownloadJob.library_id == library.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Download not found")
    if job.status != "completed" or not job.zip_path:
        raise HTTPException(status_code=409, detail="Download is not ready yet")
    if not os.path.exists(job.zip_path):
        raise HTTPException(status_code=410, detail="Download archive no longer available")

    # The file transfer outlives this handler; release the DB connection now
    # so it doesn't sit "idle in transaction" for the whole download.
    db.close()

    return FileResponse(
        job.zip_path,
        media_type="application/zip",
        filename=job.filename or f"{slug}-download-{job.id}.zip",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{slug}/downloads/{job_id}", status_code=204)
def delete_download(slug: str, job_id: int, db: Session = Depends(get_db)):
    """Delete a download job and its archive."""
    library = get_library_by_slug(db, slug)
    job = (
        db.query(DownloadJob)
        .filter(DownloadJob.id == job_id, DownloadJob.library_id == library.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Download not found")

    if job.zip_path and os.path.exists(job.zip_path):
        try:
            os.remove(job.zip_path)
        except OSError as exc:
            logger.warning("Could not remove archive %s: %s", job.zip_path, exc)

    db.delete(job)
    db.commit()
    return None
