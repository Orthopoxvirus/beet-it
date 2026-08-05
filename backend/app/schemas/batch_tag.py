"""Pydantic schemas for the batch tag editor API.

This module defines the request and response schemas for the preview
and batch-update endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ============================================================================
# Enums and Types
# ============================================================================


class TransformationMode(str, Enum):
    """Supported transformation modes."""

    FIXED = "fixed"
    REGEX = "regex"
    SEQUENCE = "sequence"
    EXPLICIT = "explicit"


class TagName(str, Enum):
    """Canonical tag names supported for transformation."""

    ALBUM = "album"
    ALBUM_ARTIST = "album_artist"
    ARTIST = "artist"
    TITLE = "title"
    GENRE = "genre"
    TRACK_NUMBER = "track_number"
    DISC_NUMBER = "disc_number"


class SourceField(str, Enum):
    """Valid source fields for regex transformations."""

    FILENAME = "filename"
    PATH = "path"
    ALBUM = "album"
    ALBUM_ARTIST = "album_artist"
    ARTIST = "artist"
    TITLE = "title"
    GENRE = "genre"
    TRACK_NUMBER = "track_number"
    DISC_NUMBER = "disc_number"


# ============================================================================
# Transformation Rules
# ============================================================================


class FixedRule(BaseModel):
    """Replace a tag with a fixed constant value."""

    tag: TagName = Field(..., description="Tag to modify")
    mode: Literal["fixed"] = Field("fixed", description="Transformation mode")
    value: str = Field(
        ...,
        max_length=1000,
        description="Fixed value to set. Empty string clears the tag.",
    )


class RegexRule(BaseModel):
    """Apply regex transformation with capture group substitution."""

    tag: TagName = Field(..., description="Tag to modify")
    mode: Literal["regex"] = Field("regex", description="Transformation mode")
    source_field: SourceField = Field(
        ...,
        description="Field to apply regex pattern to",
    )
    pattern: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Python-compatible regex pattern",
    )
    replacement: str = Field(
        ...,
        max_length=500,
        description="Replacement template with capture groups ($1, $2, etc.)",
    )


class SequenceRule(BaseModel):
    """Auto-number tracks sequentially."""

    tag: Literal[TagName.TRACK_NUMBER] = Field(
        TagName.TRACK_NUMBER,
        description="Tag to modify (must be track_number)",
    )
    mode: Literal["sequence"] = Field("sequence", description="Transformation mode")
    start: int = Field(
        1,
        ge=1,
        le=9999,
        description="Starting number for the sequence",
    )
    per_directory: bool = Field(
        False,
        description="If true, restart numbering for each directory",
    )


class ExplicitRule(BaseModel):
    """Assign explicit per-item values for a tag.

    Carries a ``item_id -> value`` map computed by the client (the drag
    reorder UI). Items not present in the map are left unchanged. Used to
    commit a manual track reorder exactly as previewed.
    """

    tag: TagName = Field(..., description="Tag to modify")
    mode: Literal["explicit"] = Field("explicit", description="Transformation mode")
    values: Dict[int, str] = Field(
        ...,
        max_length=50000,
        description="Map of beets item ID to the explicit value to set for this tag.",
    )


# Discriminated union type for transformation rules
TransformationRule = Annotated[
    Union[FixedRule, RegexRule, SequenceRule, ExplicitRule],
    Field(discriminator="mode"),
]


# ============================================================================
# Request Schemas
# ============================================================================


class BatchPreviewRequest(BaseModel):
    """Request body for previewing tag transformations."""

    item_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of import item IDs to preview transformations for",
    )
    rules: List[TransformationRule] = Field(
        ...,
        min_length=1,
        description="List of transformation rules to apply",
    )


class BatchUpdateRequest(BaseModel):
    """Request body for applying tag transformations."""

    item_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of import item IDs to update",
    )
    rules: List[TransformationRule] = Field(
        ...,
        min_length=1,
        description="List of transformation rules to apply",
    )


# ============================================================================
# Response Schemas - Preview
# ============================================================================


class PreviewWarning(BaseModel):
    """Warning for a tag that couldn't be transformed."""

    tag: str = Field(..., description="Tag that has the warning")
    code: str = Field(..., description="Warning code")
    message: str = Field(..., description="Human-readable warning message")


