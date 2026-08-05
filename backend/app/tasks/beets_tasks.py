"""Celery tasks for beets operations (import, analysis, etc.)."""

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import traceback
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import yaml
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.config import get_settings
from app.database import SessionLocal
from app.models.enums import TaskStatus, TaskType
from app.models.library import Library
from app.services.beets_autotag_service import (
    BeetsAutotagService,
    AnalysisTimeoutError,
    BeetsAnalysisError,
    MusicBrainzError,
    get_beets_autotag_service,
)
from app.services.audio_discovery import find_audio_files, infer_disc_number
from app.services.beets_library_service import BeetsLibraryService, TrackData
from app.services.release_parts import (
    ReleasePart,
    disambiguate_part_albums,
    split_release_parts,
)
from app.services.cover_art import ensure_album_cover, get_art_filename  # noqa: F401 - re-exported
from app.services.scanner.folder_name import parse_album_folder_name
from app.services.redis_keys import get_redis_key_manager, RedisKeyManager
from app.services.task_events import get_task_event_service
from app.services.tag_writer import get_tag_writer_registry
from app.services.tag_writer.mappings import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)
settings = get_settings()


def get_db():
    """Get a database session."""
    return SessionLocal()


def get_redis_manager() -> RedisKeyManager:
    """Get a Redis key manager instance."""
    return get_redis_key_manager(settings.redis_url)


def drain_analysis_queue(library_id: int, redis_manager: Optional[RedisKeyManager] = None) -> bool:
    """Drain the analysis queue by dispatching the next pending album.

    This function is called after an analysis completes (success or failure)
    to dispatch the next album in the queue if capacity allows.

    Uses the atomic dequeue-and-dispatch Lua script to prevent race conditions.

    Args:
        library_id: The library ID.
        redis_manager: Optional Redis manager (creates one if not provided).

    Returns:
        True if a new analysis was dispatched, False otherwise.
    """
    if redis_manager is None:
        redis_manager = get_redis_manager()

    concurrency_cap = settings.max_concurrent_analyses_per_library

    # Generate a new job_id for the next analysis
    job_id = str(uuid.uuid4())

    # Attempt to atomically dequeue and register
    dequeued = redis_manager.dequeue_next_album(library_id, concurrency_cap, job_id)

    if dequeued is None:
        # Queue is empty or at capacity
        return False

    album_path = dequeued.get("album_path")
    if not album_path:
        logger.error(f"Dequeued item missing album_path: {dequeued}")
        return False

    # Dispatch the task
    try:
        # Set initial status in Redis before task starts
        redis_manager.set_beets_analysis_result(
            job_id,
            status="analyzing",
            started_at=datetime.now(timezone.utc),
        )

        analyze_album_task.delay(
            library_id=library_id,
            album_path=album_path,
            job_id=job_id,
        )

        logger.info(
            f"Drained analysis queue: dispatched job {job_id} for library {library_id}, "
            f"album: {album_path}"
        )
        return True

    except Exception as e:
        # Dispatch failed - unregister the active analysis
        logger.error(f"Failed to dispatch analysis task from queue drain: {e}")
        redis_manager.unregister_active_analysis(library_id, job_id)
        return False


@celery_app.task(bind=True)
def analyze_album_task(
    self,
    library_id: int,
    album_path: str,
    job_id: str,
) -> Dict[str, Any]:
    """Celery task to analyze an album using beets autotag.

    This task runs the beets analysis in the background and stores results in Redis.

    Args:
        library_id: The library ID.
        album_path: Absolute path to the album folder.
        job_id: Unique job ID for tracking progress.

    Returns:
        Dict with analysis results or error information.
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
            error = {"error": "Library not found"}
            redis_manager.set_beets_analysis_result(
                job_id,
                status="failed",
                error=error,
            )
            return {"status": "failed", "error": error}

        logger.info(
            f"Starting beets analysis task for library {library.slug}, "
            f"album: {album_path}, job_id: {job_id}"
        )

        # Extract album folder name for description
        album_folder_name = album_path.split("/")[-1] if album_path else "Unknown"

        # Record task start for activity monitor
        activity_event_id = task_event_service.record_start(
            task_type="analysis",
            library_id=library_id,
            library_slug=library.slug,
            description=f"Album: {album_folder_name}",
            metadata={"job_id": job_id, "album_path": album_path},
        )

        # Set initial progress
        redis_manager.set_beets_analysis_result(
            job_id,
            status="analyzing",
            started_at=datetime.now(timezone.utc),
        )

        # Get timeout from settings
        timeout = int(settings.beets_analysis_timeout_seconds if hasattr(settings, 'beets_analysis_timeout_seconds') else 30)
        autotag_service = get_beets_autotag_service(timeout=timeout)

        # Run the analysis
        local_album, candidates, analyzed_at, augmentation_degraded = (
            autotag_service.analyze_album(
                library_slug=library.slug,
                album_path=album_path,
                config_path=library.config_path,
            )
        )

        # Convert to serializable format
        result = {
            "album_path": album_path,
            "local_album": {
                "path": local_album.path,
                "artist": local_album.artist,
                "album": local_album.album,
                "metadata_source": local_album.metadata_source,
                "dominant_format": local_album.dominant_format,
                "has_wav": local_album.has_wav,
                "has_flac": local_album.has_flac,
                "duplicate_wav_count": local_album.duplicate_wav_count,
                "has_wma": local_album.has_wma,
                "wma_recommended_target": local_album.wma_recommended_target,
                "tracks": [
                    {
                        "path": track.path,
                        "title": track.title,
                        "track_num": track.track_num,
                        "length": track.length,
                        "disc": track.disc,
                    }
                    for track in local_album.tracks
                ],
            },
            "candidates": [
                {
                    "source": c.source,
                    "source_id": c.source_id,
                    "similarity": c.similarity,
                    "artist": c.artist,
                    "album": c.album,
                    "year": c.year,
                    "label": c.label,
                    "country": c.country,
                    "media": c.media,
                    "tracks": [
                        {
                            "index": t.index,
                            "disc": t.disc,
                            "title": t.title,
                            "length": t.length,
                            "local_title": t.local_title,
                            "local_path": t.local_path,
                            "changes": t.changes,
                        }
                        for t in c.tracks
                    ],
                    "changes": c.changes,
                    "track_changes": c.track_changes,
                }
                for c in candidates
            ],
            "analyzed_at": analyzed_at.isoformat(),
        }

        # Store result in Redis (by job_id for status polling)
        redis_manager.set_beets_analysis_result(
            job_id,
            status="completed",
            result=result,
            completed_at=datetime.now(timezone.utc),
        )

        # Also cache by album path so future requests for the same album are
        # instant — but only when the provider augmentation actually ran. A
        # degraded run (provider search/resolve outage or timeout) can miss
        # every real candidate; caching it for 7 days pins that empty answer
        # to the album until a manual force-reanalyze (seen with 500-track
        # audiobooks resolved against the old 15s timeout). The job result
        # above still serves this run; the next analyze request retries fresh.
        if augmentation_degraded:
            logger.warning(
                f"Provider augmentation degraded for job {job_id}; "
                f"skipping 7-day album-path cache for: {album_path}"
            )
        else:
            redis_manager.set_beets_album_result(
                library_id=library_id,
                album_path=album_path,
                result=result,
                ttl_seconds=86400 * 7,  # 7 days
            )

        logger.info(
            f"Beets analysis completed for job {job_id}: "
            f"found {len(candidates)} candidates"
        )

        # Record completion for activity monitor
        if activity_event_id:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed",
                metadata={
                    "job_id": job_id,
                    "candidates_found": len(candidates),
                },
            )

        return {
            "status": "completed",
            "job_id": job_id,
            "candidates_found": len(candidates),
        }

    except FileNotFoundError as e:
        error_msg = str(e)
        logger.error(f"Beets analysis failed (FileNotFoundError) for job {job_id}: {e}")
        error = {"code": "NOT_FOUND", "message": error_msg}
        redis_manager.set_beets_analysis_result(
            job_id,
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
        # Record failure for activity monitor
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"error": error},
                )
            except Exception as activity_error:
                logger.error(f"Failed to record activity completion: {activity_error}")
        return {"status": "failed", "error": error}

    except AnalysisTimeoutError as e:
        logger.error(f"Beets analysis timed out for job {job_id}: {e}")
        error = {"code": "TIMEOUT", "message": str(e)}
        redis_manager.set_beets_analysis_result(
            job_id,
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
        # Record failure for activity monitor
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"error": error},
                )
            except Exception as activity_error:
                logger.error(f"Failed to record activity completion: {activity_error}")
        return {"status": "failed", "error": error}

    except MusicBrainzError as e:
        logger.error(f"MusicBrainz error for job {job_id}: {e}")
        error = {"code": "MUSICBRAINZ_ERROR", "message": str(e)}
        redis_manager.set_beets_analysis_result(
            job_id,
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
        # Record failure for activity monitor
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"error": error},
                )
            except Exception as activity_error:
                logger.error(f"Failed to record activity completion: {activity_error}")
        return {"status": "failed", "error": error}

    except BeetsAnalysisError as e:
        logger.error(f"Beets analysis error for job {job_id}: {e}")
        error = {"code": "BEETS_ERROR", "message": str(e)}
        redis_manager.set_beets_analysis_result(
            job_id,
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
        # Record failure for activity monitor
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"error": error},
                )
            except Exception as activity_error:
                logger.error(f"Failed to record activity completion: {activity_error}")
        return {"status": "failed", "error": error}

    except Exception as e:
        logger.error(
            f"Unexpected error during beets analysis for job {job_id}: {e}",
            exc_info=True,
        )
        error = {"code": "UNKNOWN_ERROR", "message": str(e), "traceback": traceback.format_exc()}
        redis_manager.set_beets_analysis_result(
            job_id,
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
        # Record failure for activity monitor
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"error": error},
                )
            except Exception as activity_error:
                logger.error(f"Failed to record activity completion: {activity_error}")
        return {"status": "failed", "error": error}

    finally:
        # Unregister this analysis from the active set and drain queue
        try:
            redis_manager.unregister_active_analysis(library_id, job_id)
            drain_analysis_queue(library_id, redis_manager)
        except Exception as drain_error:
            logger.error(f"Error during queue drain for library {library_id}: {drain_error}")
        db.close()


def get_import_mode(config_path: Optional[str]) -> str:
    """Get the import mode (copy or move) from beets config.

    Args:
        config_path: Path to beets config file.

    Returns:
        'copy' or 'move' based on config. Defaults to 'copy'.
    """
    if not config_path or not os.path.exists(config_path):
        return "copy"

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        import_config = config.get("import", {})

        # Check for explicit copy setting
        if import_config.get("copy") is True:
            return "copy"

        # Check for move setting (takes precedence if both are set)
        if import_config.get("move") is True:
            return "move"

        # Default to copy
        return "copy"

    except Exception as e:
        logger.warning(f"Error reading beets config: {e}, defaulting to copy mode")
        return "copy"


def get_audio_files(album_path: str) -> List[str]:
    """Get list of audio files in an album folder, including disc subfolders.

    Walks the folder recursively so a multi-disc parent (``Album/Disc 1/``,
    ``Album/Disc 2/``) yields its audio too — the analysis side already walks
    the whole tree, so a top-level-only listing here would make the import of
    a multi-disc parent fail with "no audio files found". Hidden directories
    are skipped.

    Args:
        album_path: Path to the album folder.

    Returns:
        Sorted list of absolute paths to audio files.
    """
    return find_audio_files(album_path)


def infer_disc_for_file(
    audio_file: str, album_path: str, track_data: Optional[Dict[str, Any]]
) -> Optional[int]:
    """Determine which disc an audio file belongs to.

    The paired candidate track's ``disc`` is authoritative (set only for
    multi-disc provider candidates). Without a pairing — import-as-is, or an
    unmatched extra file — fall back to the file's disc subfolder name
    (``Disc N`` / ``CDN``), so a folder-per-disc rip still keeps its discs
    apart. Returns ``None`` when neither source knows a disc.
    """
    if track_data and track_data.get("disc"):
        return int(track_data["disc"])

    return infer_disc_number(audio_file, album_path)


def plan_destination_files(
    audio_files: List[str],
    album_path: str,
    destination_path: str,
    paired_tracks: Dict[str, Dict[str, Any]],
) -> tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
    """Plan the destination path for every audio file of an import.

    The destination is a single flat folder, and on a multi-disc release
    track numbers (and thus filenames like "01 - Title") repeat per disc, so
    unprefixed basenames from different disc folders would silently overwrite
    each other. When the files span more than one disc, every destination
    filename gets a ``<disc>-`` prefix; single-disc imports keep their
    basenames untouched.

    Args:
        audio_files: Source audio file paths.
        album_path: The album folder being imported (for disc-subfolder
            inference).
        destination_path: Flat library folder the files will land in.
        paired_tracks: ``{source_path: track_dict}`` pairing from
            :func:`pair_candidate_tracks_to_files`.

    Returns:
        ``(planned, dest_track_map)`` where ``planned`` maps each destination
        path to its source file and ``dest_track_map`` maps destination paths
        to their paired candidate track.

    Raises:
        ValueError: If two source files would land on the same destination
            path — never overwrite silently; losing a track is worse than a
            failed import the user can retry from an intact source.
    """
    file_discs = {
        f: infer_disc_for_file(f, album_path, paired_tracks.get(f))
        for f in audio_files
    }
    multi_disc = len({d for d in file_discs.values() if d}) > 1

    planned: Dict[str, str] = {}
    dest_track_map: Dict[str, Dict[str, Any]] = {}
    for audio_file in audio_files:
        src_filename = os.path.basename(audio_file)
        if multi_disc:
            dst_filename = f"{file_discs[audio_file] or 1}-{src_filename}"
        else:
            dst_filename = src_filename
        dst_path = os.path.join(destination_path, dst_filename)
        if dst_path in planned:
            raise ValueError(
                f"Destination filename collision: {planned[dst_path]!r} and "
                f"{audio_file!r} both map to {dst_path!r}"
            )
        planned[dst_path] = audio_file
        track_data = paired_tracks.get(audio_file)
        if track_data is not None:
            dest_track_map[dst_path] = track_data

    return planned, dest_track_map


def pair_candidate_tracks_to_files(
    candidate: Optional[Dict[str, Any]], files: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Pair each file to the candidate track beets matched it with.

    Keys on the track's ``local_path`` (the matcher's authoritative item↔track
    pairing), normalised, with a basename fallback for when the resolved path
    was canonicalised differently than the import/destination path. This is the
    multi-disc-safe replacement for keying by the per-disc track ``index``: on a
    multi-disc release every CD restarts at track 1 with the same titles, so an
    index key collides across discs and scrambles the tracks.

    Args:
        candidate: Candidate metadata dict (``None`` yields an empty mapping).
        files: Audio file paths to pair.

    Returns:
        ``{file_path: track_dict}`` for every file that has a paired track.
        Unpaired files are omitted so callers can fall back to position.
    """
    by_path: Dict[str, Dict[str, Any]] = {}
    by_base: Dict[str, Dict[str, Any]] = {}
    for track in (candidate.get("tracks") if candidate else []) or []:
        lp = track.get("local_path")
        if lp:
            by_path[os.path.normpath(lp)] = track
            by_base.setdefault(os.path.basename(lp), track)

    paired: Dict[str, Dict[str, Any]] = {}
    for f in files:
        track = by_path.get(os.path.normpath(f)) or by_base.get(os.path.basename(f))
        if track is not None:
            paired[f] = track
    return paired


