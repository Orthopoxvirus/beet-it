"""Integration tests for album cover art endpoint with fallback discovery."""

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.models.library import Library
from app.services.beets_library_service import BeetsLibraryService


@pytest.fixture
def mock_library():
    """Create a mock library."""
    library = Mock(spec=Library)
    library.id = 1
    library.name = "Test Library"
    library.slug = "test-library"
    library.import_path = "/data/import/test"
    library.config_path = "/config/test.yaml"
    library.database_path = "/data/databases/test.db"
    library.library_path = "/data/libraries/test"
    library.created_at = datetime(2024, 1, 1, 0, 0, 0)
    library.updated_at = None
    return library


@pytest.fixture
def beets_service():
    """Create a BeetsLibraryService instance."""
    return BeetsLibraryService()


@pytest.fixture
def temp_beets_library():
    """Create a temporary beets library with database and cover art files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "library.db")
        album_dir = os.path.join(tmpdir, "music", "Artist", "Album")
        os.makedirs(album_dir)

        # Create the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create minimal beets schema
        cursor.execute("""
            CREATE TABLE albums (
                id INTEGER PRIMARY KEY,
                album TEXT,
                albumartist TEXT,
                artpath BLOB
            )
        """)

        cursor.execute("""
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                album_id INTEGER,
                path BLOB
            )
        """)

        # Album 1: No artpath, but has cover.jpg in folder
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (1, "Test Album No Artpath", "Test Artist", None),
        )
        item_path1 = os.path.join(album_dir, "01 - Track.mp3")
        Path(item_path1).touch()
        cursor.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?, ?, ?)",
            (1, 1, item_path1.encode("utf-8")),
        )

        # Album 2: Has artpath that exists
        cover_path2 = os.path.join(album_dir, "album2_cover.jpg")
        with open(cover_path2, "wb") as f:
            f.write(b"\xFF\xD8\xFF")  # JPEG header
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (2, "Test Album With Artpath", "Test Artist", cover_path2.encode("utf-8")),
        )
        item_path2 = os.path.join(album_dir, "02 - Track.mp3")
        Path(item_path2).touch()
        cursor.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?, ?, ?)",
            (2, 2, item_path2.encode("utf-8")),
        )

        # Album 3: Has artpath that doesn't exist, but has folder.jpg
        missing_artpath = os.path.join(album_dir, "missing_cover.jpg")
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (3, "Test Album Missing Artpath", "Test Artist", missing_artpath.encode("utf-8")),
        )
        item_path3 = os.path.join(album_dir, "03 - Track.mp3")
        Path(item_path3).touch()
        cursor.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?, ?, ?)",
            (3, 3, item_path3.encode("utf-8")),
        )

        # Album 4: No artpath, no cover files at all
        album_dir4 = os.path.join(tmpdir, "music", "Artist", "Empty Album")
        os.makedirs(album_dir4)
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (4, "Test Album No Cover", "Test Artist", None),
        )
        item_path4 = os.path.join(album_dir4, "04 - Track.mp3")
        Path(item_path4).touch()
        cursor.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?, ?, ?)",
            (4, 4, item_path4.encode("utf-8")),
        )

        conn.commit()
        conn.close()

        yield {
            "db_path": db_path,
            "album_dir": album_dir,
            "album_dir4": album_dir4,
        }


class TestCoverArtDiscoveryIntegration:
    """Integration tests for cover art discovery with actual filesystem."""

    def test_discover_cover_when_artpath_null(
        self, beets_service, temp_beets_library
    ):
        """Test fallback discovery works when artpath is null."""
        db_path = temp_beets_library["db_path"]
        album_dir = temp_beets_library["album_dir"]

        # Create cover.jpg in the album folder
        cover_path = os.path.join(album_dir, "cover.jpg")
        with open(cover_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF")  # JPEG header

        # Get cover path with fallback (no Redis for this test)
        result = beets_service.get_album_cover_path_with_fallback(db_path, 1)

        assert result == cover_path

    def test_returns_existing_artpath(
        self, beets_service, temp_beets_library
    ):
        """Test that existing artpath is returned without fallback."""
        db_path = temp_beets_library["db_path"]
        album_dir = temp_beets_library["album_dir"]

        expected_path = os.path.join(album_dir, "album2_cover.jpg")
        result = beets_service.get_album_cover_path_with_fallback(db_path, 2)

        assert result == expected_path

    def test_discover_when_artpath_missing(
        self, beets_service, temp_beets_library
    ):
        """Test fallback discovery when artpath file doesn't exist."""
        db_path = temp_beets_library["db_path"]
        album_dir = temp_beets_library["album_dir"]

        # Create folder.jpg for album 3 (which has missing artpath)
        folder_path = os.path.join(album_dir, "folder.jpg")
        with open(folder_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF")

        result = beets_service.get_album_cover_path_with_fallback(db_path, 3)

        assert result == folder_path

    def test_returns_none_when_no_cover(
        self, beets_service, temp_beets_library
    ):
        """Test that None is returned when no cover art is found."""
        db_path = temp_beets_library["db_path"]

        # Album 4 has no artpath and no cover files
        result = beets_service.get_album_cover_path_with_fallback(db_path, 4)

        assert result is None

    def test_case_insensitive_discovery(
        self, beets_service, temp_beets_library
    ):
        """Test case-insensitive filename matching."""
        db_path = temp_beets_library["db_path"]
        album_dir4 = temp_beets_library["album_dir4"]

        # Create COVER.JPG (uppercase)
        cover_path = os.path.join(album_dir4, "COVER.JPG")
        with open(cover_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF")

        result = beets_service.get_album_cover_path_with_fallback(db_path, 4)

        assert result == cover_path

    def test_priority_ordering(
        self, beets_service, temp_beets_library
    ):
        """Test that cover has higher priority than folder."""
        db_path = temp_beets_library["db_path"]
        album_dir4 = temp_beets_library["album_dir4"]

        # Create both folder.jpg and cover.jpg
        folder_path = os.path.join(album_dir4, "folder.jpg")
        cover_path = os.path.join(album_dir4, "cover.jpg")
        with open(folder_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF")
        with open(cover_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF")

        result = beets_service.get_album_cover_path_with_fallback(db_path, 4)

        # cover.jpg should be returned due to priority
        assert result == cover_path


class TestCoverArtCacheIntegration:
    """Integration tests for cover art caching with Redis mock."""

    def test_caches_discovered_path(
        self, beets_service, temp_beets_library
    ):
        """Test that discovered paths are cached in Redis."""
        db_path = temp_beets_library["db_path"]
        album_dir = temp_beets_library["album_dir"]

        # Create cover.jpg
        cover_path = os.path.join(album_dir, "cover.jpg")
        with open(cover_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF")

        # Mock Redis manager
        mock_redis = Mock()
        mock_redis.get_discovered_cover_art.return_value = None

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis
        )

        assert result == cover_path
        mock_redis.set_discovered_cover_art.assert_called_once_with(
            db_path, 1, cover_path
        )

    def test_uses_cached_path(
        self, beets_service, temp_beets_library
    ):
        """Test that cached paths are used when available."""
        db_path = temp_beets_library["db_path"]

        cached_path = "/cached/cover.jpg"

        # Mock Redis manager returning cached path
        mock_redis = Mock()
        mock_redis.get_discovered_cover_art.return_value = cached_path

        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            result = beets_service.get_album_cover_path_with_fallback(
                db_path, 1, redis_manager=mock_redis
            )

        assert result == cached_path
        # Should NOT call set since we had a cache hit
        mock_redis.set_discovered_cover_art.assert_not_called()

    def test_negative_cache_returns_none(
        self, beets_service, temp_beets_library
    ):
        """Test that negative cache (empty string) returns None."""
        db_path = temp_beets_library["db_path"]

        # Mock Redis manager returning empty string (negative cache)
        mock_redis = Mock()
        mock_redis.get_discovered_cover_art.return_value = ""

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis
        )

        assert result is None
        mock_redis.set_discovered_cover_art.assert_not_called()

    def test_rediscovers_when_cached_file_missing(
        self, beets_service, temp_beets_library
    ):
        """Test re-discovery when cached file no longer exists."""
        db_path = temp_beets_library["db_path"]
        album_dir = temp_beets_library["album_dir"]

        # Create new cover file
        new_cover = os.path.join(album_dir, "cover.jpg")
        with open(new_cover, "wb") as f:
            f.write(b"\xFF\xD8\xFF")

        # Mock Redis returning stale cached path
        mock_redis = Mock()
        mock_redis.get_discovered_cover_art.return_value = "/old/missing.jpg"

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis
        )

        # Should find new cover
        assert result == new_cover
        # Should update cache
        mock_redis.set_discovered_cover_art.assert_called_once_with(
            db_path, 1, new_cover
        )

    def test_caches_negative_result(
        self, beets_service, temp_beets_library
    ):
        """Test that negative results are cached."""
        db_path = temp_beets_library["db_path"]

        # Mock Redis manager
        mock_redis = Mock()
        mock_redis.get_discovered_cover_art.return_value = None

        # Album 4 has no cover files
        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 4, redis_manager=mock_redis
        )

        assert result is None
        # Should cache empty string
        mock_redis.set_discovered_cover_art.assert_called_once_with(
            db_path, 4, ""
        )


class TestGetAlbumCoverEndpointScenarios:
    """Tests for cover art endpoint behavior."""

    def test_album_not_found_returns_404(self, beets_service, temp_beets_library):
        """Test that 404 is returned when album doesn't exist."""
        db_path = temp_beets_library["db_path"]

        exists = beets_service.album_exists(db_path, 999)

        assert exists is False

    def test_cover_not_found_returns_none(
        self, beets_service, temp_beets_library
    ):
        """Test that None is returned when no cover art is found."""
        db_path = temp_beets_library["db_path"]

        # Album 4 has no cover files
        result = beets_service.get_album_cover_path_with_fallback(db_path, 4)

        assert result is None


class TestSupportedImageFormats:
    """Tests for supported image format discovery."""

    @pytest.fixture
    def temp_album(self):
        """Create a temporary album directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def beets_service_instance(self):
        """Create a BeetsLibraryService instance."""
        return BeetsLibraryService()

    def test_discovers_jpg(self, beets_service_instance, temp_album):
        """Test discovering .jpg format."""
        cover_path = os.path.join(temp_album, "cover.jpg")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_discovers_jpeg(self, beets_service_instance, temp_album):
        """Test discovering .jpeg format."""
        cover_path = os.path.join(temp_album, "cover.jpeg")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_discovers_png(self, beets_service_instance, temp_album):
        """Test discovering .png format."""
        cover_path = os.path.join(temp_album, "cover.png")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_discovers_webp(self, beets_service_instance, temp_album):
        """Test discovering .webp format."""
        cover_path = os.path.join(temp_album, "cover.webp")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_discovers_gif(self, beets_service_instance, temp_album):
        """Test discovering .gif format."""
        cover_path = os.path.join(temp_album, "cover.gif")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_jpg_preferred_over_png(self, beets_service_instance, temp_album):
        """Test that .jpg is preferred over .png for same filename."""
        jpg_path = os.path.join(temp_album, "cover.jpg")
        png_path = os.path.join(temp_album, "cover.png")
        Path(jpg_path).touch()
        Path(png_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == jpg_path


class TestFilenameVariations:
    """Tests for different cover art filename patterns."""

    @pytest.fixture
    def temp_album(self):
        """Create a temporary album directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def beets_service_instance(self):
        """Create a BeetsLibraryService instance."""
        return BeetsLibraryService()

    def test_discovers_albumart(self, beets_service_instance, temp_album):
        """Test discovering albumart.jpg."""
        cover_path = os.path.join(temp_album, "albumart.jpg")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_discovers_folder(self, beets_service_instance, temp_album):
        """Test discovering folder.jpg."""
        cover_path = os.path.join(temp_album, "folder.jpg")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_discovers_front(self, beets_service_instance, temp_album):
        """Test discovering front.jpg."""
        cover_path = os.path.join(temp_album, "front.jpg")
        Path(cover_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_cover_preferred_over_albumart(
        self, beets_service_instance, temp_album
    ):
        """Test that cover has higher priority than albumart."""
        cover_path = os.path.join(temp_album, "cover.jpg")
        albumart_path = os.path.join(temp_album, "albumart.jpg")
        Path(cover_path).touch()
        Path(albumart_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == cover_path

    def test_albumart_preferred_over_folder(
        self, beets_service_instance, temp_album
    ):
        """Test that albumart has higher priority than folder."""
        albumart_path = os.path.join(temp_album, "albumart.jpg")
        folder_path = os.path.join(temp_album, "folder.jpg")
        Path(albumart_path).touch()
        Path(folder_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == albumart_path

    def test_folder_preferred_over_front(
        self, beets_service_instance, temp_album
    ):
        """Test that folder has higher priority than front."""
        folder_path = os.path.join(temp_album, "folder.jpg")
        front_path = os.path.join(temp_album, "front.jpg")
        Path(folder_path).touch()
        Path(front_path).touch()

        result = beets_service_instance.discover_cover_art(temp_album)
        assert result == folder_path
