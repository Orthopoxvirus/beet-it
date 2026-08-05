"""Provider candidate resolution for beets autotag.

Resolves a metadata-provider hit (MusicBrainz / Spotify / Deezer / Discogs)
into a full :class:`~app.schemas.beets_autotag.Candidate` with track-level
pairing against the local album.

Extracted from ``app.api.routes.beets_autotag`` (issue #76) so both the manual
"add candidate" route AND the automatic multi-provider analysis path
(:meth:`BeetsAutotagService.analyze_album`) can call the same proven resolvers
without an import cycle. The route re-exports these names for backwards
compatibility.
"""

import functools
import logging
import os
import re
from typing import TYPE_CHECKING, List, Optional

from app.schemas.beets_autotag import (
    Candidate,
    CandidateTrack,
    MetadataChange,
    TrackChange,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from app.services.beets_autotag_service import BeetsAutotagService

logger = logging.getLogger(__name__)

# Default timeout for manual candidate resolution in seconds. Generous on
# purpose: large releases (500-track audiobook box sets) need many paginated
# provider requests for the tracklist, and the local-track pairing after the
# fetch is O(n^2)+ — 15s reliably failed around ~500 tracks (issue seen with a
# 498-track Deezer audiobook). Override via
# BEETS_MANUAL_RESOLUTION_TIMEOUT_SECONDS.
DEFAULT_MANUAL_RESOLUTION_TIMEOUT = 180

# Above this many local×candidate track pairs, `_pair_local_tracks` switches
# from beets' `assign_items` to the ordered duration alignment (#175). The
# beets matcher builds a full cost matrix of `track_distance` calls (~50µs
# each, so 500×636 ≈ 318k pairs ≈ 15s+ of pure matrix construction) and reads
# every local file via `Item.from_path` — at audiobook scale that reliably
# exhausts even the 180s resolution timeout while holding the beets config
# lock. 40 000 ≈ a 200×200 release, comfortably inside the fast regime for
# the beets matcher. Override via BEETS_LARGE_PAIRING_THRESHOLD.
DEFAULT_LARGE_PAIRING_THRESHOLD = 40_000

# Gap penalty (in seconds of duration mismatch) for leaving a local or
# candidate track unmatched in the ordered alignment. High enough that
# same-chapter pairs (duration diff of a few seconds) always win, low enough
# that a genuinely missing/extra chapter (diff of a whole chapter length)
# prefers a gap over a cascading misalignment.
_ALIGNMENT_GAP_COST = 30.0

# Neutral per-pair cost when either side lacks a duration; the positional
# drift term then dominates and the alignment degrades to (near-)positional.
_ALIGNMENT_NEUTRAL_COST = 5.0

# Weight of the normalised positional drift term (0..1 across the release),
# in the same "seconds" unit as the duration diff. Acts as a tiebreaker for
# repeating/flat durations and as the sole signal when durations are missing.
_ALIGNMENT_DRIFT_WEIGHT = 10.0


# --- Manual Candidate Resolution Exceptions ---


class PluginNotAvailableError(Exception):
    """Raised when the required beets plugin is not installed."""
    pass


class ReleaseNotFoundError(Exception):
    """Raised when the release is not found on the provider."""
    pass


class ProviderError(Exception):
    """Raised when there is an error communicating with the provider."""
    pass


class ResolutionTimeoutError(Exception):
    """Raised when manual candidate resolution times out."""
    pass


# --- Manual Candidate Resolution Functions ---


def resolve_manual_candidate(
    autotag_service: "BeetsAutotagService",
    album_path: str,
    provider: str,
    source_id: str,
    config_path: Optional[str] = None,
    timeout: int = DEFAULT_MANUAL_RESOLUTION_TIMEOUT,
) -> Candidate:
    """Resolve a manual candidate from an external provider.

    Args:
        autotag_service: The beets autotag service instance.
        album_path: Absolute path to the album folder.
        provider: Provider name ('deezer', 'spotify', 'discogs', 'musicbrainz').
        source_id: The ID extracted from the link.
        config_path: Optional path to beets config file.
        timeout: Timeout in seconds for resolution.

    Returns:
        A Candidate object with is_manual=True.

    Raises:
        PluginNotAvailableError: If the required plugin is not installed.
        ReleaseNotFoundError: If the release is not found on the provider.
        ProviderError: If there is an error communicating with the provider.
        ResolutionTimeoutError: If resolution times out.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    # Serialize access to the global beets config singleton using the single
    # process-wide lock shared with the analyze and search paths. (A fresh
    # per-call lock would not exclude concurrent resolves — or those other
    # paths — from clobbering the same global mid-read.)
    from app.services.beets_autotag_service import _beets_config_lock

    def _resolve() -> Candidate:
        """Inner function to resolve the candidate (executed in thread pool)."""
        try:
            from beets import plugins
            from beets import config as beets_config
        except ImportError as e:
            raise PluginNotAvailableError(f"Beets library not installed: {e}")

        with _beets_config_lock:
            # Configure beets if config path provided
            if config_path and os.path.exists(config_path):
                beets_config.clear()
                beets_config.set_file(config_path)
                beets_config.read()
                plugins.load_plugins()
                logger.info(f"Loaded beets config from: {config_path}")

            # Read local album data for comparison
            local_album = autotag_service._read_local_album(album_path)

            # Resolve based on provider
            if provider == "musicbrainz":
                return resolve_musicbrainz_candidate(source_id, local_album)
            elif provider == "spotify":
                return resolve_spotify_candidate(source_id, local_album)
            elif provider == "deezer":
                return resolve_deezer_candidate(source_id, local_album)
            elif provider == "discogs":
                return resolve_discogs_candidate(source_id, local_album)
            else:
                raise PluginNotAvailableError(f"Unknown provider: {provider}")

    # Use ThreadPoolExecutor for timeout handling
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_resolve)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            raise ResolutionTimeoutError(
                f"Manual candidate resolution timed out after {timeout} seconds. "
                "The provider may be slow or unreachable."
            )


def _large_pairing_threshold() -> int:
    """Local×candidate pair count above which the ordered alignment is used."""
    raw = os.environ.get("BEETS_LARGE_PAIRING_THRESHOLD")
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                f"Invalid BEETS_LARGE_PAIRING_THRESHOLD {raw!r}; "
                f"using default {DEFAULT_LARGE_PAIRING_THRESHOLD}"
            )
    return DEFAULT_LARGE_PAIRING_THRESHOLD


def _pair_by_track_number(local_album, candidate_rows: List[dict]) -> List:
    """Last-resort pairing by tag track number (shared fallback).

    On a multi-disc release track numbers repeat per disc, so when both sides
    know their disc the (disc, per-disc number) pair is tried first; the bare
    number map (last write wins on collisions) stays as the final fallback.
    """
    local_by_num = {
        t.track_num: t for t in local_album.tracks if t.track_num is not None
    }
    local_by_disc_num = {
        (t.disc, t.track_num): t
        for t in local_album.tracks
        if getattr(t, "disc", None) is not None and t.track_num is not None
    }

    paired = []
    for row in candidate_rows:
        track = None
        medium = row.get("medium")
        medium_index = row.get("medium_index")
        if medium is not None and medium_index is not None:
            track = local_by_disc_num.get((medium, medium_index))
        if track is None:
            track = local_by_num.get(row["index"])
        paired.append(track)
    return paired


def _natural_sort_key(path: str):
    """Sort key treating digit runs numerically so track 10 follows track 9."""
    return [
        int(chunk) if chunk.isdigit() else chunk.lower()
        for chunk in re.split(r"(\d+)", os.path.basename(path))
    ]


def _locals_in_playback_order(local_album) -> List:
    """Local tracks in playback order for the ordered alignment.

    Tag track numbers win when they are complete and unique (a flat 500-file
    audiobook rip numbered 1..500). For a folder-per-disc rip the numbers
    repeat per disc, so (disc, number) orders the set — a bare filename sort
    would interleave the discs (CD 2 track 1 before CD 1 track 2), scrambling
    the ordered alignment. Only when neither works is a disc-grouped natural
    filename sort the best available order.
    """
    tracks = list(local_album.tracks)
    nums = [t.track_num for t in tracks]
    if all(n is not None for n in nums) and len(set(nums)) == len(nums):
        return sorted(tracks, key=lambda t: t.track_num)
    disc_nums = [(getattr(t, "disc", None) or 0, t.track_num) for t in tracks]
    if (
        all(n is not None for _, n in disc_nums)
        and len(set(disc_nums)) == len(disc_nums)
    ):
        return sorted(tracks, key=lambda t: ((t.disc or 0), t.track_num))
    return sorted(
        tracks,
        key=lambda t: ((getattr(t, "disc", None) or 0), _natural_sort_key(t.path or "")),
    )


def _locals_are_sequentially_ordered(local_album) -> bool:
    """True when local tags define a complete, unique playback order.

    Mirrors the tag-based branches of ``_locals_in_playback_order``: every
    track carries a number and either the bare numbers or the
    (disc, number) pairs are unique. Such an album is inherently ordered
    (audiobook / chapter rip), so the monotonic alignment is a correctness
    requirement, not just a perf escape hatch (#182).
    """
    tracks = list(local_album.tracks)
    if not tracks:
        return False
    nums = [t.track_num for t in tracks]
    if any(n is None for n in nums):
        return False
    if len(set(nums)) == len(nums):
        return True
    disc_nums = [((getattr(t, "disc", None) or 0), n) for t, n in zip(tracks, nums)]
    return len(set(disc_nums)) == len(disc_nums)


def _items_are_sequentially_ordered(items) -> bool:
    """Beets-Item twin of ``_locals_are_sequentially_ordered``.

    ``Item.track`` / ``Item.disc`` default to 0 when untagged, so 0 counts
    as missing.
    """
    if not items:
        return False
    nums = [item.track or None for item in items]
    if any(n is None for n in nums):
        return False
    if len(set(nums)) == len(nums):
        return True
    disc_nums = [((item.disc or 0), n) for item, n in zip(items, nums)]
    return len(set(disc_nums)) == len(disc_nums)


def _pair_large_release_by_order(local_album, candidate_rows: List[dict]) -> List:
    """Monotonic duration-anchored pairing for ordered releases (#175, #182).

    Both sides of an audiobook / chapter release are inherently ordered, so
    instead of beets' Hungarian assignment (full O(n·m) `track_distance`
    matrix, ~50µs per pair — the wall that made 500×636 releases blow the
    resolution timeout) this runs a Needleman-Wunsch-style alignment with a
    cheap per-cell cost: absolute duration difference plus a small positional
    drift term. Gap penalties let surplus candidate tracks (provider segments
    chapters differently, e.g. local 500 vs Deezer 636) go unmatched instead
    of derailing the rest of the pairing. Monotonicity also guarantees the
    pairing never scrambles chapter order — something the unconstrained
    assignment cannot promise for near-identical durations/titles.

    Returns the same shape as ``_pair_local_tracks``: one entry per candidate
    row, LocalTrackData or None.
    """
    locals_sorted = _locals_in_playback_order(local_album)
    alignment = _align_ordered_lengths(
        [t.length for t in locals_sorted],
        [row.get("length") for row in candidate_rows],
    )
    return [
        locals_sorted[local_pos] if local_pos is not None else None
        for local_pos in alignment
    ]


def _align_ordered_lengths(
    local_lengths: List[Optional[float]],
    cand_lengths: List[Optional[float]],
) -> List[Optional[int]]:
    """Align two ordered duration sequences; the DP core of the fast pairing.

    Returns one entry per candidate position: the aligned local position, or
    None where the candidate track has no local counterpart. Monotonic — the
    matched (local, candidate) index pairs are strictly increasing on both
    sides.
    """
    n = len(local_lengths)
    m = len(cand_lengths)
    if n == 0 or m == 0:
        return [None] * m

    gap = _ALIGNMENT_GAP_COST
    neutral = _ALIGNMENT_NEUTRAL_COST
    drift_weight = _ALIGNMENT_DRIFT_WEIGHT

    # DP over (n+1)×(m+1); rolling rows for the score, full byte matrix for
    # the backtrace (0 = diag/match, 1 = up/skip local, 2 = left/skip cand).
    # ~320k cells for the 500×636 case: well under a second, a few MB.
    prev = [j * gap for j in range(m + 1)]
    back = [bytearray(m + 1) for _ in range(n + 1)]
    back[0][1:] = b"\x02" * m
    for i in range(1, n + 1):
        back[i][0] = 1
        cur = [i * gap] + [0.0] * m
        dl = local_lengths[i - 1]
        pos_l = (i - 1) / n
        prev_row = prev
        back_row = back[i]
        for j in range(1, m + 1):
            dc = cand_lengths[j - 1]
            if dl is not None and dc is not None:
                match_cost = dl - dc if dl >= dc else dc - dl
            else:
                match_cost = neutral
            match_cost += drift_weight * abs(pos_l - (j - 1) / m)

            best = prev_row[j - 1] + match_cost
            ptr = 0
            up = prev_row[j] + gap
            if up < best:
                best, ptr = up, 1
            left = cur[j - 1] + gap
            if left < best:
                best, ptr = left, 2
            cur[j] = best
            back_row[j] = ptr
        prev = cur

    alignment: List[Optional[int]] = [None] * m
    i, j = n, m
    while i > 0 or j > 0:
        ptr = back[i][j]
        if ptr == 0:
            alignment[j - 1] = i - 1
            i -= 1
            j -= 1
        elif ptr == 1:
            i -= 1
        else:
            j -= 1
    return alignment


def _item_playback_key(item):
    """Playback-order sort key for a beets Item: disc, track, natural path."""
    path = item.path
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    return (item.disc or 0, item.track or 0, _natural_sort_key(path or ""))


def _assign_items_by_order(items, tracks):
    """``assign_items``-compatible ordered alignment for huge releases (#175).

    Same return shape as beets' ``assign_items``: (mapping pairs, extra
    items, extra tracks). Items are sorted into playback order (disc, track,
    natural filename); the candidate tracklist is taken in the order beets
    provides it (canonical album order).
    """
    items_sorted = sorted(items, key=_item_playback_key)
    alignment = _align_ordered_lengths(
        [float(i.length) if i.length else None for i in items_sorted],
        [t.length if t.length else None for t in tracks],
    )

    mapping = []
    matched_item_ids = set()
    for cand_pos, local_pos in enumerate(alignment):
        if local_pos is not None:
            item = items_sorted[local_pos]
            mapping.append((item, tracks[cand_pos]))
            matched_item_ids.add(id(item))

    # Leftover sorting mirrors beets' assign_items so downstream display of
    # unmatched items/tracks is indistinguishable from the original.
    extra_items = [i for i in items_sorted if id(i) not in matched_item_ids]
    extra_items.sort(key=lambda i: (i.disc, i.track, i.title))
    matched_track_ids = {id(t) for _, t in mapping}
    extra_tracks = [t for t in tracks if id(t) not in matched_track_ids]
    extra_tracks.sort(key=lambda t: (t.index or 0, t.title or ""))
    return mapping, extra_items, extra_tracks


def install_large_release_assignment_guard() -> None:
    """Size-guard beets' internal ``assign_items`` for the analyze path (#175).

    The automatic analysis runs beets' ``tag_album``, which pairs the local
    items against EVERY candidate's tracklist via ``assign_items`` — the same
    O(n·m) ``track_distance`` cost matrix that made manual resolution blow
    its timeout at 500×636. One large MusicBrainz candidate is enough to eat
    the whole 30s analysis budget. This wraps ``assign_items`` module-wide:
    above ``BEETS_LARGE_PAIRING_THRESHOLD`` item×track pairs — or whenever
    the local items are sequentially ordered (complete + unique track
    numbers, #182) — it answers with the ordered duration alignment; other
    small releases keep the original untouched.

    Idempotent — safe to call before every analysis. The original function
    is kept on the wrapper (``_beet_it_original``) for tests/uninstall.
    """
    try:
        from beets.autotag import match
    except ImportError:
        return

    current = getattr(match, "assign_items", None)
    if current is None or getattr(current, "_beet_it_size_guarded", False):
        return
    original = current

    @functools.wraps(original)
    def guarded_assign_items(items, tracks):
        is_large = len(items) * len(tracks) > _large_pairing_threshold()
        if is_large or _items_are_sequentially_ordered(items):
            reason = "Large" if is_large else "Sequentially ordered"
            logger.info(
                f"{reason} release in beets matcher ({len(items)} items × "
                f"{len(tracks)} tracks): using ordered duration alignment"
            )
            try:
                return _assign_items_by_order(items, tracks)
            except Exception as e:
                if not is_large:
                    # Small enough that the original matcher is affordable —
                    # better than a blind positional zip.
                    logger.warning(
                        f"Ordered assign_items alignment failed, using beets "
                        f"matcher instead: {e}"
                    )
                    return original(items, tracks)
                # Positional zip, NOT the original matcher: at this scale the
                # original would just eat the whole analysis timeout.
                logger.warning(
                    f"Ordered assign_items alignment failed, pairing "
                    f"positionally instead: {e}"
                )
                mapping = list(zip(items, tracks))
                return mapping, list(items[len(tracks):]), list(tracks[len(items):])
        return original(items, tracks)

    guarded_assign_items._beet_it_size_guarded = True
    guarded_assign_items._beet_it_original = original
    match.assign_items = guarded_assign_items


def _pair_local_tracks(local_album, candidate_rows: List[dict]) -> List:
    """Pair each candidate track with its best-matching local track.

    Uses beets' distance-based assignment (duration + title) — the same
    matcher the automatic analysis path gets via ``match.mapping`` — so local
    files without a ``tracknumber`` tag still pair by duration. Falls back to
    pairing by tag track number if the matcher is unavailable or fails.

    Very large releases (local×candidate pairs above
    ``BEETS_LARGE_PAIRING_THRESHOLD``, e.g. 500-file audiobooks against a
    636-track Deezer tracklist) skip the beets matcher entirely — its full
    cost matrix and per-file reads blow the resolution timeout at that scale
    — and use the ordered duration alignment instead (#175). So do
    sequentially ordered local albums of ANY size (#182): when titles carry
    no signal (filename-titled audiobook chapters) the unconstrained matcher
    assigns by duration similarity and scrambles chapter order, which the
    monotonic alignment cannot do by construction.

    Args:
        local_album: LocalAlbumData for the folder being imported.
        candidate_rows: One dict per candidate track, in display order:
            ``{"title": str, "length": float | None, "index": int}``.

    Returns:
        A list the same length as ``candidate_rows``; each entry is the
        paired LocalTrackData or None (genuinely new track).
    """
    n_pairs = len(local_album.tracks) * len(candidate_rows)
    is_large = n_pairs > _large_pairing_threshold()
    if is_large or _locals_are_sequentially_ordered(local_album):
        reason = "Large" if is_large else "Sequentially ordered"
        logger.info(
            f"{reason} release ({len(local_album.tracks)} local × "
            f"{len(candidate_rows)} candidate tracks): pairing by ordered "
            f"duration alignment instead of beets assign_items"
        )
        try:
            return _pair_large_release_by_order(local_album, candidate_rows)
        except Exception as e:
            # Deliberately NOT falling back to assign_items here: at large
            # scale it would just eat the whole resolution timeout, and an
            # ordered album pairs fine by its (complete, unique) tag numbers.
            logger.warning(
                f"Ordered alignment failed, pairing by track number instead: {e}"
            )
            return _pair_by_track_number(local_album, candidate_rows)

    try:
        from beets.autotag.hooks import TrackInfo
        from beets.autotag.match import assign_items
        from beets.library import Item

        items = []
        item_to_local = {}
        for local_track in local_album.tracks:
            # Prefer Item.from_path so the file's DISCNUMBER is loaded. Without
            # the disc, a multi-disc release whose per-disc track titles repeat
            # (e.g. an audio drama with "Teil 1" on every CD and near-identical
            # durations) cannot be disambiguated and assign_items scrambles the
            # repeated titles across discs. Fall back to the metadata we already
            # read if the on-disk read fails.
            item = None
            path = getattr(local_track, "path", None)
            if path:
                try:
                    item = Item.from_path(path)
                except Exception:
                    item = None
            if item is None:
                item = Item(
                    title=local_track.title or "",
                    length=local_track.length or 0.0,
                    track=local_track.track_num or 0,
                )
            # Folder-per-disc rips usually carry no DISCNUMBER tag; the
            # folder-inferred disc (see _read_local_album) fills the gap so
            # assign_items can keep the discs apart.
            local_disc = getattr(local_track, "disc", None)
            if not item.disc and local_disc:
                item.disc = local_disc
            items.append(item)
            item_to_local[id(item)] = local_track

        track_infos = [
            TrackInfo(
                title=row["title"] or "",
                length=row["length"],
                index=row["index"],
                # Pass the disc through so assign_items keeps tracks grouped by
                # CD. None for single-disc / providers without media info, which
                # leaves matching behaviour unchanged.
                medium=row.get("medium"),
                medium_index=row.get("medium_index"),
            )
            for row in candidate_rows
        ]
        position_by_id = {id(ti): pos for pos, ti in enumerate(track_infos)}

        paired = [None] * len(candidate_rows)
        if items and track_infos:
            mapping, _extra_items, _extra_tracks = assign_items(items, track_infos)
            for item, track_info in mapping:
                paired[position_by_id[id(track_info)]] = item_to_local[id(item)]
        return paired
    except Exception as e:
        logger.warning(
            f"beets track assignment failed, pairing by track number instead: {e}"
        )
        return _pair_by_track_number(local_album, candidate_rows)


def _build_manual_track_change(
    *, index, candidate_title, candidate_length, local_track
) -> TrackChange:
    """Build a per-track comparison row for a manual candidate.

    The paired local track (from ``_pair_local_tracks``) carries its duration
    and filename so the UI can show local vs. candidate length and the source
    filename. Emitted for every track, not only renamed ones (mirrors the
    autotag analysis path).
    """
    return TrackChange(
        index=index,
        local_title=local_track.title if local_track else None,
        candidate_title=candidate_title,
        local_length=local_track.length if local_track else None,
        candidate_length=candidate_length,
        local_path=local_track.path if local_track else None,
    )


def resolve_musicbrainz_candidate(
    release_id: str,
    local_album,
) -> Candidate:
    """Resolve a MusicBrainz release ID to a candidate.

    Args:
        release_id: MusicBrainz release UUID.
        local_album: Local album data for comparison.

    Returns:
        A Candidate object.
    """
    try:
        import musicbrainzngs
    except ImportError:
        raise PluginNotAvailableError(
            "The musicbrainzngs library is not installed. "
            "Please install it to use MusicBrainz links."
        )

    try:
        # Set user agent for MusicBrainz API
        musicbrainzngs.set_useragent("beets-ui", "1.0", "https://github.com/beets-ui")

        # Fetch release data
        result = musicbrainzngs.get_release_by_id(
            release_id,
            includes=["artists", "recordings", "labels", "media", "release-groups"]
        )
        release = result.get("release", {})

        if not release:
            raise ReleaseNotFoundError(
                "Release not found on MusicBrainz. The release ID may be incorrect."
            )

        # Extract metadata
        artist = ""
        artist_credit = release.get("artist-credit", [])
        if artist_credit:
            artist_parts = []
            for credit in artist_credit:
                if isinstance(credit, dict) and "artist" in credit:
                    artist_parts.append(credit["artist"].get("name", ""))
                elif isinstance(credit, str):
                    artist_parts.append(credit)
            artist = "".join(artist_parts)

        album = release.get("title", "")
        year = None
        date_str = release.get("date", "")
        if date_str and len(date_str) >= 4:
            try:
                year = int(date_str[:4])
            except ValueError:
                pass

        country = release.get("country", None)

        label = None
        label_info = release.get("label-info-list", [])
        if label_info and len(label_info) > 0:
            label = label_info[0].get("label", {}).get("name")

        # Get media format
        media = None
        media_list = release.get("medium-list", [])
        if media_list:
            media = media_list[0].get("format")

        # Build track list
        tracks = []
        track_changes = []
        all_tracks = []

        for medium in media_list:
            medium_pos = int(medium.get("position", 1) or 1)
            track_list = medium.get("track-list", [])
            for track in track_list:
                recording = track.get("recording", {})
                all_tracks.append({
                    "medium": medium_pos,
                    "position": int(track.get("position", len(all_tracks) + 1)),
                    "title": recording.get("title", "Unknown"),
                    "length": int(recording.get("length", 0)) / 1000.0 if recording.get("length") else None,
                })

        # Sort by (disc, position) and create CandidateTrack objects. Carrying
        # the medium through lets assign_items keep discs apart when per-disc
        # track titles repeat, and lets the import apply each track to the right
        # disc instead of collapsing the repeating per-disc track numbers.
        multi_disc = len({t["medium"] for t in all_tracks}) > 1
        all_tracks.sort(key=lambda t: (t["medium"], t["position"]))
        candidate_rows = [
            {
                "title": t["title"],
                "length": t["length"],
                "index": t["position"],
                "medium": t["medium"],
                "medium_index": t["position"],
            }
            for t in all_tracks
        ]
        paired_locals = _pair_local_tracks(local_album, candidate_rows)
        for t, local_track in zip(all_tracks, paired_locals):
            track_index = t["position"]
            # Only stamp a disc on genuinely multi-disc releases so single-disc
            # candidates serialise exactly as before (disc=None).
            track_disc = t["medium"] if multi_disc else None
            candidate_title = t["title"]

            tc = _build_manual_track_change(
                index=track_index,
                candidate_title=candidate_title,
                candidate_length=t["length"],
                local_track=local_track,
            )
            track_changes.append(tc)

            track_meta_changes = []
            if tc.local_title and tc.local_title != candidate_title:
                track_meta_changes.append(
                    MetadataChange(
                        field="title",
                        from_value=tc.local_title,
                        to_value=candidate_title,
                    )
                )

            tracks.append(
                CandidateTrack(
                    index=track_index,
                    disc=track_disc,
                    title=candidate_title,
                    length=t["length"],
                    local_title=tc.local_title,
                    local_path=tc.local_path,
                    changes=track_meta_changes,
                )
            )

        # Compute album-level changes
        changes = []
        if local_album.artist and local_album.artist != artist:
            changes.append(
                MetadataChange(
                    field="artist",
                    from_value=local_album.artist,
                    to_value=artist,
                )
            )
        if local_album.album and local_album.album != album:
            changes.append(
                MetadataChange(
                    field="album",
                    from_value=local_album.album,
                    to_value=album,
                )
            )
        if year:
            changes.append(
                MetadataChange(
                    field="year",
                    from_value=None,
                    to_value=str(year),
                )
            )

        return Candidate(
            source="MusicBrainz",
            source_id=release_id,
            similarity=1.0,  # Manual candidates get full similarity
            artist=artist,
            album=album,
            year=year,
            label=label,
            country=country,
            media=media,
            tracks=tracks,
            changes=changes,
            track_changes=track_changes,
            is_manual=True,
            # MusicBrainz exposes no cover URL here; its art lives in the Cover
            # Art Archive, which is not wired up (see #148).
            cover_url=None,
        )

    except musicbrainzngs.WebServiceError as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise ReleaseNotFoundError(
                "Release not found on MusicBrainz. The release ID may be incorrect."
            )
        raise ProviderError(f"Error communicating with MusicBrainz API: {e}")
    except Exception as e:
        if isinstance(e, (PluginNotAvailableError, ReleaseNotFoundError, ProviderError)):
            raise
        raise ProviderError(f"Error resolving MusicBrainz release: {e}")


def resolve_spotify_candidate(
    album_id: str,
    local_album,
) -> Candidate:
    """Resolve a Spotify album ID to a candidate.

    Note: This requires the spotify beets plugin to be installed and configured.

    Args:
        album_id: Spotify album ID.
        local_album: Local album data for comparison.

    Returns:
        A Candidate object.
    """
    try:
        from beetsplug.spotify import SpotifyPlugin
    except ImportError:
        raise PluginNotAvailableError("beetsplug.spotify could not be imported.")

    try:
        plugin = SpotifyPlugin()
        info = plugin.album_for_id(album_id)
    except Exception as e:
        raise ProviderError(f"Error communicating with Spotify API: {e}")

    if info is None:
        raise ReleaseNotFoundError(
            "Album not found on Spotify. The album ID may be incorrect."
        )

    tracks = []
    track_changes = []
    sorted_tracks = sorted(info.tracks, key=lambda t: t.index or 0)
    candidate_rows = [
        {"title": t.title or "", "length": t.length, "index": t.index or pos + 1}
        for pos, t in enumerate(sorted_tracks)
    ]
    paired_locals = _pair_local_tracks(local_album, candidate_rows)
    for track, local_track in zip(sorted_tracks, paired_locals):
        candidate_title = track.title or ""

        tc = _build_manual_track_change(
            index=track.index,
            candidate_title=candidate_title,
            candidate_length=track.length,
            local_track=local_track,
        )
        track_changes.append(tc)

        meta_changes = []
        if tc.local_title and tc.local_title != candidate_title:
            meta_changes.append(
                MetadataChange(field="title", from_value=tc.local_title, to_value=candidate_title)
            )

        tracks.append(
            CandidateTrack(
                index=track.index or 0,
                title=candidate_title,
                length=track.length,
                local_title=tc.local_title,
                local_path=tc.local_path,
                changes=meta_changes,
            )
        )

    artist = info.artist or ""
    album = info.album or ""
    year = info.year
    changes = []
    if local_album.artist and local_album.artist != artist:
        changes.append(MetadataChange(field="artist", from_value=local_album.artist, to_value=artist))
    if local_album.album and local_album.album != album:
        changes.append(MetadataChange(field="album", from_value=local_album.album, to_value=album))
    if year:
        changes.append(MetadataChange(field="year", from_value=None, to_value=str(year)))

    return Candidate(
        source="Spotify",
        source_id=str(info.album_id),
        similarity=1.0,
        artist=artist,
        album=album,
        year=year,
        label=getattr(info, "label", None),
        country=getattr(info, "country", None),
        media=getattr(info, "media", None),
        tracks=tracks,
        changes=changes,
        track_changes=track_changes,
        is_manual=True,
        cover_url=getattr(info, "cover_art_url", None),
    )


def resolve_deezer_candidate(
    album_id: str,
    local_album,
) -> Candidate:
    """Resolve a Deezer album ID to a candidate using the built-in beets Deezer plugin.

    The Deezer API is public — no authentication required.

    Args:
        album_id: Deezer album ID.
        local_album: Local album data for comparison.

    Returns:
        A Candidate object.
    """
    try:
        from beetsplug.deezer import DeezerPlugin
    except ImportError:
        raise PluginNotAvailableError("beetsplug.deezer could not be imported.")

    try:
        plugin = DeezerPlugin()
        info = plugin.album_for_id(album_id)
    except Exception as e:
        raise ProviderError(f"Error communicating with Deezer API: {e}")

    if info is None:
        raise ReleaseNotFoundError(
            "Album not found on Deezer. The album ID may be incorrect."
        )

    # Build track list
    tracks = []
    track_changes = []
    sorted_tracks = sorted(info.tracks, key=lambda t: t.index or 0)
    candidate_rows = [
        {"title": t.title or "", "length": t.length, "index": t.index or pos + 1}
        for pos, t in enumerate(sorted_tracks)
    ]
    paired_locals = _pair_local_tracks(local_album, candidate_rows)
    for track, local_track in zip(sorted_tracks, paired_locals):
        candidate_title = track.title or ""

        tc = _build_manual_track_change(
            index=track.index,
            candidate_title=candidate_title,
            candidate_length=track.length,
            local_track=local_track,
        )
        track_changes.append(tc)

        meta_changes = []
        if tc.local_title and tc.local_title != candidate_title:
            meta_changes.append(
                MetadataChange(field="title", from_value=tc.local_title, to_value=candidate_title)
            )

        tracks.append(
            CandidateTrack(
                index=track.index or 0,
                title=candidate_title,
                length=track.length,
                local_title=tc.local_title,
                local_path=tc.local_path,
                changes=meta_changes,
            )
        )

    # Album-level changes
    artist = info.artist or ""
    album = info.album or ""
    year = info.year
    changes = []
    if local_album.artist and local_album.artist != artist:
        changes.append(MetadataChange(field="artist", from_value=local_album.artist, to_value=artist))
    if local_album.album and local_album.album != album:
        changes.append(MetadataChange(field="album", from_value=local_album.album, to_value=album))
    if year:
        changes.append(MetadataChange(field="year", from_value=None, to_value=str(year)))

    return Candidate(
        source="Deezer",
        source_id=str(info.album_id),
        similarity=1.0,
        artist=artist,
        album=album,
        year=year,
        label=info.label,
        country=info.country,
        media=info.media,
        tracks=tracks,
        changes=changes,
        track_changes=track_changes,
        is_manual=True,
        # The beets Deezer plugin sets cover_art_url to the high-res cover_xl.
        cover_url=getattr(info, "cover_art_url", None),
    )


def resolve_discogs_candidate(
    release_id: str,
    local_album,
) -> Candidate:
    """Resolve a Discogs release/master ID to a candidate via the public REST API.

    Fetches /releases/{id} first and falls back to /masters/{id}. No auth
    token required for public reads; anonymous rate limit (60 req/min) is
    plenty for a one-shot lookup. The beets `discogs` plugin is avoided here
    because it requires `discogs_client` + an OAuth / user_token setup that
    the backend container doesn't have.
    """
    import httpx

    headers = {"User-Agent": "beet-it/1.0 (+https://github.com/Orthopoxvirus/beet-it)"}
    base = "https://api.discogs.com"

    def fetch(path: str) -> dict | None:
        try:
            resp = httpx.get(f"{base}{path}", headers=headers, timeout=15.0)
        except httpx.HTTPError as e:
            raise ProviderError(f"Error communicating with Discogs API: {e}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ProviderError(f"Discogs API returned {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    data = fetch(f"/releases/{release_id}") or fetch(f"/masters/{release_id}")
    if data is None:
        raise ReleaseNotFoundError(
            "Release not found on Discogs. The release ID may be incorrect."
        )

    def parse_duration(s: str | None) -> float | None:
        # Discogs returns durations like "3:45" or "1:02:30" (or empty).
        if not s:
            return None
        parts = s.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return None
        if len(nums) == 3:
            h, m, sec = nums
            return float(h * 3600 + m * 60 + sec)
        if len(nums) == 2:
            m, sec = nums
            return float(m * 60 + sec)
        if len(nums) == 1:
            return float(nums[0])
        return None

    artists = data.get("artists") or []
    artist = ", ".join(a.get("name", "") for a in artists if a.get("name")) or ""
    album = data.get("title") or ""
    year = data.get("year") or None
    if isinstance(year, int) and year == 0:
        year = None
    labels = data.get("labels") or []
    label = labels[0].get("name") if labels else None
    country = data.get("country")
    formats = data.get("formats") or []
    media = formats[0].get("name") if formats else None

    # Discogs tracklists can include headings/index tracks (type_ != "track").
    # Only count real tracks and use their 1-indexed ordinal as the track number.
    real_tracks = [
        t
        for t in (data.get("tracklist") or [])
        if not (t.get("type_") and t["type_"] != "track")
    ]
    candidate_rows = [
        {
            "title": t.get("title") or "",
            "length": parse_duration(t.get("duration")),
            "index": pos + 1,
        }
        for pos, t in enumerate(real_tracks)
    ]
    paired_locals = _pair_local_tracks(local_album, candidate_rows)

    tracks = []
    track_changes = []
    for row, local_track in zip(candidate_rows, paired_locals):
        tc = _build_manual_track_change(
            index=row["index"],
            candidate_title=row["title"],
            candidate_length=row["length"],
            local_track=local_track,
        )
        track_changes.append(tc)

        meta_changes = []
        if tc.local_title and tc.local_title != row["title"]:
            meta_changes.append(
                MetadataChange(field="title", from_value=tc.local_title, to_value=row["title"])
            )

        tracks.append(
            CandidateTrack(
                index=row["index"],
                title=row["title"],
                length=row["length"],
                local_title=tc.local_title,
                local_path=tc.local_path,
                changes=meta_changes,
            )
        )

    changes = []
    if local_album.artist and local_album.artist != artist:
        changes.append(MetadataChange(field="artist", from_value=local_album.artist, to_value=artist))
    if local_album.album and local_album.album != album:
        changes.append(MetadataChange(field="album", from_value=local_album.album, to_value=album))
    if year:
        changes.append(MetadataChange(field="year", from_value=None, to_value=str(year)))

    # Prefer the primary image, falling back to the first available one.
    images = data.get("images") or []
    primary_image = next(
        (im for im in images if im.get("type") == "primary"), images[0] if images else None
    )
    cover_url = (primary_image.get("uri") or primary_image.get("resource_url")) if primary_image else None

    return Candidate(
        source="Discogs",
        source_id=str(data.get("id") or release_id),
        similarity=1.0,
        artist=artist,
        album=album,
        year=year,
        label=label,
        country=country,
        media=media,
        tracks=tracks,
        changes=changes,
        track_changes=track_changes,
        is_manual=True,
        cover_url=cover_url,
    )
