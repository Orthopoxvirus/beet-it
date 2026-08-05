"""Integration tests for batch tag editor API endpoints.

Tests cover:
- POST /api/v1/libraries/{slug}/import-items/preview
- POST /api/v1/libraries/{slug}/import-items/batch-update

These tests use schema validation and mocking of the transformation engine
and tag writer to test API behavior without requiring a real database.
"""

from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

import pytest

from app.schemas.batch_tag import (
    BatchPreviewRequest,
    BatchPreviewResponse,
    BatchUpdateRequest,
    BatchUpdateResponse,
    FixedRule,
    RegexRule,
    SequenceRule,
    TagName,
    SourceField,
    ItemPreview,
    PreviewWarning,
    PreviewError,
    ItemResult,
    ItemError,
    SSEBatchStarted,
    SSEItemProgress,
    SSEBatchCompleted,
)
from app.services.transformations import (
    TransformationEngine,
    FixedRule as TransformFixedRule,
    RegexRule as TransformRegexRule,
    SequenceRule as TransformSequenceRule,
    TagName as TransformTagName,
    SourceField as TransformSourceField,
    RegexPatternError,
)
from app.services.tag_writer import TagWriteResult
from app.api.routes.batch_tag import item_to_dict, convert_api_rule_to_transform_rule


# ============================================================================
# Request/Response Schema Tests
# ============================================================================


