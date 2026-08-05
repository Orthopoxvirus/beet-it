"""Celery application configuration with worker signals.

This module configures the Celery application and sets up worker signals
for initializing the WatcherService singleton and resuming watchers on startup.

Worker Lifecycle:
1. worker_process_init: Called when a worker process is spawned
   - Initializes the global WatcherService singleton
   - Sets up the scan trigger callback

2. worker_ready: Called when the worker is ready to accept tasks
   - Triggers resume_watchers to start all watchers

3. worker_shutdown: Called when the worker is shutting down
   - Stops all watchers and cleans up the singleton
"""

import logging
from celery import Celery
from celery.signals import worker_process_init, worker_ready, worker_shutdown
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "beets_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.beets_tasks", "app.tasks.scan_tasks", "app.tasks.maintenance", "app.tasks.download_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    worker_prefetch_multiplier=1,
)


@worker_process_init.connect
def on_worker_process_init(sender=None, **kwargs):
    """Initialize the WatcherService singleton when the worker process starts.

    This signal is called once per worker process and is the correct place to
    initialize long-lived services like the WatcherService.
    """
    # Check if watchers are enabled before initializing
    if hasattr(settings, 'enable_import_watchers') and not settings.enable_import_watchers:
        logger.info("Import watchers are disabled, skipping WatcherService initialization")
        return

    logger.info("Worker process initializing, setting up WatcherService singleton")

    try:
        from app.services.watcher import initialize_watcher_service
        from app.services.redis_keys import get_redis_key_manager

        # Get Redis manager
        redis_manager = get_redis_key_manager(settings.redis_url)

        # Get configuration values
        debounce_seconds = getattr(settings, 'scan_debounce_seconds', 30)
        heartbeat_interval = 10  # seconds

        # Initialize the singleton
        watcher_service = initialize_watcher_service(
            redis_manager=redis_manager,
            debounce_seconds=debounce_seconds,
            heartbeat_interval=heartbeat_interval,
        )

        # Set up the scan trigger callback
        # This is called when changes are detected and debounce completes
        def on_scan_trigger(library_id: int) -> None:
            from app.tasks.scan_tasks import trigger_scan
            trigger_scan.delay(library_id, "watcher")

        watcher_service.set_scan_trigger_callback(on_scan_trigger)

        logger.info("WatcherService singleton initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize WatcherService singleton: {e}")


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    """Resume watchers when the worker is ready to accept tasks.

    This signal is called after the worker has finished setup and is ready
    to process tasks. This is the correct time to resume watching all
    previously active import folders.
    """
    # Check if watchers are enabled
    if hasattr(settings, 'enable_import_watchers') and not settings.enable_import_watchers:
        logger.info("Import watchers are disabled, skipping watcher resume")
        return

    logger.info("Worker ready, resuming import folder watchers")

    try:
        from app.tasks.scan_tasks import resume_watchers
        # Call the resume task asynchronously
        resume_watchers.delay()
        logger.info("Watcher resume task queued")
    except Exception as e:
        logger.error(f"Failed to queue watcher resume task: {e}")


@worker_shutdown.connect
def on_worker_shutdown(sender=None, **kwargs):
    """Clean up watchers when the worker is shutting down.

    This signal is called when the worker is about to shut down.
    We stop all watchers to ensure clean shutdown.
    """
    logger.info("Worker shutting down, stopping all watchers")

    try:
        from app.services.watcher import shutdown_watcher_service
        shutdown_watcher_service()
        logger.info("WatcherService shutdown complete")
    except Exception as e:
        logger.error(f"Error during WatcherService shutdown: {e}")
