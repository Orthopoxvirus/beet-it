"""Unit tests for ScannerService."""

import os
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.scanner.scanner_service import (
    ScannerService,
    AudioMetadata,
    ScannedItem,
    AUDIO_EXTENSIONS,
    is_audio_filename,
)


@pytest.fixture
def scanner_service():
    """Create a ScannerService instance."""
    return ScannerService(batch_size=10, timeout_seconds=60)


class TestIsAudioFilename:
    """Tests for the shared audio-extension classifier."""

    @pytest.mark.parametrize(
        "name",
        ["01-track.flac", "song.mp3", "a.m4a", "b.opus", "c.wav", "UPPER.FLAC"],
    )
    def test_audio_files_are_audio(self, name):
        assert is_audio_filename(name) is True

    @pytest.mark.parametrize(
        "name",
        ["cover.jpg", "playlist.m3u", "checksums.sfv", "release.nfo", "folder.png", "notes.txt", ""],
    )
    def test_sidecar_files_are_not_audio(self, name):
        assert is_audio_filename(name) is False


@pytest.fixture
def temp_import_dir():
    """Create a temporary import directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structure
        artist_dir = os.path.join(tmpdir, "Artist Name")
        album_dir = os.path.join(artist_dir, "Album Title")
        os.makedirs(album_dir)

        # Create files
        files = [
            os.path.join(album_dir, "01 - Track One.mp3"),
            os.path.join(album_dir, "02 - Track Two.mp3"),
            os.path.join(album_dir, "cover.jpg"),
        ]
        for f in files:
            with open(f, "w") as fp:
                fp.write("dummy content")

        # Create hidden files (should be ignored)
        hidden_file = os.path.join(album_dir, ".hidden")
        with open(hidden_file, "w") as fp:
            fp.write("hidden")

        yield tmpdir


class TestAudioFileDetection:
    """Tests for audio file detection."""

    def test_is_audio_file_mp3(self, scanner_service):
        """Test detecting MP3 files."""
        assert scanner_service._is_audio_file("/path/song.mp3") is True
        assert scanner_service._is_audio_file("/path/song.MP3") is True

    def test_is_audio_file_flac(self, scanner_service):
        """Test detecting FLAC files."""
        assert scanner_service._is_audio_file("/path/song.flac") is True
        assert scanner_service._is_audio_file("/path/song.FLAC") is True

    def test_is_audio_file_ogg(self, scanner_service):
        """Test detecting OGG files."""
        assert scanner_service._is_audio_file("/path/song.ogg") is True
        assert scanner_service._is_audio_file("/path/song.opus") is True

    def test_is_audio_file_m4a(self, scanner_service):
        """Test detecting M4A files."""
        assert scanner_service._is_audio_file("/path/song.m4a") is True
        assert scanner_service._is_audio_file("/path/song.mp4") is True

    def test_is_audio_file_other(self, scanner_service):
        """Test non-audio files."""
        assert scanner_service._is_audio_file("/path/image.jpg") is False
        assert scanner_service._is_audio_file("/path/document.pdf") is False
        assert scanner_service._is_audio_file("/path/readme.txt") is False


class TestHiddenFileDetection:
    """Tests for hidden file detection."""

    def test_is_hidden_dotfile(self, scanner_service):
        """Test detecting hidden files starting with dot."""
        assert scanner_service._is_hidden(".hidden") is True
        assert scanner_service._is_hidden("/path/.hidden") is True

    def test_is_hidden_hidden_dir(self, scanner_service):
        """Test detecting files in hidden directories."""
        assert scanner_service._is_hidden(".hidden/file.mp3") is True
        assert scanner_service._is_hidden("/path/.hidden/file.mp3") is True

    def test_is_hidden_normal_files(self, scanner_service):
        """Test normal files are not hidden."""
        assert scanner_service._is_hidden("file.mp3") is False
        assert scanner_service._is_hidden("/path/file.mp3") is False


class TestDirectoryScanning:
    """Tests for directory scanning."""

    def test_scan_directory_structure(self, scanner_service, temp_import_dir):
        """Test scanning directory returns expected structure."""
        items = list(scanner_service.scan_directory(temp_import_dir))

        # Should have: 2 directories (Artist, Album) + 3 non-hidden files
        paths = [item.path for item in items]

        # Check directories
        assert any("Artist Name" in p and os.path.isdir(p) for p in paths)
        assert any("Album Title" in p and os.path.isdir(p) for p in paths)

        # Check files
        assert any("Track One.mp3" in p for p in paths)
        assert any("Track Two.mp3" in p for p in paths)
        assert any("cover.jpg" in p for p in paths)

        # Hidden file should not be present
        assert not any(".hidden" in p for p in paths)

    def test_scan_directory_item_types(self, scanner_service, temp_import_dir):
        """Test scanned items have correct types."""
        items = list(scanner_service.scan_directory(temp_import_dir))

        folders = [i for i in items if i.item_type == "folder"]
        files = [i for i in items if i.item_type == "file"]

        assert len(folders) == 2  # Artist, Album directories
        assert len(files) == 3  # 2 mp3 + 1 jpg

    def test_scan_directory_audio_detection(self, scanner_service, temp_import_dir):
        """Test audio files are correctly identified."""
        items = list(scanner_service.scan_directory(temp_import_dir))

        audio_items = [i for i in items if i.is_audio]
        non_audio_items = [i for i in items if not i.is_audio]

        assert len(audio_items) == 2  # 2 mp3 files
        assert len(non_audio_items) == 3  # 2 folders + 1 jpg

    def test_scan_directory_nonexistent(self, scanner_service):
        """Test scanning nonexistent directory."""
        items = list(scanner_service.scan_directory("/nonexistent/path"))

        assert len(items) == 0

    def test_scan_directory_progress_callback(self, scanner_service, temp_import_dir):
        """Test progress callback is called."""
        callback = Mock()
        scanner_service.batch_size = 1  # Call callback after each item

        list(scanner_service.scan_directory(temp_import_dir, callback))

        assert callback.called


class TestMetadataExtraction:
    """Tests for audio metadata extraction."""

    def test_extract_metadata_invalid_file(self, scanner_service):
        """Test extracting metadata from invalid file."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"not a real mp3 file")
            f.flush()

            try:
                result = scanner_service._extract_metadata(f.name)
                # Should return None or empty metadata for invalid file
                assert result is None or isinstance(result, AudioMetadata)
            finally:
                os.unlink(f.name)

    def test_extract_metadata_nonexistent_file(self, scanner_service):
        """Test extracting metadata from nonexistent file."""
        result = scanner_service._extract_metadata("/nonexistent/file.mp3")

        assert result is None

    def test_get_first_tag(self, scanner_service):
        """Test getting first available tag."""
        mock_audio = {"album": ["Test Album"], "artist": ["Test Artist"]}

        result = scanner_service._get_first_tag(mock_audio, ["album"])
        assert result == "Test Album"

        result = scanner_service._get_first_tag(mock_audio, ["nonexistent", "artist"])
        assert result == "Test Artist"

        result = scanner_service._get_first_tag(mock_audio, ["nonexistent"])
        assert result is None


