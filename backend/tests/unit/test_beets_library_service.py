"""Unit tests for BeetsLibraryService cover art discovery."""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.beets_library_service import BeetsLibraryService


@pytest.fixture
def beets_service():
    """Create a BeetsLibraryService instance."""
    return BeetsLibraryService()


@pytest.fixture
def temp_album_dir():
    """Create a temporary album directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        album_dir = os.path.join(tmpdir, "Artist", "Album")
        os.makedirs(album_dir)
        yield album_dir


@pytest.fixture
def temp_beets_db():
    """Create a temporary beets database with test data."""
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

        # Insert test data - album with null artpath
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (1, "Test Album", "Test Artist", None),
        )

        # Album with artpath
        cover_path = os.path.join(album_dir, "cover.jpg")
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (2, "Test Album 2", "Test Artist", cover_path.encode("utf-8")),
        )

        # Insert item for album 1
        item_path = os.path.join(album_dir, "01 - Track.mp3")
        Path(item_path).touch()
        cursor.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?, ?, ?)",
            (1, 1, item_path.encode("utf-8")),
        )

        # Insert item for album 2
        item_path2 = os.path.join(album_dir, "02 - Track.mp3")
        Path(item_path2).touch()
        cursor.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?, ?, ?)",
            (2, 2, item_path2.encode("utf-8")),
        )

        # Album with no items
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?, ?, ?, ?)",
            (3, "Empty Album", "Test Artist", None),
        )

        conn.commit()
        conn.close()

        yield {"db_path": db_path, "album_dir": album_dir}


class TestGetAlbumFolderPath:
    """Tests for get_album_folder_path method."""

    def test_get_album_folder_path_returns_directory(
        self, beets_service, temp_beets_db
    ):
        """Test getting album folder path from item paths."""
        db_path = temp_beets_db["db_path"]
        album_dir = temp_beets_db["album_dir"]

        result = beets_service.get_album_folder_path(db_path, 1)

        assert result == album_dir

    def test_get_album_folder_path_no_items(self, beets_service, temp_beets_db):
        """Test getting album folder path when album has no items."""
        db_path = temp_beets_db["db_path"]

        result = beets_service.get_album_folder_path(db_path, 3)

        assert result is None

    def test_get_album_folder_path_album_not_exists(
        self, beets_service, temp_beets_db
    ):
        """Test getting album folder path for non-existent album."""
        db_path = temp_beets_db["db_path"]

        result = beets_service.get_album_folder_path(db_path, 999)

        assert result is None

    def test_get_album_folder_path_db_not_found(self, beets_service):
        """Test getting album folder path with non-existent database."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_album_folder_path("/nonexistent/db.db", 1)


