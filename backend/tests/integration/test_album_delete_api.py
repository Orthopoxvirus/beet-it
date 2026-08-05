"""Tests for per-album deletion: the resolve_album_folder safety resolver and
the DELETE /libraries/{slug}/albums/{album_id} endpoint (both disposal modes).
"""

import os
import sqlite3
import tempfile
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.database import get_db
from app.services.beets_library_service import BeetsLibraryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_schema(cursor) -> None:
    cursor.execute(
        """CREATE TABLE albums (
            id INTEGER PRIMARY KEY, album TEXT, albumartist TEXT, artpath BLOB,
            year INTEGER, genre TEXT, genres TEXT, label TEXT, added REAL,
            albumtype TEXT, mb_albumid TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE items (
            id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB, title TEXT,
            artist TEXT, track INTEGER, disc INTEGER, genre TEXT, genres TEXT,
            format TEXT, bitrate INTEGER
        )"""
    )


def _make_db_with_paths(db_path: str, albums, items):
    """albums: list of (id, name). items: list of (id, album_id, stored_path)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    _create_schema(cur)
    for aid, name in albums:
        cur.execute(
            "INSERT INTO albums (id, album, albumartist) VALUES (?, ?, ?)",
            (aid, name, "Artist"),
        )
    for iid, aid, stored in items:
        raw = stored.encode("utf-8") if isinstance(stored, str) else stored
        cur.execute(
            "INSERT INTO items (id, album_id, path, title, track, disc, format, bitrate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (iid, aid, raw, f"Track {iid}", iid, 1, "FLAC", 1000000),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Service: resolve_album_folder
# ---------------------------------------------------------------------------

class TestResolveAlbumFolder:
    def setup_method(self):
        self.service = BeetsLibraryService()

    def test_single_folder_returns_album_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            folder = os.path.join(root, "Artist", "Album")
            db = os.path.join(tmp, "lib.db")
            _make_db_with_paths(
                db,
                [(1, "Album")],
                [
                    (1, 1, os.path.join(folder, "01.flac")),
                    (2, 1, os.path.join(folder, "02.flac")),
                ],
            )
            assert self.service.resolve_album_folder(db, 1, root) == folder

    def test_relative_paths_resolved_against_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            db = os.path.join(tmp, "lib.db")
            _make_db_with_paths(
                db,
                [(1, "Album")],
                [
                    (1, 1, "Artist/Album/01.flac"),
                    (2, 1, "Artist/Album/02.flac"),
                ],
            )
            assert self.service.resolve_album_folder(db, 1, root) == os.path.join(
                root, "Artist", "Album"
            )

    def test_multiple_folders_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            db = os.path.join(tmp, "lib.db")
            _make_db_with_paths(
                db,
                [(1, "Album")],
                [
                    (1, 1, os.path.join(root, "Artist", "A", "01.flac")),
                    (2, 1, os.path.join(root, "Artist", "B", "02.flac")),
                ],
            )
            with pytest.raises(ValueError, match="span multiple folders"):
                self.service.resolve_album_folder(db, 1, root)

    def test_mixed_folder_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            shared = os.path.join(root, "Artist", "Shared")
            db = os.path.join(tmp, "lib.db")
            _make_db_with_paths(
                db,
                [(1, "Album One"), (2, "Album Two")],
                [
                    (1, 1, os.path.join(shared, "01.flac")),
                    (2, 2, os.path.join(shared, "02.flac")),
                ],
            )
            with pytest.raises(ValueError, match="another album|shared folder"):
                self.service.resolve_album_folder(db, 1, root)

    def test_no_tracks_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            db = os.path.join(tmp, "lib.db")
            _make_db_with_paths(db, [(1, "Empty")], [])
            with pytest.raises(ValueError, match="no tracks"):
                self.service.resolve_album_folder(db, 1, root)

    def test_album_at_root_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "music")
            db = os.path.join(tmp, "lib.db")
            _make_db_with_paths(
                db, [(1, "Album")], [(1, 1, os.path.join(root, "01.flac"))]
            )
            with pytest.raises(ValueError, match="not below the library root"):
                self.service.resolve_album_folder(db, 1, root)


# ---------------------------------------------------------------------------
# Route: DELETE /libraries/{slug}/albums/{album_id}
# ---------------------------------------------------------------------------

@pytest.fixture
def delete_fixture():
    """Beets DB + real files with three albums, plus an empty import dir.

      music/The Beatles/Abbey Road/   -> album 1 (2 tracks)
      music/The Beatles/Let It Be/    -> album 2 (2 tracks)
      music/Solo/Only/                -> album 3 (1 track, sole album of "Solo")
      import/                         -> empty staging dir
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "library.db")
        music = os.path.join(tmp, "music")
        import_dir = os.path.join(tmp, "import")
        os.makedirs(import_dir)

        layout = {
            1: ("The Beatles", "Abbey Road", [1, 2]),
            2: ("The Beatles", "Let It Be", [3, 4]),
            3: ("Solo", "Only", [5]),
        }
        albums = []
        items = []
        for aid, (artist, album, track_ids) in layout.items():
            folder = os.path.join(music, artist, album)
            os.makedirs(folder)
            albums.append((aid, album))
            for tid in track_ids:
                p = os.path.join(folder, f"{tid:02d}.flac")
                with open(p, "wb") as fh:
                    fh.write(b"fLaC" + b"\x00" * 64)
                items.append((tid, aid, p))
        _make_db_with_paths(db, albums, items)

        yield {"db": db, "music": music, "import_dir": import_dir}


