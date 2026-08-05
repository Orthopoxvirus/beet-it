"""Integration tests for the cover-art population flow at the service layer.

These exercise the same composition the import/move/backfill paths use —
``ensure_album_cover`` to materialise a discoverable file, then
``update_album_artpath`` — and assert that ``get_albums`` (the grid path) then
returns a usable ``cover_art_path``. This is the behaviour that was broken:
albums with an in-folder cover but a NULL artpath rendered the placeholder in
the grid.
"""

import os
import sqlite3
from pathlib import Path

import pytest

from app.services.beets_library_service import BeetsLibraryService
from app.services.cover_art import ensure_album_cover

JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 16


@pytest.fixture
def beets_service():
    return BeetsLibraryService()


def _build_db(root: str):
    """Create a minimal beets-shaped DB with three albums under *root*.

    1: in-folder ``albumart.jpg``, NULL artpath (the 'grid blank' case).
    2: scene ``00-release.jpg`` only, NULL artpath.
    3: no art at all, NULL artpath.
    """
    db_path = os.path.join(root, "library.db")
    layout = {}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, albumartist TEXT, artpath BLOB)"
    )
    cur.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB)")

    specs = {
        1: "albumart.jpg",
        2: "00-release.jpg",
        3: None,
    }
    for album_id, art_name in specs.items():
        folder = os.path.join(root, "music", f"Artist{album_id}", f"Album{album_id}")
        os.makedirs(folder, exist_ok=True)
        track = os.path.join(folder, "01 - Track.flac")
        Path(track).touch()
        if art_name:
            with open(os.path.join(folder, art_name), "wb") as fh:
                fh.write(JPG)
        cur.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?,?,?,?)",
            (album_id, f"Album{album_id}", f"Artist{album_id}", None),
        )
        cur.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?,?,?)",
            (album_id, album_id, track.encode("utf-8")),
        )
        layout[album_id] = folder
    conn.commit()
    conn.close()
    return db_path, layout


def _backfill(service: BeetsLibraryService, db_path: str, library_root: str):
    """Mirror backfill_cover_art_task's per-album core (no celery/redis/db)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, artpath FROM albums").fetchall()
    conn.close()
    updated = 0
    for row in rows:
        stored = service._resolve_against_root(
            service._decode_artpath(row["artpath"]), library_root
        )
        if stored and os.path.exists(stored):
            continue
        folder = service._resolve_against_root(
            service.get_album_folder_path(db_path, row["id"]), library_root
        )
        if not folder or not os.path.isdir(folder):
            continue
        cover = ensure_album_cover(folder, "albumart")
        if cover:
            service.update_album_artpath(db_path, row["id"], cover)
            updated += 1
    return updated


def test_backfill_populates_artpath_and_grid_shows_covers(beets_service, tmp_path):
    root = str(tmp_path)
    db_path, layout = _build_db(root)
    library_root = os.path.join(root, "music")

    # Before: the grid path returns no cover for the blank albums.
    albums, _ = beets_service.get_albums(db_path, library_root=library_root)
    by_id = {a.id: a for a in albums}
    assert by_id[1].cover_art_path is None
    assert by_id[2].cover_art_path is None

    updated = _backfill(beets_service, db_path, library_root)
    assert updated == 2  # albums 1 and 2; album 3 has no art

    albums, _ = beets_service.get_albums(db_path, library_root=library_root)
    by_id = {a.id: a for a in albums}

    # Album 1: existing albumart.jpg is now the artpath and resolves on disk.
    cover1 = beets_service._resolve_against_root(by_id[1].cover_art_path, library_root)
    assert cover1 == os.path.join(layout[1], "albumart.jpg")
    assert os.path.exists(cover1)

    # Album 2: the scene 00-* file was promoted to albumart.jpg and set.
    cover2 = beets_service._resolve_against_root(by_id[2].cover_art_path, library_root)
    assert cover2 == os.path.join(layout[2], "albumart.jpg")
    assert os.path.exists(cover2)
    assert os.path.exists(os.path.join(layout[2], "00-release.jpg"))  # original kept

    # Album 3: genuinely no art → still degrades to placeholder.
    assert by_id[3].cover_art_path is None


def test_backfill_is_idempotent(beets_service, tmp_path):
    root = str(tmp_path)
    db_path, _ = _build_db(root)
    library_root = os.path.join(root, "music")

    assert _backfill(beets_service, db_path, library_root) == 2
    # Second pass: everything resolvable is skipped.
    assert _backfill(beets_service, db_path, library_root) == 0
