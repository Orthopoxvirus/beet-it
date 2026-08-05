"""Pydantic schemas for multi-provider candidate search.

These power the "search" mode of the manual-candidate dialog: the user types a
free-text term and the backend queries every metadata provider whose beets
plugin is active for the library (MusicBrainz, Spotify, Deezer, Discogs) at the
same time. Each result carries an ``external_url`` that is both a link the user
can open in a new tab AND a link the existing ``/manual-candidate`` endpoint can
resolve — so picking a search result reuses the manual-candidate flow verbatim.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.beets_autotag import to_camel


class SearchResultItem(BaseModel):
    """A single album hit from one provider's search."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    provider: str = Field(
        ..., description="Provider name: 'musicbrainz', 'spotify', 'deezer', or 'discogs'"
    )
    source_id: str = Field(..., description="Provider-native release/album identifier")
    title: str = Field(..., description="Album title")
    artist: str = Field(default="", description="Album artist (may be empty if unknown)")
    year: Optional[int] = Field(None, description="Release year, if the provider reports one")
    track_count: Optional[int] = Field(
        None, description="Number of tracks, if the provider reports one"
    )
    external_url: str = Field(
        ...,
        description=(
            "Canonical provider URL. Opens in a new tab and doubles as the link "
            "passed to the manual-candidate endpoint to resolve this hit."
        ),
    )
    cover_url: Optional[str] = Field(
        None, description="Thumbnail/cover image URL, if available"
    )


class SearchProviderGroup(BaseModel):
    """Per-provider search outcome: results, availability, and pagination state."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    provider: str = Field(..., description="Provider name")
    available: bool = Field(
        ...,
        description=(
            "True if the provider was searched (plugin active and, where required, "
            "configured). False means it was skipped — see `reason`."
        ),
    )
    reason: Optional[str] = Field(
        None,
        description=(
            "Human-readable explanation shown on hover when the provider is "
            "unavailable, or the error message when a search attempt failed."
        ),
    )
    results: List[SearchResultItem] = Field(
        default_factory=list, description="Album hits for this provider (this page)"
    )
    has_more: bool = Field(
        default=False, description="True if more result pages exist for this provider"
    )


class SearchCandidatesResponse(BaseModel):
    """Aggregated multi-provider search response for one query page."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    query: str = Field(..., description="The search term that was run")
    page: int = Field(..., ge=1, description="1-indexed page number")
    per_page: int = Field(..., ge=1, description="Results requested per provider per page")
    providers: List[SearchProviderGroup] = Field(
        default_factory=list,
        description="One entry per supported provider, in a stable display order",
    )
