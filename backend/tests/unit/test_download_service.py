"""Unit tests for the multi-album zip packer (app.services.download_service)."""

import os
import sqlite3
import tempfile
import time
import zipfile

import pytest

from app.services.beets_library_service import BeetsLibraryService
from app.services.download_service import (
    compute_album_size,
    pack_albums_to_zip,
)


def _build_library(tmpdir):
    """A beets DB with two real albums and one album whose file is missing.

    Album 1: The Beatles / Abbey Road — 2 tracks.
    Album 2: Pink Floyd / The Wall — 1 multi-disc track set (2 discs).
    Album 3: Phantom / Ghost — track row present but file missing on disk.
    """
    db_path = os.path.join(tmpdir, "library.db")
    music_dir = os.path.join(tmpdir, "music")
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
    sizes = {}

    def add_album(aid, album, artist):
        cur.execute(
            "INSERT INTO albums (id, album, albumartist, year, added, albumtype) VALUES (?,?,?,?,?,?)",
            (aid, album, artist, 1970, added, "album"),
        )

    def add_track(tid, aid, title, artist, track, disc, folder, payload, on_disk=True):
        os.makedirs(folder, exist_ok=True)
        p = os.path.join(folder, f"{disc}-{track:02d} - {title}.flac")
        if on_disk:
            with open(p, "wb") as f:
                f.write(payload)
            sizes[tid] = len(payload)
        cur.execute(
            """INSERT INTO items (id, album_id, title, artist, track, disc, length, format, channels, path)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (tid, aid, title, artist, track, disc, 100.0, "FLAC", 2, p.encode("utf-8")),
        )

    add_album(1, "Abbey Road", "The Beatles")
    beatles_dir = os.path.join(music_dir, "The Beatles", "Abbey Road")
    add_track(1, 1, "Come Together", "The Beatles", 1, 1, beatles_dir, b"fLaC" + b"\x01" * 3000)
    add_track(2, 1, "Something", "The Beatles", 2, 1, beatles_dir, b"fLaC" + b"\x02" * 4000)

    add_album(2, "The Wall", "Pink Floyd")
    wall_dir = os.path.join(music_dir, "Pink Floyd", "The Wall")
    add_track(3, 2, "In the Flesh", "Pink Floyd", 1, 1, wall_dir, b"fLaC" + b"\x03" * 2500)
    add_track(4, 2, "Hey You", "Pink Floyd", 1, 2, wall_dir, b"fLaC" + b"\x04" * 2600)

    add_album(3, "Ghost", "Phantom")
    ghost_dir = os.path.join(music_dir, "Phantom", "Ghost")
    add_track(10, 3, "Gone", "Phantom", 1, 1, ghost_dir, b"", on_disk=False)

    conn.commit()
    conn.close()
    return db_path, music_dir, sizes


@pytest.fixture
def library():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path, music_dir, sizes = _build_library(tmpdir)
        yield {
            "service": BeetsLibraryService(),
            "db_path": db_path,
            "library_path": music_dir,
            "downloads": os.path.join(tmpdir, "downloads"),
            "sizes": sizes,
        }


class TestPackAlbumsToZip:
    def test_packs_multiple_albums_nested_by_artist_album(self, library):
        dest = os.path.join(library["downloads"], "out.zip")
        size_bytes, packed = pack_albums_to_zip(
            library["service"], library["db_path"], library["library_path"],
            [1, 2], dest,
        )
        assert packed == 2
        assert os.path.exists(dest)
        assert size_bytes == os.path.getsize(dest)

        zf = zipfile.ZipFile(dest)
        assert zf.testzip() is None
        names = set(zf.namelist())
        # Nested <album artist>/<album>/<NN - title>; Wall is multi-disc -> disc prefix.
        assert "The Beatles/Abbey Road/01 - Come Together.flac" in names
        assert "The Beatles/Abbey Road/02 - Something.flac" in names
        assert "Pink Floyd/The Wall/1-01 - In the Flesh.flac" in names
        assert "Pink Floyd/The Wall/2-01 - Hey You.flac" in names
        assert len(names) == 4

    def test_skips_missing_files_but_counts_albums_with_content(self, library):
        dest = os.path.join(library["downloads"], "out.zip")
        size_bytes, packed = pack_albums_to_zip(
            library["service"], library["db_path"], library["library_path"],
            [1, 3], dest,
        )
        # Album 3's only file is missing -> not counted; album 1 still packed.
        assert packed == 1
        names = zipfile.ZipFile(dest).namelist()
        assert all("Ghost" not in n for n in names)
        assert len(names) == 2

    def test_progress_callback_fires_per_album(self, library):
        dest = os.path.join(library["downloads"], "out.zip")
        calls = []
        pack_albums_to_zip(
            library["service"], library["db_path"], library["library_path"],
            [1, 2], dest, progress_cb=lambda p, t, label: calls.append((p, t, label)),
        )
        assert [c[0] for c in calls] == [1, 2]  # processed counts
        assert all(c[1] == 2 for c in calls)    # total stays 2

    def test_raises_when_nothing_downloadable(self, library):
        dest = os.path.join(library["downloads"], "empty.zip")
        with pytest.raises(ValueError):
            pack_albums_to_zip(
                library["service"], library["db_path"], library["library_path"],
                [3], dest,
            )
        # No useless empty archive left behind.
        assert not os.path.exists(dest)


class TestComputeAlbumSize:
    def test_sums_existing_track_sizes(self, library):
        size, count = compute_album_size(
            library["service"], library["db_path"], library["library_path"], 1
        )
        assert count == 2
        assert size == library["sizes"][1] + library["sizes"][2]

    def test_missing_files_count_as_zero(self, library):
        size, count = compute_album_size(
            library["service"], library["db_path"], library["library_path"], 3
        )
        assert size == 0
        assert count == 0


class TestRelativePathSizing:
    """Regression for the '0 B' bug: beets stores paths relative to the library
    root (lscr.io/linuxserver default). Sizing must resolve them, not getsize a
    relative path against the process CWD."""

    def _build_relative_library(self, tmpdir):
        db_path = os.path.join(tmpdir, "library.db")
        music_dir = os.path.join(tmpdir, "music")
        album_dir = os.path.join(music_dir, "Artist", "Album")
        os.makedirs(album_dir)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, albumartist TEXT,
                year INTEGER, genre TEXT, genres TEXT, label TEXT, artpath BLOB,
                added REAL, albumtype TEXT, mb_albumid TEXT)
        """)
        cur.execute("""
            CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, title TEXT,
                artist TEXT, track INTEGER, disc INTEGER, length REAL, format TEXT,
                bitrate INTEGER, samplerate INTEGER, bitdepth INTEGER, channels INTEGER,
                path BLOB, mb_trackid TEXT, genre TEXT, genres TEXT)
        """)
        cur.execute("INSERT INTO albums (id, album, albumartist, added) VALUES (1,'Album','Artist',0)")
        payload = b"fLaC" + b"\x01" * 5000
        with open(os.path.join(album_dir, "01 - Song.flac"), "wb") as f:
            f.write(payload)
        # Path stored RELATIVE to the library root, as linuxserver/beets does.
        cur.execute(
            "INSERT INTO items (id, album_id, title, track, disc, format, path) VALUES (1,1,'Song',1,1,'FLAC',?)",
            (b"Artist/Album/01 - Song.flac",),
        )
        conn.commit()
        conn.close()
        return db_path, music_dir, len(payload)

    def test_sizes_relative_paths_when_root_given(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path, music_dir, payload_size = self._build_relative_library(tmpdir)
            svc = BeetsLibraryService()
            size, count = compute_album_size(svc, db_path, music_dir, 1)
            assert count == 1
            assert size == payload_size

    def test_relative_path_sizes_to_zero_without_root(self):
        # Documents the bug boundary: with no library_root, a relative path
        # can't be found and reports 0 (the old behaviour, now opt-in).
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path, _music_dir, _ = self._build_relative_library(tmpdir)
            svc = BeetsLibraryService()
            size, count = compute_album_size(svc, db_path, None, 1)
            assert size == 0
            assert count == 0
