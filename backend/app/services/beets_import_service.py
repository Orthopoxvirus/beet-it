"""Service for managing beets album imports.

This service coordinates the import workflow:
- Validates album paths and candidate data
- Creates import jobs and enqueues Celery tasks
- Provides status lookup for individual jobs and bulk queries
- Reads library configuration for import mode (copy vs move)
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.config import get_settings
from app.services.audio_discovery import has_audio_files
from app.services.redis_keys import RedisKeyManager, get_redis_key_manager
from app.services.tag_writer.mappings import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)
settings = get_settings()


class BeetsImportError(Exception):
    """Base exception for import errors."""

    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


class BeetsImportService:
    """Service for managing beets album imports."""

    def __init__(
        self,
        redis_manager: Optional[RedisKeyManager] = None,
    ):
        """Initialize the service.

        Args:
            redis_manager: Optional Redis manager. Creates one if not provided.
        """
        self._redis_manager = redis_manager

    @property
    def redis_manager(self) -> RedisKeyManager:
        """Get the Redis manager."""
        if self._redis_manager is None:
            self._redis_manager = get_redis_key_manager(settings.redis_url)
        return self._redis_manager

    def validate_album_path(
        self,
        album_path: str,
        import_path: str,
    ) -> str:
        """Validate that album_path is within import_path and exists.

        Args:
            album_path: Path to validate (can be relative or absolute).
            import_path: The library's import folder path.

        Returns:
            The canonical absolute path if valid.

        Raises:
            BeetsImportError: If path is invalid.
        """
        # Handle relative paths by joining with import_path
        if not os.path.isabs(album_path):
            full_path = os.path.join(import_path, album_path)
        else:
            full_path = album_path

        # Resolve to canonical path (follows symlinks)
        canonical_path = os.path.realpath(full_path)
        canonical_import = os.path.realpath(import_path)

        # Ensure canonical path starts with import folder
        if not (
            canonical_path.startswith(canonical_import + os.sep)
            or canonical_path == canonical_import
        ):
            raise BeetsImportError(
                "Album path must be within the library's import folder",
                "PATH_OUTSIDE_IMPORT"
            )

        # Check that path exists
        if not os.path.isdir(canonical_path):
            raise BeetsImportError(
                f"Album folder not found: {canonical_path}",
                "ALBUM_NOT_FOUND"
            )

        # Check for audio files — recursively, so a multi-disc album whose
        # tracks live in "CD 01" / "Disc 2" subfolders validates too (#180).
        if not has_audio_files(canonical_path):
            raise BeetsImportError(
                f"No audio files found in album folder: {canonical_path}",
                "NO_AUDIO_FILES"
            )

        return canonical_path

    def get_import_mode(self, config_path: Optional[str]) -> str:
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

    def start_import(
        self,
        library_id: int,
        album_path: str,
        candidate: Optional[Dict[str, Any]],
    ) -> Tuple[str, str]:
        """Start an import job for an album.

        Creates the job in Redis and enqueues a Celery task.

        Args:
            library_id: The library ID.
            album_path: Absolute path to the album folder.
            candidate: Candidate metadata dict, or None for an "import as-is"
                job where metadata is read from the files' existing tags.

        Returns:
            Tuple of (job_id, message).

        Raises:
            BeetsImportError: If import already in progress.
        """
        # Check for duplicate import
        existing_job_id = self.redis_manager.check_duplicate_import(library_id, album_path)
        if existing_job_id:
            raise BeetsImportError(
                f"Import already in progress for this album (job {existing_job_id})",
                "IMPORT_IN_PROGRESS"
            )

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Serialize candidate
        candidate_json = json.dumps(candidate)

        # Create job in Redis
        self.redis_manager.set_import_job_status(
            job_id=job_id,
            library_id=library_id,
            album_path=album_path,
            status="pending",
            candidate_json=candidate_json,
        )

        logger.info(
            f"Created import job {job_id} for library {library_id}, album: {album_path}"
        )

        return job_id, "Import job created successfully"

    def get_job_status(
        self,
        job_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the status of an import job.

        Args:
            job_id: The job ID.

        Returns:
            Job status dict, or None if not found.
        """
        job_data = self.redis_manager.get_import_job_status(job_id)
        if not job_data:
            return None

        # Build response
        result = {
            "job_id": job_id,
            "status": job_data.get("status", "unknown"),
            "library_id": job_data.get("library_id"),
            "album_path": job_data.get("album_path", ""),
            "started_at": job_data.get("started_at"),
            "completed_at": job_data.get("completed_at"),
        }

        # Add destination path on success
        if job_data.get("destination_path"):
            result["destination_path"] = job_data["destination_path"]

        # Add error on failure
        if job_data.get("error_code") or job_data.get("error_message"):
            result["error"] = {
                "code": job_data.get("error_code", "UNKNOWN_ERROR"),
                "message": job_data.get("error_message", "Unknown error occurred"),
            }

        return result

    def get_bulk_status(
        self,
        library_id: int,
        import_path: str,
        config_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get bulk import status for all albums in the library.

        Args:
            library_id: The library ID.
            import_path: The library's import folder path.
            config_path: Path to beets config file.

        Returns:
            Dict with albums, counts, and import_mode.
        """
        import_mode = self.get_import_mode(config_path)

        # Get in-progress and pending jobs from Redis
        import_status = self.redis_manager.get_library_import_status(library_id)

        # Get done albums (only relevant for copy mode)
        done_albums = []
        if import_mode == "copy":
            done_albums = self.redis_manager.get_done_albums(library_id)

        # Build albums dict
        albums: Dict[str, Dict[str, Any]] = {}
        in_progress_count = 0
        done_count = 0

        # Add in-progress and pending albums
        for album_path, status_data in import_status.items():
            status = status_data.get("status")
            if status in ("pending", "in_progress"):
                albums[album_path] = {
                    "state": "in_progress" if status == "in_progress" else "pending",
                    "job_id": status_data.get("job_id"),
                    "started_at": status_data.get("started_at"),
                }
                if status == "in_progress":
                    in_progress_count += 1

        # Add done albums (copy mode only)
        for done_data in done_albums:
            album_path = done_data.get("album_path", "")
            if album_path and album_path not in albums:
                albums[album_path] = {
                    "state": "done",
                    "completed_at": done_data.get("completed_at"),
                    "destination_path": done_data.get("destination_path"),
                }
                done_count += 1

        # Scan import folder to find all albums
        all_album_paths = self._get_album_folders(import_path)
        pending_count = 0

        for album_path in all_album_paths:
            if album_path not in albums:
                albums[album_path] = {"state": "pending"}
                pending_count += 1
            elif albums[album_path]["state"] == "pending":
                pending_count += 1

        return {
            "albums": albums,
            "counts": {
                "pending": pending_count,
                "in_progress": in_progress_count,
                "done": done_count,
            },
            "import_mode": import_mode,
        }

    def _get_album_folders(self, import_path: str) -> List[str]:
        """Get all album folders from an import path.

        An album folder is defined as a directory containing at least one
        audio file (based on supported extensions).

        Args:
            import_path: The root import folder path to scan.

        Returns:
            List of absolute paths to album folders.
        """
        if not os.path.exists(import_path):
            return []

        if not os.access(import_path, os.R_OK):
            return []

        album_folders = []

        for root, _dirs, files in os.walk(import_path):
            # Check if this directory contains audio files
            has_audio = any(
                os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS for f in files
            )
            if has_audio:
                album_folders.append(root)

        return sorted(album_folders)


# Singleton instance
_service_instance: Optional[BeetsImportService] = None


def get_beets_import_service(
    redis_manager: Optional[RedisKeyManager] = None,
) -> BeetsImportService:
    """Get the BeetsImportService singleton instance.

    Args:
        redis_manager: Optional Redis manager.

    Returns:
        BeetsImportService instance.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = BeetsImportService(redis_manager=redis_manager)
    return _service_instance
