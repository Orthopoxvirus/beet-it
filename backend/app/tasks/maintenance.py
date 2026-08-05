"""Celery tasks for maintenance operations including activity monitor cleanup."""

import logging
import os
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.config import get_settings
from app.database import SessionLocal
from app.models.enums import TaskStatus, TaskType
from app.models.library import Library
from app.services.beets_library_service import BeetsLibraryService
from app.services.redis_keys import get_redis_key_manager
from app.services.task_events import get_task_event_service

logger = logging.getLogger(__name__)
settings = get_settings()

# Items analysed per `beet autobpm` invocation. BPM analysis is CPU-bound
# (seconds per track), so chunks keep the cancel flag responsive and progress
# flowing without paying librosa's import cost per single track.
BPM_BACKFILL_CHUNK_SIZE = 20

# Max seconds one `beet autobpm` chunk subprocess may take.
BPM_CHUNK_TIMEOUT = 1800

# The lock name scans see via has_blocking_operations().
BPM_BACKFILL_OPERATION = "bpm_backfill"

# Wall-clock budget of ONE task invocation ("link"). A full-library analysis
# can take many hours — far beyond any sane celery time limit — so the job
# runs as a chain of short links: each link analyses for at most this long,
# then re-enqueues itself. Job state lives in the Redis status hash, so a
# worker restart (deploy, crash) costs one link, not the whole job.
BPM_LINK_MAX_SECONDS = 1200

# Link-lock TTL: worst-case link duration (budget + one full chunk timeout)
# plus slack. A SIGKILLed link can therefore never block resumption for long.
BPM_LINK_LOCK_TTL = BPM_LINK_MAX_SECONDS + BPM_CHUNK_TIMEOUT + 300

# The resume guard re-enqueues a job whose status heartbeat is older than
# this. The heartbeat updates at least once per finished chunk, so the
# threshold must exceed BPM_CHUNK_TIMEOUT or a slow chunk would double-fire
# (the link lock would catch that, but avoid the churn).
BPM_RESUME_STALE_SECONDS = 2700

# Pre-flight estimate fallback: compute-seconds per track on one core when
# the library has never been measured.
BPM_DEFAULT_TRACK_SECONDS = 6.0

# An item is only written off (excluded from further links) after this many
# attempts without a stored bpm. Crashed/timed-out chunks therefore retry
# their items instead of losing them to one transient failure.
BPM_MAX_ITEM_ATTEMPTS = 3


@celery_app.task(bind=True, name="maintenance.cleanup_stale_activity_entries")
def cleanup_stale_activity_entries(self, max_age_seconds: int = 7200) -> Dict[str, Any]:
    """Clean up stale activity entries from Redis and mark orphaned DB events as failed.

    This task runs periodically via Celery Beat to handle crash recovery:
    - Removes entries from Redis active task index older than max_age_seconds
    - Marks database task events with status='running' older than max_age_seconds as 'failed'

    Args:
        max_age_seconds: Maximum age in seconds before considering a task stale (default 2 hours)

    Returns:
        Dict with cleanup results
    """
    task_event_service = get_task_event_service()

    try:
        removed_count = task_event_service.cleanup_stale_entries(max_age_seconds)

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} stale activity entries")
        else:
            logger.debug("No stale activity entries found")

        return {
            "status": "completed",
            "removed_count": removed_count,
            "max_age_seconds": max_age_seconds,
        }

    except Exception as e:
        logger.error(f"Failed to clean up stale activity entries: {e}")
        return {
            "status": "failed",
            "error": str(e),
        }

    finally:
        task_event_service.close()


