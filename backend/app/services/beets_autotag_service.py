"""Service for analyzing album folders using beets autotag functionality."""

import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from mutagen import File as MutagenFile

from app.services.audio_discovery import find_audio_files, infer_disc_number
from app.services.scanner.folder_name import (
    parse_album_folder_name,
    parse_title_from_filename,
)
from app.services.tag_writer.mappings import EXTENSION_TO_FORMAT, SUPPORTED_EXTENSIONS
from app.services.wav_flac_service import summarize_wav_flac

logger = logging.getLogger(__name__)


def format_label_for_extension(ext: str) -> Optional[str]:
    """Map a file extension to a display label for its container format.

    Returns an uppercase container label (e.g. ".flac" -> "FLAC") or ``None``
    for unrecognised extensions. Only the container is reported — codec detail
    (bitrate, sample rate, ALAC vs AAC) is intentionally not surfaced.
    """
    fmt = EXTENSION_TO_FORMAT.get(ext.lower())
    return fmt.upper() if fmt else None


# Default timeout for beets analysis in seconds
DEFAULT_ANALYSIS_TIMEOUT = 30

# Lock for serializing access to beets config (which is a global singleton)
_beets_config_lock = threading.Lock()


class AnalysisTimeoutError(Exception):
    """Raised when beets analysis times out."""

    pass


class BeetsAnalysisError(Exception):
    """Raised when beets analysis encounters an error."""

    pass


class MusicBrainzError(Exception):
    """Raised when there's an error communicating with MusicBrainz."""

    pass


@dataclass
class LocalTrackData:
    """Data about a local audio track."""

    path: str
    title: Optional[str]
    track_num: Optional[int]
    length: Optional[float]
    # Disc number: from the discnumber tag, or inferred from a "CD 01" /
    # "Disc 2" subfolder for folder-per-disc rips. None when unknown.
    disc: Optional[int] = None


@dataclass
class LocalAlbumData:
    """Data about a local album folder."""

    path: str
    artist: Optional[str]
    album: Optional[str]
    tracks: List[LocalTrackData]
    dominant_format: Optional[str] = None
    # Where artist/album came from: "tags" (embedded tags), "folder" (parsed
    # from the folder name because tags were empty) or "mixed" (one of each).
    # Lets the UI label the source so a folder-derived value reads as expected
    # rather than as a contradiction, and never as authoritative metadata.
    metadata_source: str = "tags"
    # Per-album WAV/FLAC breakdown driving the convert / dedup actions on the
    # Local Album card. Computed over the whole folder tree (multi-disc aware).
    has_wav: bool = False
    has_flac: bool = False
    duplicate_wav_count: int = 0
    has_wma: bool = False
    wma_recommended_target: Optional[str] = None


@dataclass
class CandidateTrackData:
    """Data about a track in a candidate match."""

    index: int
    title: str
    length: Optional[float]
    changes: List[Dict]
    # The title/path of the local file paired to this candidate track, if any.
    # None means there is no local counterpart (a genuinely new track).
    local_title: Optional[str] = None
    local_path: Optional[str] = None
    # Disc (medium) number this track belongs to; None for single-disc matches.
    disc: Optional[int] = None


