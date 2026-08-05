"""Schemas for the Titles page — track-level search with BPM filtering."""

from typing import List, Optional

from pydantic import BaseModel


class TitleRow(BaseModel):
    """One track in the titles listing."""

    id: int
    title: str
    artist: str
    albumartist: str = ""
    album: str
    album_id: Optional[int] = None
    bpm: Optional[float] = None
    length: Optional[float] = None
    format: Optional[str] = None
    bitrate: Optional[int] = None


class TitlesListResponse(BaseModel):
    items: List[TitleRow]
    total: int
    page: int
    per_page: int


class TitleIdRow(BaseModel):
    """Minimal row for select-all-results (feeds the download gather)."""

    id: int
    title: str
    artist: str


class TitleIdsResponse(BaseModel):
    items: List[TitleIdRow]
    total: int


class TitleArtistsResponse(BaseModel):
    """Album artists for the Titles filter dropdown.

    ``in_result`` are those present in the current search + BPM result;
    ``others`` are the remaining library album artists. Both alphabetical.
    """

    in_result: List[str]
    others: List[str]
    total: int