def bpm_workers() -> int:
    """Parallel `beet autobpm` subprocesses to run.

    Configurable via BPM_ANALYSIS_WORKERS; auto default is half the CPU cores
    visible to this container (min 1) so analysis never starves the host.
    """
    configured = settings.bpm_analysis_workers
    if configured and configured > 0:
        return configured
    try:
        cores = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cores = os.cpu_count() or 1
    return max(1, cores // 2)


def estimate_backfill_seconds(redis_manager, library_id: int, missing: int) -> int:
    """Expected wall-clock duration of a backfill of ``missing`` tracks.

    Uses the measured per-track wall rate of the library's last finished job
    (which already reflects that job's parallelism); falls back to the
    single-core default divided by the current worker count.
    """
    if missing <= 0:
        return 0
    try:
        per_track = redis_manager.get_bpm_track_seconds(library_id)
    except Exception:  # noqa: BLE001 — the estimate is cosmetic, never fail the endpoint on redis
        per_track = None
    if per_track is None:
        per_track = BPM_DEFAULT_TRACK_SECONDS / bpm_workers()
    return int(missing * per_track)


def _run_autobpm_chunk(config_path: str, item_ids: List[int], timeout: int = BPM_CHUNK_TIMEOUT) -> subprocess.CompletedProcess:
    """Run `beet autobpm` for a chunk of item IDs.

    ``--plugins autobpm`` narrows the plugin list for this invocation so the
    run works whether or not the library YAML enables autobpm, and skips the
    load cost (and stderr noise) of unrelated plugins. autobpm's own
    ``overwrite: no`` default keeps pre-existing bpm tags safe, and our query
    only feeds it bpm-less items anyway.
    """
    # beets OR-combines query parts only when the comma is its OWN argv token;
    # a single "id:1 , id:2" string is parsed as one term and rejected
    # ("... is not an int or a float"). So interleave standalone "," tokens.
    query_tokens: List[str] = []
    for item_id in item_ids:
        if query_tokens:
            query_tokens.append(",")
        query_tokens.append(f"id:{item_id}")
    cmd = ["python", "-m", "beets"]
    if config_path:
        cmd.extend(["-c", config_path])
    cmd.extend(["--plugins", "autobpm", "autobpm", *query_tokens])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_autobpm_env())


def _autobpm_env() -> Dict[str, str]:
    """Environment for autobpm subprocesses running in parallel.

    Parallelism comes from running bpm_workers() processes side by side —
    nested BLAS/OpenMP thread pools inside each one only fight each other,
    so pin the math libraries to one thread per process.
    """
    env = os.environ.copy()
    for var in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        env[var] = "1"
    return env


def _autobpm_error_snippet(result: subprocess.CompletedProcess) -> str:
    """One human-readable line explaining why a chunk stored no/few bpm values."""
    for line in reversed((result.stderr or "").strip().splitlines()):
        if "autobpm:" in line or "error" in line.lower():
            return line.strip()[:300]
    return f"beets exited with code {result.returncode}"