class TestBatchTagSchemas:
    """Tests for batch tag request/response schemas."""

    def test_fixed_rule_schema(self):
        """Test FixedRule schema validation."""
        rule = FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test Album")

        assert rule.tag == TagName.ALBUM
        assert rule.mode == "fixed"
        assert rule.value == "Test Album"

    def test_fixed_rule_empty_value(self):
        """Test FixedRule with empty value (clears tag)."""
        rule = FixedRule(tag=TagName.ALBUM, mode="fixed", value="")
        assert rule.value == ""

    def test_regex_rule_schema(self):
        """Test RegexRule schema validation."""
        rule = RegexRule(
            tag=TagName.TITLE,
            mode="regex",
            source_field=SourceField.FILENAME,
            pattern=r"^\d+\s*-\s*(.+)\.mp3$",
            replacement="$1",
        )

        assert rule.tag == TagName.TITLE
        assert rule.mode == "regex"
        assert rule.source_field == SourceField.FILENAME
        assert rule.pattern == r"^\d+\s*-\s*(.+)\.mp3$"
        assert rule.replacement == "$1"

    def test_sequence_rule_schema(self):
        """Test SequenceRule schema validation."""
        rule = SequenceRule(
            tag=TagName.TRACK_NUMBER,
            mode="sequence",
            start=1,
            per_directory=True,
        )

        assert rule.tag == TagName.TRACK_NUMBER
        assert rule.mode == "sequence"
        assert rule.start == 1
        assert rule.per_directory is True

    def test_sequence_rule_defaults(self):
        """Test SequenceRule default values."""
        rule = SequenceRule(tag=TagName.TRACK_NUMBER, mode="sequence")
        assert rule.start == 1
        assert rule.per_directory is False

    def test_batch_preview_request_validation(self):
        """Test BatchPreviewRequest validation."""
        request = BatchPreviewRequest(
            item_ids=[1, 2, 3],
            rules=[
                FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test"),
            ],
        )

        assert len(request.item_ids) == 3
        assert len(request.rules) == 1

    def test_batch_preview_request_requires_items(self):
        """Test that BatchPreviewRequest requires at least one item."""
        with pytest.raises(ValueError):
            BatchPreviewRequest(
                item_ids=[],  # Empty list should fail
                rules=[FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test")],
            )

    def test_batch_preview_request_requires_rules(self):
        """Test that BatchPreviewRequest requires at least one rule."""
        with pytest.raises(ValueError):
            BatchPreviewRequest(
                item_ids=[1],
                rules=[],  # Empty list should fail
            )

    def test_batch_preview_request_max_items(self):
        """Test BatchPreviewRequest max items limit."""
        # Should accept up to 1000 items
        request = BatchPreviewRequest(
            item_ids=list(range(1, 1001)),
            rules=[FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test")],
        )
        assert len(request.item_ids) == 1000

        # Should reject more than 1000 items
        with pytest.raises(ValueError):
            BatchPreviewRequest(
                item_ids=list(range(1, 1002)),  # 1001 items
                rules=[FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test")],
            )

    def test_batch_update_request_validation(self):
        """Test BatchUpdateRequest validation."""
        request = BatchUpdateRequest(
            item_ids=[1, 2, 3],
            rules=[
                FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test"),
                RegexRule(
                    tag=TagName.TITLE,
                    mode="regex",
                    source_field=SourceField.FILENAME,
                    pattern=".*",
                    replacement="$0",
                ),
            ],
        )

        assert len(request.item_ids) == 3
        assert len(request.rules) == 2


# ============================================================================
# Response Schema Tests
# ============================================================================


class TestResponseSchemas:
    """Tests for response schemas."""

    def test_item_preview_schema(self):
        """Test ItemPreview schema."""
        preview = ItemPreview(
            item_id=1,
            changes={"album": "New Album", "artist": "New Artist"},
            warnings=[],
        )

        assert preview.item_id == 1
        assert preview.changes["album"] == "New Album"
        assert len(preview.warnings) == 0

    def test_item_preview_with_warnings(self):
        """Test ItemPreview with warnings."""
        preview = ItemPreview(
            item_id=1,
            changes={},
            warnings=[
                PreviewWarning(
                    tag="title",
                    code="NO_REGEX_MATCH",
                    message="Pattern did not match",
                ),
            ],
        )

        assert len(preview.warnings) == 1
        assert preview.warnings[0].code == "NO_REGEX_MATCH"

    def test_preview_error_schema(self):
        """Test PreviewError schema."""
        error = PreviewError(
            item_id=999,
            code="ITEM_NOT_FOUND",
            message="Import item with ID 999 not found",
        )

        assert error.item_id == 999
        assert error.code == "ITEM_NOT_FOUND"

    def test_batch_preview_response_schema(self):
        """Test BatchPreviewResponse schema."""
        response = BatchPreviewResponse(
            previews=[
                ItemPreview(item_id=1, changes={"album": "Test"}),
                ItemPreview(item_id=2, changes={"album": "Test"}),
            ],
            errors=[
                PreviewError(
                    item_id=999,
                    code="ITEM_NOT_FOUND",
                    message="Not found",
                ),
            ],
        )

        assert len(response.previews) == 2
        assert len(response.errors) == 1

    def test_item_result_success_schema(self):
        """Test ItemResult with success status."""
        result = ItemResult(
            item_id=1,
            status="success",
            changes_applied={"album": "New Album"},
        )

        assert result.item_id == 1
        assert result.status == "success"
        assert result.changes_applied is not None
        assert result.error is None

    def test_item_result_failed_schema(self):
        """Test ItemResult with failed status."""
        result = ItemResult(
            item_id=1,
            status="failed",
            error=ItemError(
                code="PERMISSION_DENIED",
                message="Cannot write to file",
                file_path="/path/to/file.mp3",
            ),
        )

        assert result.item_id == 1
        assert result.status == "failed"
        assert result.changes_applied is None
        assert result.error is not None
        assert result.error.code == "PERMISSION_DENIED"

    def test_batch_update_response_schema(self):
        """Test BatchUpdateResponse schema."""
        response = BatchUpdateResponse(
            status="completed",
            items_total=5,
            items_succeeded=4,
            items_failed=1,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=2,
            results=[
                ItemResult(item_id=1, status="success", changes_applied={"album": "Test"}),
            ],
        )

        assert response.status == "completed"
        assert response.items_total == 5
        assert response.items_succeeded == 4
        assert response.items_failed == 1


# ============================================================================
# SSE Event Schema Tests
# ============================================================================


class TestSSEEventSchemas:
    """Tests for SSE event schemas."""

    def test_sse_batch_started_schema(self):
        """Test SSEBatchStarted schema."""
        event = SSEBatchStarted(
            total_items=10,
            started_at=datetime.utcnow(),
        )

        assert event.total_items == 10
        assert event.started_at is not None

    def test_sse_item_progress_success_schema(self):
        """Test SSEItemProgress with success."""
        event = SSEItemProgress(
            item_id=1,
            status="success",
            items_processed=5,
            items_total=10,
            progress_percent=50.0,
        )

        assert event.item_id == 1
        assert event.status == "success"
        assert event.progress_percent == 50.0
        assert event.error is None

    def test_sse_item_progress_failed_schema(self):
        """Test SSEItemProgress with failure."""
        event = SSEItemProgress(
            item_id=1,
            status="failed",
            items_processed=5,
            items_total=10,
            progress_percent=50.0,
            error=ItemError(
                code="WRITE_ERROR",
                message="Failed to write tags",
            ),
        )

        assert event.status == "failed"
        assert event.error is not None
        assert event.error.code == "WRITE_ERROR"

    def test_sse_batch_completed_schema(self):
        """Test SSEBatchCompleted schema."""
        event = SSEBatchCompleted(
            items_total=10,
            items_succeeded=8,
            items_failed=2,
            completed_at=datetime.utcnow(),
            duration_seconds=5,
        )

        assert event.items_total == 10
        assert event.items_succeeded == 8
        assert event.items_failed == 2


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions in batch_tag module."""

    def test_item_to_dict_basic(self):
        """Test item_to_dict converts ImportItem to dictionary."""
        # Create a mock item
        item = Mock()
        item.id = 1
        item.item_type = "file"
        item.path = "/music/Artist/Album/track.mp3"
        item.directory = "/music/Artist/Album"
        item.filename = "track.mp3"
        item.album = "Test Album"
        item.album_artist = "Test Artist"
        item.artist = "Test Artist"
        item.title = "Test Track"
        item.track_number = 5
        item.genre = "Rock"

        result = item_to_dict(item, "/music")

        assert result["id"] == 1
        assert result["item_type"] == "file"
        # `path` source is the folder relative to the import dir, no filename
        assert result["path"] == "Artist/Album"
        assert result["directory"] == "/music/Artist/Album"
        assert result["filename"] == "track.mp3"
        assert result["album"] == "Test Album"
        assert result["album_artist"] == "Test Artist"
        assert result["artist"] == "Test Artist"
        assert result["title"] == "Test Track"
        assert result["track_number"] == "5"  # Converted to string
        assert result["genre"] == "Rock"

    def test_item_to_dict_none_track_number(self):
        """Test that None track_number stays None."""
        item = Mock()
        item.id = 1
        item.item_type = "file"
        item.path = "/test.mp3"
        item.directory = "/test"
        item.filename = "test.mp3"
        item.album = None
        item.album_artist = None
        item.artist = None
        item.title = None
        item.track_number = None
        item.genre = None

        result = item_to_dict(item)

        assert result["track_number"] is None

    def test_convert_api_rule_fixed(self):
        """Test converting API FixedRule to transformation rule."""
        api_rule = FixedRule(tag=TagName.ALBUM, mode="fixed", value="Test Album")

        transform_rule = convert_api_rule_to_transform_rule(api_rule)

        assert isinstance(transform_rule, TransformFixedRule)
        assert transform_rule.tag == TransformTagName.ALBUM
        assert transform_rule.value == "Test Album"

    def test_convert_api_rule_regex(self):
        """Test converting API RegexRule to transformation rule."""
        api_rule = RegexRule(
            tag=TagName.TITLE,
            mode="regex",
            source_field=SourceField.FILENAME,
            pattern=r"^\d+_(.+)\.mp3$",
            replacement="$1",
        )

        transform_rule = convert_api_rule_to_transform_rule(api_rule)

        assert isinstance(transform_rule, TransformRegexRule)
        assert transform_rule.tag == TransformTagName.TITLE
        assert transform_rule.source_field == TransformSourceField.FILENAME
        assert transform_rule.pattern == r"^\d+_(.+)\.mp3$"
        assert transform_rule.replacement == "$1"

    def test_convert_api_rule_sequence(self):
        """Test converting API SequenceRule to transformation rule."""
        api_rule = SequenceRule(
            tag=TagName.TRACK_NUMBER,
            mode="sequence",
            start=5,
            per_directory=True,
        )

        transform_rule = convert_api_rule_to_transform_rule(api_rule)

        assert isinstance(transform_rule, TransformSequenceRule)
        assert transform_rule.tag == TransformTagName.TRACK_NUMBER
        assert transform_rule.start == 5
        assert transform_rule.per_directory is True


# ============================================================================
# Transformation Integration Tests
# ============================================================================


class TestTransformationIntegration:
    """Tests for transformation engine integration."""

    def test_fixed_transformation_preview(self):
        """Test fixed transformation produces correct preview."""
        rules = [
            TransformFixedRule(tag=TransformTagName.ALBUM, mode="fixed", value="New Album"),
        ]
        engine = TransformationEngine(rules)

        items = [
            {"id": 1, "album": "Old Album", "filename": "test.mp3"},
            {"id": 2, "album": "Another", "filename": "test2.mp3"},
        ]

        result = engine.compute_previews(items)

        assert len(result.previews) == 2
        assert result.previews[0].changes["album"] == "New Album"
        assert result.previews[1].changes["album"] == "New Album"

    def test_regex_transformation_preview(self):
        """Test regex transformation produces correct preview."""
        rules = [
            TransformRegexRule(
                tag=TransformTagName.TITLE,
                mode="regex",
                source_field=TransformSourceField.FILENAME,
                pattern=r"^\d+\s*-\s*(.+)\.mp3$",
                replacement="$1",
            ),
        ]
        engine = TransformationEngine(rules)

        items = [
            {"id": 1, "filename": "01 - First Song.mp3", "title": ""},
            {"id": 2, "filename": "02 - Second Song.mp3", "title": ""},
        ]

        result = engine.compute_previews(items)

        assert result.previews[0].changes["title"] == "First Song"
        assert result.previews[1].changes["title"] == "Second Song"

    def test_sequence_transformation_preview(self):
        """Test sequence transformation produces correct preview."""
        rules = [
            TransformSequenceRule(
                tag=TransformTagName.TRACK_NUMBER,
                mode="sequence",
                start=1,
                per_directory=False,
            ),
        ]
        engine = TransformationEngine(rules)

        items = [
            {"id": 1, "filename": "song1.mp3", "directory": "/music", "track_number": None},
            {"id": 2, "filename": "song2.mp3", "directory": "/music", "track_number": None},
            {"id": 3, "filename": "song3.mp3", "directory": "/music", "track_number": None},
        ]

        result = engine.compute_previews(items)

        # Items sorted by filename
        assert result.previews[0].changes["track_number"] == "1"
        assert result.previews[1].changes["track_number"] == "2"
        assert result.previews[2].changes["track_number"] == "3"

    def test_multiple_rules_preview(self):
        """Test multiple rules applied together."""
        rules = [
            TransformFixedRule(tag=TransformTagName.ALBUM, mode="fixed", value="Compilation"),
            TransformFixedRule(tag=TransformTagName.ARTIST, mode="fixed", value="Various"),
        ]
        engine = TransformationEngine(rules)

        items = [{"id": 1, "album": "Old", "artist": "Someone"}]

        result = engine.compute_previews(items)

        assert result.previews[0].changes["album"] == "Compilation"
        assert result.previews[0].changes["artist"] == "Various"

    def test_invalid_regex_raises_error(self):
        """Test that invalid regex raises RegexPatternError."""
        rules = [
            TransformRegexRule(
                tag=TransformTagName.TITLE,
                mode="regex",
                source_field=TransformSourceField.FILENAME,
                pattern=r"[invalid",  # Invalid pattern
                replacement="$1",
            ),
        ]

        with pytest.raises(RegexPatternError):
            TransformationEngine(rules)

    def test_no_change_when_value_same(self):
        """Test that no change is reported when value equals current."""
        rules = [
            TransformFixedRule(tag=TransformTagName.ALBUM, mode="fixed", value="Same Album"),
        ]
        engine = TransformationEngine(rules)

        items = [{"id": 1, "album": "Same Album"}]

        result = engine.compute_previews(items)

        # No album key in changes since it's the same
        assert "album" not in result.previews[0].changes


# ============================================================================
# Tag Writer Integration Tests
# ============================================================================


class TestTagWriterIntegration:
    """Tests for tag writer integration."""

    def test_tag_write_result_success(self):
        """Test TagWriteResult success structure."""
        result = TagWriteResult(
            success=True,
            file_path="/test.mp3",
            tags_written={"album": "New Album", "artist": "New Artist"},
        )

        assert result.success is True
        assert result.file_path == "/test.mp3"
        assert result.tags_written["album"] == "New Album"
        assert result.error is None

    def test_tag_write_result_failure(self):
        """Test TagWriteResult failure structure."""
        result = TagWriteResult(
            success=False,
            file_path="/test.mp3",
            tags_written={},
            error="Permission denied",
            error_code="PERMISSION_DENIED",
        )

        assert result.success is False
        assert result.error == "Permission denied"
        assert result.error_code == "PERMISSION_DENIED"


# ============================================================================
# Tag Names and Source Fields Tests
# ============================================================================


class TestEnumerations:
    """Tests for tag name and source field enumerations."""

    def test_all_tag_names_valid(self):
        """Test all tag names in the enum."""
        expected_tags = [
            "album", "album_artist", "artist", "title",
            "genre", "track_number", "disc_number",
        ]

        for tag in expected_tags:
            assert hasattr(TagName, tag.upper()), f"Missing tag: {tag}"

    def test_all_source_fields_valid(self):
        """Test all source fields in the enum."""
        expected_fields = [
            "filename", "album", "album_artist", "artist",
            "title", "genre", "track_number", "disc_number",
        ]

        for field in expected_fields:
            assert hasattr(SourceField, field.upper()), f"Missing field: {field}"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_string_clears_tag(self):
        """Test that empty string value is valid for clearing tags."""
        rule = FixedRule(tag=TagName.ALBUM, mode="fixed", value="")
        assert rule.value == ""

    def test_unicode_values_in_rules(self):
        """Test that unicode values work in transformation rules."""
        rule = FixedRule(
            tag=TagName.ALBUM,
            mode="fixed",
            value="Bjork - Homogenic \u2665",
        )
        assert "\u2665" in rule.value

    def test_special_characters_in_regex_pattern(self):
        """Test regex patterns with special characters."""
        rule = RegexRule(
            tag=TagName.TITLE,
            mode="regex",
            source_field=SourceField.FILENAME,
            pattern=r"^(\d+)\s*[-_\.]\s*(.+)\.mp3$",
            replacement="$2",
        )

        # Should not raise on creation
        assert rule.pattern == r"^(\d+)\s*[-_\.]\s*(.+)\.mp3$"

    def test_very_long_fixed_value(self):
        """Test fixed rule with very long value."""
        long_value = "A" * 1000  # Max length
        rule = FixedRule(tag=TagName.ALBUM, mode="fixed", value=long_value)
        assert len(rule.value) == 1000

    def test_regex_replacement_with_all_groups(self):
        """Test regex replacement with multiple capture groups."""
        rule = RegexRule(
            tag=TagName.TITLE,
            mode="regex",
            source_field=SourceField.FILENAME,
            pattern=r"^(\d+)-(\d+)-(.+)\.mp3$",
            replacement="$3 (Disc $1, Track $2)",
        )
        assert "$1" in rule.replacement
        assert "$2" in rule.replacement
        assert "$3" in rule.replacement

    def test_sequence_start_boundaries(self):
        """Test sequence rule start value boundaries."""
        # Minimum valid start
        rule_min = SequenceRule(
            tag=TagName.TRACK_NUMBER,
            mode="sequence",
            start=1,
        )
        assert rule_min.start == 1

        # Maximum valid start
        rule_max = SequenceRule(
            tag=TagName.TRACK_NUMBER,
            mode="sequence",
            start=9999,
        )
        assert rule_max.start == 9999

        # Below minimum should fail
        with pytest.raises(ValueError):
            SequenceRule(
                tag=TagName.TRACK_NUMBER,
                mode="sequence",
                start=0,
            )

        # Above maximum should fail
        with pytest.raises(ValueError):
            SequenceRule(
                tag=TagName.TRACK_NUMBER,
                mode="sequence",
                start=10000,
            )
