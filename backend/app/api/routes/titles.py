"""API routes for the Titles page — track search with text + BPM filters.

Same library scoping and DB error mapping as the album routes; the ids
endpoint feeds "select all results" for the download gather, so it returns
minimal rows even for multi-thousand-track matches.
"""

import logging
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.libraries import get_beets_library_service, get_library_by_slug
from app.database import get_db
from app.schemas.titles import (
    TitleArtistsResponse,
    TitleIdRow,
    TitleIdsResponse,
    TitleRow,
    TitlesListResponse,
)
from app.services.beets_library_service import BeetsLibraryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["titles"])

# Hard ceiling for select-all: keeps the gather payload + localStorage sane.
MAX_SELECT_ALL = 5000


def _db_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"Library beets database error: {e}")


def _validate_bpm_bounds(bpm_min: Optional[float], bpm_max: Optional[float]) -> None:
    if (bpm_min is None) != (bpm_max is None):
        raise HTTPException(status_code=400, detail="bpm_min and bpm_max must be given together")
    if bpm_min is not None and bpm_min > bpm_max:
        raise HTTPException(status_code=400, detail="bpm_min must be <= bpm_max")


@router.get("/{slug}/titles", response_model=TitlesListResponse)
def list_titles(
    slug: str,
    search: Optional[str] = Query(None, max_length=200),
    bpm_min: Optional[float] = Query(None, ge=1, le=1000),
    bpm_max: Optional[float] = Query(None, ge=1, le=1000),
    include_half_double: bool = Query(False),
    album_artist: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Paginated title (track) listing with text search and BPM range filter."""
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library has no database_path configured")
    _validate_bpm_bounds(bpm_min, bpm_max)
    try:
        rows, total = beets_service.search_library_titles(
            library.database_path,
            search=search,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            include_half_double=include_half_double,
            album_artists=album_artist,
            page=page,
            per_page=per_page,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Library beets database is missing on disk")
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise _db_error(e)
    return TitlesListResponse(
        items=[TitleRow(**r) for r in rows], total=total, page=page, per_page=per_page
    )


@router.get("/{slug}/titles/ids", response_model=TitleIdsResponse)
def list_title_ids(
    slug: str,
    search: Optional[str] = Query(None, max_length=200),
    bpm_min: Optional[float] = Query(None, ge=1, le=1000),
    bpm_max: Optional[float] = Query(None, ge=1, le=1000),
    include_half_double: bool = Query(False),
    album_artist: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Every title matching the filters (id/title/artist only), for select-all.

    Rejects result sets beyond MAX_SELECT_ALL with 413 — a gather that size
    would produce an unusable multi-gigabyte zip anyway.
    """
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library has no database_path configured")
    _validate_bpm_bounds(bpm_min, bpm_max)
    try:
        rows = beets_service.search_library_title_ids(
            library.database_path,
            search=search,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            include_half_double=include_half_double,
            album_artists=album_artist,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Library beets database is missing on disk")
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise _db_error(e)
    if len(rows) > MAX_SELECT_ALL:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{len(rows)} titles match — the select-all limit is {MAX_SELECT_ALL}. "
                "Narrow the search or BPM range."
            ),
        )
    return TitleIdsResponse(items=[TitleIdRow(**r) for r in rows], total=len(rows))


@router.get("/{slug}/titles/artists", response_model=TitleArtistsResponse)
def list_title_artists(
    slug: str,
    search: Optional[str] = Query(None, max_length=200),
    bpm_min: Optional[float] = Query(None, ge=1, le=1000),
    bpm_max: Optional[float] = Query(None, ge=1, le=1000),
    include_half_double: bool = Query(False),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Album artists for the filter dropdown, grouped by the current result.

    Takes the same search + BPM params as the listing (but not the artist
    selection): ``in_result`` are the album artists present in that result,
    ``others`` the rest — so the dropdown can float the relevant ones up top.
    """
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(status_code=500, detail="Library has no database_path configured")
    _validate_bpm_bounds(bpm_min, bpm_max)
    try:
        in_result, others = beets_service.list_library_artists(
            library.database_path,
            search=search,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            include_half_double=include_half_double,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Library beets database is missing on disk")
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise _db_error(e)
    return TitleArtistsResponse(
        in_result=in_result, others=others, total=len(in_result) + len(others)
    )
