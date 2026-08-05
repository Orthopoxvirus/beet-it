"""API routes for beets autotag candidate analysis."""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.schemas.beets_search import SearchCandidatesResponse
from app.services.beets_search_service import (
    DEFAULT_SEARCH_TIMEOUT,
    PROVIDERS,
    search_all_providers,
)

from app.config import get_settings
from app.database import get_db
from app.models.library import Library
from app.schemas.beets_autotag import (
    ActiveItem,
    AnalyzeAlbumRequest,
    AnalyzeAlbumResponse,
    AnalyzeFolderRequest,
    AnalyzeFolderResponse,
    AnalyzeJobResponse,
    AnalyzeQueueResponse,
    AnalyzeStatusResponse,
    AudioOpJobResponse,
    AudioOpStatusResponse,
    AutoAnalyzeSettingRequest,
    AutoAnalyzeSettingResponse,
    ImportCleanupSettingRequest,
    ImportCleanupSettingResponse,
    BeetsAutotagErrorCodes,
    ConvertAudioRequest,
    DedupeWavRequest,
    CacheStatusResponse,
    Candidate,
    CandidateTrack,
    LocalAlbumInfo,
    LocalTrackInfo,
    ManualCandidateRequest,
    ManualCandidateResponse,
    MetadataChange,
    QueuedItem,
    TrackChange,
    detect_provider,
    extract_id_from_link,
)
from app.services.import_tree import ImportTreeService
from app.services.beets_autotag_service import (
    AnalysisTimeoutError,
    BeetsAnalysisError,
    BeetsAutotagService,
    MusicBrainzError,
    get_beets_autotag_service,
)
# Candidate resolution lives in its own service module (issue #76) so both this
# route and the automatic analysis path can reuse it. Re-exported here for
# backwards compatibility with existing imports/tests.
from app.services.candidate_resolvers import (  # noqa: F401
    DEFAULT_MANUAL_RESOLUTION_TIMEOUT,
    PluginNotAvailableError,
    ProviderError,
    ReleaseNotFoundError,
    ResolutionTimeoutError,
    _build_manual_track_change,
    _pair_local_tracks,
    resolve_deezer_candidate,
    resolve_discogs_candidate,
    resolve_manual_candidate,
    resolve_musicbrainz_candidate,
    resolve_spotify_candidate,
)
from app.services.beets_library_service import BeetsLibraryService
from app.services.redis_keys import get_redis_key_manager
from app.services.beets_import_service import (
    BeetsImportService,
    BeetsImportError,
    get_beets_import_service,
)
from app.schemas.beets_import import (
    ExistingAlbumInfo,
    IncomingAlbumInfo,
    ImportAlbumRequest,
    ImportJobResponse,
    ImportJobStatusResponse,
    ImportJobError,
    BulkImportStatusResponse,
    AlbumImportState,
    ImportStatusCounts,
    ImportErrorCodes,
)
from app.tasks.beets_tasks import (
    analyze_album_task,
    convert_audio_task,
    import_album_task,
    remove_duplicate_wavs_task,
)
from app.services import wav_flac_service

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/libraries/{slug}/beets", tags=["beets-autotag"])


def get_library_by_slug(db: Session, slug: str) -> Library:
    """Get a library by its slug, raising 404 if not found.

    Args:
        db: Database session.
        slug: The library slug to look up.

    Returns:
        The Library object.

    Raises:
        HTTPException: 404 if the library is not found.
    """
    library = db.query(Library).filter(Library.slug == slug).first()
    if not library:
        raise HTTPException(
            status_code=404,
            detail="Library not found",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.LIBRARY_NOT_FOUND},
        )
    return library


def get_autotag_service() -> BeetsAutotagService:
    """Dependency to get the beets autotag service."""
    # Get timeout from settings if available, otherwise use default
    timeout = int(os.environ.get("BEETS_ANALYSIS_TIMEOUT_SECONDS", "30"))
    return get_beets_autotag_service(timeout=timeout)