def parse_track_number(raw: Optional[str]) -> Optional[int]:
    """Parse a track number from a raw tag value.

    Tolerant of the messy real world: ``"1/12"`` (track/total), ``"01"``,
    surrounding whitespace, vinyl-style ``"A1"`` and corrupted multi-valued
    tags like ``"1;1"`` all resolve to the first integer found. Returns None
    when no digits are present. A blank/None input yields None.

    A blunt ``int(raw)`` (the previous behaviour) raised on every one of these
    and silently dropped the track number, which broke local/candidate
    pairing in the Prepare view.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Drop a "/total" suffix first so "1/12" reads as 1, not 112.
    text = text.split("/", 1)[0]
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:  # pragma: no cover - regex guarantees digits
        return None


def parse_track_number_from_filename(filename: str) -> Optional[int]:
    """Parse a leading track number from a filename like ``01-artist-title.flac``.

    Used as a fallback when the ``tracknumber`` tag is missing. Conservative
    on purpose: only 1-3 leading digits directly followed by a separator
    count, so year-prefixed names (``2020 - song.flac``) don't produce a
    bogus track number.
    """
    match = re.match(r"(\d{1,3})[\s._-]", filename)
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


@dataclass
class CandidateData:
    """Data about a candidate album match."""

    source: str
    source_id: Optional[str]
    similarity: float
    artist: str
    album: str
    year: Optional[int]
    label: Optional[str]
    country: Optional[str]
    media: Optional[str]
    tracks: List[CandidateTrackData]
    changes: List[Dict]
    track_changes: List[Dict]


class BeetsAutotagService:
    """Service for analyzing albums using beets autotag functionality.

    This service provides methods to:
    - Discover album folders in an import path
    - Read local audio file metadata
    - Analyze albums using beets.autotag.tag_album()
    - Convert beets AlbumMatch objects to serializable data
    """

    def __init__(self, timeout: int = DEFAULT_ANALYSIS_TIMEOUT):
        """Initialize the service.

        Args:
            timeout: Timeout in seconds for beets analysis operations.
        """
        self.timeout = timeout

    def get_album_folders(self, import_path: str) -> List[str]:
        """Get all album folders from an import path.

        An album folder is defined as a directory containing at least one
        audio file (based on supported extensions).

        Args:
            import_path: The root import folder path to scan.

        Returns:
            List of absolute paths to album folders.

        Raises:
            FileNotFoundError: If import_path doesn't exist.
            PermissionError: If import_path is not readable.
        """
        if not os.path.exists(import_path):
            raise FileNotFoundError(f"Import path does not exist: {import_path}")

        if not os.access(import_path, os.R_OK):
            raise PermissionError(f"Cannot read import path: {import_path}")

        album_folders = []

        for root, _dirs, files in os.walk(import_path):
            # Check if this directory contains audio files
            has_audio = any(
                os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS for f in files
            )
            if has_audio:
                album_folders.append(root)

        return sorted(album_folders)

    def _read_local_album(self, album_path: str) -> LocalAlbumData:
        """Read metadata from audio files in an album folder.

        Args:
            album_path: Path to the album folder.

        Returns:
            LocalAlbumData containing track information.

        Raises:
            FileNotFoundError: If album_path doesn't exist.
            PermissionError: If album_path is not readable.
        """
        if not os.path.isdir(album_path):
            raise FileNotFoundError(f"Album folder not found: {album_path}")

        tracks: List[LocalTrackData] = []
        artists: List[str] = []
        albums: List[str] = []
        formats: List[str] = []

        # Get all audio files — recursively, so a multi-disc rip whose tracks
        # live in "CD 01" / "Disc 2" subfolders analyzes too instead of dying
        # with "No audio files found" (issue #180). The import task uses the
        # same discovery (find_audio_files), so analyze and import agree.
        # os.walk swallows unreadable directories, so check readability first
        # to keep the explicit PermissionError of the old listdir path.
        if not os.access(album_path, os.R_OK):
            raise PermissionError(f"Cannot read album folder: {album_path}")

        audio_files = find_audio_files(album_path)

        for filepath in audio_files:
            if not os.path.isfile(filepath):
                continue

            # Read metadata using mutagen (single pass — collect all fields at once)
            track_data, track_artist, track_album = self._read_track_metadata(filepath)
            # Folder-per-disc rips rarely carry discnumber tags; fall back to
            # the disc subfolder name. A real tag is never overridden.
            if track_data.disc is None:
                track_data.disc = infer_disc_number(filepath, album_path)
            tracks.append(track_data)

            if track_artist:
                artists.append(track_artist)
            if track_album:
                albums.append(track_album)

            track_format = format_label_for_extension(
                os.path.splitext(filepath)[1].lower()
            )
            if track_format:
                formats.append(track_format)

        # Use most common artist/album/format (consensus). For mixed-format
        # albums the dominant format wins; the minority is not surfaced.
        artist = self._get_most_common(artists)
        album = self._get_most_common(albums)
        dominant_format = self._get_most_common(formats)

        # Fallback for untagged rips: when the embedded tags yield no artist
        # and/or album, derive hints from the folder name (e.g. a scene release
        # "Artist-Album-WEB-FLAC-2021-GROUP") so the autotag query has something
        # to match on and the Local Album box is not blank. Folder hints never
        # override real tags; metadata_source records what was actually used.
        metadata_source = "tags"
        if artist is None or album is None:
            folder_artist, folder_album = parse_album_folder_name(
                os.path.basename(os.path.normpath(album_path))
            )
            used_folder = False
            if artist is None and folder_artist:
                artist = folder_artist
                used_folder = True
            if album is None and folder_album:
                album = folder_album
                used_folder = True
            if used_folder:
                # "folder" when nothing came from tags at all, else "mixed".
                metadata_source = (
                    "folder" if not artists and not albums else "mixed"
                )
                # Seed per-track titles from the filenames too, so beets has
                # track-level text to match. Only fills genuinely missing
                # titles; the folder artist (if any) is stripped to avoid a
                # constant prefix on every track.
                for track in tracks:
                    if not track.title:
                        track.title = parse_title_from_filename(
                            os.path.basename(track.path), artist_hint=artist
                        )

        # WAV/FLAC summary drives the convert/dedup buttons on the Local Album
        # card; like the track list above it covers the full folder tree.
        wav_summary = summarize_wav_flac(album_path)

        return LocalAlbumData(
            path=album_path,
            artist=artist,
            album=album,
            tracks=tracks,
            dominant_format=dominant_format,
            metadata_source=metadata_source,
            has_wav=wav_summary.has_wav,
            has_flac=wav_summary.has_flac,
            duplicate_wav_count=wav_summary.duplicate_wav_count,
            has_wma=wav_summary.has_wma,
            wma_recommended_target=wav_summary.wma_recommended_target,
        )

    def _read_track_metadata(self, filepath: str) -> tuple:
        """Read metadata from a single audio file.

        Returns all fields in a single MutagenFile read to avoid double I/O.

        Args:
            filepath: Path to the audio file.

        Returns:
            Tuple of (LocalTrackData, artist_str_or_None, album_str_or_None).
        """
        title = None
        track_num = None
        length = None
        artist = None
        album = None
        disc = None

        try:
            audio = MutagenFile(filepath, easy=True)
            if audio:
                if audio.get("title"):
                    title = audio.get("title")[0]

                if audio.get("tracknumber"):
                    track_num = parse_track_number(audio.get("tracknumber")[0])

                # Same tolerant parsing as tracknumber: "1/2" reads as disc 1.
                if audio.get("discnumber"):
                    disc = parse_track_number(audio.get("discnumber")[0])

                if hasattr(audio, "info") and audio.info:
                    length = audio.info.length

                if audio.get("albumartist"):
                    artist = audio.get("albumartist")[0]
                elif audio.get("artist"):
                    artist = audio.get("artist")[0]

                if audio.get("album"):
                    album = audio.get("album")[0]

        except Exception as e:
            logger.debug(f"Error reading metadata from {filepath}: {e}")

        if track_num is None:
            track_num = parse_track_number_from_filename(os.path.basename(filepath))

        return (
            LocalTrackData(
                path=filepath,
                title=title,
                track_num=track_num,
                length=length,
                disc=disc,
            ),
            artist,
            album,
        )

    def _get_most_common(self, items: List[str]) -> Optional[str]:
        """Get the most common item from a list.

        Args:
            items: List of strings.

        Returns:
            Most common string, or None if list is empty.
        """
        if not items:
            return None
        from collections import Counter

        counter = Counter(items)
        return counter.most_common(1)[0][0]

    def validate_album_path(self, album_path: str, import_path: str) -> str:
        """Validate that album_path is within import_path.

        Args:
            album_path: Path to validate (can be relative or absolute).
            import_path: The library's import folder path.

        Returns:
            The canonical absolute path if valid.

        Raises:
            ValueError: If path escapes import folder or is invalid.
        """
        # Handle relative paths by joining with import_path
        if not os.path.isabs(album_path):
            full_path = os.path.join(import_path, album_path)
        else:
            full_path = album_path

        # Resolve to canonical path (follows symlinks)
        canonical_path = os.path.realpath(full_path)
        canonical_import = os.path.realpath(import_path)

        # Ensure canonical path starts with import folder
        if not (
            canonical_path.startswith(canonical_import + os.sep)
            or canonical_path == canonical_import
        ):
            raise ValueError("Album path must be within the library's import folder")

        return canonical_path

    def analyze_album(
        self, library_slug: str, album_path: str, config_path: Optional[str] = None
    ) -> Tuple[LocalAlbumData, List[CandidateData], datetime, bool]:
        """Analyze an album folder using beets autotag.

        Args:
            library_slug: The library slug (for logging).
            album_path: Absolute path to the album folder.
            config_path: Optional path to beets config file.

        Returns:
            Tuple of (local_album_data, candidates_list, analyzed_at_timestamp,
            augmentation_degraded). ``augmentation_degraded`` is True when the
            provider-augmentation path could not do its job (search failed,
            resolve/merge failed, or every resolve attempt failed) — callers
            should not long-term-cache such a result, a retry may do better.

        Raises:
            FileNotFoundError: If album_path doesn't exist.
            AnalysisTimeoutError: If analysis times out.
            BeetsAnalysisError: If beets encounters an error.
        """
        logger.info(f"Analyzing album for library '{library_slug}': {album_path}")

        if not os.path.isdir(album_path):
            raise FileNotFoundError(f"Album folder not found: {album_path}")

        # Read local album metadata first
        local_album = self._read_local_album(album_path)

        if not local_album.tracks:
            raise FileNotFoundError(f"No audio files found in album folder: {album_path}")

        # Run the native beets autotagger and the multi-provider search
        # concurrently. The autotagger (MusicBrainz via beets) holds the global
        # beets-config lock for the duration of tag_album(); the provider search
        # is mostly lock-free network I/O, so it overlaps for free. Issue #76:
        # the autotagger alone surfaces only MusicBrainz hits (often poor), while
        # the same multi-provider path the manual dialog uses finds exact
        # Spotify/Deezer/Discogs matches.
        with ThreadPoolExecutor(max_workers=2) as executor:
            autotag_future = executor.submit(
                self._run_beets_analysis, album_path, local_album, config_path
            )
            search_future = executor.submit(
                self._search_providers, local_album, config_path
            )

            # The autotagger result is the baseline — let its errors propagate.
            candidates = autotag_future.result()

            # Provider augmentation must never sink the analysis: a search/resolve
            # failure just means we fall back to the autotagger candidates.
            augmentation_degraded = False
            try:
                search_response = search_future.result()
            except Exception as e:  # noqa: BLE001 - augmentation is best-effort
                logger.warning(f"Provider search failed, using autotagger only: {e}")
                search_response = None
                augmentation_degraded = True

        if search_response is not None:
            try:
                provider_candidates, resolves_degraded = self._resolve_search_results(
                    search_response, local_album, candidates, config_path
                )
                candidates = self._merge_candidates(candidates, provider_candidates)
                augmentation_degraded = augmentation_degraded or resolves_degraded
            except Exception as e:  # noqa: BLE001 - augmentation is best-effort
                logger.warning(
                    f"Provider resolve/merge failed, using autotagger only: {e}"
                )
                augmentation_degraded = True

        analyzed_at = datetime.now(timezone.utc)

        return local_album, candidates, analyzed_at, augmentation_degraded

    def _run_beets_analysis(
        self,
        album_path: str,
        local_album: LocalAlbumData,
        config_path: Optional[str] = None,
    ) -> List[CandidateData]:
        """Run beets autotag analysis on an album.

        Args:
            album_path: Path to the album folder.
            local_album: Local album data for comparison.
            config_path: Optional beets config path.

        Returns:
            List of candidate matches.

        Raises:
            AnalysisTimeoutError: If analysis times out.
            BeetsAnalysisError: If beets encounters an error.
        """
        # Import beets modules with specific error handling
        try:
            from beets import autotag, plugins
            from beets import config as beets_config
        except ImportError as e:
            raise BeetsAnalysisError(f"Beets library not installed or not available: {e}")

        def _analyze() -> List[CandidateData]:
            """Inner function to run beets analysis (executed in thread pool)."""
            candidates: List[CandidateData] = []

            # Use lock to serialize access to beets config (global singleton)
            with _beets_config_lock:
                # tag_album pairs the local items against every candidate's
                # tracklist via beets' assign_items — at 500+ tracks one large
                # candidate eats the whole analysis timeout (#175). Guarded
                # here, inside the lock, right before beets can hit it.
                from app.services.candidate_resolvers import (
                    install_large_release_assignment_guard,
                )

                install_large_release_assignment_guard()

                # Configure beets if config path provided
                if config_path and os.path.exists(config_path):
                    beets_config.clear()
                    beets_config.set_file(config_path)
                    beets_config.read()  # Read AFTER setting the file path
                    logger.info(f"Loaded beets config from: {config_path}")

                    # CRITICAL: Load plugins after config is read
                    # Without this, the MusicBrainz plugin won't be active!
                    plugins.load_plugins()
                    logger.info(f"Loaded beets plugins: {beets_config['plugins'].as_str_seq()}")
                else:
                    logger.warning(f"No beets config found at: {config_path if config_path else 'None'}")

                # Get track items from the album folder
                # We need to create beets Item objects from our local tracks
                items, item_to_local = self._create_beets_items(local_album)

                if not items:
                    logger.warning(f"No valid tracks found for beets analysis: {album_path}")
                    return []

                # Debug: Log item metadata
                logger.info(f"Created {len(items)} beets items for analysis")
                if items:
                    first_item = items[0]
                    logger.info(f"  Sample item metadata: artist='{first_item.artist}', album='{first_item.album}', title='{first_item.title}'")

                # Run beets autotag
                try:
                    # tag_album returns (artist, album, Proposal)
                    # where Proposal contains candidates and recommendation
                    logger.info("Calling autotag.tag_album()...")
                    artist_suggestion, album_suggestion, proposal = autotag.tag_album(items)
                    match_candidates = proposal.candidates
                    recommendation = proposal.recommendation

                    logger.info(f"Beets returned {len(match_candidates)} candidates for: {album_path}")
                    logger.info(f"Artist suggestion: {artist_suggestion}, Album suggestion: {album_suggestion}")
                    logger.info(f"Recommendation: {recommendation}")

                    # Convert AlbumMatch objects to our data format
                    for idx, match in enumerate(match_candidates):
                        logger.info(f"Processing candidate {idx+1}/{len(match_candidates)}: distance={match.distance}, info={match.info}")
                        candidate = self._convert_album_match(match, local_album, item_to_local)
                        if candidate:
                            logger.info(f"  ✓ Converted successfully: {candidate.artist} - {candidate.album} (similarity: {candidate.similarity})")
                            candidates.append(candidate)
                        else:
                            logger.warning(f"  ✗ Conversion failed for candidate {idx+1}")

                    logger.info(f"Total candidates after conversion: {len(candidates)}")

                    # Sort by similarity (highest first)
                    candidates.sort(key=lambda c: c.similarity, reverse=True)

                except Exception as e:
                    error_msg = str(e).lower()
                    if "musicbrainz" in error_msg or "network" in error_msg:
                        raise MusicBrainzError(f"Error communicating with MusicBrainz: {e}")
                    raise BeetsAnalysisError(f"Beets analysis error: {e}")

            return candidates

        # Use ThreadPoolExecutor for timeout handling (works in any thread context)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_analyze)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeoutError:
                raise AnalysisTimeoutError(
                    f"Beets analysis timed out after {self.timeout} seconds"
                )
            except MusicBrainzError:
                raise
            except BeetsAnalysisError:
                raise
            except Exception as e:
                logger.error(f"Unexpected error during beets analysis: {e}")
                raise BeetsAnalysisError(f"Unexpected error during analysis: {e}")

    # --- Multi-provider augmentation (issue #76) -------------------------------
    #
    # The native beets autotagger reliably surfaces only MusicBrainz candidates.
    # The manual "add candidate" dialog already queries every configured provider
    # (Spotify/Deezer/Discogs/MusicBrainz) directly and finds exact matches the
    # autotagger misses. These helpers run that same path automatically and merge
    # its hits into the candidate list.

    # How many top-ranked search hits (across all providers, after dedup) we pay
    # to resolve into full candidates. Bounds the added network cost per analysis.
    _MAX_PROVIDER_RESOLVES = 5
    # Per-provider results to request from the search before ranking/dedup.
    _PROVIDER_SEARCH_PER_PAGE = 3

    def _search_providers(self, local_album, config_path):
        """Query every configured provider for the local album's artist/album.

        Returns a ``SearchCandidatesResponse`` (or ``None`` if there is nothing
        to search for). Runs concurrently with the autotagger in
        :meth:`analyze_album`; it deliberately swallows nothing here so the
        caller can decide how to degrade.
        """
        artist = (local_album.artist or "").strip()
        album = (local_album.album or "").strip()
        if not artist and not album:
            logger.info("No local artist/album to search providers with; skipping")
            return None

        from app.services.beets_search_service import (
            DEFAULT_SEARCH_TIMEOUT,
            search_all_providers,
        )

        query = " ".join(part for part in (artist, album) if part)
        logger.info(f"Searching providers for: artist='{artist}', album='{album}'")
        return search_all_providers(
            config_path,
            query=query,
            per_page=self._PROVIDER_SEARCH_PER_PAGE,
            timeout=DEFAULT_SEARCH_TIMEOUT,
            artist=artist or None,
            album=album or None,
        )

    def _resolve_search_results(
        self,
        search_response,
        local_album: LocalAlbumData,
        existing_candidates: List[CandidateData],
        config_path: Optional[str],
    ) -> Tuple[List[CandidateData], bool]:
        """Resolve the best provider search hits into full ``CandidateData``.

        Pre-scores every hit cheaply from its summary fields, drops hits that
        duplicate an autotagger candidate, resolves only the top
        ``_MAX_PROVIDER_RESOLVES`` to bound network cost, and tags each resolved
        candidate with a similarity comparable to the autotagger's distance score
        so the merged list ranks sensibly.

        Returns:
            Tuple of (resolved_candidates, degraded). ``degraded`` is True when
            every resolve attempt errored (provider timeouts/outages) — the
            empty result then says nothing about the album and must not be
            long-term-cached. Hits dropped as duplicates of autotagger
            candidates are not failures.
        """
        # Source/id pairs already produced by the autotagger, so we don't resolve
        # (and later show) the same release twice — issue #76 dedup item.
        seen = {
            (c.source.lower(), c.source_id)
            for c in existing_candidates
            if c.source_id
        }

        # Flatten all provider hits and pre-score from summary fields.
        scored_hits = []
        for group in search_response.providers:
            for item in group.results:
                key = (item.provider.lower(), item.source_id)
                if item.source_id and key in seen:
                    continue
                score = self._score_provider_fields(
                    local_album, item.artist, item.title, item.track_count
                )
                scored_hits.append((score, item))

        # Resolve the highest-scoring hits first; cap the count.
        scored_hits.sort(key=lambda pair: pair[0], reverse=True)
        to_resolve = scored_hits[: self._MAX_PROVIDER_RESOLVES]
        if not to_resolve:
            return [], False

        from app.services.candidate_resolvers import resolve_manual_candidate

        resolved: List[CandidateData] = []
        resolved_keys = set(seen)
        resolve_failures = 0
        for _score, item in to_resolve:
            try:
                candidate = resolve_manual_candidate(
                    self,
                    local_album.path,
                    item.provider,
                    item.source_id,
                    config_path=config_path,
                )
            except Exception as e:  # noqa: BLE001 - skip a single bad hit
                logger.info(
                    f"Could not resolve {item.provider} hit {item.source_id}: {e}"
                )
                resolve_failures += 1
                continue

            key = (candidate.source.lower(), candidate.source_id)
            if candidate.source_id and key in resolved_keys:
                continue
            resolved_keys.add(key)

            # Re-score from the fully resolved candidate (real track count etc.)
            # so the similarity reflects the actual match, not just the summary.
            similarity = self._score_provider_fields(
                local_album,
                candidate.artist,
                candidate.album,
                len(candidate.tracks) if candidate.tracks else None,
            )
            resolved.append(self._candidate_to_data(candidate, similarity))

        degraded = resolve_failures == len(to_resolve)
        logger.info(
            f"Resolved {len(resolved)} provider candidate(s) from "
            f"{len(scored_hits)} search hit(s)"
            + (f" ({resolve_failures} resolve failure(s))" if resolve_failures else "")
        )
        return resolved, degraded

    def _merge_candidates(
        self,
        autotag_candidates: List[CandidateData],
        provider_candidates: List[CandidateData],
    ) -> List[CandidateData]:
        """Merge autotagger and provider candidates, dedup, sort by similarity.

        On a (source, source_id) collision the autotagger candidate wins because
        it carries beets' own track mapping. Provider candidates that don't
        collide are appended. The result is sorted by similarity descending.
        """
        merged = list(autotag_candidates)
        seen = {
            (c.source.lower(), c.source_id)
            for c in autotag_candidates
            if c.source_id
        }
        for candidate in provider_candidates:
            key = (candidate.source.lower(), candidate.source_id)
            if candidate.source_id and key in seen:
                continue
            seen.add(key)
            merged.append(candidate)

        merged.sort(key=lambda c: c.similarity, reverse=True)
        return merged

    @staticmethod
    def _normalize_for_match(value: Optional[str]) -> str:
        """Lowercase, strip, and collapse non-alphanumerics for fuzzy matching."""
        if not value:
            return ""
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def _score_provider_fields(
        self,
        local_album: LocalAlbumData,
        cand_artist: Optional[str],
        cand_album: Optional[str],
        cand_track_count: Optional[int],
    ) -> float:
        """Similarity in [0, 1] for a provider hit vs. the local album.

        Combines fuzzy artist + album string ratios with a track-count agreement
        term. Components whose local side is unknown are dropped and the weights
        renormalized, so a missing local artist doesn't unfairly penalize a hit.
        Roughly comparable to the autotagger's ``1 - distance`` so the merged
        list ranks sensibly (issue #76 open item: comparable scoring).
        """
        import difflib

        def ratio(a: Optional[str], b: Optional[str]) -> float:
            na, nb = self._normalize_for_match(a), self._normalize_for_match(b)
            if not na or not nb:
                return 0.0
            return difflib.SequenceMatcher(None, na, nb).ratio()

        components = []  # (weight, score)
        if local_album.album:
            components.append((0.5, ratio(local_album.album, cand_album)))
        if local_album.artist:
            components.append((0.35, ratio(local_album.artist, cand_artist)))

        local_count = len(local_album.tracks)
        if local_count and cand_track_count:
            diff = abs(local_count - cand_track_count)
            count_score = max(0.0, 1.0 - diff / local_count)
            components.append((0.15, count_score))

        if not components:
            return 0.0

        total_weight = sum(w for w, _ in components)
        score = sum(w * s for w, s in components) / total_weight
        return round(score, 4)

    def _candidate_to_data(self, candidate, similarity: float) -> CandidateData:
        """Convert a resolver ``Candidate`` (pydantic) to ``CandidateData``.

        The resolvers return the API schema type with ``similarity=1.0`` and
        ``is_manual=True``; here we drop ``is_manual`` (these are auto-discovered,
        not user-added), apply the computed similarity, and flatten the nested
        pydantic models to the plain dicts the task serializer expects.
        """
        tracks = [
            CandidateTrackData(
                index=t.index,
                title=t.title,
                length=t.length,
                changes=[c.model_dump() for c in t.changes],
                local_title=t.local_title,
                local_path=t.local_path,
            )
            for t in candidate.tracks
        ]
        return CandidateData(
            source=candidate.source,
            source_id=candidate.source_id,
            similarity=round(similarity, 4),
            artist=candidate.artist,
            album=candidate.album,
            year=candidate.year,
            label=candidate.label,
            country=candidate.country,
            media=candidate.media,
            tracks=tracks,
            changes=[c.model_dump() for c in candidate.changes],
            track_changes=[tc.model_dump() for tc in candidate.track_changes],
        )

    def _create_beets_items(
        self, local_album: LocalAlbumData
    ) -> Tuple[List, Dict[int, LocalTrackData]]:
        """Create beets Item objects from local track data.

        Args:
            local_album: Local album data.

        Returns:
            Tuple of (list of beets Item objects, mapping of id(item) ->
            originating LocalTrackData). The id-keyed map lets us pair a beets
            match item back to its exact local track without re-resolving a
            normalized path string (which can diverge across symlinks, encoding,
            or abspath/realpath differences).
        """
        from beets.library import Item

        # Highest disc across the album: with 2+ discs beets should see the
        # set as one multi-disc album, so items missing disctotal get it
        # backfilled below.
        discs = {track.disc for track in local_album.tracks if track.disc}
        disctotal = max(discs) if len(discs) > 1 else None

        items = []
        item_to_local: Dict[int, LocalTrackData] = {}
        for track in local_album.tracks:
            try:
                # Create a beets Item from the file path
                item = Item.from_path(track.path)
                # Backfill artist/album from the consensus values we already
                # read off the folder (see _read_local_album). Item.from_path
                # only reads embedded file tags; when those are missing beets
                # builds a useless internal search query and tag_album returns
                # zero candidates — even though a manual search for the same
                # artist+album string hits immediately. Mirror that manual path.
                if not item.artist and local_album.artist:
                    item.artist = local_album.artist
                if not item.album and local_album.album:
                    item.album = local_album.album
                # Same for the title: untagged rips get a filename-derived
                # title hint (see _read_local_album) so beets can score tracks.
                if not item.title and track.title:
                    item.title = track.title
                # Multi-disc: stamp the folder-inferred disc (and the disc
                # count) when the file tags don't carry them, so beets scores
                # the set as one proper multi-disc album instead of 200+
                # colliding track numbers (issue #180).
                if track.disc and not getattr(item, "disc", 0):
                    item.disc = track.disc
                if disctotal and not getattr(item, "disctotal", 0):
                    item.disctotal = disctotal
                items.append(item)
                item_to_local[id(item)] = track
            except Exception as e:
                logger.debug(f"Could not create beets Item from {track.path}: {e}")

        return items, item_to_local

    def _convert_album_match(
        self,
        match,
        local_album: LocalAlbumData,
        item_to_local: Optional[Dict[int, LocalTrackData]] = None,
    ) -> Optional[CandidateData]:
        """Convert a beets AlbumMatch to CandidateData.

        Args:
            match: A beets AlbumMatch object.
            local_album: Local album data for comparison.
            item_to_local: Optional mapping of id(beets_item) -> LocalTrackData,
                used to pair match items back to local tracks by identity.

        Returns:
            CandidateData or None if conversion fails.
        """
        try:
            info = match.info

            # Determine source
            source = "MusicBrainz"  # Default
            source_id = None
            if hasattr(info, "album_id"):
                source_id = info.album_id
            if hasattr(info, "data_source"):
                source = info.data_source

            # Get similarity (distance is inverse of similarity)
            similarity = 1.0 - match.distance.distance if match.distance else 0.0

            # Get album-level metadata
            artist = info.artist or ""
            album = info.album or ""
            year = info.year if hasattr(info, "year") else None
            label = info.label if hasattr(info, "label") else None
            country = info.country if hasattr(info, "country") else None
            media = info.media if hasattr(info, "media") else None

            # Build album-level changes
            changes = self._compute_album_changes(local_album, info)

            # Build track data
            tracks, track_changes = self._compute_track_data(
                match, local_album, item_to_local
            )

            return CandidateData(
                source=source,
                source_id=source_id,
                similarity=round(similarity, 4),
                artist=artist,
                album=album,
                year=year,
                label=label,
                country=country,
                media=media,
                tracks=tracks,
                changes=changes,
                track_changes=track_changes,
            )

        except Exception as e:
            logger.error(f"Error converting album match: {e}")
            return None

    def _compute_album_changes(
        self, local_album: LocalAlbumData, candidate_info
    ) -> List[Dict]:
        """Compute album-level metadata changes.

        Args:
            local_album: Local album data.
            candidate_info: Candidate album info from beets.

        Returns:
            List of change dictionaries.
        """
        changes = []

        # Artist change
        local_artist = local_album.artist or ""
        candidate_artist = candidate_info.artist or ""
        if local_artist != candidate_artist:
            changes.append(
                {
                    "field": "artist",
                    "from_value": local_artist if local_artist else None,
                    "to_value": candidate_artist if candidate_artist else None,
                }
            )

        # Album change
        local_album_name = local_album.album or ""
        candidate_album = candidate_info.album or ""
        if local_album_name != candidate_album:
            changes.append(
                {
                    "field": "album",
                    "from_value": local_album_name if local_album_name else None,
                    "to_value": candidate_album if candidate_album else None,
                }
            )

        # Year change
        if hasattr(candidate_info, "year") and candidate_info.year:
            changes.append(
                {
                    "field": "year",
                    "from_value": None,  # We don't track local year currently
                    "to_value": str(candidate_info.year),
                }
            )

        return changes

    @staticmethod
    def _item_length(item) -> Optional[float]:
        """Extract a beets Item's duration in seconds, if available."""
        length = getattr(item, "length", None)
        try:
            return float(length) if length is not None else None
        except (TypeError, ValueError):
            return None

    def _compute_track_data(
        self,
        match,
        local_album: LocalAlbumData,
        item_to_local: Optional[Dict[int, LocalTrackData]] = None,
    ) -> Tuple[List[CandidateTrackData], List[Dict]]:
        """Compute track-level data and changes.

        Args:
            match: A beets AlbumMatch object.
            local_album: Local album data for comparison.
            item_to_local: Optional mapping of id(beets_item) -> LocalTrackData,
                the authoritative item->local pairing captured at item creation.

        Returns:
            Tuple of (track_data_list, track_changes_list).
        """
        item_to_local = item_to_local or {}
        tracks: List[CandidateTrackData] = []
        track_changes: List[Dict] = []

        # Create mappings of local tracks by track number and by canonical path.
        # On a multi-disc album track numbers repeat per disc, so the bare
        # number map collides — the (disc, num) map disambiguates when both
        # sides know their disc.
        local_by_num = {
            t.track_num: t for t in local_album.tracks if t.track_num is not None
        }
        local_by_disc_num = {
            (t.disc, t.track_num): t
            for t in local_album.tracks
            if t.disc is not None and t.track_num is not None
        }
        local_by_path = {
            os.path.normpath(t.path): t for t in local_album.tracks
        }

        def _append(
            track_index, track_title, track_length, local_title, local_path,
            local_length, disc=None
        ):
            """Build one candidate track row paired to its local counterpart."""
            track_meta_changes = []
            if local_title and local_title != track_title:
                track_meta_changes.append(
                    {
                        "field": "title",
                        "from_value": local_title,
                        "to_value": track_title,
                    }
                )

            # Emit a comparison row for every mapped track (not only renamed ones)
            # so the UI can show local vs. candidate duration and the filename even
            # when the title is unchanged.
            track_changes.append(
                {
                    "index": track_index,
                    "disc": disc,
                    "local_title": local_title,
                    "candidate_title": track_title,
                    "local_length": local_length,
                    "candidate_length": track_length,
                    "local_path": local_path,
                }
            )

            tracks.append(
                CandidateTrackData(
                    index=track_index,
                    title=track_title,
                    length=track_length,
                    changes=track_meta_changes,
                    local_title=local_title,
                    local_path=local_path,
                    disc=disc,
                )
            )

        # Get track mapping from the match
        if hasattr(match, "mapping") and match.mapping:
            # mapping is a dict of {beets_item: TrackInfo} — the authoritative
            # local↔candidate pairing produced by beets (survives missing/odd
            # track numbers, reordering, etc.).
            mapped_mediums = {
                getattr(ti, "medium", None)
                for _it, ti in match.mapping.items()
                if ti is not None
            }
            mapped_mediums.discard(None)
            multi_disc = len(mapped_mediums) > 1
            for idx, (item, track_info) in enumerate(match.mapping.items(), start=1):
                if track_info is None:
                    continue

                track_title = track_info.title or ""
                track_length = track_info.length if hasattr(track_info, "length") else None
                # Use the per-disc track number for multi-disc releases (so disc 2
                # track 1 stays "1", not "26"); the disc keeps it on the right CD.
                # Single-disc / providers without media info keep the absolute
                # index and a None disc so serialisation is unchanged.
                medium = getattr(track_info, "medium", None)
                medium_index = getattr(track_info, "medium_index", None)
                disc = medium if multi_disc else None
                if multi_disc and medium_index:
                    track_index = medium_index
                else:
                    track_index = track_info.index if hasattr(track_info, "index") else idx

                # Resolve the beets item back to our LocalTrackData. Identity is
                # authoritative (the item was built from this exact local track);
                # fall back to a normalized-path match for safety. Path strings
                # alone are brittle — symlinks, encoding, or abspath/realpath
                # differences can make them diverge and silently drop the pairing.
                local_track = item_to_local.get(id(item))
                if local_track is None:
                    item_path = getattr(item, "path", None)
                    if item_path is not None:
                        try:
                            decoded = os.path.normpath(os.fsdecode(item_path))
                        except (TypeError, ValueError):
                            decoded = None
                        if decoded:
                            local_track = local_by_path.get(decoded)

                if local_track is not None:
                    local_title = local_track.title
                    local_path = local_track.path
                    local_length = local_track.length
                else:
                    # Path didn't resolve to a known local file: still surface the
                    # beets-read local title so the comparison isn't lost, but leave
                    # local_path None (never an empty string) so local-only
                    # reconciliation in the UI stays correct. Duration still comes
                    # from the beets item, which reads it from the audio file.
                    local_title = getattr(item, "title", None) or None
                    local_path = None
                    local_length = self._item_length(item)

                _append(
                    track_index, track_title, track_length, local_title, local_path,
                    local_length, disc=disc
                )

        elif hasattr(match.info, "tracks") and match.info.tracks:
            # Fall back to candidate track list if no mapping; pair by track number.
            tracklist_mediums = {
                getattr(ti, "medium", None) for ti in match.info.tracks
            }
            tracklist_mediums.discard(None)
            multi_disc = len(tracklist_mediums) > 1
            for track_info in match.info.tracks:
                track_title = track_info.title or ""
                track_length = track_info.length if hasattr(track_info, "length") else None
                medium = getattr(track_info, "medium", None)
                medium_index = getattr(track_info, "medium_index", None)
                disc = medium if multi_disc else None
                if multi_disc and medium_index:
                    track_index = medium_index
                else:
                    track_index = track_info.index if hasattr(track_info, "index") else 1

                local_track = None
                if disc is not None:
                    local_track = local_by_disc_num.get((disc, track_index))
                if local_track is None:
                    local_track = local_by_num.get(track_index)
                local_title = local_track.title if local_track else None
                local_path = local_track.path if local_track else None
                local_length = local_track.length if local_track else None
                _append(
                    track_index, track_title, track_length, local_title, local_path,
                    local_length, disc=disc
                )

        # Sort by (disc, track number) so multi-disc candidates list disc 1
        # in full before disc 2, instead of interleaving the repeated per-disc
        # track numbers.
        tracks.sort(key=lambda t: ((t.disc or 0), t.index))
        track_changes.sort(key=lambda c: ((c.get("disc") or 0), c["index"]))

        return tracks, track_changes


# Singleton instance
_service_instance: Optional[BeetsAutotagService] = None


def get_beets_autotag_service(timeout: int = DEFAULT_ANALYSIS_TIMEOUT) -> BeetsAutotagService:
    """Get the BeetsAutotagService singleton instance.

    Args:
        timeout: Timeout in seconds for analysis operations.

    Returns:
        BeetsAutotagService instance.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = BeetsAutotagService(timeout=timeout)
    return _service_instance
