"""Unit tests for tag writer handlers with sample audio files.

Tests cover:
- MP3TagHandler: ID3v2.4 tags
- FLACTagHandler: Vorbis comments
- OGGTagHandler: Vorbis comments
- M4ATagHandler: MP4 atoms
- TagWriterRegistry: format detection and handler selection
"""

import os
import struct
import tempfile
from io import BytesIO
from typing import Dict, Optional

import pytest

# Import mutagen for creating test files
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPE2, TCON, TRCK, TPOS
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

from app.services.tag_writer import (
    MP3TagHandler,
    FLACTagHandler,
    OGGTagHandler,
    M4ATagHandler,
    TagWriterRegistry,
    get_tag_writer_registry,
    TagWriteResult,
    UnsupportedFormatError,
    CorruptedFileError,
    CANONICAL_TAGS,
    CanonicalTag,
)


# ============================================================================
# Fixtures for creating minimal test audio files
# ============================================================================


def create_minimal_mp3(path: str, tags: Optional[Dict[str, str]] = None):
    """Create a minimal valid MP3 file with optional tags.

    Creates a minimal MP3 file with a valid frame header.
    """
    # Minimal MP3 frame header and data
    # Frame sync (11 bits), MPEG Audio version 1, Layer 3, no protection
    # 128 kbps, 44100 Hz, stereo
    frame_header = bytes([
        0xFF, 0xFB,  # Sync word + MPEG1 Layer3
        0x90,  # 128kbps, 44100Hz
        0x00,  # Padding, channel mode, etc.
    ])
    # Minimal frame data (just enough to be valid)
    frame_data = bytes([0x00] * 417)  # 128kbps at 44100Hz = 418 bytes/frame

    # Write the file
    with open(path, "wb") as f:
        f.write(frame_header + frame_data)

    # Add tags if provided
    if tags:
        try:
            audio = ID3(path)
        except Exception:
            audio = ID3()

        if "album" in tags:
            audio.add(TALB(encoding=3, text=[tags["album"]]))
        if "title" in tags:
            audio.add(TIT2(encoding=3, text=[tags["title"]]))
        if "artist" in tags:
            audio.add(TPE1(encoding=3, text=[tags["artist"]]))
        if "album_artist" in tags:
            audio.add(TPE2(encoding=3, text=[tags["album_artist"]]))
        if "genre" in tags:
            audio.add(TCON(encoding=3, text=[tags["genre"]]))
        if "track_number" in tags:
            audio.add(TRCK(encoding=3, text=[tags["track_number"]]))
        if "disc_number" in tags:
            audio.add(TPOS(encoding=3, text=[tags["disc_number"]]))

        audio.save(path, v2_version=4)


def create_minimal_flac(path: str, tags: Optional[Dict[str, str]] = None):
    """Create a minimal valid FLAC file with optional tags.

    Uses mutagen to create a proper FLAC file.
    """
    # Create minimal FLAC file structure
    # FLAC files start with 'fLaC' marker followed by metadata blocks
    # Minimum: STREAMINFO block (required)

    # fLaC marker
    flac_marker = b"fLaC"

    # STREAMINFO block header (last block, type 0, length 34)
    streaminfo_header = bytes([0x80, 0x00, 0x00, 0x22])

    # STREAMINFO content (34 bytes)
    # Min/max block size, min/max frame size, sample rate, channels, bits, total samples, MD5
    streaminfo = bytes([
        0x10, 0x00,  # Min block size: 4096
        0x10, 0x00,  # Max block size: 4096
        0x00, 0x00, 0x00,  # Min frame size
        0x00, 0x00, 0x00,  # Max frame size
        0x0A, 0xC4, 0x42,  # Sample rate (44100) in 20 bits + channels (2) in 3 bits
        0xF0,  # bits per sample - 1 (15 = 16 bits) in 5 bits + total samples in 36 bits
        0x00, 0x00, 0x00, 0x00, 0x00,  # Total samples (0 = unknown)
        # MD5 signature (16 bytes of zeros)
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ])

    with open(path, "wb") as f:
        f.write(flac_marker + streaminfo_header + streaminfo)

    # Add tags using mutagen
    if tags:
        audio = FLAC(path)
        for key, value in tags.items():
            if key == "album":
                audio["ALBUM"] = value
            elif key == "title":
                audio["TITLE"] = value
            elif key == "artist":
                audio["ARTIST"] = value
            elif key == "album_artist":
                audio["ALBUMARTIST"] = value
            elif key == "genre":
                audio["GENRE"] = value
            elif key == "track_number":
                audio["TRACKNUMBER"] = value
            elif key == "disc_number":
                audio["DISCNUMBER"] = value
        audio.save()


