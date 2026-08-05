"""Unit tests for BeetsAutotagService."""

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.beets_autotag_service import (
    BeetsAutotagService,
    AnalysisTimeoutError,
    BeetsAnalysisError,
    MusicBrainzError,
    LocalTrackData,
    LocalAlbumData,
    CandidateData,
    CandidateTrackData,
    format_label_for_extension,
    get_beets_autotag_service,
    parse_track_number,
)


@pytest.fixture
def autotag_service():
    """Create a BeetsAutotagService instance."""
    return BeetsAutotagService(timeout=30)


@pytest.fixture
def temp_album_dir():
    """Create a temporary album directory with dummy audio files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        album_dir = os.path.join(tmpdir, "Artist Name", "Album Title")
        os.makedirs(album_dir)

        # Create dummy mp3 files
        for i in range(1, 4):
            filepath = os.path.join(album_dir, f"{i:02d} - Track {i}.mp3")
            with open(filepath, "wb") as f:
                # Write minimal data to create the file
                f.write(b"dummy mp3 content")

        yield album_dir


@pytest.fixture
def temp_import_dir():
    """Create a temporary import directory with album folders."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create multiple album folders
        albums = [
            ("Artist One", "Album A"),
            ("Artist One", "Album B"),
            ("Artist Two", "Album C"),
        ]

        for artist, album in albums:
            album_dir = os.path.join(tmpdir, artist, album)
            os.makedirs(album_dir)

            # Create dummy audio files
            for i in range(1, 3):
                filepath = os.path.join(album_dir, f"{i:02d} - Track {i}.mp3")
                with open(filepath, "wb") as f:
                    f.write(b"dummy mp3 content")

        # Create a non-album folder (no audio files)
        non_album_dir = os.path.join(tmpdir, "Non Album Folder")
        os.makedirs(non_album_dir)
        with open(os.path.join(non_album_dir, "readme.txt"), "w") as f:
            f.write("This is not an album folder")

        yield tmpdir


class TestGetAlbumFolders:
    """Tests for get_album_folders method."""

    def test_get_album_folders_finds_all(self, autotag_service, temp_import_dir):
        """Test that all album folders are found."""
        folders = autotag_service.get_album_folders(temp_import_dir)

        assert len(folders) == 3
        assert any("Album A" in f for f in folders)
        assert any("Album B" in f for f in folders)
        assert any("Album C" in f for f in folders)

    def test_get_album_folders_excludes_non_audio(self, autotag_service, temp_import_dir):
        """Test that folders without audio files are excluded."""
        folders = autotag_service.get_album_folders(temp_import_dir)

        assert not any("Non Album Folder" in f for f in folders)

    def test_get_album_folders_nonexistent(self, autotag_service):
        """Test that FileNotFoundError is raised for nonexistent path."""
        with pytest.raises(FileNotFoundError):
            autotag_service.get_album_folders("/nonexistent/path")

    def test_get_album_folders_sorted(self, autotag_service, temp_import_dir):
        """Test that folders are returned sorted."""
        folders = autotag_service.get_album_folders(temp_import_dir)

        assert folders == sorted(folders)


class TestValidateAlbumPath:
    """Tests for validate_album_path method."""

    def test_validate_relative_path(self, autotag_service, temp_import_dir):
        """Test validation of relative path."""
        result = autotag_service.validate_album_path(
            "Artist One/Album A", temp_import_dir
        )

        assert os.path.isabs(result)
        assert result.startswith(temp_import_dir)

    def test_validate_absolute_path_within(self, autotag_service, temp_import_dir):
        """Test validation of absolute path within import folder."""
        album_path = os.path.join(temp_import_dir, "Artist One", "Album A")
        result = autotag_service.validate_album_path(album_path, temp_import_dir)

        assert result == os.path.realpath(album_path)

    def test_validate_path_traversal_rejected(self, autotag_service, temp_import_dir):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(ValueError, match="within the library's import folder"):
            autotag_service.validate_album_path(
                "../../../etc/passwd", temp_import_dir
            )

    def test_validate_absolute_path_outside_rejected(self, autotag_service, temp_import_dir):
        """Test that absolute paths outside import folder are rejected."""
        with pytest.raises(ValueError, match="within the library's import folder"):
            autotag_service.validate_album_path("/etc/passwd", temp_import_dir)

    def test_validate_symlink_outside_rejected(self, autotag_service, temp_import_dir):
        """Test that symlinks pointing outside are rejected."""
        # Create a symlink pointing outside
        symlink_path = os.path.join(temp_import_dir, "evil_link")
        try:
            os.symlink("/etc", symlink_path)

            with pytest.raises(ValueError, match="within the library's import folder"):
                autotag_service.validate_album_path("evil_link", temp_import_dir)
        finally:
            if os.path.islink(symlink_path):
                os.unlink(symlink_path)