class TestDiscoverCoverArt:
    """Tests for discover_cover_art method."""

    def test_discover_cover_art_finds_cover_jpg(
        self, beets_service, temp_album_dir
    ):
        """Test discovering cover.jpg in album folder."""
        cover_path = os.path.join(temp_album_dir, "cover.jpg")
        Path(cover_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result == cover_path

    def test_discover_cover_art_case_insensitive(
        self, beets_service, temp_album_dir
    ):
        """Test case-insensitive filename matching."""
        cover_path = os.path.join(temp_album_dir, "Cover.JPG")
        Path(cover_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result == cover_path

    def test_discover_cover_art_priority_order(
        self, beets_service, temp_album_dir
    ):
        """Test that cover has higher priority than albumart."""
        # Create both files
        albumart_path = os.path.join(temp_album_dir, "albumart.jpg")
        cover_path = os.path.join(temp_album_dir, "cover.jpg")
        Path(albumart_path).touch()
        Path(cover_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        # cover should be returned, not albumart
        assert result == cover_path

    def test_discover_cover_art_extension_priority(
        self, beets_service, temp_album_dir
    ):
        """Test that jpg has higher priority than png for same filename."""
        # Create both files
        png_path = os.path.join(temp_album_dir, "cover.png")
        jpg_path = os.path.join(temp_album_dir, "cover.jpg")
        Path(png_path).touch()
        Path(jpg_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        # jpg should be returned before png
        assert result == jpg_path

    def test_discover_cover_art_finds_albumart(
        self, beets_service, temp_album_dir
    ):
        """Test discovering albumart.jpg when cover.jpg doesn't exist."""
        albumart_path = os.path.join(temp_album_dir, "albumart.jpg")
        Path(albumart_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result == albumart_path

    def test_discover_cover_art_finds_folder(
        self, beets_service, temp_album_dir
    ):
        """Test discovering folder.jpg when higher priority files don't exist."""
        folder_path = os.path.join(temp_album_dir, "folder.jpg")
        Path(folder_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result == folder_path

    def test_discover_cover_art_finds_front(
        self, beets_service, temp_album_dir
    ):
        """Test discovering front.jpg when higher priority files don't exist."""
        front_path = os.path.join(temp_album_dir, "front.jpg")
        Path(front_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result == front_path

    def test_discover_cover_art_finds_webp(
        self, beets_service, temp_album_dir
    ):
        """Test discovering cover.webp format."""
        cover_path = os.path.join(temp_album_dir, "cover.webp")
        Path(cover_path).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result == cover_path

    def test_discover_cover_art_no_matches(
        self, beets_service, temp_album_dir
    ):
        """Test when no cover art files exist."""
        # Album dir is empty
        result = beets_service.discover_cover_art(temp_album_dir)

        assert result is None

    def test_discover_cover_art_nonexistent_dir(self, beets_service):
        """Test with non-existent directory."""
        result = beets_service.discover_cover_art("/nonexistent/directory")

        assert result is None

    def test_discover_cover_art_file_not_dir(
        self, beets_service, temp_album_dir
    ):
        """Test with a file path instead of directory."""
        file_path = os.path.join(temp_album_dir, "somefile.txt")
        Path(file_path).touch()

        result = beets_service.discover_cover_art(file_path)

        assert result is None

    def test_discover_cover_art_ignores_non_matching_files(
        self, beets_service, temp_album_dir
    ):
        """Test that non-matching filenames are ignored."""
        # Create files that don't match pattern
        Path(os.path.join(temp_album_dir, "artwork.jpg")).touch()
        Path(os.path.join(temp_album_dir, "album_cover.jpg")).touch()
        Path(os.path.join(temp_album_dir, "cover.txt")).touch()

        result = beets_service.discover_cover_art(temp_album_dir)

        assert result is None


class TestGetAlbumCoverPathWithFallback:
    """Tests for get_album_cover_path_with_fallback method."""

    def test_returns_artpath_when_exists(self, beets_service, temp_beets_db):
        """Test that artpath is returned when file exists."""
        db_path = temp_beets_db["db_path"]
        album_dir = temp_beets_db["album_dir"]

        # Create the cover file at the artpath location
        cover_path = os.path.join(album_dir, "cover.jpg")
        Path(cover_path).touch()

        result = beets_service.get_album_cover_path_with_fallback(db_path, 2)

        assert result == cover_path

    def test_discovers_cover_when_artpath_null(
        self, beets_service, temp_beets_db
    ):
        """Test fallback discovery when artpath is null."""
        db_path = temp_beets_db["db_path"]
        album_dir = temp_beets_db["album_dir"]

        # Create cover file in album folder
        cover_path = os.path.join(album_dir, "cover.jpg")
        Path(cover_path).touch()

        # Album 1 has null artpath
        result = beets_service.get_album_cover_path_with_fallback(db_path, 1)

        assert result == cover_path

    def test_discovers_cover_when_artpath_missing(
        self, beets_service, temp_beets_db
    ):
        """Test fallback discovery when artpath file doesn't exist."""
        db_path = temp_beets_db["db_path"]
        album_dir = temp_beets_db["album_dir"]

        # Create a different cover file (not at artpath)
        cover_path = os.path.join(album_dir, "folder.jpg")
        Path(cover_path).touch()

        # Album 2 has artpath but file doesn't exist (it was never created)
        result = beets_service.get_album_cover_path_with_fallback(db_path, 2)

        assert result == cover_path

    def test_returns_none_when_no_cover_found(
        self, beets_service, temp_beets_db
    ):
        """Test returns None when no cover art is found."""
        db_path = temp_beets_db["db_path"]

        # Album 1 has null artpath and no cover files
        result = beets_service.get_album_cover_path_with_fallback(db_path, 1)

        assert result is None

    def test_returns_none_for_album_without_items(
        self, beets_service, temp_beets_db
    ):
        """Test returns None for album with no items (can't derive folder)."""
        db_path = temp_beets_db["db_path"]

        # Album 3 has no items
        result = beets_service.get_album_cover_path_with_fallback(db_path, 3)

        assert result is None

    def test_uses_redis_cache_on_hit(self, beets_service, temp_beets_db):
        """Test that Redis cache is used when available."""
        db_path = temp_beets_db["db_path"]

        # Create mock Redis manager
        mock_redis_manager = Mock()
        mock_redis_manager.get_discovered_cover_art.return_value = "/cached/cover.jpg"

        # Mock os.path.exists to return True for cached path
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            result = beets_service.get_album_cover_path_with_fallback(
                db_path, 1, redis_manager=mock_redis_manager
            )

        assert result == "/cached/cover.jpg"
        mock_redis_manager.get_discovered_cover_art.assert_called_once()

    def test_caches_discovered_path(self, beets_service, temp_beets_db):
        """Test that discovered path is cached in Redis."""
        db_path = temp_beets_db["db_path"]
        album_dir = temp_beets_db["album_dir"]

        # Create cover file
        cover_path = os.path.join(album_dir, "cover.jpg")
        Path(cover_path).touch()

        # Create mock Redis manager with cache miss
        mock_redis_manager = Mock()
        mock_redis_manager.get_discovered_cover_art.return_value = None

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis_manager
        )

        assert result == cover_path
        mock_redis_manager.set_discovered_cover_art.assert_called_once_with(
            db_path, 1, cover_path
        )

    def test_caches_negative_result(self, beets_service, temp_beets_db):
        """Test that negative result (no cover found) is cached."""
        db_path = temp_beets_db["db_path"]

        # Create mock Redis manager with cache miss
        mock_redis_manager = Mock()
        mock_redis_manager.get_discovered_cover_art.return_value = None

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis_manager
        )

        assert result is None
        mock_redis_manager.set_discovered_cover_art.assert_called_once_with(
            db_path, 1, ""
        )

    def test_returns_none_for_empty_string_cache(
        self, beets_service, temp_beets_db
    ):
        """Test that empty string cache (negative cache) returns None."""
        db_path = temp_beets_db["db_path"]

        # Create mock Redis manager returning empty string (negative cache)
        mock_redis_manager = Mock()
        mock_redis_manager.get_discovered_cover_art.return_value = ""

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis_manager
        )

        assert result is None

    def test_rediscovers_when_cached_path_missing(
        self, beets_service, temp_beets_db
    ):
        """Test re-discovery when cached path no longer exists."""
        db_path = temp_beets_db["db_path"]
        album_dir = temp_beets_db["album_dir"]

        # Create new cover file
        new_cover_path = os.path.join(album_dir, "cover.jpg")
        Path(new_cover_path).touch()

        # Create mock Redis manager with stale cache
        mock_redis_manager = Mock()
        mock_redis_manager.get_discovered_cover_art.return_value = "/old/missing.jpg"

        result = beets_service.get_album_cover_path_with_fallback(
            db_path, 1, redis_manager=mock_redis_manager
        )

        # Should rediscover and find the new cover
        assert result == new_cover_path
        # Should update cache with new path
        mock_redis_manager.set_discovered_cover_art.assert_called_once_with(
            db_path, 1, new_cover_path
        )


@pytest.fixture
def temp_letters_db():
    """Create a temporary beets database with albums for letter testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "library.db")

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

        conn.commit()
        conn.close()

        yield db_path


class TestGetAlbumLetters:
    """Tests for get_album_letters method."""

    def test_returns_sorted_letters(self, beets_service, temp_letters_db):
        """Test that letters are returned in sorted order A-Z."""
        # Add albums starting with C, A, B
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Coldplay", "Artist"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Abbey Road", "Artist"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Blue Train", "Artist"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A", "B", "C"]

    def test_returns_uppercase_letters(self, beets_service, temp_letters_db):
        """Test that lowercase starting letters are returned as uppercase."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("abbey road", "Artist"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A"]

    def test_groups_numbers_under_hash(self, beets_service, temp_letters_db):
        """Test that albums starting with numbers are grouped under '#'."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("1989", "Taylor Swift"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("21", "Adele"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Abbey Road", "Artist"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A", "#"]

    def test_groups_special_chars_under_hash(self, beets_service, temp_letters_db):
        """Test that albums starting with special characters are grouped under '#'."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("...And Justice for All", "Metallica"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("(What's the Story) Morning Glory?", "Oasis"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["#"]

    def test_hash_appears_last(self, beets_service, temp_letters_db):
        """Test that '#' always appears at the end of the list."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("1989", "Taylor Swift"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Zeppelin", "Artist"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Abbey Road", "Artist"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A", "Z", "#"]
        assert result[-1] == "#"

    def test_empty_library_returns_empty_list(self, beets_service, temp_letters_db):
        """Test that an empty library returns an empty list."""
        result = beets_service.get_album_letters(temp_letters_db)

        assert result == []

    def test_excludes_null_album_titles(self, beets_service, temp_letters_db):
        """Test that albums with null titles are excluded."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            (None, "Artist"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Abbey Road", "Artist"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A"]

    def test_excludes_empty_album_titles(self, beets_service, temp_letters_db):
        """Test that albums with empty string titles are excluded."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("", "Artist"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Abbey Road", "Artist"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A"]

    def test_no_duplicate_letters(self, beets_service, temp_letters_db):
        """Test that each letter appears only once even with multiple albums."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("Abbey Road", "The Beatles"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("A Night at the Opera", "Queen"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("American Idiot", "Green Day"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["A"]

    def test_only_numbered_albums(self, beets_service, temp_letters_db):
        """Test library with only numbered/special character albums."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("1989", "Taylor Swift"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("21", "Adele"),
        )
        cursor.execute(
            "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
            ("25", "Adele"),
        )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        assert result == ["#"]

    def test_db_not_found(self, beets_service):
        """Test with non-existent database."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_album_letters("/nonexistent/db.db")

    def test_all_letters_az(self, beets_service, temp_letters_db):
        """Test with albums covering all letters A-Z."""
        conn = sqlite3.connect(temp_letters_db)
        cursor = conn.cursor()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            cursor.execute(
                "INSERT INTO albums (album, albumartist) VALUES (?, ?)",
                (f"{letter} Album", "Artist"),
            )
        conn.commit()
        conn.close()

        result = beets_service.get_album_letters(temp_letters_db)

        expected = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        assert result == expected


# ============================================================================
# Fixtures for Library Items Tests
# ============================================================================


@pytest.fixture
def temp_library_db():
    """Create a temporary beets database with items for library items testing."""
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

        # Create items table with all necessary columns
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

        # Insert test albums
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, year) VALUES (?, ?, ?, ?)",
            (1, "Abbey Road", "The Beatles", 1969),
        )
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, year) VALUES (?, ?, ?, ?)",
            (2, "Dark Side of the Moon", "Pink Floyd", 1973),
        )
        cursor.execute(
            "INSERT INTO albums (id, album, albumartist, year) VALUES (?, ?, ?, ?)",
            (3, "Empty Album", "Test Artist", None),
        )

        # Insert test items for album 1
        for i in range(1, 4):
            item_path = os.path.join(music_dir, "Beatles", "Abbey Road", f"{i:02d} Track {i}.mp3")
            cursor.execute(
                "INSERT INTO items (id, album_id, path, title, artist, track, disc, genre) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (i, 1, item_path.encode("utf-8"), f"Track {i}", "The Beatles", i, 1, "Rock"),
            )

        # Insert test items for album 2
        for i in range(4, 7):
            track_num = i - 3
            item_path = os.path.join(music_dir, "Pink Floyd", "Dark Side", f"{track_num:02d} Song {track_num}.mp3")
            cursor.execute(
                "INSERT INTO items (id, album_id, path, title, artist, track, disc, genre) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (i, 2, item_path.encode("utf-8"), f"Song {track_num}", "Pink Floyd", track_num, 1, "Progressive Rock"),
            )

        conn.commit()
        conn.close()

        yield {"db_path": db_path, "music_dir": music_dir}