def create_minimal_ogg(path: str, tags: Optional[Dict[str, str]] = None):
    """Create a minimal valid OGG Vorbis file with optional tags.

    OGG Vorbis files have a complex structure. We create a minimal
    file using low-level construction.
    """
    # Creating a proper OGG file requires the Ogg container format
    # plus Vorbis stream. This is complex, so we use a pre-made minimal file.

    # Minimal OGG Vorbis file bytes (from ffmpeg -f lavfi -i sine=frequency=1000:duration=0.001 -c:a libvorbis minimal.ogg)
    # This is a pre-encoded minimal OGG file
    minimal_ogg = bytes([
        0x4F, 0x67, 0x67, 0x53, 0x00, 0x02, 0x00, 0x00,  # OggS header, BOS
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # granule position
        0x00, 0x00, 0x00, 0x00,  # serial number
        0x00, 0x00, 0x00, 0x00,  # page sequence number
        0x00, 0x00, 0x00, 0x00,  # checksum (will be recalculated)
        0x01,  # page segments
        0x1E,  # segment table: 30 bytes
        # Vorbis identification header
        0x01, 0x76, 0x6F, 0x72, 0x62, 0x69, 0x73,  # packet type 1 + "vorbis"
        0x00, 0x00, 0x00, 0x00,  # vorbis version
        0x01,  # channels
        0x44, 0xAC, 0x00, 0x00,  # sample rate (44100)
        0x00, 0x00, 0x00, 0x00,  # bitrate max
        0x80, 0xBB, 0x00, 0x00,  # bitrate nominal
        0x00, 0x00, 0x00, 0x00,  # bitrate min
        0xB8,  # blocksize 0 & 1
        0x01,  # framing flag
    ])

    # Write minimal OGG structure - this won't be fully valid but
    # the test files can be created differently

    # For proper testing, we'll rely on the fixture creating a
    # basic file that mutagen can handle
    with open(path, "wb") as f:
        f.write(minimal_ogg)

    # Note: This minimal OGG may not be playable but should be enough
    # for basic tag tests. For production tests, use real audio files.


def create_minimal_m4a(path: str, tags: Optional[Dict[str, str]] = None):
    """Create a minimal valid M4A/MP4 file with optional tags.

    M4A files use the MP4 container format with atoms/boxes.
    """
    # Create minimal M4A structure with ftyp and moov atoms
    # This is a simplified version - real M4A files are more complex

    def make_atom(name: bytes, data: bytes) -> bytes:
        """Create an MP4 atom/box."""
        size = len(data) + 8
        return struct.pack(">I", size) + name + data

    def make_container_atom(name: bytes, children: bytes) -> bytes:
        """Create an MP4 container atom with children."""
        return make_atom(name, children)

    # ftyp atom (file type)
    ftyp = make_atom(b"ftyp", b"M4A \x00\x00\x00\x00M4A mp42isom")

    # Create minimal moov (movie) structure
    # This is simplified - a real file would have more atoms

    # mvhd (movie header)
    mvhd_data = bytes(108)  # Simplified mvhd
    mvhd = make_atom(b"mvhd", mvhd_data)

    # trak (track) - simplified
    tkhd_data = bytes(92)  # Track header
    tkhd = make_atom(b"tkhd", tkhd_data)

    # mdia (media) - simplified
    mdhd_data = bytes(32)
    mdhd = make_atom(b"mdhd", mdhd_data)

    # hdlr (handler reference)
    hdlr_data = b"\x00\x00\x00\x00" + b"mhlr" + b"soun" + bytes(12)
    hdlr = make_atom(b"hdlr", hdlr_data)

    minf = make_container_atom(b"minf", bytes(8))
    mdia = make_container_atom(b"mdia", mdhd + hdlr + minf)
    trak = make_container_atom(b"trak", tkhd + mdia)

    moov = make_container_atom(b"moov", mvhd + trak)

    # mdat (media data) - empty for minimal file
    mdat = make_atom(b"mdat", b"")

    with open(path, "wb") as f:
        f.write(ftyp + moov + mdat)

    # Add tags using mutagen
    if tags:
        try:
            audio = MP4(path)
            if audio.tags is None:
                audio.add_tags()

            for key, value in tags.items():
                if key == "album":
                    audio["\xa9alb"] = [value]
                elif key == "title":
                    audio["\xa9nam"] = [value]
                elif key == "artist":
                    audio["\xa9ART"] = [value]
                elif key == "album_artist":
                    audio["aART"] = [value]
                elif key == "genre":
                    audio["\xa9gen"] = [value]
                elif key == "track_number":
                    # Parse "N" or "N/T" format
                    if "/" in str(value):
                        parts = str(value).split("/")
                        audio["trkn"] = [(int(parts[0]), int(parts[1]))]
                    else:
                        audio["trkn"] = [(int(value), 0)]
                elif key == "disc_number":
                    if "/" in str(value):
                        parts = str(value).split("/")
                        audio["disk"] = [(int(parts[0]), int(parts[1]))]
                    else:
                        audio["disk"] = [(int(value), 0)]

            audio.save()
        except Exception:
            pass  # M4A creation may fail with minimal file


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mp3_file(temp_dir):
    """Create a temporary MP3 file."""
    path = os.path.join(temp_dir, "test.mp3")
    create_minimal_mp3(path)
    return path