@router.post("/analyze", response_model=AnalyzeJobResponse, status_code=202)
def analyze_album(
    slug: str,
    request: AnalyzeAlbumRequest,
    db: Session = Depends(get_db),
    autotag_service: BeetsAutotagService = Depends(get_autotag_service),
):
    """Trigger async beets candidate analysis for an album in the library's import folder.

    Starts an async analysis job using beets' autotag functionality
    (beets.autotag.tag_album()) to match the album against configured sources
    (MusicBrainz, etc.). Returns immediately with a job ID.

    When the library has fewer than MAX_CONCURRENT_ANALYSES active analyses,
    the request is dispatched immediately. When at capacity, the request is
    queued and the response indicates the queue position.

    Use the /analyze/{job_id}/status endpoint to poll for results.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Request Body:
        album_path: Path to the album folder to analyze (relative or absolute)
        forceReanalyze: If true, bypass cached results and run fresh analysis

    Returns:
        AnalyzeJobResponse with job_id and status (202 Accepted)
        - status: "analyzing" if dispatched immediately
        - status: "queued" with queue_position if waiting
        - status: "completed" if returning cached result

    Raises:
        400: Invalid album path or path outside import folder
        404: Library not found or album not found
        409: Album already queued or being analyzed
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    # Check if library has import path configured
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no import path configured",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_IMPORT_PATH},
        )

    # Validate the album path (security check)
    try:
        canonical_album_path = autotag_service.validate_album_path(
            request.album_path, library.import_path
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.PATH_OUTSIDE_IMPORT},
        )

    # Check if album folder exists
    if not os.path.isdir(canonical_album_path):
        raise HTTPException(
            status_code=404,
            detail="Album folder not found at the specified path",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.ALBUM_NOT_FOUND},
        )

    redis_manager = get_redis_key_manager(settings.redis_url)

    # Check album path cache - return immediately if result is cached and not forcing re-analysis
    if not request.force_reanalyze:
        cached_result = redis_manager.get_beets_album_result(library.id, canonical_album_path)
        if cached_result is not None:
            # Create a synthetic completed job so the frontend can poll normally
            job_id = str(uuid.uuid4())
            redis_manager.set_beets_analysis_result(
                job_id,
                status="completed",
                result=cached_result,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            logger.info(
                f"Returning cached beets analysis for library '{slug}', "
                f"album: {request.album_path} (job_id={job_id})"
            )
            return AnalyzeJobResponse(
                job_id=job_id,
                album_path=request.album_path,
                status="completed",
                message=f"Cached analysis result for album: {request.album_path}",
            )

    # Check if album is already queued or being analyzed (duplicate detection)
    is_queued, queue_position, is_active = redis_manager.is_album_in_queue_or_active(
        library.id, canonical_album_path
    )

    if is_active:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Album is currently being analyzed",
                "errorCode": BeetsAutotagErrorCodes.ALREADY_ANALYZING,
            },
            headers={"X-Error-Code": BeetsAutotagErrorCodes.ALREADY_ANALYZING},
        )

    if is_queued:
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"Album is already queued for analysis at position {queue_position}",
                "errorCode": BeetsAutotagErrorCodes.ALREADY_QUEUED,
                "queuePosition": queue_position,
            },
            headers={"X-Error-Code": BeetsAutotagErrorCodes.ALREADY_QUEUED},
        )

    # If force_reanalyze, clear the album path cache
    if request.force_reanalyze:
        redis_manager.invalidate_beets_album_result(library.id, canonical_album_path)

    # Check concurrency cap
    concurrency_cap = settings.max_concurrent_analyses_per_library
    active_count = redis_manager.get_active_analysis_count(library.id)

    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    if active_count < concurrency_cap:
        # Dispatch immediately - pre-register to prevent race conditions
        try:
            redis_manager.register_active_analysis(library.id, job_id, canonical_album_path)

            # Create initial job status in Redis BEFORE starting task
            redis_manager.set_beets_analysis_result(
                job_id,
                status="analyzing",
                started_at=datetime.now(timezone.utc),
            )

            # Start the async analysis task
            analyze_album_task.delay(
                library_id=library.id,
                album_path=canonical_album_path,
                job_id=job_id,
            )

            logger.info(
                f"Started async beets analysis job {job_id} for library '{slug}', "
                f"album: {request.album_path}"
            )

            return AnalyzeJobResponse(
                job_id=job_id,
                album_path=request.album_path,
                status="analyzing",
                message=f"Analysis started for album: {request.album_path}",
            )
        except Exception as e:
            # Dispatch failed - unregister the active analysis
            redis_manager.unregister_active_analysis(library.id, job_id)
            logger.error(f"Failed to dispatch analysis task: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start analysis: {str(e)}",
            )
    else:
        # At capacity - enqueue the album
        queue_position = redis_manager.enqueue_album_analysis(library.id, canonical_album_path)

        # Create initial job status in Redis indicating queued state
        redis_manager.set_beets_analysis_result(
            job_id,
            status="queued",
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            f"Queued beets analysis job {job_id} at position {queue_position} "
            f"for library '{slug}', album: {request.album_path}"
        )

        return AnalyzeJobResponse(
            job_id=job_id,
            album_path=request.album_path,
            status="queued",
            queue_position=queue_position,
            message=f"Analysis queued at position {queue_position}",
        )


@router.get("/analyze/{job_id}/status", response_model=AnalyzeStatusResponse)
def get_analyze_status(
    slug: str,
    job_id: str,
    db: Session = Depends(get_db),
):
    """Get the status and results of an async beets analysis job.

    Poll this endpoint to check if the analysis is complete and retrieve results.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)
        job_id: The job ID returned from the /analyze endpoint

    Returns:
        AnalyzeStatusResponse with current status and results (if completed)

    Status values:
        - "analyzing": Analysis is in progress
        - "completed": Analysis finished successfully (result field populated)
        - "failed": Analysis failed (error field populated)

    Raises:
        404: Job ID not found or library not found
    """
    # Verify library exists
    library = get_library_by_slug(db, slug)

    # Get analysis result from Redis
    redis_manager = get_redis_key_manager(settings.redis_url)
    result = redis_manager.get_beets_analysis_result(job_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis job not found: {job_id}",
            headers={"X-Error-Code": "JOB_NOT_FOUND"},
        )

    # Build response based on status
    status = result.get("status", "unknown")

    if status == "completed":
        # Parse result and convert to response schema
        result_data = result.get("result")
        if result_data:
            # Convert the result to AnalyzeAlbumResponse
            local_album_data = result_data.get("local_album", {})
            candidates_data = result_data.get("candidates", [])

            local_album = LocalAlbumInfo(
                path=local_album_data.get("path", ""),
                artist=local_album_data.get("artist"),
                album=local_album_data.get("album"),
                metadata_source=local_album_data.get("metadata_source", "tags"),
                dominant_format=local_album_data.get("dominant_format"),
                has_wav=local_album_data.get("has_wav", False),
                has_flac=local_album_data.get("has_flac", False),
                duplicate_wav_count=local_album_data.get("duplicate_wav_count", 0),
                has_wma=local_album_data.get("has_wma", False),
                wma_recommended_target=local_album_data.get("wma_recommended_target"),
                tracks=[
                    LocalTrackInfo(**track) for track in local_album_data.get("tracks", [])
                ],
            )

            def parse_candidate(c: dict) -> Candidate:
                """Parse a candidate dict into a Candidate object."""
                return Candidate(
                    source=c.get("source", ""),
                    source_id=c.get("source_id"),
                    similarity=c.get("similarity", 0.0),
                    artist=c.get("artist", ""),
                    album=c.get("album", ""),
                    year=c.get("year"),
                    label=c.get("label"),
                    country=c.get("country"),
                    media=c.get("media"),
                    tracks=[
                        CandidateTrack(
                            index=t.get("index", 1),
                            title=t.get("title", ""),
                            length=t.get("length"),
                            local_title=t.get("local_title"),
                            local_path=t.get("local_path"),
                            changes=[MetadataChange(**change) for change in t.get("changes", [])],
                        )
                        for t in c.get("tracks", [])
                    ],
                    changes=[MetadataChange(**change) for change in c.get("changes", [])],
                    track_changes=[TrackChange(**tc) for tc in c.get("track_changes", [])],
                    is_manual=c.get("is_manual", False),
                )

            candidates = [parse_candidate(c) for c in candidates_data]

            # Parse manual candidates from cache
            manual_candidates_data = result_data.get("manual_candidates", [])
            manual_candidates = [parse_candidate(c) for c in manual_candidates_data]

            analyze_response = AnalyzeAlbumResponse(
                album_path=result_data.get("album_path", ""),
                local_album=local_album,
                candidates=candidates,
                manual_candidates=manual_candidates,
                analyzed_at=datetime.fromisoformat(result_data.get("analyzed_at")),
            )

            return AnalyzeStatusResponse(
                job_id=job_id,
                status=status,
                started_at=result.get("started_at"),
                completed_at=result.get("completed_at"),
                result=analyze_response,
                error=None,
            )

    elif status == "failed":
        return AnalyzeStatusResponse(
            job_id=job_id,
            status=status,
            started_at=result.get("started_at"),
            completed_at=result.get("completed_at"),
            result=None,
            error=result.get("error"),
        )

    # Status is "analyzing" or unknown
    return AnalyzeStatusResponse(
        job_id=job_id,
        status=status,
        started_at=result.get("started_at"),
        completed_at=None,
        result=None,
        error=None,
    )


def _validate_audio_op_album(
    autotag_service: BeetsAutotagService, library: Library, album_path: str
) -> str:
    """Shared guards for the convert/dedup endpoints: import path configured,
    album path inside the import root, and the folder exists. Returns the
    canonical absolute album path."""
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no import path configured",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_IMPORT_PATH},
        )
    try:
        canonical_album_path = autotag_service.validate_album_path(
            album_path, library.import_path
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.PATH_OUTSIDE_IMPORT},
        )
    if not os.path.isdir(canonical_album_path):
        raise HTTPException(
            status_code=404,
            detail="Album folder not found at the specified path",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.ALBUM_NOT_FOUND},
        )
    return canonical_album_path


@router.post("/convert-audio", response_model=AudioOpJobResponse, status_code=202)
def convert_audio(
    slug: str,
    request: ConvertAudioRequest,
    db: Session = Depends(get_db),
    autotag_service: BeetsAutotagService = Depends(get_autotag_service),
):
    """Convert an album folder's WAV/WMA files to FLAC or MP3 (V0), async.

    Enqueues a Celery task and returns a job id the frontend polls via
    ``/audio-op/{job_id}/status``. An existing target of the same name is never
    overwritten; with ``delete_originals`` set, each source is removed only
    after its target is verified. Concurrent ops on the same album → 409.
    """
    library = get_library_by_slug(db, slug)
    canonical_album_path = _validate_audio_op_album(
        autotag_service, library, request.album_path
    )

    source_ext = wav_flac_service.SOURCE_EXTS[request.source_format]
    if not wav_flac_service.find_audio_files(canonical_album_path, source_ext):
        raise HTTPException(
            status_code=400,
            detail=f"No {request.source_format.upper()} files found in the album folder",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_SOURCE_FILES},
        )

    redis_manager = get_redis_key_manager(settings.redis_url)
    job_id = str(uuid.uuid4())
    if not redis_manager.acquire_audio_op_lock(library.id, canonical_album_path, job_id):
        raise HTTPException(
            status_code=409,
            detail="Another audio operation is already running for this album",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.AUDIO_OP_IN_PROGRESS},
        )

    try:
        # Enqueue as "queued"; the worker flips it to "running" when it actually
        # starts. This gives the UI a real queued→running lifecycle so a burst of
        # converts shows each album's spinner immediately instead of looking hung.
        redis_manager.set_audio_op_status(job_id, status="queued")
        convert_audio_task.delay(
            job_id=job_id,
            library_id=library.id,
            album_path=canonical_album_path,
            source_format=request.source_format,
            target_format=request.target_format,
            delete_originals=request.delete_originals,
        )
    except Exception as e:
        redis_manager.release_audio_op_lock(library.id, canonical_album_path)
        logger.error(f"Failed to dispatch audio convert task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start conversion: {e}")

    label = f"{request.source_format.upper()}→{request.target_format.upper()}"
    return AudioOpJobResponse(
        job_id=job_id,
        album_path=request.album_path,
        status="queued",
        message=f"{label} conversion queued",
    )


@router.post("/dedupe-wav", response_model=AudioOpJobResponse, status_code=202)
def dedupe_wav(
    slug: str,
    request: DedupeWavRequest,
    db: Session = Depends(get_db),
    autotag_service: BeetsAutotagService = Depends(get_autotag_service),
):
    """Delete duplicate WAVs (those with a same-basename FLAC sibling), async.

    Never touches a WAV without a FLAC twin. Enqueues a Celery task; poll
    ``/audio-op/{job_id}/status``. Concurrent ops on the same album → 409.
    """
    library = get_library_by_slug(db, slug)
    canonical_album_path = _validate_audio_op_album(
        autotag_service, library, request.album_path
    )

    if not wav_flac_service.find_duplicate_wavs(canonical_album_path):
        raise HTTPException(
            status_code=400,
            detail="No duplicate WAV files (with a FLAC twin) found",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_DUPLICATE_WAVS},
        )

    redis_manager = get_redis_key_manager(settings.redis_url)
    job_id = str(uuid.uuid4())
    if not redis_manager.acquire_audio_op_lock(library.id, canonical_album_path, job_id):
        raise HTTPException(
            status_code=409,
            detail="Another WAV operation is already running for this album",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.AUDIO_OP_IN_PROGRESS},
        )

    try:
        # Queued until a worker starts it (see convert_audio for the rationale).
        redis_manager.set_audio_op_status(job_id, status="queued")
        remove_duplicate_wavs_task.delay(
            job_id=job_id,
            library_id=library.id,
            album_path=canonical_album_path,
        )
    except Exception as e:
        redis_manager.release_audio_op_lock(library.id, canonical_album_path)
        logger.error(f"Failed to dispatch WAV dedup task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start cleanup: {e}")

    return AudioOpJobResponse(
        job_id=job_id,
        album_path=request.album_path,
        status="queued",
        message="Duplicate-WAV cleanup queued",
    )


@router.get("/audio-op/{job_id}/status", response_model=AudioOpStatusResponse)
def get_audio_op_status(
    slug: str,
    job_id: str,
    db: Session = Depends(get_db),
):
    """Poll the status + result of a WAV convert / dedup job."""
    get_library_by_slug(db, slug)
    redis_manager = get_redis_key_manager(settings.redis_url)
    status_data = redis_manager.get_audio_op_status(job_id)
    if not status_data:
        raise HTTPException(
            status_code=404,
            detail=f"Audio operation job not found: {job_id}",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.AUDIO_OP_NOT_FOUND},
        )
    return AudioOpStatusResponse(
        job_id=job_id,
        status=status_data.get("status", "unknown"),
        started_at=status_data.get("started_at"),
        completed_at=status_data.get("completed_at"),
        result=status_data.get("result"),
        error=status_data.get("error"),
    )


# Maximum number of album paths allowed per cache status request
MAX_CACHE_STATUS_PATHS = 500


@router.get("/cache-status", response_model=CacheStatusResponse)
def get_cache_status(
    slug: str,
    album_paths: List[str] = Query(
        default=[],
        description="Album paths to check cache status for (can be repeated)",
    ),
    db: Session = Depends(get_db),
    autotag_service: BeetsAutotagService = Depends(get_autotag_service),
):
    """Check cache status for multiple album paths.

    Returns the cache status for multiple album paths in a single request.
    Optimized for bulk status checks without returning cached data.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Query Parameters:
        album_paths: Album paths to check (can be repeated). Maximum 500 paths.

    Returns:
        CacheStatusResponse with cache_status map, paths_checked, and paths_cached

    Raises:
        400: Too many paths or invalid path
        404: Library not found
        500: Redis connection failure
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    # Check if library has import path configured
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no import path configured",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_IMPORT_PATH},
        )

    # Return empty response if no paths provided
    if not album_paths:
        return CacheStatusResponse(
            cache_status={},
            paths_checked=0,
            paths_cached=0,
        )

    # Validate path count limit
    if len(album_paths) > MAX_CACHE_STATUS_PATHS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many album paths: maximum {MAX_CACHE_STATUS_PATHS} allowed, received {len(album_paths)}",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.TOO_MANY_PATHS},
        )

    # Validate paths and resolve to canonical paths
    canonical_paths = {}
    for album_path in album_paths:
        # Check for null bytes (security)
        if "\x00" in album_path:
            raise HTTPException(
                status_code=400,
                detail=f"Album path contains invalid characters: {album_path}",
                headers={"X-Error-Code": BeetsAutotagErrorCodes.INVALID_PATH},
            )

        # Validate and resolve the album path
        try:
            canonical_path = autotag_service.validate_album_path(
                album_path, library.import_path
            )
            canonical_paths[album_path] = canonical_path
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
                headers={"X-Error-Code": BeetsAutotagErrorCodes.PATH_OUTSIDE_IMPORT},
            )

    # Perform bulk cache existence check
    try:
        redis_manager = get_redis_key_manager(settings.redis_url)
        # Check cache using canonical paths
        canonical_results = redis_manager.check_beets_album_cache_exists(
            library.id, list(canonical_paths.values())
        )

        # Map results back to original album paths
        cache_status = {}
        for original_path, canonical_path in canonical_paths.items():
            cache_status[original_path] = canonical_results.get(canonical_path, False)

    except Exception as e:
        logger.error(f"Failed to check cache status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check cache status: {str(e)}",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.CACHE_CHECK_ERROR},
        )

    paths_cached = sum(1 for v in cache_status.values() if v)

    return CacheStatusResponse(
        cache_status=cache_status,
        paths_checked=len(cache_status),
        paths_cached=paths_cached,
    )