class TestReadLocalAlbum:
    """Tests for _read_local_album method."""

    def test_read_local_album_finds_tracks(self, autotag_service, temp_album_dir):
        """Test that tracks are found in album folder."""
        result = autotag_service._read_local_album(temp_album_dir)

        assert result.path == temp_album_dir
        assert len(result.tracks) == 3

    def test_read_local_album_nonexistent(self, autotag_service):
        """Test that FileNotFoundError is raised for nonexistent path."""
        with pytest.raises(FileNotFoundError):
            autotag_service._read_local_album("/nonexistent/path")

    def test_read_local_album_track_paths(self, autotag_service, temp_album_dir):
        """Test that track paths are absolute."""
        result = autotag_service._read_local_album(temp_album_dir)

        for track in result.tracks:
            assert os.path.isabs(track.path)
            assert track.path.startswith(temp_album_dir)

    def test_read_local_album_descends_into_disc_subfolders(self, autotag_service):
        """A folder-per-disc rip (audio only in CD 01/CD 02) analyzes instead of
        reporting zero tracks, and every track carries its folder-inferred disc
        (regression for #180)."""
        with tempfile.TemporaryDirectory() as album_dir:
            for disc in (1, 2):
                disc_dir = os.path.join(album_dir, f"CD {disc:02d}")
                os.makedirs(disc_dir)
                for i in range(1, 3):
                    with open(os.path.join(disc_dir, f"{i:02d} - Kapitel.mp3"), "wb") as f:
                        f.write(b"dummy")

            result = autotag_service._read_local_album(album_dir)

        assert len(result.tracks) == 4
        assert [t.disc for t in result.tracks] == [1, 1, 2, 2]

    def test_read_local_album_flat_folder_has_no_disc(self, autotag_service, temp_album_dir):
        """Single-folder albums stay disc-less (no behavior change)."""
        result = autotag_service._read_local_album(temp_album_dir)

        assert all(t.disc is None for t in result.tracks)

    def test_read_local_album_dominant_format_uniform(self, autotag_service, temp_album_dir):
        """All-MP3 folder reports MP3 as the dominant format (extension-based)."""
        result = autotag_service._read_local_album(temp_album_dir)

        assert result.dominant_format == "MP3"

    def test_read_local_album_dominant_format_mixed(self, autotag_service):
        """A mixed FLAC/MP3 folder reports the majority format."""
        with tempfile.TemporaryDirectory() as album_dir:
            for i in range(1, 4):
                with open(os.path.join(album_dir, f"{i:02d}.flac"), "wb") as f:
                    f.write(b"dummy")
            with open(os.path.join(album_dir, "04.mp3"), "wb") as f:
                f.write(b"dummy")

            result = autotag_service._read_local_album(album_dir)

        assert result.dominant_format == "FLAC"

    def test_read_local_album_dominant_format_none_when_unreadable(self, autotag_service):
        """A folder with no recognised audio extensions yields no format."""
        with tempfile.TemporaryDirectory() as album_dir:
            with open(os.path.join(album_dir, "cover.jpg"), "wb") as f:
                f.write(b"dummy")

            result = autotag_service._read_local_album(album_dir)

        assert result.dominant_format is None


