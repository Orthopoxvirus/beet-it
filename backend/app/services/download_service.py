"""Service for packing multiple albums into a single ZIP archive on disk.

Reuses the single-album zip helpers (path resolution, in-library validation,
filename sanitisation) from ``app.api.libraries`` so the multi-album packer
applies the exact same security and naming rules, then nests each album under
``<album artist>/<album>/`` inside one archive.

Unlike the single-album streaming download, this writes the archive to a file
(the Download Center serves it later), so it is run from a Celery worker.
"""

import logging
import os
import zipfile
from typing import Callable, List, Optional, Tuple

from app.api.libraries import (
    resolve_track_path,
    sanitize_filename_component,
    validate_path_in_library,
)
from app.services.beets_library_service import BeetsLibraryService

logger = logging.getLogger(__name__)

# Read from each source file in 1 MiB chunks while writing the archive so a
# huge album never has to sit in memory.
_CHUNK_SIZE = 1024 * 1024

# Progress callback: (processed_albums, total_albums, current_label) -> None
ProgressCallback = Callable[[int, int, str], None]


def _album_entries(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_path: Optional[str],
    album_id: int,
) -> Tuple[str, List[Tuple[str, str]]]:
    """Resolve one album to (label, [(absolute_path, arcname)]).

    ``arcname`` is nested as ``<album artist>/<album>/<NN - title.ext>`` and
    deduplicated within the album. Missing files and files escaping the library
    are skipped (mirrors ``download_album_zip``). Returns an empty file list if
    the album is unknown or has no downloadable tracks.
    """
    album = beets_service.get_album_by_id(db_path, album_id)
    if album is None:
        logger.warning("Download pack: album %s not found, skipping", album_id)
        return f"album-{album_id}", []

    tracks = beets_service.get_album_tracks(db_path, album_id)

    artist = sanitize_filename_component(album.artist or "", "Unknown Artist")
    title = sanitize_filename_component(album.title or "", f"album-{album_id}")
    album_dir = f"{artist}/{title}"
    label = f"{album.artist} - {album.title}" if album.artist else (album.title or title)

    multi_disc = len({t.disc_number for t in tracks if t.disc_number}) > 1

    files: List[Tuple[str, str]] = []
    used_names: set[str] = set()
    for index, track in enumerate(tracks, start=1):
        absolute_path = resolve_track_path(track.path or "", library_path)
        if not absolute_path or not os.path.exists(absolute_path):
            logger.warning("Download pack: track file missing, skipping: %s", absolute_path)
            continue
        if library_path and not validate_path_in_library(absolute_path, library_path):
            logger.warning("Download pack: path traversal attempt skipped: %s", absolute_path)
            continue

        ext = os.path.splitext(absolute_path)[1]
        track_no = track.track_number or index
        track_title = sanitize_filename_component(track.title or "", f"Track {index}")
        prefix = f"{track.disc_number or 1}-" if multi_disc else ""
        base = f"{prefix}{track_no:02d} - {track_title}"

        candidate, n = f"{base}{ext}", 1
        while candidate in used_names:
            n += 1
            candidate = f"{base} ({n}){ext}"
        used_names.add(candidate)
        files.append((absolute_path, f"{album_dir}/{candidate}"))

    return label, files


def compute_album_size(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_path: Optional[str],
    album_id: int,
) -> Tuple[int, int]:
    """Return (total_size_bytes, track_count) for an album's on-disk track files.

    Used by the gathering bar to show the summed size of selected albums.
    ``library_path`` must be passed so relative beets paths resolve on disk
    (otherwise every track sizes to 0).
    """
    tracks = beets_service.get_album_tracks(db_path, album_id, library_root=library_path)
    total = sum(t.file_size for t in tracks if t.file_size)
    counted = sum(1 for t in tracks if t.file_size)
    return total, counted


def _zip_write_streamed(zf, absolute_path: str, arcname: str) -> bool:
    """Stream one file into the open archive; False when unreadable."""
    try:
        src = open(absolute_path, "rb")
    except OSError:
        logger.warning("Download pack: unreadable track skipped: %s", absolute_path)
        return False
    with src:
        zinfo = zipfile.ZipInfo(arcname)
        zinfo.compress_type = zipfile.ZIP_STORED
        with zf.open(zinfo, mode="w") as dest:
            while True:
                data = src.read(_CHUNK_SIZE)
                if not data:
                    break
                dest.write(data)
    return True


