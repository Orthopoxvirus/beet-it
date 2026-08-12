"""Unit tests for the library maintenance service (issue #147).

Covers missing-cover detection, stray (unimported) cleanup actions with their
safety guards, the tracked-path helpers, and plugin enablement.
"""
import os
import sqlite3
import tempfile
from unittest.mock import Mock

import pytest

from app.services import maintenance_service
from app.services.beets_config_service import BeetsConfigService
from app.services.beets_library_service import BeetsLibraryService


def _make_db(tmpdir, albums, items):
    db_path = os.path.join(tmpdir, "library.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, "
        "albumartist TEXT, artpath BLOB, mb_albumid TEXT)"
    )
    cur.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, album_id INTEGER, path BLOB)"
    )
    for a in albums:
        cur.execute(
            "INSERT INTO albums (id, album, albumartist, artpath) VALUES (?,?,?,?)",
            (a["id"], a.get("album", ""), a.get("albumartist", ""), a.get("artpath")),
        )
    for it in items:
        cur.execute(
            "INSERT INTO items (id, album_id, path) VALUES (?,?,?)",
            (it["id"], it["album_id"], it["path"].encode("utf-8")),
        )
    conn.commit()
    conn.close()
    return db_path


def _touch(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Missing cover art
# ---------------------------------------------------------------------------
def test_list_albums_missing_cover():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music = os.path.join(tmp, "music")
        # album 1: has a real cover file referenced by artpath -> NOT missing
        a1_cover = os.path.join(music, "a1", "cover.jpg")
        _touch(a1_cover)
        _touch(os.path.join(music, "a1", "t.mp3"))
        # album 2: artpath points at a missing file, no discoverable cover -> missing
        _touch(os.path.join(music, "a2", "t.mp3"))
        # album 3: no artpath but a cover.jpg in the folder -> NOT missing (fallback)
        _touch(os.path.join(music, "a3", "cover.jpg"))
        _touch(os.path.join(music, "a3", "t.mp3"))
        # album 4: nothing -> missing
        _touch(os.path.join(music, "a4", "t.mp3"))

        db = _make_db(
            tmp,
            albums=[
                {"id": 1, "album": "A1", "albumartist": "Art", "artpath": a1_cover.encode()},
                {"id": 2, "album": "A2", "albumartist": "Art",
                 "artpath": os.path.join(music, "a2", "cover.jpg").encode()},
                {"id": 3, "album": "A3", "albumartist": "Art", "artpath": None},
                {"id": 4, "album": "A4", "albumartist": "Art", "artpath": None},
            ],
            items=[
                {"id": 1, "album_id": 1, "path": os.path.join(music, "a1", "t.mp3")},
                {"id": 2, "album_id": 2, "path": os.path.join(music, "a2", "t.mp3")},
                {"id": 3, "album_id": 3, "path": os.path.join(music, "a3", "t.mp3")},
                {"id": 4, "album_id": 4, "path": os.path.join(music, "a4", "t.mp3")},
            ],
        )

        missing = maintenance_service.list_albums_missing_cover(svc, db, music)
        missing_ids = sorted(m["album_id"] for m in missing)
        assert missing_ids == [2, 4]
        # Both folders exist on disk — not ghosts.
        assert all(m["folder_missing"] is False for m in missing)


def test_list_albums_missing_cover_flags_ghost_albums():
    """Albums whose folder is gone from disk are flagged as ghosts (#207)."""
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music = os.path.join(tmp, "music")
        # album 1: healthy missing-cover album (folder exists, no cover)
        _touch(os.path.join(music, "a1", "t.mp3"))
        db = _make_db(
            tmp,
            albums=[
                {"id": 1, "album": "Mätzler Bräu Sessions",
                 "albumartist": "Jürgen Groß", "artpath": None},
                # album 2: ghost — item path rooted at "/", file long gone
                # (the botched-import shape from #207)
                {"id": 2, "album": "Geissbock Chärly reist um die Welt",
                 "albumartist": "", "artpath": None},
                # album 3: ghost — relative item path with no matching folder
                # under the library root
                {"id": 3, "album": "Verschwundene Grüße",
                 "albumartist": "Über Art", "artpath": None},
            ],
            items=[
                {"id": 1, "album_id": 1, "path": os.path.join(music, "a1", "t.mp3")},
                {"id": 2, "album_id": 2,
                 "path": "/Geissbock Chärly reist um die Welt/01 -.mp3"},
                {"id": 3, "album_id": 3, "path": "gone/album/01 track.mp3"},
            ],
        )

        missing = maintenance_service.list_albums_missing_cover(svc, db, music)
        by_id = {m["album_id"]: m for m in missing}
        assert sorted(by_id) == [1, 2, 3]
        assert by_id[1]["folder_missing"] is False
        assert by_id[2]["folder_missing"] is True
        assert by_id[3]["folder_missing"] is True


# ---------------------------------------------------------------------------
# Tracked-path helpers
# ---------------------------------------------------------------------------
def test_tracked_item_dirs_and_paths():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music = os.path.join(tmp, "music")
        p = os.path.join(music, "real", "t.mp3")
        _touch(p)
        db = _make_db(
            tmp,
            albums=[{"id": 1, "album": "R", "albumartist": "Art", "artpath": None}],
            items=[{"id": 1, "album_id": 1, "path": p}],
        )
        paths = svc.get_tracked_item_paths(db, music)
        dirs = svc.get_tracked_item_dirs(db, music)
        assert os.path.normpath(p) in paths
        assert os.path.join(music, "real") in dirs


# ---------------------------------------------------------------------------
# Stray cleanup actions
# ---------------------------------------------------------------------------
def _stray_setup(tmp):
    music = os.path.join(tmp, "music")
    imp = os.path.join(tmp, "import")
    os.makedirs(imp, exist_ok=True)
    tracked = os.path.join(music, "real", "t.mp3")
    _touch(tracked)
    stray = os.path.join(music, "stray", "song.mp3")
    _touch(stray)
    db = _make_db(
        tmp,
        albums=[{"id": 1, "album": "R", "albumartist": "Art", "artpath": None}],
        items=[{"id": 1, "album_id": 1, "path": tracked}],
    )
    library = Mock()
    library.database_path = db
    library.library_path = music
    library.import_path = imp
    return music, imp, tracked, stray, library


def test_act_on_strays_delete_and_prune():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music, imp, tracked, stray, library = _stray_setup(tmp)
        results = maintenance_service.act_on_strays(svc, library, [stray], "delete")
        assert results[0]["status"] == "deleted"
        assert not os.path.exists(stray)
        # empty parent folder pruned
        assert not os.path.exists(os.path.join(music, "stray"))


def test_act_on_strays_move_recreates_relative_path():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music, imp, tracked, stray, library = _stray_setup(tmp)
        results = maintenance_service.act_on_strays(
            svc, library, [stray], "move_to_import"
        )
        assert results[0]["status"] == "moved"
        dest = os.path.join(imp, "stray", "song.mp3")
        assert os.path.exists(dest)
        assert not os.path.exists(stray)


def test_act_on_strays_refuses_outside_root():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music, imp, tracked, stray, library = _stray_setup(tmp)
        outside = os.path.join(tmp, "elsewhere.mp3")
        _touch(outside)
        results = maintenance_service.act_on_strays(svc, library, [outside], "delete")
        assert results[0]["status"] == "error"
        assert os.path.exists(outside)  # untouched


def test_act_on_strays_skips_tracked_file():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music, imp, tracked, stray, library = _stray_setup(tmp)
        results = maintenance_service.act_on_strays(svc, library, [tracked], "delete")
        assert results[0]["status"] == "skipped"
        assert os.path.exists(tracked)  # never touched


def test_act_on_strays_tracked_file_via_dir_symlink_is_skipped():
    """A directory symlink must not alias a tracked file past the guard."""
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music, imp, tracked, stray, library = _stray_setup(tmp)
        # <music>/link -> <music>/real ; "link/t.mp3" resolves to the tracked file
        link = os.path.join(music, "link")
        os.symlink(os.path.join(music, "real"), link)
        aliased = os.path.join(link, "t.mp3")
        results = maintenance_service.act_on_strays(svc, library, [aliased], "delete")
        assert results[0]["status"] == "skipped"
        assert os.path.exists(tracked)  # real tracked file untouched


def test_act_on_strays_move_skips_existing_destination():
    svc = BeetsLibraryService()
    with tempfile.TemporaryDirectory() as tmp:
        music, imp, tracked, stray, library = _stray_setup(tmp)
        # Pre-create the destination so the move would otherwise clobber it.
        dest = os.path.join(imp, "stray", "song.mp3")
        _touch(dest, b"existing")
        results = maintenance_service.act_on_strays(
            svc, library, [stray], "move_to_import"
        )
        assert results[0]["status"] == "skipped"
        assert os.path.exists(stray)  # source left in place
        assert open(dest, "rb").read() == b"existing"  # destination untouched


# ---------------------------------------------------------------------------
# Plugin enablement
# ---------------------------------------------------------------------------
def _write_config(tmp, music):
    config_path = os.path.join(tmp, "config.yaml")
    with open(config_path, "w") as f:
        f.write(
            f"directory: {music}\n"
            f"library: {os.path.join(tmp, 'library.db')}\n"
            "plugins:\n"
            "  - fetchart\n"
        )
    return config_path


def test_enable_plugin_adds_unimported():
    cfg_service = BeetsConfigService()
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _write_config(tmp, os.path.join(tmp, "music"))
        assert not maintenance_service.is_plugin_enabled(
            cfg_service, config_path, "unimported"
        )
        plugins = maintenance_service.enable_plugin(
            cfg_service, config_path, "unimported"
        )
        assert "unimported" in plugins
        assert maintenance_service.is_plugin_enabled(
            cfg_service, config_path, "unimported"
        )


def test_enable_plugin_rejects_non_allowlisted():
    cfg_service = BeetsConfigService()
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _write_config(tmp, os.path.join(tmp, "music"))
        with pytest.raises(ValueError):
            maintenance_service.enable_plugin(cfg_service, config_path, "arbitrary")


def test_get_unimported_disabled_returns_flag():
    svc = BeetsLibraryService()
    cfg_service = BeetsConfigService()
    with tempfile.TemporaryDirectory() as tmp:
        music = os.path.join(tmp, "music")
        os.makedirs(music, exist_ok=True)
        config_path = _write_config(tmp, music)
        db = _make_db(tmp, albums=[], items=[])
        library = Mock()
        library.database_path = db
        library.library_path = music
        library.config_path = config_path
        data = maintenance_service.get_unimported(svc, cfg_service, library)
        assert data == {"enabled": False, "groups": [], "total_files": 0}