# ============================================================================
# Tests for get_library_items
# ============================================================================


class TestGetLibraryItems:
    """Tests for get_library_items method."""

    def test_get_all_items_without_filter(self, beets_service, temp_library_db):
        """Test getting all library items without album filter."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path)

        assert total == 6
        assert len(items) == 6

    def test_get_items_filtered_by_album_id(self, beets_service, temp_library_db):
        """Test getting items filtered by album ID."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path, album_id=1)

        assert total == 3
        assert len(items) == 3
        for item in items:
            assert item.album_id == 1
            assert item.album == "Abbey Road"

    def test_get_items_pagination_first_page(self, beets_service, temp_library_db):
        """Test pagination - first page."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path, page=1, page_size=2)

        assert total == 6
        assert len(items) == 2

    def test_get_items_pagination_second_page(self, beets_service, temp_library_db):
        """Test pagination - second page."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path, page=2, page_size=2)

        assert total == 6
        assert len(items) == 2

    def test_get_items_pagination_last_page_partial(self, beets_service, temp_library_db):
        """Test pagination - last page with partial results."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path, page=3, page_size=2)

        assert total == 6
        assert len(items) == 2  # Items 5 and 6

    def test_get_items_pagination_beyond_total(self, beets_service, temp_library_db):
        """Test pagination - page beyond total returns empty list."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path, page=10, page_size=2)

        assert total == 6
        assert len(items) == 0

    def test_get_items_empty_album(self, beets_service, temp_library_db):
        """Test getting items from album with no items."""
        db_path = temp_library_db["db_path"]

        items, total = beets_service.get_library_items(db_path, album_id=3)

        assert total == 0
        assert len(items) == 0

    def test_get_items_returns_correct_fields(self, beets_service, temp_library_db):
        """Test that items have all expected fields."""
        db_path = temp_library_db["db_path"]

        items, _ = beets_service.get_library_items(db_path, album_id=1, page_size=1)

        assert len(items) == 1
        item = items[0]
        assert item.id == 1
        assert item.album == "Abbey Road"
        assert item.album_artist == "The Beatles"
        assert item.artist == "The Beatles"
        assert item.title == "Track 1"
        assert item.track_number == 1
        assert item.disc_number == 1
        assert item.genre == "Rock"
        assert item.year == 1969
        assert item.album_id == 1
        assert item.filename.endswith(".mp3")
        assert "Abbey Road" in item.directory

    def test_get_items_db_not_found(self, beets_service):
        """Test error when database file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_library_items("/nonexistent/db.db")


# ============================================================================
# Tests for get_items_by_ids
# ============================================================================


class TestGetItemsByIds:
    """Tests for get_items_by_ids method."""

    def test_get_single_item_by_id(self, beets_service, temp_library_db):
        """Test getting a single item by ID."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [1])

        assert len(items) == 1
        assert items[0].id == 1
        assert items[0].title == "Track 1"

    def test_get_multiple_items_by_ids(self, beets_service, temp_library_db):
        """Test getting multiple items by IDs."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [1, 3, 5])

        assert len(items) == 3
        item_ids = [item.id for item in items]
        assert 1 in item_ids
        assert 3 in item_ids
        assert 5 in item_ids

    def test_get_items_by_ids_preserves_order(self, beets_service, temp_library_db):
        """Test that items are returned in ID order."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [5, 1, 3])

        # Items should be sorted by ID
        assert items[0].id == 1
        assert items[1].id == 3
        assert items[2].id == 5

    def test_get_items_by_ids_nonexistent_ids(self, beets_service, temp_library_db):
        """Test that nonexistent IDs are excluded from results."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [1, 999, 3])

        assert len(items) == 2
        item_ids = [item.id for item in items]
        assert 1 in item_ids
        assert 3 in item_ids
        assert 999 not in item_ids

    def test_get_items_by_ids_all_nonexistent(self, beets_service, temp_library_db):
        """Test with all nonexistent IDs returns empty list."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [997, 998, 999])

        assert len(items) == 0

    def test_get_items_by_ids_empty_list(self, beets_service, temp_library_db):
        """Test with empty list returns empty list."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [])

        assert len(items) == 0

    def test_get_items_by_ids_returns_correct_fields(self, beets_service, temp_library_db):
        """Test that items have all expected fields."""
        db_path = temp_library_db["db_path"]

        items = beets_service.get_items_by_ids(db_path, [4])

        assert len(items) == 1
        item = items[0]
        assert item.id == 4
        assert item.album == "Dark Side of the Moon"
        assert item.album_artist == "Pink Floyd"
        assert item.artist == "Pink Floyd"
        assert item.title == "Song 1"
        assert item.track_number == 1
        assert item.disc_number == 1
        assert item.genre == "Progressive Rock"
        assert item.year == 1973
        assert item.album_id == 2

    def test_get_items_by_ids_db_not_found(self, beets_service):
        """Test error when database file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_items_by_ids("/nonexistent/db.db", [1, 2, 3])