@pytest.fixture
def mock_library(delete_fixture):
    lib = Mock()
    lib.id = 1
    lib.slug = "test-library"
    lib.database_path = delete_fixture["db"]
    lib.library_path = delete_fixture["music"]
    lib.import_path = delete_fixture["import_dir"]
    return lib


@pytest.fixture
def client(mock_library):
    session = Mock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = mock_library

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestDeleteAlbumEndpoint:
    def test_delete_files_removes_folder_and_db_rows(self, client, delete_fixture):
        folder = os.path.join(delete_fixture["music"], "The Beatles", "Abbey Road")
        assert os.path.isdir(folder)

        resp = client.delete("/api/v1/libraries/test-library/albums/1?mode=delete_files")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["mode"] == "delete_files"
        assert body["files_deleted"] is True
        assert body["relocated_to"] is None
        # Files gone, sibling album untouched (artist folder not pruned).
        assert not os.path.exists(folder)
        assert os.path.isdir(os.path.join(delete_fixture["music"], "The Beatles", "Let It Be"))
        # DB rows gone.
        assert not BeetsLibraryService().album_exists(delete_fixture["db"], 1)

    def test_move_to_import_relocates_and_prunes(self, client, delete_fixture):
        src = os.path.join(delete_fixture["music"], "Solo", "Only")
        assert os.path.isdir(src)

        resp = client.delete("/api/v1/libraries/test-library/albums/3?mode=move_to_import")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "move_to_import"
        assert body["files_deleted"] is False
        dest = os.path.join(delete_fixture["import_dir"], "Solo", "Only")
        assert body["relocated_to"] == dest
        # Moved to import, original gone, emptied artist folder pruned.
        assert os.path.isfile(os.path.join(dest, "05.flac"))
        assert not os.path.exists(src)
        assert not os.path.exists(os.path.join(delete_fixture["music"], "Solo"))
        assert not BeetsLibraryService().album_exists(delete_fixture["db"], 3)

    def test_unknown_album_404(self, client):
        resp = client.delete("/api/v1/libraries/test-library/albums/999?mode=delete_files")
        assert resp.status_code == 404

    def test_move_to_import_conflict_409(self, client, delete_fixture):
        # Pre-create the destination so the move refuses.
        os.makedirs(os.path.join(delete_fixture["import_dir"], "Solo", "Only"))
        resp = client.delete("/api/v1/libraries/test-library/albums/3?mode=move_to_import")
        assert resp.status_code == 409
        # DB row preserved on a pre-flight refusal.
        assert BeetsLibraryService().album_exists(delete_fixture["db"], 3)

    def test_missing_mode_is_422(self, client):
        resp = client.delete("/api/v1/libraries/test-library/albums/1")
        assert resp.status_code == 422


def test_symlink_escape_refused_400():
    """An album folder whose *real* path escapes the library root (reached via
    a symlinked parent) must be refused by the route's realpath guard even
    though its lexical path looks contained — and the outside files survive.
    """
    with tempfile.TemporaryDirectory() as tmp:
        music = os.path.join(tmp, "music")
        os.makedirs(music)
        outside = os.path.join(tmp, "outside")
        real_album = os.path.join(outside, "Album")
        os.makedirs(real_album)
        track = os.path.join(real_album, "01.flac")
        with open(track, "wb") as fh:
            fh.write(b"fLaC" + b"\x00" * 16)
        # music/Artist -> outside, so music/Artist/Album really is outside/Album.
        os.symlink(outside, os.path.join(music, "Artist"))

        db = os.path.join(tmp, "library.db")
        _make_db_with_paths(
            db,
            [(1, "Album")],
            [(1, 1, os.path.join(music, "Artist", "Album", "01.flac"))],
        )

        lib = Mock()
        lib.id = 1
        lib.slug = "test-library"
        lib.database_path = db
        lib.library_path = music
        lib.import_path = os.path.join(tmp, "import")

        session = Mock(spec=Session)
        session.query.return_value.filter.return_value.first.return_value = lib

        def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            resp = client.delete(
                "/api/v1/libraries/test-library/albums/1?mode=delete_files"
            )
            assert resp.status_code == 400
            assert "outside the library root" in resp.json()["detail"]
            # The real files (outside the root) must be untouched.
            assert os.path.isfile(track)
            # DB row preserved — nothing was deleted.
            assert BeetsLibraryService().album_exists(db, 1)
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route: mode=detach (row-only removal) — issue #192
# ---------------------------------------------------------------------------