def pack_selection_to_zip(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_path: Optional[str],
    album_ids: List[int],
    track_ids: List[int],
    dest_path: str,
    progress_cb: Optional[ProgressCallback] = None,
) -> Tuple[int, int]:
    """Pack albums (as folders) and/or single titles (flat) into ONE archive.

    Albums keep the ``Artist/Album/track`` nesting of the album packer;
    titles land flat as ``Artist - Title.ext`` like the old BPM-range zips.
    Progress counts one unit per album plus one per title. Returns
    (archive_size_bytes, packed_units); raises ValueError when nothing was
    downloadable (the caller fails the job instead of shipping an empty zip).
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    total = len(album_ids) + len(track_ids)
    processed = 0
    packed_units = 0
    seen_arcnames: set[str] = set()

    # allowZip64: large selections can exceed the 4 GiB / 65k-entry ZIP32 limits.
    with zipfile.ZipFile(dest_path, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for album_id in album_ids:
            label, files = _album_entries(beets_service, db_path, library_path, album_id)
            album_had_file = False
            for absolute_path, arcname in files:
                # Guard against cross-album arcname collisions (same artist /
                # album / track packed twice) so no entry is silently dropped.
                unique_arcname, n = arcname, 1
                root, ext = os.path.splitext(arcname)
                while unique_arcname in seen_arcnames:
                    n += 1
                    unique_arcname = f"{root} ({n}){ext}"
                seen_arcnames.add(unique_arcname)
                if _zip_write_streamed(zf, absolute_path, unique_arcname):
                    album_had_file = True
            if album_had_file:
                packed_units += 1
            processed += 1
            if progress_cb:
                progress_cb(processed, total, label)

        tracks = beets_service.get_tracks_by_ids(db_path, track_ids, library_root=library_path)
        for track in tracks:
            label = f"{track.artist} - {track.title}" if track.artist else (track.title or f"track-{track.id}")
            processed += 1

            absolute_path = resolve_track_path(track.path or "", library_path)
            if not absolute_path or not os.path.exists(absolute_path):
                logger.warning("Download pack: track file missing, skipping: %s", absolute_path)
                if progress_cb:
                    progress_cb(processed, total, label)
                continue
            if library_path and not validate_path_in_library(absolute_path, library_path):
                logger.warning("Download pack: path traversal attempt skipped: %s", absolute_path)
                if progress_cb:
                    progress_cb(processed, total, label)
                continue

            ext = os.path.splitext(absolute_path)[1]
            artist = sanitize_filename_component(track.artist or "", "Unknown Artist")
            title = sanitize_filename_component(track.title or "", f"track-{track.id}")
            base = f"{artist} - {title}"

            arcname, n = f"{base}{ext}", 1
            while arcname in seen_arcnames:
                n += 1
                arcname = f"{base} ({n}){ext}"
            seen_arcnames.add(arcname)

            if _zip_write_streamed(zf, absolute_path, arcname):
                packed_units += 1
            if progress_cb:
                progress_cb(processed, total, label)

    if packed_units == 0:
        # Don't leave a useless empty archive behind.
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise ValueError("No downloadable files found for the selection")

    return os.path.getsize(dest_path), packed_units


def pack_albums_to_zip(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_path: Optional[str],
    album_ids: List[int],
    dest_path: str,
    progress_cb: Optional[ProgressCallback] = None,
) -> Tuple[int, int]:
    """Album-only convenience wrapper around :func:`pack_selection_to_zip`."""
    return pack_selection_to_zip(
        beets_service=beets_service,
        db_path=db_path,
        library_path=library_path,
        album_ids=album_ids,
        track_ids=[],
        dest_path=dest_path,
        progress_cb=progress_cb,
    )


def pack_tracks_to_zip(
    beets_service: BeetsLibraryService,
    db_path: str,
    library_path: Optional[str],
    track_ids: List[int],
    dest_path: str,
    progress_cb: Optional[ProgressCallback] = None,
) -> Tuple[int, int]:
    """Track-only convenience wrapper around :func:`pack_selection_to_zip`.

    The flat "Artist - Title.ext" structure is deliberate — sports-watch sync
    tools want a plain file list, not artist/album nesting.
    """
    return pack_selection_to_zip(
        beets_service=beets_service,
        db_path=db_path,
        library_path=library_path,
        album_ids=[],
        track_ids=track_ids,
        dest_path=dest_path,
        progress_cb=progress_cb,
    )
