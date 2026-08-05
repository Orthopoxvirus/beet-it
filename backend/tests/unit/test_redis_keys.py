"""Unit tests for Redis key manager."""

import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.redis_keys import (
    RedisKeyManager,
    DEBOUNCE_PREFIX,
    WATCHER_STATE_PREFIX,
    WATCHER_HEARTBEAT_PREFIX,
    SCAN_PROGRESS_PREFIX,
    SCAN_QUEUE_PREFIX,
    OPERATION_LOCK_PREFIX,
    SCAN_CHANNEL_PREFIX,
    BEETS_ANALYSIS_QUEUE_PREFIX,
    BEETS_ACTIVE_ANALYSES_PREFIX,
    COVER_DISCOVERED_PREFIX,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return Mock()


@pytest.fixture
def redis_manager(mock_redis):
    """Create a RedisKeyManager with mock Redis."""
    return RedisKeyManager(mock_redis)


class TestDebounceKeyManagement:
    """Tests for debounce key operations."""

    def test_set_debounce_new_key(self, redis_manager, mock_redis):
        """Test setting a new debounce key."""
        mock_redis.set.return_value = True

        result = redis_manager.set_debounce(123, ttl_seconds=30)

        assert result is True
        mock_redis.set.assert_called_once_with(
            f"{DEBOUNCE_PREFIX}123", "1", nx=True, ex=30
        )

    def test_set_debounce_existing_key(self, redis_manager, mock_redis):
        """Test setting debounce when key already exists."""
        mock_redis.set.return_value = False

        result = redis_manager.set_debounce(123)

        assert result is False

    def test_refresh_debounce(self, redis_manager, mock_redis):
        """Test refreshing debounce TTL."""
        mock_redis.set.return_value = True

        result = redis_manager.refresh_debounce(123, ttl_seconds=60)

        assert result is True
        mock_redis.set.assert_called_once_with(
            f"{DEBOUNCE_PREFIX}123", "1", xx=True, ex=60
        )

    def test_check_debounce_active(self, redis_manager, mock_redis):
        """Test checking if debounce is active."""
        mock_redis.exists.return_value = 1

        result = redis_manager.check_debounce(123)

        assert result is True
        mock_redis.exists.assert_called_once_with(f"{DEBOUNCE_PREFIX}123")

    def test_check_debounce_inactive(self, redis_manager, mock_redis):
        """Test checking if debounce is inactive."""
        mock_redis.exists.return_value = 0

        result = redis_manager.check_debounce(123)

        assert result is False

    def test_clear_debounce(self, redis_manager, mock_redis):
        """Test clearing debounce key."""
        mock_redis.delete.return_value = 1

        result = redis_manager.clear_debounce(123)

        assert result is True
        mock_redis.delete.assert_called_once_with(f"{DEBOUNCE_PREFIX}123")

    def test_get_debounce_ttl(self, redis_manager, mock_redis):
        """Test getting debounce TTL."""
        mock_redis.ttl.return_value = 25

        result = redis_manager.get_debounce_ttl(123)

        assert result == 25


class TestWatcherStateManagement:
    """Tests for watcher state operations."""

    def test_set_watcher_state(self, redis_manager, mock_redis):
        """Test setting watcher state."""
        now = datetime.utcnow()

        redis_manager.set_watcher_state(
            123, active=True, last_event=now, pending_scan=False
        )

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == f"{WATCHER_STATE_PREFIX}123"
        mapping = call_args[1]["mapping"]
        assert mapping["active"] == "1"
        assert mapping["pending_scan"] == "0"
        assert "last_event" in mapping

    def test_get_watcher_state(self, redis_manager, mock_redis):
        """Test getting watcher state."""
        now = datetime.utcnow()
        mock_redis.hgetall.return_value = {
            b"active": b"1",
            b"pending_scan": b"0",
            b"last_event": now.isoformat().encode(),
        }

        result = redis_manager.get_watcher_state(123)

        assert result["active"] is True
        assert result["pending_scan"] is False
        assert result["last_event"] is not None

    def test_get_watcher_state_not_found(self, redis_manager, mock_redis):
        """Test getting non-existent watcher state."""
        mock_redis.hgetall.return_value = {}

        result = redis_manager.get_watcher_state(123)

        assert result is None

    def test_is_watcher_active(self, redis_manager, mock_redis):
        """Test checking if watcher is active."""
        mock_redis.hgetall.return_value = {b"active": b"1", b"pending_scan": b"0"}

        result = redis_manager.is_watcher_active(123)

        assert result is True


class TestHeartbeatManagement:
    """Tests for watcher heartbeat operations."""

    def test_set_heartbeat(self, redis_manager, mock_redis):
        """Test setting heartbeat."""
        redis_manager.set_heartbeat(123, ttl_seconds=15)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"{WATCHER_HEARTBEAT_PREFIX}123"
        assert call_args[1]["ex"] == 15

    def test_check_heartbeat_alive(self, redis_manager, mock_redis):
        """Test checking heartbeat when alive."""
        mock_redis.exists.return_value = 1

        result = redis_manager.check_heartbeat(123)

        assert result is True

    def test_check_heartbeat_dead(self, redis_manager, mock_redis):
        """Test checking heartbeat when dead."""
        mock_redis.exists.return_value = 0

        result = redis_manager.check_heartbeat(123)

        assert result is False


class TestScanProgressManagement:
    """Tests for scan progress operations."""

    def test_set_scan_progress(self, redis_manager, mock_redis):
        """Test setting scan progress."""
        now = datetime.utcnow()

        redis_manager.set_scan_progress(
            library_id=123,
            scan_id=456,
            status="scanning",
            items_total=100,
            items_processed=50,
            current_file="/path/to/file.mp3",
            started_at=now,
        )

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == f"{SCAN_PROGRESS_PREFIX}123"
        mapping = call_args[1]["mapping"]
        assert mapping["scan_id"] == "456"
        assert mapping["status"] == "scanning"
        assert mapping["items_total"] == "100"
        assert mapping["items_processed"] == "50"
        assert mapping["current_file"] == "/path/to/file.mp3"

    def test_get_scan_progress(self, redis_manager, mock_redis):
        """Test getting scan progress."""
        mock_redis.hgetall.return_value = {
            b"scan_id": b"456",
            b"status": b"scanning",
            b"items_total": b"100",
            b"items_processed": b"50",
            b"current_file": b"/path/to/file.mp3",
        }

        result = redis_manager.get_scan_progress(123)

        assert result["scan_id"] == 456
        assert result["status"] == "scanning"
        assert result["items_total"] == 100
        assert result["items_processed"] == 50
        assert result["current_file"] == "/path/to/file.mp3"


class TestScanQueueManagement:
    """Tests for scan queue operations."""

    def test_enqueue_scan(self, redis_manager, mock_redis):
        """Test enqueueing a scan."""
        mock_redis.rpush.return_value = 1

        result = redis_manager.enqueue_scan(123, triggered_by="manual")

        assert result == 1
        mock_redis.rpush.assert_called_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == f"{SCAN_QUEUE_PREFIX}123"

    def test_dequeue_scan(self, redis_manager, mock_redis):
        """Test dequeuing a scan."""
        mock_redis.lpop.return_value = json.dumps({
            "triggered_by": "manual",
            "queued_at": "2024-01-01T00:00:00",
        }).encode()

        result = redis_manager.dequeue_scan(123)

        assert result["triggered_by"] == "manual"
        mock_redis.lpop.assert_called_once_with(f"{SCAN_QUEUE_PREFIX}123")

    def test_dequeue_scan_empty(self, redis_manager, mock_redis):
        """Test dequeuing from empty queue."""
        mock_redis.lpop.return_value = None

        result = redis_manager.dequeue_scan(123)

        assert result is None

    def test_get_scan_queue_length(self, redis_manager, mock_redis):
        """Test getting queue length."""
        mock_redis.llen.return_value = 3

        result = redis_manager.get_scan_queue_length(123)

        assert result == 3


class TestOperationLockManagement:
    """Tests for operation lock operations."""

    def test_acquire_operation_lock(self, redis_manager, mock_redis):
        """Test acquiring an operation lock."""
        mock_redis.sadd.return_value = 1

        result = redis_manager.acquire_operation_lock(123, "import")

        assert result is True
        mock_redis.sadd.assert_called_once_with(f"{OPERATION_LOCK_PREFIX}123", "import")

    def test_release_operation_lock(self, redis_manager, mock_redis):
        """Test releasing an operation lock."""
        mock_redis.srem.return_value = 1

        result = redis_manager.release_operation_lock(123, "import")

        assert result is True
        mock_redis.srem.assert_called_once_with(f"{OPERATION_LOCK_PREFIX}123", "import")

    def test_check_operation_lock(self, redis_manager, mock_redis):
        """Test checking an operation lock."""
        mock_redis.sismember.return_value = True

        result = redis_manager.check_operation_lock(123, "import")

        assert result is True

    def test_get_active_operations(self, redis_manager, mock_redis):
        """Test getting active operations."""
        mock_redis.smembers.return_value = {b"import", b"tag_modify"}

        result = redis_manager.get_active_operations(123)

        assert "import" in result
        assert "tag_modify" in result

    def test_has_blocking_operations_true(self, redis_manager, mock_redis):
        """Test checking for blocking operations when present."""
        mock_redis.smembers.return_value = {b"import"}

        result = redis_manager.has_blocking_operations(123)

        assert result is True

    def test_has_blocking_operations_false(self, redis_manager, mock_redis):
        """Test checking for blocking operations when none."""
        mock_redis.smembers.return_value = set()

        result = redis_manager.has_blocking_operations(123)

        assert result is False


class TestPubSubHelpers:
    """Tests for pub/sub operations."""

    def test_get_scan_channel(self, redis_manager):
        """Test getting scan channel name."""
        result = redis_manager.get_scan_channel(123)

        assert result == f"{SCAN_CHANNEL_PREFIX}123"

    def test_publish_scan_event(self, redis_manager, mock_redis):
        """Test publishing a scan event."""
        mock_redis.publish.return_value = 2

        result = redis_manager.publish_scan_event(
            123, "scan_started", {"scan_id": 456}
        )

        assert result == 2
        mock_redis.publish.assert_called_once()


class TestCleanup:
    """Tests for cleanup operations."""

    def test_cleanup_library_keys(self, redis_manager, mock_redis):
        """Test cleaning up all library keys."""
        mock_redis.delete.return_value = 1

        result = redis_manager.cleanup_library_keys(123)

        assert "debounce" in result
        assert "watcher_state" in result
        assert "heartbeat" in result
        assert "scan_progress" in result
        assert "scan_queue" in result
        assert "operation_locks" in result
        assert "analysis_queue" in result
        assert "active_analyses" in result


class TestAnalysisQueueManagement:
    """Tests for analysis queue operations."""

    def test_enqueue_album_analysis(self, redis_manager, mock_redis):
        """Test enqueueing an album for analysis."""
        mock_redis.rpush.return_value = 1

        result = redis_manager.enqueue_album_analysis(123, "/import/Artist/Album")

        assert result == 1
        mock_redis.rpush.assert_called_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == f"{BEETS_ANALYSIS_QUEUE_PREFIX}123"
        # Check that JSON was pushed
        pushed_json = call_args[0][1]
        data = json.loads(pushed_json)
        assert data["album_path"] == "/import/Artist/Album"
        assert "queued_at" in data

    def test_register_active_analysis(self, redis_manager, mock_redis):
        """Test registering an active analysis."""
        redis_manager.register_active_analysis(
            123, "job-uuid-123", "/import/Artist/Album"
        )

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == f"{BEETS_ACTIVE_ANALYSES_PREFIX}123"
        assert call_args[0][1] == "job-uuid-123"

    def test_unregister_active_analysis(self, redis_manager, mock_redis):
        """Test unregistering an active analysis."""
        mock_redis.hdel.return_value = 1

        result = redis_manager.unregister_active_analysis(123, "job-uuid-123")

        assert result is True
        mock_redis.hdel.assert_called_once_with(
            f"{BEETS_ACTIVE_ANALYSES_PREFIX}123", "job-uuid-123"
        )

    def test_get_analysis_queue_depth(self, redis_manager, mock_redis):
        """Test getting analysis queue depth."""
        mock_redis.llen.return_value = 5

        result = redis_manager.get_analysis_queue_depth(123)

        assert result == 5
        mock_redis.llen.assert_called_once_with(f"{BEETS_ANALYSIS_QUEUE_PREFIX}123")

    def test_get_active_analysis_count(self, redis_manager, mock_redis):
        """Test getting active analysis count."""
        mock_redis.hlen.return_value = 2

        result = redis_manager.get_active_analysis_count(123)

        assert result == 2
        mock_redis.hlen.assert_called_once_with(f"{BEETS_ACTIVE_ANALYSES_PREFIX}123")

    def test_get_analysis_queue_items(self, redis_manager, mock_redis):
        """Test getting all items in the analysis queue."""
        mock_redis.lrange.return_value = [
            json.dumps({
                "album_path": "/import/Artist1/Album1",
                "queued_at": "2024-01-01T10:00:00Z",
            }).encode(),
            json.dumps({
                "album_path": "/import/Artist2/Album2",
                "queued_at": "2024-01-01T10:01:00Z",
            }).encode(),
        ]

        result = redis_manager.get_analysis_queue_items(123)

        assert len(result) == 2
        assert result[0]["album_path"] == "/import/Artist1/Album1"
        assert result[0]["position"] == 1
        assert result[1]["album_path"] == "/import/Artist2/Album2"
        assert result[1]["position"] == 2

    def test_get_active_analysis_items(self, redis_manager, mock_redis):
        """Test getting active analysis items."""
        mock_redis.hgetall.return_value = {
            b"job-1": b"job-1|2024-01-01T10:00:00Z|/import/Artist1/Album1",
            b"job-2": b"job-2|2024-01-01T10:01:00Z|/import/Artist2/Album2",
        }

        result = redis_manager.get_active_analysis_items(123)

        assert len(result) == 2
        job_ids = {item["job_id"] for item in result}
        assert "job-1" in job_ids
        assert "job-2" in job_ids

    def test_is_album_in_queue_or_active_when_queued(self, redis_manager, mock_redis):
        """Test checking if album is queued."""
        mock_redis.lrange.return_value = [
            json.dumps({
                "album_path": "/import/Artist/Album",
                "queued_at": "2024-01-01T10:00:00Z",
            }).encode(),
        ]
        mock_redis.hgetall.return_value = {}

        is_queued, position, is_active = redis_manager.is_album_in_queue_or_active(
            123, "/import/Artist/Album"
        )

        assert is_queued is True
        assert position == 1
        assert is_active is False

    def test_is_album_in_queue_or_active_when_active(self, redis_manager, mock_redis):
        """Test checking if album is active."""
        mock_redis.lrange.return_value = []
        mock_redis.hgetall.return_value = {
            b"job-1": b"job-1|2024-01-01T10:00:00Z|/import/Artist/Album",
        }

        is_queued, position, is_active = redis_manager.is_album_in_queue_or_active(
            123, "/import/Artist/Album"
        )

        assert is_queued is False
        assert position is None
        assert is_active is True

    def test_is_album_in_queue_or_active_when_neither(self, redis_manager, mock_redis):
        """Test checking if album is neither queued nor active."""
        mock_redis.lrange.return_value = []
        mock_redis.hgetall.return_value = {}

        is_queued, position, is_active = redis_manager.is_album_in_queue_or_active(
            123, "/import/Artist/Album"
        )

        assert is_queued is False
        assert position is None
        assert is_active is False

    def test_clear_analysis_queue(self, redis_manager, mock_redis):
        """Test clearing the analysis queue."""
        mock_redis.delete.return_value = 1

        result = redis_manager.clear_analysis_queue(123)

        assert result is True
        mock_redis.delete.assert_called_once_with(f"{BEETS_ANALYSIS_QUEUE_PREFIX}123")

    def test_clear_active_analyses(self, redis_manager, mock_redis):
        """Test clearing active analyses."""
        mock_redis.delete.return_value = 1

        result = redis_manager.clear_active_analyses(123)

        assert result is True
        mock_redis.delete.assert_called_once_with(f"{BEETS_ACTIVE_ANALYSES_PREFIX}123")

    def test_dequeue_next_album_when_below_cap(self, redis_manager, mock_redis):
        """Test dequeuing next album when below concurrency cap."""
        album_item = json.dumps({
            "album_path": "/import/Artist/Album",
            "queued_at": "2024-01-01T10:00:00Z",
        })
        mock_redis.eval.return_value = [album_item.encode(), b"job-uuid-123"]

        result = redis_manager.dequeue_next_album(123, 2, "job-uuid-123")

        assert result is not None
        assert result["album_path"] == "/import/Artist/Album"
        mock_redis.eval.assert_called_once()

    def test_dequeue_next_album_at_capacity(self, redis_manager, mock_redis):
        """Test dequeuing next album when at concurrency cap."""
        mock_redis.eval.return_value = None

        result = redis_manager.dequeue_next_album(123, 2, "job-uuid-123")

        assert result is None

    def test_dequeue_next_album_empty_queue(self, redis_manager, mock_redis):
        """Test dequeuing from empty queue."""
        mock_redis.eval.return_value = None

        result = redis_manager.dequeue_next_album(123, 2, "job-uuid-123")

        assert result is None


class TestCoverArtDiscoveryCache:
    """Tests for cover art discovery caching operations."""

    def test_hash_db_path(self, redis_manager):
        """Test database path hashing."""
        db_path = "/path/to/library.db"

        result = redis_manager._hash_db_path(db_path)

        # Should return 16-character hash
        assert len(result) == 16
        # Should be consistent
        assert result == redis_manager._hash_db_path(db_path)

    def test_hash_db_path_different_paths(self, redis_manager):
        """Test that different paths produce different hashes."""
        path1 = "/path/to/library1.db"
        path2 = "/path/to/library2.db"

        hash1 = redis_manager._hash_db_path(path1)
        hash2 = redis_manager._hash_db_path(path2)

        assert hash1 != hash2

    def test_get_discovered_cover_art_found(self, redis_manager, mock_redis):
        """Test getting cached cover art path."""
        mock_redis.get.return_value = b"/path/to/cover.jpg"

        result = redis_manager.get_discovered_cover_art("/db/path.db", 42)

        assert result == "/path/to/cover.jpg"
        mock_redis.get.assert_called_once()
        call_args = mock_redis.get.call_args[0][0]
        assert call_args.startswith(COVER_DISCOVERED_PREFIX)
        assert ":42" in call_args

    def test_get_discovered_cover_art_not_found(self, redis_manager, mock_redis):
        """Test cache miss returns None."""
        mock_redis.get.return_value = None

        result = redis_manager.get_discovered_cover_art("/db/path.db", 42)

        assert result is None

    def test_get_discovered_cover_art_negative_cache(
        self, redis_manager, mock_redis
    ):
        """Test negative cache (empty string) is returned."""
        mock_redis.get.return_value = b""

        result = redis_manager.get_discovered_cover_art("/db/path.db", 42)

        assert result == ""

    def test_get_discovered_cover_art_string_response(
        self, redis_manager, mock_redis
    ):
        """Test handling string response (non-bytes)."""
        mock_redis.get.return_value = "/path/to/cover.jpg"

        result = redis_manager.get_discovered_cover_art("/db/path.db", 42)

        assert result == "/path/to/cover.jpg"

    def test_set_discovered_cover_art(self, redis_manager, mock_redis):
        """Test caching discovered cover art path."""
        redis_manager.set_discovered_cover_art(
            "/db/path.db", 42, "/path/to/cover.jpg"
        )

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        value = call_args[0][1]
        ttl = call_args[1]["ex"]

        assert key.startswith(COVER_DISCOVERED_PREFIX)
        assert ":42" in key
        assert value == "/path/to/cover.jpg"
        assert ttl == 604800  # 7 days

    def test_set_discovered_cover_art_custom_ttl(self, redis_manager, mock_redis):
        """Test caching with custom TTL."""
        redis_manager.set_discovered_cover_art(
            "/db/path.db", 42, "/path/to/cover.jpg", ttl_seconds=3600
        )

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 3600

    def test_set_discovered_cover_art_negative_cache(
        self, redis_manager, mock_redis
    ):
        """Test caching negative result (empty string)."""
        redis_manager.set_discovered_cover_art("/db/path.db", 42, "")

        call_args = mock_redis.set.call_args
        assert call_args[0][1] == ""

    def test_invalidate_discovered_cover_art(self, redis_manager, mock_redis):
        """Test invalidating single album cache."""
        mock_redis.delete.return_value = 1

        result = redis_manager.invalidate_discovered_cover_art("/db/path.db", 42)

        assert result is True
        mock_redis.delete.assert_called_once()
        call_args = mock_redis.delete.call_args[0][0]
        assert call_args.startswith(COVER_DISCOVERED_PREFIX)
        assert ":42" in call_args

    def test_invalidate_discovered_cover_art_not_found(
        self, redis_manager, mock_redis
    ):
        """Test invalidating non-existent cache returns False."""
        mock_redis.delete.return_value = 0

        result = redis_manager.invalidate_discovered_cover_art("/db/path.db", 42)

        assert result is False

    def test_invalidate_all_discovered_cover_art(self, redis_manager, mock_redis):
        """Test invalidating all cache for a library."""
        mock_redis.scan_iter.return_value = [
            b"cover:discovered:abc123:1",
            b"cover:discovered:abc123:2",
            b"cover:discovered:abc123:3",
        ]
        mock_redis.delete.return_value = 3

        result = redis_manager.invalidate_all_discovered_cover_art("/db/path.db")

        assert result == 3
        mock_redis.scan_iter.assert_called_once()
        mock_redis.delete.assert_called_once()

    def test_invalidate_all_discovered_cover_art_empty(
        self, redis_manager, mock_redis
    ):
        """Test invalidating when no keys exist."""
        mock_redis.scan_iter.return_value = []

        result = redis_manager.invalidate_all_discovered_cover_art("/db/path.db")

        assert result == 0
        mock_redis.delete.assert_not_called()
