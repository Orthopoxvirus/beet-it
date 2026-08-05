"""WatcherService for monitoring import folder filesystem changes.

This module provides a singleton WatcherService that persists for the lifetime
of the Celery worker process. The singleton pattern is critical because:

1. Filesystem watchers (Observer threads) are long-lived background services
2. Celery tasks are short-lived - local variables are garbage collected when tasks complete
3. The singleton ensures watchers persist beyond individual task execution

Usage:
    from app.services.watcher import get_watcher_service, initialize_watcher_service

    # During worker startup (in celery_app.py):
    initialize_watcher_service(redis_manager)

    # In tasks:
    watcher_service = get_watcher_service()
    watcher_service.start_watcher(library_id, path)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, TYPE_CHECKING

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

if TYPE_CHECKING:
    from app.services.redis_keys import RedisKeyManager

logger = logging.getLogger(__name__)

# Module-level singleton instance
_watcher_service_instance: Optional["WatcherService"] = None
_watcher_service_lock = threading.Lock()


class ImportFolderEventHandler(FileSystemEventHandler):
    """Handler for filesystem events in import folders."""

    def __init__(
        self,
        library_id: int,
        redis_manager: RedisKeyManager,
        on_change_callback: Optional[Callable[[int], None]] = None,
        local_debounce_seconds: float = 1.0,
    ):
        """Initialize the event handler.

        Args:
            library_id: The library ID this handler monitors.
            redis_manager: Redis key manager for state tracking.
            on_change_callback: Callback when changes are detected after debounce.
            local_debounce_seconds: Local debounce time before Redis update.
        """
        super().__init__()
        self.library_id = library_id
        self.redis_manager = redis_manager
        self.on_change_callback = on_change_callback
        self.local_debounce_seconds = local_debounce_seconds

        self._last_event_time: Optional[float] = None
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def _is_ignored_file(self, path: str) -> bool:
        """Check if a file should be ignored.

        Args:
            path: File path to check.

        Returns:
            True if the file should be ignored.
        """
        filename = os.path.basename(path)

        # Ignore hidden files and common temporary files
        if filename.startswith("."):
            return True
        if filename.endswith((".tmp", ".part", ".crdownload", "~")):
            return True
        if filename.startswith("~$"):  # Office temp files
            return True

        return False

    def _should_process_event(self) -> bool:
        """Check if we should process this event (not blocked by operations).

        Returns:
            True if event should be processed.
        """
        # Check if any blocking operations are running
        if self.redis_manager.has_blocking_operations(self.library_id):
            logger.debug(
                f"Ignoring filesystem event for library {self.library_id}: "
                "blocking operation in progress"
            )
            return False
        return True

    def _handle_event(self, event: FileSystemEvent) -> None:
        """Handle a filesystem event with local debouncing.

        Args:
            event: The filesystem event.
        """
        # Ignore directory events for debounce - we care about file changes
        if event.is_directory:
            # Still log it but don't trigger debounce
            logger.debug(f"Directory event: {event.event_type} - {event.src_path}")
            return

        # Ignore temporary and hidden files
        if self._is_ignored_file(event.src_path):
            logger.debug(f"Ignoring temporary/hidden file: {event.src_path}")
            return

        # Check for blocking operations
        if not self._should_process_event():
            return

        with self._lock:
            self._last_event_time = time.time()

            # Cancel existing timer
            if self._debounce_timer:
                self._debounce_timer.cancel()

            # Start new local debounce timer
            self._debounce_timer = threading.Timer(
                self.local_debounce_seconds,
                self._on_local_debounce_complete,
            )
            self._debounce_timer.start()

            logger.debug(
                f"Filesystem event detected for library {self.library_id}: "
                f"{event.event_type} - {event.src_path}"
            )

    def _on_local_debounce_complete(self) -> None:
        """Called when local debounce timer completes."""
        # Update watcher state in Redis
        self.redis_manager.set_watcher_state(
            self.library_id,
            active=True,
            last_event=datetime.now(timezone.utc),
            pending_scan=True,
        )

        # Trigger callback if provided
        if self.on_change_callback:
            self.on_change_callback(self.library_id)

        logger.info(
            f"Local debounce complete for library {self.library_id}, "
            "triggering Redis debounce"
        )

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file/folder creation."""
        self._handle_event(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file/folder deletion."""
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification."""
        self._handle_event(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file/folder move/rename."""
        self._handle_event(event)

    def stop(self) -> None:
        """Stop the event handler and cancel any pending timer."""
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None


class WatcherService:
    """Service for managing filesystem watchers for import folders."""

    def __init__(
        self,
        redis_manager: RedisKeyManager,
        debounce_seconds: int = 30,
        heartbeat_interval: int = 10,
    ):
        """Initialize the watcher service.

        Args:
            redis_manager: Redis key manager for state tracking.
            debounce_seconds: Redis debounce time in seconds.
            heartbeat_interval: Seconds between heartbeat updates.
        """
        self.redis_manager = redis_manager
        self.debounce_seconds = debounce_seconds
        self.heartbeat_interval = heartbeat_interval

        self._observers: Dict[int, Observer] = {}
        self._handlers: Dict[int, ImportFolderEventHandler] = {}
        self._heartbeat_threads: Dict[int, threading.Thread] = {}
        self._stop_events: Dict[int, threading.Event] = {}
        self._lock = threading.Lock()

        # Callback to trigger scan after debounce
        self._on_scan_trigger: Optional[Callable[[int], None]] = None

    def set_scan_trigger_callback(self, callback: Callable[[int], None]) -> None:
        """Set the callback to trigger a scan after debounce.

        Args:
            callback: Function that takes library_id and triggers a scan.
        """
        self._on_scan_trigger = callback

    def _on_change_detected(self, library_id: int) -> None:
        """Called when changes are detected after local debounce.

        Args:
            library_id: The library that detected changes.
        """
        # Set or refresh the Redis debounce timer
        if not self.redis_manager.set_debounce(library_id, self.debounce_seconds):
            # Debounce already active, refresh it
            self.redis_manager.refresh_debounce(library_id, self.debounce_seconds)
            logger.debug(
                f"Refreshed Redis debounce for library {library_id} "
                f"({self.debounce_seconds}s)"
            )
        else:
            logger.info(
                f"Started Redis debounce for library {library_id} "
                f"({self.debounce_seconds}s)"
            )

    def _heartbeat_loop(self, library_id: int) -> None:
        """Heartbeat loop to indicate watcher is healthy.

        Args:
            library_id: The library ID.
        """
        stop_event = self._stop_events.get(library_id)
        if not stop_event:
            return

        while not stop_event.is_set():
            try:
                self.redis_manager.set_heartbeat(
                    library_id,
                    ttl_seconds=self.heartbeat_interval * 2,  # TTL > interval
                )
            except Exception as e:
                logger.error(
                    f"Failed to update heartbeat for library {library_id}: {e}"
                )

            stop_event.wait(self.heartbeat_interval)

    def start_watcher(self, library_id: int, import_path: str) -> bool:
        """Start watching an import folder.

        Args:
            library_id: The library ID.
            import_path: Path to the import folder.

        Returns:
            True if watcher started successfully.
        """
        with self._lock:
            # Check if already watching
            if library_id in self._observers:
                logger.warning(f"Watcher already running for library {library_id}")
                return True

            # Validate path exists
            if not os.path.isdir(import_path):
                logger.error(
                    f"Cannot start watcher for library {library_id}: "
                    f"path does not exist: {import_path}"
                )
                return False

            try:
                # Create event handler
                handler = ImportFolderEventHandler(
                    library_id=library_id,
                    redis_manager=self.redis_manager,
                    on_change_callback=self._on_change_detected,
                )
                self._handlers[library_id] = handler

                # Create and start observer
                observer = Observer()
                observer.schedule(handler, import_path, recursive=True)
                observer.start()
                self._observers[library_id] = observer

                # Start heartbeat thread
                stop_event = threading.Event()
                self._stop_events[library_id] = stop_event
                heartbeat_thread = threading.Thread(
                    target=self._heartbeat_loop,
                    args=(library_id,),
                    daemon=True,
                )
                heartbeat_thread.start()
                self._heartbeat_threads[library_id] = heartbeat_thread

                # Update state in Redis
                self.redis_manager.set_watcher_state(
                    library_id,
                    active=True,
                    pending_scan=False,
                )
                self.redis_manager.set_heartbeat(
                    library_id,
                    ttl_seconds=self.heartbeat_interval * 2,
                )

                logger.info(
                    f"Started watcher for library {library_id} "
                    f"on path: {import_path}"
                )
                return True

            except Exception as e:
                logger.error(
                    f"Failed to start watcher for library {library_id}: {e}"
                )
                # Cleanup partial state
                self._cleanup_watcher(library_id)
                return False

    def stop_watcher(self, library_id: int) -> bool:
        """Stop watching an import folder.

        Args:
            library_id: The library ID.

        Returns:
            True if watcher was stopped.
        """
        with self._lock:
            return self._cleanup_watcher(library_id)

    def _cleanup_watcher(self, library_id: int) -> bool:
        """Clean up watcher resources for a library.

        Args:
            library_id: The library ID.

        Returns:
            True if anything was cleaned up.
        """
        cleaned = False

        # Stop heartbeat thread
        if library_id in self._stop_events:
            self._stop_events[library_id].set()
            del self._stop_events[library_id]
            cleaned = True

        if library_id in self._heartbeat_threads:
            # Don't join - it's a daemon thread
            del self._heartbeat_threads[library_id]

        # Stop handler
        if library_id in self._handlers:
            self._handlers[library_id].stop()
            del self._handlers[library_id]
            cleaned = True

        # Stop observer
        if library_id in self._observers:
            try:
                self._observers[library_id].stop()
                self._observers[library_id].join(timeout=5)
            except Exception as e:
                logger.error(f"Error stopping observer for library {library_id}: {e}")
            del self._observers[library_id]
            cleaned = True

        # Clear Redis state
        self.redis_manager.set_watcher_state(library_id, active=False)
        self.redis_manager.clear_heartbeat(library_id)

        if cleaned:
            logger.info(f"Stopped watcher for library {library_id}")

        return cleaned

    def is_watching(self, library_id: int) -> bool:
        """Check if a library is being watched.

        Args:
            library_id: The library ID.

        Returns:
            True if watcher is running.
        """
        with self._lock:
            return library_id in self._observers and self._observers[library_id].is_alive()

    def get_watched_libraries(self) -> list[int]:
        """Get list of library IDs being watched.

        Returns:
            List of library IDs.
        """
        with self._lock:
            return [
                lib_id
                for lib_id, obs in self._observers.items()
                if obs.is_alive()
            ]

    def stop_all(self) -> None:
        """Stop all watchers."""
        with self._lock:
            library_ids = list(self._observers.keys())

        for library_id in library_ids:
            self.stop_watcher(library_id)

        logger.info("All watchers stopped")

    def check_health(self, library_id: int) -> bool:
        """Check if a watcher is healthy.

        Args:
            library_id: The library ID.

        Returns:
            True if watcher is healthy (observer running and heartbeat active).
        """
        # Check local observer
        if not self.is_watching(library_id):
            return False

        # Check Redis heartbeat
        return self.redis_manager.check_heartbeat(library_id)

    def get_stale_watchers(self) -> list[int]:
        """Find watchers that are registered but not healthy.

        Returns:
            List of library IDs with stale watchers.
        """
        stale = []
        with self._lock:
            for library_id in self._observers:
                if not self.check_health(library_id):
                    stale.append(library_id)
        return stale


# --- Singleton Management Functions ---


def initialize_watcher_service(
    redis_manager: "RedisKeyManager",
    debounce_seconds: int = 30,
    heartbeat_interval: int = 10,
) -> WatcherService:
    """Initialize the global WatcherService singleton.

    This function should be called once during Celery worker startup
    (via worker_process_init or worker_ready signals).

    Args:
        redis_manager: Redis key manager for state tracking.
        debounce_seconds: Redis debounce time in seconds.
        heartbeat_interval: Seconds between heartbeat updates.

    Returns:
        The initialized WatcherService singleton.

    Raises:
        RuntimeError: If the singleton is already initialized.
    """
    global _watcher_service_instance

    with _watcher_service_lock:
        if _watcher_service_instance is not None:
            logger.warning(
                "WatcherService singleton already initialized, returning existing instance"
            )
            return _watcher_service_instance

        logger.info("Initializing global WatcherService singleton")
        _watcher_service_instance = WatcherService(
            redis_manager=redis_manager,
            debounce_seconds=debounce_seconds,
            heartbeat_interval=heartbeat_interval,
        )
        return _watcher_service_instance


def get_watcher_service() -> Optional[WatcherService]:
    """Get the global WatcherService singleton.

    Returns:
        The WatcherService singleton, or None if not initialized.
    """
    global _watcher_service_instance
    return _watcher_service_instance


def shutdown_watcher_service() -> None:
    """Shutdown the global WatcherService singleton.

    This stops all watchers and clears the singleton reference.
    Should be called during worker shutdown.
    """
    global _watcher_service_instance

    with _watcher_service_lock:
        if _watcher_service_instance is not None:
            logger.info("Shutting down global WatcherService singleton")
            _watcher_service_instance.stop_all()
            _watcher_service_instance = None


def is_watcher_service_initialized() -> bool:
    """Check if the WatcherService singleton is initialized.

    Returns:
        True if the singleton is initialized.
    """
    global _watcher_service_instance
    return _watcher_service_instance is not None