def _write_flac_with_vorbis_blocks(path, blocks):
    """Write a minimal valid FLAC at ``path`` carrying the given comment blocks.

    ``blocks`` is a list of ``{tag: [values]}`` dicts, each becoming one
    VORBIS_COMMENT block (more than one is illegal per the FLAC spec but occurs
    in real SoX/"WALKMAN" rips). mutagen reads metadata without decoding audio,
    so a header-only FLAC with valid StreamInfo is enough — no encoder needed.
    """
    import struct

    from mutagen.flac import FLAC, VCFLACDict

    # "fLaC" magic + a single last-block StreamInfo (4096 block size, 44100 Hz,
    # 2 channels, 16 bps, 0 total samples, zero MD5).
    streaminfo_body = (
        struct.pack(">HH", 4096, 4096)
        + b"\x00\x00\x00\x00\x00\x00"
        + struct.pack(">Q", (44100 << 44) | ((2 - 1) << 41) | ((16 - 1) << 36))
        + bytes(16)
    )
    header = bytes([0x80]) + struct.pack(">I", len(streaminfo_body))[1:]
    with open(path, "wb") as fh:
        fh.write(b"fLaC" + header + streaminfo_body)

    flac = FLAC(path)
    flac.metadata_blocks = [
        b for b in flac.metadata_blocks if not isinstance(b, VCFLACDict)
    ]
    vc_blocks = []
    for tags in blocks:
        vc = VCFLACDict()
        for key, values in tags.items():
            vc[key] = values
        vc_blocks.append(vc)
        flac.metadata_blocks.append(vc)
    # mutagen exposes the first comment block as .tags
    flac.tags = vc_blocks[0]
    flac.save(path)