@celery_app.task(bind=True, name="maintenance.bpm_backfill", soft_time_limit=3300, time_limit=3600)
def bpm_backfill(self, library_id: int, job_id: str) -> Dict[str, Any]:
    """One link of the chained BPM backfill for a library.

    Analyses missing-bpm items on ``bpm_workers()`` parallel subprocesses for
    at most BPM_LINK_MAX_SECONDS, then re-enqueues itself with the same
    job_id. Counters, the activity event id and the last error travel in the
    Redis status hash, so the chain survives worker restarts; the beat task
    ``resume_stalled_bpm_backfills`` revives a job whose link was killed.

    Items that were attempted but stored no bpm (unreadable files) land in a
    Redis exclusion set, so every link makes strict progress and the chain
    always terminates.
    """
    db = SessionLocal()
    redis_manager = get_redis_key_manager(settings.redis_url)
    task_event_service = get_task_event_service(db=db, redis_manager=redis_manager)

    if not redis_manager.acquire_bpm_link_lock(library_id, BPM_LINK_LOCK_TTL):
        # Another link of this job is still alive (e.g. the resume guard
        # double-fired during a slow chunk) — this one is redundant.
        task_event_service.close()
        db.close()
        logger.info("bpm_backfill: link lock held for library %s, skipping duplicate link", library_id)
        return {"status": "duplicate_link_skipped"}

    workers = bpm_workers()
    state = redis_manager.get_bpm_backfill_status(library_id) or {}
    if state.get("job_id") == job_id:
        # Later link of the same job: continue its counters.
        total = int(state.get("total") or 0)
        processed = int(state.get("processed") or 0)
        failed = int(state.get("failed") or 0)
        active_seconds = float(state.get("active_seconds") or 0.0)
        event_id = state.get("event_id")
        last_error = state.get("error")
    else:
        total = processed = failed = 0
        active_seconds = 0.0
        event_id = None
        last_error = None

    link_started = time.monotonic()
    base_active_seconds = active_seconds
    lock_acquired = False

    def publish(status: str, eta: Optional[int] = None) -> None:
        redis_manager.set_bpm_backfill_status(
            library_id,
            status=status,
            total=total,
            processed=processed,
            failed=failed,
            job_id=job_id,
            error=last_error,
            active_seconds=base_active_seconds + (time.monotonic() - link_started),
            eta_seconds=eta,
            workers=workers,
            event_id=event_id,
        )

    def eta_seconds() -> Optional[int]:
        if processed <= 0:
            return None
        elapsed = base_active_seconds + (time.monotonic() - link_started)
        remaining = max(0, total - processed - failed)
        return int(remaining * (elapsed / processed))

    def store_rate() -> None:
        elapsed = base_active_seconds + (time.monotonic() - link_started)
        if processed > 0 and elapsed > 0:
            redis_manager.set_bpm_track_seconds(library_id, elapsed / processed)

    def finalize(final_status: str, event_status: str, event_metadata: Dict[str, Any]) -> None:
        publish(final_status, eta=0)
        if event_id:
            task_event_service.record_completion(
                event_id=event_id, status=event_status, metadata=event_metadata
            )

    def requeue_next_link() -> None:
        publish("running", eta=eta_seconds())
        # countdown gives this link's finally-block time to drop the link lock
        bpm_backfill.apply_async(kwargs={"library_id": library_id, "job_id": job_id}, countdown=2)

    try:
        library = db.query(Library).filter(Library.id == library_id).first()
        if not library or not library.database_path:
            last_error = "Library or beets database not available"
            publish("failed", eta=0)
            return {"status": "failed", "error": "library not available"}

        if redis_manager.is_bpm_backfill_cancelled(library_id):
            redis_manager.clear_bpm_backfill_cancel(library_id)
            finalize("cancelled", TaskStatus.FAILED.value,
                     {"cancelled": True, "processed": processed, "failed": failed})
            logger.info("bpm_backfill cancelled for library %s at %d/%d", library_id, processed, total)
            return {"status": "cancelled", "processed": processed, "total": total}

        beets_service = BeetsLibraryService()
        failed_ids = redis_manager.get_bpm_failed_items(library_id)
        item_ids = [
            i for i in beets_service.get_item_ids_missing_bpm(library.database_path)
            if i not in failed_ids
        ]

        if state.get("job_id") != job_id or total <= 0:
            total = len(item_ids)

        if not item_ids:
            final = "completed" if failed == 0 else "completed_with_errors"
            store_rate()
            finalize(final, TaskStatus.COMPLETED.value,
                     {"processed": processed, "failed": failed, "total": total})
            logger.info("bpm_backfill done for library %s: %d ok, %d failed of %d",
                        library_id, processed, failed, total)
            return {"status": final, "processed": processed, "failed": failed, "total": total}

        lock_acquired = redis_manager.acquire_operation_lock(library_id, BPM_BACKFILL_OPERATION)

        if event_id is None:
            event_id = task_event_service.record_start(
                task_type=TaskType.BPM_BACKFILL.value,
                library_id=library.id,
                library_slug=library.slug,
                description=f"Analyzing BPM for {total} track(s)",
                metadata={"job_id": job_id, "total": total, "workers": workers},
            )
        publish("running", eta=eta_seconds())

        chunks = [item_ids[i:i + BPM_BACKFILL_CHUNK_SIZE]
                  for i in range(0, len(item_ids), BPM_BACKFILL_CHUNK_SIZE)]
        chunk_iter = iter(chunks)
        in_flight: Dict[Any, List[int]] = {}

        def budget_left() -> bool:
            return time.monotonic() - link_started < BPM_LINK_MAX_SECONDS

        def account_chunk(chunk: List[int], result, timed_out: bool) -> None:
            nonlocal processed, failed, last_error
            # beets exits 0 even when every track fails (per-track errors are
            # only logged), so count what actually landed in the beets DB.
            stored_ids = beets_service.get_item_ids_with_bpm(library.database_path, chunk)
            processed += len(stored_ids)
            unstored = [i for i in chunk if i not in stored_ids]
            if unstored:
                if timed_out:
                    last_error = f"autobpm chunk timed out ({len(chunk)} items)"
                    logger.warning("bpm_backfill: chunk timed out (%d items)", len(chunk))
                elif result is not None:
                    last_error = _autobpm_error_snippet(result)
                    log = logger.error if result.returncode < 0 else logger.warning
                    log(
                        "bpm_backfill: %d/%d items in chunk got no bpm (rc=%s): %s",
                        len(unstored), len(chunk), result.returncode,
                        (result.stderr or "")[-500:],
                    )
                # Retry unstored items in later links; only write an item off
                # after BPM_MAX_ITEM_ATTEMPTS (a crashed chunk is transient,
                # an unreadable file fails every time).
                attempts = redis_manager.incr_bpm_attempts(library_id, unstored)
                give_up = [i for i in unstored if attempts.get(i, 0) >= BPM_MAX_ITEM_ATTEMPTS]
                if give_up:
                    failed += len(give_up)
                    redis_manager.add_bpm_failed_items(library_id, give_up)

            publish("running", eta=eta_seconds())
            if event_id:
                task_event_service.record_progress(
                    event_id=event_id,
                    progress_percent=min(100.0, (processed + failed) / max(1, total) * 100.0),
                    metadata={
                        "items_total": total,
                        "items_processed": processed,
                        "items_failed": failed,
                    },
                )

        def run_serial_chunk(chunk: List[int]) -> None:
            result = None
            timed_out = False
            try:
                result = _run_autobpm_chunk(library.config_path, chunk)
            except subprocess.TimeoutExpired:
                timed_out = True
            account_chunk(chunk, result, timed_out)

        # Warm-up: the first chunk of every link runs alone. librosa's
        # resampy kernels are numba-JIT-compiled into a cache shared by all
        # subprocesses (inside site-packages); concurrent cold-start compiles
        # corrupt it and later loads segfault at NULL. One serial chunk
        # populates the cache, after which parallel readers are safe.
        if budget_left() and not redis_manager.is_bpm_backfill_cancelled(library_id):
            warm_chunk = next(chunk_iter, None)
            if warm_chunk is not None:
                run_serial_chunk(warm_chunk)

        with ThreadPoolExecutor(max_workers=workers) as pool:

            def submit_next() -> bool:
                if not budget_left() or redis_manager.is_bpm_backfill_cancelled(library_id):
                    return False
                chunk = next(chunk_iter, None)
                if chunk is None:
                    return False
                future = pool.submit(_run_autobpm_chunk, library.config_path, chunk)
                in_flight[future] = chunk
                return True

            for _ in range(workers):
                if not submit_next():
                    break

            while in_flight:
                done, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    chunk = in_flight.pop(future)
                    result = None
                    timed_out = False
                    try:
                        result = future.result()
                    except subprocess.TimeoutExpired:
                        timed_out = True
                    account_chunk(chunk, result, timed_out)
                    submit_next()

        if redis_manager.is_bpm_backfill_cancelled(library_id):
            redis_manager.clear_bpm_backfill_cancel(library_id)
            finalize("cancelled", TaskStatus.FAILED.value,
                     {"cancelled": True, "processed": processed, "failed": failed})
            logger.info("bpm_backfill cancelled for library %s at %d/%d", library_id, processed, total)
            return {"status": "cancelled", "processed": processed, "total": total}

        remaining = [
            i for i in beets_service.get_item_ids_missing_bpm(library.database_path)
            if i not in redis_manager.get_bpm_failed_items(library_id)
        ]
        if remaining:
            requeue_next_link()
            logger.info("bpm_backfill link done for library %s: %d/%d, %d remaining — chaining next link",
                        library_id, processed + failed, total, len(remaining))
            return {"status": "chained", "processed": processed, "failed": failed, "total": total}

        final = "completed" if failed == 0 else "completed_with_errors"
        store_rate()
        finalize(final, TaskStatus.COMPLETED.value,
                 {"processed": processed, "failed": failed, "total": total})
        logger.info("bpm_backfill done for library %s: %d ok, %d failed of %d",
                    library_id, processed, failed, total)
        return {"status": final, "processed": processed, "failed": failed, "total": total}

    except SoftTimeLimitExceeded:
        # Safety net — the link budget should end the link long before celery's
        # limit. Hand over to a fresh link.
        logger.warning("bpm_backfill: link hit celery soft time limit for library %s, chaining", library_id)
        requeue_next_link()
        return {"status": "chained", "processed": processed, "failed": failed, "total": total}

    except Exception as exc:  # noqa: BLE001 — surface any failure on the job status
        logger.exception("bpm_backfill failed for library %s", library_id)
        last_error = str(exc)
        publish("failed", eta=0)
        if event_id:
            task_event_service.record_completion(
                event_id=event_id,
                status=TaskStatus.FAILED.value,
                metadata={"error": str(exc)},
            )
        return {"status": "failed", "error": str(exc)}

    finally:
        if lock_acquired:
            redis_manager.release_operation_lock(library_id, BPM_BACKFILL_OPERATION)
        redis_manager.release_bpm_link_lock(library_id)
        task_event_service.close()
        db.close()