@router.get("/analyze-queue", response_model=AnalyzeQueueResponse)
def get_analyze_queue(
    slug: str,
    db: Session = Depends(get_db),
):
    """Get the current analysis queue status for a library.

    Returns the queue depth, list of queued album paths with positions,
    and count of active analyses.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Returns:
        AnalyzeQueueResponse with queue depth, items, and active analyses

    Raises:
        404: Library not found
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    redis_manager = get_redis_key_manager(settings.redis_url)

    # Get queue items
    queue_items = redis_manager.get_analysis_queue_items(library.id)
    queued_items = [
        QueuedItem(
            album_path=item["album_path"],
            position=item["position"],
            queued_at=datetime.fromisoformat(item["queued_at"]),
        )
        for item in queue_items
    ]

    # Get active analyses
    active_items_data = redis_manager.get_active_analysis_items(library.id)
    active_items = []
    for item in active_items_data:
        started_at = None
        if item.get("started_at"):
            try:
                started_at = datetime.fromisoformat(item["started_at"])
            except (ValueError, TypeError):
                pass
        active_items.append(
            ActiveItem(
                album_path=item["album_path"],
                job_id=item["job_id"],
                started_at=started_at,
            )
        )

    return AnalyzeQueueResponse(
        queue_depth=len(queued_items),
        active_count=len(active_items),
        max_concurrent=settings.max_concurrent_analyses_per_library,
        queued_items=queued_items,
        active_items=active_items,
    )


def _compute_incoming_stats(album_path: str) -> Optional[dict]:
    """Walk an import folder and return track_count / total_bytes / duration /
    dominant format / avg bitrate across all audio files it contains.

    Uses mutagen so the response includes the same shape as the stats we pull
    from the beets DB for the existing album. Returns None if the folder is
    empty or unreadable. Per-file failures are skipped silently so one bad
    tag doesn't void the comparison.
    """
    from mutagen import File as MutagenFile

    AUDIO_EXT = {".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".wma", ".aiff", ".aif"}

    total_bytes = 0
    total_duration = 0.0
    weighted_bitrate_sum = 0.0
    weighted_bitrate_weight = 0.0
    fmt_counts: Dict[str, int] = {}
    track_count = 0

    try:
        for root, _dirs, files in os.walk(album_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in AUDIO_EXT:
                    continue
                full = os.path.join(root, fname)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                try:
                    audio = MutagenFile(full)
                except Exception:
                    audio = None

                length = 0.0
                bitrate_bps = 0
                fmt = None
                if audio is not None and audio.info is not None:
                    length = float(getattr(audio.info, "length", 0) or 0)
                    bitrate_bps = int(getattr(audio.info, "bitrate", 0) or 0)
                    fmt = type(audio).__name__.upper()
                if not fmt:
                    fmt = ext.lstrip(".").upper() or None

                track_count += 1
                total_bytes += size
                total_duration += length
                if bitrate_bps and length:
                    weighted_bitrate_sum += bitrate_bps * length
                    weighted_bitrate_weight += length
                if fmt:
                    fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1
    except OSError:
        return None

    if track_count == 0:
        return None

    return {
        "track_count": track_count,
        "total_bytes": total_bytes,
        "total_duration_seconds": total_duration,
        "dominant_format": (
            max(fmt_counts.items(), key=lambda kv: kv[1])[0] if fmt_counts else None
        ),
        "avg_bitrate_kbps": (
            int(round(weighted_bitrate_sum / weighted_bitrate_weight / 1000))
            if weighted_bitrate_weight > 0
            else None
        ),
    }


def _collect_album_paths(import_path: str) -> List[str]:
    """Collect all album folder paths from the import tree.

    Args:
        import_path: Root import path for the library.

    Returns:
        List of absolute album folder paths.
    """
    tree_service = ImportTreeService()
    tree = tree_service.build_import_tree(import_path)

    album_paths = []

    def collect_albums(nodes, base_path: str):
        for node in nodes:
            node_path = os.path.join(base_path, node.path) if node.path != node.name else os.path.join(base_path, node.name)
            # Use absolute path
            abs_path = os.path.join(import_path, node.path)
            if node.is_album:
                album_paths.append(abs_path)
            if node.children:
                collect_albums(node.children, base_path)

    collect_albums(tree, import_path)
    return album_paths


@router.post("/analyze-folder", response_model=AnalyzeFolderResponse, status_code=202)
def analyze_folder(
    slug: str,
    request: AnalyzeFolderRequest,
    db: Session = Depends(get_db),
):
    """Bulk enqueue analysis for all albums in the library's import folder.

    Identifies all album folders in the import folder, filters out already-cached
    albums (unless force is True), and enqueues each remaining path for analysis.
    Returns a summary of how many albums were enqueued, dispatched immediately,
    and skipped.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Request Body:
        force: If True, re-analyze albums even if cached results exist (default: False)

    Returns:
        AnalyzeFolderResponse with counts of enqueued, dispatched, cached, and total

    Raises:
        400: Library has no import path configured
        404: Library not found
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    # Check if library has import path configured
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no import path configured",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_IMPORT_PATH},
        )

    redis_manager = get_redis_key_manager(settings.redis_url)
    concurrency_cap = settings.max_concurrent_analyses_per_library

    # Collect all album paths from the import folder
    try:
        album_paths = _collect_album_paths(library.import_path)
    except Exception as e:
        logger.error(f"Failed to collect album paths for library {slug}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scan import folder: {str(e)}",
        )

    total = len(album_paths)
    enqueued = 0
    dispatched = 0
    already_cached = 0
    already_queued = 0

    for album_path in album_paths:
        # Check if already in queue or active
        is_queued, queue_pos, is_active = redis_manager.is_album_in_queue_or_active(
            library.id, album_path
        )

        if is_queued or is_active:
            already_queued += 1
            continue

        # Check cache unless forcing re-analysis
        if not request.force:
            cached_result = redis_manager.get_beets_album_result(library.id, album_path)
            if cached_result is not None:
                already_cached += 1
                continue

        # If force, invalidate the cache
        if request.force:
            redis_manager.invalidate_beets_album_result(library.id, album_path)

        # Check if we can dispatch immediately
        active_count = redis_manager.get_active_analysis_count(library.id)

        if active_count < concurrency_cap:
            # Dispatch immediately
            job_id = str(uuid.uuid4())
            try:
                redis_manager.register_active_analysis(library.id, job_id, album_path)
                redis_manager.set_beets_analysis_result(
                    job_id,
                    status="analyzing",
                    started_at=datetime.now(timezone.utc),
                )
                analyze_album_task.delay(
                    library_id=library.id,
                    album_path=album_path,
                    job_id=job_id,
                )
                dispatched += 1
            except Exception as e:
                # Dispatch failed - unregister and try to enqueue instead
                redis_manager.unregister_active_analysis(library.id, job_id)
                logger.warning(f"Failed to dispatch analysis for {album_path}, enqueueing: {e}")
                redis_manager.enqueue_album_analysis(library.id, album_path)
                enqueued += 1
        else:
            # At capacity - enqueue
            redis_manager.enqueue_album_analysis(library.id, album_path)
            enqueued += 1

    message = f"Enqueued {enqueued} albums for analysis, {dispatched} dispatched immediately"
    if already_cached > 0:
        message += f", {already_cached} already cached"
    if already_queued > 0:
        message += f", {already_queued} already in queue"

    return AnalyzeFolderResponse(
        enqueued=enqueued,
        dispatched=dispatched,
        already_cached=already_cached,
        already_queued=already_queued,
        total=total,
        message=message,
    )


