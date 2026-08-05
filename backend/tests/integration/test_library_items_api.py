"""Integration tests for library items batch edit API endpoints.

Tests cover:
- GET /api/v1/libraries/{slug}/library-items
- POST /api/v1/libraries/{slug}/library-items/preview
- POST /api/v1/libraries/{slug}/library-items/batch-update
- GET /api/v1/libraries/{slug}/batch-update-status/{job_id}
"""

import os
import sqlite3
import tempfile
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.database import get_db
from app.models.library import Library
from app.services.beets_library_service import LibraryItemData


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_library_db():
    """Create a temporary beets database with items for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "library.db")
        music_dir = os.path.join(tmpdir, "music")
        os.makedirs(music_dir)

        # Create the database with full items schema
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create albums table
        cursor.execute("""
            CREATE TABLE albums (
                id INTEGER PRIMARY KEY,
                album TEXT,
                albumartist TEXT,
                artpath BLOB,
                year INTEGER,
                genre TEXT,
                genres TEXT
            )
        """)

        # Create items table
        cursor.execute("""
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                album_id INTEGER,
                path BLOB,
                title TEXT,
                artist TEXT,
                track INTEGER,
                disc INTEGER,
                genre TEXT,
                genres TEXT,
                format TEXT,
                bitrate INTEGER,
                FOREIGN KEY (album_id) REFERENCES albums(id)
            )
        """)

        # Insert test album
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, year) VALUES (?, ?, ?, ?)",
            (1, "Test Album", "Test Artist", 2023),
        )

        # Insert test items
        for i in range(1, 4):
            item_path = os.path.join(music_dir, f"track_{i}.mp3")
            # Create actual file for tag writer tests
            with open(item_path, "wb") as f:
                # Minimal MP3 header
                f.write(bytes([0xFF, 0xFB, 0x90, 0x00] + [0x00] * 417))
            cursor.execute(
                "INSERT INTO items (id, album_id, path, title, artist, track, disc, genre, format, bitrate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (i, 1, item_path.encode("utf-8"), f"Track {i}", "Test Artist", i, 1, "Rock", "MP3", 320000),
            )

        conn.commit()
        conn.close()

        yield {"db_path": db_path, "music_dir": music_dir}


@pytest.fixture
def mock_library(temp_library_db):
    """Create a mock library object."""
    library = Mock()
    library.id = 1
    library.slug = "test-library"
    library.name = "Test Library"
    library.database_path = temp_library_db["db_path"]
    library.config_path = None
    library.library_path = temp_library_db["music_dir"]
    return library


@pytest.fixture
def mock_db_session(mock_library):
    """Create a mock database session."""
    session = Mock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = mock_library
    return session


@pytest.fixture
def client(mock_db_session):
    """Create test client with mocked database."""
    def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ============================================================================
# GET /api/v1/libraries/{slug}/library-items Tests
# ============================================================================


class TestGetLibraryItemsEndpoint:
    """Tests for the GET library items endpoint."""

    def test_get_library_items_success(self, client, temp_library_db, mock_db_session, mock_library):
        """Test successful retrieval of library items."""
        response = client.get("/api/v1/libraries/test-library/library-items")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_get_library_items_with_album_filter(self, client, temp_library_db):
        """Test getting items filtered by album ID."""
        response = client.get("/api/v1/libraries/test-library/library-items?album_id=1")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        for item in data["items"]:
            assert item["album_id"] == 1

    def test_get_library_items_pagination(self, client, temp_library_db):
        """Test pagination parameters."""
        response = client.get("/api/v1/libraries/test-library/library-items?page=1&page_size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["total_pages"] == 2

    def test_get_library_items_library_not_found(self, client, mock_db_session):
        """Test 404 when library not found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.get("/api/v1/libraries/nonexistent/library-items")

        assert response.status_code == 404
        assert response.json()["detail"] == "Library not found"

    def test_get_library_items_no_database(self, client, mock_db_session, mock_library):
        """Test error when library has no database configured."""
        mock_library.database_path = None
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_library

        response = client.get("/api/v1/libraries/test-library/library-items")

        assert response.status_code == 400
        assert "NO_DATABASE" in response.headers.get("X-Error-Code", "")

    def test_get_library_items_item_structure(self, client, temp_library_db):
        """Test that returned items have correct structure."""
        response = client.get("/api/v1/libraries/test-library/library-items?page_size=1")

        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]

        # Check all expected fields
        assert "id" in item
        assert "path" in item
        assert "filename" in item
        assert "directory" in item
        assert "item_type" in item
        assert item["item_type"] == "track"
        assert "album" in item
        assert "album_artist" in item
        assert "artist" in item
        assert "title" in item
        assert "track_number" in item
        assert "disc_number" in item
        assert "genre" in item
        assert "year" in item
        assert "album_id" in item
        # File/quality facts used by the batch-edit album header row.
        assert item["format"] == "MP3"
        assert item["bitrate"] == 320000