class TestReadTrackMetadata:
    """Tests for _read_track_metadata method."""

    def test_read_track_metadata_invalid_file(self, autotag_service):
        """Test reading metadata from invalid audio file."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"not a real mp3")
            f.flush()

            try:
                # Returns (LocalTrackData, artist, album) — single-pass read.
                track_data, _artist, _album = autotag_service._read_track_metadata(f.name)

                assert isinstance(track_data, LocalTrackData)
                assert track_data.path == f.name
                # Metadata may be None for invalid file
            finally:
                os.unlink(f.name)

    def test_read_track_metadata_nonexistent(self, autotag_service):
        """Test reading metadata from nonexistent file."""
        track_data, _artist, _album = autotag_service._read_track_metadata("/nonexistent/file.mp3")

        assert isinstance(track_data, LocalTrackData)
        assert track_data.path == "/nonexistent/file.mp3"
        assert track_data.title is None
        assert track_data.track_num is None


class TestFormatLabelForExtension:
    """Tests for the format_label_for_extension helper."""

    @pytest.mark.parametrize(
        "ext,expected",
        [
            (".flac", "FLAC"),
            (".mp3", "MP3"),
            (".MP3", "MP3"),
            (".m4a", "M4A"),
            (".ogg", "OGG"),
            (".txt", None),
            ("", None),
        ],
    )
    def test_format_label(self, ext, expected):
        assert format_label_for_extension(ext) == expected


class TestGetMostCommon:
    """Tests for _get_most_common helper method."""

    def test_get_most_common_single(self, autotag_service):
        """Test with single item."""
        result = autotag_service._get_most_common(["Artist"])
        assert result == "Artist"

    def test_get_most_common_majority(self, autotag_service):
        """Test with majority item."""
        result = autotag_service._get_most_common(["A", "A", "B"])
        assert result == "A"

    def test_get_most_common_empty(self, autotag_service):
        """Test with empty list."""
        result = autotag_service._get_most_common([])
        assert result is None


class TestAnalyzeAlbum:
    """Tests for analyze_album method."""

    def test_analyze_album_nonexistent_path(self, autotag_service):
        """Test that FileNotFoundError is raised for nonexistent path."""
        with pytest.raises(FileNotFoundError):
            autotag_service.analyze_album("test-lib", "/nonexistent/path")

    def test_analyze_album_no_audio_files(self, autotag_service):
        """Test that error is raised when no audio files found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create folder with no audio files
            with open(os.path.join(tmpdir, "readme.txt"), "w") as f:
                f.write("no audio here")

            with pytest.raises(FileNotFoundError, match="No audio files"):
                autotag_service.analyze_album("test-lib", tmpdir)

    @patch('app.services.beets_autotag_service.MutagenFile')
    def test_analyze_album_loads_plugins_with_config(self, mock_mutagen, autotag_service):
        """Test that beets plugins are loaded when config is provided."""
        # beets submodules are imported lazily *inside* analyze_album (to avoid a slow
        # top-level import), so they're not attributes of beets_autotag_service. Patch
        # them on the `beets` package itself so the inline `from beets import ...` sees
        # the mocks.
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "test.mp3")
            with open(audio_file, "wb") as f:
                f.write(b"dummy mp3 content")

            config_file = os.path.join(tmpdir, "config.yaml")
            with open(config_file, "w") as f:
                f.write("plugins: [musicbrainz]\nimport:\n  autotag: yes\n")

            mock_audio = MagicMock()
            mock_audio.info.length = 180.0
            mock_audio.tags = {'artist': ['Test Artist'], 'album': ['Test Album'], 'title': ['Test Track']}
            mock_mutagen.return_value = mock_audio

            # analyze_album imports `beets.autotag`, `beets.plugins` and `beets.config`
            # lazily (inside the function) to keep top-level imports fast. Patching the
            # package attributes works because `from beets import X` resolves X via the
            # package's attribute after first load.
            import beets  # type: ignore
            # Force the submodules to be importable/attached so patch.object can find them.
            from beets import autotag as _, plugins as _p  # noqa: F401

            mock_autotag = MagicMock()
            mock_plugins = MagicMock()
            mock_config = MagicMock()
            mock_config.__getitem__ = MagicMock(
                return_value=MagicMock(get=lambda: ['musicbrainz'], as_str_seq=lambda: ['musicbrainz'])
            )

            mock_proposal = MagicMock()
            mock_proposal.candidates = []
            mock_proposal.recommendation = 0
            mock_autotag.tag_album.return_value = ("Test Artist", "Test Album", mock_proposal)

            with patch.object(beets, 'autotag', mock_autotag), \
                 patch.object(beets, 'plugins', mock_plugins), \
                 patch.object(beets, 'config', mock_config):

                try:
                    autotag_service.analyze_album("test-lib", tmpdir, config_path=config_file)
                except Exception:
                    # Mocked flow may raise later steps; we only assert plugin loading here.
                    pass

                mock_plugins.load_plugins.assert_called_once()