@pytest.fixture
def mp3_file_with_tags(temp_dir):
    """Create a temporary MP3 file with tags."""
    path = os.path.join(temp_dir, "test_with_tags.mp3")
    create_minimal_mp3(path, {
        "album": "Test Album",
        "title": "Test Title",
        "artist": "Test Artist",
        "album_artist": "Test Album Artist",
        "genre": "Rock",
        "track_number": "5/12",
        "disc_number": "1/2",
    })
    return path


@pytest.fixture
def flac_file(temp_dir):
    """Create a temporary FLAC file."""
    path = os.path.join(temp_dir, "test.flac")
    create_minimal_flac(path)
    return path


@pytest.fixture
def flac_file_with_tags(temp_dir):
    """Create a temporary FLAC file with tags."""
    path = os.path.join(temp_dir, "test_with_tags.flac")
    create_minimal_flac(path, {
        "album": "Test Album",
        "title": "Test Title",
        "artist": "Test Artist",
        "album_artist": "Test Album Artist",
        "genre": "Rock",
        "track_number": "5/12",
        "disc_number": "1/2",
    })
    return path


# ============================================================================
# MP3TagHandler Tests
# ============================================================================


class TestMP3TagHandler:
    """Tests for MP3/ID3v2.4 tag handler."""

    def test_can_handle_mp3_extension(self):
        """Test handler recognizes .mp3 extension."""
        handler = MP3TagHandler()
        assert handler.can_handle("/path/to/file.mp3") is True
        assert handler.can_handle("/path/to/file.MP3") is True
        assert handler.can_handle("/path/to/file.flac") is False

    def test_supported_extensions(self):
        """Test supported extensions property."""
        handler = MP3TagHandler()
        assert ".mp3" in handler.supported_extensions

    def test_format_name(self):
        """Test format name property."""
        handler = MP3TagHandler()
        assert handler.format_name == "mp3"

    def test_write_tags_to_new_file(self, mp3_file):
        """Test writing tags to MP3 file without existing tags."""
        handler = MP3TagHandler()
        result = handler.write_tags(mp3_file, {
            "album": "New Album",
            "title": "New Title",
            "artist": "New Artist",
        })

        assert result.success is True
        assert result.tags_written["album"] == "New Album"
        assert result.tags_written["title"] == "New Title"
        assert result.tags_written["artist"] == "New Artist"

    def test_write_tags_overwrites_existing(self, mp3_file_with_tags):
        """Test that writing tags overwrites existing values."""
        handler = MP3TagHandler()

        # Write new values
        result = handler.write_tags(mp3_file_with_tags, {
            "album": "Updated Album",
        })

        assert result.success is True
        assert result.tags_written["album"] == "Updated Album"

        # Verify the change
        tags = handler.read_tags(mp3_file_with_tags)
        assert tags["album"] == "Updated Album"
        # Other tags should be preserved
        assert tags["title"] == "Test Title"

    def test_read_tags(self, mp3_file_with_tags):
        """Test reading tags from MP3 file."""
        handler = MP3TagHandler()
        tags = handler.read_tags(mp3_file_with_tags)

        assert tags["album"] == "Test Album"
        assert tags["title"] == "Test Title"
        assert tags["artist"] == "Test Artist"
        assert tags["album_artist"] == "Test Album Artist"
        assert tags["genre"] == "Rock"
        assert tags["track_number"] == "5/12"
        assert tags["disc_number"] == "1/2"

    def test_clear_tag_with_empty_string(self, mp3_file_with_tags):
        """Test that empty string clears the tag."""
        handler = MP3TagHandler()

        # Clear the album tag
        result = handler.write_tags(mp3_file_with_tags, {"album": ""})
        assert result.success is True
        assert result.tags_written["album"] == ""

        # Verify it's cleared
        tags = handler.read_tags(mp3_file_with_tags)
        assert tags["album"] is None

    def test_write_track_number_formats(self, mp3_file):
        """Test writing track numbers in various formats."""
        handler = MP3TagHandler()

        # Single number
        result = handler.write_tags(mp3_file, {"track_number": "5"})
        assert result.success is True
        tags = handler.read_tags(mp3_file)
        assert tags["track_number"] == "5"

        # With total
        result = handler.write_tags(mp3_file, {"track_number": "3/12"})
        assert result.success is True
        tags = handler.read_tags(mp3_file)
        assert tags["track_number"] == "3/12"

    def test_file_not_found_error(self, temp_dir):
        """Test error when file doesn't exist."""
        handler = MP3TagHandler()
        result = handler.write_tags(
            os.path.join(temp_dir, "nonexistent.mp3"),
            {"album": "Test"},
        )

        assert result.success is False
        assert result.error_code == "FILE_NOT_FOUND"

    def test_read_file_not_found_error(self, temp_dir):
        """Test error when reading nonexistent file."""
        handler = MP3TagHandler()
        with pytest.raises(FileNotFoundError):
            handler.read_tags(os.path.join(temp_dir, "nonexistent.mp3"))


