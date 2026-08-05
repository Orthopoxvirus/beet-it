"""Integration tests for album detail and track streaming API endpoints."""

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.models.library import Library
from app.services.beets_library_service import BeetsLibraryService


@pytest.fixture
def beets_service():
    """Create a BeetsLibraryService instance."""
    return BeetsLibraryService()


@pytest.fixture
def temp_beets_library_with_tracks():
    """Create a temporary beets library with database, tracks, and cover art."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "library.db")
        album_dir = os.path.join(tmpdir, "music", "Artist", "Album")
        os.makedirs(album_dir)

        # Create the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create beets schema with all columns we need
        cursor.execute("""
            CREATE TABLE albums (
                id INTEGER PRIMARY KEY,
                album TEXT,
                albumartist TEXT,
                year INTEGER,
                genre TEXT,
                genres TEXT,
                label TEXT,
                artpath BLOB,
                added REAL,
                albumtype TEXT,
                mb_albumid TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                album_id INTEGER,
                title TEXT,
                artist TEXT,
                track INTEGER,
                disc INTEGER,
                length REAL,
                format TEXT,
                bitrate INTEGER,
                samplerate INTEGER,
                bitdepth INTEGER,
                channels INTEGER,
                path BLOB,
                mb_trackid TEXT,
                genre TEXT,
                genres TEXT
            )
        """)

        # Create cover art
        cover_path = os.path.join(album_dir, "cover.jpg")
        with open(cover_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF" + b"\x00" * 100)  # JPEG header

        # Insert album with full metadata
        added_time = time.time()
        cursor.execute(
            """INSERT INTO albums
               (id, album, albumartist, year, genre, label, artpath, added, albumtype, mb_albumid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, "Abbey Road", "The Beatles", 1969, "Rock", "Apple Records",
             cover_path.encode("utf-8"), added_time, "album", "b84ee12a-09ef-421b-82de-0441a926375b"),
        )

        # Create track files and insert into database
        track_files = []
        for i, (title, length) in enumerate([
            ("Come Together", 259.0),
            ("Something", 182.0),
            ("Maxwell's Silver Hammer", 207.0),
        ], start=1):
            track_path = os.path.join(album_dir, f"{i:02d} - {title}.flac")
            # Write a small fake audio file
            with open(track_path, "wb") as f:
                f.write(b"fLaC" + b"\x00" * 1000)  # FLAC header + dummy data
            track_files.append(track_path)

            cursor.execute(
                """INSERT INTO items
                   (id, album_id, title, artist, track, disc, length, format, bitrate, samplerate, bitdepth, channels, path, mb_trackid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (i, 1, title, "The Beatles", i, 1, length, "FLAC", 1411, 44100, 16, 2,
                 track_path.encode("utf-8"), f"track-{i}-mb-id"),
            )

        # Album 2: Empty album with no tracks
        cursor.execute(
            """INSERT INTO albums
               (id, album, albumartist, year, genre, label, artpath, added, albumtype, mb_albumid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (2, "Empty Album", "Test Artist", 2020, None, None, None, added_time, None, None),
        )

        conn.commit()
        conn.close()

        yield {
            "db_path": db_path,
            "album_dir": album_dir,
            "cover_path": cover_path,
            "track_files": track_files,
            "library_path": os.path.join(tmpdir, "music"),
        }


class TestGetAlbumById:
    """Tests for get_album_by_id method."""

    def test_get_album_by_id_returns_full_metadata(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting album by ID returns all metadata."""
        db_path = temp_beets_library_with_tracks["db_path"]

        album = beets_service.get_album_by_id(db_path, 1)

        assert album is not None
        assert album.id == 1
        assert album.title == "Abbey Road"
        assert album.artist == "The Beatles"
        assert album.year == 1969
        assert album.genre == "Rock"
        assert album.label == "Apple Records"
        assert album.total_tracks == 3
        assert album.total_duration == 259.0 + 182.0 + 207.0
        assert album.disc_count == 1
        assert album.album_type == "album"
        assert album.mb_albumid == "b84ee12a-09ef-421b-82de-0441a926375b"
        assert album.added is not None

    def test_get_album_by_id_nonexistent(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting nonexistent album returns None."""
        db_path = temp_beets_library_with_tracks["db_path"]

        album = beets_service.get_album_by_id(db_path, 999)

        assert album is None

    def test_get_album_by_id_empty_album(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting album with no tracks."""
        db_path = temp_beets_library_with_tracks["db_path"]

        album = beets_service.get_album_by_id(db_path, 2)

        assert album is not None
        assert album.id == 2
        assert album.title == "Empty Album"
        assert album.total_tracks == 0
        assert album.total_duration == 0

    def test_get_album_by_id_db_not_found(self, beets_service):
        """Test with non-existent database."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_album_by_id("/nonexistent/db.db", 1)

    def test_get_album_by_id_cover_version_is_mtime(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """cover_version is the cover file mtime (cache-buster for the URL)."""
        db_path = temp_beets_library_with_tracks["db_path"]
        cover_path = temp_beets_library_with_tracks["cover_path"]

        album = beets_service.get_album_by_id(db_path, 1)

        assert album.cover_version == int(os.path.getmtime(cover_path))

    def test_get_album_by_id_cover_version_none_without_artpath(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Albums with no artpath have no cover_version."""
        db_path = temp_beets_library_with_tracks["db_path"]

        album = beets_service.get_album_by_id(db_path, 2)

        assert album.cover_version is None


class TestGetAlbumTracks:
    """Tests for get_album_tracks method."""

    def test_get_album_tracks_returns_ordered(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting album tracks returns them in order."""
        db_path = temp_beets_library_with_tracks["db_path"]

        tracks = beets_service.get_album_tracks(db_path, 1)

        assert len(tracks) == 3
        assert tracks[0].track_number == 1
        assert tracks[0].title == "Come Together"
        assert tracks[1].track_number == 2
        assert tracks[1].title == "Something"
        assert tracks[2].track_number == 3
        assert tracks[2].title == "Maxwell's Silver Hammer"

    def test_get_album_tracks_includes_metadata(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test track metadata is complete."""
        db_path = temp_beets_library_with_tracks["db_path"]

        tracks = beets_service.get_album_tracks(db_path, 1)
        track = tracks[0]

        assert track.id == 1
        assert track.artist == "The Beatles"
        assert track.album == "Abbey Road"
        assert track.album_id == 1
        assert track.disc_number == 1
        assert track.duration == 259.0
        assert track.format.lower() == "flac"
        assert track.bitrate == 1411
        assert track.sample_rate == 44100
        assert track.channels == 2
        assert track.file_size > 0  # We wrote actual bytes
        assert track.mb_trackid == "track-1-mb-id"

    def test_get_album_tracks_empty_album(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting tracks for album with no tracks."""
        db_path = temp_beets_library_with_tracks["db_path"]

        tracks = beets_service.get_album_tracks(db_path, 2)

        assert tracks == []

    def test_get_album_tracks_nonexistent_album(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting tracks for nonexistent album."""
        db_path = temp_beets_library_with_tracks["db_path"]

        tracks = beets_service.get_album_tracks(db_path, 999)

        # Should return empty list, not error
        assert tracks == []


class TestGetTrackById:
    """Tests for get_track_by_id method."""

    def test_get_track_by_id_returns_metadata(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting track by ID returns full metadata."""
        db_path = temp_beets_library_with_tracks["db_path"]

        track = beets_service.get_track_by_id(db_path, 1)

        assert track is not None
        assert track.id == 1
        assert track.title == "Come Together"
        assert track.artist == "The Beatles"
        assert track.album == "Abbey Road"
        assert track.album_id == 1
        assert track.track_number == 1
        assert track.disc_number == 1
        assert track.duration == 259.0
        assert track.format.lower() == "flac"
        assert len(track.path) > 0

    def test_get_track_by_id_nonexistent(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test getting nonexistent track returns None."""
        db_path = temp_beets_library_with_tracks["db_path"]

        track = beets_service.get_track_by_id(db_path, 999)

        assert track is None

    def test_get_track_by_id_db_not_found(self, beets_service):
        """Test with non-existent database."""
        with pytest.raises(FileNotFoundError):
            beets_service.get_track_by_id("/nonexistent/db.db", 1)


class TestUpdateAlbumArtpath:
    """Tests for update_album_artpath method."""

    def test_update_album_artpath_success(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test updating album artpath."""
        db_path = temp_beets_library_with_tracks["db_path"]
        new_artpath = "/new/path/cover.jpg"

        result = beets_service.update_album_artpath(db_path, 1, new_artpath)

        assert result is True

        # Verify the update
        album = beets_service.get_album_by_id(db_path, 1)
        assert album.cover_art_path == new_artpath

    def test_update_album_artpath_nonexistent(
        self, beets_service, temp_beets_library_with_tracks
    ):
        """Test updating nonexistent album returns False."""
        db_path = temp_beets_library_with_tracks["db_path"]

        result = beets_service.update_album_artpath(db_path, 999, "/path/cover.jpg")

        assert result is False


class TestRangeHeaderParsing:
    """Tests for HTTP Range header parsing."""

    def test_parse_range_header_simple(self):
        """Test parsing simple byte range."""
        from app.api.libraries import parse_range_header

        result = parse_range_header("bytes=0-1023", 10000)

        assert result == (0, 1023)

    def test_parse_range_header_from_start(self):
        """Test parsing range from start to end."""
        from app.api.libraries import parse_range_header

        result = parse_range_header("bytes=500-", 10000)

        assert result == (500, 9999)

    def test_parse_range_header_suffix(self):
        """Test parsing suffix range (last N bytes)."""
        from app.api.libraries import parse_range_header

        result = parse_range_header("bytes=-500", 10000)

        assert result == (9500, 9999)

    def test_parse_range_header_invalid(self):
        """Test parsing invalid range header."""
        from app.api.libraries import parse_range_header

        assert parse_range_header("invalid", 10000) is None
        assert parse_range_header("bytes=", 10000) is None
        assert parse_range_header("bytes=abc-def", 10000) is None

    def test_parse_range_header_out_of_bounds(self):
        """Test parsing range larger than file size."""
        from app.api.libraries import parse_range_header

        result = parse_range_header("bytes=0-99999", 10000)

        # Should clamp to file size
        assert result == (0, 9999)

    def test_parse_range_header_start_exceeds_size(self):
        """Test parsing range with start > file size."""
        from app.api.libraries import parse_range_header

        result = parse_range_header("bytes=50000-", 10000)

        assert result is None


class TestImageFormatValidation:
    """Tests for image format validation."""

    def test_validate_jpeg(self):
        """Test JPEG validation."""
        from app.api.libraries import validate_image_format

        jpeg_data = b"\xFF\xD8\xFF" + b"\x00" * 100
        result = validate_image_format(jpeg_data)

        assert result == "image/jpeg"

    def test_validate_png(self):
        """Test PNG validation."""
        from app.api.libraries import validate_image_format

        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = validate_image_format(png_data)

        assert result == "image/png"

    def test_validate_gif(self):
        """Test GIF validation."""
        from app.api.libraries import validate_image_format

        gif_data = b"GIF89a" + b"\x00" * 100
        result = validate_image_format(gif_data)

        assert result == "image/gif"

    def test_validate_webp(self):
        """Test WebP validation."""
        from app.api.libraries import validate_image_format

        webp_data = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
        result = validate_image_format(webp_data)

        assert result == "image/webp"

    def test_validate_invalid(self):
        """Test invalid image data."""
        from app.api.libraries import validate_image_format

        invalid_data = b"not an image"
        result = validate_image_format(invalid_data)

        assert result is None


class TestPathValidation:
    """Tests for path traversal prevention."""

    def test_validate_path_in_library_valid(self):
        """Test valid path within library."""
        from app.api.libraries import validate_path_in_library

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            file_path = os.path.join(subdir, "file.mp3")
            Path(file_path).touch()

            result = validate_path_in_library(file_path, tmpdir)

            assert result is True

    def test_validate_path_in_library_traversal(self):
        """Test path traversal attack is blocked."""
        from app.api.libraries import validate_path_in_library

        with tempfile.TemporaryDirectory() as tmpdir:
            library_path = os.path.join(tmpdir, "library")
            os.makedirs(library_path)

            # Try to escape library directory
            evil_path = os.path.join(library_path, "..", "secret.txt")

            result = validate_path_in_library(evil_path, library_path)

            assert result is False

    def test_validate_path_in_library_symlink_escape(self):
        """Test symlink escape is blocked."""
        from app.api.libraries import validate_path_in_library

        with tempfile.TemporaryDirectory() as tmpdir:
            library_path = os.path.join(tmpdir, "library")
            outside_path = os.path.join(tmpdir, "outside")
            os.makedirs(library_path)
            os.makedirs(outside_path)

            secret_file = os.path.join(outside_path, "secret.txt")
            Path(secret_file).touch()

            # Create symlink inside library pointing outside
            symlink_path = os.path.join(library_path, "evil_link")
            os.symlink(secret_file, symlink_path)

            result = validate_path_in_library(symlink_path, library_path)

            assert result is False


class TestSSRFProtection:
    """Tests for SSRF protection."""

    def test_private_ip_blocked_10_range(self):
        """Test 10.x.x.x range is blocked."""
        from app.api.libraries import is_private_ip

        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("10.255.255.255") is True

    def test_private_ip_blocked_172_range(self):
        """Test 172.16.x.x range is blocked."""
        from app.api.libraries import is_private_ip

        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("172.31.255.255") is True

    def test_private_ip_blocked_192_range(self):
        """Test 192.168.x.x range is blocked."""
        from app.api.libraries import is_private_ip

        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("192.168.255.255") is True

    def test_private_ip_blocked_localhost(self):
        """Test localhost is blocked."""
        from app.api.libraries import is_private_ip

        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("127.255.255.255") is True

    def test_private_ip_blocked_link_local(self):
        """Test link-local is blocked."""
        from app.api.libraries import is_private_ip

        assert is_private_ip("169.254.0.1") is True

    def test_public_ip_allowed(self):
        """Test public IPs are allowed."""
        from app.api.libraries import is_private_ip

        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False
        assert is_private_ip("93.184.216.34") is False


class TestIterFile:
    """Tests for file iteration/streaming."""

    def test_iter_file_full(self):
        """Test iterating full file."""
        from app.api.libraries import iter_file

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Hello World!")
            f.flush()
            file_path = f.name

        try:
            chunks = list(iter_file(file_path))
            content = b"".join(chunks)
            assert content == b"Hello World!"
        finally:
            os.unlink(file_path)

    def test_iter_file_range(self):
        """Test iterating file range."""
        from app.api.libraries import iter_file

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Hello World!")
            f.flush()
            file_path = f.name

        try:
            chunks = list(iter_file(file_path, start=0, end=4))
            content = b"".join(chunks)
            assert content == b"Hello"
        finally:
            os.unlink(file_path)

    def test_iter_file_middle_range(self):
        """Test iterating middle section of file."""
        from app.api.libraries import iter_file

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Hello World!")
            f.flush()
            file_path = f.name

        try:
            chunks = list(iter_file(file_path, start=6, end=10))
            content = b"".join(chunks)
            assert content == b"World"
        finally:
            os.unlink(file_path)

    def test_iter_file_chunked(self):
        """Test file is properly chunked."""
        from app.api.libraries import iter_file

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"A" * 5000)
            f.flush()
            file_path = f.name

        try:
            chunks = list(iter_file(file_path, chunk_size=1000))
            assert len(chunks) == 5  # 5000 bytes / 1000 chunk size
            assert all(len(c) == 1000 for c in chunks)
        finally:
            os.unlink(file_path)