class TestCreateBeetsItems:
    """Tests for _create_beets_items metadata backfill (regression for #60)."""

    def _patched_item_cls(self, artist="", album=""):
        """A fake beets Item whose .from_path returns an item with the given
        (empty by default) embedded tags — simulating tagless files."""
        def from_path(_path):
            return SimpleNamespace(artist=artist, album=album, title="")
        return SimpleNamespace(from_path=from_path)

    def test_backfills_missing_artist_and_album_from_folder(self, autotag_service):
        """Tagless files get artist/album backfilled from the folder consensus
        so beets builds a usable search query (#60)."""
        local_album = LocalAlbumData(
            path="/test",
            artist="The Petersens",
            album="My Ozark Mountain Home",
            tracks=[LocalTrackData(path="/test/01.mp3", title=None, track_num=1, length=None)],
        )

        with patch("beets.library.Item", self._patched_item_cls()):
            items, item_to_local = autotag_service._create_beets_items(local_album)

        assert len(items) == 1
        assert items[0].artist == "The Petersens"
        assert items[0].album == "My Ozark Mountain Home"
        assert item_to_local[id(items[0])] is local_album.tracks[0]

    def test_does_not_overwrite_present_tags(self, autotag_service):
        """Embedded tags win; folder consensus only fills genuinely empty fields."""
        local_album = LocalAlbumData(
            path="/test", artist="Folder Artist", album="Folder Album",
            tracks=[LocalTrackData(path="/test/01.mp3", title=None, track_num=1, length=None)],
        )

        with patch("beets.library.Item", self._patched_item_cls(artist="Tag Artist", album="Tag Album")):
            items, _ = autotag_service._create_beets_items(local_album)

        assert items[0].artist == "Tag Artist"
        assert items[0].album == "Tag Album"

    def test_noop_when_both_empty(self, autotag_service):
        """No folder consensus and no tags → fields stay empty, no crash."""
        local_album = LocalAlbumData(
            path="/test", artist=None, album=None,
            tracks=[LocalTrackData(path="/test/01.mp3", title=None, track_num=1, length=None)],
        )

        with patch("beets.library.Item", self._patched_item_cls()):
            items, _ = autotag_service._create_beets_items(local_album)

        assert items[0].artist == ""
        assert items[0].album == ""

    def test_backfills_missing_title_from_filename_hint(self, autotag_service):
        """A filename-derived track title (set by _read_local_album for untagged
        rips) is pushed onto the beets Item so it can score tracks (#138)."""
        local_album = LocalAlbumData(
            path="/test", artist="A", album="B",
            tracks=[LocalTrackData(
                path="/test/01.flac", title="teil 1", track_num=1, length=None
            )],
        )

        with patch("beets.library.Item", self._patched_item_cls()):
            items, _ = autotag_service._create_beets_items(local_album)

        assert items[0].title == "teil 1"

    def test_backfills_disc_and_disctotal_for_multi_disc(self, autotag_service):
        """Folder-inferred discs land on the beets Items (with disctotal) so a
        folder-per-disc rip scores as one multi-disc album (#180)."""
        local_album = LocalAlbumData(
            path="/test", artist="A", album="B",
            tracks=[
                LocalTrackData(path="/test/CD 01/01.mp3", title=None, track_num=1, length=None, disc=1),
                LocalTrackData(path="/test/CD 02/01.mp3", title=None, track_num=1, length=None, disc=2),
            ],
        )

        with patch("beets.library.Item", self._patched_item_cls()):
            items, _ = autotag_service._create_beets_items(local_album)

        assert [i.disc for i in items] == [1, 2]
        assert [i.disctotal for i in items] == [2, 2]

    def test_single_disc_items_untouched(self, autotag_service):
        """Disc-less tracks leave the beets Items' disc fields alone."""
        local_album = LocalAlbumData(
            path="/test", artist="A", album="B",
            tracks=[LocalTrackData(path="/test/01.mp3", title=None, track_num=1, length=None)],
        )

        with patch("beets.library.Item", self._patched_item_cls()):
            items, _ = autotag_service._create_beets_items(local_album)

        assert not hasattr(items[0], "disc") or not items[0].disc
        assert not hasattr(items[0], "disctotal") or not items[0].disctotal