# ============================================================================
# FLACTagHandler Tests
# ============================================================================


class TestFLACTagHandler:
    """Tests for FLAC/Vorbis comment tag handler."""

    def test_can_handle_flac_extension(self):
        """Test handler recognizes .flac extension."""
        handler = FLACTagHandler()
        assert handler.can_handle("/path/to/file.flac") is True
        assert handler.can_handle("/path/to/file.FLAC") is True
        assert handler.can_handle("/path/to/file.mp3") is False

    def test_supported_extensions(self):
        """Test supported extensions property."""
        handler = FLACTagHandler()
        assert ".flac" in handler.supported_extensions

    def test_format_name(self):
        """Test format name property."""
        handler = FLACTagHandler()
        assert handler.format_name == "flac"

    def test_write_tags(self, flac_file):
        """Test writing tags to FLAC file."""
        handler = FLACTagHandler()
        result = handler.write_tags(flac_file, {
            "album": "Test Album",
            "title": "Test Title",
            "artist": "Test Artist",
        })

        assert result.success is True
        assert result.tags_written["album"] == "Test Album"

    def test_read_tags(self, flac_file_with_tags):
        """Test reading tags from FLAC file."""
        handler = FLACTagHandler()
        tags = handler.read_tags(flac_file_with_tags)

        assert tags["album"] == "Test Album"
        assert tags["title"] == "Test Title"
        assert tags["artist"] == "Test Artist"

    def test_file_not_found_error(self, temp_dir):
        """Test error when file doesn't exist."""
        handler = FLACTagHandler()
        result = handler.write_tags(
            os.path.join(temp_dir, "nonexistent.flac"),
            {"album": "Test"},
        )

        assert result.success is False
        assert result.error_code == "FILE_NOT_FOUND"


# ============================================================================
# OGGTagHandler Tests
# ============================================================================


class TestOGGTagHandler:
    """Tests for OGG Vorbis tag handler."""

    def test_can_handle_ogg_extensions(self):
        """Test handler recognizes .ogg and .oga extensions."""
        handler = OGGTagHandler()
        assert handler.can_handle("/path/to/file.ogg") is True
        assert handler.can_handle("/path/to/file.OGG") is True
        assert handler.can_handle("/path/to/file.oga") is True
        assert handler.can_handle("/path/to/file.mp3") is False

    def test_supported_extensions(self):
        """Test supported extensions property."""
        handler = OGGTagHandler()
        assert ".ogg" in handler.supported_extensions
        assert ".oga" in handler.supported_extensions

    def test_format_name(self):
        """Test format name property."""
        handler = OGGTagHandler()
        assert handler.format_name == "ogg"

    def test_file_not_found_error(self, temp_dir):
        """Test error when file doesn't exist."""
        handler = OGGTagHandler()
        result = handler.write_tags(
            os.path.join(temp_dir, "nonexistent.ogg"),
            {"album": "Test"},
        )

        assert result.success is False
        assert result.error_code == "FILE_NOT_FOUND"


