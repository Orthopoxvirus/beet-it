"""Unit tests for multi-disc-safe import pairing.

A multi-disc release restarts each CD at track 1, often with identical per-disc
track titles (an audio drama with "Teil 1" on every disc). Keying the import's
metadata application by the per-disc track *index* collapses those tracks across
discs and scrambles them. ``pair_candidate_tracks_to_files`` keys on the
matcher's ``local_path`` instead, so each file gets exactly the track beets
paired it with — on the right disc.
"""

from app.tasks.beets_tasks import pair_candidate_tracks_to_files


def _candidate(tracks):
    return {"source": "MusicBrainz", "tracks": tracks}


def test_multidisc_repeating_titles_do_not_collapse():
    """Three discs each starting at "Teil 1" must stay on their own disc."""
    files = [
        "/import/box/1-01 Teil 1.flac",
        "/import/box/1-02 Teil 2.flac",
        "/import/box/2-01 Teil 1.flac",
        "/import/box/2-02 Teil 2.flac",
        "/import/box/3-01 Teil 1.flac",
    ]
    candidate = _candidate(
        [
            {"index": 1, "disc": 1, "title": "Teil 1", "local_path": files[0]},
            {"index": 2, "disc": 1, "title": "Teil 2", "local_path": files[1]},
            {"index": 1, "disc": 2, "title": "Teil 1", "local_path": files[2]},
            {"index": 2, "disc": 2, "title": "Teil 2", "local_path": files[3]},
            {"index": 1, "disc": 3, "title": "Teil 1", "local_path": files[4]},
        ]
    )

    paired = pair_candidate_tracks_to_files(candidate, files)

    # Every file pairs to its own disc's track — no collapsing of the repeated
    # (index, title) pairs across discs.
    assert paired[files[0]]["disc"] == 1 and paired[files[0]]["index"] == 1
    assert paired[files[2]]["disc"] == 2 and paired[files[2]]["index"] == 1
    assert paired[files[3]]["disc"] == 2 and paired[files[3]]["index"] == 2
    assert paired[files[4]]["disc"] == 3 and paired[files[4]]["index"] == 1
    assert len(paired) == 5


def test_basename_fallback_when_directory_differs():
    """Pairs by basename when the candidate path was resolved in a different
    directory than the file being tagged (e.g. canonicalised import path or the
    post-copy destination directory)."""
    candidate = _candidate(
        [
            {"index": 1, "disc": 1, "title": "Teil 1",
             "local_path": "/import/box/1-01 Teil 1.flac"},
        ]
    )
    # Same filename, different directory (as after copy/move to the library).
    dest = ["/library/Artist/Box/1-01 Teil 1.flac"]

    paired = pair_candidate_tracks_to_files(candidate, dest)

    assert paired[dest[0]]["disc"] == 1
    assert paired[dest[0]]["title"] == "Teil 1"


def test_unpaired_file_is_omitted():
    candidate = _candidate(
        [{"index": 1, "title": "Only", "local_path": "/a/known.flac"}]
    )
    paired = pair_candidate_tracks_to_files(candidate, ["/a/unknown.flac"])
    assert paired == {}


def test_no_candidate_returns_empty():
    assert pair_candidate_tracks_to_files(None, ["/a/1.flac"]) == {}


def test_tracks_without_local_path_are_skipped():
    candidate = _candidate([{"index": 1, "title": "No path"}])
    assert pair_candidate_tracks_to_files(candidate, ["/a/1.flac"]) == {}


def test_surplus_candidate_tracks_do_not_disturb_file_pairing():
    """Unequal counts (#175): a provider tracklist longer than the local rip
    (e.g. 636 Deezer chapters vs 500 files) leaves the surplus tracks — those
    the matcher paired to no file, local_path=None — out of the mapping while
    every file still pairs to exactly its own track."""
    files = [f"/import/buch/{i:03d} Kapitel.flac" for i in range(1, 4)]
    candidate = _candidate(
        [
            {"index": 1, "title": "Kapitel 1", "local_path": files[0]},
            {"index": 2, "title": "Kapitel 2", "local_path": None},
            {"index": 3, "title": "Kapitel 3", "local_path": files[1]},
            {"index": 4, "title": "Kapitel 4", "local_path": None},
            {"index": 5, "title": "Kapitel 5", "local_path": files[2]},
        ]
    )

    paired = pair_candidate_tracks_to_files(candidate, files)

    assert len(paired) == 3
    assert paired[files[0]]["index"] == 1
    assert paired[files[1]]["index"] == 3
    assert paired[files[2]]["index"] == 5


# ---------------------------------------------------------------------------
# Destination planning (flat library folder, disc-prefixed filenames)
# ---------------------------------------------------------------------------

from app.tasks.beets_tasks import (  # noqa: E402
    get_audio_files,
    infer_disc_for_file,
    plan_destination_files,
)


def _touch(path):
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb"):
        pass


class TestGetAudioFilesRecursive:
    def test_multi_disc_parent_yields_subfolder_audio(self, tmp_path):
        """A multi-disc parent (audio only in Disc N subfolders) must yield
        its audio — the analysis side walks the tree, so the import side
        finding zero files here broke multi-disc imports outright."""
        album = tmp_path / "Die Grosse Box"
        _touch(str(album / "Disc 1" / "01 - Teil 1.mp3"))
        _touch(str(album / "Disc 2" / "01 - Teil 1.mp3"))
        _touch(str(album / "Disc 2" / "cover.jpg"))

        files = get_audio_files(str(album))

        assert [f.replace(str(album) + "/", "") for f in files] == [
            "Disc 1/01 - Teil 1.mp3",
            "Disc 2/01 - Teil 1.mp3",
        ]

    def test_flat_folder_unchanged(self, tmp_path):
        album = tmp_path / "Album"
        _touch(str(album / "02 - B.flac"))
        _touch(str(album / "01 - A.flac"))
        _touch(str(album / ".hidden" / "x.mp3"))

        files = get_audio_files(str(album))

        assert [f.split("/")[-1] for f in files] == ["01 - A.flac", "02 - B.flac"]