class TestComputeAlbumChanges:
    """Tests for _compute_album_changes method."""

    def test_compute_album_changes_artist(self, autotag_service):
        """Test computing artist changes."""
        local_album = LocalAlbumData(
            path="/test", artist="Old Artist", album="Album", tracks=[]
        )

        candidate_info = Mock()
        candidate_info.artist = "New Artist"
        candidate_info.album = "Album"
        candidate_info.year = None

        changes = autotag_service._compute_album_changes(local_album, candidate_info)

        assert len(changes) == 1
        assert changes[0]["field"] == "artist"
        assert changes[0]["from_value"] == "Old Artist"
        assert changes[0]["to_value"] == "New Artist"

    def test_compute_album_changes_album(self, autotag_service):
        """Test computing album name changes."""
        local_album = LocalAlbumData(
            path="/test", artist="Artist", album="Old Album", tracks=[]
        )

        candidate_info = Mock()
        candidate_info.artist = "Artist"
        candidate_info.album = "New Album"
        candidate_info.year = None

        changes = autotag_service._compute_album_changes(local_album, candidate_info)

        assert len(changes) == 1
        assert changes[0]["field"] == "album"
        assert changes[0]["from_value"] == "Old Album"
        assert changes[0]["to_value"] == "New Album"

    def test_compute_album_changes_year(self, autotag_service):
        """Test computing year changes."""
        local_album = LocalAlbumData(
            path="/test", artist="Artist", album="Album", tracks=[]
        )

        candidate_info = Mock()
        candidate_info.artist = "Artist"
        candidate_info.album = "Album"
        candidate_info.year = 2020

        changes = autotag_service._compute_album_changes(local_album, candidate_info)

        year_changes = [c for c in changes if c["field"] == "year"]
        assert len(year_changes) == 1
        assert year_changes[0]["to_value"] == "2020"

    def test_compute_album_changes_no_changes(self, autotag_service):
        """Test when there are no changes."""
        local_album = LocalAlbumData(
            path="/test", artist="Artist", album="Album", tracks=[]
        )

        candidate_info = Mock()
        candidate_info.artist = "Artist"
        candidate_info.album = "Album"
        candidate_info.year = None

        changes = autotag_service._compute_album_changes(local_album, candidate_info)

        assert len(changes) == 0


class TestServiceSingleton:
    """Tests for service singleton pattern."""

    def test_get_beets_autotag_service_returns_instance(self):
        """Test that get_beets_autotag_service returns an instance."""
        service = get_beets_autotag_service()
        assert isinstance(service, BeetsAutotagService)

    def test_get_beets_autotag_service_returns_same_instance(self):
        """Test that get_beets_autotag_service returns same instance."""
        service1 = get_beets_autotag_service()
        service2 = get_beets_autotag_service()
        assert service1 is service2


class TestExceptions:
    """Tests for custom exceptions."""

    def test_analysis_timeout_error(self):
        """Test AnalysisTimeoutError can be raised."""
        with pytest.raises(AnalysisTimeoutError):
            raise AnalysisTimeoutError("Timed out")

    def test_beets_analysis_error(self):
        """Test BeetsAnalysisError can be raised."""
        with pytest.raises(BeetsAnalysisError):
            raise BeetsAnalysisError("Analysis failed")

    def test_musicbrainz_error(self):
        """Test MusicBrainzError can be raised."""
        with pytest.raises(MusicBrainzError):
            raise MusicBrainzError("MusicBrainz error")


