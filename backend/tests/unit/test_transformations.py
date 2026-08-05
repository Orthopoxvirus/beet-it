"""Unit tests for transformation engine (all modes and edge cases).

Tests cover:
- FixedTransformer: constant value replacement
- RegexTransformer: pattern matching with capture groups
- SequenceTransformer: auto-numbering with per-directory grouping
- TransformationEngine: orchestration of multiple rules
"""

import signal
import sys
from unittest.mock import patch, MagicMock

import pytest

from app.services.transformations import (
    TransformationEngine,
    FixedTransformer,
    FixedTransformResult,
    RegexTransformer,
    RegexTransformResult,
    RegexTimeoutError,
    RegexPatternError,
    SequenceTransformer,
    SequenceTransformResult,
    ExplicitTransformer,
    ExplicitTransformResult,
    FixedRule,
    RegexRule,
    SequenceRule,
    ExplicitRule,
    TagName,
    SourceField,
    validate_regex_pattern,
)


# ============================================================================
# FixedTransformer Tests
# ============================================================================


class TestFixedTransformer:
    """Tests for the FixedTransformer class."""

    def test_returns_fixed_value(self):
        """Test that transformer returns the configured fixed value."""
        transformer = FixedTransformer("Greatest Hits")
        result = transformer.transform({"id": 1, "album": "Old Album"})

        assert result.success is True
        assert result.value == "Greatest Hits"
        assert result.error is None

    def test_returns_empty_string_to_clear_tag(self):
        """Test that empty string clears the tag."""
        transformer = FixedTransformer("")
        result = transformer.transform({"id": 1, "album": "Some Album"})

        assert result.success is True
        assert result.value == ""

    def test_ignores_item_data(self):
        """Test that fixed transformer ignores the actual item data."""
        transformer = FixedTransformer("Fixed Value")

        # Same result regardless of input
        result1 = transformer.transform({"id": 1})
        result2 = transformer.transform({"id": 2, "album": "Different"})
        result3 = transformer.transform({})

        assert result1.value == result2.value == result3.value == "Fixed Value"

    def test_handles_special_characters(self):
        """Test that special characters are preserved."""
        special_value = "Album: The \"Special\" One! (2024)"
        transformer = FixedTransformer(special_value)
        result = transformer.transform({"id": 1})

        assert result.value == special_value

    def test_handles_unicode(self):
        """Test that unicode characters are preserved."""
        unicode_value = "Bjork - Homogenic \u2665 \u00e9\u00e8\u00ea"
        transformer = FixedTransformer(unicode_value)
        result = transformer.transform({"id": 1})

        assert result.value == unicode_value


# ============================================================================
# RegexTransformer Tests
# ============================================================================


