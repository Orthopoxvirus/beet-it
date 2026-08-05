"""Watcher service module for filesystem monitoring.

This module provides the WatcherService for monitoring import folder filesystem
changes. The service uses a singleton pattern to ensure watchers persist for
the lifetime of the Celery worker process.

Usage:
    # During worker startup (in celery_app.py):
    from app.services.watcher import initialize_watcher_service
    initialize_watcher_service(redis_manager)

    # In tasks:
    from app.services.watcher import get_watcher_service
    watcher = get_watcher_service()
    if watcher:
        watcher.start_watcher(library_id, path)
"""

from app.services.watcher.watcher_service import (
    WatcherService,
    get_watcher_service,
    initialize_watcher_service,
    shutdown_watcher_service,
    is_watcher_service_initialized,
)

__all__ = [
    "WatcherService",
    "get_watcher_service",
    "initialize_watcher_service",
    "shutdown_watcher_service",
    "is_watcher_service_initialized",
]