class TestParseTrackNumber:
    """Tests for the tolerant track-number parser."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1", 1),
            ("01", 1),
            ("12", 12),
            ("1/12", 1),       # track/total
            (" 3 ", 3),         # surrounding whitespace
            ("A1", 1),          # vinyl-style side prefix
            ("1;1", 1),         # corrupted multi-valued tag — used to crash int()
            ("", None),
            ("   ", None),
            ("none", None),
            (None, None),
        ],
    )
    def test_parse_track_number(self, raw, expected):
        assert parse_track_number(raw) == expected


class TestComputeTrackData:
    """Tests for _compute_track_data local↔candidate pairing."""

    def _track_info(self, index, title, length=180.0, medium=1, medium_index=None):
        ti = Mock()
        ti.index = index
        ti.title = title
        ti.length = length
        # Real beets TrackInfo always carries medium/medium_index; model that so
        # getattr() doesn't return a truthy auto-Mock and mis-trigger the
        # multi-disc path.
        ti.medium = medium
        ti.medium_index = medium_index if medium_index is not None else index
        return ti

    def test_mapping_pairs_local_title_and_path(self, autotag_service, tmp_path):
        """A matched track carries the local title AND path (so the UI can
        show a real before/after comparison instead of '(new)')."""
        track_path = str(tmp_path / "01.flac")
        local_album = LocalAlbumData(
            path=str(tmp_path),
            artist="Ezra George",
            album="Photobook",
            tracks=[LocalTrackData(path=track_path, title="Stay", track_num=1, length=180.0)],
        )

        item = Mock()
        item.path = os.fsencode(track_path)
        item.title = "Stay"

        match = Mock()
        match.mapping = {item: self._track_info(1, "Stay")}

        tracks, track_changes = autotag_service._compute_track_data(match, local_album)

        assert len(tracks) == 1
        assert tracks[0].local_title == "Stay"
        assert tracks[0].local_path == track_path
        # A comparison row is emitted for every matched track (even unchanged
        # titles) so the UI can show durations and the filename.
        assert track_changes == [
            {
                "index": 1,
                "disc": None,
                "local_title": "Stay",
                "candidate_title": "Stay",
                "local_length": 180.0,
                "candidate_length": 180.0,
                "local_path": track_path,
            }
        ]

    def test_fallback_pairs_by_track_number(self, autotag_service):
        """Without a beets mapping, pair candidate tracks to local by number."""
        local_album = LocalAlbumData(
            path="/album",
            artist="A",
            album="B",
            tracks=[LocalTrackData(path="/album/2.flac", title="Old", track_num=2, length=200.0)],
        )

        match = Mock()
        match.mapping = None
        info = Mock()
        info.tracks = [self._track_info(2, "New")]
        match.info = info

        tracks, track_changes = autotag_service._compute_track_data(match, local_album)

        assert len(tracks) == 1
        assert tracks[0].local_title == "Old"
        assert tracks[0].local_path == "/album/2.flac"
        # Row carries both durations and the local path alongside the rename.
        assert track_changes == [
            {
                "index": 2,
                "disc": None,
                "local_title": "Old",
                "candidate_title": "New",
                "local_length": 200.0,
                "candidate_length": 180.0,
                "local_path": "/album/2.flac",
            }
        ]

    def test_multidisc_mapping_uses_per_disc_number_and_disc(
        self, autotag_service, tmp_path
    ):
        """A multi-disc match keeps per-disc track numbers and stamps the disc,
        so disc 2 track 1 is (disc=2, index=1) — not the absolute index 2 with
        no disc, which would collapse onto disc 1 track 1 at import time."""
        d1 = str(tmp_path / "1-01.flac")
        d2 = str(tmp_path / "2-01.flac")
        local_album = LocalAlbumData(
            path=str(tmp_path),
            artist="A",
            album="Box",
            tracks=[
                LocalTrackData(path=d1, title="Teil 1", track_num=1, length=180.0),
                LocalTrackData(path=d2, title="Teil 1", track_num=1, length=200.0),
            ],
        )

        item1 = Mock(); item1.path = os.fsencode(d1); item1.title = "Teil 1"
        item2 = Mock(); item2.path = os.fsencode(d2); item2.title = "Teil 1"

        match = Mock()
        match.mapping = {
            item1: self._track_info(1, "Teil 1", length=180.0, medium=1, medium_index=1),
            item2: self._track_info(2, "Teil 1", length=200.0, medium=2, medium_index=1),
        }

        tracks, track_changes = autotag_service._compute_track_data(match, local_album)

        by_path = {t.local_path: t for t in tracks}
        assert by_path[d1].disc == 1 and by_path[d1].index == 1
        assert by_path[d2].disc == 2 and by_path[d2].index == 1
        # Sorted disc-1-first, not interleaved by the repeating per-disc index.
        assert [(t.disc, t.index) for t in tracks] == [(1, 1), (2, 1)]
        assert [(c["disc"], c["index"]) for c in track_changes] == [(1, 1), (2, 1)]

    def test_mapping_unresolved_path_keeps_title_drops_path(self, autotag_service, tmp_path):
        """If a beets item's path doesn't resolve to a known local file, the
        beets-read title is still surfaced but local_path stays None (never an
        empty string, which would corrupt local-only reconciliation)."""
        local_album = LocalAlbumData(
            path=str(tmp_path),
            artist="A",
            album="B",
            tracks=[LocalTrackData(path=str(tmp_path / "01.flac"), title="Stay", track_num=1, length=180.0)],
        )

        item = Mock()
        item.path = os.fsencode("/somewhere/else/unknown.flac")  # not in local_by_path
        item.title = "Stay (beets-read)"

        match = Mock()
        match.mapping = {item: self._track_info(1, "Stay")}

        tracks, _ = autotag_service._compute_track_data(match, local_album)

        assert tracks[0].local_title == "Stay (beets-read)"
        assert tracks[0].local_path is None

    def test_mapping_pairs_by_item_identity_when_path_diverges(
        self, autotag_service, tmp_path
    ):
        """The item->local pairing must survive even when the beets item's path
        string doesn't match our normalized local path (symlink / abspath vs.
        realpath / encoding divergence). Identity resolution via item_to_local
        keeps local_path set, so a tag-less track isn't wrongly reported as
        '(new)' — the root cause of the 2xN-unmatched bug."""
        track_path = str(tmp_path / "01-untagged.flac")
        local_track = LocalTrackData(
            path=track_path, title=None, track_num=None, length=150.0
        )
        local_album = LocalAlbumData(
            path=str(tmp_path), artist="A", album="B", tracks=[local_track]
        )

        item = Mock()
        # A path that will NOT resolve via local_by_path string matching.
        item.path = os.fsencode("/different/mount/01-untagged.flac")
        item.title = ""  # tag-less file: no title to fall back on

        match = Mock()
        match.mapping = {item: self._track_info(1, "Teil 01", length=150.0)}

        tracks, _ = autotag_service._compute_track_data(
            match, local_album, item_to_local={id(item): local_track}
        )

        assert len(tracks) == 1
        assert tracks[0].local_path == track_path
        assert tracks[0].local_title is None  # untagged, but still paired

    def test_candidate_without_local_has_no_pairing(self, autotag_service):
        """A candidate track with no local counterpart stays unpaired."""
        local_album = LocalAlbumData(path="/album", artist="A", album="B", tracks=[])

        match = Mock()
        match.mapping = None
        info = Mock()
        info.tracks = [self._track_info(4, "Cycling")]
        match.info = info

        tracks, _ = autotag_service._compute_track_data(match, local_album)

        assert len(tracks) == 1
        assert tracks[0].local_title is None
        assert tracks[0].local_path is None


class TestDataClasses:
    """Tests for data classes."""

    def test_local_track_data(self):
        """Test LocalTrackData creation."""
        track = LocalTrackData(
            path="/path/track.mp3",
            title="Track Title",
            track_num=1,
            length=180.5,
        )
        assert track.path == "/path/track.mp3"
        assert track.title == "Track Title"
        assert track.track_num == 1
        assert track.length == 180.5

    def test_local_album_data(self):
        """Test LocalAlbumData creation."""
        album = LocalAlbumData(
            path="/path/album",
            artist="Artist",
            album="Album",
            tracks=[],
        )
        assert album.path == "/path/album"
        assert album.artist == "Artist"
        assert album.album == "Album"
        assert album.tracks == []

    def test_candidate_track_data(self):
        """Test CandidateTrackData creation."""
        track = CandidateTrackData(
            index=1,
            title="Track Title",
            length=180.5,
            changes=[{"field": "title", "from_value": "Old", "to_value": "New"}],
        )
        assert track.index == 1
        assert track.title == "Track Title"
        assert track.length == 180.5
        assert len(track.changes) == 1
        # Pairing fields default to None when not provided.
        assert track.local_title is None
        assert track.local_path is None

    def test_candidate_track_data_with_local_pairing(self):
        """CandidateTrackData carries the paired local title/path."""
        track = CandidateTrackData(
            index=1,
            title="Stay",
            length=180.0,
            changes=[],
            local_title="Stay",
            local_path="/album/01.flac",
        )
        assert track.local_title == "Stay"
        assert track.local_path == "/album/01.flac"

    def test_candidate_data(self):
        """Test CandidateData creation."""
        candidate = CandidateData(
            source="MusicBrainz",
            source_id="mb-123",
            similarity=0.95,
            artist="Artist",
            album="Album",
            year=2020,
            label="Label",
            country="US",
            media="CD",
            tracks=[],
            changes=[],
            track_changes=[],
        )
        assert candidate.source == "MusicBrainz"
        assert candidate.source_id == "mb-123"
        assert candidate.similarity == 0.95
        assert candidate.year == 2020



class TestReadLocalAlbumFolderFallback:
    """_read_local_album falls back to folder/filename hints for untagged rips
    (issue #138). Dummy files are unparseable by mutagen, i.e. fully untagged."""

    def _make_album(self, parent, folder, filenames):
        album_dir = os.path.join(parent, folder)
        os.makedirs(album_dir)
        for name in filenames:
            with open(os.path.join(album_dir, name), "wb") as f:
                f.write(b"dummy")
        return album_dir

    def test_untagged_folder_seeds_artist_album_and_source(self, autotag_service):
        with tempfile.TemporaryDirectory() as tmp:
            album_dir = self._make_album(
                tmp,
                "Holy Klassiker-Folge 1  Der kleine Prinz"
                "-16BIT-44-KHZ-WEB-FLAC-2021-WALKMAN",
                [
                    "01-holy_klassiker-teil_1_-_folge_1.flac",
                    "02-holy_klassiker-teil_2_-_folge_1.flac",
                ],
            )
            result = autotag_service._read_local_album(album_dir)

        assert result.artist == "Holy Klassiker"
        assert result.album == "Folge 1 Der kleine Prinz"
        assert result.metadata_source == "folder"

    def test_untagged_folder_seeds_track_titles_from_filenames(self, autotag_service):
        with tempfile.TemporaryDirectory() as tmp:
            album_dir = self._make_album(
                tmp,
                "Holy Klassiker-Folge 1-WEB-FLAC-2021-GRP",
                ["01-holy_klassiker-teil_1.flac"],
            )
            result = autotag_service._read_local_album(album_dir)

        # Filename title seeded, with the folder artist stripped off the front.
        assert result.tracks[0].title == "teil 1"

    def test_unparseable_folder_leaves_metadata_none(self, autotag_service):
        """A folder name that parses to nothing usable stays unseeded so the
        explicit 'no metadata' path still triggers downstream."""
        with tempfile.TemporaryDirectory() as tmp:
            album_dir = self._make_album(tmp, "-", ["01.flac"])
            result = autotag_service._read_local_album(album_dir)

        assert result.artist is None
        assert result.album is None
        assert result.metadata_source == "tags"