class TestRegexTransformer:
    """Tests for the RegexTransformer class."""

    def test_basic_pattern_match(self):
        """Test basic pattern matching."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="$2",
        )
        result = transformer.transform({
            "id": 1,
            "filename": "01 - My Song.mp3",
        })

        assert result.success is True
        assert result.value == "My Song"

    def test_capture_group_substitution(self):
        """Test $1, $2, etc. capture group substitution."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="Track $1: $2",
        )
        result = transformer.transform({
            "id": 1,
            "filename": "05 - Awesome Song.mp3",
        })

        assert result.success is True
        assert result.value == "Track 05: Awesome Song"

    def test_entire_match_with_dollar_zero(self):
        """Test $0 substitution for entire match."""
        transformer = RegexTransformer(
            source_field="title",
            pattern=r".*",
            replacement="[$0]",
        )
        result = transformer.transform({
            "id": 1,
            "title": "My Song",
        })

        assert result.success is True
        assert result.value == "[My Song]"

    def test_no_match_returns_warning(self):
        """Test that no match returns warning with NO_REGEX_MATCH code."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="$2",
        )
        result = transformer.transform({
            "id": 1,
            "filename": "not-matching.flac",
        })

        assert result.success is True
        assert result.value is None
        assert result.warning_code == "NO_REGEX_MATCH"
        assert "Pattern did not match" in result.warning

    def test_empty_source_field_returns_warning(self):
        """Test that empty source field returns EMPTY_SOURCE warning."""
        transformer = RegexTransformer(
            source_field="album",
            pattern=r".*",
            replacement="$0",
        )

        # Test with None
        result = transformer.transform({"id": 1, "album": None})
        assert result.warning_code == "EMPTY_SOURCE"

        # Test with empty string
        result = transformer.transform({"id": 1, "album": ""})
        assert result.warning_code == "EMPTY_SOURCE"

    def test_missing_source_field_returns_warning(self):
        """Test that missing source field returns EMPTY_SOURCE warning."""
        transformer = RegexTransformer(
            source_field="nonexistent",
            pattern=r".*",
            replacement="$0",
        )
        result = transformer.transform({"id": 1})

        assert result.warning_code == "EMPTY_SOURCE"

    def test_invalid_pattern_raises_error(self):
        """Test that invalid regex pattern raises RegexPatternError."""
        with pytest.raises(RegexPatternError):
            RegexTransformer(
                source_field="filename",
                pattern=r"[invalid",  # Unclosed bracket
                replacement="$1",
            )

    def test_optional_capture_groups(self):
        """Test handling of optional (non-matching) capture groups."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)?(.+)\.mp3$",
            replacement="$1-$2",
        )
        # Pattern where $1 doesn't match
        result = transformer.transform({
            "id": 1,
            "filename": "song.mp3",
        })

        assert result.success is True
        # Empty string for non-matching group
        assert result.value == "-song"

    def test_converts_non_string_source_to_string(self):
        """Test that numeric source values are converted to strings."""
        transformer = RegexTransformer(
            source_field="track_number",
            pattern=r"(\d+)",
            replacement="Track $1",
        )
        result = transformer.transform({
            "id": 1,
            "track_number": 5,
        })

        assert result.success is True
        assert result.value == "Track 5"

    def test_uses_different_source_fields(self):
        """Test regex can use different source fields."""
        pattern = r"^(.+)$"
        replacement = "$1"

        # Test with filename
        t1 = RegexTransformer("filename", pattern, replacement)
        r1 = t1.transform({"id": 1, "filename": "song.mp3"})
        assert r1.value == "song.mp3"

        # Test with album
        t2 = RegexTransformer("album", pattern, replacement)
        r2 = t2.transform({"id": 1, "album": "Best Album"})
        assert r2.value == "Best Album"

        # Test with artist
        t3 = RegexTransformer("artist", pattern, replacement)
        r3 = t3.transform({"id": 1, "artist": "Cool Band"})
        assert r3.value == "Cool Band"


class TestRegexTransformerTimeout:
    """Tests for regex timeout protection."""

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM") or sys.platform == "win32",
        reason="SIGALRM not available on this platform"
    )
    def test_timeout_protection_is_active(self):
        """Test that timeout mechanism is properly set up on Unix."""
        from app.services.transformations.regex import _SUPPORTS_SIGALRM

        assert _SUPPORTS_SIGALRM is True

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM") or sys.platform == "win32",
        reason="SIGALRM not available on this platform"
    )
    def test_signal_handler_is_restored_after_success(self):
        """Test that the original signal handler is restored after success."""
        original_handler = signal.getsignal(signal.SIGALRM)

        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=1000,
        )
        transformer.transform({"id": 1, "filename": "test.mp3"})

        # Handler should be restored
        assert signal.getsignal(signal.SIGALRM) == original_handler

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM") or sys.platform == "win32",
        reason="SIGALRM not available on this platform"
    )
    def test_timeout_raises_regex_timeout_error(self):
        """Test that RegexTimeoutError is raised on timeout."""
        from app.services.transformations.regex import _timeout_handler

        # Directly trigger the timeout handler
        with pytest.raises(RegexTimeoutError):
            _timeout_handler(signal.SIGALRM, None)


