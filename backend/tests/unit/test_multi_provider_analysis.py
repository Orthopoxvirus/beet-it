"""Unit tests for multi-provider analysis augmentation (issue #76).

The native beets autotagger surfaces only MusicBrainz candidates. These tests
cover the helpers that also query Spotify/Deezer/Discogs (the same path the
manual dialog uses), score the hits comparably, dedup them against the
autotagger results, and merge everything into one ranked candidate list.
"""

from unittest.mock import patch

import pytest

from app.schemas.beets_autotag import (
    Candidate,
    CandidateTrack,
    MetadataChange,
    TrackChange,
)
from app.schemas.beets_search import (
    SearchCandidatesResponse,
    SearchProviderGroup,
    SearchResultItem,
)
from app.services.beets_autotag_service import (
    BeetsAutotagService,
    CandidateData,
    CandidateTrackData,
    LocalAlbumData,
    LocalTrackData,
)


@pytest.fixture
def service():
    return BeetsAutotagService(timeout=30)


def _local_album(artist, album, n_tracks=12):
    return LocalAlbumData(
        path="/import/album",
        artist=artist,
        album=album,
        tracks=[
            LocalTrackData(path=f"/import/album/{i}.flac", title=str(i), track_num=i, length=180.0)
            for i in range(1, n_tracks + 1)
        ],
    )


def _candidate_data(source, source_id, similarity, artist="A", album="B"):
    return CandidateData(
        source=source,
        source_id=source_id,
        similarity=similarity,
        artist=artist,
        album=album,
        year=None,
        label=None,
        country=None,
        media=None,
        tracks=[],
        changes=[],
        track_changes=[],
    )


def _resolved_candidate(source, source_id, artist, album, n_tracks=12):
    """A Candidate as the resolvers return it: similarity=1.0, is_manual=True."""
    return Candidate(
        source=source,
        source_id=source_id,
        similarity=1.0,
        artist=artist,
        album=album,
        year=2019,
        label=None,
        country=None,
        media=None,
        tracks=[
            CandidateTrack(
                index=i,
                title=f"Track {i}",
                length=180.0,
                local_title=str(i),
                local_path=f"/import/album/{i}.flac",
                changes=[MetadataChange(field="title", from_value=str(i), to_value=f"Track {i}")],
            )
            for i in range(1, n_tracks + 1)
        ],
        changes=[MetadataChange(field="artist", from_value="x", to_value=artist)],
        track_changes=[
            TrackChange(index=i, local_title=str(i), candidate_title=f"Track {i}")
            for i in range(1, n_tracks + 1)
        ],
        is_manual=True,
    )


# --- scoring ---------------------------------------------------------------


class TestScoreProviderFields:
    def test_exact_match_scores_one(self, service):
        la = _local_album("Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical")
        score = service._score_provider_fields(
            la, "Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical", 12
        )
        assert score == pytest.approx(1.0)

    def test_wrong_match_scores_low(self, service):
        la = _local_album("Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical")
        score = service._score_provider_fields(
            la, "Ingo Siegner", "Kokosnuss – Hörspiel 5", 30
        )
        # A bad match must rank well below an exact one.
        assert score < 0.6

    def test_exact_outranks_wrong(self, service):
        """The issue scenario: exact provider hit must beat the bad MB hit."""
        la = _local_album("Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical")
        good = service._score_provider_fields(
            la, "Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical", 12
        )
        bad = service._score_provider_fields(la, "Ingo Siegner", "Hörbuch", 5)
        assert good > bad

    def test_missing_local_artist_does_not_crash(self, service):
        la = _local_album(None, "Some Album")
        score = service._score_provider_fields(la, "Whoever", "Some Album", 12)
        # Only album + track count contribute; exact album still scores high.
        assert score > 0.8

    def test_no_local_metadata_scores_zero(self, service):
        la = LocalAlbumData(path="/x", artist=None, album=None, tracks=[])
        assert service._score_provider_fields(la, "A", "B", None) == 0.0

    def test_track_count_mismatch_lowers_score(self, service):
        la = _local_album("Artist", "Album", n_tracks=12)
        same = service._score_provider_fields(la, "Artist", "Album", 12)
        off = service._score_provider_fields(la, "Artist", "Album", 30)
        assert same > off


# --- conversion ------------------------------------------------------------