class TestFlacMultiVorbisBlocks:
    """Regression tests for FLACs carrying multiple VORBIS_COMMENT blocks (#29)."""

    def test_title_and_track_read_from_second_block(self, scanner_service):
        """title/track living in a later comment block must still be picked up."""
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
            path = f.name
        try:
            _write_flac_with_vorbis_blocks(
                path,
                [
                    # Block A — what mutagen's easy view sees, no title/track
                    {
                        "album": ["Photobook"],
                        "artist": ["George Ezra"],
                        "comment": ["Processed by SoX"],
                    },
                    # Block B — holds the real title/track
                    {
                        "title": ["Stay"],
                        "track": ["1"],
                        "tracktotal": ["3"],
                        "artist": ["Ezra George"],
                    },
                ],
            )
            meta = scanner_service._extract_metadata(path)
            assert meta is not None
            assert meta.title == "Stay"
            assert meta.track_number == 1
            assert meta.track_total == 3
            assert meta.album == "Photobook"  # filled from the other block
            # On conflict the title/track-bearing block wins.
            assert meta.artist == "Ezra George"
        finally:
            os.unlink(path)

    def test_single_block_flac_is_unchanged(self, scanner_service):
        """A normal one-block FLAC reads exactly as before (no merge path)."""
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
            path = f.name
        try:
            _write_flac_with_vorbis_blocks(
                path,
                [
                    {
                        "album": ["Solo Album"],
                        "artist": ["Solo Artist"],
                        "title": ["Solo Track"],
                        "tracknumber": ["2"],
                    }
                ],
            )
            meta = scanner_service._extract_metadata(path)
            assert meta is not None
            assert meta.title == "Solo Track"
            assert meta.track_number == 2
            assert meta.album == "Solo Album"
            assert meta.artist == "Solo Artist"
        finally:
            os.unlink(path)


class TestTrackTotalExtraction:
    """Tests for track total extraction from audio tags."""

    def test_audio_metadata_has_track_total(self):
        """Test AudioMetadata includes track_total field."""
        metadata = AudioMetadata(
            album="Test Album",
            track_number=3,
            track_total=12
        )
        assert metadata.track_number == 3
        assert metadata.track_total == 12

    def test_audio_metadata_track_total_default_none(self):
        """Test AudioMetadata track_total defaults to None."""
        metadata = AudioMetadata()
        assert metadata.track_total is None

    def test_parse_track_with_total_format(self, scanner_service):
        """Test parsing track tag in 'x/y' format extracts both values."""
        # Mock audio with tracknumber in "3/12" format
        mock_audio = MagicMock()
        mock_audio.get.return_value = ["3/12"]

        # Call _get_first_tag to get the raw track value
        track_raw = scanner_service._get_first_tag(mock_audio, ["tracknumber"])
        assert track_raw == "3/12"

        # Verify the format can be parsed
        if "/" in track_raw:
            parts = track_raw.split("/")
            assert int(parts[0]) == 3
            assert int(parts[1]) == 12


class TestChangeDetection:
    """Tests for change detection."""

    def test_detect_changes_new_items(self, scanner_service):
        """Test detecting new items."""
        current = {
            "/path/new.mp3": ScannedItem(
                path="/path/new.mp3",
                item_type="file",
                directory="/path",
                filename="new.mp3",
                is_audio=True,
            )
        }
        previous = {}

        new, modified, unchanged, deleted = scanner_service.detect_changes(
            current, previous
        )

        assert "/path/new.mp3" in new
        assert len(modified) == 0
        assert len(unchanged) == 0
        assert len(deleted) == 0

    def test_detect_changes_deleted_items(self, scanner_service):
        """Test detecting deleted items."""
        current = {}
        previous = {
            "/path/deleted.mp3": {"item_type": "file", "metadata": None}
        }

        new, modified, unchanged, deleted = scanner_service.detect_changes(
            current, previous
        )

        assert len(new) == 0
        assert len(modified) == 0
        assert len(unchanged) == 0
        assert "/path/deleted.mp3" in deleted

    def test_detect_changes_unchanged_items(self, scanner_service):
        """Test detecting unchanged items."""
        current = {
            "/path/same.mp3": ScannedItem(
                path="/path/same.mp3",
                item_type="file",
                directory="/path",
                filename="same.mp3",
                is_audio=True,
                metadata=AudioMetadata(album="Album", artist="Artist"),
            )
        }
        previous = {
            "/path/same.mp3": {
                "item_type": "file",
                "metadata": {"album": "Album", "artist": "Artist"},
            }
        }

        new, modified, unchanged, deleted = scanner_service.detect_changes(
            current, previous
        )

        assert len(new) == 0
        assert len(modified) == 0
        assert "/path/same.mp3" in unchanged
        assert len(deleted) == 0

    def test_detect_changes_modified_items(self, scanner_service):
        """Test detecting modified items."""
        current = {
            "/path/modified.mp3": ScannedItem(
                path="/path/modified.mp3",
                item_type="file",
                directory="/path",
                filename="modified.mp3",
                is_audio=True,
                metadata=AudioMetadata(album="New Album", artist="Artist"),
            )
        }
        previous = {
            "/path/modified.mp3": {
                "item_type": "file",
                "metadata": {"album": "Old Album", "artist": "Artist"},
            }
        }

        new, modified, unchanged, deleted = scanner_service.detect_changes(
            current, previous
        )

        assert len(new) == 0
        assert "/path/modified.mp3" in modified
        assert len(unchanged) == 0
        assert len(deleted) == 0

    def test_detect_changes_track_total_modified(self, scanner_service):
        """Test detecting changes when track_total is modified."""
        current = {
            "/path/track.mp3": ScannedItem(
                path="/path/track.mp3",
                item_type="file",
                directory="/path",
                filename="track.mp3",
                is_audio=True,
                metadata=AudioMetadata(
                    album="Album",
                    artist="Artist",
                    track_number=3,
                    track_total=15,  # Changed from 12 to 15
                ),
            )
        }
        previous = {
            "/path/track.mp3": {
                "item_type": "file",
                "metadata": {
                    "album": "Album",
                    "artist": "Artist",
                    "track_number": 3,
                    "track_total": 12,
                },
            }
        }

        new, modified, unchanged, deleted = scanner_service.detect_changes(
            current, previous
        )

        assert len(new) == 0
        assert "/path/track.mp3" in modified
        assert len(unchanged) == 0
        assert len(deleted) == 0

    def test_detect_changes_unchanged_with_track_total(self, scanner_service):
        """Test items are unchanged when track_total matches."""
        current = {
            "/path/track.mp3": ScannedItem(
                path="/path/track.mp3",
                item_type="file",
                directory="/path",
                filename="track.mp3",
                is_audio=True,
                metadata=AudioMetadata(
                    album="Album",
                    artist="Artist",
                    track_number=3,
                    track_total=12,
                ),
            )
        }
        previous = {
            "/path/track.mp3": {
                "item_type": "file",
                "metadata": {
                    "album": "Album",
                    "artist": "Artist",
                    "track_number": 3,
                    "track_total": 12,
                },
            }
        }

        new, modified, unchanged, deleted = scanner_service.detect_changes(
            current, previous
        )

        assert len(new) == 0
        assert len(modified) == 0
        assert "/path/track.mp3" in unchanged
        assert len(deleted) == 0