@router.post("/manual-candidate", response_model=ManualCandidateResponse)
def add_manual_candidate(
    slug: str,
    request: ManualCandidateRequest,
    db: Session = Depends(get_db),
    autotag_service: BeetsAutotagService = Depends(get_autotag_service),
):
    """Resolve an external service link or MusicBrainz ID to a candidate album match.

    Accepts a link from a supported provider (Deezer, Spotify, Discogs, or MusicBrainz)
    and uses the corresponding beets plugin to fetch album metadata. Returns a structured
    candidate that can be used alongside automatically discovered candidates.
    The candidate is stored in the server-side cache for the specified album.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Request Body:
        album_path: Path to the album folder for metadata comparison context
        link: External service URL or MusicBrainz release ID

    Returns:
        ManualCandidateResponse with the resolved candidate and provider name

    Raises:
        400: Invalid link format, invalid album path, or path outside import folder
        404: Library not found, album not found, or release not found on provider
        503: Plugin not available or provider API error
        408: Resolution timeout
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    # Check if library has import path configured
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail="Library has no import path configured",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.NO_IMPORT_PATH},
        )

    # Validate the album path (security check)
    try:
        canonical_album_path = autotag_service.validate_album_path(
            request.album_path, library.import_path
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.PATH_OUTSIDE_IMPORT},
        )

    # Check if album folder exists
    if not os.path.isdir(canonical_album_path):
        raise HTTPException(
            status_code=404,
            detail="Album folder not found at the specified path",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.ALBUM_NOT_FOUND},
        )

    # Detect provider from link
    provider = detect_provider(request.link)
    if provider is None:
        raise HTTPException(
            status_code=400,
            detail="Link must be a valid URL from Deezer, Spotify, Discogs, MusicBrainz, "
                   "or a MusicBrainz release UUID",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.INVALID_LINK},
        )

    # Extract ID from link
    source_id = extract_id_from_link(request.link, provider)
    if source_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Could not extract ID from {provider} link",
            headers={"X-Error-Code": BeetsAutotagErrorCodes.INVALID_LINK},
        )

    # Get timeout from environment
    timeout = int(os.environ.get("BEETS_MANUAL_RESOLUTION_TIMEOUT_SECONDS",
                                  str(DEFAULT_MANUAL_RESOLUTION_TIMEOUT)))

    # Resolve the manual candidate using beets
    try:
        candidate = resolve_manual_candidate(
            autotag_service=autotag_service,
            album_path=canonical_album_path,
            provider=provider,
            source_id=source_id,
            config_path=library.config_path,
            timeout=timeout,
        )
    except PluginNotAvailableError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.PLUGIN_NOT_AVAILABLE},
        )
    except ReleaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.RELEASE_NOT_FOUND},
        )
    except ProviderError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.PROVIDER_ERROR},
        )
    except ResolutionTimeoutError as e:
        raise HTTPException(
            status_code=408,
            detail=str(e),
            headers={"X-Error-Code": BeetsAutotagErrorCodes.RESOLUTION_TIMEOUT},
        )

    # Store manual candidate in cache
    redis_manager = get_redis_key_manager(settings.redis_url)
    store_manual_candidate_in_cache(
        redis_manager=redis_manager,
        library_id=library.id,
        album_path=canonical_album_path,
        candidate=candidate,
        provider=provider,
    )

    logger.info(
        f"Resolved manual candidate from {provider} for library '{slug}', "
        f"album: {request.album_path}, source_id: {source_id}"
    )

    return ManualCandidateResponse(
        candidate=candidate,
        provider=provider,
    )


@router.get("/search-candidates", response_model=SearchCandidatesResponse)
def search_candidates(
    slug: str,
    q: str = Query(..., min_length=1, max_length=500, description="Free-text search term"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    per_page: int = Query(
        5, ge=1, le=20, alias="perPage", description="Results per provider per page"
    ),
    providers: Optional[str] = Query(
        None,
        description=(
            "Comma-separated subset of providers to search "
            "(e.g. 'deezer,spotify'). Default: all."
        ),
    ),
    artist: Optional[str] = Query(
        None,
        max_length=500,
        description=(
            "Structured artist term. When set (with/without `album`), providers "
            "are queried with their field-search syntax instead of free-text `q`, "
            "narrowing results."
        ),
    ),
    album: Optional[str] = Query(
        None,
        max_length=500,
        description="Structured album/release-title term (see `artist`).",
    ),
    expected_tracks: Optional[int] = Query(
        None,
        ge=0,
        alias="expectedTracks",
        description=(
            "Track count of the local folder being imported. Hits whose track "
            "count matches are ranked to the top of their provider group."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Search active metadata providers for a free-text term at once.

    Queries MusicBrainz, Spotify, Deezer, and Discogs concurrently, gated by the
    plugins enabled in the library's config (and, for Discogs, by the presence of
    an access token). Each result carries a canonical provider URL that the user
    can open in a new tab or feed straight into the manual-candidate endpoint to
    resolve as a candidate — so no separate resolution path is needed here.

    Path Parameters:
        slug: Library slug.

    Query Parameters:
        q: Free-text search term (album, artist, or both).
        page: 1-indexed page number (default 1).
        perPage: Results per provider per page (default 5, max 20).
        providers: Comma-separated provider subset; the response then contains
            only those groups. Omit to search all providers.
        artist: Optional structured artist term; when set, each provider uses
            its field-search syntax instead of free-text `q`.
        album: Optional structured album/release-title term (see `artist`).
        expectedTracks: Local folder's track count; matching hits rank first.

    Returns:
        SearchCandidatesResponse with one group per requested provider, in
        display order. Unavailable providers come back with available=false and
        a reason for the UI to show on hover; a single provider failing never
        fails the call.

    Raises:
        404: Library not found.
        422: Unknown provider name in `providers`.
    """
    provider_filter: Optional[List[str]] = None
    if providers is not None:
        provider_filter = [p.strip().lower() for p in providers.split(",") if p.strip()]
        unknown = sorted(set(provider_filter) - set(PROVIDERS))
        if unknown or not provider_filter:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unknown provider(s): {', '.join(unknown) or '(empty)'}. "
                    f"Valid values: {', '.join(PROVIDERS)}."
                ),
            )

    library = get_library_by_slug(db, slug)

    return search_all_providers(
        config_path=library.config_path,
        query=q,
        page=page,
        per_page=per_page,
        timeout=DEFAULT_SEARCH_TIMEOUT,
        providers=provider_filter,
        artist=artist,
        album=album,
        expected_tracks=expected_tracks,
    )


