"""Shared enums for the activity monitor and task tracking."""

from enum import Enum


class TaskType(str, Enum):
    """Types of background tasks tracked by the activity monitor."""
    SCAN = "scan"
    ANALYSIS = "analysis"
    TAG_WRITE = "tag_write"
    IMPORT = "import"
    MOVE = "move"
    BATCH_EDIT_SYNC = "batch_edit_sync"
    EMBY_REFRESH = "emby_refresh"
    DOWNLOAD = "download"
    CONVERT_WAV = "convert_wav"
    DEDUPE_WAV = "dedupe_wav"
    CLEANUP = "cleanup"
    BPM_BACKFILL = "bpm_backfill"


class TaskStatus(str, Enum):
    """Possible states for a task event."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
