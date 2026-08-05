"""Unit tests for upload path sanitization and validation."""

import tempfile
from pathlib import Path

import pytest

from app.api.routes.upload import (
    validate_and_sanitize_path,
    parse_paths_json,
)


class TestValidateAndSanitizePath:
    """Tests for the validate_and_sanitize_path function."""

    @pytest.fixture
    def temp_import_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_valid_simple_filename(self, temp_import_dir):
        """Test valid simple filename."""
        result = validate_and_sanitize_path("track.mp3", temp_import_dir)
        assert result == (temp_import_dir / "track.mp3").resolve()

    def test_valid_path_with_subdirectory(self, temp_import_dir):
        """Test valid path with subdirectory."""
        result = validate_and_sanitize_path("Album/track.mp3", temp_import_dir)
        assert result == (temp_import_dir / "Album" / "track.mp3").resolve()

    def test_valid_nested_path(self, temp_import_dir):
        """Test valid deeply nested path."""
        result = validate_and_sanitize_path("Artist/Album/Disc 1/track.mp3", temp_import_dir)
        expected = (temp_import_dir / "Artist" / "Album" / "Disc 1" / "track.mp3").resolve()
        assert result == expected

    def test_valid_path_with_spaces(self, temp_import_dir):
        """Test valid path with spaces in names."""
        result = validate_and_sanitize_path("Artist Name/Album Title/01 Track.mp3", temp_import_dir)
        expected = (
            temp_import_dir / "Artist Name" / "Album Title" / "01 Track.mp3"
        ).resolve()
        assert result == expected

    def test_valid_path_with_special_characters(self, temp_import_dir):
        """Test valid path with special characters (parentheses, hyphens)."""
        result = validate_and_sanitize_path(
            "Artist - Album (2024)/01 - Track.flac", temp_import_dir
        )
        expected = (
            temp_import_dir / "Artist - Album (2024)" / "01 - Track.flac"
        ).resolve()
        assert result == expected

    def test_rejects_empty_path(self, temp_import_dir):
        """Test that empty paths are rejected."""
        with pytest.raises(ValueError, match="Empty path not allowed"):
            validate_and_sanitize_path("", temp_import_dir)

    def test_rejects_whitespace_only_path(self, temp_import_dir):
        """Test that whitespace-only paths are rejected."""
        with pytest.raises(ValueError, match="Empty path not allowed"):
            validate_and_sanitize_path("   ", temp_import_dir)

    def test_rejects_null_bytes(self, temp_import_dir):
        """Test that paths with null bytes are rejected."""
        with pytest.raises(ValueError, match="Null bytes not allowed"):
            validate_and_sanitize_path("track\x00.mp3", temp_import_dir)

    def test_rejects_null_bytes_in_directory(self, temp_import_dir):
        """Test that paths with null bytes in directory are rejected."""
        with pytest.raises(ValueError, match="Null bytes not allowed"):
            validate_and_sanitize_path("Album\x00/track.mp3", temp_import_dir)

    def test_rejects_absolute_path_forward_slash(self, temp_import_dir):
        """Test that absolute paths with forward slash are rejected."""
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            validate_and_sanitize_path("/etc/passwd", temp_import_dir)

    def test_rejects_absolute_path_backslash(self, temp_import_dir):
        """Test that absolute paths with backslash are rejected."""
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            validate_and_sanitize_path("\\Windows\\System32\\file", temp_import_dir)

    def test_rejects_parent_directory_traversal_simple(self, temp_import_dir):
        """Test that simple parent directory traversal is rejected."""
        with pytest.raises(ValueError, match="Parent directory traversal not allowed"):
            validate_and_sanitize_path("../secret.txt", temp_import_dir)

    def test_rejects_parent_directory_traversal_nested(self, temp_import_dir):
        """Test that nested parent directory traversal is rejected."""
        with pytest.raises(ValueError, match="Parent directory traversal not allowed"):
            validate_and_sanitize_path("Album/../../../etc/passwd", temp_import_dir)

    def test_rejects_parent_directory_traversal_middle(self, temp_import_dir):
        """Test that parent traversal in middle of path is rejected."""
        with pytest.raises(ValueError, match="Parent directory traversal not allowed"):
            validate_and_sanitize_path("Artist/../OtherArtist/track.mp3", temp_import_dir)

    def test_rejects_parent_directory_traversal_backslash(self, temp_import_dir):
        """Test that parent traversal with backslashes is rejected."""
        with pytest.raises(ValueError, match="Parent directory traversal not allowed"):
            validate_and_sanitize_path("Album\\..\\..\\secret.txt", temp_import_dir)

    def test_rejects_escaping_import_folder(self, temp_import_dir):
        """Test that paths resolving outside import folder are rejected."""
        # Even without explicit .., some path manipulation might escape
        # This tests the resolved path check
        with pytest.raises(ValueError, match="Parent directory traversal not allowed"):
            validate_and_sanitize_path("valid/../../escape", temp_import_dir)

    def test_handles_backslash_as_separator(self, temp_import_dir):
        """Test that backslashes are treated as path separators."""
        result = validate_and_sanitize_path("Artist\\Album\\track.mp3", temp_import_dir)
        expected = (temp_import_dir / "Artist" / "Album" / "track.mp3").resolve()
        assert result == expected

    def test_handles_mixed_separators(self, temp_import_dir):
        """Test that mixed path separators work correctly."""
        result = validate_and_sanitize_path("Artist/Album\\track.mp3", temp_import_dir)
        expected = (temp_import_dir / "Artist" / "Album" / "track.mp3").resolve()
        assert result == expected


