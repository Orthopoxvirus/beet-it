"""Tests for multi-provider candidate search (service + endpoint)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.beets_search_service as bss
from app.api.routes.beets_autotag import router
from app.database import get_db
from app.schemas.beets_search import (
    SearchCandidatesResponse,
    SearchProviderGroup,
    SearchResultItem,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _http_response(json_data, status_code=200, text=""):
    """Build a stand-in for an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Provider availability gating
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_all_active_with_discogs_token(self):
        av = bss._determine_availability(
            ["musicbrainz", "spotify", "deezer", "discogs"], "tok"
        )
        assert all(av[p][0] for p in bss.PROVIDERS)
        assert all(av[p][1] is None for p in bss.PROVIDERS)

    def test_plugin_not_enabled_is_unavailable_with_reason(self):
        av = bss._determine_availability(["musicbrainz"], "")
        assert av["musicbrainz"][0] is True
        assert av["spotify"][0] is False
        assert "Spotify" in av["spotify"][1]
        assert av["deezer"][0] is False

    def test_discogs_requires_token(self):
        av = bss._determine_availability(["discogs"], "")
        available, reason = av["discogs"]
        assert available is False
        assert "token" in reason.lower()

    def test_discogs_available_with_token(self):
        av = bss._determine_availability(["discogs"], "secret")
        assert av["discogs"][0] is True


# ---------------------------------------------------------------------------
# Per-provider search parsing
# ---------------------------------------------------------------------------


class TestMusicBrainzSearch:
    def test_parses_results_and_pagination(self):
        payload = {
            "releases": [
                {
                    "id": "uuid-1",
                    "title": "Discovery",
                    "artist-credit": [
                        {"name": "Daft Punk", "joinphrase": "", "artist": {"name": "Daft Punk"}}
                    ],
                    "date": "2001-03-12",
                    "track-count": 14,
                }
            ],
            "count": 30,
            "offset": 0,
        }
        with patch("httpx.get", return_value=_http_response(payload)):
            items, has_more = bss.search_musicbrainz("daft punk", page=1, per_page=5)

        assert len(items) == 1
        item = items[0]
        assert item.provider == "musicbrainz"
        assert item.source_id == "uuid-1"
        assert item.title == "Discovery"
        assert item.artist == "Daft Punk"
        assert item.year == 2001
        assert item.track_count == 14
        assert item.external_url == "https://musicbrainz.org/release/uuid-1"
        assert has_more is True  # offset 0 + 1 < 30

    def test_joins_collaborating_artists_with_joinphrase(self):
        payload = {
            "releases": [
                {
                    "id": "uuid-2",
                    "title": "Collab",
                    "artist-credit": [
                        {"name": "A", "joinphrase": " & "},
                        {"name": "B", "joinphrase": ""},
                    ],
                    "date": "2010",
                }
            ],
            "count": 1,
        }
        with patch("httpx.get", return_value=_http_response(payload)):
            items, _ = bss.search_musicbrainz("x", page=1, per_page=5)
        assert items[0].artist == "A & B"

    def test_no_more_when_page_exhausts_count(self):
        payload = {"releases": [], "count": 0}
        with patch("httpx.get", return_value=_http_response(payload)):
            items, has_more = bss.search_musicbrainz("nope", page=1, per_page=5)
        assert items == []
        assert has_more is False

    def test_http_error_raises_provider_error(self):
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("boom")):
            with pytest.raises(bss.ProviderSearchError):
                bss.search_musicbrainz("x", page=1, per_page=5)


class TestDeezerSearch:
    def test_parses_results_and_builds_canonical_url(self):
        payload = {
            "data": [
                {
                    "id": 111,
                    "title": "Homework",
                    "artist": {"name": "Daft Punk"},
                    "nb_tracks": 16,
                    "cover_medium": "http://img/cover",
                }
            ],
            "total": 50,
            "next": "http://api.deezer.com/...",
        }
        with patch("httpx.get", return_value=_http_response(payload)):
            items, has_more = bss.search_deezer("daft punk", page=1, per_page=5)

        assert len(items) == 1
        item = items[0]
        assert item.provider == "deezer"
        assert item.source_id == "111"
        assert item.title == "Homework"
        assert item.artist == "Daft Punk"
        assert item.track_count == 16
        assert item.external_url == "https://www.deezer.com/album/111"
        assert item.cover_url == "http://img/cover"
        assert has_more is True

    def test_no_more_at_count_boundary_without_next(self):
        # index 0 + 1 result == total 1, and no "next" key → has_more False
        payload = {"data": [{"id": 1, "title": "X", "artist": {"name": "Y"}}], "total": 1}
        with patch("httpx.get", return_value=_http_response(payload)):
            _, has_more = bss.search_deezer("x", page=1, per_page=5)
        assert has_more is False

    def test_http_error_raises_provider_error(self):
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("down")):
            with pytest.raises(bss.ProviderSearchError):
                bss.search_deezer("x", page=1, per_page=5)