def store_manual_candidate_in_cache(
    redis_manager,
    library_id: int,
    album_path: str,
    candidate: Candidate,
    provider: str,
) -> None:
    """Store a manual candidate in the Redis cache alongside automatic candidates.

    Implements provider deduplication - replaces any existing manual candidate
    from the same provider.

    Args:
        redis_manager: The Redis key manager instance.
        library_id: The library ID.
        album_path: Absolute path to the album folder.
        candidate: The manual candidate to store.
        provider: The provider name (for deduplication).
    """
    # Get existing cached result
    cached_result = redis_manager.get_beets_album_result(library_id, album_path)

    if cached_result is None:
        # No existing cache - create minimal structure with just manual candidate
        cached_result = {
            "album_path": album_path,
            "local_album": {},
            "candidates": [],
            "manual_candidates": [],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    # Get existing manual candidates
    manual_candidates = cached_result.get("manual_candidates", [])

    # Remove any existing candidate from the same provider (deduplication)
    manual_candidates = [
        mc for mc in manual_candidates
        if mc.get("source", "").lower() != provider_to_source_name(provider).lower()
    ]

    # Add the new manual candidate
    candidate_dict = {
        "source": candidate.source,
        "source_id": candidate.source_id,
        "similarity": candidate.similarity,
        "artist": candidate.artist,
        "album": candidate.album,
        "year": candidate.year,
        "label": candidate.label,
        "country": candidate.country,
        "media": candidate.media,
        "tracks": [
            {
                "index": t.index,
                "title": t.title,
                "length": t.length,
                "local_title": t.local_title,
                "local_path": t.local_path,
                "changes": [
                    {"field": c.field, "from_value": c.from_value, "to_value": c.to_value}
                    for c in t.changes
                ],
            }
            for t in candidate.tracks
        ],
        "changes": [
            {"field": c.field, "from_value": c.from_value, "to_value": c.to_value}
            for c in candidate.changes
        ],
        "track_changes": [
            {"index": tc.index, "local_title": tc.local_title, "candidate_title": tc.candidate_title}
            for tc in candidate.track_changes
        ],
        "is_manual": True,
    }
    manual_candidates.append(candidate_dict)

    # Update the cached result
    cached_result["manual_candidates"] = manual_candidates

    # Store back in Redis
    redis_manager.set_beets_album_result(library_id, album_path, cached_result)


def provider_to_source_name(provider: str) -> str:
    """Convert a provider identifier to the display source name.

    Args:
        provider: Provider identifier ('deezer', 'spotify', 'discogs', 'musicbrainz').

    Returns:
        Display name for the source.
    """
    mapping = {
        "deezer": "Deezer",
        "spotify": "Spotify",
        "discogs": "Discogs",
        "musicbrainz": "MusicBrainz",
    }
    return mapping.get(provider, provider.title())


# --- Beets Import Endpoints ---


def get_import_service() -> BeetsImportService:
    """Dependency to get the beets import service."""
    return get_beets_import_service()


@router.post("/import", response_model=ImportJobResponse, status_code=201)
def start_import(
    slug: str,
    request: ImportAlbumRequest,
    db: Session = Depends(get_db),
    import_service: BeetsImportService = Depends(get_import_service),
):
    """Start an import job for an album with a selected candidate.

    Creates a Celery task to import an album into the beets library
    using the selected candidate's metadata. Returns immediately with
    a job ID that can be used to poll for status.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Request Body:
        albumPath: Path to the album folder
        candidate: Selected candidate metadata to apply

    Returns:
        ImportJobResponse with jobId, status, and message

    Raises:
        400: Invalid album path, path outside import folder, or no audio files
        404: Library not found or no import path configured
        409: Import already in progress for this album
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    # Check if library has import path configured
    if not library.import_path:
        raise HTTPException(
            status_code=404,
            detail="Library has no import path configured",
            headers={"X-Error-Code": ImportErrorCodes.NO_IMPORT_PATH},
        )

    # Validate the album path
    try:
        canonical_album_path = import_service.validate_album_path(
            request.album_path, library.import_path
        )
    except BeetsImportError as e:
        raise HTTPException(
            status_code=400,
            detail=e.message,
            headers={"X-Error-Code": e.code},
        )

    # Check the beets DB for an existing album with the same MB ID or the same
    # albumartist+title. Behaviour depends on replace_existing:
    #   - false (default): return 409 so the frontend can prompt for upgrade
    #   - true: delete the existing DB entry up front so the import task can
    #     insert a clean replacement row (files on disk are overwritten when
    #     the destination path matches)
    # The duplicate check keys off the candidate's MB id / artist+album. In
    # as-is mode there is no candidate yet (metadata is read from the files in
    # the task), so there's nothing to match on here — skip it.
    if (
        not request.import_as_is
        and library.database_path
        and os.path.exists(library.database_path)
    ):
        try:
            library_service = BeetsLibraryService()
            existing = library_service.find_existing_album(
                library.database_path,
                mb_albumid=request.candidate.source_id
                if request.candidate.source.lower() == "musicbrainz"
                else None,
                albumartist=request.candidate.artist,
                album=request.candidate.album,
            )
        except Exception as e:
            # A DB-level error here shouldn't block imports on a healthy library.
            # Log and continue without the duplicate check.
            logger.warning(
                f"Existing-album lookup failed for library {library.id}: {e}"
            )
            existing = None
        if existing and not request.replace_existing:
            # Best-effort stats enrichment: failures must not block the 409 —
            # the dialog falls back to the legacy name-only display.
            try:
                existing["stats"] = library_service.compute_album_stats(
                    library.database_path,
                    existing["album_id"],
                    library_root=library.library_path,
                )
            except Exception as stats_exc:
                logger.warning(
                    f"Existing-album stats failed for library {library.id}: {stats_exc}"
                )

            incoming_stats = None
            try:
                incoming_stats = _compute_incoming_stats(canonical_album_path)
            except Exception as inc_exc:
                logger.warning(
                    f"Incoming stats failed for {canonical_album_path}: {inc_exc}"
                )

            info = ExistingAlbumInfo(**existing)
            incoming_info = IncomingAlbumInfo(stats=incoming_stats)
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        f"Album already in library: {info.artist} — {info.album}"
                    ),
                    "error_code": ImportErrorCodes.ALBUM_ALREADY_EXISTS,
                    "existing": info.model_dump(by_alias=True),
                    "incoming": incoming_info.model_dump(by_alias=True),
                },
                headers={"X-Error-Code": ImportErrorCodes.ALBUM_ALREADY_EXISTS},
            )
        if existing and request.replace_existing:
            try:
                library_service.delete_album(library.database_path, existing["album_id"])
                logger.info(
                    f"Removed existing beets album {existing['album_id']} in "
                    f"library {library.id} to make room for replacement import"
                )
            except Exception as e:
                logger.error(
                    f"Failed to delete existing album {existing['album_id']} "
                    f"before replacement import: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to remove existing album before upgrade",
                    headers={"X-Error-Code": "REPLACE_FAILED"},
                )

    # Convert candidate to dict for serialization. None in as-is mode — the
    # task reads metadata from the files' existing tags instead.
    candidate_dict = (
        None
        if request.import_as_is
        else {
            "source": request.candidate.source,
            "source_id": request.candidate.source_id,
            "artist": request.candidate.artist,
            "album": request.candidate.album,
            "year": request.candidate.year,
            "cover_url": request.candidate.cover_url,
            "tracks": [
                {
                    "index": t.index,
                    "title": t.title,
                    "length": t.length,
                    "disc": t.disc,
                    "local_path": t.local_path,
                }
                for t in request.candidate.tracks
            ],
        }
    )

    # Start the import job
    try:
        job_id, message = import_service.start_import(
            library_id=library.id,
            album_path=canonical_album_path,
            candidate=candidate_dict,
        )
    except BeetsImportError as e:
        if e.code == "IMPORT_IN_PROGRESS":
            raise HTTPException(
                status_code=409,
                detail=e.message,
                headers={"X-Error-Code": e.code},
            )
        raise HTTPException(
            status_code=400,
            detail=e.message,
            headers={"X-Error-Code": e.code},
        )

    # Dispatch the Celery task
    import json
    candidate_json = json.dumps(candidate_dict)

    import_album_task.delay(
        job_id=job_id,
        library_id=library.id,
        album_path=canonical_album_path,
        candidate_json=candidate_json,
        import_as_is=request.import_as_is,
    )

    logger.info(
        f"Started import job {job_id} for library '{slug}', "
        f"album: {request.album_path}"
    )

    return ImportJobResponse(
        job_id=job_id,
        status="pending",
        album_path=canonical_album_path,
        message=message,
    )


@router.get("/import/{job_id}/status", response_model=ImportJobStatusResponse)
def get_import_status(
    slug: str,
    job_id: str,
    db: Session = Depends(get_db),
    import_service: BeetsImportService = Depends(get_import_service),
):
    """Get the status of an import job.

    Used for polling to track import progress. Returns the current status
    along with timestamps and result/error information.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)
        job_id: UUID of the import job

    Returns:
        ImportJobStatusResponse with current job state

    Raises:
        404: Library or job not found
    """
    # Look up the library (validates slug)
    library = get_library_by_slug(db, slug)

    # Get job status
    job_status = import_service.get_job_status(job_id)
    if not job_status:
        raise HTTPException(
            status_code=404,
            detail="Import job not found",
            headers={"X-Error-Code": ImportErrorCodes.JOB_NOT_FOUND},
        )

    # Verify job belongs to this library
    if job_status.get("library_id") != library.id:
        raise HTTPException(
            status_code=404,
            detail="Import job not found",
            headers={"X-Error-Code": ImportErrorCodes.JOB_NOT_FOUND},
        )

    # Build response
    error = None
    if job_status.get("error"):
        error = ImportJobError(
            code=job_status["error"].get("code", "UNKNOWN_ERROR"),
            message=job_status["error"].get("message", "Unknown error"),
        )

    return ImportJobStatusResponse(
        job_id=job_id,
        status=job_status.get("status", "unknown"),
        album_path=job_status.get("album_path", ""),
        started_at=job_status.get("started_at"),
        completed_at=job_status.get("completed_at"),
        destination_path=job_status.get("destination_path"),
        error=error,
    )


@router.get("/import-status", response_model=BulkImportStatusResponse)
def get_bulk_import_status(
    slug: str,
    db: Session = Depends(get_db),
    import_service: BeetsImportService = Depends(get_import_service),
):
    """Get the import status for all albums in the library's import folder.

    Returns a map of album paths to their import state (pending, in_progress,
    or done) along with counts and the library's import mode.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Returns:
        BulkImportStatusResponse with albums map, counts, and import mode

    Raises:
        404: Library not found or no import path configured
    """
    # Look up the library
    library = get_library_by_slug(db, slug)

    # Check if library has import path configured
    if not library.import_path:
        raise HTTPException(
            status_code=404,
            detail="Library has no import path configured",
            headers={"X-Error-Code": ImportErrorCodes.NO_IMPORT_PATH},
        )

    # Get bulk status
    bulk_status = import_service.get_bulk_status(
        library_id=library.id,
        import_path=library.import_path,
        config_path=library.config_path,
    )

    # Convert to response format
    albums = {}
    for album_path, state_data in bulk_status.get("albums", {}).items():
        state = state_data.get("state", "pending")
        # Map status values to state values
        if state == "in_progress":
            state = "in_progress"
        elif state == "completed":
            state = "done"

        albums[album_path] = AlbumImportState(
            state=state if state in ("pending", "in_progress", "done") else "pending",
            job_id=state_data.get("job_id"),
            started_at=state_data.get("started_at"),
            completed_at=state_data.get("completed_at"),
            destination_path=state_data.get("destination_path"),
        )

    counts = bulk_status.get("counts", {})
    import_mode = bulk_status.get("import_mode", "copy")

    return BulkImportStatusResponse(
        albums=albums,
        counts=ImportStatusCounts(
            pending=counts.get("pending", 0),
            in_progress=counts.get("in_progress", 0),
            done=counts.get("done", 0),
        ),
        import_mode=import_mode,
    )


# --- Library Settings Router ---

library_settings_router = APIRouter(
    prefix="/libraries/{slug}/settings",
    tags=["library-settings"]
)


def _get_auto_analyze_setting_key(library_id: int) -> str:
    """Get the user_settings key for auto-analyze setting."""
    return f"auto_analyze:{library_id}"


def _get_auto_analyze_setting(db: Session, library_id: int) -> bool:
    """Get the auto-analyze-after-scan setting for a library.

    Args:
        db: Database session.
        library_id: The library ID.

    Returns:
        True if auto-analyze is enabled, False otherwise (default).
    """
    from app.models.user_settings import UserSettings

    settings = db.query(UserSettings).first()
    if not settings:
        return False

    key = _get_auto_analyze_setting_key(library_id)
    auto_analyze_settings = settings.preferences.get("auto_analyze_settings", {})
    return auto_analyze_settings.get(str(library_id), False)


def _set_auto_analyze_setting(db: Session, library_id: int, enabled: bool) -> None:
    """Set the auto-analyze-after-scan setting for a library.

    Args:
        db: Database session.
        library_id: The library ID.
        enabled: Whether to enable auto-analyze.
    """
    from app.models.user_settings import UserSettings

    settings = db.query(UserSettings).first()
    if not settings:
        # Create default settings
        settings = UserSettings(
            preferences={"auto_analyze_settings": {str(library_id): enabled}},
        )
        db.add(settings)
    else:
        # Update existing settings
        preferences = settings.preferences.copy()
        auto_analyze_settings = preferences.get("auto_analyze_settings", {})
        auto_analyze_settings[str(library_id)] = enabled
        preferences["auto_analyze_settings"] = auto_analyze_settings
        settings.preferences = preferences

    db.commit()


@library_settings_router.get("/auto-analyze", response_model=AutoAnalyzeSettingResponse)
def get_auto_analyze_setting(
    slug: str,
    db: Session = Depends(get_db),
):
    """Get the auto-analyze-after-scan setting for a library.

    Returns the current value of the auto_analyze_after_scan setting,
    which controls whether albums are automatically enqueued for analysis
    when a library scan completes.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Returns:
        AutoAnalyzeSettingResponse with the current setting value

    Raises:
        404: Library not found
    """
    library = get_library_by_slug(db, slug)

    enabled = _get_auto_analyze_setting(db, library.id)

    return AutoAnalyzeSettingResponse(
        auto_analyze_after_scan=enabled,
    )


@library_settings_router.put("/auto-analyze", response_model=AutoAnalyzeSettingResponse)
def set_auto_analyze_setting(
    slug: str,
    request: AutoAnalyzeSettingRequest,
    db: Session = Depends(get_db),
):
    """Set the auto-analyze-after-scan setting for a library.

    Updates the auto_analyze_after_scan setting for the library. When enabled,
    all newly discovered albums will be automatically enqueued for analysis
    after a scan completes.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Request Body:
        autoAnalyzeAfterScan: Whether to auto-analyze albums after scan

    Returns:
        AutoAnalyzeSettingResponse with confirmation message

    Raises:
        404: Library not found
        422: Validation error
    """
    library = get_library_by_slug(db, slug)

    _set_auto_analyze_setting(db, library.id, request.auto_analyze_after_scan)

    message = "Auto-analyze after scan enabled" if request.auto_analyze_after_scan else "Auto-analyze after scan disabled"

    return AutoAnalyzeSettingResponse(
        auto_analyze_after_scan=request.auto_analyze_after_scan,
        message=message,
    )


# ---------------------------------------------------------------------------
# Import drop-zone cleanup settings (per-library override over global defaults)
# ---------------------------------------------------------------------------


def _get_import_cleanup_override(db: Session, library_id: int) -> dict:
    """Return the stored per-library cleanup override, or ``{}`` if none."""
    from app.models.user_settings import UserSettings
    from app.services.import_cleanup import PREF_LIBRARY_KEY

    settings = db.query(UserSettings).first()
    if not settings:
        return {}
    per_library = settings.preferences.get(PREF_LIBRARY_KEY)
    if not isinstance(per_library, dict):
        return {}
    override = per_library.get(str(library_id))
    return override if isinstance(override, dict) else {}


def _set_import_cleanup_override(
    db: Session, library_id: int, override: dict
) -> None:
    """Persist (or clear) the per-library cleanup override.

    Mirrors :func:`_set_auto_analyze_setting`: it reads/writes the single
    ``UserSettings`` row, replacing this library's override block. An empty
    ``override`` removes the entry so the library re-inherits the defaults.
    """
    from app.models.user_settings import UserSettings
    from app.services.import_cleanup import PREF_LIBRARY_KEY

    settings = db.query(UserSettings).first()
    if not settings:
        settings = UserSettings(
            preferences={PREF_LIBRARY_KEY: {str(library_id): override}}
        )
        db.add(settings)
    else:
        preferences = settings.preferences.copy()
        existing = preferences.get(PREF_LIBRARY_KEY)
        per_library = dict(existing) if isinstance(existing, dict) else {}
        if override:
            per_library[str(library_id)] = override
        else:
            per_library.pop(str(library_id), None)
        preferences[PREF_LIBRARY_KEY] = per_library
        settings.preferences = preferences

    db.commit()


def _import_cleanup_response(
    db: Session, library_id: int, message: Optional[str] = None
) -> "ImportCleanupSettingResponse":
    """Build the effective-config response for a library."""
    from app.models.user_settings import UserSettings
    from app.services.import_cleanup import resolve_import_cleanup_config

    settings = db.query(UserSettings).first()
    preferences = settings.preferences if settings else None
    config = resolve_import_cleanup_config(preferences, library_id)

    return ImportCleanupSettingResponse(
        enabled=config.enabled,
        sidecar_extensions=sorted(config.sidecar_extensions),
        delete_redundant_images=config.delete_redundant_images,
        promote_orphan_cover=config.promote_orphan_cover,
        overridden=bool(_get_import_cleanup_override(db, library_id)),
        message=message,
    )


@library_settings_router.get(
    "/import-cleanup", response_model=ImportCleanupSettingResponse
)
def get_import_cleanup_setting(
    slug: str,
    db: Session = Depends(get_db),
):
    """Get the effective import drop-zone cleanup config for a library.

    Returns the resolved config (baked-in defaults ← global ← this library's
    override) plus whether an override is stored.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Raises:
        404: Library not found
    """
    library = get_library_by_slug(db, slug)
    return _import_cleanup_response(db, library.id)


@library_settings_router.put(
    "/import-cleanup", response_model=ImportCleanupSettingResponse
)
def set_import_cleanup_setting(
    slug: str,
    request: ImportCleanupSettingRequest,
    db: Session = Depends(get_db),
):
    """Set the per-library import drop-zone cleanup override.

    Only the fields present in the request are stored; omitted fields keep
    inheriting the global / default value. Sending an all-empty body clears the
    override so the library re-inherits the defaults.

    Path Parameters:
        slug: Library slug (lowercase alphanumeric + hyphens)

    Raises:
        404: Library not found
        422: Validation error
    """
    from app.services.import_cleanup import _normalize_extensions

    library = get_library_by_slug(db, slug)

    override: dict = {}
    if request.enabled is not None:
        override["enabled"] = request.enabled
    if request.sidecar_extensions is not None:
        # Persist a normalized, de-duplicated list so the stored value matches
        # what the resolver will actually match against.
        override["sidecar_extensions"] = sorted(
            _normalize_extensions(request.sidecar_extensions)
        )
    if request.delete_redundant_images is not None:
        override["delete_redundant_images"] = request.delete_redundant_images
    if request.promote_orphan_cover is not None:
        override["promote_orphan_cover"] = request.promote_orphan_cover

    _set_import_cleanup_override(db, library.id, override)

    message = (
        "Import cleanup override cleared (inheriting defaults)"
        if not override
        else "Import cleanup settings updated"
    )
    return _import_cleanup_response(db, library.id, message=message)