def _trigger_emby_refresh(config_path: Optional[str]) -> Dict[str, Any]:
    """Tell Emby to rescan its library after a successful import.

    Replaces the third-party ``embyupdate`` beets plugin, whose post-import
    ``POST /Library/Refresh`` raised an unhandled ``ConnectTimeout`` traceback
    when Emby was unreachable — even though the import itself had succeeded.

    This runs the same call through :class:`EmbyConnectionService` (bounded
    timeout, mapped exceptions) and is strictly best-effort: it reads the Emby
    connection settings from the library's beets config and **never raises**.
    A missing/empty Emby config is a no-op (``status="skipped"``). Before the
    refresh a fast pre-flight connection test runs: if Emby is unreachable the
    refresh is deliberately skipped (``status="skipped_unreachable"``) rather
    than fired blind into a timeout — a transient outage (Emby reboot, network
    hiccup) self-heals on the next import, with no permanent disable. A
    reachable-but-failing refresh stays a soft warning (``status="failed"``).
    The caller keeps the import status at ``completed`` regardless.

    Args:
        config_path: Path to the library's beets YAML config.

    Returns:
        Dict with ``status`` (``ok`` | ``skipped`` | ``skipped_unreachable`` |
        ``failed``) and a ``message`` suitable for the activity feed.
    """
    try:
        if not config_path or not os.path.exists(config_path):
            return {"status": "skipped", "message": "No beets config to read Emby settings from"}

        # Imported lazily so the import task doesn't pull these in unless an
        # import actually completes (and to keep test patching local).
        from app.services.beets_config_service import BeetsConfigService
        from app.services.emby_service import EmbyConnectionService

        emby = BeetsConfigService().parse_yaml_config(config_path).emby
        if not emby.host or not emby.apikey:
            return {"status": "skipped", "message": "Emby not configured"}

        # Short timeout: a refresh is fire-and-forget, the import is already done.
        service = EmbyConnectionService(timeout=5.0)

        async def _check_then_refresh():
            # Pre-flight: don't run the refresh blind into a timeout. If Emby
            # is down, skip this one refresh and let the caller warn.
            reachable = await service.test_connection(
                host=emby.host,
                port=emby.port,
                userid=emby.userid,
                apikey=emby.apikey,
            )
            if not reachable.success:
                return {"status": "skipped_unreachable", "message": reachable.message}

            response = await service.refresh_library(
                host=emby.host, port=emby.port, apikey=emby.apikey
            )
            if response.skipped:
                return {"status": "skipped", "message": response.message}
            if response.success:
                return {"status": "ok", "message": response.message}
            return {"status": "failed", "message": response.message}

        return asyncio.run(_check_then_refresh())

    except Exception as e:
        # Defensive: config parse / event-loop errors must not touch the import.
        logger.warning(f"Emby library refresh raised unexpectedly: {e}")
        return {"status": "failed", "message": str(e)}