class TestValidateRegexPattern:
    """Tests for the validate_regex_pattern function."""

    def test_valid_patterns(self):
        """Test that valid patterns pass validation."""
        valid_patterns = [
            r"^.*$",
            r"(\d+)",
            r"[a-zA-Z]+",
            r"foo|bar",
            r"^\d{2}-(.+)\.mp3$",
        ]
        for pattern in valid_patterns:
            is_valid, error = validate_regex_pattern(pattern)
            assert is_valid is True, f"Pattern {pattern} should be valid"
            assert error is None

    def test_invalid_patterns(self):
        """Test that invalid patterns fail validation."""
        invalid_patterns = [
            r"[invalid",  # Unclosed bracket
            r"(unclosed",  # Unclosed paren
            r"*invalid",  # Invalid quantifier
        ]
        for pattern in invalid_patterns:
            is_valid, error = validate_regex_pattern(pattern)
            assert is_valid is False, f"Pattern {pattern} should be invalid"
            assert error is not None


# ============================================================================
# SequenceTransformer Tests
# ============================================================================


class TestSequenceTransformer:
    """Tests for the SequenceTransformer class."""

    def test_basic_sequential_numbering(self):
        """Test basic sequential numbering starting from 1."""
        items = [
            {"id": 1, "filename": "c_song.mp3", "directory": "/music"},
            {"id": 2, "filename": "a_song.mp3", "directory": "/music"},
            {"id": 3, "filename": "b_song.mp3", "directory": "/music"},
        ]
        transformer = SequenceTransformer(items, start=1, per_directory=False)

        # Items are sorted by directory then filename
        # So order is: a_song (id=2), b_song (id=3), c_song (id=1)
        assert transformer.transform({"id": 2}).value == "1"  # a_song
        assert transformer.transform({"id": 3}).value == "2"  # b_song
        assert transformer.transform({"id": 1}).value == "3"  # c_song

    def test_custom_start_value(self):
        """Test sequential numbering with custom start value."""
        items = [
            {"id": 1, "filename": "song1.mp3", "directory": "/music"},
            {"id": 2, "filename": "song2.mp3", "directory": "/music"},
        ]
        transformer = SequenceTransformer(items, start=5, per_directory=False)

        assert transformer.transform({"id": 1}).value == "5"
        assert transformer.transform({"id": 2}).value == "6"

    def test_per_directory_numbering(self):
        """Test that per_directory restarts numbering for each directory."""
        items = [
            {"id": 1, "filename": "track1.mp3", "directory": "/music/album1"},
            {"id": 2, "filename": "track2.mp3", "directory": "/music/album1"},
            {"id": 3, "filename": "track1.mp3", "directory": "/music/album2"},
            {"id": 4, "filename": "track2.mp3", "directory": "/music/album2"},
        ]
        transformer = SequenceTransformer(items, start=1, per_directory=True)

        # Album1 tracks
        assert transformer.transform({"id": 1}).value == "1"
        assert transformer.transform({"id": 2}).value == "2"
        # Album2 tracks - numbering restarts
        assert transformer.transform({"id": 3}).value == "1"
        assert transformer.transform({"id": 4}).value == "2"

    def test_per_directory_with_custom_start(self):
        """Test per_directory with custom start value."""
        items = [
            {"id": 1, "filename": "track1.mp3", "directory": "/album1"},
            {"id": 2, "filename": "track2.mp3", "directory": "/album1"},
            {"id": 3, "filename": "track1.mp3", "directory": "/album2"},
        ]
        transformer = SequenceTransformer(items, start=10, per_directory=True)

        assert transformer.transform({"id": 1}).value == "10"
        assert transformer.transform({"id": 2}).value == "11"
        assert transformer.transform({"id": 3}).value == "10"  # Restarts at 10

    def test_sorted_by_filename_within_directory(self):
        """Test that items are sorted by filename within each directory."""
        items = [
            {"id": 1, "filename": "03_song.mp3", "directory": "/album"},
            {"id": 2, "filename": "01_song.mp3", "directory": "/album"},
            {"id": 3, "filename": "02_song.mp3", "directory": "/album"},
        ]
        transformer = SequenceTransformer(items, start=1, per_directory=True)

        # Sorted by filename: 01_song (2), 02_song (3), 03_song (1)
        assert transformer.transform({"id": 2}).value == "1"  # 01_song
        assert transformer.transform({"id": 3}).value == "2"  # 02_song
        assert transformer.transform({"id": 1}).value == "3"  # 03_song

    def test_item_without_id_returns_error(self):
        """Test that items without ID return error."""
        items = [{"id": 1, "filename": "song.mp3", "directory": "/music"}]
        transformer = SequenceTransformer(items, start=1)

        result = transformer.transform({"filename": "song.mp3"})  # No id
        assert result.success is False
        assert "no ID" in result.error

    def test_unknown_item_returns_error(self):
        """Test that unknown items return error."""
        items = [{"id": 1, "filename": "song.mp3", "directory": "/music"}]
        transformer = SequenceTransformer(items, start=1)

        result = transformer.transform({"id": 999})  # Unknown id
        assert result.success is False
        assert "not found" in result.error

    def test_get_sequence_number_method(self):
        """Test the get_sequence_number helper method."""
        items = [
            {"id": 1, "filename": "song1.mp3", "directory": "/music"},
            {"id": 2, "filename": "song2.mp3", "directory": "/music"},
        ]
        transformer = SequenceTransformer(items, start=1)

        assert transformer.get_sequence_number(1) == 1
        assert transformer.get_sequence_number(2) == 2
        assert transformer.get_sequence_number(999) is None

    def test_empty_directory_handled(self):
        """Test that empty/None directory is handled."""
        items = [
            {"id": 1, "filename": "song1.mp3", "directory": ""},
            {"id": 2, "filename": "song2.mp3", "directory": None},
        ]
        transformer = SequenceTransformer(items, start=1, per_directory=True)

        # Both treated as same empty directory
        result1 = transformer.transform({"id": 1})
        result2 = transformer.transform({"id": 2})
        assert result1.success is True
        assert result2.success is True

    def test_case_insensitive_filename_sorting(self):
        """Test that filename sorting is case-insensitive."""
        items = [
            {"id": 1, "filename": "BETA.mp3", "directory": "/album"},
            {"id": 2, "filename": "alpha.mp3", "directory": "/album"},
            {"id": 3, "filename": "Charlie.mp3", "directory": "/album"},
        ]
        transformer = SequenceTransformer(items, start=1, per_directory=True)

        # Case-insensitive sort: alpha, BETA, Charlie
        assert transformer.transform({"id": 2}).value == "1"  # alpha
        assert transformer.transform({"id": 1}).value == "2"  # BETA
        assert transformer.transform({"id": 3}).value == "3"  # Charlie