# ============================================================================
# M4ATagHandler Tests
# ============================================================================


class TestM4ATagHandler:
    """Tests for M4A/MP4 atom tag handler."""

    def test_can_handle_m4a_extensions(self):
        """Test handler recognizes M4A-related extensions."""
        handler = M4ATagHandler()
        assert handler.can_handle("/path/to/file.m4a") is True
        assert handler.can_handle("/path/to/file.M4A") is True
        assert handler.can_handle("/path/to/file.mp4") is True
        assert handler.can_handle("/path/to/file.aac") is True
        assert handler.can_handle("/path/to/file.mp3") is False

    def test_supported_extensions(self):
        """Test supported extensions property."""
        handler = M4ATagHandler()
        assert ".m4a" in handler.supported_extensions
        assert ".mp4" in handler.supported_extensions
        assert ".aac" in handler.supported_extensions

    def test_format_name(self):
        """Test format name property."""
        handler = M4ATagHandler()
        assert handler.format_name == "m4a"

    def test_file_not_found_error(self, temp_dir):
        """Test error when file doesn't exist."""
        handler = M4ATagHandler()
        result = handler.write_tags(
            os.path.join(temp_dir, "nonexistent.m4a"),
            {"album": "Test"},
        )

        assert result.success is False
        assert result.error_code == "FILE_NOT_FOUND"


# ============================================================================
# TagWriterRegistry Tests
# ============================================================================


class TestTagWriterRegistry:
    """Tests for the TagWriterRegistry class."""

    def test_default_handlers_registered(self):
        """Test that default handlers are registered."""
        registry = TagWriterRegistry()

        assert registry.get_handler("test.mp3") is not None
        assert registry.get_handler("test.flac") is not None
        assert registry.get_handler("test.ogg") is not None
        assert registry.get_handler("test.m4a") is not None

    def test_is_supported(self):
        """Test format support checking."""
        registry = TagWriterRegistry()

        assert registry.is_supported("test.mp3") is True
        assert registry.is_supported("test.flac") is True
        assert registry.is_supported("test.ogg") is True
        assert registry.is_supported("test.m4a") is True
        assert registry.is_supported("test.wav") is False
        assert registry.is_supported("test.txt") is False

    def test_get_format(self):
        """Test format name retrieval."""
        registry = TagWriterRegistry()

        assert registry.get_format("test.mp3") == "mp3"
        assert registry.get_format("test.flac") == "flac"
        assert registry.get_format("test.ogg") == "ogg"
        assert registry.get_format("test.m4a") == "m4a"
        assert registry.get_format("test.wav") is None

    def test_read_tags_unsupported_format(self, temp_dir):
        """Test that unsupported format raises error."""
        registry = TagWriterRegistry()

        # Create a dummy file with unsupported extension
        path = os.path.join(temp_dir, "test.wav")
        with open(path, "wb") as f:
            f.write(b"RIFF")

        with pytest.raises(UnsupportedFormatError):
            registry.read_tags(path)

    def test_write_tags_unsupported_format(self, temp_dir):
        """Test that unsupported format returns error result."""
        registry = TagWriterRegistry()

        path = os.path.join(temp_dir, "test.wav")
        with open(path, "wb") as f:
            f.write(b"RIFF")

        result = registry.write_tags(path, {"album": "Test"})

        assert result.success is False
        assert result.error_code == "UNSUPPORTED_FORMAT"

    def test_batch_write(self, temp_dir):
        """Test batch writing to multiple files."""
        registry = TagWriterRegistry()

        # Create test files
        mp3_path = os.path.join(temp_dir, "test.mp3")
        create_minimal_mp3(mp3_path)

        flac_path = os.path.join(temp_dir, "test.flac")
        create_minimal_flac(flac_path)

        file_tags = [
            (mp3_path, {"album": "Album 1"}),
            (flac_path, {"album": "Album 2"}),
        ]

        result = registry.batch_write(file_tags)

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0

    def test_batch_write_with_failures(self, temp_dir):
        """Test batch writing with some failures."""
        registry = TagWriterRegistry()

        # Create one valid file
        mp3_path = os.path.join(temp_dir, "test.mp3")
        create_minimal_mp3(mp3_path)

        # Create path to nonexistent file
        nonexistent_path = os.path.join(temp_dir, "nonexistent.mp3")

        file_tags = [
            (mp3_path, {"album": "Album 1"}),
            (nonexistent_path, {"album": "Album 2"}),
        ]

        result = registry.batch_write(file_tags)

        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1

    def test_singleton_registry(self):
        """Test that get_tag_writer_registry returns singleton."""
        registry1 = get_tag_writer_registry()
        registry2 = get_tag_writer_registry()

        assert registry1 is registry2