class TestScanResult:
    """Tests for full scan results."""

    def test_scan_directory_full(self, scanner_service, temp_import_dir):
        """Test full directory scan returns complete results."""
        result = scanner_service.scan_directory_full(temp_import_dir)

        assert result.total_files == 3  # 2 mp3 + 1 jpg
        assert result.total_folders == 2  # Artist + Album
        assert result.audio_files == 2  # 2 mp3
        assert len(result.items) == 5  # All items

    def test_get_item_count(self, scanner_service, temp_import_dir):
        """Test getting item count."""
        count = scanner_service.get_item_count(temp_import_dir)

        # Should count all non-hidden items
        assert count >= 5  # 2 dirs + 3 files

    def test_get_item_count_nonexistent(self, scanner_service):
        """Test getting item count for nonexistent directory."""
        count = scanner_service.get_item_count("/nonexistent/path")

        assert count == 0


class TestAudioQualityExtraction:
    """Tests for container format + bitrate extraction (#47)."""

    def test_audio_metadata_quality_defaults_none(self):
        """format and bitrate default to None."""
        metadata = AudioMetadata()
        assert metadata.format is None
        assert metadata.bitrate is None

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/music/song.mp3", "mp3"),
            ("/music/song.FLAC", "flac"),
            ("/music/a.m4a", "m4a"),
            ("/music/UPPER.OPUS", "opus"),
        ],
    )
    def test_extract_format_known_extensions(self, scanner_service, path, expected):
        assert scanner_service._extract_format(path) == expected

    @pytest.mark.parametrize(
        "path",
        ["/music/cover.jpg", "/music/playlist.m3u", "/music/noext"],
    )
    def test_extract_format_non_audio(self, scanner_service, path):
        assert scanner_service._extract_format(path) is None

    def test_extract_bitrate_converts_bps_to_kbps(self, scanner_service):
        audio = Mock()
        audio.info.bitrate = 320000
        assert scanner_service._extract_bitrate(audio) == 320

    def test_extract_bitrate_rounds(self, scanner_service):
        audio = Mock()
        audio.info.bitrate = 128500
        assert scanner_service._extract_bitrate(audio) == 128

    def test_extract_bitrate_missing_info(self, scanner_service):
        audio = Mock(spec=[])  # no .info attribute
        assert scanner_service._extract_bitrate(audio) is None

    def test_extract_bitrate_zero_is_none(self, scanner_service):
        audio = Mock()
        audio.info.bitrate = 0
        assert scanner_service._extract_bitrate(audio) is None

    def test_extract_metadata_sets_format_from_extension(self, scanner_service):
        """A real FLAC file gets format='flac' regardless of tag layout."""
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
            path = f.name
        try:
            _write_flac_with_vorbis_blocks(
                path,
                [{"album": ["A"], "artist": ["B"], "title": ["C"], "tracknumber": ["1"]}],
            )
            meta = scanner_service._extract_metadata(path)
            assert meta is not None
            assert meta.format == "flac"
        finally:
            os.unlink(path)