# ============================================================================
# TransformationEngine Tests
# ============================================================================


class TestTransformationEngine:
    """Tests for the TransformationEngine class."""

    def test_single_fixed_rule(self):
        """Test engine with a single fixed rule."""
        rules = [
            FixedRule(tag=TagName.ALBUM, mode="fixed", value="Greatest Hits"),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "album": "Old Album"},
            {"id": 2, "album": "Another Album"},
        ]

        result = engine.compute_previews(items)

        assert len(result.previews) == 2
        assert result.previews[0].changes["album"] == "Greatest Hits"
        assert result.previews[1].changes["album"] == "Greatest Hits"

    def test_multiple_rules_applied_together(self):
        """Test engine applies multiple rules to each item."""
        rules = [
            FixedRule(tag=TagName.ALBUM, mode="fixed", value="Hits"),
            FixedRule(tag=TagName.ARTIST, mode="fixed", value="Various"),
        ]
        engine = TransformationEngine(rules)
        items = [{"id": 1, "album": "Old", "artist": "Someone"}]

        result = engine.compute_previews(items)

        assert result.previews[0].changes["album"] == "Hits"
        assert result.previews[0].changes["artist"] == "Various"

    def test_regex_rule(self):
        """Test engine with regex rule."""
        rules = [
            RegexRule(
                tag=TagName.TITLE,
                mode="regex",
                source_field=SourceField.FILENAME,
                pattern=r"^\d+\s*-\s*(.+)\.mp3$",
                replacement="$1",
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "filename": "01 - My Song.mp3", "title": ""},
            {"id": 2, "filename": "02 - Other Song.mp3", "title": ""},
        ]

        result = engine.compute_previews(items)

        assert result.previews[0].changes["title"] == "My Song"
        assert result.previews[1].changes["title"] == "Other Song"

    def test_regex_rule_path_source(self):
        """Test engine with a regex rule reading the `path` source field."""
        rules = [
            RegexRule(
                tag=TagName.ALBUM,
                mode="regex",
                source_field=SourceField.PATH,
                pattern=r"^[^/]+/(.+)$",
                replacement="$1",
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "path": "Artist/Greatest Hits", "album": ""},
        ]

        result = engine.compute_previews(items)

        assert result.previews[0].changes["album"] == "Greatest Hits"

    def test_sequence_rule(self):
        """Test engine with sequence rule."""
        rules = [
            SequenceRule(
                tag=TagName.TRACK_NUMBER,
                mode="sequence",
                start=1,
                per_directory=False,
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "filename": "song1.mp3", "directory": "/music", "track_number": None},
            {"id": 2, "filename": "song2.mp3", "directory": "/music", "track_number": None},
        ]

        result = engine.compute_previews(items)

        # Sorted by filename, so song1 is first
        assert result.previews[0].changes["track_number"] == "1"
        assert result.previews[1].changes["track_number"] == "2"

    def test_no_change_when_value_same(self):
        """Test that no change is reported when value is same as current."""
        rules = [
            FixedRule(tag=TagName.ALBUM, mode="fixed", value="Same Album"),
        ]
        engine = TransformationEngine(rules)
        items = [{"id": 1, "album": "Same Album"}]

        result = engine.compute_previews(items)

        # No changes since value is already the same
        assert "album" not in result.previews[0].changes

    def test_invalid_regex_raises_error_on_init(self):
        """Test that invalid regex raises error during engine initialization."""
        rules = [
            RegexRule(
                tag=TagName.TITLE,
                mode="regex",
                source_field=SourceField.FILENAME,
                pattern=r"[invalid",  # Invalid pattern
                replacement="$1",
            ),
        ]

        with pytest.raises(RegexPatternError):
            TransformationEngine(rules)

    def test_warnings_included_in_result(self):
        """Test that warnings are included in item results."""
        rules = [
            RegexRule(
                tag=TagName.TITLE,
                mode="regex",
                source_field=SourceField.FILENAME,
                pattern=r"^\d+\s*-\s*(.+)\.mp3$",
                replacement="$1",
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "filename": "not-matching.flac", "title": ""},  # Won't match
        ]

        result = engine.compute_previews(items)

        assert len(result.previews[0].warnings) == 1
        assert result.previews[0].warnings[0].code == "NO_REGEX_MATCH"

    def test_items_without_id_reported_as_errors(self):
        """Test that items without ID are reported as errors."""
        rules = [
            FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test"),
        ]
        engine = TransformationEngine(rules)
        items = [{"album": "Old Album"}]  # No id field

        result = engine.compute_previews(items)

        assert len(result.errors) == 1
        assert result.errors[0].code == "MISSING_ID"

    def test_mixed_rules_all_types(self):
        """Test engine with all three rule types together."""
        rules = [
            FixedRule(tag=TagName.ALBUM, mode="fixed", value="Compilation"),
            RegexRule(
                tag=TagName.TITLE,
                mode="regex",
                source_field=SourceField.FILENAME,
                pattern=r"^\d+_(.+)\.mp3$",
                replacement="$1",
            ),
            SequenceRule(
                tag=TagName.TRACK_NUMBER,
                mode="sequence",
                start=1,
                per_directory=True,
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {
                "id": 1,
                "filename": "01_First.mp3",
                "directory": "/album",
                "album": "Old",
                "title": "",
                "track_number": None,
            },
            {
                "id": 2,
                "filename": "02_Second.mp3",
                "directory": "/album",
                "album": "Old",
                "title": "",
                "track_number": None,
            },
        ]

        result = engine.compute_previews(items)

        # First item
        assert result.previews[0].changes["album"] == "Compilation"
        assert result.previews[0].changes["title"] == "First"
        assert result.previews[0].changes["track_number"] == "1"

        # Second item
        assert result.previews[1].changes["album"] == "Compilation"
        assert result.previews[1].changes["title"] == "Second"
        assert result.previews[1].changes["track_number"] == "2"


# ============================================================================
# Edge Cases
# ============================================================================


class TestTransformationEdgeCases:
    """Tests for edge cases in transformations."""

    def test_empty_items_list(self):
        """Test transformation with empty items list."""
        rules = [FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test")]
        engine = TransformationEngine(rules)

        result = engine.compute_previews([])

        assert len(result.previews) == 0
        assert len(result.errors) == 0

    def test_empty_rules_list(self):
        """Test transformation with no rules."""
        engine = TransformationEngine([])
        items = [{"id": 1, "album": "Test"}]

        result = engine.compute_previews(items)

        # No changes since no rules
        assert len(result.previews) == 1
        assert result.previews[0].changes == {}

    def test_regex_with_many_capture_groups(self):
        """Test regex with many capture groups.

        Note: The simple $N replacement approach interprets $10 as $1 + "0",
        not as capture group 10. This is a known limitation.
        """
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(.)-(.)-(.)-(.)-(.)-(.)-(.)-(.)-(.)-(.+)\.mp3$",
            replacement="$1$2$3$4$5$6$7$8$9",  # Only use groups 1-9
        )
        result = transformer.transform({
            "id": 1,
            "filename": "a-b-c-d-e-f-g-h-i-rest.mp3",
        })

        assert result.success is True
        assert result.value == "abcdefghi"

    def test_sequence_with_single_item(self):
        """Test sequence transformer with single item."""
        items = [{"id": 1, "filename": "song.mp3", "directory": "/music"}]
        transformer = SequenceTransformer(items, start=1)

        result = transformer.transform({"id": 1})
        assert result.value == "1"

    def test_fixed_with_very_long_value(self):
        """Test fixed transformer with very long value."""
        long_value = "A" * 1000
        transformer = FixedTransformer(long_value)
        result = transformer.transform({"id": 1})

        assert result.value == long_value

    def test_null_vs_empty_string_handling(self):
        """Test distinction between null and empty string values."""
        rules = [FixedRule(tag=TagName.ALBUM, mode="fixed", value="New Album")]
        engine = TransformationEngine(rules)

        # Item with None value
        result1 = engine.compute_previews([{"id": 1, "album": None}])
        assert result1.previews[0].changes["album"] == "New Album"

        # Item with empty string value
        result2 = engine.compute_previews([{"id": 2, "album": ""}])
        assert result2.previews[0].changes["album"] == "New Album"

    def test_numeric_tag_conversion(self):
        """Test that numeric values are properly converted."""
        rules = [FixedRule(tag=TagName.TRACK_NUMBER, mode="fixed", value="5")]
        engine = TransformationEngine(rules)
        items = [{"id": 1, "track_number": 5}]  # Current value is integer

        result = engine.compute_previews(items)

        # No change since "5" == str(5)
        assert "track_number" not in result.previews[0].changes

    def test_sequence_filters_file_items_only(self):
        """Test that sequence transformer filters to file items only."""
        rules = [
            SequenceRule(tag=TagName.TRACK_NUMBER, mode="sequence", start=1),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "item_type": "folder", "filename": "Album", "directory": "/", "track_number": None},
            {"id": 2, "item_type": "file", "filename": "song1.mp3", "directory": "/Album", "track_number": None},
            {"id": 3, "item_type": "file", "filename": "song2.mp3", "directory": "/Album", "track_number": None},
        ]

        result = engine.compute_previews(items)

        # Folder should have no track number change (or error)
        # Files should be numbered
        file_results = [p for p in result.previews if p.item_id in [2, 3]]
        assert len([r for r in file_results if "track_number" in r.changes]) == 2


