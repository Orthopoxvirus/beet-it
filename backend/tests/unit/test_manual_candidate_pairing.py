"""Unit tests for manual-candidate track pairing (issue #56).

Manually resolved candidates (Spotify/Deezer/Discogs/MusicBrainz links) must
pair local files to candidate tracks with beets' distance-based assignment —
the same matcher the automatic analysis path uses — so files without a
``tracknumber`` tag still pair by duration.
"""

import pytest

from app.api.routes.beets_autotag import (
    _build_manual_track_change,
    _pair_local_tracks,
)
from app.services.beets_autotag_service import (
    LocalAlbumData,
    LocalTrackData,
    parse_track_number_from_filename,
)


def _album(tracks):
    return LocalAlbumData(path="/import/album", artist=None, album=None, tracks=tracks)


class TestPairLocalTracks:
    """Tests for _pair_local_tracks."""

    def test_untagged_files_pair_by_duration(self):
        """Regression for #56: files with no tags at all (no title, no
        tracknumber) must still pair with candidate tracks via duration."""
        locals_ = [
            LocalTrackData(path="/a/01-stay.flac", title=None, track_num=None, length=185.0),
            LocalTrackData(path="/a/02-somewhere_west.flac", title=None, track_num=None, length=77.0),
            LocalTrackData(path="/a/03-moons_tides.flac", title=None, track_num=None, length=241.0),
        ]
        candidate_rows = [
            {"title": "Stay", "length": 185.0, "index": 1},
            {"title": "Somewhere West", "length": 77.0, "index": 2},
            {"title": "Moons & Tides", "length": 241.0, "index": 3},
            {"title": "Cycling", "length": 274.0, "index": 4},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert len(paired) == 4
        assert paired[0] is locals_[0]
        assert paired[1] is locals_[1]
        assert paired[2] is locals_[2]
        assert paired[3] is None  # genuinely new track

    def test_reordered_locals_pair_by_title(self):
        """Tagged titles win even when local file order disagrees."""
        locals_ = [
            LocalTrackData(path="/a/b.flac", title="Beta", track_num=None, length=200.0),
            LocalTrackData(path="/a/a.flac", title="Alpha", track_num=None, length=200.0),
        ]
        candidate_rows = [
            {"title": "Alpha", "length": 200.0, "index": 1},
            {"title": "Beta", "length": 200.0, "index": 2},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert paired[0] is locals_[1]
        assert paired[1] is locals_[0]

    def test_no_local_tracks(self):
        candidate_rows = [{"title": "Solo", "length": 100.0, "index": 1}]
        assert _pair_local_tracks(_album([]), candidate_rows) == [None]

    def test_no_candidate_tracks(self):
        locals_ = [LocalTrackData(path="/a/1.flac", title=None, track_num=1, length=100.0)]
        assert _pair_local_tracks(_album(locals_), []) == []

    def test_falls_back_to_track_number_when_matcher_fails(self, monkeypatch):
        """If beets' assignment blows up, pairing degrades to tag track numbers.

        Locals are deliberately only partially numbered — a fully numbered
        album routes to the ordered alignment and never reaches the beets
        matcher (#182).
        """
        import beets.autotag.match

        def boom(items, tracks):
            raise RuntimeError("matcher unavailable")

        monkeypatch.setattr(beets.autotag.match, "assign_items", boom)

        locals_ = [
            LocalTrackData(path="/a/1.flac", title="One", track_num=1, length=100.0),
            LocalTrackData(path="/a/2.flac", title="Two", track_num=None, length=110.0),
        ]
        candidate_rows = [
            {"title": "Eins", "length": 100.0, "index": 1},
            {"title": "Zwei", "length": 110.0, "index": 2},
            {"title": "Drei", "length": 120.0, "index": 3},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert paired[0] is locals_[0]
        assert paired[1] is None  # no tag number to fall back to
        assert paired[2] is None


class TestBuildManualTrackChange:
    """Tests for _build_manual_track_change."""

    def test_paired_local_fills_fields(self):
        local = LocalTrackData(
            path="/a/01-stay.flac", title=None, track_num=None, length=185.0
        )
        tc = _build_manual_track_change(
            index=1, candidate_title="Stay", candidate_length=185.0, local_track=local
        )
        assert tc.local_title is None
        assert tc.local_path == "/a/01-stay.flac"
        assert tc.local_length == 185.0
        assert tc.candidate_title == "Stay"

    def test_unpaired_leaves_local_fields_none(self):
        tc = _build_manual_track_change(
            index=4, candidate_title="Cycling", candidate_length=274.0, local_track=None
        )
        assert tc.local_title is None
        assert tc.local_path is None
        assert tc.local_length is None


class TestParseTrackNumberFromFilename:
    """Tests for parse_track_number_from_filename."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("01-ezra_george-stay.flac", 1),
            ("12 - Some Title.mp3", 12),
            ("3. Title.ogg", 3),
            ("101 Title.flac", 101),
            ("2020 - Year Prefixed Song.flac", None),  # 4 digits = not a track
            ("Title Without Number.flac", None),
            ("00-hidden.flac", None),  # track 0 is not a real number
        ],
    )
    def test_parsing(self, filename, expected):
        assert parse_track_number_from_filename(filename) == expected


class TestLargeReleasePairing:
    """Tests for the ordered duration alignment on very large releases (#175).

    A 500-file audiobook rip against a 636-track Deezer candidate must pair
    within the resolution timeout. Above BEETS_LARGE_PAIRING_THRESHOLD
    local×candidate pairs, _pair_local_tracks skips beets' assign_items (full
    track_distance cost matrix + per-file reads — the wall) and aligns both
    ordered sequences by duration instead.
    """

    @staticmethod
    def _chapter_length(j: int) -> float:
        # Deterministic pseudo-varied chapter durations, period 240.
        return 60.0 + float((j * 37) % 240)

    def _forbid_beets_matcher(self, monkeypatch):
        import beets.autotag.match

        def boom(items, tracks):
            raise AssertionError(
                "assign_items must not run for a large release"
            )

        monkeypatch.setattr(beets.autotag.match, "assign_items", boom)

    def test_audiobook_scale_pairs_fast_without_beets_matcher(self, monkeypatch):
        """Tintenblut shape: ~500 local chapters vs 636 candidate tracks.

        The provider segments chapters differently — every fifth candidate
        track has no local counterpart. The alignment must recover the exact
        correspondence, leave the surplus candidate tracks unpaired, and stay
        far inside the resolution timeout (this ran 180s+ via assign_items).
        """
        import time

        self._forbid_beets_matcher(monkeypatch)

        m = 636
        candidate_rows = [
            {"title": f"Kapitel {j + 1}", "length": self._chapter_length(j), "index": j + 1}
            for j in range(m)
        ]
        # Locals mirror the candidates except every 5th chapter is missing.
        kept = [j for j in range(m) if j % 5 != 2]
        locals_ = [
            LocalTrackData(
                path=f"/import/tintenblut/{pos + 1:03d} Kapitel.flac",
                title=None,
                track_num=pos + 1,
                length=self._chapter_length(j),
            )
            for pos, j in enumerate(kept)
        ]
        assert len(locals_) * m > 40_000  # sanity: above the default threshold

        start = time.monotonic()
        paired = _pair_local_tracks(_album(locals_), candidate_rows)
        elapsed = time.monotonic() - start

        assert elapsed < 20.0, f"alignment took {elapsed:.1f}s"
        assert len(paired) == m
        by_kept = {j: locals_[pos] for pos, j in enumerate(kept)}
        mismatches = [
            j for j in range(m) if paired[j] is not by_kept.get(j)
        ]
        assert not mismatches, f"misaligned candidate rows: {mismatches[:10]}"

    def test_large_release_without_durations_pairs_positionally(self, monkeypatch):
        """No durations anywhere: alignment degrades to playback order."""
        self._forbid_beets_matcher(monkeypatch)

        n = 300
        locals_ = [
            LocalTrackData(
                path=f"/import/book/{i + 1:03d}.mp3",
                title=None,
                track_num=i + 1,
                length=None,
            )
            for i in range(n)
        ]
        candidate_rows = [
            {"title": f"Teil {j + 1}", "length": None, "index": j + 1}
            for j in range(n)
        ]
        assert n * n > 40_000

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert paired == locals_

    def test_untagged_locals_align_by_natural_filename_order(self, monkeypatch):
        """Without usable track numbers the filename sort must be natural:
        chapter 10 sorts after chapter 9, not after chapter 1."""
        monkeypatch.setenv("BEETS_LARGE_PAIRING_THRESHOLD", "1")
        self._forbid_beets_matcher(monkeypatch)

        # Deliberately unpadded filenames in scrambled lexical order.
        locals_ = [
            LocalTrackData(path=f"/b/Kapitel {i}.flac", title=None, track_num=None, length=None)
            for i in (1, 10, 2, 9)
        ]
        candidate_rows = [
            {"title": f"Kapitel {j}", "length": None, "index": pos + 1}
            for pos, j in enumerate((1, 2, 9, 10))
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert [t.path for t in paired] == [
            "/b/Kapitel 1.flac",
            "/b/Kapitel 2.flac",
            "/b/Kapitel 9.flac",
            "/b/Kapitel 10.flac",
        ]

    def test_threshold_env_override(self, monkeypatch):
        """BEETS_LARGE_PAIRING_THRESHOLD routes even tiny albums to the
        ordered alignment (and an invalid value keeps the default)."""
        from app.services import candidate_resolvers

        monkeypatch.setenv("BEETS_LARGE_PAIRING_THRESHOLD", "nope")
        assert (
            candidate_resolvers._large_pairing_threshold()
            == candidate_resolvers.DEFAULT_LARGE_PAIRING_THRESHOLD
        )

        monkeypatch.setenv("BEETS_LARGE_PAIRING_THRESHOLD", "1")
        self._forbid_beets_matcher(monkeypatch)
        locals_ = [
            LocalTrackData(path="/a/1.flac", title=None, track_num=1, length=100.0),
            LocalTrackData(path="/a/2.flac", title=None, track_num=2, length=200.0),
        ]
        candidate_rows = [
            {"title": "Eins", "length": 100.0, "index": 1},
            {"title": "Zwei", "length": 200.0, "index": 2},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert paired == locals_

    def test_small_release_still_uses_beets_matcher(self, monkeypatch):
        """Below the threshold nothing changes: assign_items still pairs."""
        import beets.autotag.match

        calls = []
        original = beets.autotag.match.assign_items

        def spy(items, tracks):
            calls.append(len(items))
            return original(items, tracks)

        monkeypatch.setattr(beets.autotag.match, "assign_items", spy)

        locals_ = [
            LocalTrackData(path="/a/1.flac", title=None, track_num=None, length=185.0),
        ]
        candidate_rows = [{"title": "Stay", "length": 185.0, "index": 1}]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert calls == [1]
        assert paired == locals_

    def test_alignment_failure_falls_back_to_track_numbers(self, monkeypatch):
        """A blown-up alignment degrades to tag-number pairing, never to the
        (timeout-eating) beets matcher."""
        from app.services import candidate_resolvers

        monkeypatch.setenv("BEETS_LARGE_PAIRING_THRESHOLD", "1")
        self._forbid_beets_matcher(monkeypatch)

        def boom(local_album, candidate_rows):
            raise RuntimeError("alignment exploded")

        monkeypatch.setattr(
            candidate_resolvers, "_pair_large_release_by_order", boom
        )

        locals_ = [
            LocalTrackData(path="/a/1.flac", title=None, track_num=1, length=100.0),
            LocalTrackData(path="/a/2.flac", title=None, track_num=2, length=110.0),
        ]
        candidate_rows = [
            {"title": "Eins", "length": 100.0, "index": 1},
            {"title": "Zwei", "length": 110.0, "index": 2},
            {"title": "Drei", "length": 120.0, "index": 3},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert paired[0] is locals_[0]
        assert paired[1] is locals_[1]
        assert paired[2] is None


class TestOrderedReleaseBelowThreshold:
    """Ordered albums use the monotonic alignment at ANY size (#182).

    Repro shape: *Das magische Messer*, 163 filename-titled chapters vs a
    163-track MusicBrainz candidate — 26 569 pairs, below the 40k threshold.
    Titles share no similarity, so beets' unconstrained matcher assigns by
    duration alone and scrambles chapter order.
    """

    def _forbid_beets_matcher(self, monkeypatch):
        import beets.autotag.match

        def boom(items, tracks):
            raise AssertionError(
                "assign_items must not run for a sequentially ordered release"
            )

        monkeypatch.setattr(beets.autotag.match, "assign_items", boom)

    def test_ordered_audiobook_below_threshold_pairs_in_order(self, monkeypatch):
        self._forbid_beets_matcher(monkeypatch)

        n = 163
        assert n * n < 40_000  # sanity: below the default threshold
        # Near-identical durations — exactly the shape that makes a
        # duration-similarity assignment scramble chapters.
        lengths = [300.0 + (i % 7) * 0.5 for i in range(n)]
        locals_ = [
            LocalTrackData(
                path=f"/import/messer/DasmagischeMesser_{i + 1:03d}.mp3",
                title=f"DasmagischeMesser_{i + 1:03d}",
                track_num=i + 1,
                length=lengths[i],
            )
            for i in range(n)
        ]
        candidate_rows = [
            {"title": f"Kapitel {j + 1}", "length": lengths[j], "index": j + 1}
            for j in range(n)
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        mismatches = [j for j in range(n) if paired[j] is not locals_[j]]
        assert not mismatches, f"scrambled candidate rows: {mismatches[:10]}"

    def test_ordered_multi_disc_pairs_in_disc_order(self, monkeypatch):
        """Per-disc numbering (repeating track numbers) also counts as
        ordered when the (disc, number) pairs are unique."""
        self._forbid_beets_matcher(monkeypatch)

        locals_ = [
            LocalTrackData(path="/b/CD2/01.mp3", title=None, track_num=1, length=100.0, disc=2),
            LocalTrackData(path="/b/CD1/01.mp3", title=None, track_num=1, length=90.0, disc=1),
            LocalTrackData(path="/b/CD1/02.mp3", title=None, track_num=2, length=95.0, disc=1),
        ]
        candidate_rows = [
            {"title": "Teil 1", "length": 90.0, "index": 1},
            {"title": "Teil 2", "length": 95.0, "index": 2},
            {"title": "Teil 3", "length": 100.0, "index": 3},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert paired[0] is locals_[1]
        assert paired[1] is locals_[2]
        assert paired[2] is locals_[0]

    def test_duplicate_numbers_without_disc_still_use_beets_matcher(self, monkeypatch):
        """Colliding track numbers = no inherent order → beets matcher."""
        import beets.autotag.match

        calls = []
        original = beets.autotag.match.assign_items

        def spy(items, tracks):
            calls.append(len(items))
            return original(items, tracks)

        monkeypatch.setattr(beets.autotag.match, "assign_items", spy)

        locals_ = [
            LocalTrackData(path="/a/x.flac", title="Alpha", track_num=1, length=100.0),
            LocalTrackData(path="/a/y.flac", title="Beta", track_num=1, length=200.0),
        ]
        candidate_rows = [
            {"title": "Alpha", "length": 100.0, "index": 1},
            {"title": "Beta", "length": 200.0, "index": 2},
        ]

        paired = _pair_local_tracks(_album(locals_), candidate_rows)

        assert calls == [2]
        assert paired == locals_


class TestPlaybackOrderMultiDisc:
    """Multi-disc local ordering for the large-release alignment (#180)."""

    def test_disc_grouping_beats_filename_interleave(self):
        """Per-disc track numbers repeat, so ordering must group by disc —
        a bare filename sort would put CD 2 track 1 before CD 1 track 2."""
        from app.services.candidate_resolvers import _locals_in_playback_order

        tracks = [
            LocalTrackData(path="/imp/Box/CD 02/01.mp3", title=None, track_num=1, length=None, disc=2),
            LocalTrackData(path="/imp/Box/CD 01/02.mp3", title=None, track_num=2, length=None, disc=1),
            LocalTrackData(path="/imp/Box/CD 01/01.mp3", title=None, track_num=1, length=None, disc=1),
        ]

        ordered = _locals_in_playback_order(_album(tracks))

        assert [(t.disc, t.track_num) for t in ordered] == [(1, 1), (1, 2), (2, 1)]

    def test_flat_unique_numbers_unchanged(self):
        from app.services.candidate_resolvers import _locals_in_playback_order

        tracks = [
            LocalTrackData(path="/imp/A/02.mp3", title=None, track_num=2, length=None),
            LocalTrackData(path="/imp/A/01.mp3", title=None, track_num=1, length=None),
        ]

        ordered = _locals_in_playback_order(_album(tracks))

        assert [t.track_num for t in ordered] == [1, 2]
