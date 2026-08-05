"""Integration tests for the album ZIP download endpoint.

GET /api/v1/libraries/{slug}/albums/{album_id}/download
"""

import io
import os
import sqlite3
import tempfile
import time
import zipfile
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.database import get_db


@pytest.fixture
def temp_library_db():
    """A temp beets DB with a 3-track album (id 1), an empty album (id 2),
    and an album whose files are missing on disk (id 3)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "library.db")
        music_dir = os.path.join(tmpdir, "music")
        album_dir = os.path.join(music_dir, "The Beatles", "Abbey Road")
        os.makedirs(album_dir)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE albums (
                id INTEGER PRIMARY KEY, album TEXT, albumartist TEXT, year INTEGER,
                genre TEXT, genres TEXT, label TEXT, artpath BLOB, added REAL,
                albumtype TEXT, mb_albumid TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE items (
                id INTEGER PRIMARY KEY, album_id INTEGER, title TEXT, artist TEXT,
                track INTEGER, disc INTEGER, length REAL, format TEXT, bitrate INTEGER,
                samplerate INTEGER, bitdepth INTEGER, channels INTEGER, path BLOB,
                mb_trackid TEXT, genre TEXT, genres TEXT
            )
        """)

        added = time.time()
        cur.execute(
            """INSERT INTO albums (id, album, albumartist, year, added, albumtype)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (1, "Abbey Road", "The Beatles", 1969, added, "album"),
        )
        track_bytes = {}
        for i, title in enumerate(["Come Together", "Something", "Maxwell"], start=1):
            p = os.path.join(album_dir, f"{i:02d} - {title}.flac")
            payload = b"fLaC" + bytes([i]) * 2000
            with open(p, "wb") as f:
                f.write(payload)
            track_bytes[f"{i:02d} - {title}.flac"] = payload
            cur.execute(
                """INSERT INTO items
                   (id, album_id, title, artist, track, disc, length, format, channels, path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (i, 1, title, "The Beatles", i, 1, 100.0, "FLAC", 2, p.encode("utf-8")),
            )

        # Album 2: exists, no tracks.
        cur.execute(
            "INSERT INTO albums (id, album, albumartist, added) VALUES (?, ?, ?, ?)",
            (2, "Empty Album", "Nobody", added),
        )

        # Album 3: has a track row but the file is gone.
        cur.execute(
            "INSERT INTO albums (id, album, albumartist, added) VALUES (?, ?, ?, ?)",
            (3, "Ghost Album", "Phantom", added),
        )
        cur.execute(
            """INSERT INTO items (id, album_id, title, artist, track, disc, format, path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (10, 3, "Gone", "Phantom", 1, 1, "FLAC",
             os.path.join(album_dir, "missing.flac").encode("utf-8")),
        )

        conn.commit()
        conn.close()
        yield {"db_path": db_path, "music_dir": music_dir, "tracks": track_bytes}


@pytest.fixture
def mock_library(temp_library_db):
    lib = Mock()
    lib.id = 1
    lib.slug = "test-library"
    lib.name = "Test Library"
    lib.database_path = temp_library_db["db_path"]
    lib.config_path = None
    lib.library_path = temp_library_db["music_dir"]
    return lib


@pytest.fixture
def mock_db_session(mock_library):
    session = Mock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = mock_library
    return session


@pytest.fixture
def client(mock_db_session):
    def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestAlbumDownload:
    def test_returns_valid_zip_of_all_tracks(self, client, temp_library_db):
        resp = client.get("/api/v1/libraries/test-library/albums/1/download")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert zf.testzip() is None
        assert len(zf.namelist()) == 3
        # Every track's bytes round-trip exactly.
        for name, payload in temp_library_db["tracks"].items():
            assert zf.read(name) == payload

    def test_content_disposition_names_the_album(self, client):
        resp = client.get("/api/v1/libraries/test-library/albums/1/download")
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert "The Beatles - Abbey Road.zip" in cd

    def test_404_for_unknown_album(self, client):
        resp = client.get("/api/v1/libraries/test-library/albums/999/download")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Album not found"

    def test_404_for_album_without_tracks(self, client):
        resp = client.get("/api/v1/libraries/test-library/albums/2/download")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No downloadable tracks found"

    def test_404_when_all_track_files_missing(self, client):
        resp = client.get("/api/v1/libraries/test-library/albums/3/download")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No downloadable tracks found"

    def test_404_for_unknown_library(self, client, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        resp = client.get("/api/v1/libraries/nope/albums/1/download")
        assert resp.status_code == 404