# ============================================================================
# ExplicitTransformer Tests
# ============================================================================


class TestExplicitTransformer:
    """Tests for the ExplicitTransformer (per-item value assignment)."""

    def test_returns_mapped_value(self):
        """An item present in the map gets its explicit value."""
        transformer = ExplicitTransformer(values={1: "3", 2: "1"})
        result = transformer.transform({"id": 1})
        assert result.success is True
        assert result.value == "3"

    def test_item_absent_from_map_yields_no_value(self):
        """An item not in the map emits no value (no change)."""
        transformer = ExplicitTransformer(values={1: "3"})
        result = transformer.transform({"id": 99})
        assert result.success is True
        assert result.value is None

    def test_missing_id_is_an_error(self):
        """An item without an id is a failure, not a silent skip."""
        transformer = ExplicitTransformer(values={1: "3"})
        result = transformer.transform({})
        assert result.success is False
        assert result.value is None
        assert result.error is not None


class TestExplicitRuleEngine:
    """Engine-level behaviour for explicit rules (the reorder commit path)."""

    def test_reorder_track_numbers(self):
        """Explicit track numbers are applied per item, only where they change."""
        # Move track 3 to the front: each track adopts its new slot's number.
        rules = [
            ExplicitRule(
                tag=TagName.TRACK_NUMBER,
                mode="explicit",
                values={1: "2", 2: "3", 3: "1"},
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "track_number": "1", "title": "A"},
            {"id": 2, "track_number": "2", "title": "B"},
            {"id": 3, "track_number": "3", "title": "C"},
        ]

        result = engine.compute_previews(items)
        by_id = {p.item_id: p.changes for p in result.previews}
        assert by_id[1]["track_number"] == "2"
        assert by_id[2]["track_number"] == "3"
        assert by_id[3]["track_number"] == "1"

    def test_unchanged_value_produces_no_change(self):
        """An explicit value equal to the current one is dropped (no no-op writes)."""
        rules = [
            ExplicitRule(
                tag=TagName.TRACK_NUMBER,
                mode="explicit",
                values={1: "1", 2: "5"},
            ),
        ]
        engine = TransformationEngine(rules)
        items = [
            {"id": 1, "track_number": "1"},  # already 1 -> no change
            {"id": 2, "track_number": "2"},  # 2 -> 5
        ]

        result = engine.compute_previews(items)
        by_id = {p.item_id: p.changes for p in result.previews}
        assert "track_number" not in by_id[1]
        assert by_id[2]["track_number"] == "5"

    def test_keep_titles_writes_both_tags(self):
        """A reorder with 'keep titles' on commits track_number and title rules."""
        rules = [
            ExplicitRule(
                tag=TagName.TRACK_NUMBER, mode="explicit", values={3: "1"}
            ),
            ExplicitRule(tag=TagName.TITLE, mode="explicit", values={3: "A"}),
        ]
        engine = TransformationEngine(rules)
        items = [{"id": 3, "track_number": "3", "title": "C"}]

        result = engine.compute_previews(items)
        changes = result.previews[0].changes
        assert changes["track_number"] == "1"
        assert changes["title"] == "A"

    def test_string_keys_are_coerced_to_int(self):
        """JSON object keys (strings) coerce to int item ids on the schema model."""
        rule = ExplicitRule(
            tag=TagName.TRACK_NUMBER,
            mode="explicit",
            values={"1": "2"},  # type: ignore[dict-item]
        )
        assert rule.values == {1: "2"}