@celery_app.task(bind=True)
def import_album_task(
    self,
    job_id: str,
    library_id: int,
    album_path: str,
    candidate_json: str,
    import_as_is: bool = False,
) -> Dict[str, Any]:
    """Celery task to import an album using the selected candidate metadata.

    This task:
    1. Writes metadata tags to source files (skipped for import-as-is)
    2. Copies or moves files to beets library destination
    3. Adds album and items to beets SQLite database
    4. Updates Redis job status and writes task_events

    Args:
        job_id: Unique job ID for tracking.
        library_id: The library ID.
        album_path: Absolute path to the album folder.
        candidate_json: JSON-serialized candidate metadata ("null" / empty for
            an import-as-is job).
        import_as_is: When true, no candidate was selected — keep the files'
            existing tags and read library metadata from them.

    Returns:
        Dict with import result or error information.
    """
    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    activity_event_id = None
    destination_path = None
    started_at = datetime.now(timezone.utc)

    try:
        # Parse candidate (None for an import-as-is job — metadata is read from
        # the files' existing tags instead).
        candidate = json.loads(candidate_json) if candidate_json else None

        # Get the library
        library = db.query(Library).filter(Library.id == library_id).first()
        if not library:
            logger.error(f"Library {library_id} not found for import job {job_id}")
            raise ValueError("Library not found")

        logger.info(
            f"Starting import task for library {library.slug}, "
            f"album: {album_path}, job_id: {job_id}"
        )

        # Update job status to in_progress
        redis_manager.set_import_job_status(
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            status="in_progress",
            started_at=started_at,
        )

        # Extract album folder name for description / fallback metadata
        album_folder_name = os.path.basename(album_path) if album_path else "Unknown"

        # Get audio files (needed early to derive as-is metadata)
        audio_files = get_audio_files(album_path)
        if not audio_files:
            raise FileNotFoundError(f"No audio files found in {album_path}")

        # Resolve album-level metadata. A normal import takes it from the chosen
        # candidate and is always a single album (the candidate defines the
        # release). An import-as-is may be a multi-part release ("Komplett-
        # lesung"): split it into parts, each imported as its own album with
        # metadata read from that part's files (issue #190).
        if import_as_is:
            parts = split_release_parts(audio_files, album_path)
            part_metas = [
                _read_album_metadata(part.files, album_folder_name) for part in parts
            ]
            if len(parts) > 1:
                # Identical artist+album across parts (missing/uniform tags)
                # would re-collapse the split into one destination folder.
                disambiguate_part_albums(part_metas, parts)
                logger.info(
                    f"Multi-part release detected ({len(parts)} parts): "
                    + ", ".join(part.name or "?" for part in parts)
                )
            candidate_artist = part_metas[0]["artist"]
            candidate_album = (
                f"{album_folder_name} ({len(parts)} parts)"
                if len(parts) > 1
                else part_metas[0]["album"]
            )
        else:
            parts = [ReleasePart(name=None, root=album_path, files=audio_files)]
            candidate_artist = candidate.get("artist", "Unknown")
            candidate_album = candidate.get("album", "Unknown")
            part_metas = [{"artist": candidate_artist, "album": candidate_album}]

        # Record task start for activity monitor
        activity_event_id = task_event_service.record_start(
            task_type="import",
            library_id=library_id,
            library_slug=library.slug,
            description=f"Importing: {candidate_artist} - {candidate_album}",
            metadata={
                "job_id": job_id,
                "album_path": album_path,
                "candidate_source": candidate.get("source") if candidate else "as-is",
                "candidate_artist": candidate_artist,
                "candidate_album": candidate_album,
            },
        )

        # Get import mode
        import_mode = get_import_mode(library.config_path)
        logger.info(f"Import mode: {import_mode}")

        # Pair each source file to the candidate track beets matched it with.
        # Multi-disc safe (keys on local_path, not the per-disc track index) so
        # releases where every CD restarts at track 1 with the same titles (e.g.
        # an audio drama's "Teil 1" on each disc) don't scramble across discs.
        paired_tracks = pair_candidate_tracks_to_files(candidate, audio_files)

        # Highest disc number across the candidate's tracks. None for a
        # single-disc candidate (the resolver only sets disc on multi-disc
        # releases) and for import-as-is.
        candidate_disctotal = max(
            (
                int(t["disc"])
                for t in ((candidate.get("tracks") if candidate else None) or [])
                if t.get("disc")
            ),
            default=None,
        )

        # Step 1: Write metadata tags to source files. Skipped for import-as-is,
        # which leaves the files' existing tags untouched.
        if import_as_is:
            logger.info("Step 1: Skipped (import-as-is keeps existing tags)")
        else:
            logger.info(f"Step 1: Writing tags to {len(audio_files)} files")
            tag_registry = get_tag_writer_registry()

            # Build file_tags list for batch write
            file_tags = []
            for i, audio_file in enumerate(audio_files, start=1):
                track_data = paired_tracks.get(audio_file) or {}
                tags = {
                    "artist": candidate.get("artist", ""),
                    "album": candidate.get("album", ""),
                }
                if track_data:
                    tags["title"] = track_data.get("title", "")
                    # Per-disc track number (e.g. disc 2 track 1 is "1", not the
                    # running count "26"); the disc number keeps it on the right CD.
                    tags["track_number"] = str(track_data.get("index", i))
                    disc = track_data.get("disc")
                    if disc and candidate_disctotal:
                        tags["disc_number"] = f"{disc}/{candidate_disctotal}"
                    elif disc:
                        tags["disc_number"] = str(disc)
                else:
                    # No paired candidate track (e.g. an unmatched extra file):
                    # keep its position rather than fabricating an empty title.
                    tags["track_number"] = str(i)
                if candidate.get("year"):
                    tags["year"] = str(candidate["year"])
                if candidate.get("source_id"):
                    # Store source ID as musicbrainz_albumid for MusicBrainz sources
                    if candidate.get("source", "").lower() == "musicbrainz":
                        tags["musicbrainz_albumid"] = candidate["source_id"]

                file_tags.append((audio_file, tags))

            # Batch write tags
            batch_result = tag_registry.batch_write(file_tags)
            if batch_result.failed > 0:
                failed_files = [r.file_path for r in batch_result.results if not r.success]
                raise Exception(f"Failed to write tags to {batch_result.failed} files: {failed_files}")

            logger.info(f"Successfully wrote tags to {batch_result.succeeded} files")

        # Steps 2-4 run once per part (a single-part import loops once, exactly
        # as before): compute the destination, copy/move the part's files,
        # register the part as its own beets album.
        library_path = library.library_path or library.path
        if not library_path:
            raise ValueError("Library has no library_path configured")

        art_filename = get_art_filename(library.config_path)
        imported_albums: List[Dict[str, Any]] = []
        skipped_existing: List[Dict[str, Any]] = []
        destination_paths: List[str] = []

        for part, part_meta in zip(parts, part_metas):
            part_artist = part_meta["artist"]
            part_album = part_meta["album"]

            # Duplicate guard for as-is imports. The endpoint's existing-album
            # check needs a candidate to match on, so it explicitly skips as-is
            # mode — without this task-side check a re-run of the same as-is
            # import silently inserts a second identical album row (#190).
            if (
                import_as_is
                and library.database_path
                and os.path.exists(library.database_path)
            ):
                try:
                    existing = BeetsLibraryService().find_existing_album(
                        library.database_path,
                        albumartist=part_artist,
                        album=part_album,
                    )
                except Exception as lookup_err:
                    # A DB-level lookup error must not block a healthy import.
                    logger.warning(
                        f"Existing-album lookup failed for as-is import: {lookup_err}"
                    )
                    existing = None
                if existing:
                    logger.info(
                        f"Skipping already-imported album: {part_artist} - "
                        f"{part_album} (beets album {existing['album_id']})"
                    )
                    skipped_existing.append(
                        {
                            "artist": part_artist,
                            "album": part_album,
                            "existing_album_id": existing["album_id"],
                        }
                    )
                    continue

            # Step 2: Compute destination path using beets path templates
            # For simplicity, use a standard path format: library_path/Artist/Album/
            safe_artist = _sanitize_path_component(part_artist)
            safe_album = _sanitize_path_component(part_album)

            destination_path = os.path.join(library_path, safe_artist, safe_album)

            # Create destination directory
            os.makedirs(destination_path, exist_ok=True)
            logger.info(f"Step 2: Destination path: {destination_path}")

            # Step 3: Copy or move files to destination
            logger.info(
                f"Step 3: {'Copying' if import_mode == 'copy' else 'Moving'} "
                f"{len(part.files)} files"
            )

            planned, dest_track_map = plan_destination_files(
                part.files, part.root, destination_path, paired_tracks
            )

            for dst_path, audio_file in planned.items():
                if import_mode == "copy":
                    shutil.copy2(audio_file, dst_path)
                else:
                    shutil.move(audio_file, dst_path)

            # Step 4: Add to beets library database
            logger.info("Step 4: Adding to beets library database")
            part_album_id = _add_to_beets_library(
                library=library,
                destination_path=destination_path,
                candidate=candidate,
                audio_files=part.files,
                dest_track_map=dest_track_map,
                disctotal=candidate_disctotal,
                # Only audio is moved into destination_path; the source folder may
                # still hold the cover image, so let the cover step pull it across.
                source_folder=part.root,
                art_filename=art_filename,
                # Remote cover from the chosen candidate (Deezer/Discogs/etc.); used
                # as a fallback when no local/embedded cover is found.
                cover_url=candidate.get("cover_url") if candidate else None,
            )

            destination_paths.append(destination_path)
            imported_albums.append(
                {
                    "artist": part_artist,
                    "album": part_album,
                    "destination_path": destination_path,
                    "album_id": part_album_id,
                    "tracks": len(part.files),
                }
            )

        if not imported_albums:
            # Every part already exists in the library — surface the same
            # error the endpoint raises for candidate imports instead of
            # reporting a successful import that did nothing.
            skipped_names = "; ".join(
                f"{s['artist']} — {s['album']}" for s in skipped_existing
            )
            error_msg = f"Album already in library: {skipped_names}"
            logger.warning(f"Import job {job_id}: {error_msg}")
            _record_import_failure(
                redis_manager=redis_manager,
                task_event_service=task_event_service,
                job_id=job_id,
                library_id=library_id,
                album_path=album_path,
                started_at=started_at,
                error_code="ALBUM_ALREADY_EXISTS",
                error_message=error_msg,
                activity_event_id=activity_event_id,
                destination_path=None,
            )
            return {
                "status": "failed",
                "error": {"code": "ALBUM_ALREADY_EXISTS", "message": error_msg},
            }

        # Primary destination for single-valued consumers (job status, done-
        # album registry, drop-zone cleanup); the full list travels in the
        # result and activity metadata.
        destination_path = destination_paths[0]
        tracks_imported = sum(a["tracks"] for a in imported_albums)

        # Step 5: Clean up the import drop-zone (move mode only).
        # A successful move leaves the audio-empty release folder full of
        # sidecars, redundant cover images and now-empty parents. Strip them so
        # the scan count reflects what's actually still pending — strictly
        # inside the drop-zone, and never at the cost of an album's only cover.
        if import_mode == "move":
            # The whole cleanup step is best-effort: the import has already
            # succeeded by this point (audio moved + registered in beets), so a
            # config-resolution, prune, or dispatch hiccup must never flip the
            # job to "failed". Guard the entire block, not just the inner calls.
            try:
                cleanup_config = _resolve_import_cleanup_config(db, library_id)
                if cleanup_config.enabled:
                    logger.info("Step 5: Cleaning up import drop-zone")
                    _cleanup_import_drop_zone(
                        db=db,
                        redis_manager=redis_manager,
                        task_event_service=task_event_service,
                        library=library,
                        album_path=album_path,
                        destination_path=destination_path,
                        job_id=job_id,
                        config=cleanup_config,
                    )
                else:
                    # Feature disabled: preserve the original minimal behaviour
                    # of pruning the release folder and now-empty parents only.
                    logger.info(
                        "Step 5: Pruning empty source folders (cleanup disabled)"
                    )
                    from app.services.import_cleanup import (
                        prune_empty_drop_zone_folders,
                    )

                    prune_empty_drop_zone_folders(album_path, library.import_path)
            except Exception as cleanup_error:  # noqa: BLE001 - never fail the import
                logger.warning(
                    "Error during import drop-zone cleanup (import already "
                    "succeeded): %s",
                    cleanup_error,
                )

        completed_at = datetime.now(timezone.utc)

        # Update job status to completed
        redis_manager.set_import_job_status(
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            destination_path=destination_path,
            ttl_seconds=86400,  # 24 hours
        )

        # Register as done album (copy mode only)
        if import_mode == "copy":
            redis_manager.register_done_album(
                library_id=library_id,
                album_path=album_path,
                destination_path=destination_path,
                completed_at=completed_at,
            )

        # Post-import: ask Emby to rescan. Best-effort — the import is already
        # done, so a refresh failure is a soft warning, never a failed import.
        emby_refresh = _trigger_emby_refresh(library.config_path)
        if emby_refresh["status"] == "skipped_unreachable":
            # Pre-flight said Emby is down — skip this one refresh and surface a
            # visible, self-healing warning (no permanent disable). Recorded as
            # its own activity event so it persists in history, not just the log.
            logger.warning(
                f"Emby unreachable after import job {job_id}; library refresh "
                f"skipped: {emby_refresh['message']}"
            )
            task_event_service.record_event(
                task_type=TaskType.EMBY_REFRESH.value,
                library_id=library_id,
                library_slug=library.slug,
                description="Emby nicht erreichbar — Library-Refresh übersprungen",
                status=TaskStatus.FAILED.value,
                metadata={"job_id": job_id, "reason": emby_refresh["message"]},
            )
        elif emby_refresh["status"] == "failed":
            logger.warning(
                f"Emby library refresh failed after import job {job_id}: "
                f"{emby_refresh['message']}"
            )

        # Record completion for activity monitor
        if activity_event_id:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed",
                metadata={
                    "job_id": job_id,
                    "destination_path": destination_path,
                    "destination_paths": destination_paths,
                    "import_mode": import_mode,
                    "tracks_imported": tracks_imported,
                    "albums": imported_albums,
                    "skipped_existing": skipped_existing,
                    "emby_refresh": emby_refresh,
                },
            )

        logger.info(
            f"Import completed for job {job_id}: "
            f"{candidate_artist} - {candidate_album} -> "
            f"{'; '.join(destination_paths)}"
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "destination_path": destination_path,
            "destination_paths": destination_paths,
            "import_mode": import_mode,
            "tracks_imported": tracks_imported,
            "albums": imported_albums,
            "skipped_existing": skipped_existing,
        }

    except FileNotFoundError as e:
        error_msg = str(e)
        error_code = "ALBUM_NOT_FOUND"
        logger.error(f"Import failed (FileNotFoundError) for job {job_id}: {e}")
        _record_import_failure(
            redis_manager=redis_manager,
            task_event_service=task_event_service,
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            started_at=started_at,
            error_code=error_code,
            error_message=error_msg,
            activity_event_id=activity_event_id,
            destination_path=destination_path,
        )
        return {"status": "failed", "error": {"code": error_code, "message": error_msg}}

    except PermissionError as e:
        error_msg = str(e)
        error_code = "PERMISSION_DENIED"
        logger.error(f"Import failed (PermissionError) for job {job_id}: {e}")
        _record_import_failure(
            redis_manager=redis_manager,
            task_event_service=task_event_service,
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            started_at=started_at,
            error_code=error_code,
            error_message=error_msg,
            activity_event_id=activity_event_id,
            destination_path=destination_path,
        )
        return {"status": "failed", "error": {"code": error_code, "message": error_msg}}

    except OSError as e:
        # Handle disk full and other OS errors
        error_msg = str(e)
        error_code = "DISK_FULL" if e.errno == 28 else "FILE_COPY_FAILED"
        logger.error(f"Import failed (OSError) for job {job_id}: {e}")
        _record_import_failure(
            redis_manager=redis_manager,
            task_event_service=task_event_service,
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            started_at=started_at,
            error_code=error_code,
            error_message=error_msg,
            activity_event_id=activity_event_id,
            destination_path=destination_path,
        )
        return {"status": "failed", "error": {"code": error_code, "message": error_msg}}

    except Exception as e:
        error_msg = str(e)
        error_code = "BEETS_ERROR"
        logger.error(
            f"Unexpected error during import for job {job_id}: {e}",
            exc_info=True,
        )
        _record_import_failure(
            redis_manager=redis_manager,
            task_event_service=task_event_service,
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            started_at=started_at,
            error_code=error_code,
            error_message=error_msg,
            activity_event_id=activity_event_id,
            destination_path=destination_path,
        )
        return {"status": "failed", "error": {"code": error_code, "message": error_msg}}

    finally:
        db.close()


def _sanitize_path_component(name: str) -> str:
    """Sanitize a string for use as a filesystem path component.

    Args:
        name: The string to sanitize.

    Returns:
        Sanitized string safe for filesystem paths.
    """
    if not name:
        return "Unknown"

    # Replace problematic characters
    replacements = {
        '/': '_',
        '\\': '_',
        ':': '_',
        '*': '_',
        '?': '_',
        '"': "'",
        '<': '_',
        '>': '_',
        '|': '_',
    }
    for char, replacement in replacements.items():
        name = name.replace(char, replacement)

    # Strip leading/trailing whitespace and dots
    name = name.strip('. ')

    # Ensure not empty after sanitization
    if not name:
        return "Unknown"

    return name