class TestCandidateToData:
    def test_converts_and_applies_similarity(self, service):
        cand = _resolved_candidate("Spotify", "spid", "Theater Lichtermeer", "Das Musical", n_tracks=2)
        data = service._candidate_to_data(cand, 0.91)
        assert isinstance(data, CandidateData)
        assert data.source == "Spotify"
        assert data.source_id == "spid"
        assert data.similarity == 0.91  # not the resolver's hardcoded 1.0
        assert len(data.tracks) == 2
        # changes flattened to plain dicts (task serializer dumps these to JSON)
        assert all(isinstance(c, dict) for c in data.changes)
        assert data.changes[0]["field"] == "artist"
        assert all(isinstance(t, CandidateTrackData) for t in data.tracks)
        assert all(isinstance(c, dict) for c in data.tracks[0].changes)
        assert all(isinstance(tc, dict) for tc in data.track_changes)


# --- merge / dedup ---------------------------------------------------------


class TestMergeCandidates:
    def test_sorts_by_similarity_descending(self, service):
        auto = [_candidate_data("MusicBrainz", "mb1", 0.45)]
        prov = [_candidate_data("Spotify", "sp1", 0.95)]
        merged = service._merge_candidates(auto, prov)
        assert [c.source for c in merged] == ["Spotify", "MusicBrainz"]

    def test_dedups_musicbrainz_autotag_vs_direct(self, service):
        """Same MB release from autotagger and direct API must appear once."""
        auto = [_candidate_data("MusicBrainz", "dup", 0.45)]
        prov = [_candidate_data("musicbrainz", "dup", 0.99)]  # different casing too
        merged = service._merge_candidates(auto, prov)
        assert len(merged) == 1
        # Autotagger entry wins (it carries beets' track mapping).
        assert merged[0].similarity == 0.45

    def test_provider_only_candidates_appended(self, service):
        auto = []
        prov = [_candidate_data("Deezer", "dz1", 0.8)]
        merged = service._merge_candidates(auto, prov)
        assert len(merged) == 1
        assert merged[0].source == "Deezer"

    def test_candidates_without_source_id_not_deduped(self, service):
        auto = [_candidate_data("MusicBrainz", None, 0.5)]
        prov = [_candidate_data("Spotify", None, 0.6)]
        merged = service._merge_candidates(auto, prov)
        assert len(merged) == 2


# --- resolve search results ------------------------------------------------


def _search_response(items_by_provider):
    groups = [
        SearchProviderGroup(
            provider=prov,
            available=True,
            results=[
                SearchResultItem(
                    provider=prov,
                    source_id=sid,
                    title=title,
                    artist=artist,
                    track_count=tc,
                    external_url=f"https://example.com/{prov}/{sid}",
                )
                for (sid, title, artist, tc) in items
            ],
        )
        for prov, items in items_by_provider.items()
    ]
    return SearchCandidatesResponse(query="q", page=1, per_page=3, providers=groups)