# ============================================================================
# TagHandler Base Class Tests
# ============================================================================


class TestTagHandlerBase:
    """Tests for TagHandler base class methods."""

    def test_normalize_track_number_single(self):
        """Test normalizing single track number."""
        handler = MP3TagHandler()

        track, total = handler._normalize_track_number("5")
        assert track == 5
        assert total is None

    def test_normalize_track_number_with_total(self):
        """Test normalizing track number with total."""
        handler = MP3TagHandler()

        track, total = handler._normalize_track_number("5/12")
        assert track == 5
        assert total == 12

    def test_normalize_track_number_empty(self):
        """Test normalizing empty track number."""
        handler = MP3TagHandler()

        track, total = handler._normalize_track_number("")
        assert track is None
        assert total is None

        track, total = handler._normalize_track_number(None)
        assert track is None
        assert total is None

    def test_normalize_track_number_with_spaces(self):
        """Test normalizing track number with spaces."""
        handler = MP3TagHandler()

        track, total = handler._normalize_track_number(" 5 / 12 ")
        assert track == 5
        assert total == 12

    def test_normalize_track_number_invalid(self):
        """Test normalizing invalid track number."""
        handler = MP3TagHandler()

        track, total = handler._normalize_track_number("invalid")
        assert track is None
        assert total is None

        track, total = handler._normalize_track_number("a/b")
        assert track is None
        assert total is None


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestTagWriterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unicode_tag_values(self, mp3_file):
        """Test writing unicode characters in tags."""
        handler = MP3TagHandler()

        result = handler.write_tags(mp3_file, {
            "album": "Bjork - Homogenic \u2665",
            "artist": "\u00c9mile Durkheim",
            "title": "\u4e2d\u6587\u6807\u9898",  # Chinese characters
        })

        assert result.success is True

        tags = handler.read_tags(mp3_file)
        assert tags["album"] == "Bjork - Homogenic \u2665"
        assert tags["artist"] == "\u00c9mile Durkheim"
        assert tags["title"] == "\u4e2d\u6587\u6807\u9898"

    def test_special_characters_in_tags(self, mp3_file):
        """Test writing special characters in tags."""
        handler = MP3TagHandler()

        result = handler.write_tags(mp3_file, {
            "album": "Album: The \"Special\" One! (2024)",
            "title": "Song & Dance <3>",
        })

        assert result.success is True

        tags = handler.read_tags(mp3_file)
        assert tags["album"] == "Album: The \"Special\" One! (2024)"
        assert tags["title"] == "Song & Dance <3>"

    def test_very_long_tag_values(self, mp3_file):
        """Test writing very long tag values."""
        handler = MP3TagHandler()
        long_value = "A" * 10000  # 10KB string

        result = handler.write_tags(mp3_file, {"album": long_value})

        assert result.success is True

        tags = handler.read_tags(mp3_file)
        assert tags["album"] == long_value

    def test_unknown_canonical_tag_ignored(self, mp3_file):
        """Test that unknown canonical tags are ignored."""
        handler = MP3TagHandler()

        result = handler.write_tags(mp3_file, {
            "album": "Test Album",
            "unknown_tag": "Should be ignored",
        })

        assert result.success is True
        assert "album" in result.tags_written
        assert "unknown_tag" not in result.tags_written

    def test_read_file_with_no_tags(self, mp3_file):
        """Test reading from file with no tags."""
        handler = MP3TagHandler()
        tags = handler.read_tags(mp3_file)

        # All tags should be None
        for tag in CANONICAL_TAGS:
            assert tags[tag] is None

    def test_write_preserves_unmodified_tags(self, mp3_file_with_tags):
        """Test that writing some tags preserves others."""
        handler = MP3TagHandler()

        # Only modify album
        result = handler.write_tags(mp3_file_with_tags, {"album": "New Album"})
        assert result.success is True

        # Verify other tags are preserved
        tags = handler.read_tags(mp3_file_with_tags)
        assert tags["album"] == "New Album"
        assert tags["title"] == "Test Title"  # Unchanged
        assert tags["artist"] == "Test Artist"  # Unchanged