# ============================================================================
# POST /api/v1/libraries/{slug}/library-items/preview Tests
# ============================================================================


class TestPreviewLibraryItemsEndpoint:
    """Tests for the POST library items preview endpoint."""

    def test_preview_fixed_rule(self, client, temp_library_db):
        """Test preview with fixed transformation rule."""
        request_data = {
            "item_ids": [1, 2, 3],
            "rules": [
                {"tag": "album", "mode": "fixed", "value": "New Album Name"}
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert "previews" in data
        assert "errors" in data
        assert len(data["previews"]) == 3
        for preview in data["previews"]:
            assert "album" in preview["changes"]
            assert preview["changes"]["album"] == "New Album Name"

    def test_preview_regex_rule(self, client, temp_library_db):
        """Test preview with regex transformation rule."""
        request_data = {
            "item_ids": [1],
            "rules": [
                {
                    "tag": "title",
                    "mode": "regex",
                    "source_field": "filename",
                    "pattern": r"track_(\d+)\.mp3",
                    "replacement": "Song $1",
                }
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["previews"]) == 1
        assert "title" in data["previews"][0]["changes"]

    def test_preview_nonexistent_items(self, client, temp_library_db):
        """Test preview with nonexistent item IDs."""
        request_data = {
            "item_ids": [1, 999],
            "rules": [
                {"tag": "album", "mode": "fixed", "value": "New Album"}
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["previews"]) == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["code"] == "ITEM_NOT_FOUND"

    def test_preview_invalid_regex(self, client, temp_library_db):
        """Test preview with invalid regex pattern."""
        request_data = {
            "item_ids": [1],
            "rules": [
                {
                    "tag": "title",
                    "mode": "regex",
                    "source_field": "filename",
                    "pattern": "[invalid",  # Invalid regex
                    "replacement": "$1",
                }
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 400
        assert "INVALID_REGEX" in response.headers.get("X-Error-Code", "")

    def test_preview_library_not_found(self, client, mock_db_session):
        """Test 404 when library not found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        request_data = {
            "item_ids": [1],
            "rules": [{"tag": "album", "mode": "fixed", "value": "New"}]
        }

        response = client.post(
            "/api/v1/libraries/nonexistent/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 404

    def test_preview_multiple_rules(self, client, temp_library_db):
        """Test preview with multiple transformation rules."""
        request_data = {
            "item_ids": [1],
            "rules": [
                {"tag": "album", "mode": "fixed", "value": "New Album"},
                {"tag": "artist", "mode": "fixed", "value": "New Artist"},
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["previews"]) == 1
        changes = data["previews"][0]["changes"]
        assert changes.get("album") == "New Album"
        assert changes.get("artist") == "New Artist"


# ============================================================================
# POST /api/v1/libraries/{slug}/library-items/batch-update Tests
# ============================================================================


class TestBatchUpdateLibraryItemsEndpoint:
    """Tests for the POST library items batch-update endpoint."""

    @patch("app.api.routes.library_items.get_tag_writer_registry")
    @patch("app.api.routes.library_items.get_redis_key_manager")
    @patch("app.api.routes.library_items.get_task_event_service")
    @patch("app.api.routes.library_items.beets_update_albums")
    def test_batch_update_success(
        self,
        mock_beets_task,
        mock_task_event_service,
        mock_redis_manager,
        mock_tag_writer,
        client,
        temp_library_db,
    ):
        """Test successful batch update."""
        # Mock tag writer
        mock_writer = Mock()
        mock_writer.write_tags.return_value = Mock(
            success=True,
            tags_written={"album": "New Album"},
            error=None,
            error_code=None,
        )
        mock_tag_writer.return_value = mock_writer

        # Mock Redis manager
        mock_redis = Mock()
        mock_redis_manager.return_value = mock_redis

        # Mock task event service
        mock_events = Mock()
        mock_events.record_start.return_value = 1
        mock_task_event_service.return_value = mock_events

        # Mock Celery task
        mock_beets_task.delay = Mock()

        request_data = {
            "item_ids": [1, 2],
            "rules": [
                {"tag": "album", "mode": "fixed", "value": "New Album"}
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/batch-update",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "job_id" in data
        assert "items_total" in data
        assert "items_succeeded" in data
        assert "items_failed" in data
        assert "results" in data
        assert "albums_to_sync" in data

    @patch("app.api.routes.library_items.beets_update_albums")
    @patch("app.api.routes.library_items.get_tag_writer_registry")
    @patch("app.api.routes.library_items.get_redis_key_manager")
    @patch("app.api.routes.library_items.get_task_event_service")
    def test_batch_update_with_write_failures(
        self,
        mock_task_event_service,
        mock_redis_manager,
        mock_tag_writer,
        mock_beets_task,
        client,
        temp_library_db,
    ):
        """Test batch update with some write failures."""
        # One item succeeds -> the route enqueues a beets sync. Patch the
        # Celery task like the sibling test above, otherwise .delay() tries to
        # reach a real broker and the test only passes where redis resolves.
        mock_beets_task.delay = Mock()
        # Mock tag writer - first succeeds, second fails
        mock_writer = Mock()
        mock_writer.write_tags.side_effect = [
            Mock(success=True, tags_written={"album": "New"}, error=None, error_code=None),
            Mock(success=False, tags_written={}, error="Permission denied", error_code="PERMISSION_DENIED"),
        ]
        mock_tag_writer.return_value = mock_writer

        # Mock Redis manager
        mock_redis = Mock()
        mock_redis_manager.return_value = mock_redis

        # Mock task event service
        mock_events = Mock()
        mock_events.record_start.return_value = 1
        mock_task_event_service.return_value = mock_events

        request_data = {
            "item_ids": [1, 2],
            "rules": [
                {"tag": "album", "mode": "fixed", "value": "New Album"}
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/batch-update",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items_succeeded"] == 1
        assert data["items_failed"] == 1
        assert data["status"] == "partial"

    def test_batch_update_library_not_found(self, client, mock_db_session):
        """Test 404 when library not found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        request_data = {
            "item_ids": [1],
            "rules": [{"tag": "album", "mode": "fixed", "value": "New"}]
        }

        response = client.post(
            "/api/v1/libraries/nonexistent/library-items/batch-update",
            json=request_data,
        )

        assert response.status_code == 404

    def test_batch_update_invalid_regex(self, client, temp_library_db):
        """Test batch update with invalid regex pattern."""
        request_data = {
            "item_ids": [1],
            "rules": [
                {
                    "tag": "title",
                    "mode": "regex",
                    "source_field": "filename",
                    "pattern": "[invalid",
                    "replacement": "$1",
                }
            ]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/batch-update",
            json=request_data,
        )

        assert response.status_code == 400
        assert "INVALID_REGEX" in response.headers.get("X-Error-Code", "")


# ============================================================================
# GET /api/v1/libraries/{slug}/batch-update-status/{job_id} Tests
# ============================================================================


class TestBatchUpdateStatusEndpoint:
    """Tests for the GET batch update status endpoint."""

    @patch("app.api.routes.library_items.get_redis_key_manager")
    def test_get_status_success(self, mock_redis_manager, client, mock_library, mock_db_session):
        """Test successful status retrieval."""
        mock_redis = Mock()
        mock_redis.get_batch_update_status.return_value = {
            "job_id": "test-job-123",
            "status": "completed",
            "library_id": 1,
            "albums": [
                # Album-level status uses AlbumUpdateStatus enum: pending|syncing|success|failed.
                # (Job-level status uses "completed" — a different enum.)
                {"album": "Test Album", "status": "success", "error": None}
            ],
            "started_at": "2023-01-01T00:00:00",
            "completed_at": "2023-01-01T00:01:00",
        }
        mock_redis_manager.return_value = mock_redis

        response = client.get("/api/v1/libraries/test-library/batch-update-status/test-job-123")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "completed"
        # The response surfaces per-album results under `beets_updates`
        # (renamed to reflect that the list is the output of `beet update`).
        assert len(data["beets_updates"]) == 1

    @patch("app.api.routes.library_items.get_redis_key_manager")
    def test_get_status_job_not_found(self, mock_redis_manager, client, mock_library, mock_db_session):
        """Test 404 when job not found."""
        mock_redis = Mock()
        mock_redis.get_batch_update_status.return_value = None
        mock_redis_manager.return_value = mock_redis

        response = client.get("/api/v1/libraries/test-library/batch-update-status/nonexistent")

        assert response.status_code == 404
        assert "JOB_NOT_FOUND" in response.headers.get("X-Error-Code", "")

    @patch("app.api.routes.library_items.get_redis_key_manager")
    def test_get_status_wrong_library(self, mock_redis_manager, client, mock_library, mock_db_session):
        """Test 404 when job belongs to different library."""
        mock_redis = Mock()
        mock_redis.get_batch_update_status.return_value = {
            "job_id": "test-job-123",
            "status": "completed",
            "library_id": 999,  # Different library
            "albums": [],
        }
        mock_redis_manager.return_value = mock_redis

        response = client.get("/api/v1/libraries/test-library/batch-update-status/test-job-123")

        assert response.status_code == 404
        assert "JOB_NOT_FOUND" in response.headers.get("X-Error-Code", "")

    def test_get_status_library_not_found(self, client, mock_db_session):
        """Test 404 when library not found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.get("/api/v1/libraries/nonexistent/batch-update-status/test-job")

        assert response.status_code == 404


# ============================================================================
# Request/Response Schema Validation Tests
# ============================================================================


class TestSchemaValidation:
    """Tests for request/response schema validation."""

    def test_preview_requires_item_ids(self, client, temp_library_db):
        """Test that preview requires at least one item ID."""
        request_data = {
            "item_ids": [],  # Empty
            "rules": [{"tag": "album", "mode": "fixed", "value": "New"}]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 422  # Validation error

    def test_preview_requires_rules(self, client, temp_library_db):
        """Test that preview requires at least one rule."""
        request_data = {
            "item_ids": [1],
            "rules": []  # Empty
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 422  # Validation error

    def test_preview_max_items_limit(self, client, temp_library_db):
        """Test that preview enforces max items limit."""
        request_data = {
            "item_ids": list(range(1, 50002)),  # 50001 items, exceeds max_length=50000
            "rules": [{"tag": "album", "mode": "fixed", "value": "New"}]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/preview",
            json=request_data,
        )

        assert response.status_code == 422  # Validation error

    def test_batch_update_requires_item_ids(self, client, temp_library_db):
        """Test that batch update requires at least one item ID."""
        request_data = {
            "item_ids": [],  # Empty
            "rules": [{"tag": "album", "mode": "fixed", "value": "New"}]
        }

        response = client.post(
            "/api/v1/libraries/test-library/library-items/batch-update",
            json=request_data,
        )

        assert response.status_code == 422  # Validation error

    def test_pagination_bounds(self, client, temp_library_db):
        """Test pagination parameter bounds."""
        # Page 0 should fail
        response = client.get("/api/v1/libraries/test-library/library-items?page=0")
        assert response.status_code == 422

        # Negative page_size should fail
        response = client.get("/api/v1/libraries/test-library/library-items?page_size=-1")
        assert response.status_code == 422

        # Page size above max (le=50000) should fail
        response = client.get("/api/v1/libraries/test-library/library-items?page_size=50001")
        assert response.status_code == 422


class TestMultiAlbumLibraryItemsEndpoint:
    """POST /library-items with repeated album_id query params."""

    def test_multi_album_id(self, client, temp_library_db):
        # The fixture only seeds one album (id=1) with 3 items. Repeat the
        # query param twice and confirm we get the same 3 items back (both
        # repeats resolve to the same album id).
        response = client.get(
            "/api/v1/libraries/test-library/library-items?album_id=1&album_id=1&per_page=500"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert all(item["album_id"] == 1 for item in data["items"])
        # album_filter is only for the legacy name filter.
        assert data["album_filter"] is None

    def test_single_album_id_still_works(self, client):
        """Back-compat: single album_id param is still accepted."""
        response = client.get("/api/v1/libraries/test-library/library-items?album_id=1")
        assert response.status_code == 200


class TestGetLibraryTreeEndpoint:
    def test_returns_nested_tree(self, client, temp_library_db):
        response = client.get("/api/v1/libraries/test-library/library-tree")
        assert response.status_code == 200
        body = response.json()
        assert body["libraryPath"] == temp_library_db["music_dir"]
        root = body["root"]
        # Fixture's items live directly under music_dir → root is a terminal album.
        assert root["isAlbum"] is True
        assert root["albumIds"] == [1]
        assert root["children"] == []

    def test_library_not_found(self, client, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        response = client.get("/api/v1/libraries/does-not-exist/library-tree")
        assert response.status_code == 404
        assert response.headers.get("X-Error-Code") == "LIBRARY_NOT_FOUND"

    def test_no_database_configured(self, client, mock_library):
        mock_library.database_path = None
        response = client.get("/api/v1/libraries/test-library/library-tree")
        assert response.status_code == 400
        assert response.headers.get("X-Error-Code") == "NO_DATABASE"

    def test_no_library_path_configured(self, client, mock_library):
        mock_library.library_path = None
        response = client.get("/api/v1/libraries/test-library/library-tree")
        assert response.status_code == 400
        assert response.headers.get("X-Error-Code") == "NO_LIBRARY_PATH"
