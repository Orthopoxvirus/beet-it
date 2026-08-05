"""Unit tests for post-import drop-zone cleanup (issue #135).

Covers the acceptance criteria:
- a fully-imported release leaves the drop-zone empty (sidecars gone, empty
  parents pruned), honouring the sidecar extension list;
- a redundant image is deleted only when the album already has a cover, and the
  only-artwork case is promoted/kept rather than dropped;
- empty-parent pruning stops at the drop-zone root and never ascends into the
  library;
- a skipped/failed album (path outside the drop-zone, or a sibling left in the
  same drop-zone) is left fully intact.
"""

import os
from unittest.mock import patch

import pytest

from app.services.import_cleanup import (
    DEFAULT_IMPORT_CLEANUP_CONFIG,
    IMPORT_SIDECAR_EXTENSIONS,
    CleanupResult,
    ImportCleanupConfig,
    cleanup_import_drop_zone,
    prune_empty_drop_zone_folders,
    resolve_import_cleanup_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _touch(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


@pytest.fixture
def zones(tmp_path):
    """A drop-zone root and a library album folder."""
    import_root = tmp_path / "import"
    library = tmp_path / "library"
    album = import_root / "Artist" / "Album"
    dest = library / "Artist" / "Album"
    album.mkdir(parents=True)
    dest.mkdir(parents=True)
    return {
        "import_root": str(import_root),
        "library": str(library),
        "album": str(album),
        "dest": str(dest),
    }


# ---------------------------------------------------------------------------
# 1. Fully-imported release → drop-zone emptied, sidecar list honoured
# ---------------------------------------------------------------------------


class TestFullyImportedRelease:
    def test_sidecars_removed_and_folder_pruned(self, zones):
        # Drop-zone leftovers after a move import (audio already gone).
        for name in ["release.nfo", "00.m3u", "cd.sfv", "info.txt", "list.cue"]:
            _touch(os.path.join(zones["album"], name))
        # Album already has a cover in the library, so the loose image is junk.
        _touch(os.path.join(zones["album"], "cover.jpg"))
        _touch(os.path.join(zones["dest"], "albumart.jpg"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
        )

        assert result.skipped_reason is None
        assert result.changed is True
        # Every sidecar + the redundant image are gone.
        assert len(result.files_removed) == 6
        # The release folder and its now-empty Artist parent are pruned.
        assert not os.path.exists(zones["album"])
        assert not os.path.exists(os.path.dirname(zones["album"]))
        assert os.path.abspath(zones["album"]) in result.folders_pruned
        # Library is untouched.
        assert os.path.exists(os.path.join(zones["dest"], "albumart.jpg"))

    def test_sidecar_extension_list_is_the_constant(self):
        # Guards against silent drift of the documented extension list.
        assert IMPORT_SIDECAR_EXTENSIONS == frozenset(
            {".nfo", ".m3u", ".m3u8", ".sfv", ".srr", ".txt", ".cue", ".log",
             ".url", ".diz"}
        )

    def test_unknown_files_are_left_and_block_pruning(self, zones):
        # A non-sidecar, non-image file must be preserved → folder not pruned.
        _touch(os.path.join(zones["album"], "release.nfo"))
        keep = _touch(os.path.join(zones["album"], "bonus.pdf"))
        _touch(os.path.join(zones["dest"], "albumart.jpg"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
        )

        assert os.path.exists(keep)
        assert os.path.exists(zones["album"])  # not pruned: pdf remains
        assert result.folders_pruned == []
        # The .nfo was still removed.
        assert any(p.endswith("release.nfo") for p in result.files_removed)

    def test_disable_sidecars_keeps_them(self, zones):
        nfo = _touch(os.path.join(zones["album"], "release.nfo"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
            delete_sidecars=False,
        )

        assert os.path.exists(nfo)
        assert result.files_removed == []


# ---------------------------------------------------------------------------
# 2. Image deletion only when redundant; otherwise promote / keep
# ---------------------------------------------------------------------------


class TestImageSafety:
    def test_image_deleted_when_album_has_folder_cover(self, zones):
        img = _touch(os.path.join(zones["album"], "front.jpg"))
        _touch(os.path.join(zones["dest"], "albumart.jpg"))  # cover present

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
        )

        assert not os.path.exists(img)
        assert img in result.files_removed
        assert result.images_promoted == []

    def test_image_deleted_when_audio_has_embedded_art(self, zones):
        img = _touch(os.path.join(zones["album"], "cover.jpg"))
        _touch(os.path.join(zones["dest"], "01.mp3"))  # audio, no folder cover

        with patch(
            "app.services.import_cleanup._file_has_embedded_art",
            return_value=True,
        ):
            result = cleanup_import_drop_zone(
                album_path=zones["album"],
                destination_path=zones["dest"],
                import_root=zones["import_root"],
            )

        assert not os.path.exists(img)
        assert img in result.files_removed

    def test_only_artwork_is_promoted_not_dropped(self, zones):
        # No cover anywhere → the loose image is the only artwork.
        img = _touch(os.path.join(zones["album"], "00-release.jpg"))
        _touch(os.path.join(zones["dest"], "01.mp3"))

        with patch(
            "app.services.import_cleanup._file_has_embedded_art",
            return_value=False,
        ):
            result = cleanup_import_drop_zone(
                album_path=zones["album"],
                destination_path=zones["dest"],
                import_root=zones["import_root"],
            )

        promoted = os.path.join(zones["dest"], "albumart.jpg")
        assert os.path.exists(promoted)          # cover preserved in library
        assert not os.path.exists(img)           # moved out of drop-zone
        assert result.images_promoted == [promoted]
        assert result.images_kept == []
        # Folder is now empty → pruned.
        assert not os.path.exists(zones["album"])

    def test_best_cover_promoted_rest_deleted(self, zones):
        # Multiple loose images, no cover: promote the recognised cover name,
        # the rest become redundant once the album has a cover.
        cover = _touch(os.path.join(zones["album"], "cover.jpg"))
        other = _touch(os.path.join(zones["album"], "back.png"))
        _touch(os.path.join(zones["dest"], "01.mp3"))

        with patch(
            "app.services.import_cleanup._file_has_embedded_art",
            return_value=False,
        ):
            result = cleanup_import_drop_zone(
                album_path=zones["album"],
                destination_path=zones["dest"],
                import_root=zones["import_root"],
            )

        assert os.path.exists(os.path.join(zones["dest"], "albumart.jpg"))
        assert not os.path.exists(cover)
        assert not os.path.exists(other)
        assert len(result.images_promoted) == 1
        assert other in result.files_removed

    def test_image_kept_when_promotion_impossible(self, tmp_path):
        # Destination folder missing → cannot promote → keep the only artwork.
        import_root = tmp_path / "import"
        album = import_root / "Artist" / "Album"
        album.mkdir(parents=True)
        img = _touch(os.path.join(str(album), "folder.jpg"))
        missing_dest = str(tmp_path / "library" / "Artist" / "Album")

        with patch(
            "app.services.import_cleanup._file_has_embedded_art",
            return_value=False,
        ):
            result = cleanup_import_drop_zone(
                album_path=str(album),
                destination_path=missing_dest,
                import_root=str(import_root),
            )

        assert os.path.exists(img)               # artwork preserved in place
        assert img in result.images_kept
        assert result.files_removed == []
        assert os.path.exists(str(album))        # not pruned: image remains


# ---------------------------------------------------------------------------
# 3. Empty-parent pruning stops at the drop-zone root
# ---------------------------------------------------------------------------


class TestPruning:
    def test_walks_up_but_stops_at_import_root(self, tmp_path):
        import_root = tmp_path / "import"
        album = import_root / "Artist" / "Album"
        album.mkdir(parents=True)

        pruned = prune_empty_drop_zone_folders(str(album), str(import_root))

        assert not os.path.exists(str(album))
        assert not os.path.exists(str(import_root / "Artist"))
        assert os.path.exists(str(import_root))          # root never removed
        assert str(import_root) not in pruned

    def test_stops_at_non_empty_parent(self, tmp_path):
        import_root = tmp_path / "import"
        album = import_root / "Artist" / "Album"
        album.mkdir(parents=True)
        # A sibling album keeps the Artist folder non-empty.
        sibling = import_root / "Artist" / "Other"
        sibling.mkdir()
        _touch(os.path.join(str(sibling), "keep.flac"))

        pruned = prune_empty_drop_zone_folders(str(album), str(import_root))

        assert not os.path.exists(str(album))
        assert os.path.exists(str(import_root / "Artist"))  # sibling protects it
        assert os.path.exists(str(sibling))

    def test_no_import_root_is_noop(self, tmp_path):
        album = tmp_path / "Album"
        album.mkdir()
        assert prune_empty_drop_zone_folders(str(album), None) == []
        assert os.path.exists(str(album))


# ---------------------------------------------------------------------------
# 4. Skipped / failed albums and path safety
# ---------------------------------------------------------------------------


class TestSafety:
    def test_path_outside_import_root_is_skipped(self, tmp_path):
        import_root = tmp_path / "import"
        import_root.mkdir()
        outside = tmp_path / "library" / "Artist" / "Album"
        outside.mkdir(parents=True)
        keep = _touch(os.path.join(str(outside), "release.nfo"))

        result = cleanup_import_drop_zone(
            album_path=str(outside),
            destination_path=str(outside),
            import_root=str(import_root),
        )

        assert result.skipped_reason == "album path outside import root"
        assert os.path.exists(keep)              # nothing touched

    def test_import_root_itself_is_never_cleaned(self, tmp_path):
        import_root = tmp_path / "import"
        import_root.mkdir()
        keep = _touch(os.path.join(str(import_root), "release.nfo"))

        result = cleanup_import_drop_zone(
            album_path=str(import_root),
            destination_path=str(import_root),
            import_root=str(import_root),
        )

        assert result.skipped_reason is not None
        assert os.path.exists(keep)

    def test_no_import_root_is_skipped(self, zones):
        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=None,
        )
        assert result.skipped_reason == "no import root configured"

    def test_sibling_album_in_drop_zone_untouched(self, zones):
        # Only the imported album_path is cleaned; a skipped sibling that's
        # still pending in the same drop-zone must be left fully intact.
        sibling = os.path.join(os.path.dirname(zones["album"]), "Skipped")
        os.makedirs(sibling)
        sib_audio = _touch(os.path.join(sibling, "01.flac"))
        sib_nfo = _touch(os.path.join(sibling, "info.nfo"))

        _touch(os.path.join(zones["album"], "release.nfo"))
        _touch(os.path.join(zones["dest"], "albumart.jpg"))

        cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
        )

        # Imported album folder gone, but Artist parent survives because the
        # sibling keeps it non-empty — and the sibling is fully intact.
        assert not os.path.exists(zones["album"])
        assert os.path.exists(sib_audio)
        assert os.path.exists(sib_nfo)
        assert os.path.exists(sibling)


class TestCleanupResult:
    def test_changed_and_affected_paths(self):
        r = CleanupResult(
            files_removed=["/a/x.nfo"],
            folders_pruned=["/a"],
            images_promoted=["/lib/albumart.jpg"],
        )
        assert r.changed is True
        assert set(r.affected_paths) == {"/a/x.nfo", "/a"}

    def test_empty_result_not_changed(self):
        assert CleanupResult().changed is False


# ---------------------------------------------------------------------------
# 5. Configurable sidecar allowlist + image sub-toggles (issue #137)
# ---------------------------------------------------------------------------


class TestConfigurableSidecars:
    def test_custom_extension_list_narrows_deletion(self, zones):
        # Only .nfo is whitelisted → .m3u must survive (and block pruning).
        _touch(os.path.join(zones["album"], "release.nfo"))
        m3u = _touch(os.path.join(zones["album"], "playlist.m3u"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
            sidecar_extensions={".nfo"},
        )

        assert any(p.endswith("release.nfo") for p in result.files_removed)
        assert os.path.exists(m3u)
        assert os.path.exists(zones["album"])  # .m3u remains → not pruned

    def test_extensions_normalized(self, zones):
        # Sloppy entries ("NFO", " .m3u ") still match.
        _touch(os.path.join(zones["album"], "release.nfo"))
        _touch(os.path.join(zones["album"], "playlist.m3u"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
            sidecar_extensions=["NFO", " .m3u "],
        )

        assert len(result.files_removed) == 2

    def test_empty_extension_list_deletes_no_sidecars(self, zones):
        nfo = _touch(os.path.join(zones["album"], "release.nfo"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
            sidecar_extensions=[],
        )

        assert os.path.exists(nfo)
        assert result.files_removed == []


class TestImageSubToggles:
    def test_delete_redundant_images_false_keeps_redundant_image(self, zones):
        # Album has a cover, but image deletion is disabled → keep the image.
        img = _touch(os.path.join(zones["album"], "front.jpg"))
        _touch(os.path.join(zones["dest"], "albumart.jpg"))

        result = cleanup_import_drop_zone(
            album_path=zones["album"],
            destination_path=zones["dest"],
            import_root=zones["import_root"],
            delete_redundant_images=False,
        )

        assert os.path.exists(img)
        assert img in result.images_kept
        assert result.files_removed == []

    def test_promote_orphan_false_keeps_only_artwork_without_promoting(self, zones):
        # No cover + promotion disabled → keep the loose image where it is.
        img = _touch(os.path.join(zones["album"], "cover.jpg"))
        _touch(os.path.join(zones["dest"], "01.mp3"))

        with patch(
            "app.services.import_cleanup._file_has_embedded_art",
            return_value=False,
        ):
            result = cleanup_import_drop_zone(
                album_path=zones["album"],
                destination_path=zones["dest"],
                import_root=zones["import_root"],
                promote_orphan_cover=False,
            )

        assert os.path.exists(img)
        assert img in result.images_kept
        assert result.images_promoted == []
        assert not os.path.exists(os.path.join(zones["dest"], "albumart.jpg"))


class TestConfigResolution:
    def test_defaults_when_no_preferences(self):
        cfg = resolve_import_cleanup_config(None, library_id=1)
        assert cfg.enabled is True
        assert cfg.delete_redundant_images is True
        assert cfg.promote_orphan_cover is True
        assert cfg.sidecar_extensions == IMPORT_SIDECAR_EXTENSIONS
        assert cfg == DEFAULT_IMPORT_CLEANUP_CONFIG or isinstance(
            cfg, ImportCleanupConfig
        )

    def test_global_block_applies_to_all_libraries(self):
        prefs = {"import_cleanup": {"enabled": False}}
        assert resolve_import_cleanup_config(prefs, 1).enabled is False
        assert resolve_import_cleanup_config(prefs, 99).enabled is False

    def test_per_library_override_wins_over_global(self):
        prefs = {
            "import_cleanup": {"enabled": True, "promote_orphan_cover": True},
            "import_cleanup_by_library": {
                "7": {"enabled": False, "promote_orphan_cover": False}
            },
        }
        # Library 7 overridden off; others inherit the global (on).
        lib7 = resolve_import_cleanup_config(prefs, 7)
        assert lib7.enabled is False
        assert lib7.promote_orphan_cover is False

        other = resolve_import_cleanup_config(prefs, 8)
        assert other.enabled is True
        assert other.promote_orphan_cover is True

    def test_partial_override_inherits_unset_keys(self):
        prefs = {
            "import_cleanup": {"delete_redundant_images": False},
            "import_cleanup_by_library": {"3": {"enabled": False}},
        }
        cfg = resolve_import_cleanup_config(prefs, 3)
        assert cfg.enabled is False                     # from per-library
        assert cfg.delete_redundant_images is False     # inherited from global
        assert cfg.promote_orphan_cover is True         # baked-in default

    def test_override_extension_list_is_normalized(self):
        prefs = {
            "import_cleanup_by_library": {
                "5": {"sidecar_extensions": ["NFO", "m3u", " .sfv "]}
            }
        }
        cfg = resolve_import_cleanup_config(prefs, 5)
        assert cfg.sidecar_extensions == frozenset({".nfo", ".m3u", ".sfv"})

    def test_stray_keys_in_blob_are_ignored(self):
        prefs = {
            "import_cleanup": {"enabled": False, "bogus_key": "ignored"},
        }
        cfg = resolve_import_cleanup_config(prefs, 1)
        assert cfg.enabled is False  # resolves without choking on the stray key

    @pytest.mark.parametrize("garbage", ["garbage", ["a", "b"], 7, True])
    def test_non_dict_per_library_container_falls_back(self, garbage):
        # A malformed (non-dict) import_cleanup_by_library value — from a hand
        # edit, a botched migration, or another writer to the shared JSONB —
        # must NOT crash the resolver (it runs in the success path of an
        # import). It falls back to the defaults instead.
        prefs = {"import_cleanup_by_library": garbage}
        cfg = resolve_import_cleanup_config(prefs, 3)
        assert cfg == DEFAULT_IMPORT_CLEANUP_CONFIG

    @pytest.mark.parametrize("garbage", ["garbage", ["a"], 5])
    def test_non_dict_preferences_falls_back(self, garbage):
        cfg = resolve_import_cleanup_config(garbage, 1)
        assert cfg == DEFAULT_IMPORT_CLEANUP_CONFIG

    def test_non_dict_per_library_block_is_ignored(self):
        # The container is a dict, but this library's block is junk.
        prefs = {"import_cleanup_by_library": {"3": "not-a-dict"}}
        cfg = resolve_import_cleanup_config(prefs, 3)
        assert cfg == DEFAULT_IMPORT_CLEANUP_CONFIG

    def test_non_list_sidecar_extensions_keeps_default(self):
        # A bare string must NOT be iterated into single-character extensions;
        # it's rejected and the default allowlist is kept.
        prefs = {"import_cleanup": {"sidecar_extensions": ".nfo"}}
        cfg = resolve_import_cleanup_config(prefs, 1)
        assert cfg.sidecar_extensions == IMPORT_SIDECAR_EXTENSIONS
