"""ScannerService for scanning import folders and extracting audio metadata."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Optional, Dict, Any, List, Callable, Tuple

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC, VCFLACDict
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4

logger = logging.getLogger(__name__)

# Supported audio file extensions
AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".ogg",
    ".opus",
    ".m4a",
    ".mp4",
    ".aac",
    ".wma",
    ".wav",
    ".aiff",
    ".aif",
    ".ape",
    ".wv",
    ".mpc",
    ".dsf",
    ".dff",
}


def is_audio_filename(name: str) -> bool:
    """Return True if a filename has a recognised audio extension.

    Pure helper shared by the scanner and the import-items API so both agree on
    what counts as a track. Sidecar files (cover art, .m3u, .sfv, .nfo, …) are
    not audio and must never be treated as importable tracks.
    """
    if not name:
        return False
    _, ext = os.path.splitext(name.lower())
    return ext in AUDIO_EXTENSIONS


@dataclass
class AudioMetadata:
    """Container for extracted audio metadata."""

    album: Optional[str] = None
    album_artist: Optional[str] = None
    artist: Optional[str] = None
    title: Optional[str] = None
    track_number: Optional[int] = None
    track_total: Optional[int] = None
    genre: Optional[str] = None
    # Audio quality
    format: Optional[str] = None  # Container format, e.g. "mp3", "flac"
    bitrate: Optional[int] = None  # Bitrate in kbps


@dataclass
class ScannedItem:
    """Container for a scanned file or folder."""

    path: str
    item_type: str  # 'file' or 'folder'
    directory: str
    filename: str
    metadata: Optional[AudioMetadata] = None
    is_audio: bool = False


@dataclass
class ScanResult:
    """Container for scan results."""

    items: List[ScannedItem]
    total_files: int
    total_folders: int
    audio_files: int
    errors: List[str]


class ScannerService:
    """Service for scanning import folders and extracting audio metadata."""

    def __init__(
        self,
        batch_size: int = 100,
        timeout_seconds: int = 3600,
    ):
        """Initialize the scanner service.

        Args:
            batch_size: Number of items to process before progress update.
            timeout_seconds: Maximum scan duration in seconds.
        """
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds

    def _is_audio_file(self, path: str) -> bool:
        """Check if a file is an audio file based on extension.

        Args:
            path: File path to check.

        Returns:
            True if the file appears to be an audio file.
        """
        return is_audio_filename(path)

    def _is_hidden(self, path: str) -> bool:
        """Check if a path component is hidden.

        Args:
            path: Path to check.

        Returns:
            True if any component starts with a dot.
        """
        parts = path.split(os.sep)
        return any(part.startswith(".") for part in parts if part)

    def _extract_metadata(self, path: str) -> Optional[AudioMetadata]:
        """Extract audio metadata from a file.

        Args:
            path: Path to the audio file.

        Returns:
            AudioMetadata object or None if extraction failed.
        """
        try:
            audio = mutagen.File(path, easy=True)
            if audio is None:
                logger.debug(f"Could not read audio file: {path}")
                return None

            metadata = AudioMetadata()

            # By default read tags straight off the easy view. For FLAC files
            # that (illegally, per spec) carry more than one VORBIS_COMMENT
            # block, mutagen exposes only the first block — so when title/track
            # live in a later block, fall back to a merged view of all blocks.
            tag_source: Any = audio
            if isinstance(audio, FLAC):
                merged = self._merge_flac_vorbis_blocks(audio)
                if merged is not None:
                    tag_source = merged

            # Handle different tag formats
            if hasattr(tag_source, "get"):
                # Easy tags (most common formats)
                metadata.album = self._get_first_tag(tag_source, ["album"])
                metadata.album_artist = self._get_first_tag(
                    tag_source, ["albumartist", "album artist", "ALBUMARTIST"]
                )
                metadata.artist = self._get_first_tag(tag_source, ["artist"])
                metadata.title = self._get_first_tag(tag_source, ["title"])
                metadata.genre = self._get_first_tag(tag_source, ["genre"])

                # Track number handling (format can be "3" or "3/12")
                track = self._get_first_tag(tag_source, ["tracknumber", "track"])
                if track:
                    if "/" in track:
                        # Handle "3/12" format - extract both track number and total
                        parts = track.split("/")
                        try:
                            metadata.track_number = int(parts[0])
                        except ValueError:
                            pass
                        if len(parts) > 1:
                            try:
                                metadata.track_total = int(parts[1])
                            except ValueError:
                                pass
                    else:
                        try:
                            metadata.track_number = int(track)
                        except ValueError:
                            pass

                # Also check for separate totaltracks/tracktotal tag
                if metadata.track_total is None:
                    total_track = self._get_first_tag(
                        tag_source, ["totaltracks", "tracktotal"]
                    )
                    if total_track:
                        try:
                            metadata.track_total = int(total_track)
                        except ValueError:
                            pass

            # Special handling for MP4/M4A
            if isinstance(audio, MP4):
                metadata = self._extract_mp4_metadata(audio)

            # Audio quality is independent of the tag format, so set it last so
            # it survives the MP4 branch (which returns a fresh metadata object).
            metadata.format = self._extract_format(path)
            metadata.bitrate = self._extract_bitrate(audio)

            return metadata

        except mutagen.MutagenError as e:
            logger.warning(f"Error extracting metadata from {path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error extracting metadata from {path}: {e}")
            return None

    def _extract_format(self, path: str) -> Optional[str]:
        """Derive the container format from a file extension.

        Returns the lowercased extension without the leading dot (e.g. "mp3",
        "flac"), or None if the path has no recognised audio extension.
        """
        _, ext = os.path.splitext(path.lower())
        if not ext:
            return None
        ext = ext.lstrip(".")
        return ext if f".{ext}" in AUDIO_EXTENSIONS else None

    def _extract_bitrate(self, audio: Any) -> Optional[int]:
        """Read the bitrate from a mutagen audio object, in kbps.

        mutagen reports bitrate in bits/second; we surface kbps to match the
        convention used elsewhere in the codebase. Returns None when the format
        does not expose a bitrate (e.g. some lossless containers).
        """
        info = getattr(audio, "info", None)
        bitrate = getattr(info, "bitrate", None)
        if not bitrate:
            return None
        try:
            return round(int(bitrate) / 1000)
        except (TypeError, ValueError):
            return None

    def _merge_flac_vorbis_blocks(
        self, audio: FLAC
    ) -> Optional[Dict[str, List[str]]]:
        """Merge all VORBIS_COMMENT blocks of a FLAC into one tag mapping.

        The FLAC spec allows only a single VORBIS_COMMENT block, but some rips
        (e.g. SoX / "WALKMAN") embed two: one carrying album/artist and a
        second holding title/track. mutagen surfaces only the first block via
        its easy/tags view, so those fields would otherwise be lost and beets
        autotagging would match poorly.

        We collect every comment block and merge field by field, keeping the
        first non-empty value and preferring blocks that carry title/track when
        a key appears in more than one block.

        Args:
            audio: A mutagen FLAC object.

        Returns:
            A lowercased ``{tag: [values]}`` mapping when the file has more than
            one comment block, otherwise ``None`` (the normal easy view is
            already correct for the common single-block case).
        """
        vc_blocks = [
            block
            for block in audio.metadata_blocks
            if isinstance(block, VCFLACDict)
        ]
        if len(vc_blocks) <= 1:
            return None

        def carries_title_or_track(block: VCFLACDict) -> bool:
            for key in block.keys():
                if key.lower() in ("title", "track", "tracknumber") and block[key]:
                    return True
            return False

        # Blocks with title/track take priority on conflicting keys; document
        # order is preserved within each priority group.
        primary = [b for b in vc_blocks if carries_title_or_track(b)]
        secondary = [b for b in vc_blocks if not carries_title_or_track(b)]

        merged: Dict[str, List[str]] = {}
        for block in primary + secondary:
            for key in block.keys():
                value = block[key]
                if value and key.lower() not in merged:
                    merged[key.lower()] = value
        return merged

    def _get_first_tag(
        self, audio: Any, tag_names: List[str]
    ) -> Optional[str]:
        """Get the first available tag value.

        Args:
            audio: Mutagen audio object.
            tag_names: List of tag names to try.

        Returns:
            First available tag value or None.
        """
        for tag_name in tag_names:
            try:
                value = audio.get(tag_name)
                if value:
                    if isinstance(value, list):
                        return str(value[0]) if value else None
                    return str(value)
            except Exception:
                continue
        return None

    def _extract_mp4_metadata(self, audio: MP4) -> AudioMetadata:
        """Extract metadata from MP4/M4A files.

        Args:
            audio: MP4 audio object.

        Returns:
            AudioMetadata object.
        """
        metadata = AudioMetadata()

        # MP4 uses different tag keys
        tag_mapping = {
            "\xa9alb": "album",
            "aART": "album_artist",
            "\xa9ART": "artist",
            "\xa9nam": "title",
            "\xa9gen": "genre",
        }

        for mp4_key, attr_name in tag_mapping.items():
            value = audio.tags.get(mp4_key) if audio.tags else None
            if value:
                if isinstance(value, list):
                    setattr(metadata, attr_name, str(value[0]) if value else None)
                else:
                    setattr(metadata, attr_name, str(value))

        # Track number for MP4 (format is tuple: (track_number, track_total))
        track_data = audio.tags.get("trkn") if audio.tags else None
        if track_data and isinstance(track_data, list) and len(track_data) > 0:
            track_tuple = track_data[0]
            if isinstance(track_tuple, tuple):
                if len(track_tuple) > 0 and track_tuple[0]:
                    metadata.track_number = int(track_tuple[0])
                if len(track_tuple) > 1 and track_tuple[1]:
                    metadata.track_total = int(track_tuple[1])

        return metadata

    def scan_directory(
        self,
        import_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Iterator[ScannedItem]:
        """Scan a directory and yield items.

        This is a generator that yields items as they are discovered,
        making it memory-efficient for large directories.

        Args:
            import_path: Path to the import folder.
            progress_callback: Optional callback(processed, total, current_file).

        Yields:
            ScannedItem objects for each file and folder.
        """
        if not os.path.isdir(import_path):
            logger.error(f"Import path does not exist: {import_path}")
            return

        start_time = datetime.now(timezone.utc)
        processed = 0

        # First pass: count total items for progress tracking
        total_items = 0
        for root, dirs, files in os.walk(import_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            rel_root = os.path.relpath(root, import_path)
            if not self._is_hidden(rel_root):
                total_items += len(dirs) + len(files)

        logger.info(f"Starting scan of {import_path}: {total_items} items to process")

        # Second pass: process items
        for root, dirs, files in os.walk(import_path):
            # Check timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > self.timeout_seconds:
                logger.warning(
                    f"Scan timeout reached after {elapsed:.0f}s for {import_path}"
                )
                return

            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            # Skip if we're in a hidden path
            rel_root = os.path.relpath(root, import_path)
            if self._is_hidden(rel_root) and rel_root != ".":
                continue

            # Process directories
            for dirname in dirs:
                full_path = os.path.join(root, dirname)
                parent_dir = root

                yield ScannedItem(
                    path=full_path,
                    item_type="folder",
                    directory=parent_dir,
                    filename=dirname,
                    is_audio=False,
                )

                processed += 1
                if progress_callback and processed % self.batch_size == 0:
                    progress_callback(processed, total_items, full_path)

            # Process files
            for filename in files:
                # Skip hidden files
                if filename.startswith("."):
                    continue

                full_path = os.path.join(root, filename)
                parent_dir = root
                is_audio = self._is_audio_file(full_path)

                # Extract metadata for audio files
                metadata = None
                if is_audio:
                    metadata = self._extract_metadata(full_path)

                yield ScannedItem(
                    path=full_path,
                    item_type="file",
                    directory=parent_dir,
                    filename=filename,
                    metadata=metadata,
                    is_audio=is_audio,
                )

                processed += 1
                if progress_callback and processed % self.batch_size == 0:
                    progress_callback(processed, total_items, full_path)

        # Final progress update
        if progress_callback:
            progress_callback(processed, total_items, "")

        logger.info(
            f"Scan complete for {import_path}: {processed} items processed"
        )

    def scan_directory_full(
        self,
        import_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> ScanResult:
        """Scan a directory and return full results.

        This loads all items into memory. Use scan_directory for
        memory-efficient streaming.

        Args:
            import_path: Path to the import folder.
            progress_callback: Optional callback(processed, total, current_file).

        Returns:
            ScanResult with all items and statistics.
        """
        items = []
        total_files = 0
        total_folders = 0
        audio_files = 0
        errors = []

        for item in self.scan_directory(import_path, progress_callback):
            items.append(item)

            if item.item_type == "file":
                total_files += 1
                if item.is_audio:
                    audio_files += 1
            else:
                total_folders += 1

        return ScanResult(
            items=items,
            total_files=total_files,
            total_folders=total_folders,
            audio_files=audio_files,
            errors=errors,
        )

    def detect_changes(
        self,
        current_items: Dict[str, ScannedItem],
        previous_items: Dict[str, Dict[str, Any]],
    ) -> Tuple[List[str], List[str], List[str], List[str]]:
        """Detect changes between current and previous scan.

        Args:
            current_items: Dict of path -> ScannedItem from current scan.
            previous_items: Dict of path -> item data from previous scan.

        Returns:
            Tuple of (new_paths, modified_paths, unchanged_paths, deleted_paths).
        """
        new_paths = []
        modified_paths = []
        unchanged_paths = []
        deleted_paths = []

        current_paths = set(current_items.keys())
        previous_paths = set(previous_items.keys())

        # New items
        for path in current_paths - previous_paths:
            new_paths.append(path)

        # Deleted items
        for path in previous_paths - current_paths:
            deleted_paths.append(path)

        # Check for modifications in existing items
        for path in current_paths & previous_paths:
            current = current_items[path]
            previous = previous_items[path]

            # Compare metadata for audio files
            if current.is_audio and current.metadata:
                prev_meta = previous.get("metadata", {}) or {}
                curr_meta = current.metadata

                # Check if any metadata changed
                changed = (
                    curr_meta.album != prev_meta.get("album")
                    or curr_meta.album_artist != prev_meta.get("album_artist")
                    or curr_meta.artist != prev_meta.get("artist")
                    or curr_meta.title != prev_meta.get("title")
                    or curr_meta.track_number != prev_meta.get("track_number")
                    or curr_meta.track_total != prev_meta.get("track_total")
                    or curr_meta.genre != prev_meta.get("genre")
                )

                if changed:
                    modified_paths.append(path)
                else:
                    unchanged_paths.append(path)
            else:
                # Non-audio files/folders are unchanged if they exist
                unchanged_paths.append(path)

        return new_paths, modified_paths, unchanged_paths, deleted_paths

    def get_item_count(self, import_path: str) -> int:
        """Get approximate item count for progress tracking.

        Args:
            import_path: Path to the import folder.

        Returns:
            Approximate number of items.
        """
        if not os.path.isdir(import_path):
            return 0

        count = 0
        for root, dirs, files in os.walk(import_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            count += len(dirs) + len(files)

        return count