class TestDiscogsSearch:
    def test_splits_artist_album_and_builds_url(self):
        payload = {
            "results": [
                {
                    "id": 222,
                    "type": "release",
                    "title": "Daft Punk - Homework",
                    "year": "1997",
                    "cover_image": "http://c",
                },
                {
                    "id": 333,
                    "type": "master",
                    "title": "Justice - Cross",
                    "year": 2007,
                },
            ],
            "pagination": {"page": 1, "pages": 3},
        }
        with patch("httpx.get", return_value=_http_response(payload)):
            items, has_more = bss.search_discogs("x", page=1, per_page=5, token="tok")

        assert items[0].artist == "Daft Punk"
        assert items[0].title == "Homework"
        assert items[0].year == 1997
        assert items[0].external_url == "https://www.discogs.com/release/222"
        # master type → master URL
        assert items[1].external_url == "https://www.discogs.com/master/333"
        assert has_more is True  # page 1 < 3

    def test_title_without_separator_keeps_full_string_as_title(self):
        payload = {
            "results": [{"id": 9, "type": "release", "title": "Untitled"}],
            "pagination": {"page": 1, "pages": 1},
        }
        with patch("httpx.get", return_value=_http_response(payload)):
            items, has_more = bss.search_discogs("x", page=1, per_page=5, token="tok")
        assert items[0].title == "Untitled"
        assert items[0].artist == ""
        assert has_more is False  # page 1 == pages 1

    def test_rejected_token_raises(self):
        with patch("httpx.get", return_value=_http_response({}, status_code=401)):
            with pytest.raises(bss.ProviderSearchError):
                bss.search_discogs("x", page=1, per_page=5, token="bad")

    def test_server_error_raises(self):
        with patch(
            "httpx.get", return_value=_http_response({}, status_code=500, text="boom")
        ):
            with pytest.raises(bss.ProviderSearchError):
                bss.search_discogs("x", page=1, per_page=5, token="tok")


class TestSpotifySearch:
    def test_uses_plugin_token_and_parses(self):
        plugin = MagicMock()
        plugin.access_token = "tok"
        plugin.search_url = "https://api.spotify.com/v1/search"
        payload = {
            "albums": {
                "items": [
                    {
                        "id": "sp1",
                        "name": "Random Access Memories",
                        "artists": [{"name": "Daft Punk"}],
                        "release_date": "2013-05-17",
                        "total_tracks": 13,
                        "images": [{"url": "big"}, {"url": "small"}],
                    }
                ],
                "total": 1,
            }
        }
        with patch("beetsplug.spotify.SpotifyPlugin", return_value=plugin), patch(
            "httpx.get", return_value=_http_response(payload)
        ):
            items, has_more = bss.search_spotify("x", page=1, per_page=5, config_path=None)

        assert len(items) == 1
        item = items[0]
        assert item.source_id == "sp1"
        assert item.artist == "Daft Punk"
        assert item.year == 2013
        assert item.track_count == 13
        assert item.external_url == "https://open.spotify.com/album/sp1"
        assert item.cover_url == "small"  # smallest image
        assert has_more is False  # 0 + 1 < 1 is False

    def test_refreshes_token_on_401_then_retries(self):
        plugin = MagicMock()
        plugin.access_token = "stale"
        plugin.search_url = "https://api.spotify.com/v1/search"
        ok = _http_response({"albums": {"items": [], "total": 0}})
        unauthorized = _http_response({}, status_code=401)
        with patch("beetsplug.spotify.SpotifyPlugin", return_value=plugin), patch(
            "httpx.get", side_effect=[unauthorized, ok]
        ) as mock_get:
            items, has_more = bss.search_spotify("x", page=1, per_page=5, config_path=None)

        # 401 → one token refresh → one retry
        plugin._authenticate.assert_called_once()
        assert mock_get.call_count == 2
        assert items == []
        assert has_more is False