# ============================================================================
# Tests for get_original_album_tags
# ============================================================================


class TestGetOriginalAlbumTags:
    """Tests for get_original_album_tags method."""

    def test_get_album_tags_single_item(self, beets_service, temp_library_db):
        """Test getting original album tag for single item."""
        db_path = temp_library_db["db_path"]

        result = beets_service.get_original_album_tags(db_path, [1])

        assert 1 in result
        assert result[1] == "Abbey Road"

    def test_get_album_tags_multiple_items_same_album(self, beets_service, temp_library_db):
        """Test getting album tags for multiple items from same album."""
        db_path = temp_library_db["db_path"]

        result = beets_service.get_original_album_tags(db_path, [1, 2, 3])

        assert len(result) == 3
        assert result[1] == "Abbey Road"
        assert result[2] == "Abbey Road"
        assert result[3] == "Abbey Road"

    def test_get_album_tags_items_from_different_albums(self, beets_service, temp_library_db):
        """Test getting album tags for items from different albums."""
        db_path = temp_library_db["db_path"]

        result = beets_service.get_original_album_tags(db_path, [1, 4])

        assert len(result) == 2
        assert result[1] == "Abbey Road"
        assert result[4] == "Dark Side of the Moon"

    def test_get_album_tags_nonexistent_ids_excluded(self, beets_service, temp_library_db):
        """Test that nonexistent IDs are not in result."""
        db_path = temp_library_db["db_path"]

        result = beets_service.get_original_album_tags(db_path, [1, 999])

        assert len(result) == 1
        assert 1 in result
        assert 999 not in result

    def test_get_album_tags_empty_list(self, beets_service, temp_library_db):
        """Test with empty list returns empty dict."""
        db_path = temp_library_db["db_path"]

        result = beets_service.get_original_album_tags(db_path, [])

        assert result == {}

    def test_get_album_tags_unique_albums(self, beets_service, temp_library_db):
        """Test that unique albums can be derived from result."""
        db_path = temp_library_db["db_path"]

        result = beets_service.get_original_album_tags(db_path, [1, 2, 4, 5])

        unique_albums = set(result.values())
        assert len(unique_albums) == 2
        assert "Abbey Road" in unique_albums
        assert "Dark Side of the Moon" in unique_albums

    def test_get_album_tags_db_not_found(self, beets_service):
        """Test error when database file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_original_album_tags("/nonexistent/db.db", [1, 2, 3])


# ============================================================================
# Tests for get_library_tree
# ============================================================================


class TestGetLibraryTree:
    """The tree is derived from items.path relative to library_root.

    The fixture's items live under
        {music_dir}/Beatles/Abbey Road/*.mp3     (album_id=1)
        {music_dir}/Pink Floyd/Dark Side/*.mp3   (album_id=2)
    so rooted at music_dir we expect two top-level folders, each with one
    nested album folder.
    """

    def test_builds_nested_tree(self, beets_service, temp_library_db):
        db_path = temp_library_db["db_path"]
        library_root = temp_library_db["music_dir"]

        tree = beets_service.get_library_tree(db_path, library_root)

        assert tree["library_path"] == library_root
        root = tree["root"]
        assert root["name"] == "music"
        assert root["path"] == ""
        assert root["is_album"] is False
        assert set(root["album_ids"]) == {1, 2}

        # Top-level artist folders, alphabetically sorted
        names = [c["name"] for c in root["children"]]
        assert names == ["Beatles", "Pink Floyd"]

        beatles = root["children"][0]
        assert beatles["is_album"] is False  # has subfolder, no tracks directly
        assert beatles["album_ids"] == [1]
        assert len(beatles["children"]) == 1

        abbey = beatles["children"][0]
        assert abbey["name"] == "Abbey Road"
        assert abbey["path"] == os.path.join("Beatles", "Abbey Road")
        assert abbey["is_album"] is True
        assert abbey["album_ids"] == [1]
        assert abbey["children"] == []

    def test_folder_with_tracks_directly_is_album_true(self, beets_service):
        """A folder whose items live directly in it (no nested album folder) is a terminal album."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "library.db")
            music_dir = os.path.join(tmpdir, "music")
            os.makedirs(music_dir)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB, title TEXT)"
            )
            # Flat layout: music/01 track.mp3, music/02 track.mp3
            for i in range(1, 3):
                p = os.path.join(music_dir, f"{i:02d} track.mp3")
                cursor.execute(
                    "INSERT INTO items (id, album_id, path, title) VALUES (?, ?, ?, ?)",
                    (i, 42, p.encode("utf-8"), f"Track {i}"),
                )
            conn.commit()
            conn.close()

            tree = beets_service.get_library_tree(db_path, music_dir)
            root = tree["root"]
            assert root["is_album"] is True
            assert root["album_ids"] == [42]
            assert root["children"] == []

    def test_empty_library_returns_bare_root(self, beets_service):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "library.db")
            music_dir = os.path.join(tmpdir, "music")
            os.makedirs(music_dir)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB, title TEXT)"
            )
            conn.commit()
            conn.close()

            tree = beets_service.get_library_tree(db_path, music_dir)
            assert tree["root"]["album_ids"] == []
            assert tree["root"]["children"] == []
            assert tree["root"]["is_album"] is False

    def test_items_outside_library_root_are_skipped(self, beets_service):
        """Orphaned items whose paths fall outside the library root are ignored.

        Happens in practice when a user moves their `directory:` to a new
        location but hasn't re-imported yet.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "library.db")
            music_dir = os.path.join(tmpdir, "music")
            orphan_dir = os.path.join(tmpdir, "orphans")
            os.makedirs(music_dir)
            os.makedirs(orphan_dir)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB, title TEXT)"
            )
            # Inside the library
            good = os.path.join(music_dir, "Good Album", "01 track.mp3")
            cursor.execute(
                "INSERT INTO items (id, album_id, path, title) VALUES (?, ?, ?, ?)",
                (1, 1, good.encode("utf-8"), "Good"),
            )
            # Outside — should be skipped
            bad = os.path.join(orphan_dir, "Old Library", "01 track.mp3")
            cursor.execute(
                "INSERT INTO items (id, album_id, path, title) VALUES (?, ?, ?, ?)",
                (2, 99, bad.encode("utf-8"), "Stray"),
            )
            conn.commit()
            conn.close()

            tree = beets_service.get_library_tree(db_path, music_dir)
            assert tree["root"]["album_ids"] == [1]
            assert 99 not in tree["root"]["album_ids"]

    def test_deeply_nested_tree(self, beets_service):
        """Disc subfolders beneath an album folder should still collapse to the album."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "library.db")
            music_dir = os.path.join(tmpdir, "music")
            os.makedirs(music_dir)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB, title TEXT)"
            )
            # Artist/Album/Disc 1/01 track.mp3, /Disc 2/02 track.mp3
            paths = [
                os.path.join(music_dir, "Artist", "Album", "Disc 1", "01 track.mp3"),
                os.path.join(music_dir, "Artist", "Album", "Disc 2", "02 track.mp3"),
            ]
            for i, p in enumerate(paths, start=1):
                cursor.execute(
                    "INSERT INTO items (id, album_id, path, title) VALUES (?, ?, ?, ?)",
                    (i, 7, p.encode("utf-8"), f"Track {i}"),
                )
            conn.commit()
            conn.close()

            tree = beets_service.get_library_tree(db_path, music_dir)
            artist = tree["root"]["children"][0]
            album = artist["children"][0]
            assert album["name"] == "Album"
            assert album["is_album"] is False  # no tracks directly
            disc_names = sorted(c["name"] for c in album["children"])
            assert disc_names == ["Disc 1", "Disc 2"]
            for disc in album["children"]:
                assert disc["is_album"] is True
                assert disc["album_ids"] == [7]

    def test_invalid_db_raises(self, beets_service):
        with pytest.raises(FileNotFoundError):
            beets_service.get_library_tree("/nonexistent/db.db", "/music")


# ============================================================================
# Tests for get_library_items with multi-album filter
# ============================================================================


class TestGetLibraryItemsMultiAlbum:
    def test_multi_album_returns_items_from_all(self, beets_service, temp_library_db):
        db_path = temp_library_db["db_path"]
        items, total = beets_service.get_library_items(
            db_path=db_path, album_id=[1, 2], per_page=500
        )
        # Fixture has 3 items for album 1 + 3 for album 2 = 6
        assert total == 6
        album_ids = {i.album_id for i in items}
        assert album_ids == {1, 2}

    def test_multi_album_ordered_by_album_id(self, beets_service, temp_library_db):
        db_path = temp_library_db["db_path"]
        items, _ = beets_service.get_library_items(
            db_path=db_path, album_id=[2, 1], per_page=500
        )
        # Even with reversed input order, results come back sorted by album_id.
        album_id_sequence = [i.album_id for i in items]
        assert album_id_sequence == sorted(album_id_sequence)

    def test_single_id_in_list_behaves_like_scalar(self, beets_service, temp_library_db):
        db_path = temp_library_db["db_path"]
        items_list, total_list = beets_service.get_library_items(
            db_path=db_path, album_id=[1], per_page=500
        )
        items_scalar, total_scalar = beets_service.get_library_items(
            db_path=db_path, album_id=1, per_page=500
        )
        assert total_list == total_scalar
        assert {i.id for i in items_list} == {i.id for i in items_scalar}

    def test_empty_list_returns_all_items(self, beets_service, temp_library_db):
        """An empty list should behave like no filter, matching `album_id=None`."""
        db_path = temp_library_db["db_path"]
        items, total = beets_service.get_library_items(
            db_path=db_path, album_id=[], per_page=500
        )
        assert total == 6  # everything in the fixture


def _make_minimal_db(db_path, album_artpath, item_path):
    """Build a tiny beets DB with one album + one item (bytes-encoded paths)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, "
        "albumartist TEXT, artpath BLOB)"
    )
    conn.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB)"
    )
    conn.execute(
        "INSERT INTO albums (id, album, albumartist, artpath) VALUES (1, 'Album', 'Artist', ?)",
        (album_artpath.encode("utf-8") if album_artpath else None,),
    )
    conn.execute(
        "INSERT INTO items (id, album_id, path) VALUES (1, 1, ?)",
        (item_path.encode("utf-8"),),
    )
    conn.commit()
    conn.close()


def _read_artpath(db_path, album_id=1):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT artpath FROM albums WHERE id = ?", (album_id,)
    ).fetchone()
    conn.close()
    value = row[0]
    return value.decode("utf-8") if isinstance(value, bytes) else value


class TestRelocateCoverAfterMove:
    """Tests for relocate_cover_after_move (issue #105 — covers left behind)."""

    def test_moves_orphaned_cover_to_new_folder(self, beets_service):
        """Cover left in the old folder is carried into the moved album folder."""
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            old_dir = os.path.join(root, "Old Artist", "Album")
            new_dir = os.path.join(root, "New Artist", "Album")
            os.makedirs(old_dir)
            os.makedirs(new_dir)
            # Post-move state: the track already lives in the new folder…
            track = os.path.join(new_dir, "01 - Track.mp3")
            Path(track).touch()
            # …but the cover was left behind in the old folder.
            old_cover = os.path.join(old_dir, "cover.jpg")
            Path(old_cover).write_bytes(b"img")

            db_path = os.path.join(tmp, "library.db")
            _make_minimal_db(db_path, old_cover, track)

            result = beets_service.relocate_cover_after_move(
                db_path, 1, root, old_cover
            )

            new_cover = os.path.join(new_dir, "cover.jpg")
            assert result == new_cover
            assert os.path.exists(new_cover)
            assert not os.path.exists(old_cover)
            assert _read_artpath(db_path) == new_cover

    def test_noop_when_folder_unchanged(self, beets_service):
        """No move happened (cover already beside the tracks) → no-op, None."""
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            album_dir = os.path.join(root, "Artist", "Album")
            os.makedirs(album_dir)
            track = os.path.join(album_dir, "01 - Track.mp3")
            Path(track).touch()
            cover = os.path.join(album_dir, "cover.jpg")
            Path(cover).write_bytes(b"img")

            db_path = os.path.join(tmp, "library.db")
            _make_minimal_db(db_path, cover, track)

            result = beets_service.relocate_cover_after_move(
                db_path, 1, root, cover
            )

            assert result is None
            assert os.path.exists(cover)  # untouched

    def test_uses_existing_cover_when_beets_already_moved_it(self, beets_service):
        """If a cover already reached the new folder, don't double-move; fix artpath."""
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            old_dir = os.path.join(root, "Old Artist", "Album")
            new_dir = os.path.join(root, "New Artist", "Album")
            os.makedirs(old_dir)
            os.makedirs(new_dir)
            track = os.path.join(new_dir, "01 - Track.mp3")
            Path(track).touch()
            # Cover is already present in the new folder (beets moved it).
            new_cover = os.path.join(new_dir, "cover.jpg")
            Path(new_cover).write_bytes(b"new")
            # The pre-move reference points at the (now stale) old location.
            old_cover = os.path.join(old_dir, "cover.jpg")
            Path(old_cover).write_bytes(b"old")

            db_path = os.path.join(tmp, "library.db")
            _make_minimal_db(db_path, old_cover, track)

            result = beets_service.relocate_cover_after_move(
                db_path, 1, root, old_cover
            )

            assert result == new_cover
            assert _read_artpath(db_path) == new_cover
            # The existing new-folder cover is preserved, not overwritten.
            assert Path(new_cover).read_bytes() == b"new"

    def test_returns_none_when_no_pre_move_cover(self, beets_service):
        """Album had no cover to begin with → nothing to relocate."""
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "music", "Artist", "Album")
            os.makedirs(new_dir)
            track = os.path.join(new_dir, "01 - Track.mp3")
            Path(track).touch()
            db_path = os.path.join(tmp, "library.db")
            _make_minimal_db(db_path, None, track)

            result = beets_service.relocate_cover_after_move(
                db_path, 1, tmp, None
            )

            assert result is None


class TestCoverVersion:
    """Tests for the cover_version cache-buster on get_albums."""

    def test_cover_version_is_mtime_when_artpath_exists(self, beets_service):
        with tempfile.TemporaryDirectory() as tmp:
            album_dir = os.path.join(tmp, "music", "Artist", "Album")
            os.makedirs(album_dir)
            cover = os.path.join(album_dir, "cover.jpg")
            Path(cover).write_bytes(b"img")
            track = os.path.join(album_dir, "01 - Track.mp3")
            Path(track).touch()
            db_path = os.path.join(tmp, "library.db")
            _make_minimal_db(db_path, cover, track)

            albums, _ = beets_service.get_albums(db_path)

            assert albums[0].cover_version == int(os.path.getmtime(cover))

    def test_cover_version_none_when_artpath_null(self, beets_service, temp_beets_db):
        albums, _ = beets_service.get_albums(temp_beets_db["db_path"])
        by_id = {a.id: a for a in albums}
        assert by_id[1].cover_version is None  # fixture album 1 has null artpath

    def test_cover_version_resolves_relative_artpath(self, beets_service):
        """Relative artpath (linuxserver/beets) needs library_root to resolve."""
        with tempfile.TemporaryDirectory() as tmp:
            album_dir = os.path.join(tmp, "Artist", "Album")
            os.makedirs(album_dir)
            cover = os.path.join(album_dir, "cover.jpg")
            Path(cover).write_bytes(b"img")
            rel_artpath = os.path.join("Artist", "Album", "cover.jpg")
            db_path = os.path.join(tmp, "library.db")
            _make_minimal_db(db_path, rel_artpath, os.path.join(album_dir, "t.mp3"))

            with_root, _ = beets_service.get_albums(db_path, library_root=tmp)
            assert with_root[0].cover_version == int(os.path.getmtime(cover))

            # Without the root the relative path can't be stat'd → None.
            without_root, _ = beets_service.get_albums(db_path)
            assert without_root[0].cover_version is None