class TestResolveSearchResults:
    def test_skips_hits_already_in_autotag(self, service):
        la = _local_album("Artist", "Album")
        existing = [_candidate_data("MusicBrainz", "mbid", 0.45)]
        resp = _search_response(
            {"musicbrainz": [("mbid", "Album", "Artist", 12)]}  # already present
        )
        with patch(
            "app.services.candidate_resolvers.resolve_manual_candidate"
        ) as mock_resolve:
            out, degraded = service._resolve_search_results(resp, la, existing, None)
        mock_resolve.assert_not_called()
        assert out == []
        assert degraded is False

    def test_resolves_and_scores_new_hit(self, service):
        la = _local_album("Theater Lichtermeer", "Das Musical")
        resp = _search_response(
            {"spotify": [("sp1", "Das Musical", "Theater Lichtermeer", 12)]}
        )
        resolved = _resolved_candidate("Spotify", "sp1", "Theater Lichtermeer", "Das Musical")
        with patch(
            "app.services.candidate_resolvers.resolve_manual_candidate",
            return_value=resolved,
        ):
            out, degraded = service._resolve_search_results(resp, la, [], None)
        assert len(out) == 1
        assert degraded is False
        assert out[0].source == "Spotify"
        # Real computed similarity, not the resolver's 1.0.
        assert 0.9 <= out[0].similarity <= 1.0

    def test_caps_number_of_resolves(self, service):
        la = _local_album("Artist", "Album")
        many = {
            "deezer": [(f"d{i}", "Album", "Artist", 12) for i in range(10)],
        }
        resp = _search_response(many)
        calls = []

        def fake_resolve(_self, _path, provider, source_id, config_path=None):
            calls.append(source_id)
            return _resolved_candidate(provider.title(), source_id, "Artist", "Album")

        with patch(
            "app.services.candidate_resolvers.resolve_manual_candidate",
            side_effect=fake_resolve,
        ):
            out, degraded = service._resolve_search_results(resp, la, [], None)
        assert len(calls) == service._MAX_PROVIDER_RESOLVES
        assert len(out) == service._MAX_PROVIDER_RESOLVES
        assert degraded is False

    def test_failed_resolve_is_skipped(self, service):
        la = _local_album("Artist", "Album")
        resp = _search_response(
            {
                "spotify": [("ok", "Album", "Artist", 12)],
                "deezer": [("bad", "Album", "Artist", 12)],
            }
        )

        def fake_resolve(_self, _path, provider, source_id, config_path=None):
            if source_id == "bad":
                raise RuntimeError("provider down")
            return _resolved_candidate(provider.title(), source_id, "Artist", "Album")

        with patch(
            "app.services.candidate_resolvers.resolve_manual_candidate",
            side_effect=fake_resolve,
        ):
            out, degraded = service._resolve_search_results(resp, la, [], None)
        assert [c.source_id for c in out] == ["ok"]
        # One hit still resolved — the run is usable, not degraded.
        assert degraded is False

    def test_all_resolves_failing_is_degraded(self, service):
        la = _local_album("Artist", "Album")
        resp = _search_response(
            {
                "spotify": [("bad1", "Album", "Artist", 12)],
                "deezer": [("bad2", "Album", "Artist", 12)],
            }
        )

        with patch(
            "app.services.candidate_resolvers.resolve_manual_candidate",
            side_effect=RuntimeError("provider down"),
        ):
            out, degraded = service._resolve_search_results(resp, la, [], None)
        assert out == []
        assert degraded is True


# --- end-to-end analyze_album ----------------------------------------------


class TestAnalyzeAlbumIntegration:
    def test_provider_exact_match_outranks_bad_autotag(self, service, tmp_path):
        """The whole point of #76: an exact Spotify hit beats a poor MB hit."""
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        la = _local_album("Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical")

        bad_mb = _candidate_data(
            "MusicBrainz", "mb-bad", 0.457, artist="Ingo Siegner", album="Hörbuch"
        )
        resp = _search_response(
            {
                "spotify": [
                    ("sp1", "Der kleine Drache Kokosnuss – Das Musical", "Theater Lichtermeer", 12)
                ]
            }
        )
        resolved = _resolved_candidate(
            "Spotify", "sp1", "Theater Lichtermeer", "Der kleine Drache Kokosnuss – Das Musical"
        )

        with patch.object(service, "_read_local_album", return_value=la), patch.object(
            service, "_run_beets_analysis", return_value=[bad_mb]
        ), patch.object(service, "_search_providers", return_value=resp), patch(
            "app.services.candidate_resolvers.resolve_manual_candidate",
            return_value=resolved,
        ):
            _local, candidates, _at, degraded = service.analyze_album(
                "lib", str(album_dir), None
            )

        assert len(candidates) == 2
        assert degraded is False
        assert candidates[0].source == "Spotify"  # ranked first
        assert candidates[0].similarity > candidates[1].similarity

    def test_provider_failure_falls_back_to_autotag(self, service, tmp_path):
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        la = _local_album("Artist", "Album")
        mb = _candidate_data("MusicBrainz", "mb1", 0.8)

        with patch.object(service, "_read_local_album", return_value=la), patch.object(
            service, "_run_beets_analysis", return_value=[mb]
        ), patch.object(
            service, "_search_providers", side_effect=RuntimeError("search exploded")
        ):
            _local, candidates, _at, degraded = service.analyze_album(
                "lib", str(album_dir), None
            )

        # Autotagger result still returned despite the provider path blowing up,
        # but the run is flagged degraded so it won't be long-term-cached.
        assert len(candidates) == 1
        assert candidates[0].source == "MusicBrainz"
        assert degraded is True