# ---------------------------------------------------------------------------
# Structured (field-scoped) queries — issue #69
# ---------------------------------------------------------------------------


class TestFieldQuery:
    def test_builds_both_fields_with_default_space_join(self):
        q = bss._field_query("Daft Punk", "Discovery", "artist", "album")
        assert q == 'artist:"Daft Punk" album:"Discovery"'

    def test_and_join_for_lucene(self):
        q = bss._field_query("Daft Punk", "Discovery", "artist", "release", join=" AND ")
        assert q == 'artist:"Daft Punk" AND release:"Discovery"'

    def test_single_field_only(self):
        assert bss._field_query("Daft Punk", None, "artist", "album") == 'artist:"Daft Punk"'
        assert bss._field_query("", "Discovery", "artist", "album") == 'album:"Discovery"'

    def test_empty_when_nothing_known(self):
        assert bss._field_query(None, None, "artist", "album") == ""
        assert bss._field_query("  ", "", "artist", "album") == ""

    def test_strips_embedded_quotes(self):
        q = bss._field_query('A"B', 'C"D', "artist", "album")
        assert q == 'artist:"AB" album:"CD"'


class TestStructuredProviderQueries:
    def test_musicbrainz_uses_lucene_field_query(self):
        with patch("httpx.get", return_value=_http_response({"releases": [], "count": 0})) as g:
            bss.search_musicbrainz("free text", 1, 5, artist="Daft Punk", album="Discovery")
        assert g.call_args.kwargs["params"]["query"] == 'artist:"Daft Punk" AND release:"Discovery"'

    def test_musicbrainz_falls_back_to_free_text(self):
        with patch("httpx.get", return_value=_http_response({"releases": [], "count": 0})) as g:
            bss.search_musicbrainz("daft punk discovery", 1, 5)
        assert g.call_args.kwargs["params"]["query"] == "daft punk discovery"

    def test_deezer_uses_advanced_query(self):
        with patch("httpx.get", return_value=_http_response({"data": [], "total": 0})) as g:
            bss.search_deezer("free text", 1, 5, artist="Daft Punk", album="Discovery")
        assert g.call_args.kwargs["params"]["q"] == 'artist:"Daft Punk" album:"Discovery"'

    def test_discogs_uses_separate_fields_not_q(self):
        payload = {"results": [], "pagination": {"page": 1, "pages": 1}}
        with patch("httpx.get", return_value=_http_response(payload)) as g:
            bss.search_discogs("free text", 1, 5, token="tok", artist="Daft Punk", album="Discovery")
        params = g.call_args.kwargs["params"]
        assert params["artist"] == "Daft Punk"
        assert params["release_title"] == "Discovery"
        assert "q" not in params

    def test_discogs_falls_back_to_q(self):
        payload = {"results": [], "pagination": {"page": 1, "pages": 1}}
        with patch("httpx.get", return_value=_http_response(payload)) as g:
            bss.search_discogs("daft punk", 1, 5, token="tok")
        params = g.call_args.kwargs["params"]
        assert params["q"] == "daft punk"
        assert "artist" not in params and "release_title" not in params

    def test_spotify_uses_field_filters(self):
        plugin = MagicMock()
        plugin.access_token = "tok"
        plugin.search_url = "https://api.spotify.com/v1/search"
        payload = {"albums": {"items": [], "total": 0}}
        with patch("beetsplug.spotify.SpotifyPlugin", return_value=plugin), patch(
            "httpx.get", return_value=_http_response(payload)
        ) as g:
            bss.search_spotify("free text", 1, 5, config_path=None, artist="Daft Punk", album="Discovery")
        assert g.call_args.kwargs["params"]["q"] == 'artist:"Daft Punk" album:"Discovery"'

    def test_search_all_providers_forwards_structured_terms(self):
        captured = {}

        def fake_mb(q, page, per_page, artist=None, album=None):
            captured["artist"] = artist
            captured["album"] = album
            return [], False

        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz"], "")), \
            patch.object(bss, "search_musicbrainz", side_effect=fake_mb):
            bss.search_all_providers(
                config_path=None, query="x", artist="Daft Punk", album="Discovery"
            )

        assert captured == {"artist": "Daft Punk", "album": "Discovery"}