class ItemPreview(BaseModel):
    """Preview result for a single import item."""

    item_id: int = Field(..., description="Import item ID")
    changes: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of tag names to their new values (only includes changed tags)",
    )
    warnings: List[PreviewWarning] = Field(
        default_factory=list,
        description="Warnings for tags that couldn't be fully processed",
    )


class PreviewError(BaseModel):
    """Error for an item that couldn't be previewed."""

    item_id: int = Field(..., description="Import item ID that failed")
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")


class BatchPreviewResponse(BaseModel):
    """Response body for preview endpoint."""

    previews: List[ItemPreview] = Field(
        ...,
        description="Preview results for each successfully processed item",
    )
    errors: List[PreviewError] = Field(
        default_factory=list,
        description="Errors for items that couldn't be previewed",
    )


# ============================================================================
# Response Schemas - Batch Update
# ============================================================================


class ItemError(BaseModel):
    """Error details for a failed item update."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    file_path: Optional[str] = Field(None, description="File path if relevant")


class ItemResult(BaseModel):
    """Result for a single item in the batch update."""

    item_id: int = Field(..., description="Import item ID")
    status: Literal["success", "failed"] = Field(..., description="Update status")
    changes_applied: Optional[Dict[str, str]] = Field(
        None,
        description="Map of tag names to applied values (only on success)",
    )
    error: Optional[ItemError] = Field(
        None,
        description="Error details (only on failure)",
    )


class BatchUpdateResponse(BaseModel):
    """Response body for batch update endpoint."""

    status: Literal["completed"] = Field("completed", description="Batch operation status")
    items_total: int = Field(..., ge=0, description="Total items in batch")
    items_succeeded: int = Field(..., ge=0, description="Items successfully updated")
    items_failed: int = Field(..., ge=0, description="Items that failed to update")
    started_at: datetime = Field(..., description="When the batch operation started")
    completed_at: datetime = Field(..., description="When the batch operation completed")
    duration_seconds: int = Field(..., ge=0, description="Total duration in seconds")
    results: List[ItemResult] = Field(..., description="Results for each item")


# ============================================================================
# SSE Event Schemas
# ============================================================================


class SSEBatchStarted(BaseModel):
    """Data for batch_started SSE event."""

    total_items: int = Field(..., description="Total items to process")
    started_at: datetime = Field(..., description="When the operation started")


class SSEItemProgress(BaseModel):
    """Data for item_progress SSE event."""

    item_id: int = Field(..., description="ID of the processed item")
    status: Literal["success", "failed"] = Field(..., description="Item processing status")
    items_processed: int = Field(..., description="Total items processed so far")
    items_total: int = Field(..., description="Total items in batch")
    progress_percent: float = Field(..., ge=0, le=100, description="Progress percentage")
    error: Optional[ItemError] = Field(None, description="Error details if failed")


class SSEBatchCompleted(BaseModel):
    """Data for batch_completed SSE event."""

    items_total: int = Field(..., description="Total items in batch")
    items_succeeded: int = Field(..., description="Items successfully updated")
    items_failed: int = Field(..., description="Items that failed to update")
    completed_at: datetime = Field(..., description="When the operation completed")
    duration_seconds: int = Field(..., description="Total duration in seconds")


class SSEBatchFailed(BaseModel):
    """Data for batch_failed SSE event."""

    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    failed_at: datetime = Field(..., description="When the failure occurred")


class SSEHeartbeat(BaseModel):
    """Data for heartbeat SSE event."""

    timestamp: datetime = Field(..., description="Current server time")