class TestInferDiscForFile:
    def test_paired_track_disc_wins(self):
        assert (
            infer_disc_for_file("/imp/Box/Disc 1/a.mp3", "/imp/Box", {"disc": 3}) == 3
        )

    def test_bare_disc_folder(self):
        assert infer_disc_for_file("/imp/Box/Disc 2/a.mp3", "/imp/Box", None) == 2

    def test_bare_cd_folder(self):
        assert infer_disc_for_file("/imp/Box/CD3/a.mp3", "/imp/Box", None) == 3

    def test_prefixed_disc_folder(self):
        assert (
            infer_disc_for_file("/imp/Box/Die Box CD 12/a.mp3", "/imp/Box", None) == 12
        )

    def test_flat_file_has_no_disc(self):
        assert infer_disc_for_file("/imp/Box/a.mp3", "/imp/Box", None) is None

    def test_non_disc_subfolder_has_no_disc(self):
        assert infer_disc_for_file("/imp/Box/Bonus/a.mp3", "/imp/Box", None) is None


class TestPlanDestinationFiles:
    def test_multi_disc_folders_get_disc_prefix_no_collision(self):
        """Disc 1/01 and Disc 2/01 share a basename; the flat destination must
        keep both (this used to silently overwrite one with the other)."""
        files = [
            "/imp/Box/Disc 1/01 - Teil 1.mp3",
            "/imp/Box/Disc 2/01 - Teil 1.mp3",
        ]
        planned, dest_map = plan_destination_files(files, "/imp/Box", "/lib/A/Box", {})

        assert set(planned) == {
            "/lib/A/Box/1-01 - Teil 1.mp3",
            "/lib/A/Box/2-01 - Teil 1.mp3",
        }
        assert dest_map == {}

    def test_flat_multi_disc_candidate_prefixes_from_pairing(self):
        """A flat local rip matched against a multi-disc provider candidate
        gets its disc from the paired track."""
        files = ["/imp/Box/a.mp3", "/imp/Box/b.mp3"]
        paired = {
            files[0]: {"index": 1, "disc": 1, "title": "Teil 1"},
            files[1]: {"index": 1, "disc": 2, "title": "Teil 1"},
        }
        planned, dest_map = plan_destination_files(files, "/imp/Box", "/lib/A/Box", paired)

        assert set(planned) == {"/lib/A/Box/1-a.mp3", "/lib/A/Box/2-b.mp3"}
        # dest_track_map is keyed by the *renamed* destination so the DB-add
        # step pairs the right track to the right file.
        assert dest_map["/lib/A/Box/1-a.mp3"]["disc"] == 1
        assert dest_map["/lib/A/Box/2-b.mp3"]["disc"] == 2

    def test_single_disc_names_unchanged(self):
        files = ["/imp/Album/01 - A.mp3", "/imp/Album/02 - B.mp3"]
        paired = {files[0]: {"index": 1, "title": "A"}}

        planned, dest_map = plan_destination_files(
            files, "/imp/Album", "/lib/A/Album", paired
        )

        assert set(planned) == {
            "/lib/A/Album/01 - A.mp3",
            "/lib/A/Album/02 - B.mp3",
        }
        assert list(dest_map) == ["/lib/A/Album/01 - A.mp3"]

    def test_residual_collision_raises_instead_of_overwriting(self):
        """Same basename mapping to the same disc must fail loudly, never
        silently drop a track."""
        import pytest

        files = [
            "/imp/Box/Disc 1/01.mp3",
            "/imp/Box/CD 1/01.mp3",
            "/imp/Box/Disc 2/01.mp3",
        ]
        with pytest.raises(ValueError, match="collision"):
            plan_destination_files(files, "/imp/Box", "/lib/A/Box", {})


# ---------------------------------------------------------------------------
# Import validation (recursive audio discovery, issue #180)
# ---------------------------------------------------------------------------

from app.services.beets_import_service import (  # noqa: E402
    BeetsImportError,
    BeetsImportService,
)


class TestValidateAlbumPathRecursive:
    def test_disc_subfolder_audio_validates(self, tmp_path):
        """A folder-per-disc rip (no top-level audio) must pass validation
        instead of failing with NO_AUDIO_FILES."""
        album = tmp_path / "Origin"
        _touch(str(album / "CD 01" / "01 - Kapitel 1.mp3"))
        _touch(str(album / "CD 02" / "01 - Kapitel 2.mp3"))

        service = BeetsImportService()
        result = service.validate_album_path(str(album), str(tmp_path))

        import os

        assert result == os.path.realpath(str(album))

    def test_no_audio_anywhere_rejected(self, tmp_path):
        album = tmp_path / "Scans Only"
        _touch(str(album / "Artwork" / "front.jpg"))

        service = BeetsImportService()
        import pytest

        with pytest.raises(BeetsImportError) as exc:
            service.validate_album_path(str(album), str(tmp_path))
        assert exc.value.code == "NO_AUDIO_FILES"