def _read_album_metadata(
    audio_files: List[str],
    fallback_name: str,
) -> Dict[str, Any]:
    """Derive album-level metadata from the files' existing tags.

    Used by import-as-is, where no candidate was selected. Reads artist /
    album / year from the first tagged file. When tags are missing it parses
    the folder name into separate artist/album hints (stripping scene-release
    suffixes) rather than dumping the whole raw folder name into both fields,
    so this path agrees with the analyze path's Local Album summary. The raw
    folder name remains the last-resort value so neither field is ever empty.

    Args:
        audio_files: Audio file paths to inspect.
        fallback_name: Album folder name, used to derive hints (and as the
            last-resort value) when tags are absent.

    Returns:
        Dict with "artist", "album" and "year" (year may be None).
    """
    artist = ""
    album = ""
    year = None

    try:
        from beets.library import Item
    except ImportError as e:
        logger.warning(f"Beets not available for tag read, using folder name: {e}")
        Item = None

    if Item is not None:
        for f in audio_files:
            try:
                item = Item.from_path(f)
            except Exception as read_err:
                logger.warning(f"Could not read tags from {f}: {read_err}")
                continue
            artist = artist or item.albumartist or item.artist
            album = album or item.album
            if not year and item.year:
                year = item.year
            if artist and album:
                break

    folder_artist, folder_album = parse_album_folder_name(fallback_name)
    return {
        "artist": artist or folder_artist or fallback_name,
        "album": album or folder_album or fallback_name,
        "year": year,
    }


def _materialise_album_cover(
    *,
    album_id: int,
    database_path: str,
    destination_path: str,
    art_filename: str,
    source_folder: Optional[str],
    audio_files: List[str],
    cover_url: Optional[str] = None,
    library_path: Optional[str] = None,
) -> None:
    """Point the album's beets ``artpath`` at a cover image.

    The import pipeline doesn't run beets fetchart/embedart, so without this an
    in-folder cover (scene ``00-*`` etc.) or embedded art never becomes visible
    in the album grid, which reads only the stored ``artpath``.

    A locally discoverable cover wins; only when none is found do we fall back
    to downloading the chosen candidate's remote cover (Deezer/Discogs/etc.).
    Best-effort throughout: the files and DB rows already exist, so a cover
    failure never fails the import.
    """
    try:
        cover_path = ensure_album_cover(
            destination_path,
            art_filename,
            source_folder=source_folder,
            audio_files=audio_files,
        )
        if cover_path:
            BeetsLibraryService().update_album_artpath(database_path, album_id, cover_path)
        elif cover_url and database_path:
            # No local/embedded art — persist the candidate's remote cover. The
            # helper validates the URL (SSRF guard) and swallows its own errors.
            from app.services.cover_download import download_cover_to_album

            download_cover_to_album(
                cover_url,
                database_path=database_path,
                album_id=album_id,
                library_path=library_path,
                art_filename=art_filename,
            )
    except Exception as cover_err:
        logger.warning(
            f"Cover-art materialisation failed for album {album_id}: {cover_err}"
        )


def _add_to_beets_library(
    library: Library,
    destination_path: str,
    candidate: Optional[Dict[str, Any]],
    audio_files: List[str],
    source_folder: Optional[str] = None,
    art_filename: str = "albumart",
    cover_url: Optional[str] = None,
    dest_track_map: Optional[Dict[str, Dict[str, Any]]] = None,
    disctotal: Optional[int] = None,
) -> Optional[int]:
    """Add an imported album to the beets library database.

    Args:
        library: The Library model instance.
        destination_path: Final path where files were copied/moved.
        candidate: Candidate metadata dict, or None for an import-as-is job —
            in which case the files' existing tags are kept as read.
        audio_files: List of original audio file paths.
        source_folder: Original album folder the audio came from. Only the
            audio files are moved into ``destination_path``, so a cover image
            still sitting in the source folder is pulled across from here.
        art_filename: Beets ``art_filename`` basename for any materialised cover.
        cover_url: Optional remote cover URL from the chosen candidate. Used as
            a fallback only — downloaded and persisted when no local/embedded
            cover is found.
        dest_track_map: Optional explicit ``{destination_path: track_dict}``
            pairing computed by the import step. Authoritative when given —
            destination filenames may carry a disc prefix the basename
            re-pairing below can't see.
        disctotal: Total number of discs on the release; stamped on every
            item (with its disc) and on the album when set.

    Returns:
        The new beets album id, or None if nothing was added.
    """
    try:
        from beets import config as beets_config
        from beets.library import Library as BeetsLibrary, Album, Item
    except ImportError as e:
        logger.warning(f"Beets library not available for database import: {e}")
        return None

    database_path = library.database_path
    if not database_path or not os.path.exists(database_path):
        logger.warning(f"Beets database not found at {database_path}, skipping DB import")
        return None

    new_album_id: Optional[int] = None
    try:
        # Initialize beets library with the database path
        lib = BeetsLibrary(database_path)

        # Get list of destination files
        dest_files = []
        for f in os.listdir(destination_path):
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                dest_files.append(os.path.join(destination_path, f))
        dest_files = sorted(dest_files)

        # Create Item objects for each track. Prefer the explicit pairing from
        # the import step (multi-disc destinations get a disc-prefixed
        # filename, which basename matching can't recover); otherwise pair via
        # the matcher's local_path (basename survives the copy/move) rather
        # than by a per-disc track index, which would collide across discs on
        # a multi-disc release and mislabel the library DB rows.
        items = []
        if dest_track_map is not None:
            by_norm = {os.path.normpath(k): v for k, v in dest_track_map.items()}
            paired_tracks = {
                f: by_norm[os.path.normpath(f)]
                for f in dest_files
                if os.path.normpath(f) in by_norm
            }
        else:
            paired_tracks = pair_candidate_tracks_to_files(candidate, dest_files)

        for i, dest_file in enumerate(dest_files, start=1):
            track_data = paired_tracks.get(dest_file, {})

            # Create item from file path. For import-as-is, the tags read here
            # are exactly what we keep — no candidate overrides applied.
            item = Item.from_path(dest_file)

            if candidate:
                # Set album-level metadata
                item.artist = candidate.get("artist", "")
                item.album = candidate.get("album", "")
                item.albumartist = candidate.get("artist", "")
                if candidate.get("year"):
                    item.year = candidate["year"]

                # Set track-level metadata from the paired candidate track. Use
                # the per-disc track number and disc so multi-disc albums stay
                # correctly numbered; fall back to position only when unpaired.
                if track_data:
                    item.title = track_data.get("title", "")
                    item.track = track_data.get("index", i)
                    disc = track_data.get("disc")
                    if disc:
                        item.disc = disc
                        if disctotal:
                            item.disctotal = disctotal
                else:
                    item.track = i

                # Set source ID if available
                if candidate.get("source_id"):
                    if candidate.get("source", "").lower() == "musicbrainz":
                        item.mb_albumid = candidate["source_id"]
            elif not item.albumartist:
                # As-is: fall back to the track artist for grouping when the
                # file has no explicit album artist.
                item.albumartist = item.artist

            # Add item to library
            lib.add(item)
            items.append(item)

        # Create album record linking all items
        if items:
            if candidate:
                album_data = {
                    "album": candidate.get("album", ""),
                    "artist": candidate.get("artist", ""),
                    "albumartist": candidate.get("artist", ""),
                }
                if candidate.get("year"):
                    album_data["year"] = candidate["year"]
                if disctotal:
                    album_data["disctotal"] = disctotal
                if candidate.get("source_id") and candidate.get("source", "").lower() == "musicbrainz":
                    album_data["mb_albumid"] = candidate["source_id"]
            else:
                # As-is: derive album-level fields from the first item's tags.
                first = items[0]
                album_data = {
                    "album": first.album or "",
                    "artist": first.albumartist or first.artist or "",
                    "albumartist": first.albumartist or first.artist or "",
                }
                if first.year:
                    album_data["year"] = first.year

            # beets library.add_album requires items to already be in the library
            album = lib.add_album(items)
            if album:
                # Update album metadata
                for key, value in album_data.items():
                    setattr(album, key, value)
                album.store()
                new_album_id = album.id

        lib.close()
        logger.info(f"Added album with {len(items)} tracks to beets database")

        if new_album_id is not None:
            _materialise_album_cover(
                album_id=new_album_id,
                database_path=database_path,
                destination_path=destination_path,
                art_filename=art_filename,
                source_folder=source_folder,
                audio_files=dest_files,
                cover_url=cover_url,
                library_path=library.library_path,
            )

    except Exception as e:
        logger.error(f"Error adding to beets library database: {e}")
        # Don't fail the import if database write fails - files are already copied

    return new_album_id


def _record_import_failure(
    redis_manager: RedisKeyManager,
    task_event_service,
    job_id: str,
    library_id: int,
    album_path: str,
    started_at: datetime,
    error_code: str,
    error_message: str,
    activity_event_id: Optional[int],
    destination_path: Optional[str],
) -> None:
    """Record an import failure in Redis and task_events.

    Args:
        redis_manager: Redis manager instance.
        task_event_service: Task event service instance.
        job_id: The job ID.
        library_id: The library ID.
        album_path: The album path.
        started_at: When the job started.
        error_code: Error code.
        error_message: Error message.
        activity_event_id: Activity event ID if available.
        destination_path: Partial destination path if available.
    """
    completed_at = datetime.now(timezone.utc)

    # Update Redis job status
    redis_manager.set_import_job_status(
        job_id=job_id,
        library_id=library_id,
        album_path=album_path,
        status="failed",
        started_at=started_at,
        completed_at=completed_at,
        error_code=error_code,
        error_message=error_message,
        ttl_seconds=86400,  # 24 hours
    )

    # Record failure in activity monitor
    if activity_event_id:
        try:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="failed",
                metadata={
                    "job_id": job_id,
                    "error_code": error_code,
                    "error_message": error_message,
                },
            )
        except Exception as activity_error:
            logger.error(f"Failed to record activity completion: {activity_error}")

    # Clean up partial destination if it exists and is empty
    if destination_path and os.path.exists(destination_path):
        try:
            if not os.listdir(destination_path):
                os.rmdir(destination_path)
        except Exception as cleanup_error:
            logger.warning(f"Error cleaning up partial destination: {cleanup_error}")


@celery_app.task(bind=True)
def import_music(self, library_id: int, source_path: str, options: dict = None):
    """
    Import music files into a beets library (legacy placeholder).

    Args:
        library_id: The ID of the target library
        source_path: Path to the source files to import
        options: Optional beets import options
    """
    self.update_state(state="PROGRESS", meta={"status": "Starting import..."})

    # This is a placeholder - use import_album_task for the new workflow
    result = {
        "library_id": library_id,
        "source_path": source_path,
        "status": "completed",
        "message": "Use import_album_task for the new import workflow"
    }

    return result


@celery_app.task(bind=True)
def update_tags(self, library_id: int, item_ids: list, tags: dict):
    """
    Update tags on music items.

    Args:
        library_id: The ID of the library
        item_ids: List of item IDs to update
        tags: Dictionary of tag updates
    """
    self.update_state(state="PROGRESS", meta={"status": "Updating tags..."})

    result = {
        "library_id": library_id,
        "items_updated": len(item_ids),
        "status": "completed"
    }

    return result


# `beet move` prints "Moving N items." (or "Would move N items." with
# --pretend), where N already excludes files that are in place. Depending on
# the beets version the line lands on stdout or stderr, so both are searched.
_MOVE_COUNT_RE = re.compile(r"(?:Moving|Would move)\s+(\d+)\s+item")

# Per-file allowance for a move attempt: covers cross-device copies of large
# FLAC files; a same-filesystem rename finishes orders of magnitude faster.
_MOVE_SECONDS_PER_FILE = 10
_MOVE_TIMEOUT_FLOOR = 600
_MOVE_MAX_ATTEMPTS = 5


