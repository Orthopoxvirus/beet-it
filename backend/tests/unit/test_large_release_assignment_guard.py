"""Unit tests for the beets assign_items size guard (#175, analyze path).

The automatic analysis runs beets' ``tag_album``, which pairs local items
against every candidate's tracklist via ``assign_items`` — a full O(n·m)
``track_distance`` cost matrix. One 600-track MusicBrainz/Deezer candidate is
enough to eat the whole 30s analysis timeout on a 500-file audiobook.
``install_large_release_assignment_guard`` wraps ``assign_items`` module-wide
with the same ordered duration alignment the manual resolution path uses;
small releases keep delegating to the original.
"""

import time

import pytest

from app.services.candidate_resolvers import (
    _assign_items_by_order,
    install_large_release_assignment_guard,
)


def _guarded():
    from beets.autotag import match

    return match.assign_items


def _restore_pristine_assign_items():
    from beets.autotag import match

    original = getattr(match.assign_items, "_beet_it_original", None)
    if original is not None:
        match.assign_items = original


@pytest.fixture(autouse=True)
def _uninstall_guard():
    """Start from and restore the pristine beets assign_items.

    Other suites exercise the real analyze path, which installs the guard
    process-wide — uninstall on both sides so these tests are order-proof.
    """
    _restore_pristine_assign_items()
    yield
    _restore_pristine_assign_items()


def _item(title, length, track=0, disc=0, path=b""):
    from beets.library import Item

    item = Item(title=title, length=length, track=track, disc=disc)
    if path:
        item.path = path
    return item


def _track_info(title, length, index):
    from beets.autotag.hooks import TrackInfo

    return TrackInfo(title=title, length=length, index=index)


class TestInstaller:
    def test_installs_once_and_is_idempotent(self):
        from beets.autotag import match

        pristine = match.assign_items
        install_large_release_assignment_guard()
        first = match.assign_items
        assert first is not pristine
        assert first._beet_it_original is pristine

        install_large_release_assignment_guard()
        assert match.assign_items is first  # no double wrap

    def test_small_release_delegates_to_original(self, monkeypatch):
        from beets.autotag import match

        calls = []
        pristine = match.assign_items

        def spy(items, tracks):
            calls.append((len(items), len(tracks)))
            return pristine(items, tracks)

        monkeypatch.setattr(match, "assign_items", spy)
        install_large_release_assignment_guard()

        items = [_item("Stay", 185.0)]
        tracks = [_track_info("Stay", 185.0, 1)]
        mapping, extra_items, extra_tracks = _guarded()(items, tracks)

        assert calls == [(1, 1)]
        assert mapping == [(items[0], tracks[0])]
        assert extra_items == [] and extra_tracks == []


class TestLargeReleaseGuard:
    def _forbid_original(self, monkeypatch):
        from beets.autotag import match

        def boom(items, tracks):
            raise AssertionError("original assign_items must not run")

        monkeypatch.setattr(match, "assign_items", boom)
        install_large_release_assignment_guard()

    def test_large_release_aligns_by_duration_order(self, monkeypatch):
        monkeypatch.setenv("BEETS_LARGE_PAIRING_THRESHOLD", "1")
        self._forbid_original(monkeypatch)

        # Local rip misses the middle chapter of a 4-track candidate.
        items = [
            _item("Kapitel 1", 100.0, track=1),
            _item("Kapitel 2", 200.0, track=2),
            _item("Kapitel 4", 400.0, track=3),
        ]
        tracks = [
            _track_info("Kapitel 1", 100.0, 1),
            _track_info("Kapitel 2", 200.0, 2),
            _track_info("Kapitel 3", 300.0, 3),
            _track_info("Kapitel 4", 400.0, 4),
        ]

        mapping, extra_items, extra_tracks = _guarded()(items, tracks)

        assert dict((id(i), t.index) for i, t in mapping) == {
            id(items[0]): 1,
            id(items[1]): 2,
            id(items[2]): 4,
        }
        assert extra_items == []
        assert [t.index for t in extra_tracks] == [3]

    def test_audiobook_scale_is_fast_and_exact(self, monkeypatch):
        """Tintenblut shape through the guard: ~500 items vs 636 tracks."""
        self._forbid_original(monkeypatch)

        def length(j):
            return 60.0 + float((j * 37) % 240)

        m = 636
        tracks = [_track_info(f"Kapitel {j + 1}", length(j), j + 1) for j in range(m)]
        kept = [j for j in range(m) if j % 5 != 2]
        items = [
            _item(f"Kapitel {j + 1}", length(j), track=pos + 1)
            for pos, j in enumerate(kept)
        ]
        assert len(items) * m > 40_000  # above the default threshold

        start = time.monotonic()
        mapping, extra_items, extra_tracks = _guarded()(items, tracks)
        elapsed = time.monotonic() - start

        assert elapsed < 20.0, f"guarded assignment took {elapsed:.1f}s"
        assert len(mapping) == len(items)
        assert extra_items == []
        assert sorted(t.index for t in extra_tracks) == [
            j + 1 for j in range(m) if j % 5 == 2
        ]
        by_item = {id(i): t.index for i, t in mapping}
        mismatches = [
            j + 1
            for pos, j in enumerate(kept)
            if by_item.get(id(items[pos])) != j + 1
        ]
        assert not mismatches, f"misaligned tracks: {mismatches[:10]}"

    def test_alignment_failure_falls_back_to_positional_zip(self, monkeypatch):
        from app.services import candidate_resolvers

        monkeypatch.setenv("BEETS_LARGE_PAIRING_THRESHOLD", "1")
        self._forbid_original(monkeypatch)

        def boom(items, tracks):
            raise RuntimeError("alignment exploded")

        monkeypatch.setattr(candidate_resolvers, "_assign_items_by_order", boom)

        items = [_item("Eins", 100.0), _item("Zwei", 110.0)]
        tracks = [
            _track_info("Eins", 100.0, 1),
            _track_info("Zwei", 110.0, 2),
            _track_info("Drei", 120.0, 3),
        ]

        mapping, extra_items, extra_tracks = _guarded()(items, tracks)

        assert mapping == [(items[0], tracks[0]), (items[1], tracks[1])]
        assert extra_items == []
        assert [t.index for t in extra_tracks] == [3]