class TestParsePathsJson:
    """Tests for the parse_paths_json function."""

    def test_parse_none(self):
        """Test that None returns None."""
        result = parse_paths_json(None)
        assert result is None

    def test_parse_valid_array(self):
        """Test parsing a valid JSON array."""
        result = parse_paths_json('["Album/track1.mp3", "Album/track2.mp3"]')
        assert result == ["Album/track1.mp3", "Album/track2.mp3"]

    def test_parse_empty_array(self):
        """Test parsing an empty JSON array."""
        result = parse_paths_json("[]")
        assert result == []

    def test_parse_single_element_array(self):
        """Test parsing a single-element array."""
        result = parse_paths_json('["track.mp3"]')
        assert result == ["track.mp3"]

    def test_parse_array_with_special_characters(self):
        """Test parsing array with special characters in paths."""
        result = parse_paths_json('["Artist - Album (2024)/01 - Track.flac"]')
        assert result == ["Artist - Album (2024)/01 - Track.flac"]

    def test_rejects_invalid_json(self):
        """Test that invalid JSON raises an exception."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_paths_json("not valid json")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_PATHS"

    def test_rejects_non_array_object(self):
        """Test that a JSON object is rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_paths_json('{"path": "track.mp3"}')
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_PATHS"

    def test_rejects_json_string(self):
        """Test that a JSON string is rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_paths_json('"just a string"')
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_PATHS"

    def test_rejects_json_number(self):
        """Test that a JSON number is rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_paths_json("123")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_PATHS"

    def test_rejects_array_with_non_string_elements(self):
        """Test that arrays with non-string elements are rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_paths_json('["valid.mp3", 123, "another.mp3"]')
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_PATHS"

    def test_rejects_array_with_null(self):
        """Test that arrays with null elements are rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_paths_json('["valid.mp3", null]')
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_PATHS"


class TestPathTraversalSecurity:
    """Security-focused tests for path traversal prevention."""

    @pytest.fixture
    def temp_import_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_blocks_basic_traversal(self, temp_import_dir):
        """Test blocking of basic ../path traversal."""
        with pytest.raises(ValueError):
            validate_and_sanitize_path("../file.txt", temp_import_dir)

    def test_blocks_deep_traversal(self, temp_import_dir):
        """Test blocking of deep ../../.. traversal."""
        with pytest.raises(ValueError):
            validate_and_sanitize_path("../../../../../../etc/passwd", temp_import_dir)

    def test_blocks_encoded_traversal_not_decoded(self, temp_import_dir):
        """Test that URL-encoded traversal is not automatically decoded.

        Note: URL decoding should happen at the HTTP layer, not here.
        This function receives decoded paths, so we test the actual decoded values.
        """
        # The path would be decoded by FastAPI before reaching our function
        # Test that the decoded version is blocked
        with pytest.raises(ValueError):
            validate_and_sanitize_path("../secret", temp_import_dir)

    def test_blocks_windows_style_traversal(self, temp_import_dir):
        """Test blocking of Windows-style traversal."""
        with pytest.raises(ValueError):
            validate_and_sanitize_path("..\\..\\secret.txt", temp_import_dir)

    def test_blocks_mixed_style_traversal(self, temp_import_dir):
        """Test blocking of mixed separator traversal."""
        with pytest.raises(ValueError):
            validate_and_sanitize_path("Album/..\\..\\secret.txt", temp_import_dir)

    def test_blocks_null_byte_injection(self, temp_import_dir):
        """Test blocking of null byte injection attacks."""
        with pytest.raises(ValueError, match="Null bytes"):
            validate_and_sanitize_path("file.mp3\x00.txt", temp_import_dir)

    def test_blocks_traversal_after_valid_path(self, temp_import_dir):
        """Test blocking traversal even after valid path components."""
        with pytest.raises(ValueError):
            validate_and_sanitize_path("valid/path/../../../escape", temp_import_dir)

    def test_allows_similar_looking_valid_paths(self, temp_import_dir):
        """Test that similar-looking valid paths are allowed."""
        # '...' (three dots) is a valid filename
        result = validate_and_sanitize_path("Album .../track.mp3", temp_import_dir)
        assert result == (temp_import_dir / "Album ..." / "track.mp3").resolve()

    def test_allows_dots_in_filenames(self, temp_import_dir):
        """Test that dots in filenames are allowed."""
        result = validate_and_sanitize_path("track.v2.final.mp3", temp_import_dir)
        assert result == (temp_import_dir / "track.v2.final.mp3").resolve()

    def test_allows_single_dot_segments_in_filenames(self, temp_import_dir):
        """Test that filenames containing dots are allowed."""
        result = validate_and_sanitize_path("Mr. Smith/track.mp3", temp_import_dir)
        expected = (temp_import_dir / "Mr. Smith" / "track.mp3").resolve()
        assert result == expected
