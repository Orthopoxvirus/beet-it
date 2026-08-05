"""Multi-provider candidate search.

Fans out a free-text query to every metadata provider whose beets plugin is
active for a library and returns normalized album hits. Used by the
``/search-candidates`` endpoint to power the search mode of the manual-candidate
dialog.

Design notes:
  * Each provider is queried in its own thread (the underlying clients —
    musicbrainzngs, httpx, the beets Spotify plugin — are synchronous) with a
    per-provider timeout. A single provider failing or timing out never fails
    the whole request; its group comes back with ``available=True`` and a
    ``reason`` describing the error.
  * Providers are *gated* before fan-out: a provider whose plugin is not in the
    library's ``plugins`` list (or, for Discogs, which has no access token) is
    returned with ``available=False`` and a reason for the UI to show on hover.
  * Every hit's ``external_url`` is a canonical provider URL that the existing
    ``detect_provider`` / ``extract_id_from_link`` helpers can parse, so the
    frontend resolves a picked result through the unchanged manual-candidate
    endpoint.
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import List, Optional, Tuple

from app.schemas.beets_config import DEFAULT_PLUGINS
from app.schemas.beets_search import (
    SearchCandidatesResponse,
    SearchProviderGroup,
    SearchResultItem,
)
from app.services.beets_config_service import BeetsConfigService
# Reuse the single process-wide lock that guards the global beets config
# singleton, so search serializes against the analyze/resolve paths that mutate
# the same object (rather than each path locking a different mutex).
from app.services.beets_autotag_service import _beets_config_lock

logger = logging.getLogger(__name__)

# Canonical display order for providers in the response.
PROVIDERS = ["musicbrainz", "spotify", "deezer", "discogs"]

# Plugin name in the beets config that enables each provider.
_PLUGIN_NAME = {
    "musicbrainz": "musicbrainz",
    "spotify": "spotify",
    "deezer": "deezer",
    "discogs": "discogs",
}

_PROVIDER_LABEL = {
    "musicbrainz": "MusicBrainz",
    "spotify": "Spotify",
    "deezer": "Deezer",
    "discogs": "Discogs",
}

# Default per-provider request timeout (the outer guard around each thread).
DEFAULT_SEARCH_TIMEOUT = int(os.environ.get("BEETS_SEARCH_TIMEOUT_SECONDS", "20"))

# HTTP-level timeout for the provider clients — kept below the outer guard so a
# hung socket unwinds on its own rather than via the (uncancellable) thread.
_HTTP_TIMEOUT = 15.0

_USER_AGENT = "beet-it/1.0 (+https://github.com/Orthopoxvirus/beet-it)"

# --- Result ranking (issue #112) -------------------------------------------
#
# Providers return hits in their own relevance order, which buries two signals
# the user cares about most: a number in the query (e.g. the "45" in
# "die drei ??? 45") and a track count that matches the local folder being
# imported. We re-rank each provider's hits by a small additive score so those
# float to the top, using the provider's own order as the tiebreaker (a stable
# sort) so we never fully override an otherwise-good native ranking.
#
# Weights are deliberately coarse and easy to tune — bump them here if the
# ranking misses.
_SCORE_TRACK_COUNT_EXACT = 100  # result's track count == the local folder's
_SCORE_TRACK_COUNT_NEAR = 40    # off by one (a hidden / bonus track)
_SCORE_NUMBER_MATCH = 80        # a number from the query appears in the result

# When there is something to rank for, fetch a wider window per provider so a
# strong match sitting below the provider's top hits can be pulled up by the
# re-rank instead of hiding on a later page. The multiplier also becomes the
# pagination stride (it scales the provider offset), so pages stay contiguous
# and no result is skipped between them. The window is capped so a large
# per_page can't push a single provider request past its API limit (Spotify
# caps `limit` at 50).
_SCORE_OVERFETCH = max(1, int(os.environ.get("BEETS_SEARCH_OVERFETCH", "3")))
_SCORE_OVERFETCH_MAX = 50

_NUMBER_RE = re.compile(r"\d+")


class ProviderSearchError(Exception):
    """A provider search attempt failed (network, auth, or bad response)."""


# --- Helpers ---------------------------------------------------------------


def _field_query(
    artist: Optional[str],
    album: Optional[str],
    artist_field: str,
    album_field: str,
    join: str = " ",
) -> str:
    """Build a ``field:"value"`` query for providers with field-search syntax.

    MusicBrainz (Lucene), Spotify, and Deezer all accept field-qualified terms
    so the artist and the album title are matched against the right index rather
    than smeared across a single free-text blob — which is what made an
    ``"Artist - Album"`` string return a flood of loose matches (issue #69).

    Embedded double-quotes are stripped so a stray ``"`` in a tag can't break
    out of the quoted term. Returns ``""`` when neither field is known, so the
    caller can fall back to the user's free-text query.
    """
    parts: List[str] = []
    a = (artist or "").strip().replace('"', "")
    al = (album or "").strip().replace('"', "")
    if a:
        parts.append(f'{artist_field}:"{a}"')
    if al:
        parts.append(f'{album_field}:"{al}"')
    return join.join(parts)


def _year_from_date(date_str: Optional[str]) -> Optional[int]:
    """Pull a 4-digit year off an ISO-ish date string ('2020', '2020-05-01')."""
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


def _mb_artist_from_json(artist_credit: list) -> str:
    """Join a MusicBrainz ws/2 JSON artist-credit list into a display string.

    Each entry carries a credited ``name`` plus a ``joinphrase`` ("", " & ",
    " feat. ", …); concatenating them reproduces the canonical artist string.
    """
    parts: List[str] = []
    for entry in artist_credit or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            artist = entry.get("artist")
            name = artist.get("name", "") if isinstance(artist, dict) else ""
        parts.append(name or "")
        parts.append(entry.get("joinphrase", "") or "")
    return "".join(parts).strip()


def _numbers_in(text: Optional[str]) -> set[str]:
    """Return the distinct digit runs in *text* (``'Folge 45'`` -> ``{'45'}``)."""
    if not text:
        return set()
    return set(_NUMBER_RE.findall(text))


def _score_item(
    item: SearchResultItem,
    query_numbers: set[str],
    expected_tracks: Optional[int],
) -> int:
    """Relevance bonus for one search hit (issue #112).

    Sums the two signals the user flagged as significant: a number from the
    query also appearing in the hit's title/artist (e.g. the ``45`` in
    ``"die drei ??? 45"``), and the hit's track count matching the local
    folder's. A score of 0 means "no signal" — the caller's stable sort then
    leaves the provider's own order untouched.
    """
    score = 0
    if query_numbers and (query_numbers & (_numbers_in(item.title) | _numbers_in(item.artist))):
        score += _SCORE_NUMBER_MATCH
    if expected_tracks is not None and item.track_count is not None:
        diff = abs(item.track_count - expected_tracks)
        if diff == 0:
            score += _SCORE_TRACK_COUNT_EXACT
        elif diff == 1:
            score += _SCORE_TRACK_COUNT_NEAR
    return score


def _rank_results(
    items: List[SearchResultItem],
    query_numbers: set[str],
    expected_tracks: Optional[int],
) -> List[SearchResultItem]:
    """Stable-sort hits by descending score; ties keep the provider's order.

    A no-op when there is nothing to rank for (no query numbers and no known
    track count), so plain searches behave exactly as before.
    """
    if not query_numbers and expected_tracks is None:
        return items
    return sorted(items, key=lambda it: -_score_item(it, query_numbers, expected_tracks))


def _read_search_config(config_path: Optional[str]) -> Tuple[List[str], str]:
    """Return (active_plugins, discogs_token) parsed from the library config.

    Falls back to the default plugin set (and an empty Discogs token) when the
    config is missing or unparseable, so search degrades gracefully rather than
    erroring.
    """
    plugins: List[str] = list(DEFAULT_PLUGINS)
    discogs_token = ""
    if config_path and os.path.exists(config_path):
        try:
            cfg = BeetsConfigService().parse_yaml_config(config_path)
            plugins = cfg.plugins
            discogs_token = (cfg.discogs.user_token or "").strip()
        except Exception as e:  # noqa: BLE001 - config issues must not break search
            logger.warning(
                "Could not parse beets config %s for search; using defaults: %s",
                config_path,
                e,
            )
    return plugins, discogs_token


def _determine_availability(
    plugins: List[str], discogs_token: str
) -> dict[str, Tuple[bool, Optional[str]]]:
    """Decide which providers can be searched and why the others cannot."""
    active = set(plugins)
    availability: dict[str, Tuple[bool, Optional[str]]] = {}
    for provider in PROVIDERS:
        label = _PROVIDER_LABEL[provider]
        if _PLUGIN_NAME[provider] not in active:
            availability[provider] = (
                False,
                f"The {label} plugin is not enabled for this library.",
            )
            continue
        if provider == "discogs" and not discogs_token:
            availability[provider] = (
                False,
                "Discogs search requires a personal access token "
                "(set discogs.user_token in the library config).",
            )
            continue
        availability[provider] = (True, None)
    return availability


# --- Per-provider search ---------------------------------------------------


def search_musicbrainz(
    query: str,
    page: int,
    per_page: int,
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> Tuple[List[SearchResultItem], bool]:
    """Search MusicBrainz releases via the public ws/2 JSON API (no auth).

    Uses httpx directly (rather than musicbrainzngs) so the request carries an
    explicit timeout — the musicbrainzngs client sets none, which would let a
    stalled connection hang the worker thread past the fan-out's guard.

    When ``artist``/``album`` are known they are sent as Lucene field terms
    (``artist:"X" AND release:"Y"``) instead of the free-text ``query``, so the
    match is scoped to the right fields (issue #69).
    """
    import httpx

    effective_query = (
        _field_query(artist, album, "artist", "release", join=" AND ") or query
    )
    offset = (page - 1) * per_page
    try:
        resp = httpx.get(
            "https://musicbrainz.org/ws/2/release",
            params={"query": effective_query, "fmt": "json", "limit": per_page, "offset": offset},
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise ProviderSearchError(f"MusicBrainz search failed: {e}")

    releases = data.get("releases", []) or []
    count = int(data.get("count", 0) or 0)

    items: List[SearchResultItem] = []
    for release in releases:
        rid = release.get("id")
        if not rid:
            continue
        track_count = release.get("track-count")
        try:
            track_count = int(track_count) if track_count is not None else None
        except (TypeError, ValueError):
            track_count = None
        items.append(
            SearchResultItem(
                provider="musicbrainz",
                source_id=rid,
                title=release.get("title", ""),
                artist=_mb_artist_from_json(release.get("artist-credit", [])),
                year=_year_from_date(release.get("date")),
                track_count=track_count,
                external_url=f"https://musicbrainz.org/release/{rid}",
                cover_url=None,
            )
        )

    has_more = offset + len(releases) < count
    return items, has_more


def search_deezer(
    query: str,
    page: int,
    per_page: int,
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> Tuple[List[SearchResultItem], bool]:
    """Search Deezer albums via the public API (no auth).

    Uses Deezer's advanced query syntax (``artist:"X" album:"Y"``) when the
    artist/album are known, falling back to the free-text ``query`` otherwise
    (issue #69).
    """
    import httpx

    effective_query = _field_query(artist, album, "artist", "album") or query
    index = (page - 1) * per_page
    try:
        resp = httpx.get(
            "https://api.deezer.com/search/album",
            params={"q": effective_query, "limit": per_page, "index": index},
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise ProviderSearchError(f"Deezer search failed: {e}")

    albums = data.get("data", []) or []
    items: List[SearchResultItem] = []
    for album in albums:
        aid = album.get("id")
        if not aid:
            continue
        items.append(
            SearchResultItem(
                provider="deezer",
                source_id=str(aid),
                title=album.get("title", ""),
                artist=(album.get("artist") or {}).get("name", ""),
                year=None,  # Deezer's album-search payload omits the release date
                track_count=album.get("nb_tracks"),
                external_url=f"https://www.deezer.com/album/{aid}",
                cover_url=album.get("cover_medium") or album.get("cover"),
            )
        )

    total = int(data.get("total", 0) or 0)
    has_more = bool(data.get("next")) or (index + len(albums) < total)
    return items, has_more


def search_discogs(
    query: str,
    page: int,
    per_page: int,
    token: str,
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> Tuple[List[SearchResultItem], bool]:
    """Search Discogs releases via the database search API (token required).

    Discogs exposes dedicated ``artist`` and ``release_title`` search fields, so
    when those are known we send them as separate params rather than merging
    everything into ``q`` — which narrows the result set the same way the other
    providers' field queries do (issue #69).
    """
    import httpx

    a = (artist or "").strip()
    al = (album or "").strip()
    params = {
        "type": "release",
        "per_page": per_page,
        "page": page,
        "token": token,
    }
    if a or al:
        if a:
            params["artist"] = a
        if al:
            params["release_title"] = al
    else:
        params["q"] = query

    try:
        resp = httpx.get(
            "https://api.discogs.com/database/search",
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise ProviderSearchError(f"Discogs search failed: {e}")

    if resp.status_code in (401, 403):
        raise ProviderSearchError(
            "Discogs rejected the access token. Check discogs.user_token."
        )
    if resp.status_code != 200:
        raise ProviderSearchError(
            f"Discogs API returned {resp.status_code}: {resp.text[:200]}"
        )
    data = resp.json()

    items: List[SearchResultItem] = []
    for hit in data.get("results", []) or []:
        rid = hit.get("id")
        if not rid:
            continue
        # Discogs search titles are "Artist - Album"; split on the first " - ".
        full_title = hit.get("title", "") or ""
        artist, sep, album = full_title.partition(" - ")
        if not sep:
            album, artist = full_title, ""
        hit_type = hit.get("type", "release")
        url_type = "master" if hit_type == "master" else "release"
        year = hit.get("year")
        try:
            year = int(year) if year else None
        except (TypeError, ValueError):
            year = None
        items.append(
            SearchResultItem(
                provider="discogs",
                source_id=str(rid),
                title=album.strip(),
                artist=artist.strip(),
                year=year,
                track_count=None,
                external_url=f"https://www.discogs.com/{url_type}/{rid}",
                cover_url=hit.get("cover_image") or hit.get("thumb"),
            )
        )

    pagination = data.get("pagination", {}) or {}
    try:
        has_more = int(pagination.get("page", page)) < int(pagination.get("pages", page))
    except (TypeError, ValueError):
        has_more = False
    return items, has_more


def search_spotify(
    query: str,
    page: int,
    per_page: int,
    config_path: Optional[str],
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> Tuple[List[SearchResultItem], bool]:
    """Search Spotify albums using the beets Spotify plugin for authentication.

    The plugin manages the client-credentials token (it ships with working
    default credentials, overridable via the library config). We borrow its
    access token and call the Web API directly so we can paginate with `offset`.

    When the artist/album are known they are sent as Spotify field filters
    (``artist:"X" album:"Y"``) rather than free text, so the search is scoped to
    the right fields (issue #69).
    """
    import httpx

    effective_query = _field_query(artist, album, "artist", "album") or query

    with _beets_config_lock:
        try:
            from beets import config as beets_config
            from beets import plugins as beets_plugins
            from beetsplug.spotify import SpotifyPlugin
        except ImportError as e:
            raise ProviderSearchError(f"Spotify plugin not available: {e}")

        # Load the library config so user-supplied Spotify credentials apply.
        if config_path and os.path.exists(config_path):
            beets_config.clear()
            beets_config.set_file(config_path)
            beets_config.read()
            beets_plugins.load_plugins()

        try:
            plugin = SpotifyPlugin()
        except Exception as e:  # noqa: BLE001
            raise ProviderSearchError(f"Spotify authentication failed: {e}")

        search_url = getattr(plugin, "search_url", "https://api.spotify.com/v1/search")
        offset = (page - 1) * per_page

        def _request(token: Optional[str]) -> httpx.Response:
            return httpx.get(
                search_url,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q": effective_query,
                    "type": "album",
                    "limit": per_page,
                    "offset": offset,
                },
                timeout=_HTTP_TIMEOUT,
            )

        try:
            resp = _request(getattr(plugin, "access_token", None))
            if resp.status_code == 401:
                # Token expired — let the plugin refresh once, then retry.
                plugin._authenticate()
                resp = _request(plugin.access_token)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderSearchError(f"Spotify search failed: {e}")

    albums = data.get("albums", {}) or {}
    items: List[SearchResultItem] = []
    for album in albums.get("items", []) or []:
        aid = album.get("id")
        if not aid:
            continue
        artists = ", ".join(
            a.get("name", "") for a in album.get("artists", []) if a.get("name")
        )
        images = album.get("images", []) or []
        cover = images[-1]["url"] if images else None  # smallest image
        items.append(
            SearchResultItem(
                provider="spotify",
                source_id=aid,
                title=album.get("name", ""),
                artist=artists,
                year=_year_from_date(album.get("release_date")),
                track_count=album.get("total_tracks"),
                external_url=f"https://open.spotify.com/album/{aid}",
                cover_url=cover,
            )
        )

    total = int(albums.get("total", 0) or 0)
    has_more = offset + len(albums.get("items", []) or []) < total
    return items, has_more


# --- Fan-out orchestration -------------------------------------------------


def _run_provider(
    provider: str,
    query: str,
    page: int,
    per_page: int,
    discogs_token: str,
    config_path: Optional[str],
    artist: Optional[str] = None,
    album: Optional[str] = None,
    query_numbers: Optional[set[str]] = None,
    expected_tracks: Optional[int] = None,
) -> SearchProviderGroup:
    """Run one provider's search, converting any failure into a group result.

    The hits are re-ranked (issue #112) before being returned so a matching
    number or track count rises to the top of this provider's group.
    """
    try:
        if provider == "musicbrainz":
            items, has_more = search_musicbrainz(query, page, per_page, artist, album)
        elif provider == "deezer":
            items, has_more = search_deezer(query, page, per_page, artist, album)
        elif provider == "discogs":
            items, has_more = search_discogs(
                query, page, per_page, discogs_token, artist, album
            )
        elif provider == "spotify":
            items, has_more = search_spotify(
                query, page, per_page, config_path, artist, album
            )
        else:  # pragma: no cover - guarded by PROVIDERS
            raise ProviderSearchError(f"Unknown provider: {provider}")
        items = _rank_results(items, query_numbers or set(), expected_tracks)
        return SearchProviderGroup(
            provider=provider, available=True, reason=None, results=items, has_more=has_more
        )
    except Exception as e:  # noqa: BLE001 - one provider must not fail the request
        logger.warning("Search failed for provider %s: %s", provider, e)
        return SearchProviderGroup(
            provider=provider,
            available=True,
            reason=f"Search failed: {e}",
            results=[],
            has_more=False,
        )


def search_all_providers(
    config_path: Optional[str],
    query: str,
    page: int = 1,
    per_page: int = 5,
    timeout: int = DEFAULT_SEARCH_TIMEOUT,
    providers: Optional[List[str]] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    expected_tracks: Optional[int] = None,
) -> SearchCandidatesResponse:
    """Query every active provider concurrently and aggregate the results.

    Args:
        config_path: Path to the library's beets config (for plugin gating and
            Spotify/Discogs credentials). May be None.
        query: Free-text search term.
        page: 1-indexed page number.
        per_page: Results per provider per page.
        timeout: Per-provider wall-clock guard in seconds.
        providers: Subset of PROVIDERS to search; None means all. The response
            contains one group per *requested* provider only, so per-provider
            pagination doesn't re-query (or re-transfer) the other providers.
        artist: Optional structured artist term. When set (with/without
            ``album``) each provider is queried with its field-search syntax
            instead of the free-text ``query``, sharply narrowing results
            (issue #69). ``query`` remains the fallback and the echoed term.
        album: Optional structured album/release-title term (see ``artist``).
        expected_tracks: Track count of the local folder being imported, if
            known. Hits whose track count matches are ranked to the top of their
            provider group (issue #112).

    Returns:
        A SearchCandidatesResponse with one group per requested provider, in the
        canonical PROVIDERS order.
    """
    plugins, discogs_token = _read_search_config(config_path)
    availability = _determine_availability(plugins, discogs_token)

    # Numbers from the query and the structured terms drive the numeric-match
    # boost; together with a known track count they decide whether re-ranking
    # is active at all (issue #112).
    query_numbers = _numbers_in(query) | _numbers_in(artist) | _numbers_in(album)
    scoring_active = bool(query_numbers or expected_tracks is not None)
    # Over-fetch when ranking so a strong match buried below a provider's top
    # hits can be pulled up rather than stranded on a later page. Multiplying
    # per_page also scales each provider's offset, keeping pages contiguous.
    effective_per_page = (
        min(per_page * _SCORE_OVERFETCH, _SCORE_OVERFETCH_MAX)
        if scoring_active
        else per_page
    )

    requested = PROVIDERS if providers is None else [p for p in PROVIDERS if p in providers]
    active = [p for p in requested if availability[p][0]]
    results_map: dict[str, SearchProviderGroup] = {}

    if active:
        # Don't use the executor as a context manager: its __exit__ calls
        # shutdown(wait=True), which would block the request thread until every
        # worker finishes — defeating the per-provider timeout below. Shut down
        # without waiting so the response is bounded even if a provider hangs.
        executor = ThreadPoolExecutor(max_workers=len(active))
        try:
            futures = {
                executor.submit(
                    _run_provider,
                    provider,
                    query,
                    page,
                    effective_per_page,
                    discogs_token,
                    config_path,
                    artist,
                    album,
                    query_numbers,
                    expected_tracks,
                ): provider
                for provider in active
            }
            for future, provider in futures.items():
                try:
                    results_map[provider] = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    logger.warning("Search timed out for provider %s", provider)
                    results_map[provider] = SearchProviderGroup(
                        provider=provider,
                        available=True,
                        reason="Search timed out.",
                        results=[],
                        has_more=False,
                    )
        finally:
            executor.shutdown(wait=False)

    groups: List[SearchProviderGroup] = []
    for provider in requested:
        if provider in results_map:
            groups.append(results_map[provider])
        else:
            _, reason = availability[provider]
            groups.append(
                SearchProviderGroup(
                    provider=provider, available=False, reason=reason, results=[], has_more=False
                )
            )

    return SearchCandidatesResponse(
        query=query, page=page, per_page=per_page, providers=groups
    )