class TestDetachMode:
    def test_detach_leaves_files_untouched(self, client, delete_fixture):
        """Detach on a normal album removes the rows but never touches disk."""
        folder = os.path.join(delete_fixture["music"], "Solo", "Only")
        assert os.path.isdir(folder)

        resp = client.delete("/api/v1/libraries/test-library/albums/3?mode=detach")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["mode"] == "detach"
        assert body["files_deleted"] is False
        assert body["relocated_to"] is None
        assert os.path.isfile(os.path.join(folder, "05.flac"))
        assert not BeetsLibraryService().album_exists(delete_fixture["db"], 3)

    def test_detach_unknown_album_404(self, client):
        resp = client.delete("/api/v1/libraries/test-library/albums/999?mode=detach")
        assert resp.status_code == 404


@pytest.fixture
def shared_folder_fixture():
    """Two duplicate album rows (1 and 2) whose items live in one folder —
    the pre-#190 duplicate situation issue #192 is about. Album 3 is an
    unrelated control album in its own folder.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "library.db")
        music = os.path.join(tmp, "music")
        import_dir = os.path.join(tmp, "import")
        os.makedirs(import_dir)

        shared = os.path.join(music, "Jürgen Groß", "Die Gefährten")
        os.makedirs(shared)
        control = os.path.join(music, "Jürgen Groß", "Die zwei Türme")
        os.makedirs(control)
        items = []
        for tid, aid, folder in [(1, 1, shared), (2, 2, shared), (3, 3, control)]:
            p = os.path.join(folder, f"{tid:02d}.flac")
            with open(p, "wb") as fh:
                fh.write(b"fLaC" + b"\x00" * 64)
            items.append((tid, aid, p))
        _make_db_with_paths(
            db,
            [(1, "Die Gefährten"), (2, "Die Gefährten"), (3, "Die zwei Türme")],
            items,
        )

        yield {"db": db, "music": music, "import_dir": import_dir, "shared": shared}


@pytest.fixture
def shared_client(shared_folder_fixture):
    lib = Mock()
    lib.id = 1
    lib.slug = "test-library"
    lib.database_path = shared_folder_fixture["db"]
    lib.library_path = shared_folder_fixture["music"]
    lib.import_path = shared_folder_fixture["import_dir"]

    session = Mock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = lib

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestDetachSharedFolder:
    def test_file_modes_refuse_shared_folder_409(self, shared_client, shared_folder_fixture):
        """The issue's dead-end: both file modes 409 on either duplicate row."""
        for album_id in (1, 2):
            for mode in ("delete_files", "move_to_import"):
                resp = shared_client.delete(
                    f"/api/v1/libraries/test-library/albums/{album_id}?mode={mode}"
                )
                assert resp.status_code == 409, (album_id, mode)
                assert "shared folder" in resp.json()["detail"]
        # Nothing was deleted by the refusals.
        service = BeetsLibraryService()
        assert service.album_exists(shared_folder_fixture["db"], 1)
        assert service.album_exists(shared_folder_fixture["db"], 2)

    def test_detach_removes_one_duplicate_row_sibling_and_files_survive(
        self, shared_client, shared_folder_fixture
    ):
        resp = shared_client.delete("/api/v1/libraries/test-library/albums/2?mode=detach")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "detach"
        assert body["files_deleted"] is False
        assert body["relocated_to"] is None
        # Files untouched — both tracks still in the shared folder.
        shared = shared_folder_fixture["shared"]
        assert os.path.isfile(os.path.join(shared, "01.flac"))
        assert os.path.isfile(os.path.join(shared, "02.flac"))
        # Detached row gone, sibling row survives.
        service = BeetsLibraryService()
        assert not service.album_exists(shared_folder_fixture["db"], 2)
        assert service.album_exists(shared_folder_fixture["db"], 1)

    def test_surviving_sibling_deletable_normally_after_detach(
        self, shared_client, shared_folder_fixture
    ):
        """Once the duplicate is detached, the folder is no longer shared and
        the sibling can use the regular file modes again."""
        assert (
            shared_client.delete(
                "/api/v1/libraries/test-library/albums/2?mode=detach"
            ).status_code
            == 200
        )
        resp = shared_client.delete(
            "/api/v1/libraries/test-library/albums/1?mode=delete_files"
        )
        assert resp.status_code == 200
        assert not os.path.exists(shared_folder_fixture["shared"])
        # Control album untouched.
        assert BeetsLibraryService().album_exists(shared_folder_fixture["db"], 3)

    def test_detach_works_when_folder_missing_on_disk(
        self, shared_client, shared_folder_fixture
    ):
        """Detach has no on-disk preconditions — a row whose folder vanished
        can still be cleared."""
        import shutil as _shutil

        _shutil.rmtree(shared_folder_fixture["shared"])
        resp = shared_client.delete("/api/v1/libraries/test-library/albums/2?mode=detach")
        assert resp.status_code == 200
        assert not BeetsLibraryService().album_exists(shared_folder_fixture["db"], 2)