# ---------------------------------------------------------------------------
# Result ranking (issue #112)
# ---------------------------------------------------------------------------


def _item(title="T", artist="A", track_count=None, source_id="x", provider="musicbrainz"):
    """Build a minimal SearchResultItem for ranking tests."""
    return SearchResultItem(
        provider=provider,
        source_id=source_id,
        title=title,
        artist=artist,
        year=None,
        track_count=track_count,
        external_url=f"https://example/{source_id}",
        cover_url=None,
    )


class TestNumbersIn:
    def test_extracts_distinct_digit_runs(self):
        assert bss._numbers_in("Die drei ??? 45") == {"45"}
        assert bss._numbers_in("Fünf Freunde 33 - Folge 33") == {"33"}
        assert bss._numbers_in("Vol. 2 (2009)") == {"2", "2009"}

    def test_empty_or_none(self):
        assert bss._numbers_in(None) == set()
        assert bss._numbers_in("") == set()
        assert bss._numbers_in("no digits here") == set()


class TestScoreItem:
    def test_number_match_in_title(self):
        assert bss._score_item(_item(title="Folge 45"), {"45"}, None) == bss._SCORE_NUMBER_MATCH

    def test_number_match_in_artist(self):
        item = _item(title="Folge", artist="Die drei ??? 45")
        assert bss._score_item(item, {"45"}, None) == bss._SCORE_NUMBER_MATCH

    def test_no_number_match(self):
        assert bss._score_item(_item(title="Folge 44"), {"45"}, None) == 0

    def test_substring_number_does_not_count(self):
        # "145" must not satisfy a query for "45" — findall tokenizes digit runs.
        assert bss._score_item(_item(title="Folge 145"), {"45"}, None) == 0

    def test_exact_track_count(self):
        assert bss._score_item(_item(track_count=12), set(), 12) == bss._SCORE_TRACK_COUNT_EXACT

    def test_near_track_count_either_side(self):
        assert bss._score_item(_item(track_count=13), set(), 12) == bss._SCORE_TRACK_COUNT_NEAR
        assert bss._score_item(_item(track_count=11), set(), 12) == bss._SCORE_TRACK_COUNT_NEAR

    def test_far_track_count_no_bonus(self):
        assert bss._score_item(_item(track_count=20), set(), 12) == 0

    def test_missing_track_count_no_bonus(self):
        assert bss._score_item(_item(track_count=None), set(), 12) == 0

    def test_signals_add_up(self):
        item = _item(title="Folge 45", track_count=12)
        assert bss._score_item(item, {"45"}, 12) == (
            bss._SCORE_NUMBER_MATCH + bss._SCORE_TRACK_COUNT_EXACT
        )


class TestRankResults:
    def test_noop_returns_same_list_without_signals(self):
        items = [_item(source_id="a"), _item(source_id="b")]
        assert bss._rank_results(items, set(), None) is items

    def test_track_count_match_floats_up_keeping_order(self):
        items = [
            _item(source_id="a", track_count=20),
            _item(source_id="b", track_count=12),  # exact match
            _item(source_id="c", track_count=99),
        ]
        ranked = bss._rank_results(items, set(), 12)
        assert [it.source_id for it in ranked] == ["b", "a", "c"]

    def test_number_match_floats_up(self):
        items = [
            _item(source_id="a", title="Folge 44"),
            _item(source_id="b", title="Folge 45"),
        ]
        ranked = bss._rank_results(items, {"45"}, None)
        assert [it.source_id for it in ranked] == ["b", "a"]

    def test_ties_keep_provider_order(self):
        items = [_item(source_id="a"), _item(source_id="b"), _item(source_id="c")]
        # nothing matches → all score 0 → stable sort preserves input order
        ranked = bss._rank_results(items, {"45"}, 12)
        assert [it.source_id for it in ranked] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Fan-out orchestration
# ---------------------------------------------------------------------------