def _count_pending_moves(
    base_cmd: List[str], move_args: List[str]
) -> Optional[int]:
    """Return how many files `beet move` still wants to relocate.

    Uses `beet move --pretend`, which only computes destinations (no file
    I/O). Returns None when the count cannot be determined.
    """
    import subprocess

    cmd = base_cmd + ["move", "--pretend"] + move_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except SoftTimeLimitExceeded:
        raise
    except Exception as pretend_error:
        logger.warning(f"beet move --pretend failed: {pretend_error}")
        return None
    if result.returncode != 0:
        logger.warning(
            f"beet move --pretend exited {result.returncode}: {result.stderr}"
        )
        return None
    match = _MOVE_COUNT_RE.search(
        (result.stdout or "") + "\n" + (result.stderr or "")
    )
    if match:
        return int(match.group(1))
    # No "Moving N items" line: nothing matched the query or nothing needs
    # moving.
    return 0


def _move_album_files(
    base_cmd: List[str],
    move_args: List[str],
    track_count: Optional[int],
) -> tuple[bool, Optional[str]]:
    """Run `beet move`, retrying on timeout while progress is being made.

    `beet move` is resumable: files already at their template destination are
    skipped, so re-running after a killed attempt continues where it stopped.
    Attempts abort once a timeout brings no progress. Completion is verified
    with a final pretend count of 0 — the guard against the half-moved-album
    failure mode (issue #188).

    Returns (success, error_message).
    """
    import subprocess

    pending = _count_pending_moves(base_cmd, move_args)
    if pending == 0:
        return True, None
    total = pending if pending is not None else track_count
    cmd = base_cmd + ["move"] + move_args

    for attempt in range(1, _MOVE_MAX_ATTEMPTS + 1):
        budget = pending if pending is not None else track_count
        timeout = max(
            _MOVE_TIMEOUT_FLOOR,
            _MOVE_SECONDS_PER_FILE * budget if budget else 0,
        )
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            remaining = _count_pending_moves(base_cmd, move_args)
            if remaining == 0:
                return True, None
            if (
                remaining is not None
                and pending is not None
                and remaining < pending
            ):
                logger.warning(
                    f"beet move timed out after {timeout}s with progress "
                    f"({pending} -> {remaining} pending); resuming "
                    f"(attempt {attempt}/{_MOVE_MAX_ATTEMPTS})"
                )
                pending = remaining
                continue
            shown = remaining if remaining is not None else "unknown"
            return False, (
                f"move timed out after {timeout}s without progress: "
                f"{shown} of {total or '?'} files still misplaced"
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception as move_error:
            return False, f"move failed: {move_error}"

        if result.returncode != 0:
            return False, (
                f"move exited {result.returncode}: "
                f"{result.stderr or result.stdout or 'no output'}"
            )

        remaining = _count_pending_moves(base_cmd, move_args)
        if remaining not in (0, None):
            return False, (
                f"move incomplete: {remaining} of {total or '?'} files "
                f"still misplaced"
            )
        return True, None

    return False, (
        f"move did not finish after {_MOVE_MAX_ATTEMPTS} attempts; "
        f"{pending if pending is not None else 'unknown'} of {total or '?'} "
        f"files still misplaced"
    )


# Large albums (multi-GB, hundreds of tracks) need real time for the
# per-album `beet update` re-read and the file moves; the old 300s soft
# limit killed the task mid-move and left albums split across two folders
# (issue #188).
@celery_app.task(bind=True, soft_time_limit=3300, time_limit=3600)
def beets_update_albums(
    self,
    job_id: str,
    library_id: int,
    albums: List[str],
    config_path: Optional[str],
    activity_event_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Celery task to run beets update for multiple albums.

    Executes `beet update -a '<album>'` for each album to synchronize
    metadata changes from audio files back to the beets database.

    Args:
        job_id: Unique job ID for tracking.
        library_id: The library ID.
        albums: List of album names to update.
        config_path: Path to beets config file.
        activity_event_id: Optional activity event ID for progress tracking.

    Returns:
        Dict with update results for each album.
    """
    import subprocess

    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    started_at = datetime.now(timezone.utc)

    logger.info(
        f"Starting beets update task for job {job_id}, "
        f"library {library_id}, albums: {albums}"
    )

    # Resolve each album name to its beets album_id BEFORE we run any
    # `beet update`. The update command may rename the album (if the user
    # changed `album` itself), at which point a follow-up `beet move -a
    # 'old name'` would no longer match anything. album_id is stable across
    # renames — beets keeps the same row id and just rewrites the `album`
    # column — so caching it here lets the move step survive renames.
    library_record = db.query(Library).filter(Library.id == library_id).first()
    library_db_path = library_record.database_path if library_record else None
    library_root = library_record.library_path if library_record else None

    # Cover reconciliation after `beet move`: beets only relocates album art it
    # tracks via `artpath`, which beet-it imports leave null. Without this the
    # standalone cover.jpg is orphaned in the old folder when a tag edit moves
    # the tracks (issue #105). We capture each album's cover before the move and
    # relocate it afterwards.
    cover_service = BeetsLibraryService()
    cover_redis: Optional[RedisKeyManager] = None
    try:
        cover_redis = get_redis_key_manager(get_settings().redis_url)
    except Exception as cover_redis_err:  # pragma: no cover - cache is best-effort
        logger.warning(
            f"Cover-art reconciliation will skip the discovery cache: "
            f"{cover_redis_err}"
        )

    album_ids_by_name: Dict[str, Optional[int]] = {}
    # Track counts scale the subprocess timeouts: a 498-track audiobook needs
    # far more than a fixed 120s for update/move (issue #188).
    track_counts_by_name: Dict[str, Optional[int]] = {}
    if library_db_path:
        try:
            ro_conn = sqlite3.connect(f"file:{library_db_path}?mode=ro", uri=True)
            try:
                cursor = ro_conn.cursor()
                for album_name in albums:
                    cursor.execute(
                        "SELECT id FROM albums WHERE album = ? LIMIT 1",
                        (album_name,),
                    )
                    row = cursor.fetchone()
                    album_id = row[0] if row else None
                    album_ids_by_name[album_name] = album_id
                    if album_id is not None:
                        cursor.execute(
                            "SELECT COUNT(*) FROM items WHERE album_id = ?",
                            (album_id,),
                        )
                        count_row = cursor.fetchone()
                        track_counts_by_name[album_name] = (
                            count_row[0] if count_row else None
                        )
            finally:
                ro_conn.close()
        except Exception as lookup_error:
            logger.warning(
                f"Failed to pre-resolve album ids for job {job_id}: "
                f"{lookup_error}; move step will fall back to -a 'name'."
            )

    # Update job status to running (frontend expects "running" instead of "in_progress")
    redis_manager.set_batch_update_status(
        job_id=job_id,
        library_id=library_id,
        status="running",
        albums=albums,
        started_at=started_at,
    )

    results = {}
    albums_succeeded = 0
    albums_failed = 0

    try:
        for album in albums:
            album_status = "pending"
            album_error = None
            update_timeout = 120

            try:
                # Use python -m beets for consistent invocation in
                # containerized environments.
                base_cmd = ["python", "-m", "beets"]
                if config_path:
                    base_cmd.extend(["-c", config_path])

                # Build beets update command; -a flag for album query.
                cmd = base_cmd + ["update", "-a", album]
                logger.info(f"Running beets update command: {' '.join(cmd)}")

                # `beet update` re-reads every file's tags; scale the timeout
                # with the album size instead of a flat 120s.
                track_count = track_counts_by_name.get(album)
                if track_count:
                    update_timeout = max(120, 2 * track_count)

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=update_timeout,
                )

                if result.returncode == 0:
                    logger.info(f"Beets update succeeded for album: {album}")
                    if result.stdout:
                        logger.debug(f"Beets output: {result.stdout}")

                    # Run `beet move` so files relocate when a tag change
                    # touches a path-template field (albumartist, album,
                    # year, …). `beet update` alone only refreshes the DB —
                    # it leaves files at their old on-disk paths.
                    #
                    # Prefer the cached album_id query — it survives the user
                    # renaming the album itself in this same batch (then the
                    # post-update DB has the *new* album name, and a -a 'old
                    # name' move would no-op). Fall back to -a 'name' for the
                    # rare case where pre-resolution failed.
                    cached_album_id = album_ids_by_name.get(album)
                    if cached_album_id is not None:
                        move_args = [f"album_id:{cached_album_id}"]
                    else:
                        move_args = ["-a", album]

                    # Capture the album's cover *before* the move relocates
                    # the tracks, so we can carry an orphaned cover.jpg over
                    # to the new folder afterwards (issue #105). album_id is
                    # required to target the album reliably; skip
                    # reconciliation when it's unknown.
                    pre_move_cover: Optional[str] = None
                    if cached_album_id is not None and library_db_path:
                        try:
                            pre_move_cover = (
                                cover_service.get_album_cover_path_with_fallback(
                                    library_db_path,
                                    cached_album_id,
                                    redis_manager=cover_redis,
                                    library_root=library_root,
                                )
                            )
                        except Exception as cover_err:
                            logger.warning(
                                f"Could not resolve pre-move cover for album "
                                f"{cached_album_id}: {cover_err}"
                            )

                    move_ok, move_error = _move_album_files(
                        base_cmd, move_args, track_count
                    )
                    if move_ok:
                        album_status = "completed"
                        albums_succeeded += 1
                        # Carry the cover over to the new folder if beets
                        # left it behind, and refresh the discovery cache.
                        if cached_album_id is not None and library_db_path:
                            try:
                                relocated = cover_service.relocate_cover_after_move(
                                    library_db_path,
                                    cached_album_id,
                                    library_root,
                                    pre_move_cover,
                                )
                                if relocated and cover_redis is not None:
                                    cover_redis.invalidate_discovered_cover_art(
                                        library_db_path, cached_album_id
                                    )
                            except Exception as reconcile_err:
                                logger.warning(
                                    f"Cover reconciliation failed for album "
                                    f"{cached_album_id}: {reconcile_err}"
                                )
                    else:
                        # A half-moved album split across two folders is
                        # worse than a failed update: fail loudly instead of
                        # the old warn-and-report-success (issue #188). The
                        # DB already carries the new tags; re-running the
                        # sync resumes the move.
                        album_status = "failed"
                        albums_failed += 1
                        album_error = (
                            f"database updated but file move failed: {move_error}"
                        )
                        logger.error(
                            f"Beets move failed for album {album}: {move_error}"
                        )
                else:
                    album_status = "failed"
                    albums_failed += 1
                    album_error = result.stderr or f"Exit code: {result.returncode}"
                    logger.error(f"Beets update failed for album {album}: {album_error}")

            except subprocess.TimeoutExpired:
                album_status = "failed"
                albums_failed += 1
                album_error = f"Command timed out after {update_timeout} seconds"
                logger.error(f"Beets update timed out for album: {album}")

            except SoftTimeLimitExceeded:
                raise

            except Exception as e:
                album_status = "failed"
                albums_failed += 1
                album_error = str(e)
                logger.error(f"Error running beets update for album {album}: {e}")

            results[album] = {
                "status": album_status,
                "error": album_error,
            }

            # Update per-album status in Redis
            redis_manager.update_batch_update_album_status(
                job_id=job_id,
                album=album,
                status=album_status,
                error=album_error,
            )

    except SoftTimeLimitExceeded:
        # Celery is about to kill the task; write an honest final state so
        # the job never sticks in "running" with albums half-synced
        # (issue #188). The hard limit leaves headroom for these writes.
        logger.error(
            f"Soft time limit reached during batch-edit sync job {job_id}; "
            f"marking unfinished albums as failed"
        )
        for album in albums:
            if album in results:
                continue
            albums_failed += 1
            album_error = "sync aborted: task time limit reached"
            results[album] = {
                "status": "failed",
                "error": album_error,
            }
            redis_manager.update_batch_update_album_status(
                job_id=job_id,
                album=album,
                status="failed",
                error=album_error,
            )

    completed_at = datetime.now(timezone.utc)

    # Determine overall status
    if albums_failed == 0:
        overall_status = "completed"
    elif albums_succeeded == 0:
        overall_status = "failed"
    else:
        overall_status = "partial"

    # Update final job status
    redis_manager.set_batch_update_status(
        job_id=job_id,
        library_id=library_id,
        status=overall_status,
        albums=albums,
        started_at=started_at,
        completed_at=completed_at,
        album_results=results,
    )

    # Record completion for activity monitor
    if activity_event_id:
        try:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed" if overall_status == "completed" else "failed",
                metadata={
                    "job_id": job_id,
                    "albums_succeeded": albums_succeeded,
                    "albums_failed": albums_failed,
                    "results": results,
                },
            )
        except Exception as activity_error:
            logger.error(f"Failed to record activity completion: {activity_error}")

    db.close()

    logger.info(
        f"Beets update task completed for job {job_id}: "
        f"{albums_succeeded} succeeded, {albums_failed} failed"
    )

    return {
        "status": overall_status,
        "job_id": job_id,
        "albums_succeeded": albums_succeeded,
        "albums_failed": albums_failed,
        "results": results,
    }


# =============================================================================
# Move-album-to-library task
# =============================================================================


def _resolve_track_paths(
    tracks: List[TrackData],
    source_root: str,
) -> tuple[List[str], List[str]]:
    """Resolve each track's stored path to (absolute, relative-to-source-root).

    Beets item paths can be absolute (standard install) or relative to the
    library directory (a lscr.io/linuxserver/beets image quirk). Both forms
    must round-trip cleanly.

    Raises ValueError on the first track whose stored path is empty or sits
    outside ``source_root``.
    """
    absolute_paths: List[str] = []
    relative_paths: List[str] = []
    for track in tracks:
        stored = track.path or ""
        if not stored:
            raise ValueError(f"Track {track.id} has no path stored in beets DB")
        if os.path.isabs(stored):
            normalised = os.path.normpath(stored)
            if not normalised.startswith(source_root + os.sep):
                raise ValueError(
                    f"Track path '{stored}' is outside source library root '{source_root}'"
                )
            absolute = normalised
            relative = normalised[len(source_root) + 1 :]
        else:
            relative = stored
            absolute = os.path.join(source_root, relative)
        absolute_paths.append(absolute)
        relative_paths.append(relative)
    return absolute_paths, relative_paths


def _assert_folder_holds_only_album(
    db_path: str,
    source_album_id: int,
    source_root: str,
    album_folder: str,
) -> None:
    """Raise if any other album_id has items inside ``album_folder``.

    The whole-folder move strategy assumes the folder belongs exclusively to
    this album. Mixed folders happen rarely (manual organising mistakes) but
    would silently steal another album's tracks if we did not check.
    """
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT album_id, path FROM items")
        rows = cursor.fetchall()
    finally:
        connection.close()

    for row in rows:
        other_album_id = row["album_id"]
        if other_album_id == source_album_id:
            continue
        raw_path = row["path"]
        if isinstance(raw_path, bytes):
            try:
                other_path = raw_path.decode("utf-8")
            except UnicodeDecodeError:
                other_path = raw_path.decode("latin-1", errors="replace")
        else:
            other_path = str(raw_path or "")
        if not other_path:
            continue
        other_abs = (
            os.path.normpath(other_path)
            if os.path.isabs(other_path)
            else os.path.join(source_root, other_path)
        )
        other_dir = os.path.dirname(other_abs)
        if other_dir == album_folder or other_dir.startswith(album_folder + os.sep):
            raise ValueError(
                f"Folder '{album_folder}' contains items from another album "
                f"(id={other_album_id}); refusing to move."
            )


# Source DB columns that represent file-derived facts. Don't copy these from
# source rows onto the new Item objects — Item.from_path already reads them
# off the moved file (and copying a stale source value would lie about the
# real file).
_FILE_DERIVED_ITEM_COLUMNS = frozenset({
    "id",
    "album_id",
    "path",
    "mtime",
    "added",
    "format",
    "samplerate",
    "bitrate",
    "bitdepth",
    "channels",
    "length",
})

# Album-row columns to skip when overlaying source values onto the target
# album. ``id`` is auto-assigned; the source ``artpath`` referenced the
# now-vanished source folder, so we drop it here and re-materialise a correct
# artpath from the moved folder (see ``ensure_album_cover`` below) — otherwise
# the album grid, which reads only the stored artpath, shows a placeholder.
_SKIP_ALBUM_COLUMNS = frozenset({"id", "artpath", "added"})


def _add_moved_album_to_target_db(
    target_lib: Library,
    target_album_folder: str,
    source_db_path: str,
    source_album_id: int,
    art_filename: str = "albumart",
) -> Optional[int]:
    """Register every audio file in ``target_album_folder`` with the target
    beets DB and return the new album_id (or None if nothing was added).

    Item.from_path reads tags off each moved file, then we overlay the
    metadata from the source beets DB on top. This matters because beets'
    DB rows can drift from file tags (the user can edit album-level fields
    in beets without a `beet write`), and the user expects the album they
    were *looking at* to be what shows up in the target library — not a
    re-derivation from possibly-stale ID3 tags.

    Source items are matched to target files by track number; album-level
    columns are pulled from the source albums row and applied after
    add_album().
    """
    try:
        from beets.library import Library as BeetsLibrary, Item
    except ImportError as e:
        raise RuntimeError(f"beets library not available in this container: {e}")

    audio_files = [
        os.path.join(target_album_folder, name)
        for name in sorted(os.listdir(target_album_folder))
        if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS
    ]
    if not audio_files:
        raise ValueError(
            f"Target folder has no audio files after move: {target_album_folder}"
        )

    # Pull the full source album + items rows so we can mirror their values
    # onto the new target rows, not just whatever Item.from_path sees in
    # the file tags.
    source_album_row, source_items_by_track = _load_source_album_rows(
        source_db_path, source_album_id
    )

    library_dir = (target_lib.library_path or "").rstrip("/")
    # beets.library.Library has no .close() — connections are managed via
    # transaction context managers and finalised by GC. Don't try to close
    # it here (the legacy _add_to_beets_library calls .close() too but its
    # AttributeError gets swallowed by a broad except).
    lib = BeetsLibrary(target_lib.database_path, library_dir)
    items = []
    for audio_file in audio_files:
        item = Item.from_path(audio_file)
        # Item.track is set from the file tag; use it to find the matching
        # source row. Fall back to filename-order if a file has no track tag.
        source_row = source_items_by_track.get(int(item.track) if item.track else None)
        if source_row is None and len(audio_files) == len(source_items_by_track):
            # Same number of files as source items but tags don't line up —
            # use ordinal position so we still match something.
            ordinal = audio_files.index(audio_file) + 1
            source_row = source_items_by_track.get(ordinal)
        if source_row is not None:
            _overlay_source_columns(
                source_row, item, blacklist=_FILE_DERIVED_ITEM_COLUMNS
            )
        lib.add(item)
        items.append(item)
    if not items:
        return None
    album = lib.add_album(items)
    if album is None:
        return None
    if source_album_row is not None:
        _overlay_source_columns(
            source_album_row, album, blacklist=_SKIP_ALBUM_COLUMNS
        )
    # The whole folder moved with the tracks, so any folder image / scene 00-*
    # art is already here; otherwise fall back to embedded art. Setting artpath
    # via the album object reuses this connection (no separate write that could
    # race the open beets lib). Best-effort — a stale artpath only costs a
    # discovery fallback on the next read.
    try:
        cover_path = ensure_album_cover(
            target_album_folder, art_filename, audio_files=audio_files
        )
        if cover_path:
            album.artpath = cover_path
    except Exception as cover_err:
        logger.warning(
            f"Cover-art materialisation failed for moved album "
            f"{album.id}: {cover_err}"
        )
    album.store()
    return album.id


def _load_source_album_rows(
    db_path: str, album_id: int
) -> tuple[Optional[sqlite3.Row], Dict[Optional[int], sqlite3.Row]]:
    """Return (album_row, {track_number: item_row}) for the given album.

    Reads the raw SQLite rows so callers can copy every column verbatim —
    BeetsLibraryService's typed dataclasses only expose the fields the API
    uses, which would lose label/genre/mb_albumid/etc. on the round trip.
    """
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM albums WHERE id = ?", (album_id,))
        album_row = cursor.fetchone()
        cursor.execute("SELECT * FROM items WHERE album_id = ?", (album_id,))
        items_by_track: Dict[Optional[int], sqlite3.Row] = {}
        for row in cursor.fetchall():
            track = row["track"] if "track" in row.keys() else None
            try:
                track_int = int(track) if track is not None else None
            except (TypeError, ValueError):
                track_int = None
            items_by_track[track_int] = row
        return album_row, items_by_track
    finally:
        connection.close()


def _overlay_source_columns(
    source_row: sqlite3.Row,
    target_obj,
    blacklist: frozenset,
) -> None:
    """Copy non-blacklisted columns from a source DB row onto a beets model.

    Wrapped in a try/except per column so an unknown field on the target
    object (schema drift between beets versions) just gets skipped instead
    of failing the whole move.
    """
    for column in source_row.keys():
        if column in blacklist:
            continue
        value = source_row[column]
        # beets stores some BLOB fields (path, artpath) as bytes — those are
        # already in the blacklist for items/albums above, but be defensive
        # if we ever expand the whitelist later.
        if isinstance(value, bytes):
            continue
        try:
            setattr(target_obj, column, value)
        except Exception:
            continue


@celery_app.task(bind=True, soft_time_limit=900, time_limit=1200)
def move_album_task(
    self,
    job_id: str,
    source_library_id: int,
    target_library_id: int,
    source_album_id: int,
) -> Dict[str, Any]:
    """Move an album's files and DB records from one library to another.

    Strategy:
    1. Identify the album folder by computing the common parent of all item paths.
    2. Verify the folder contains only this album's items (refuse on mixed folders).
    3. Verify the target folder does not already exist (refuse on conflict).
    4. ``shutil.move`` the entire folder so cover art / .nfo / extras follow the audio.
    5. Register the moved files with the target beets DB via Item.from_path / add_album.
    6. Delete the album + items from the source beets DB.
    7. Walk up the source side and rmdir empty parent folders (artist directories etc.).

    On failure after files have already moved we attempt a best-effort
    rollback so the source library doesn't end up with a dangling DB row
    pointing at vanished files.
    """
    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    library_service = BeetsLibraryService()
    activity_event_id: Optional[int] = None
    started_at = datetime.now(timezone.utc)

    moved_files = False
    target_album_folder: Optional[str] = None
    source_album_folder: Optional[str] = None
    new_album_id: Optional[int] = None
    target_db_path: Optional[str] = None

    try:
        source_lib = db.query(Library).filter(Library.id == source_library_id).first()
        target_lib = db.query(Library).filter(Library.id == target_library_id).first()
        if source_lib is None:
            raise ValueError(f"Source library {source_library_id} not found")
        if target_lib is None:
            raise ValueError(f"Target library {target_library_id} not found")
        if not source_lib.database_path or not target_lib.database_path:
            raise ValueError("Source or target library has no database_path configured")
        if not source_lib.library_path or not target_lib.library_path:
            raise ValueError("Source or target library has no library_path configured")
        target_db_path = target_lib.database_path

        album = library_service.get_album_by_id(source_lib.database_path, source_album_id)
        if album is None:
            raise ValueError(
                f"Album {source_album_id} not found in library '{source_lib.slug}'"
            )
        tracks = library_service.get_album_tracks(source_lib.database_path, source_album_id)
        if not tracks:
            raise ValueError(f"Album {source_album_id} has no tracks to move")

        activity_event_id = task_event_service.record_start(
            task_type="move",
            library_id=source_library_id,
            library_slug=source_lib.slug,
            description=f"Moving: {album.artist} - {album.title} → {target_lib.slug}",
            metadata={
                "job_id": job_id,
                "source_library_slug": source_lib.slug,
                "target_library_slug": target_lib.slug,
                "target_library_id": target_library_id,
                "source_album_id": source_album_id,
                "track_count": len(tracks),
            },
        )

        source_root = os.path.normpath(source_lib.library_path).rstrip(os.sep)
        target_root = os.path.normpath(target_lib.library_path).rstrip(os.sep)

        absolute_paths, relative_paths = _resolve_track_paths(tracks, source_root)
        parent_dirs = {os.path.dirname(p) for p in absolute_paths}
        if len(parent_dirs) != 1:
            raise ValueError(
                f"Album {source_album_id} tracks span multiple folders: "
                f"{sorted(parent_dirs)}"
            )
        source_album_folder = parent_dirs.pop()
        relative_album_folder = os.path.dirname(relative_paths[0])
        if not relative_album_folder:
            raise ValueError(
                f"Album {source_album_id} tracks live at the library root — "
                "refusing to move (no folder to relocate)."
            )
        target_album_folder = os.path.join(target_root, relative_album_folder)

        if not os.path.isdir(source_album_folder):
            raise FileNotFoundError(
                f"Source album folder is missing on disk: {source_album_folder}"
            )

        _assert_folder_holds_only_album(
            db_path=source_lib.database_path,
            source_album_id=source_album_id,
            source_root=source_root,
            album_folder=source_album_folder,
        )

        if os.path.exists(target_album_folder):
            raise FileExistsError(
                f"Target album folder already exists: {target_album_folder}"
            )

        os.makedirs(os.path.dirname(target_album_folder), exist_ok=True)
        shutil.move(source_album_folder, target_album_folder)
        moved_files = True
        logger.info(
            f"Moved album folder: {source_album_folder} → {target_album_folder}"
        )

        new_album_id = _add_moved_album_to_target_db(
            target_lib=target_lib,
            target_album_folder=target_album_folder,
            source_db_path=source_lib.database_path,
            source_album_id=source_album_id,
            art_filename=get_art_filename(target_lib.config_path),
        )

        deleted = library_service.delete_album(source_lib.database_path, source_album_id)
        if not deleted:
            logger.warning(
                f"Source album row {source_album_id} was already gone when we got "
                f"to the cleanup step (job_id={job_id})"
            )

        try:
            parent = os.path.dirname(source_album_folder)
            while (
                parent
                and parent != source_root
                and parent.startswith(source_root + os.sep)
            ):
                if not os.listdir(parent):
                    os.rmdir(parent)
                    parent = os.path.dirname(parent)
                else:
                    break
        except OSError as cleanup_error:
            logger.warning(
                f"Error cleaning up empty parent folders in source: {cleanup_error}"
            )

        completed_at = datetime.now(timezone.utc)
        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="completed",
                    metadata={
                        "job_id": job_id,
                        "source_album_folder": source_album_folder,
                        "target_album_folder": target_album_folder,
                        "tracks_moved": len(tracks),
                        "new_album_id": new_album_id,
                    },
                )
            except Exception as activity_error:
                logger.error(
                    f"Failed to record activity completion for move {job_id}: "
                    f"{activity_error}"
                )

        logger.info(
            f"Move completed for job {job_id}: {album.artist} - {album.title} "
            f"({source_lib.slug} → {target_lib.slug}); new album_id={new_album_id}"
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "source_album_folder": source_album_folder,
            "target_album_folder": target_album_folder,
            "tracks_moved": len(tracks),
            "new_album_id": new_album_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }

    except Exception as exc:
        error_msg = str(exc)
        error_code = type(exc).__name__
        logger.error(
            f"Move failed for job {job_id}: {error_msg}",
            exc_info=True,
        )

        # Best-effort rollback. Order matters:
        #   1. Drop any rows we wrote to the target beets DB so we don't
        #      leave dangling album/items pointing at a folder we're about
        #      to move away.
        #   2. Move the album folder back to the source library so the
        #      source DB still matches disk.
        if new_album_id is not None and target_db_path:
            try:
                library_service.delete_album(target_db_path, new_album_id)
                logger.info(
                    f"Rolled back target DB rows for album {new_album_id} in "
                    f"{target_db_path}"
                )
            except Exception as db_rollback_error:
                logger.error(
                    f"Failed to roll back target DB rows for job {job_id}: "
                    f"{db_rollback_error}"
                )

        if moved_files and target_album_folder and source_album_folder:
            try:
                if os.path.exists(target_album_folder) and not os.path.exists(
                    source_album_folder
                ):
                    os.makedirs(os.path.dirname(source_album_folder), exist_ok=True)
                    shutil.move(target_album_folder, source_album_folder)
                    logger.info(
                        f"Rolled back file move: {target_album_folder} → "
                        f"{source_album_folder}"
                    )
            except Exception as rollback_error:
                logger.error(f"Rollback failed for job {job_id}: {rollback_error}")

        if activity_event_id:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={
                        "job_id": job_id,
                        "error_code": error_code,
                        "error_message": error_msg,
                    },
                )
            except Exception as activity_error:
                logger.error(
                    f"Failed to record activity failure for move {job_id}: "
                    f"{activity_error}"
                )

        return {
            "status": "failed",
            "job_id": job_id,
            "error": {"code": error_code, "message": error_msg},
        }

    finally:
        db.close()


def _library_file_permission(library: Library) -> Optional[int]:
    """Read the library's configured file permission (e.g. 664), or None.

    Used to chmod newly-written FLACs so they match beets-managed files. Failures
    are non-fatal — we just fall back to the process umask.
    """
    config_path = getattr(library, "config_path", None)
    if not config_path:
        return None
    try:
        from app.services.beets_config_service import BeetsConfigService

        config = BeetsConfigService().parse_yaml_config(config_path)
        return config.permissions.file
    except Exception as exc:  # noqa: BLE001 - permissions are best-effort
        logger.warning("Could not read file permission for library %s: %s", library.id, exc)
        return None


def _resolve_import_cleanup_config(db, library_id: int):
    """Resolve the per-library drop-zone cleanup config from user settings.

    Reads the (single) ``UserSettings`` row and layers its global +
    per-library cleanup blocks over the baked-in defaults. Falls back to the
    defaults when there's no settings row yet.

    Never raises: a DB read error must not fail an already-successful import,
    so on any error we return a *disabled* config (skip cleanup rather than
    delete under uncertainty).
    """
    from app.services.import_cleanup import (
        ImportCleanupConfig,
        resolve_import_cleanup_config,
    )

    try:
        from app.models.user_settings import UserSettings

        settings_row = db.query(UserSettings).first()
        preferences = settings_row.preferences if settings_row else None
        return resolve_import_cleanup_config(preferences, library_id)
    except Exception as exc:  # noqa: BLE001 - cleanup config must never fail an import
        logger.warning(
            "Could not resolve import-cleanup config for library %s; "
            "skipping cleanup: %s",
            library_id,
            exc,
        )
        return ImportCleanupConfig(enabled=False)


def _cleanup_import_drop_zone(
    db,
    redis_manager: RedisKeyManager,
    task_event_service,
    library: Library,
    album_path: str,
    destination_path: str,
    job_id: str,
    config=None,
) -> None:
    """Run drop-zone cleanup for a just-imported album and reconcile state.

    Removes leftover sidecars / redundant images / empty folders from the
    import drop-zone, drops the now-stale ``ImportItem`` rows so the scan count
    drops without a manual rescan, and records the result as an activity event.

    Entirely best-effort: the import has already succeeded, so any failure here
    is logged and swallowed rather than allowed to fail the job.
    """
    try:
        from sqlalchemy import or_

        from app.models.import_item import ImportItem
        from app.services.import_cleanup import (
            DEFAULT_IMPORT_CLEANUP_CONFIG,
            cleanup_import_drop_zone,
        )

        if config is None:
            config = DEFAULT_IMPORT_CLEANUP_CONFIG

        result = cleanup_import_drop_zone(
            album_path=album_path,
            destination_path=destination_path,
            import_root=library.import_path,
            art_filename=get_art_filename(library.config_path),
            sidecar_extensions=config.sidecar_extensions,
            delete_redundant_images=config.delete_redundant_images,
            promote_orphan_cover=config.promote_orphan_cover,
        )

        if result.skipped_reason:
            logger.info(
                "Drop-zone cleanup skipped for %s: %s",
                album_path,
                result.skipped_reason,
            )
            return

        # Drop stale import_items for everything removed from disk: the release
        # folder subtree plus any pruned parent folders. Mirrors the manual
        # delete-import-folder purge so the scan count reflects reality.
        items_removed = 0
        if result.changed:
            prefix = os.path.abspath(album_path).rstrip("/") + os.sep
            affected = set(result.affected_paths) | {os.path.abspath(album_path)}
            items_removed = (
                db.query(ImportItem)
                .filter(
                    ImportItem.library_id == library.id,
                    or_(
                        ImportItem.path.in_(affected),
                        ImportItem.path.startswith(prefix),
                    ),
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            redis_manager.invalidate_import_tree_cache(library.id)

        logger.info(
            "Drop-zone cleanup for %s: %d files removed, %d folders pruned, "
            "%d images promoted, %d images kept, %d import items dropped",
            album_path,
            len(result.files_removed),
            len(result.folders_pruned),
            len(result.images_promoted),
            len(result.images_kept),
            items_removed,
        )

        # Record as a point-in-time activity event so the result is visible in
        # history, not just the log. Skip the noise when nothing changed.
        if result.changed:
            task_event_service.record_event(
                task_type=TaskType.CLEANUP.value,
                library_id=library.id,
                library_slug=library.slug,
                description=(
                    f"Import-Ablage aufgeräumt: "
                    f"{len(result.files_removed)} Dateien entfernt, "
                    f"{len(result.folders_pruned)} Ordner geleert"
                ),
                status=TaskStatus.COMPLETED.value,
                metadata={
                    "job_id": job_id,
                    "album_path": album_path,
                    "files_removed": result.files_removed,
                    "folders_pruned": result.folders_pruned,
                    "images_promoted": result.images_promoted,
                    "images_kept": result.images_kept,
                    "import_items_removed": items_removed,
                },
            )
    except Exception as cleanup_error:  # noqa: BLE001 - cleanup never fails import
        logger.warning("Error cleaning up import drop-zone: %s", cleanup_error)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _refresh_import_items(library_id: int) -> None:
    """Re-scan the library's import folder so ImportItem rows reflect disk.

    Imported lazily to avoid a circular import between the beets and scan task
    modules. Failures are logged but never fail the audio op — the files have
    already changed on disk; the scan just catches the DB up.
    """
    try:
        from app.tasks.scan_tasks import execute_scan

        execute_scan.delay(library_id, "manual")
    except Exception as exc:  # noqa: BLE001 - refresh is best-effort
        logger.warning("Could not trigger rescan for library %s: %s", library_id, exc)


@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860)
def backfill_cover_art_task(self, library_id: int) -> Dict[str, Any]:
    """Fill in missing cover art across an existing library.

    Walks every album whose stored ``artpath`` is null or points at a missing
    file, resolves its on-disk folder, runs the same cover-art materialisation
    used on import/move (folder image → scene ``00-*`` → embedded art), and
    points ``artpath`` at the result. Idempotent: albums that already have a
    valid cover file on disk are left untouched. This is what makes the
    already-imported albums (artpath null since before this change) show their
    covers in the grid without a re-import.

    Returns a ``{scanned, updated, skipped}`` summary.
    """
    db = get_db()
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library or not library.database_path:
        raise ValueError(f"Library {library_id} not found or has no database")
    if not os.path.exists(library.database_path):
        raise FileNotFoundError(f"Beets database not found: {library.database_path}")

    service = BeetsLibraryService()
    redis_manager = get_redis_manager()
    art_filename = get_art_filename(library.config_path)
    library_root = library.library_path
    db_path = library.database_path

    # Snapshot album ids + artpath up front (read-only) so the per-album
    # writes below don't fight a cursor held open over the whole table.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, artpath FROM albums").fetchall()
    finally:
        conn.close()

    scanned = updated = skipped = 0
    for row in rows:
        scanned += 1
        album_id = row["id"]
        stored = service._resolve_against_root(
            service._decode_artpath(row["artpath"]), library_root
        )
        if stored and os.path.exists(stored):
            skipped += 1
            continue  # already has a valid cover on disk

        folder = service._resolve_against_root(
            service.get_album_folder_path(db_path, album_id), library_root
        )
        if not folder or not os.path.isdir(folder):
            continue
        cover_path = ensure_album_cover(folder, art_filename)
        if not cover_path:
            continue
        try:
            service.update_album_artpath(db_path, album_id, cover_path)
            # Clear any negative ("no cover") discovery cache for this album.
            redis_manager.set_discovered_cover_art(db_path, album_id, cover_path)
            updated += 1
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            logger.warning(
                f"Backfill: failed to set artpath for album {album_id}: {exc}"
            )

    logger.info(
        f"Cover-art backfill for {library.slug}: scanned={scanned}, "
        f"updated={updated}, skipped={skipped}"
    )
    return {
        "library_id": library_id,
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
    }


@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860)
def convert_audio_task(
    self,
    job_id: str,
    library_id: int,
    album_path: str,
    source_format: str,
    target_format: str,
    delete_originals: bool,
) -> Dict[str, Any]:
    """Convert an album folder's ``source_format`` files to ``target_format``.

    Generalises the WAV→FLAC path to WAV/WMA → FLAC/MP3. Mirrors the batch-task
    pattern: records activity, tracks job status in Redis for the frontend to
    poll, and always releases the per-album lock.
    """
    from app.services import wav_flac_service

    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    started_at = datetime.now(timezone.utc)
    activity_event_id: Optional[int] = None

    library = db.query(Library).filter(Library.id == library_id).first()
    album_name = os.path.basename(album_path.rstrip("/")) or album_path
    source_ext = wav_flac_service.SOURCE_EXTS.get(source_format, f".{source_format}")
    label = f"{source_format.upper()}→{target_format.upper()}"

    try:
        activity_event_id = task_event_service.record_start(
            task_type="convert_wav",
            library_id=library_id,
            library_slug=library.slug if library else str(library_id),
            description=f"Converting {label}: {album_name}",
            metadata={"job_id": job_id, "album_path": album_path,
                      "source_format": source_format,
                      "target_format": target_format,
                      "delete_originals": delete_originals},
        )
        redis_manager.set_audio_op_status(
            job_id, status="running", started_at=started_at
        )

        file_perm = _library_file_permission(library) if library else None
        result = wav_flac_service.convert_album_audio(
            album_path=album_path,
            source_ext=source_ext,
            target_format=target_format,
            delete_originals=delete_originals,
            file_perm=file_perm,
        )

        _refresh_import_items(library_id)

        redis_manager.set_audio_op_status(
            job_id,
            status="completed",
            result=result.as_dict(),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        if activity_event_id is not None:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed",
                metadata={"job_id": job_id, **result.as_dict()},
            )
        return {"status": "completed", "job_id": job_id, "result": result.as_dict()}

    except Exception as exc:  # noqa: BLE001 - report failure to the poller
        logger.error("convert_audio_task failed for job %s: %s", job_id, exc)
        redis_manager.set_audio_op_status(
            job_id,
            status="failed",
            error=str(exc),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        if activity_event_id is not None:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"job_id": job_id, "error_message": str(exc)},
                )
            except Exception:  # pragma: no cover - best effort
                pass
        return {"status": "failed", "job_id": job_id, "error": str(exc)}
    finally:
        redis_manager.release_audio_op_lock(library_id, album_path)
        db.close()


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360)
def remove_duplicate_wavs_task(
    self,
    job_id: str,
    library_id: int,
    album_path: str,
) -> Dict[str, Any]:
    """Delete duplicate WAVs (those with a FLAC twin), then rescan the folder."""
    from app.services import wav_flac_service

    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    started_at = datetime.now(timezone.utc)
    activity_event_id: Optional[int] = None

    library = db.query(Library).filter(Library.id == library_id).first()
    album_name = os.path.basename(album_path.rstrip("/")) or album_path

    try:
        activity_event_id = task_event_service.record_start(
            task_type="dedupe_wav",
            library_id=library_id,
            library_slug=library.slug if library else str(library_id),
            description=f"Removing duplicate WAVs: {album_name}",
            metadata={"job_id": job_id, "album_path": album_path},
        )
        redis_manager.set_audio_op_status(
            job_id, status="running", started_at=started_at
        )

        result = wav_flac_service.remove_duplicate_wavs(album_path)

        _refresh_import_items(library_id)

        redis_manager.set_audio_op_status(
            job_id,
            status="completed",
            result=result.as_dict(),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        if activity_event_id is not None:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed",
                metadata={"job_id": job_id, **result.as_dict()},
            )
        return {"status": "completed", "job_id": job_id, "result": result.as_dict()}

    except Exception as exc:  # noqa: BLE001 - report failure to the poller
        logger.error("remove_duplicate_wavs_task failed for job %s: %s", job_id, exc)
        redis_manager.set_audio_op_status(
            job_id,
            status="failed",
            error=str(exc),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        if activity_event_id is not None:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"job_id": job_id, "error_message": str(exc)},
                )
            except Exception:  # pragma: no cover - best effort
                pass
        return {"status": "failed", "job_id": job_id, "error": str(exc)}
    finally:
        redis_manager.release_audio_op_lock(library_id, album_path)
        db.close()


# Beets item columns describing the audio stream itself. Refreshed from the
# converted file after an in-place WAV→FLAC conversion so the DB stops
# describing the old WAV.
_ITEM_AUDIO_PROP_FIELDS = (
    "format",
    "bitrate",
    "bitdepth",
    "samplerate",
    "channels",
    "length",
)


def _refresh_item_audio_props(item, flac_path: str) -> None:
    """Update an item's audio-property fields from the file at ``flac_path``.

    Targeted fallback for when ``item.write()`` failed: a full ``item.read()``
    would overwrite the DB's tags with whatever sparse tags ffmpeg copied off
    the WAV, so only the stream facts are taken from the file here.
    """
    from mediafile import MediaFile

    mf = MediaFile(flac_path)
    for field in _ITEM_AUDIO_PROP_FIELDS:
        value = getattr(mf, field, None)
        if value is not None:
            item[field] = value


def _convert_imported_wav_items(
    library: Library,
    wav_items: List[tuple],
    delete_originals: bool,
    file_perm: Optional[int],
):
    """Convert each (track, absolute_wav_path) pair to FLAC and sync beets.

    Per item: transcode next to the original (atomic, verified), point the
    beets item at the new file, write the DB's tags into it (the DB is
    authoritative — WAVs rarely carry full tags), refresh the stream facts
    (format/bitrate/…) from the FLAC, store, and finally delete the WAV once
    everything else has succeeded. Failures are per-item: one broken track
    doesn't abort the album, and its WAV + DB row are left untouched.
    """
    from beets.library import Library as BeetsLibrary
    from beets.util import bytestring_path

    from app.services import wav_flac_service

    result = wav_flac_service.ConvertResult()
    lib = BeetsLibrary(
        library.database_path, (library.library_path or "").rstrip("/")
    )

    for track, wav_path in wav_items:
        flac_path = os.path.splitext(wav_path)[0] + ".flac"

        # A same-name FLAC of unknown provenance already sits next to the WAV.
        # Don't overwrite it, and don't repoint the item at a file we didn't
        # produce — leave this track for the user to untangle.
        if os.path.exists(flac_path):
            result.skipped += 1
            continue

        try:
            wav_flac_service.transcode_file(
                wav_path, flac_path, target_format="flac", file_perm=file_perm
            )
        except Exception as exc:  # noqa: BLE001 - report per-file, keep going
            result.failed += 1
            result.failures.append({"file": wav_path, "error": str(exc)})
            logger.warning("WAV→FLAC transcode failed for %s: %s", wav_path, exc)
            continue

        try:
            item = lib.get_item(track.id)
            if item is None:
                raise ValueError(f"Item {track.id} vanished from the beets DB")
            item.path = bytestring_path(flac_path)
            try:
                item.write()  # DB tags → FLAC
                item.read()   # FLAC stream facts (+ round-tripped tags) → DB
            except Exception as tag_exc:  # noqa: BLE001 - keep DB usable
                logger.warning(
                    "Tag sync failed for %s (item still repointed): %s",
                    flac_path,
                    tag_exc,
                )
                _refresh_item_audio_props(item, flac_path)
            item.store()
        except Exception as exc:  # noqa: BLE001 - report per-file, keep going
            # DB update failed — remove the orphan FLAC so disk matches the
            # DB row, which still points at the untouched WAV.
            result.failed += 1
            result.failures.append({"file": wav_path, "error": str(exc)})
            logger.warning("Beets DB update failed for %s: %s", flac_path, exc)
            try:
                os.unlink(flac_path)
            except OSError:  # pragma: no cover - best effort
                pass
            continue

        result.converted += 1

        if delete_originals:
            try:
                if os.path.isfile(flac_path) and os.path.getsize(flac_path) > 0:
                    os.remove(wav_path)
                    result.deleted += 1
            except OSError as exc:  # pragma: no cover - best effort
                logger.warning("Could not delete original %s: %s", wav_path, exc)

    return result


@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860)
def convert_imported_album_task(
    self,
    job_id: str,
    library_id: int,
    album_id: int,
    delete_originals: bool = True,
) -> Dict[str, Any]:
    """Convert an already-imported album's WAV tracks to FLAC, in place.

    Unlike :func:`convert_audio_task` (pre-import folders), the files here are
    owned by beets, so each conversion must also repoint the item row at the
    new file and refresh its stream metadata. Mirrors the audio-op pattern:
    activity event, Redis job status for polling, per-album lock released in
    ``finally``.
    """
    db = get_db()
    redis_manager = get_redis_manager()
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)
    library_service = BeetsLibraryService()
    started_at = datetime.now(timezone.utc)
    activity_event_id: Optional[int] = None
    lock_token = f"imported-album:{album_id}"

    try:
        library = db.query(Library).filter(Library.id == library_id).first()
        if library is None:
            raise ValueError(f"Library {library_id} not found")
        if not library.database_path or not library.library_path:
            raise ValueError("Library has no database_path or library_path configured")

        album = library_service.get_album_by_id(library.database_path, album_id)
        if album is None:
            raise ValueError(f"Album {album_id} not found in library '{library.slug}'")
        tracks = library_service.get_album_tracks(library.database_path, album_id)

        source_root = os.path.normpath(library.library_path).rstrip(os.sep)
        absolute_paths, _ = _resolve_track_paths(tracks, source_root)
        wav_items = [
            (track, path)
            for track, path in zip(tracks, absolute_paths)
            if path.lower().endswith(".wav")
        ]
        if not wav_items:
            raise ValueError("Album has no WAV tracks to convert")

        activity_event_id = task_event_service.record_start(
            task_type=TaskType.CONVERT_WAV.value,
            library_id=library_id,
            library_slug=library.slug,
            description=f"Converting WAV→FLAC: {album.artist} - {album.title}",
            metadata={
                "job_id": job_id,
                "album_id": album_id,
                "wav_track_count": len(wav_items),
                "delete_originals": delete_originals,
            },
        )
        redis_manager.set_audio_op_status(
            job_id, status="running", started_at=started_at
        )

        result = _convert_imported_wav_items(
            library=library,
            wav_items=wav_items,
            delete_originals=delete_originals,
            file_perm=_library_file_permission(library),
        )

        # The files Emby serves just changed — nudge it. Strictly best-effort.
        emby_refresh = _trigger_emby_refresh(library.config_path)

        redis_manager.set_audio_op_status(
            job_id,
            status="completed",
            result=result.as_dict(),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        if activity_event_id is not None:
            task_event_service.record_completion(
                event_id=activity_event_id,
                status="completed",
                metadata={
                    "job_id": job_id,
                    "emby_refresh": emby_refresh.get("status"),
                    **result.as_dict(),
                },
            )
        return {"status": "completed", "job_id": job_id, "result": result.as_dict()}

    except Exception as exc:  # noqa: BLE001 - report failure to the poller
        logger.error(
            "convert_imported_album_task failed for job %s: %s", job_id, exc,
            exc_info=True,
        )
        redis_manager.set_audio_op_status(
            job_id,
            status="failed",
            error=str(exc),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        if activity_event_id is not None:
            try:
                task_event_service.record_completion(
                    event_id=activity_event_id,
                    status="failed",
                    metadata={"job_id": job_id, "error_message": str(exc)},
                )
            except Exception:  # pragma: no cover - best effort
                pass
        return {"status": "failed", "job_id": job_id, "error": str(exc)}
    finally:
        redis_manager.release_audio_op_lock(library_id, lock_token)
        db.close()