@celery_app.task(name="maintenance.resume_stalled_bpm_backfills")
def resume_stalled_bpm_backfills() -> Dict[str, Any]:
    """Re-enqueue BPM backfill jobs whose heartbeat went stale.

    Runs via celery beat. A link publishes the status hash at least once per
    finished chunk; if a job is 'running'/'queued' but its updated_at is
    older than BPM_RESUME_STALE_SECONDS, its link died without finalizing
    (worker SIGKILLed — deploy, crash, OOM) and the chain needs a restart.
    The link lock makes an accidental double fire harmless.
    """
    db = SessionLocal()
    redis_manager = get_redis_key_manager(settings.redis_url)
    resumed: List[int] = []
    try:
        now = datetime.now(timezone.utc)
        for library in db.query(Library).all():
            status = redis_manager.get_bpm_backfill_status(library.id)
            if not status or status.get("status") not in ("running", "queued"):
                continue
            job_id = status.get("job_id")
            updated_at = status.get("updated_at")
            if not job_id or not updated_at:
                continue
            try:
                age = (now - datetime.fromisoformat(updated_at)).total_seconds()
            except ValueError:
                continue
            if age < BPM_RESUME_STALE_SECONDS:
                continue
            logger.warning(
                "bpm_backfill job %s on library %s stalled for %ds — re-enqueueing",
                job_id, library.id, int(age),
            )
            # Touch the heartbeat first so the next beat tick doesn't fire
            # again before the new link starts publishing.
            redis_manager.set_bpm_backfill_status(
                library.id,
                status=status.get("status", "running"),
                total=int(status.get("total") or 0),
                processed=int(status.get("processed") or 0),
                failed=int(status.get("failed") or 0),
                job_id=job_id,
                error=status.get("error"),
                eta_seconds=status.get("eta_seconds"),
            )
            bpm_backfill.delay(library_id=library.id, job_id=job_id)
            resumed.append(library.id)
        return {"status": "completed", "resumed": resumed}
    except Exception as e:
        logger.exception("resume_stalled_bpm_backfills failed")
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()
