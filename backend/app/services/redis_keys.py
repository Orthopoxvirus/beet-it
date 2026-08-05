"""Redis key management for import folder watchers and scanning.

Key Structure:
- watcher:debounce:{library_id}      # TTL key, presence = debounce active
- watcher:state:{library_id}         # Hash: {active, last_event, pending_scan}
- watcher:heartbeat:{library_id}     # TTL key for watcher health monitoring
- scan:progress:{library_id}         # Hash: {status, processed, total, current_file, scan_id}
- scan:queue:{library_id}            # List: queued scan requests
- operation:lock:{library_id}        # Set: running operation types
- scan:channel:{library_id}          # Pub/sub channel for progress updates
- beets:analysis:{job_id}            # Hash: {status, result, error, started_at, completed_at}
- import:tree:{library_id}           # String: JSON-serialized import tree (TTL 5 min)
- beets:album:{library_id}:{path_hash}  # String: JSON-serialized analysis result (TTL 7 days)
- activity:active                     # Sorted set: active task index (member: {task_type}:{event_id}, score: started_at)
- activity:events                     # Pub/sub channel: global activity events for SSE
- activity:progress:{event_id}        # Hash: per-task progress details (TTL 2 hours)
- import:job:{job_id}                # Hash: {status, library_id, album_path, candidate_json, started_at, completed_at, destination, error_code, error_message}
- import:library:{library_id}:jobs   # Set: active import job IDs for library
- import:library:{library_id}:status # Hash: album_path_hash -> status for bulk lookup
- import:library:{library_id}:done   # Hash: completed imports (TTL 24 hours, copy mode only)
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from redis import Redis

logger = logging.getLogger(__name__)

# Key prefixes
DEBOUNCE_PREFIX = "watcher:debounce:"
WATCHER_STATE_PREFIX = "watcher:state:"
WATCHER_HEARTBEAT_PREFIX = "watcher:heartbeat:"
SCAN_PROGRESS_PREFIX = "scan:progress:"
SCAN_QUEUE_PREFIX = "scan:queue:"
OPERATION_LOCK_PREFIX = "operation:lock:"
SCAN_CHANNEL_PREFIX = "scan:channel:"
BEETS_ANALYSIS_PREFIX = "beets:analysis:"
BPM_BACKFILL_PREFIX = "maintenance:bpm:"              # Hash: per-library backfill job status
BPM_BACKFILL_CANCEL_PREFIX = "maintenance:bpm:cancel:"  # String flag: cancellation requested
IMPORT_TREE_PREFIX = "import:tree:"
BEETS_ALBUM_PREFIX = "beets:album:"
# Bump when the cached analysis payload shape changes so stale-schema entries
# (keyed under an older version) are never read and simply age out via TTL.
# v2: track_changes rows carry explicit local_path/local_title pairing.
BEETS_ALBUM_SCHEMA_VERSION = "v2"

# Activity monitor keys
ACTIVITY_ACTIVE_KEY = "activity:active"           # Sorted set: active task index
ACTIVITY_CHANNEL = "activity:events"              # Pub/sub: global activity events
ACTIVITY_PROGRESS_PREFIX = "activity:progress:"   # Hash: per-task progress details

# Analysis queue keys
BEETS_ANALYSIS_QUEUE_PREFIX = "beets:queue:"          # List: queued album paths (JSON items)
BEETS_ACTIVE_ANALYSES_PREFIX = "beets:active_analyses:"  # Hash: active job_id -> album_path+started_at

# Import job keys
IMPORT_JOB_PREFIX = "import:job:"                      # Hash: per-job metadata
IMPORT_LIBRARY_JOBS_PREFIX = "import:library:"         # Format: import:library:{library_id}:jobs - Set of active job IDs
IMPORT_LIBRARY_STATUS_PREFIX = "import:library:"       # Format: import:library:{library_id}:status - Hash: album_path_hash -> status
IMPORT_LIBRARY_DONE_PREFIX = "import:library:"         # Format: import:library:{library_id}:done - Hash: completed imports

# Cover art discovery cache key
COVER_DISCOVERED_PREFIX = "cover:discovered:"          # Format: cover:discovered:{db_path_hash}:{album_id} - Discovered cover art path (TTL 7 days)

# Library batch update keys
BATCH_UPDATE_PREFIX = "library:batch_update:"          # Format: library:batch_update:{job_id} - Hash: batch update job status (TTL 24 hours)

# Audio-op keys (WAV→FLAC convert / duplicate-WAV cleanup on pre-import folders)
AUDIO_OP_PREFIX = "beets:audio_op:"                    # Hash: beets:audio_op:{job_id} - per-job status + result
AUDIO_OP_LOCK_PREFIX = "beets:audio_op:lock:"          # String: per-(library, album) lock to bar concurrent ops


class RedisKeyManager:
    """Manages Redis keys for watcher and scan state."""

    def __init__(self, redis_client: Redis):
        """Initialize with a Redis client.

        Args:
            redis_client: An active Redis connection.
        """
        self.redis = redis_client

    # --- Debounce Key Management ---

    def set_debounce(self, library_id: int, ttl_seconds: int = 30) -> bool:
        """Set a debounce key with TTL.

        Args:
            library_id: The library ID.
            ttl_seconds: Time-to-live in seconds (default 30s).

        Returns:
            True if key was set, False if it already existed.
        """
        key = f"{DEBOUNCE_PREFIX}{library_id}"
        return bool(self.redis.set(key, "1", nx=True, ex=ttl_seconds))

    def refresh_debounce(self, library_id: int, ttl_seconds: int = 30) -> bool:
        """Refresh the debounce timer by updating TTL.

        Args:
            library_id: The library ID.
            ttl_seconds: New time-to-live in seconds.

        Returns:
            True if key existed and TTL was updated.
        """
        key = f"{DEBOUNCE_PREFIX}{library_id}"
        # Set with XX flag - only update if exists
        return bool(self.redis.set(key, "1", xx=True, ex=ttl_seconds))

    def check_debounce(self, library_id: int) -> bool:
        """Check if debounce is active.

        Args:
            library_id: The library ID.

        Returns:
            True if debounce is active.
        """
        key = f"{DEBOUNCE_PREFIX}{library_id}"
        return bool(self.redis.exists(key))

    def clear_debounce(self, library_id: int) -> bool:
        """Clear the debounce key.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{DEBOUNCE_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    def get_debounce_ttl(self, library_id: int) -> int:
        """Get remaining TTL on debounce key.

        Args:
            library_id: The library ID.

        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if no TTL.
        """
        key = f"{DEBOUNCE_PREFIX}{library_id}"
        return self.redis.ttl(key)

    # --- Watcher State Management ---

    def set_watcher_state(
        self,
        library_id: int,
        active: bool,
        last_event: Optional[datetime] = None,
        pending_scan: bool = False,
    ) -> None:
        """Set watcher state.

        Args:
            library_id: The library ID.
            active: Whether the watcher is running.
            last_event: Timestamp of last filesystem event.
            pending_scan: Whether a scan is pending.
        """
        key = f"{WATCHER_STATE_PREFIX}{library_id}"
        state = {
            "active": "1" if active else "0",
            "pending_scan": "1" if pending_scan else "0",
        }
        if last_event:
            state["last_event"] = last_event.isoformat()
        self.redis.hset(key, mapping=state)

    def get_watcher_state(self, library_id: int) -> Optional[Dict[str, Any]]:
        """Get watcher state.

        Args:
            library_id: The library ID.

        Returns:
            Dict with active, last_event, pending_scan or None if not found.
        """
        key = f"{WATCHER_STATE_PREFIX}{library_id}"
        state = self.redis.hgetall(key)
        if not state:
            return None

        result = {
            "active": state.get(b"active", b"0") == b"1" if isinstance(state.get(b"active"), bytes) else state.get("active", "0") == "1",
            "pending_scan": state.get(b"pending_scan", b"0") == b"1" if isinstance(state.get(b"pending_scan"), bytes) else state.get("pending_scan", "0") == "1",
        }

        last_event = state.get(b"last_event") or state.get("last_event")
        if last_event:
            if isinstance(last_event, bytes):
                last_event = last_event.decode()
            result["last_event"] = datetime.fromisoformat(last_event)
        else:
            result["last_event"] = None

        return result

    def is_watcher_active(self, library_id: int) -> bool:
        """Check if watcher is active.

        Args:
            library_id: The library ID.

        Returns:
            True if watcher is active.
        """
        state = self.get_watcher_state(library_id)
        return state.get("active", False) if state else False

    def clear_watcher_state(self, library_id: int) -> bool:
        """Clear watcher state.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{WATCHER_STATE_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Watcher Heartbeat ---

    def set_heartbeat(self, library_id: int, ttl_seconds: int = 15) -> None:
        """Set watcher heartbeat with TTL.

        Args:
            library_id: The library ID.
            ttl_seconds: Time-to-live in seconds (default 15s).
        """
        key = f"{WATCHER_HEARTBEAT_PREFIX}{library_id}"
        self.redis.set(key, datetime.now(timezone.utc).isoformat(), ex=ttl_seconds)

    def check_heartbeat(self, library_id: int) -> bool:
        """Check if watcher heartbeat is alive.

        Args:
            library_id: The library ID.

        Returns:
            True if heartbeat exists (watcher is healthy).
        """
        key = f"{WATCHER_HEARTBEAT_PREFIX}{library_id}"
        return bool(self.redis.exists(key))

    def clear_heartbeat(self, library_id: int) -> bool:
        """Clear watcher heartbeat.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{WATCHER_HEARTBEAT_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Scan Progress ---

    def set_scan_progress(
        self,
        library_id: int,
        scan_id: int,
        status: str,
        items_total: int = 0,
        items_processed: int = 0,
        current_file: Optional[str] = None,
        started_at: Optional[datetime] = None,
    ) -> None:
        """Set scan progress.

        Args:
            library_id: The library ID.
            scan_id: The scan ID.
            status: Scan status (scanning, extracting_metadata, completed, failed).
            items_total: Total items to process.
            items_processed: Items processed so far.
            current_file: Currently processing file path.
            started_at: When the scan started.
        """
        key = f"{SCAN_PROGRESS_PREFIX}{library_id}"
        progress = {
            "scan_id": str(scan_id),
            "status": status,
            "items_total": str(items_total),
            "items_processed": str(items_processed),
        }
        if current_file:
            progress["current_file"] = current_file
        if started_at:
            progress["started_at"] = started_at.isoformat()
        self.redis.hset(key, mapping=progress)

    def get_scan_progress(self, library_id: int) -> Optional[Dict[str, Any]]:
        """Get scan progress.

        Args:
            library_id: The library ID.

        Returns:
            Dict with scan progress info or None if not found.
        """
        key = f"{SCAN_PROGRESS_PREFIX}{library_id}"
        progress = self.redis.hgetall(key)
        if not progress:
            return None

        # Handle both bytes and string keys
        def get_value(key_name: str) -> Optional[str]:
            val = progress.get(key_name.encode()) or progress.get(key_name)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else val

        result = {
            "scan_id": int(get_value("scan_id") or 0),
            "status": get_value("status") or "unknown",
            "items_total": int(get_value("items_total") or 0),
            "items_processed": int(get_value("items_processed") or 0),
            "current_file": get_value("current_file"),
        }

        started_at = get_value("started_at")
        if started_at:
            result["started_at"] = datetime.fromisoformat(started_at)

        return result

    def clear_scan_progress(self, library_id: int) -> bool:
        """Clear scan progress.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{SCAN_PROGRESS_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Scan Queue ---

    def enqueue_scan(self, library_id: int, triggered_by: str = "manual") -> int:
        """Add a scan request to the queue.

        Args:
            library_id: The library ID.
            triggered_by: What triggered the scan (manual, watcher).

        Returns:
            Position in queue (1-indexed).
        """
        key = f"{SCAN_QUEUE_PREFIX}{library_id}"
        request = json.dumps({
            "triggered_by": triggered_by,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })
        return self.redis.rpush(key, request)

    def dequeue_scan(self, library_id: int) -> Optional[Dict[str, Any]]:
        """Remove and return the next scan request from the queue.

        Args:
            library_id: The library ID.

        Returns:
            Scan request dict or None if queue is empty.
        """
        key = f"{SCAN_QUEUE_PREFIX}{library_id}"
        request = self.redis.lpop(key)
        if request:
            if isinstance(request, bytes):
                request = request.decode()
            return json.loads(request)
        return None

    def peek_scan_queue(self, library_id: int) -> Optional[Dict[str, Any]]:
        """Peek at the next scan request without removing it.

        Args:
            library_id: The library ID.

        Returns:
            Scan request dict or None if queue is empty.
        """
        key = f"{SCAN_QUEUE_PREFIX}{library_id}"
        request = self.redis.lindex(key, 0)
        if request:
            if isinstance(request, bytes):
                request = request.decode()
            return json.loads(request)
        return None

    def get_scan_queue_length(self, library_id: int) -> int:
        """Get the number of scans in the queue.

        Args:
            library_id: The library ID.

        Returns:
            Queue length.
        """
        key = f"{SCAN_QUEUE_PREFIX}{library_id}"
        return self.redis.llen(key)

    def clear_scan_queue(self, library_id: int) -> bool:
        """Clear the scan queue.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{SCAN_QUEUE_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Operation Lock ---

    def acquire_operation_lock(self, library_id: int, operation_type: str) -> bool:
        """Acquire an operation lock.

        Args:
            library_id: The library ID.
            operation_type: Type of operation (import, tag_modify, move, delete).

        Returns:
            True if lock was acquired.
        """
        key = f"{OPERATION_LOCK_PREFIX}{library_id}"
        return bool(self.redis.sadd(key, operation_type))

    def release_operation_lock(self, library_id: int, operation_type: str) -> bool:
        """Release an operation lock.

        Args:
            library_id: The library ID.
            operation_type: Type of operation to release.

        Returns:
            True if lock was released.
        """
        key = f"{OPERATION_LOCK_PREFIX}{library_id}"
        return bool(self.redis.srem(key, operation_type))

    def check_operation_lock(self, library_id: int, operation_type: str) -> bool:
        """Check if an operation lock is held.

        Args:
            library_id: The library ID.
            operation_type: Type of operation to check.

        Returns:
            True if lock is held.
        """
        key = f"{OPERATION_LOCK_PREFIX}{library_id}"
        return bool(self.redis.sismember(key, operation_type))

    def get_active_operations(self, library_id: int) -> List[str]:
        """Get all active operations for a library.

        Args:
            library_id: The library ID.

        Returns:
            List of operation types currently locked.
        """
        key = f"{OPERATION_LOCK_PREFIX}{library_id}"
        members = self.redis.smembers(key)
        return [m.decode() if isinstance(m, bytes) else m for m in members]

    def has_blocking_operations(self, library_id: int) -> bool:
        """Check if any blocking operations are running.

        Args:
            library_id: The library ID.

        Returns:
            True if any operations are blocking.
        """
        return len(self.get_active_operations(library_id)) > 0

    def clear_operation_locks(self, library_id: int) -> bool:
        """Clear all operation locks for a library.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{OPERATION_LOCK_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Pub/Sub Helpers ---

    def get_scan_channel(self, library_id: int) -> str:
        """Get the pub/sub channel name for scan progress.

        Args:
            library_id: The library ID.

        Returns:
            Channel name.
        """
        return f"{SCAN_CHANNEL_PREFIX}{library_id}"

    def publish_scan_event(self, library_id: int, event_type: str, data: Dict[str, Any]) -> int:
        """Publish a scan event to the pub/sub channel.

        Args:
            library_id: The library ID.
            event_type: Event type (scan_started, scan_progress, etc.).
            data: Event data.

        Returns:
            Number of subscribers that received the message.
        """
        channel = self.get_scan_channel(library_id)
        message = json.dumps({
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return self.redis.publish(channel, message)

    def subscribe_scan_events(self, library_id: int):
        """Get a pub/sub subscription for scan events.

        Args:
            library_id: The library ID.

        Returns:
            Redis pubsub object subscribed to the channel.
        """
        pubsub = self.redis.pubsub()
        channel = self.get_scan_channel(library_id)
        pubsub.subscribe(channel)
        return pubsub

    # --- Beets Analysis Progress ---

    def set_beets_analysis_result(
        self,
        job_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        ttl_seconds: int = 3600,  # 1 hour default
    ) -> None:
        """Set beets analysis result.

        Args:
            job_id: The job ID.
            status: Status (analyzing, completed, failed).
            result: Analysis result data (for completed status).
            error: Error information (for failed status).
            started_at: When the analysis started.
            completed_at: When the analysis completed.
            ttl_seconds: Time-to-live for the result (default 1 hour).
        """
        key = f"{BEETS_ANALYSIS_PREFIX}{job_id}"
        data = {
            "status": status,
        }
        if result:
            data["result"] = json.dumps(result)
        if error:
            data["error"] = json.dumps(error)
        if started_at:
            data["started_at"] = started_at.isoformat()
        if completed_at:
            data["completed_at"] = completed_at.isoformat()

        self.redis.hset(key, mapping=data)
        self.redis.expire(key, ttl_seconds)

    def get_beets_analysis_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get beets analysis result.

        Args:
            job_id: The job ID.

        Returns:
            Dict with analysis result or None if not found.
        """
        key = f"{BEETS_ANALYSIS_PREFIX}{job_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None

        # Handle both bytes and string keys
        def get_value(key_name: str) -> Optional[str]:
            val = data.get(key_name.encode()) or data.get(key_name)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else val

        result = {
            "status": get_value("status") or "unknown",
        }

        result_json = get_value("result")
        if result_json:
            result["result"] = json.loads(result_json)

        error_json = get_value("error")
        if error_json:
            result["error"] = json.loads(error_json)

        started_at = get_value("started_at")
        if started_at:
            result["started_at"] = datetime.fromisoformat(started_at)

        completed_at = get_value("completed_at")
        if completed_at:
            result["completed_at"] = datetime.fromisoformat(completed_at)

        return result

    def clear_beets_analysis_result(self, job_id: str) -> bool:
        """Clear beets analysis result.

        Args:
            job_id: The job ID.

        Returns:
            True if key was deleted.
        """
        key = f"{BEETS_ANALYSIS_PREFIX}{job_id}"
        return bool(self.redis.delete(key))

    # --- BPM backfill (library maintenance) ---

    def set_bpm_backfill_status(
        self,
        library_id: int,
        status: str,
        total: int = 0,
        processed: int = 0,
        failed: int = 0,
        job_id: Optional[str] = None,
        error: Optional[str] = None,
        active_seconds: Optional[float] = None,
        eta_seconds: Optional[int] = None,
        workers: Optional[int] = None,
        event_id: Optional[int] = None,
        ttl_seconds: int = 24 * 3600,
    ) -> None:
        """Persist the per-library BPM backfill job status (frontend polls it).

        The job runs as a chain of short task links; this hash is the shared
        job state that survives across links (and worker restarts).
        """
        key = f"{BPM_BACKFILL_PREFIX}{library_id}"
        data: Dict[str, str] = {
            "status": status,
            "total": str(total),
            "processed": str(processed),
            "failed": str(failed),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if job_id is not None:
            data["job_id"] = job_id
        # error/eta are cleared when passed as None (a healthy update must not
        # keep showing a stale error or countdown); the remaining fields merge
        # so links can update partially.
        if error is not None:
            data["error"] = error
        else:
            self.redis.hdel(key, "error")
        if eta_seconds is not None:
            data["eta_seconds"] = str(eta_seconds)
        else:
            self.redis.hdel(key, "eta_seconds")
        if active_seconds is not None:
            data["active_seconds"] = str(active_seconds)
        if workers is not None:
            data["workers"] = str(workers)
        if event_id is not None:
            data["event_id"] = str(event_id)
        self.redis.hset(key, mapping=data)
        self.redis.expire(key, ttl_seconds)

    def clear_bpm_backfill_status(self, library_id: int) -> None:
        """Drop the whole status hash — a new job must not inherit stale fields."""
        self.redis.delete(f"{BPM_BACKFILL_PREFIX}{library_id}")

    def get_bpm_backfill_status(self, library_id: int) -> Optional[Dict[str, Any]]:
        """Current BPM backfill status for a library, or None if none ran recently."""
        key = f"{BPM_BACKFILL_PREFIX}{library_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None

        def val(name: str) -> Optional[str]:
            v = data.get(name.encode()) or data.get(name)
            if v is None:
                return None
            return v.decode() if isinstance(v, bytes) else v

        out: Dict[str, Any] = {
            "status": val("status") or "unknown",
            "total": int(val("total") or 0),
            "processed": int(val("processed") or 0),
            "failed": int(val("failed") or 0),
        }
        if val("job_id"):
            out["job_id"] = val("job_id")
        if val("error"):
            out["error"] = val("error")
        if val("updated_at"):
            out["updated_at"] = val("updated_at")
        if val("active_seconds"):
            out["active_seconds"] = float(val("active_seconds"))
        if val("eta_seconds"):
            out["eta_seconds"] = int(float(val("eta_seconds")))
        if val("workers"):
            out["workers"] = int(val("workers"))
        if val("event_id"):
            out["event_id"] = int(val("event_id"))
        return out

    # A link-lock (SET NX + TTL) makes chain links self-deduplicating: if the
    # resume guard re-enqueues while a link is still alive, the duplicate sees
    # the lock and exits. The TTL covers a worst-case link (time budget plus
    # one full chunk timeout), so a SIGKILLed link never blocks resumption.
    def acquire_bpm_link_lock(self, library_id: int, ttl_seconds: int) -> bool:
        return bool(
            self.redis.set(f"{BPM_BACKFILL_PREFIX}link_lock:{library_id}", "1", nx=True, ex=ttl_seconds)
        )

    def release_bpm_link_lock(self, library_id: int) -> None:
        self.redis.delete(f"{BPM_BACKFILL_PREFIX}link_lock:{library_id}")

    # Items written off after BPM_MAX_ITEM_ATTEMPTS tries without a stored
    # bpm (unreadable/corrupt files). Excluded from later links so the chain
    # terminates instead of retrying them forever; cleared on new job start.
    def add_bpm_failed_items(self, library_id: int, item_ids: List[int], ttl_seconds: int = 24 * 3600) -> None:
        if not item_ids:
            return
        key = f"{BPM_BACKFILL_PREFIX}failed_items:{library_id}"
        self.redis.sadd(key, *[str(i) for i in item_ids])
        self.redis.expire(key, ttl_seconds)

    def get_bpm_failed_items(self, library_id: int) -> set:
        key = f"{BPM_BACKFILL_PREFIX}failed_items:{library_id}"
        members = self.redis.smembers(key) or set()
        return {int(m.decode() if isinstance(m, bytes) else m) for m in members}

    def clear_bpm_failed_items(self, library_id: int) -> None:
        self.redis.delete(f"{BPM_BACKFILL_PREFIX}failed_items:{library_id}")

    def incr_bpm_attempts(self, library_id: int, item_ids: List[int], ttl_seconds: int = 24 * 3600) -> Dict[int, int]:
        """Bump per-item attempt counters; returns the new counts."""
        if not item_ids:
            return {}
        key = f"{BPM_BACKFILL_PREFIX}attempts:{library_id}"
        pipe = self.redis.pipeline()
        for item_id in item_ids:
            pipe.hincrby(key, str(item_id), 1)
        counts = pipe.execute()
        self.redis.expire(key, ttl_seconds)
        return dict(zip(item_ids, (int(c) for c in counts)))

    def clear_bpm_attempts(self, library_id: int) -> None:
        self.redis.delete(f"{BPM_BACKFILL_PREFIX}attempts:{library_id}")

    # Measured wall-clock seconds per track of the last finished job — used
    # for the pre-flight duration estimate shown before starting a run.
    def set_bpm_track_seconds(self, library_id: int, seconds: float, ttl_seconds: int = 90 * 24 * 3600) -> None:
        self.redis.set(f"{BPM_BACKFILL_PREFIX}track_seconds:{library_id}", str(seconds), ex=ttl_seconds)

    def get_bpm_track_seconds(self, library_id: int) -> Optional[float]:
        v = self.redis.get(f"{BPM_BACKFILL_PREFIX}track_seconds:{library_id}")
        if v is None:
            return None
        try:
            return float(v.decode() if isinstance(v, bytes) else v)
        except ValueError:
            return None

    def request_bpm_backfill_cancel(self, library_id: int, ttl_seconds: int = 24 * 3600) -> None:
        """Flag the running backfill for cancellation (task checks between chunks)."""
        self.redis.set(f"{BPM_BACKFILL_CANCEL_PREFIX}{library_id}", "1", ex=ttl_seconds)

    def is_bpm_backfill_cancelled(self, library_id: int) -> bool:
        return bool(self.redis.get(f"{BPM_BACKFILL_CANCEL_PREFIX}{library_id}"))

    def clear_bpm_backfill_cancel(self, library_id: int) -> None:
        self.redis.delete(f"{BPM_BACKFILL_CANCEL_PREFIX}{library_id}")

    # --- Audio Ops (WAV→FLAC convert / duplicate-WAV cleanup) ---

    def set_audio_op_status(
        self,
        job_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        ttl_seconds: int = 3600,  # 1 hour
    ) -> None:
        """Set the status of an audio-op job (convert / dedup).

        Mirrors :meth:`set_beets_analysis_result`: a small hash the frontend
        polls until ``status`` is ``completed`` or ``failed``.
        """
        key = f"{AUDIO_OP_PREFIX}{job_id}"
        data: Dict[str, str] = {"status": status}
        if result is not None:
            data["result"] = json.dumps(result)
        if error is not None:
            data["error"] = error
        if started_at:
            data["started_at"] = started_at.isoformat()
        if completed_at:
            data["completed_at"] = completed_at.isoformat()

        self.redis.hset(key, mapping=data)
        self.redis.expire(key, ttl_seconds)

    def get_audio_op_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an audio-op job, or None if unknown/expired."""
        key = f"{AUDIO_OP_PREFIX}{job_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None

        def get_value(key_name: str) -> Optional[str]:
            val = data.get(key_name.encode()) or data.get(key_name)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else val

        result: Dict[str, Any] = {"status": get_value("status") or "unknown"}
        result_json = get_value("result")
        if result_json:
            result["result"] = json.loads(result_json)
        error = get_value("error")
        if error:
            result["error"] = error
        started_at = get_value("started_at")
        if started_at:
            result["started_at"] = datetime.fromisoformat(started_at)
        completed_at = get_value("completed_at")
        if completed_at:
            result["completed_at"] = datetime.fromisoformat(completed_at)
        return result

    def _audio_op_lock_key(self, library_id: int, album_path: str) -> str:
        digest = hashlib.sha256(album_path.encode()).hexdigest()[:16]
        return f"{AUDIO_OP_LOCK_PREFIX}{library_id}:{digest}"

    def acquire_audio_op_lock(
        self, library_id: int, album_path: str, job_id: str, ttl_seconds: int = 600
    ) -> bool:
        """Atomically claim the convert/dedup lock for one album.

        Returns True if the lock was acquired, False if another op already holds
        it (so the caller can return 409). Auto-expires so a crashed worker can't
        wedge the album forever.
        """
        key = self._audio_op_lock_key(library_id, album_path)
        return bool(self.redis.set(key, job_id, nx=True, ex=ttl_seconds))

    def release_audio_op_lock(self, library_id: int, album_path: str) -> bool:
        """Release the convert/dedup lock for one album."""
        key = self._audio_op_lock_key(library_id, album_path)
        return bool(self.redis.delete(key))

    # --- Import Tree Cache ---

    def set_import_tree_cache(
        self,
        library_id: int,
        children_data: List[Dict[str, Any]],
        ttl_seconds: int = 300,  # 5 minutes
    ) -> None:
        """Cache the import tree for a library.

        Args:
            library_id: The library ID.
            children_data: The serialized tree children (list of dicts).
            ttl_seconds: Time-to-live in seconds (default 5 min).
        """
        key = f"{IMPORT_TREE_PREFIX}{library_id}"
        self.redis.set(key, json.dumps(children_data), ex=ttl_seconds)

    def get_import_tree_cache(self, library_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached import tree for a library.

        Args:
            library_id: The library ID.

        Returns:
            Parsed list of tree node dicts, or None if not cached.
        """
        key = f"{IMPORT_TREE_PREFIX}{library_id}"
        data = self.redis.get(key)
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)

    def invalidate_import_tree_cache(self, library_id: int) -> bool:
        """Invalidate the import tree cache for a library.

        Args:
            library_id: The library ID.

        Returns:
            True if key was deleted.
        """
        key = f"{IMPORT_TREE_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Beets Album Path Cache ---

    def _album_cache_key(self, library_id: int, album_path: str) -> str:
        """Generate a Redis key for album path analysis cache."""
        path_hash = hashlib.md5(album_path.encode()).hexdigest()
        return f"{BEETS_ALBUM_PREFIX}{BEETS_ALBUM_SCHEMA_VERSION}:{library_id}:{path_hash}"

    def set_beets_album_result(
        self,
        library_id: int,
        album_path: str,
        result: Dict[str, Any],
        ttl_seconds: int = 86400 * 7,  # 7 days
    ) -> None:
        """Cache beets analysis result by album path.

        Args:
            library_id: The library ID.
            album_path: Absolute path to the album folder.
            result: The analysis result dict to cache.
            ttl_seconds: Time-to-live in seconds (default 7 days).
        """
        key = self._album_cache_key(library_id, album_path)
        self.redis.set(key, json.dumps(result), ex=ttl_seconds)

    def get_beets_album_result(
        self, library_id: int, album_path: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached beets analysis result by album path.

        Args:
            library_id: The library ID.
            album_path: Absolute path to the album folder.

        Returns:
            Parsed result dict, or None if not cached.
        """
        key = self._album_cache_key(library_id, album_path)
        data = self.redis.get(key)
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)

    def invalidate_beets_album_result(self, library_id: int, album_path: str) -> bool:
        """Invalidate cached beets analysis result for an album path.

        Args:
            library_id: The library ID.
            album_path: Absolute path to the album folder.

        Returns:
            True if key was deleted.
        """
        key = self._album_cache_key(library_id, album_path)
        return bool(self.redis.delete(key))

    def check_beets_album_cache_exists(
        self, library_id: int, album_paths: List[str]
    ) -> Dict[str, bool]:
        """Check cache existence for multiple album paths using Redis pipelining.

        This method only checks for key existence without retrieving the actual
        cached data, making it efficient for bulk status checks.

        Args:
            library_id: The library ID.
            album_paths: List of album paths to check.

        Returns:
            Dict mapping each album path to its cache existence status (True if cached).
        """
        if not album_paths:
            return {}

        # Use pipelining for efficient bulk key existence checks
        pipe = self.redis.pipeline()
        for album_path in album_paths:
            key = self._album_cache_key(library_id, album_path)
            pipe.exists(key)

        results = pipe.execute()

        # Map results back to album paths
        return {
            album_path: bool(exists)
            for album_path, exists in zip(album_paths, results)
        }

    def get_beets_album_cache_key(self, library_id: int, album_path: str) -> str:
        """Get the Redis cache key for a beets album analysis result.

        This is a public accessor for the cache key format, useful for
        external status checking operations.

        Args:
            library_id: The library ID.
            album_path: Absolute path to the album folder.

        Returns:
            The Redis key string.
        """
        return self._album_cache_key(library_id, album_path)

    # --- Activity Monitor ---

    def add_to_activity_index(
        self,
        task_type: str,
        event_id: int,
        started_at: datetime,
    ) -> bool:
        """Add a task to the active task index.

        Args:
            task_type: Type of task (scan, analysis, etc.).
            event_id: The event ID from the database.
            started_at: When the task started.

        Returns:
            True if the task was added.
        """
        member = f"{task_type}:{event_id}"
        score = started_at.timestamp()
        return bool(self.redis.zadd(ACTIVITY_ACTIVE_KEY, {member: score}))

    def remove_from_activity_index(self, task_type: str, event_id: int) -> bool:
        """Remove a task from the active task index.

        Args:
            task_type: Type of task.
            event_id: The event ID.

        Returns:
            True if the task was removed.
        """
        member = f"{task_type}:{event_id}"
        return bool(self.redis.zrem(ACTIVITY_ACTIVE_KEY, member))

    def get_active_task_members(self) -> List[str]:
        """Get all active task members from the sorted set.

        Returns:
            List of member strings in format "{task_type}:{event_id}".
        """
        members = self.redis.zrange(ACTIVITY_ACTIVE_KEY, 0, -1)
        return [m.decode() if isinstance(m, bytes) else m for m in members]

    def get_active_task_count(self) -> int:
        """Get the number of active tasks.

        Returns:
            Number of tasks in the active index.
        """
        return self.redis.zcard(ACTIVITY_ACTIVE_KEY)

    def cleanup_stale_activity_entries(self, max_age_seconds: int = 7200) -> int:
        """Remove stale entries from the activity index.

        Used by Celery Beat task for crash recovery. Removes entries
        older than max_age_seconds (default 2 hours).

        Args:
            max_age_seconds: Maximum age in seconds before considering stale.

        Returns:
            Number of entries removed.
        """
        import time
        cutoff = time.time() - max_age_seconds
        return self.redis.zremrangebyscore(ACTIVITY_ACTIVE_KEY, "-inf", cutoff)

    def set_activity_progress(
        self,
        event_id: int,
        task_type: str,
        library_id: int,
        library_slug: str,
        description: str,
        started_at: datetime,
        progress_percent: Optional[float] = None,
        items_total: Optional[int] = None,
        items_processed: Optional[int] = None,
        current_file: Optional[str] = None,
        ttl_seconds: int = 7200,  # 2 hours
    ) -> None:
        """Set progress details for an active task.

        Args:
            event_id: The event ID.
            task_type: Type of task.
            library_id: Library ID.
            library_slug: Library slug.
            description: Task description.
            started_at: When the task started.
            progress_percent: Progress percentage (0-100).
            items_total: Total items (for scan tasks).
            items_processed: Processed items (for scan tasks).
            current_file: Current file being processed.
            ttl_seconds: Time-to-live in seconds (default 2 hours).
        """
        key = f"{ACTIVITY_PROGRESS_PREFIX}{event_id}"
        data = {
            "task_type": task_type,
            "library_id": str(library_id) if library_id is not None else "",
            "library_slug": library_slug,
            "description": description,
            "started_at": started_at.isoformat(),
        }
        if progress_percent is not None:
            data["progress_percent"] = str(progress_percent)
        if items_total is not None:
            data["items_total"] = str(items_total)
        if items_processed is not None:
            data["items_processed"] = str(items_processed)
        if current_file is not None:
            data["current_file"] = current_file

        self.redis.hset(key, mapping=data)
        self.redis.expire(key, ttl_seconds)

    def get_activity_progress(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get progress details for an active task.

        Args:
            event_id: The event ID.

        Returns:
            Dict with progress details or None if not found.
        """
        key = f"{ACTIVITY_PROGRESS_PREFIX}{event_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None

        def get_value(key_name: str) -> Optional[str]:
            val = data.get(key_name.encode()) or data.get(key_name)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else val

        library_id_val = get_value("library_id")
        result = {
            "event_id": event_id,
            "task_type": get_value("task_type"),
            "library_id": int(library_id_val) if library_id_val and library_id_val != "" else None,
            "library_slug": get_value("library_slug"),
            "description": get_value("description"),
        }

        started_at = get_value("started_at")
        if started_at:
            result["started_at"] = datetime.fromisoformat(started_at)

        progress_percent = get_value("progress_percent")
        if progress_percent:
            result["progress_percent"] = float(progress_percent)

        items_total = get_value("items_total")
        if items_total:
            result["items_total"] = int(items_total)

        items_processed = get_value("items_processed")
        if items_processed:
            result["items_processed"] = int(items_processed)

        current_file = get_value("current_file")
        if current_file:
            result["current_file"] = current_file

        return result

    def clear_activity_progress(self, event_id: int) -> bool:
        """Clear progress details for a task.

        Args:
            event_id: The event ID.

        Returns:
            True if key was deleted.
        """
        key = f"{ACTIVITY_PROGRESS_PREFIX}{event_id}"
        return bool(self.redis.delete(key))

    def publish_activity_event(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> int:
        """Publish an activity event to the global pub/sub channel.

        Args:
            event_type: Event type (task_started, task_progress, task_completed, task_failed).
            data: Event data.

        Returns:
            Number of subscribers that received the message.
        """
        message = json.dumps({
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return self.redis.publish(ACTIVITY_CHANNEL, message)

    def subscribe_activity_events(self):
        """Get a pub/sub subscription for activity events.

        Returns:
            Redis pubsub object subscribed to the activity channel.
        """
        pubsub = self.redis.pubsub()
        pubsub.subscribe(ACTIVITY_CHANNEL)
        return pubsub

    # --- Analysis Queue ---

    # Lua script for atomic dequeue-and-dispatch
    # KEYS[1] = queue list key (beets:queue:{library_id})
    # KEYS[2] = active hash key (beets:active_analyses:{library_id})
    # ARGV[1] = concurrency cap
    # ARGV[2] = new job_id
    # ARGV[3] = started_at ISO timestamp
    #
    # Returns: {album_item_json, job_id} if dispatched, nil if at capacity or queue empty
    DEQUEUE_AND_DISPATCH_SCRIPT = """
    local active_count = redis.call('HLEN', KEYS[2])
    if active_count < tonumber(ARGV[1]) then
        local item = redis.call('LPOP', KEYS[1])
        if item then
            local job_data = ARGV[2] .. '|' .. ARGV[3] .. '|' .. item
            local parsed = cjson.decode(item)
            redis.call('HSET', KEYS[2], ARGV[2], job_data)
            return {item, ARGV[2]}
        end
    end
    return nil
    """

    def enqueue_album_analysis(
        self,
        library_id: int,
        album_path: str,
    ) -> int:
        """Add an album to the analysis queue.

        Args:
            library_id: The library ID.
            album_path: Absolute path to the album folder.

        Returns:
            Position in queue (1-indexed).
        """
        key = f"{BEETS_ANALYSIS_QUEUE_PREFIX}{library_id}"
        item = json.dumps({
            "album_path": album_path,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })
        return self.redis.rpush(key, item)

    def dequeue_next_album(
        self,
        library_id: int,
        concurrency_cap: int,
        job_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Atomically dequeue next album and register as active if under concurrency cap.

        Uses a Lua script to ensure atomicity of the dequeue + register operation.

        Args:
            library_id: The library ID.
            concurrency_cap: Maximum concurrent analyses allowed.
            job_id: Job ID to register if dispatching.

        Returns:
            Dict with album_path and queued_at if dequeued, None if at capacity or empty queue.
        """
        queue_key = f"{BEETS_ANALYSIS_QUEUE_PREFIX}{library_id}"
        active_key = f"{BEETS_ACTIVE_ANALYSES_PREFIX}{library_id}"
        started_at = datetime.now(timezone.utc).isoformat()

        result = self.redis.eval(
            self.DEQUEUE_AND_DISPATCH_SCRIPT,
            2,  # Number of keys
            queue_key,
            active_key,
            concurrency_cap,
            job_id,
            started_at,
        )

        if result:
            item_json = result[0]
            if isinstance(item_json, bytes):
                item_json = item_json.decode()
            return json.loads(item_json)
        return None

    def register_active_analysis(
        self,
        library_id: int,
        job_id: str,
        album_path: str,
    ) -> None:
        """Register a job as actively analyzing an album.

        Args:
            library_id: The library ID.
            job_id: Unique job ID.
            album_path: Album path being analyzed.
        """
        key = f"{BEETS_ACTIVE_ANALYSES_PREFIX}{library_id}"
        started_at = datetime.now(timezone.utc).isoformat()
        value = f"{job_id}|{started_at}|{album_path}"
        self.redis.hset(key, job_id, value)

    def unregister_active_analysis(
        self,
        library_id: int,
        job_id: str,
    ) -> bool:
        """Unregister a completed or failed analysis.

        Args:
            library_id: The library ID.
            job_id: The job ID to unregister.

        Returns:
            True if the job was unregistered.
        """
        key = f"{BEETS_ACTIVE_ANALYSES_PREFIX}{library_id}"
        return bool(self.redis.hdel(key, job_id))

    def get_analysis_queue_depth(self, library_id: int) -> int:
        """Get the number of albums waiting in the analysis queue.

        Args:
            library_id: The library ID.

        Returns:
            Queue depth.
        """
        key = f"{BEETS_ANALYSIS_QUEUE_PREFIX}{library_id}"
        return self.redis.llen(key)

    def get_active_analysis_count(self, library_id: int) -> int:
        """Get the number of active analyses for a library.

        Args:
            library_id: The library ID.

        Returns:
            Number of active analyses.
        """
        key = f"{BEETS_ACTIVE_ANALYSES_PREFIX}{library_id}"
        return self.redis.hlen(key)

    def get_analysis_queue_items(
        self,
        library_id: int,
    ) -> List[Dict[str, Any]]:
        """Get all items in the analysis queue with positions.

        Args:
            library_id: The library ID.

        Returns:
            List of dicts with album_path, queued_at, and position.
        """
        key = f"{BEETS_ANALYSIS_QUEUE_PREFIX}{library_id}"
        items = self.redis.lrange(key, 0, -1)
        result = []
        for idx, item in enumerate(items):
            if isinstance(item, bytes):
                item = item.decode()
            data = json.loads(item)
            data["position"] = idx + 1  # 1-indexed
            result.append(data)
        return result

    def get_active_analysis_items(
        self,
        library_id: int,
    ) -> List[Dict[str, Any]]:
        """Get all active analysis items for a library.

        Args:
            library_id: The library ID.

        Returns:
            List of dicts with job_id, album_path, and started_at.
        """
        key = f"{BEETS_ACTIVE_ANALYSES_PREFIX}{library_id}"
        items = self.redis.hgetall(key)
        result = []
        for job_id, value in items.items():
            if isinstance(job_id, bytes):
                job_id = job_id.decode()
            if isinstance(value, bytes):
                value = value.decode()
            # Value format: "{job_id}|{started_at}|{album_path}"
            parts = value.split("|", 2)
            if len(parts) >= 3:
                result.append({
                    "job_id": job_id,
                    "started_at": parts[1],
                    "album_path": parts[2],
                })
            else:
                # Fallback for simple format
                result.append({
                    "job_id": job_id,
                    "album_path": value,
                    "started_at": None,
                })
        return result

    def is_album_in_queue_or_active(
        self,
        library_id: int,
        album_path: str,
    ) -> tuple[bool, Optional[int], bool]:
        """Check if an album is already queued or being analyzed.

        Args:
            library_id: The library ID.
            album_path: The album path to check.

        Returns:
            Tuple of (is_queued, queue_position, is_active).
            queue_position is 1-indexed if queued, None otherwise.
        """
        # Check queue first
        queue_items = self.get_analysis_queue_items(library_id)
        for item in queue_items:
            if item["album_path"] == album_path:
                return (True, item["position"], False)

        # Check active analyses
        active_items = self.get_active_analysis_items(library_id)
        for item in active_items:
            if item["album_path"] == album_path:
                return (False, None, True)

        return (False, None, False)

    def clear_analysis_queue(self, library_id: int) -> bool:
        """Clear the analysis queue for a library.

        Args:
            library_id: The library ID.

        Returns:
            True if the queue was cleared.
        """
        key = f"{BEETS_ANALYSIS_QUEUE_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    def clear_active_analyses(self, library_id: int) -> bool:
        """Clear the active analyses set for a library.

        Args:
            library_id: The library ID.

        Returns:
            True if the set was cleared.
        """
        key = f"{BEETS_ACTIVE_ANALYSES_PREFIX}{library_id}"
        return bool(self.redis.delete(key))

    # --- Import Job Management ---

    def _import_job_key(self, job_id: str) -> str:
        """Get Redis key for an import job."""
        return f"{IMPORT_JOB_PREFIX}{job_id}"

    def _import_library_jobs_key(self, library_id: int) -> str:
        """Get Redis key for library's active import jobs set."""
        return f"{IMPORT_LIBRARY_JOBS_PREFIX}{library_id}:jobs"

    def _import_library_status_key(self, library_id: int) -> str:
        """Get Redis key for library's bulk status hash."""
        return f"{IMPORT_LIBRARY_STATUS_PREFIX}{library_id}:status"

    def _import_library_done_key(self, library_id: int) -> str:
        """Get Redis key for library's done albums hash."""
        return f"{IMPORT_LIBRARY_DONE_PREFIX}{library_id}:done"

    def _album_path_hash(self, album_path: str) -> str:
        """Generate a hash for an album path."""
        return hashlib.md5(album_path.encode()).hexdigest()

    def set_import_job_status(
        self,
        job_id: str,
        library_id: int,
        album_path: str,
        status: str,
        candidate_json: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        destination_path: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Create or update an import job's status in Redis.

        Args:
            job_id: Unique job ID.
            library_id: Library ID.
            album_path: Album folder path.
            status: Job status ('pending', 'in_progress', 'completed', 'failed').
            candidate_json: JSON-serialized candidate data.
            started_at: When the job started processing.
            completed_at: When the job completed.
            destination_path: Final path in beets library (on success).
            error_code: Error code (on failure).
            error_message: Error message (on failure).
            ttl_seconds: Optional TTL for the job key (set on completion).
        """
        job_key = self._import_job_key(job_id)
        jobs_key = self._import_library_jobs_key(library_id)
        status_key = self._import_library_status_key(library_id)
        path_hash = self._album_path_hash(album_path)

        # Build job data hash
        data = {
            "status": status,
            "library_id": str(library_id),
            "album_path": album_path,
        }
        if candidate_json:
            data["candidate_json"] = candidate_json
        if started_at:
            data["started_at"] = started_at.isoformat()
        if completed_at:
            data["completed_at"] = completed_at.isoformat()
        if destination_path:
            data["destination_path"] = destination_path
        if error_code:
            data["error_code"] = error_code
        if error_message:
            data["error_message"] = error_message

        # Use pipeline for atomic updates
        pipe = self.redis.pipeline()
        pipe.hset(job_key, mapping=data)

        # Add to library's active jobs set (remove on completion)
        if status in ("pending", "in_progress"):
            pipe.sadd(jobs_key, job_id)
        else:
            # Remove from active jobs on completion
            pipe.srem(jobs_key, job_id)

        # Update bulk status lookup hash
        status_data = json.dumps({
            "status": status,
            "job_id": job_id,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
        })
        pipe.hset(status_key, path_hash, status_data)

        # Set TTL if specified (typically on completion)
        if ttl_seconds:
            pipe.expire(job_key, ttl_seconds)

        pipe.execute()

    def get_import_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an import job.

        Args:
            job_id: The job ID.

        Returns:
            Dict with job status data, or None if not found.
        """
        key = self._import_job_key(job_id)
        data = self.redis.hgetall(key)
        if not data:
            return None

        def get_value(key_name: str) -> Optional[str]:
            val = data.get(key_name.encode()) or data.get(key_name)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else val

        result = {
            "job_id": job_id,
            "status": get_value("status") or "unknown",
            "library_id": int(get_value("library_id") or 0),
            "album_path": get_value("album_path") or "",
        }

        # Parse optional fields
        candidate_json = get_value("candidate_json")
        if candidate_json:
            result["candidate"] = json.loads(candidate_json)

        started_at = get_value("started_at")
        if started_at:
            result["started_at"] = datetime.fromisoformat(started_at)

        completed_at = get_value("completed_at")
        if completed_at:
            result["completed_at"] = datetime.fromisoformat(completed_at)

        destination_path = get_value("destination_path")
        if destination_path:
            result["destination_path"] = destination_path

        error_code = get_value("error_code")
        if error_code:
            result["error_code"] = error_code

        error_message = get_value("error_message")
        if error_message:
            result["error_message"] = error_message

        return result

    def get_library_import_status(
        self,
        library_id: int,
    ) -> Dict[str, Dict[str, Any]]:
        """Get bulk import status for all albums in a library.

        Args:
            library_id: The library ID.

        Returns:
            Dict mapping album_path to status info.
        """
        status_key = self._import_library_status_key(library_id)
        data = self.redis.hgetall(status_key)

        result = {}
        for path_hash, status_json in data.items():
            if isinstance(path_hash, bytes):
                path_hash = path_hash.decode()
            if isinstance(status_json, bytes):
                status_json = status_json.decode()

            status_data = json.loads(status_json)

            # We need to look up the actual album path from job data
            job_id = status_data.get("job_id")
            if job_id:
                job_data = self.get_import_job_status(job_id)
                if job_data:
                    album_path = job_data.get("album_path", "")
                    result[album_path] = {
                        "status": status_data.get("status"),
                        "job_id": job_id,
                        "started_at": status_data.get("started_at"),
                        "completed_at": status_data.get("completed_at"),
                    }

        return result

    def check_duplicate_import(
        self,
        library_id: int,
        album_path: str,
    ) -> Optional[str]:
        """Check if an import is already in progress for an album.

        Args:
            library_id: The library ID.
            album_path: The album path to check.

        Returns:
            The job_id of the in-progress import, or None if no duplicate.
        """
        status_key = self._import_library_status_key(library_id)
        path_hash = self._album_path_hash(album_path)

        status_json = self.redis.hget(status_key, path_hash)
        if not status_json:
            return None

        if isinstance(status_json, bytes):
            status_json = status_json.decode()

        status_data = json.loads(status_json)
        status = status_data.get("status")

        # Only consider pending or in_progress as duplicates
        if status in ("pending", "in_progress"):
            return status_data.get("job_id")

        return None

    def register_done_album(
        self,
        library_id: int,
        album_path: str,
        destination_path: str,
        completed_at: datetime,
        ttl_seconds: int = 86400,  # 24 hours
    ) -> None:
        """Register a completed import in the done hash (copy mode only).

        Args:
            library_id: The library ID.
            album_path: Source album path.
            destination_path: Final path in beets library.
            completed_at: Completion timestamp.
            ttl_seconds: TTL for the done hash (default 24 hours).
        """
        done_key = self._import_library_done_key(library_id)
        path_hash = self._album_path_hash(album_path)

        done_data = json.dumps({
            "album_path": album_path,
            "destination_path": destination_path,
            "completed_at": completed_at.isoformat(),
        })

        pipe = self.redis.pipeline()
        pipe.hset(done_key, path_hash, done_data)
        pipe.expire(done_key, ttl_seconds)
        pipe.execute()

    def get_done_albums(self, library_id: int) -> List[Dict[str, Any]]:
        """Get all done albums for a library (copy mode).

        Args:
            library_id: The library ID.

        Returns:
            List of done album dicts.
        """
        done_key = self._import_library_done_key(library_id)
        data = self.redis.hgetall(done_key)

        result = []
        for path_hash, done_json in data.items():
            if isinstance(done_json, bytes):
                done_json = done_json.decode()
            done_data = json.loads(done_json)
            result.append(done_data)

        return result

    def clear_import_job(self, job_id: str) -> bool:
        """Clear an import job from Redis.

        Args:
            job_id: The job ID.

        Returns:
            True if the key was deleted.
        """
        key = self._import_job_key(job_id)
        return bool(self.redis.delete(key))

    def clear_library_import_status(self, library_id: int) -> Dict[str, bool]:
        """Clear all import-related keys for a library.

        Args:
            library_id: The library ID.

        Returns:
            Dict of key types and whether they were deleted.
        """
        jobs_key = self._import_library_jobs_key(library_id)
        status_key = self._import_library_status_key(library_id)
        done_key = self._import_library_done_key(library_id)

        return {
            "jobs": bool(self.redis.delete(jobs_key)),
            "status": bool(self.redis.delete(status_key)),
            "done": bool(self.redis.delete(done_key)),
        }

    # --- Cover Art Discovery Cache ---

    def _hash_db_path(self, db_path: str) -> str:
        """Create a hash of the database path for use in Redis keys.

        Args:
            db_path: Path to the beets database.

        Returns:
            MD5 hash of the path (first 16 characters).
        """
        return hashlib.md5(db_path.encode()).hexdigest()[:16]

    def get_discovered_cover_art(
        self, db_path: str, album_id: int
    ) -> Optional[str]:
        """Get cached discovered cover art path.

        Args:
            db_path: Path to the beets database.
            album_id: The album ID.

        Returns:
            The cached cover art path, empty string if negative cache,
            or None if not cached.
        """
        db_hash = self._hash_db_path(db_path)
        key = f"{COVER_DISCOVERED_PREFIX}{db_hash}:{album_id}"
        result = self.redis.get(key)

        if result is None:
            return None

        if isinstance(result, bytes):
            return result.decode("utf-8")
        return result

    def set_discovered_cover_art(
        self,
        db_path: str,
        album_id: int,
        cover_path: str,
        ttl_seconds: int = 604800,  # 7 days
    ) -> None:
        """Cache discovered cover art path.

        Args:
            db_path: Path to the beets database.
            album_id: The album ID.
            cover_path: The discovered cover art path, or empty string for negative cache.
            ttl_seconds: Cache TTL in seconds (default 7 days).
        """
        db_hash = self._hash_db_path(db_path)
        key = f"{COVER_DISCOVERED_PREFIX}{db_hash}:{album_id}"
        self.redis.set(key, cover_path, ex=ttl_seconds)

    def invalidate_discovered_cover_art(
        self, db_path: str, album_id: int
    ) -> bool:
        """Invalidate cached cover art discovery for an album.

        Args:
            db_path: Path to the beets database.
            album_id: The album ID.

        Returns:
            True if key was deleted, False if it didn't exist.
        """
        db_hash = self._hash_db_path(db_path)
        key = f"{COVER_DISCOVERED_PREFIX}{db_hash}:{album_id}"
        return bool(self.redis.delete(key))

    def invalidate_all_discovered_cover_art(self, db_path: str) -> int:
        """Invalidate all cached cover art discovery for a library.

        Useful when a library is re-scanned or albums are modified.

        Args:
            db_path: Path to the beets database.

        Returns:
            Number of keys deleted.
        """
        db_hash = self._hash_db_path(db_path)
        pattern = f"{COVER_DISCOVERED_PREFIX}{db_hash}:*"
        keys = list(self.redis.scan_iter(match=pattern))
        if keys:
            return self.redis.delete(*keys)
        return 0

    # --- Cleanup ---

    def cleanup_library_keys(self, library_id: int) -> Dict[str, bool]:
        """Clean up all keys for a library.

        Args:
            library_id: The library ID.

        Returns:
            Dict of key types and whether they were deleted.
        """
        import_cleanup = self.clear_library_import_status(library_id)
        return {
            "debounce": self.clear_debounce(library_id),
            "watcher_state": self.clear_watcher_state(library_id),
            "heartbeat": self.clear_heartbeat(library_id),
            "scan_progress": self.clear_scan_progress(library_id),
            "scan_queue": self.clear_scan_queue(library_id),
            "operation_locks": self.clear_operation_locks(library_id),
            "analysis_queue": self.clear_analysis_queue(library_id),
            "active_analyses": self.clear_active_analyses(library_id),
            "import_jobs": import_cleanup.get("jobs", False),
            "import_status": import_cleanup.get("status", False),
            "import_done": import_cleanup.get("done", False),
        }

    # --- Library Batch Update Status ---

    def _batch_update_key(self, job_id: str) -> str:
        """Get Redis key for a batch update job."""
        return f"{BATCH_UPDATE_PREFIX}{job_id}"

    def set_batch_update_status(
        self,
        job_id: str,
        library_id: int,
        status: str,
        albums: List[str],
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        album_results: Optional[Dict[str, Dict[str, Any]]] = None,
        file_writes: Optional[Dict[str, int]] = None,
        error: Optional[str] = None,
        ttl_seconds: int = 86400,  # 24 hours
    ) -> None:
        """Set or update batch update job status.

        Args:
            job_id: Unique job ID.
            library_id: Library ID.
            status: Job status ('pending', 'running', 'completed', 'failed').
            albums: List of album names being updated.
            started_at: When the job started.
            completed_at: When the job completed.
            album_results: Dict mapping album name to status and error.
            file_writes: Dict with keys 'total', 'succeeded', 'failed' for file write stats.
            error: Overall error message if entire job failed.
            ttl_seconds: TTL for the key (default 24 hours).
        """
        key = self._batch_update_key(job_id)

        # Build albums data with corrected status values for frontend
        albums_data = []
        for album in albums:
            album_info = {"album": album, "status": "pending"}
            if album_results and album in album_results:
                # Map backend status to frontend expected values
                backend_status = album_results[album].get("status", "pending")
                if backend_status == "in_progress":
                    album_info["status"] = "syncing"
                elif backend_status == "completed":
                    album_info["status"] = "success"
                else:
                    album_info["status"] = backend_status
                if album_results[album].get("error"):
                    album_info["error"] = album_results[album]["error"]
            albums_data.append(album_info)

        data = {
            "status": status,
            "library_id": str(library_id),
            "albums": json.dumps(albums_data),
        }
        if started_at:
            data["started_at"] = started_at.isoformat()
        if completed_at:
            data["completed_at"] = completed_at.isoformat()
        if file_writes:
            data["file_writes"] = json.dumps(file_writes)
        if error:
            data["error"] = error

        pipe = self.redis.pipeline()
        pipe.hset(key, mapping=data)
        pipe.expire(key, ttl_seconds)
        pipe.execute()

    def update_batch_update_album_status(
        self,
        job_id: str,
        album: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update the status of a single album in a batch update job.

        Args:
            job_id: The job ID.
            album: Album name to update.
            status: New status for the album ('pending', 'syncing', 'success', 'failed').
            error: Error message if failed.
        """
        key = self._batch_update_key(job_id)

        # Get current albums data
        albums_json = self.redis.hget(key, "albums")
        if not albums_json:
            return

        if isinstance(albums_json, bytes):
            albums_json = albums_json.decode()

        albums_data = json.loads(albums_json)

        # Map backend status values to frontend expected values
        mapped_status = status
        if status == "in_progress":
            mapped_status = "syncing"
        elif status == "completed":
            mapped_status = "success"

        # Update the album status
        for album_info in albums_data:
            if album_info.get("album") == album:
                album_info["status"] = mapped_status
                if error:
                    album_info["error"] = error
                elif "error" in album_info and mapped_status == "success":
                    del album_info["error"]
                break

        # Save back
        self.redis.hset(key, "albums", json.dumps(albums_data))

    def get_batch_update_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a batch update job.

        Args:
            job_id: The job ID.

        Returns:
            Dict with job status data, or None if not found.
        """
        key = self._batch_update_key(job_id)
        data = self.redis.hgetall(key)
        if not data:
            return None

        def get_value(key_name: str) -> Optional[str]:
            val = data.get(key_name.encode()) or data.get(key_name)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else val

        # Map backend status values to frontend expected values
        raw_status = get_value("status") or "unknown"
        if raw_status == "in_progress":
            mapped_status = "running"
        elif raw_status == "partial":
            # "partial" maps to "completed" for frontend - partial success is still completed
            mapped_status = "completed"
        else:
            mapped_status = raw_status

        result = {
            "job_id": job_id,
            "status": mapped_status,
            "library_id": int(get_value("library_id") or 0),
        }

        albums_json = get_value("albums")
        if albums_json:
            result["albums"] = json.loads(albums_json)
        else:
            result["albums"] = []

        file_writes_json = get_value("file_writes")
        if file_writes_json:
            result["file_writes"] = json.loads(file_writes_json)

        started_at = get_value("started_at")
        if started_at:
            result["started_at"] = datetime.fromisoformat(started_at)

        completed_at = get_value("completed_at")
        if completed_at:
            result["completed_at"] = datetime.fromisoformat(completed_at)

        error = get_value("error")
        if error:
            result["error"] = error

        return result

    def clear_batch_update_status(self, job_id: str) -> bool:
        """Clear a batch update job status.

        Args:
            job_id: The job ID.

        Returns:
            True if key was deleted.
        """
        key = self._batch_update_key(job_id)
        return bool(self.redis.delete(key))


def get_redis_key_manager(redis_url: str) -> RedisKeyManager:
    """Create a RedisKeyManager with a new Redis connection.

    Args:
        redis_url: Redis connection URL.

    Returns:
        Configured RedisKeyManager instance.
    """
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    return RedisKeyManager(redis_client)