class TestSearchAllProviders:
    def test_returns_all_providers_in_canonical_order(self):
        def fake_mb(q, page, per_page, artist=None, album=None):
            return [
                SearchResultItem(
                    provider="musicbrainz",
                    source_id="mb1",
                    title="Discovery",
                    artist="Daft Punk",
                    year=2001,
                    track_count=14,
                    external_url="https://musicbrainz.org/release/mb1",
                    cover_url=None,
                )
            ], False

        with patch.object(bss, "_read_search_config", return_value=(list(bss.DEFAULT_PLUGINS), "tok")), \
            patch.object(bss, "search_musicbrainz", side_effect=fake_mb), \
            patch.object(bss, "search_spotify", return_value=([], False)), \
            patch.object(bss, "search_deezer", return_value=([], False)), \
            patch.object(bss, "search_discogs", return_value=([], False)):
            resp = bss.search_all_providers(
                config_path="/x.yaml", query="daft punk", page=1, per_page=5
            )

        assert isinstance(resp, SearchCandidatesResponse)
        assert [g.provider for g in resp.providers] == bss.PROVIDERS
        mb = next(g for g in resp.providers if g.provider == "musicbrainz")
        assert mb.available is True
        assert mb.results[0].source_id == "mb1"

    def test_inactive_providers_marked_unavailable_and_not_called(self):
        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz", "deezer"], "")), \
            patch.object(bss, "search_musicbrainz", return_value=([], False)), \
            patch.object(bss, "search_deezer", return_value=([], False)), \
            patch.object(bss, "search_spotify") as sp, \
            patch.object(bss, "search_discogs") as dc:
            resp = bss.search_all_providers(config_path=None, query="x", page=1, per_page=5)

        groups = {g.provider: g for g in resp.providers}
        assert groups["spotify"].available is False
        assert groups["discogs"].available is False
        assert groups["spotify"].reason
        sp.assert_not_called()
        dc.assert_not_called()

    def test_provider_failure_is_isolated(self):
        with patch.object(bss, "_read_search_config", return_value=(list(bss.DEFAULT_PLUGINS), "tok")), \
            patch.object(bss, "search_musicbrainz", side_effect=RuntimeError("boom")), \
            patch.object(bss, "search_spotify", return_value=([], False)), \
            patch.object(bss, "search_deezer", return_value=([], False)), \
            patch.object(bss, "search_discogs", return_value=([], False)):
            resp = bss.search_all_providers(config_path=None, query="x", page=1, per_page=5)

        mb = next(g for g in resp.providers if g.provider == "musicbrainz")
        assert mb.available is True
        assert mb.results == []
        assert "Search failed" in mb.reason

    def test_overfetches_and_ranks_when_track_count_known(self):
        captured = {}

        def fake_mb(q, page, per_page, artist=None, album=None):
            captured["per_page"] = per_page
            return [
                SearchResultItem(
                    provider="musicbrainz", source_id="a", title="A", artist="X",
                    year=None, track_count=20, external_url="https://mb/a", cover_url=None,
                ),
                SearchResultItem(
                    provider="musicbrainz", source_id="b", title="B", artist="X",
                    year=None, track_count=12, external_url="https://mb/b", cover_url=None,
                ),
            ], False

        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz"], "")), \
            patch.object(bss, "search_musicbrainz", side_effect=fake_mb):
            resp = bss.search_all_providers(
                config_path=None, query="x", per_page=5, expected_tracks=12
            )

        # A known track count activates ranking, so the provider is over-fetched.
        assert captured["per_page"] == 5 * bss._SCORE_OVERFETCH
        mb = next(g for g in resp.providers if g.provider == "musicbrainz")
        # ...and the matching-track-count hit floats to the top.
        assert [it.source_id for it in mb.results] == ["b", "a"]

    def test_query_number_triggers_overfetch_and_ranking(self):
        captured = {}

        def fake_mb(q, page, per_page, artist=None, album=None):
            captured["per_page"] = per_page
            return [
                SearchResultItem(
                    provider="musicbrainz", source_id="a", title="Folge 44",
                    artist="Die drei ???", year=None, track_count=None,
                    external_url="https://mb/a", cover_url=None,
                ),
                SearchResultItem(
                    provider="musicbrainz", source_id="b", title="Folge 45",
                    artist="Die drei ???", year=None, track_count=None,
                    external_url="https://mb/b", cover_url=None,
                ),
            ], False

        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz"], "")), \
            patch.object(bss, "search_musicbrainz", side_effect=fake_mb):
            resp = bss.search_all_providers(
                config_path=None, query="die drei ??? 45", per_page=5
            )

        assert captured["per_page"] == 5 * bss._SCORE_OVERFETCH
        mb = next(g for g in resp.providers if g.provider == "musicbrainz")
        assert [it.source_id for it in mb.results] == ["b", "a"]

    def test_no_overfetch_or_reorder_without_signals(self):
        captured = {}

        def fake_mb(q, page, per_page, artist=None, album=None):
            captured["per_page"] = per_page
            return [
                SearchResultItem(
                    provider="musicbrainz", source_id="a", title="A", artist="X",
                    year=None, track_count=20, external_url="https://mb/a", cover_url=None,
                ),
                SearchResultItem(
                    provider="musicbrainz", source_id="b", title="B", artist="X",
                    year=None, track_count=12, external_url="https://mb/b", cover_url=None,
                ),
            ], False

        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz"], "")), \
            patch.object(bss, "search_musicbrainz", side_effect=fake_mb):
            resp = bss.search_all_providers(config_path=None, query="daft punk", per_page=5)

        # No query number and no expected track count → no over-fetch, native order kept.
        assert captured["per_page"] == 5
        mb = next(g for g in resp.providers if g.provider == "musicbrainz")
        assert [it.source_id for it in mb.results] == ["a", "b"]

    def test_providers_subset_limits_fanout_and_response(self):
        with patch.object(bss, "_read_search_config", return_value=(list(bss.DEFAULT_PLUGINS), "tok")), \
            patch.object(bss, "search_musicbrainz", return_value=([], False)) as mb, \
            patch.object(bss, "search_deezer", return_value=([], True)) as dz, \
            patch.object(bss, "search_spotify") as sp, \
            patch.object(bss, "search_discogs") as dc:
            resp = bss.search_all_providers(
                config_path=None,
                query="x",
                page=2,
                per_page=5,
                providers=["deezer", "musicbrainz"],
            )

        # Only the requested providers are searched and returned (canonical order).
        assert [g.provider for g in resp.providers] == ["musicbrainz", "deezer"]
        mb.assert_called_once()
        dz.assert_called_once()
        sp.assert_not_called()
        dc.assert_not_called()

    def test_providers_subset_keeps_unavailable_gating(self):
        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz"], "")), \
            patch.object(bss, "search_discogs") as dc:
            resp = bss.search_all_providers(
                config_path=None, query="x", providers=["discogs"]
            )

        assert [g.provider for g in resp.providers] == ["discogs"]
        assert resp.providers[0].available is False
        dc.assert_not_called()

    def test_provider_timeout_yields_timed_out_group(self):
        import time

        def slow(q, page, per_page, artist=None, album=None):
            time.sleep(1.0)
            return [], False

        with patch.object(bss, "_read_search_config", return_value=(["musicbrainz"], "")), \
            patch.object(bss, "search_musicbrainz", side_effect=slow):
            resp = bss.search_all_providers(
                config_path=None, query="x", page=1, per_page=5, timeout=0.2
            )

        mb = next(g for g in resp.providers if g.provider == "musicbrainz")
        assert mb.available is True
        assert mb.reason == "Search timed out."


