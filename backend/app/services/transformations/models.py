"""Pydantic models for transformation rules.

These models define the structure of transformation rules that can be
applied to import items for batch tag editing.
"""

from enum import Enum
from typing import Annotated, Dict, Literal, Union

from pydantic import BaseModel, Field


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

    The caller supplies a ``item_id -> value`` map computed elsewhere (the
    drag-reorder UI). Items absent from the map are left unchanged. Used to
    commit a manual track reorder: the exact track numbers (and titles, when
    "keep titles" is on) the user saw in the preview.
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