# ============================================================================
# Regression: Vorbis album-artist alias shadowing (issue #114)
# ============================================================================

# All three album-artist alias keys mediafile reads, in its priority order.
ALBUM_ARTIST_ALIASES = ("ALBUM ARTIST", "ALBUM_ARTIST", "ALBUMARTIST")


@pytest.fixture
def flac_stale_alias(temp_dir):
    """FLAC seeded with a stale 'ALBUM ARTIST' (space) alias, as Picard/foobar write.

    All three album-artist alias keys hold the OLD value, mimicking a file
    tagged by another editor before our writer touches it. mediafile reads
    'ALBUM ARTIST' (with the space) first, so writing only the canonical
    'ALBUMARTIST' key would be shadowed on read-back. Returns (path, old_value).
    """
    path = os.path.join(temp_dir, "stale_alias.flac")
    create_minimal_flac(path)

    old = "D'Schlieremer Chind & Cabaret Rotstift"
    audio = FLAC(path)
    for key in ALBUM_ARTIST_ALIASES:
        audio[key] = old
    audio["ARTIST"] = old
    audio.save()
    return path, old


class TestVorbisAlbumArtistAliasShadowing:
    """Regression tests for issue #114.

    Editing album_artist on FLAC/OGG must update every alias key mediafile
    reads, so the change survives the read-back beets performs in `beet update`.
    FLAC and OGG share the same `_apply_vorbis_tag` write path, so the FLAC
    coverage here exercises both.
    """

    def test_album_artist_edit_not_shadowed_on_mediafile_readback(self, flac_stale_alias):
        """The value beets re-reads (mediafile) reflects the edit, not the stale alias."""
        mediafile = pytest.importorskip("mediafile")
        path, _old = flac_stale_alias
        new = "D'Schlieremer Chind"

        handler = FLACTagHandler()
        result = handler.write_tags(path, {"album_artist": new})

        assert result.success is True
        assert result.tags_written["album_artist"] == new
        # This is exactly what `beet update -a` re-reads from the file.
        assert mediafile.MediaFile(path).albumartist == new
        # Our own reader agrees.
        assert handler.read_tags(path)["album_artist"] == new

    def test_album_artist_write_updates_every_alias_key(self, flac_stale_alias):
        """No stale alias is left holding the old value after a write."""
        path, _old = flac_stale_alias
        new = "New Album Artist"

        FLACTagHandler().write_tags(path, {"album_artist": new})

        audio = FLAC(path)
        for key in ALBUM_ARTIST_ALIASES:
            assert audio[key] == [new], f"alias {key!r} not updated"

    def test_clear_album_artist_removes_all_aliases(self, flac_stale_alias):
        """Clearing album_artist scrubs every alias so nothing shadows the empty value."""
        mediafile = pytest.importorskip("mediafile")
        path, _old = flac_stale_alias

        result = FLACTagHandler().write_tags(path, {"album_artist": ""})

        assert result.success is True
        assert result.tags_written["album_artist"] == ""
        audio = FLAC(path)
        for key in ALBUM_ARTIST_ALIASES:
            assert key not in audio, f"alias {key!r} not removed on clear"
        assert not mediafile.MediaFile(path).albumartist

    def test_artist_edit_does_not_create_album_artist_aliases(self, flac_file_with_tags):
        """Single-key fields (artist) are untouched by the alias-scrub refactor."""
        handler = FLACTagHandler()

        handler.write_tags(flac_file_with_tags, {"artist": "Solo Artist"})

        audio = FLAC(flac_file_with_tags)
        assert audio["ARTIST"] == ["Solo Artist"]
        assert "ALBUM ARTIST" not in audio
        assert "ALBUM_ARTIST" not in audio