class TestReadSearchConfig:
    def test_missing_config_falls_back_to_defaults(self):
        plugins, token = bss._read_search_config("/no/such/file.yaml")
        assert plugins == list(bss.DEFAULT_PLUGINS)
        assert token == ""

    def test_malformed_config_falls_back_to_defaults(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("plugins: [unterminated\n:::not yaml")
        plugins, token = bss._read_search_config(str(bad))
        assert plugins == list(bss.DEFAULT_PLUGINS)
        assert token == ""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_library():
    """TestClient whose DB yields a library with a config path."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    mock_library = MagicMock()
    mock_library.id = 1
    mock_library.slug = "test-library"
    mock_library.config_path = "/data/config/test.yaml"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = mock_library
    app.dependency_overrides[get_db] = lambda: db

    return TestClient(app), mock_library


def _sample_response():
    return SearchCandidatesResponse(
        query="daft punk",
        page=1,
        per_page=5,
        providers=[
            SearchProviderGroup(
                provider="musicbrainz",
                available=True,
                reason=None,
                has_more=True,
                results=[
                    SearchResultItem(
                        provider="musicbrainz",
                        source_id="mb1",
                        title="Discovery",
                        artist="Daft Punk",
                        year=2001,
                        track_count=14,
                        external_url="https://musicbrainz.org/release/mb1",
                        cover_url=None,
                    )
                ],
            ),
            SearchProviderGroup(
                provider="discogs",
                available=False,
                reason="Discogs search requires a personal access token.",
                has_more=False,
                results=[],
            ),
        ],
    )


class TestSearchEndpoint:
    def test_returns_camelcase_results(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "daft punk", "page": 1, "perPage": 5},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "daft punk"
        assert body["perPage"] == 5
        providers = {p["provider"]: p for p in body["providers"]}
        mb = providers["musicbrainz"]
        assert mb["hasMore"] is True
        assert mb["results"][0]["externalUrl"] == "https://musicbrainz.org/release/mb1"
        assert mb["results"][0]["sourceId"] == "mb1"
        assert mb["results"][0]["trackCount"] == 14
        # unavailable provider preserved with reason
        assert providers["discogs"]["available"] is False
        assert providers["discogs"]["reason"]
        # endpoint forwards the library's config path
        mock_search.assert_called_once()
        assert mock_search.call_args.kwargs["config_path"] == "/data/config/test.yaml"

    def test_forwards_pagination_params_via_alias(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x", "page": 3, "perPage": 12},
            )
        assert resp.status_code == 200
        # The perPage query alias must bind to per_page, and page must forward.
        assert mock_search.call_args.kwargs["per_page"] == 12
        assert mock_search.call_args.kwargs["page"] == 3

    def test_forwards_providers_filter(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x", "providers": "Deezer, spotify"},
            )
        assert resp.status_code == 200
        # Names are normalized (case/whitespace) before being forwarded.
        assert mock_search.call_args.kwargs["providers"] == ["deezer", "spotify"]

    def test_forwards_structured_artist_album(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x", "artist": "Daft Punk", "album": "Discovery"},
            )
        assert resp.status_code == 200
        assert mock_search.call_args.kwargs["artist"] == "Daft Punk"
        assert mock_search.call_args.kwargs["album"] == "Discovery"

    def test_structured_terms_default_to_none(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x"},
            )
        assert resp.status_code == 200
        assert mock_search.call_args.kwargs["artist"] is None
        assert mock_search.call_args.kwargs["album"] is None

    def test_forwards_expected_tracks_via_alias(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x", "expectedTracks": 12},
            )
        assert resp.status_code == 200
        assert mock_search.call_args.kwargs["expected_tracks"] == 12

    def test_expected_tracks_defaults_to_none(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x"},
            )
        assert resp.status_code == 200
        assert mock_search.call_args.kwargs["expected_tracks"] is None

    def test_no_providers_param_forwards_none(self, client_with_library):
        client, _ = client_with_library
        with patch(
            "app.api.routes.beets_autotag.search_all_providers",
            return_value=_sample_response(),
        ) as mock_search:
            resp = client.get(
                "/api/v1/libraries/test-library/beets/search-candidates",
                params={"q": "x"},
            )
        assert resp.status_code == 200
        assert mock_search.call_args.kwargs["providers"] is None

    def test_unknown_provider_is_422(self, client_with_library):
        client, _ = client_with_library
        resp = client.get(
            "/api/v1/libraries/test-library/beets/search-candidates",
            params={"q": "x", "providers": "deezer,napster"},
        )
        assert resp.status_code == 422
        assert "napster" in resp.json()["detail"]

    def test_empty_providers_param_is_422(self, client_with_library):
        client, _ = client_with_library
        resp = client.get(
            "/api/v1/libraries/test-library/beets/search-candidates",
            params={"q": "x", "providers": " , "},
        )
        assert resp.status_code == 422

    def test_per_page_over_max_is_422(self, client_with_library):
        client, _ = client_with_library
        resp = client.get(
            "/api/v1/libraries/test-library/beets/search-candidates",
            params={"q": "x", "perPage": 99},
        )
        assert resp.status_code == 422

    def test_missing_query_is_422(self, client_with_library):
        client, _ = client_with_library
        resp = client.get(
            "/api/v1/libraries/test-library/beets/search-candidates"
        )
        assert resp.status_code == 422

    def test_library_not_found_is_404(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        resp = client.get(
            "/api/v1/libraries/missing/beets/search-candidates",
            params={"q": "x"},
        )
        assert resp.status_code == 404