class TestOrderedReleaseGuard:
    """Sequentially ordered items use the alignment below the threshold (#182)."""

    def _forbid_original(self, monkeypatch):
        from beets.autotag import match

        def boom(items, tracks):
            raise AssertionError("original assign_items must not run")

        monkeypatch.setattr(match, "assign_items", boom)
        install_large_release_assignment_guard()

    def test_ordered_small_release_skips_original(self, monkeypatch):
        self._forbid_original(monkeypatch)

        # Das-magische-Messer shape in miniature: filename titles carrying no
        # similarity to the candidate, sequential track numbers, and
        # near-identical durations — the mix that scrambles the Hungarian
        # matcher.
        items = [
            _item(f"Messer_{i + 1:03d}", 300.0 + (i % 3) * 0.5, track=i + 1)
            for i in range(5)
        ]
        tracks = [
            _track_info(f"Kapitel {j + 1}", 300.0 + (j % 3) * 0.5, j + 1)
            for j in range(5)
        ]
        assert len(items) * len(tracks) < 40_000  # below the default threshold

        mapping, extra_items, extra_tracks = _guarded()(items, tracks)

        assert [(id(i), t.index) for i, t in mapping] == [
            (id(items[j]), j + 1) for j in range(5)
        ]
        assert extra_items == [] and extra_tracks == []

    def test_alignment_failure_falls_back_to_original_matcher(self, monkeypatch):
        """Below the threshold the original matcher is affordable, so a blown
        alignment degrades to it — not to the blind positional zip."""
        from app.services import candidate_resolvers
        from beets.autotag import match

        calls = []
        pristine = match.assign_items

        def spy(items, tracks):
            calls.append(len(items))
            return pristine(items, tracks)

        monkeypatch.setattr(match, "assign_items", spy)
        install_large_release_assignment_guard()

        def boom(items, tracks):
            raise RuntimeError("alignment exploded")

        monkeypatch.setattr(candidate_resolvers, "_assign_items_by_order", boom)

        items = [_item("Eins", 100.0, track=1), _item("Zwei", 110.0, track=2)]
        tracks = [_track_info("Eins", 100.0, 1), _track_info("Zwei", 110.0, 2)]

        mapping, extra_items, extra_tracks = _guarded()(items, tracks)

        assert calls == [2]
        assert {id(i): t.index for i, t in mapping} == {
            id(items[0]): 1,
            id(items[1]): 2,
        }
        assert extra_items == [] and extra_tracks == []


class TestAssignItemsByOrder:
    def test_items_sorted_into_playback_order(self):
        """Items arriving in scrambled order still align by (disc, track)."""
        items = [
            _item("Teil 2", 200.0, track=2, disc=1),
            _item("Teil 1", 100.0, track=1, disc=1),
            _item("Teil 3", 300.0, track=1, disc=2),
        ]
        tracks = [
            _track_info("Teil 1", 100.0, 1),
            _track_info("Teil 2", 200.0, 2),
            _track_info("Teil 3", 300.0, 3),
        ]

        mapping, extra_items, extra_tracks = _assign_items_by_order(items, tracks)

        assert {id(i): t.index for i, t in mapping} == {
            id(items[1]): 1,
            id(items[0]): 2,
            id(items[2]): 3,
        }
        assert extra_items == [] and extra_tracks == []

    def test_untracked_items_align_by_natural_path_order(self):
        items = [
            _item("", 0.0, path=b"/import/buch/Kapitel 10.flac"),
            _item("", 0.0, path=b"/import/buch/Kapitel 2.flac"),
            _item("", 0.0, path=b"/import/buch/Kapitel 1.flac"),
        ]
        tracks = [
            _track_info("Kapitel 1", None, 1),
            _track_info("Kapitel 2", None, 2),
            _track_info("Kapitel 10", None, 3),
        ]

        mapping, _extra_items, _extra_tracks = _assign_items_by_order(items, tracks)

        assert {id(i): t.index for i, t in mapping} == {
            id(items[2]): 1,
            id(items[1]): 2,
            id(items[0]): 3,
        }


def test_run_beets_analysis_installs_guard(monkeypatch):
    """The analyze path installs the guard before beets can hit assign_items."""
    from app.services import candidate_resolvers
    from app.services.beets_autotag_service import (
        BeetsAutotagService,
        LocalAlbumData,
    )

    calls = []
    monkeypatch.setattr(
        candidate_resolvers,
        "install_large_release_assignment_guard",
        lambda: calls.append(1),
    )
    monkeypatch.setattr(
        BeetsAutotagService, "_create_beets_items", lambda self, la: ([], {})
    )

    service = BeetsAutotagService(timeout=5)
    local_album = LocalAlbumData(
        path="/import/buch", artist="Jürgen Groß", album="Hörbuch", tracks=[]
    )
    result = service._run_beets_analysis("/import/buch", local_album)

    assert result == []
    assert calls == [1]
