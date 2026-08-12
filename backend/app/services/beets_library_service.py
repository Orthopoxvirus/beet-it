"""Service for reading album data from beets SQLite databases."""

import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.redis_keys import RedisKeyManager

logger = logging.getLogger(__name__)


@dataclass
class AlbumData:
    """Container for album data from beets database."""
    id: int
    title: str
    artist: str
    cover_art_path: Optional[str]
    # mtime of the cover file, used as a cache-buster in cover URLs so a
    # replaced cover is re-fetched instead of served stale from the browser
    # cache. None when the album has no stored artpath.
    cover_version: Optional[int] = None


@dataclass
class AlbumDetailData:
    """Container for detailed album data from beets database."""
    id: int
    title: str
    artist: str
    year: Optional[int]
    genre: Optional[str]
    label: Optional[str]
    total_tracks: int
    total_duration: float
    cover_art_path: Optional[str]
    cover_version: Optional[int]
    disc_count: int
    added: Optional[datetime]
    album_type: Optional[str]
    mb_albumid: Optional[str]
    format: Optional[str]
    bitrate: Optional[int]
    sample_rate: Optional[int]
    bit_depth: Optional[int]
    channels: Optional[int]


@dataclass
class TrackData:
    """Container for track data from beets database."""
    id: int
    title: str
    artist: str
    album: str
    album_id: int
    track_number: int
    disc_number: int
    duration: float
    format: str
    bitrate: int
    sample_rate: int
    channels: int
    file_size: int
    path: str
    mb_trackid: Optional[str]


class BeetsLibraryService:
    """Service for querying beets SQLite library databases.

    This service provides read-only access to beets library databases
    to retrieve album information. It uses SQLite URI mode to ensure
    connections are always read-only.
    """

    # Cover art discovery configuration
    COVER_ART_FILENAMES = ["cover", "albumart", "folder", "front"]
    COVER_ART_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif"]

    def _validate_database_path(self, db_path: str) -> None:
        """Validate that the database path exists and is accessible.

        Args:
            db_path: Path to the beets SQLite database file.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Beets database not found: {db_path}")

        if not os.access(db_path, os.R_OK):
            raise PermissionError(f"Cannot read beets database: {db_path}")

    def _connect_readonly(self, db_path: str) -> sqlite3.Connection:
        """Create a read-only connection to the beets database.

        Args:
            db_path: Path to the beets SQLite database file.

        Returns:
            sqlite3.Connection in read-only mode.

        Raises:
            sqlite3.OperationalError: If the database cannot be opened.
        """
        # Use URI mode with mode=ro for read-only access
        uri = f"file:{db_path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _decode_artpath(self, artpath_value) -> Optional[str]:
        """Decode the artpath value from beets database.

        In beets, artpath is stored as BLOB (bytes), so we need to
        decode it to a string.

        Args:
            artpath_value: The raw artpath value from the database (bytes or str or None).

        Returns:
            Decoded string path, or None if artpath is null/empty.
        """
        if artpath_value is None:
            return None
        if isinstance(artpath_value, bytes):
            try:
                return artpath_value.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Failed to decode artpath as UTF-8, trying latin-1")
                try:
                    return artpath_value.decode("latin-1")
                except UnicodeDecodeError:
                    logger.error("Failed to decode artpath")
                    return None
        return str(artpath_value) if artpath_value else None

    def _resolve_against_root(
        self, path: Optional[str], library_root: Optional[str]
    ) -> Optional[str]:
        """Resolve a possibly-relative beets path to an absolute one.

        beets (lscr.io/linuxserver image) stores item/art paths relative to
        the library ``directory:``. Without joining them against that root,
        ``os.path`` checks resolve against the container CWD and fail.
        """
        if not path:
            return None
        if os.path.isabs(path) or not library_root:
            return path
        return os.path.join(library_root.rstrip("/"), path)

    def _cover_version(
        self, artpath: Optional[str], library_root: Optional[str]
    ) -> Optional[int]:
        """Integer cache-buster for an album cover: the cover file's mtime.

        Uses only the stored ``artpath`` (no folder discovery) so it stays
        cheap on the album-list path. Returns None when there is no artpath
        or the file can't be stat'd — callers then emit an un-busted URL.
        """
        resolved = self._resolve_against_root(artpath, library_root)
        if not resolved:
            return None
        try:
            return int(os.path.getmtime(resolved))
        except OSError:
            return None

    def get_albums(
        self,
        db_path: str,
        skip: int = 0,
        limit: int = 50,
        library_root: Optional[str] = None,
    ) -> tuple[list[AlbumData], int]:
        """Query albums from a beets database with pagination.

        Args:
            db_path: Path to the beets SQLite database file.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            Tuple of (list of AlbumData, total album count).

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            # Get total count
            cursor.execute("SELECT COUNT(*) FROM albums")
            total = cursor.fetchone()[0]

            # Query albums with pagination, sorted by albumartist then album
            cursor.execute(
                """
                SELECT id, album, albumartist, artpath
                FROM albums
                ORDER BY albumartist, album
                LIMIT ? OFFSET ?
                """,
                (limit, skip),
            )

            albums = []
            for row in cursor.fetchall():
                cover_art_path = self._decode_artpath(row["artpath"])
                album = AlbumData(
                    id=row["id"],
                    title=row["album"] or "",
                    artist=row["albumartist"] or "",
                    cover_art_path=cover_art_path,
                    cover_version=self._cover_version(cover_art_path, library_root),
                )
                albums.append(album)

            connection.close()
            logger.debug(f"Retrieved {len(albums)} albums from {db_path} (total: {total})")
            return albums, total

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_album_cover_path(self, db_path: str, album_id: int) -> Optional[str]:
        """Get the cover art path for a specific album.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID in the beets database.

        Returns:
            The cover art file path, or None if not found or no cover art.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            cursor.execute(
                "SELECT artpath FROM albums WHERE id = ?",
                (album_id,),
            )

            row = cursor.fetchone()
            connection.close()

            if row is None:
                return None

            return self._decode_artpath(row["artpath"])

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def album_exists(self, db_path: str, album_id: int) -> bool:
        """Check if an album exists in the beets database.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID to check.

        Returns:
            True if the album exists, False otherwise.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            cursor.execute(
                "SELECT 1 FROM albums WHERE id = ?",
                (album_id,),
            )

            exists = cursor.fetchone() is not None
            connection.close()

            return exists

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_album_folder_path(self, db_path: str, album_id: int) -> Optional[str]:
        """Get the folder path for an album by querying item paths.

        Derives the album folder from the first item's path in the album.
        This is needed when artpath is null and we need to scan for cover art.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID in the beets database.

        Returns:
            The album folder path, or None if album has no items.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            # Get the path of the first item in the album
            cursor.execute(
                "SELECT path FROM items WHERE album_id = ? LIMIT 1",
                (album_id,),
            )

            row = cursor.fetchone()
            connection.close()

            if row is None:
                return None

            # Decode the path (stored as BLOB in beets)
            item_path = self._decode_artpath(row["path"])
            if not item_path:
                return None

            # Return the parent directory
            return os.path.dirname(item_path)

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_tracked_item_paths(
        self, db_path: str, library_root: Optional[str] = None
    ) -> set[str]:
        """Return the set of absolute, normalized file paths beets tracks.

        Reads every ``items.path`` (stored as a BLOB, possibly relative to the
        library ``directory:``), decodes it, resolves it against
        ``library_root`` and normalizes it. Used to tell stray (untracked)
        files on disk apart from files beets owns.
        """
        self._validate_database_path(db_path)
        paths: set[str] = set()
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT path FROM items")
            for row in cursor.fetchall():
                decoded = self._decode_artpath(row["path"])
                resolved = self._resolve_against_root(decoded, library_root)
                if resolved:
                    paths.add(os.path.normpath(resolved))
        finally:
            connection.close()
        return paths

    def get_tracked_item_dirs(
        self, db_path: str, library_root: Optional[str] = None
    ) -> set[str]:
        """Return the set of directories that contain at least one tracked item.

        A folder absent from this set holds no beets-tracked audio — i.e. it is
        a fully stray (unimported) album folder.
        """
        return {
            os.path.dirname(p)
            for p in self.get_tracked_item_paths(db_path, library_root)
        }

    def get_tracked_dir_albums(
        self, db_path: str, library_root: Optional[str] = None
    ) -> dict[str, Optional[int]]:
        """Map each tracked folder to the single album living in it.

        A folder holding items from more than one album maps to ``None``
        (ambiguous — callers must not attach folder-level actions like
        cover promotion to it).
        """
        self._validate_database_path(db_path)
        mapping: dict[str, Optional[int]] = {}
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT album_id, path FROM items")
            for row in cursor.fetchall():
                decoded = self._decode_artpath(row["path"])
                resolved = self._resolve_against_root(decoded, library_root)
                if not resolved:
                    continue
                folder = os.path.dirname(os.path.normpath(resolved))
                album_id = row["album_id"]
                if folder in mapping:
                    if mapping[folder] != album_id:
                        mapping[folder] = None
                else:
                    mapping[folder] = album_id
        finally:
            connection.close()
        return mapping

    def resolve_album_folder(
        self, db_path: str, album_id: int, library_root: str
    ) -> str:
        """Resolve the single on-disk folder that holds *only* this album.

        Unlike :meth:`get_album_folder_path` (which just takes the first
        item's dirname for cover-art lookup), this is the safety-critical
        resolver used before destructive file operations (delete / move to
        import). It guarantees, raising ``ValueError`` otherwise, that:

          - the album has tracks on disk,
          - every track lives in one and the same folder,
          - that folder is strictly below ``library_root`` (not the root),
          - no *other* album has items inside that folder (mixed-folder guard
            — otherwise a delete would silently take another album's tracks).

        Beets stores item paths either absolute or relative to the library
        root (a lscr.io/linuxserver/beets image quirk); both forms
        are normalised to absolute against ``library_root``.

        Returns the absolute album folder path.
        """
        self._validate_database_path(db_path)
        root = os.path.normpath(library_root).rstrip(os.sep)

        def _to_abs(raw) -> str:
            path = self._decode_artpath(raw) or ""
            if not path:
                return ""
            if os.path.isabs(path):
                return os.path.normpath(path)
            return os.path.normpath(os.path.join(root, path))

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()
            cursor.execute("SELECT album_id, path FROM items")
            rows = cursor.fetchall()
            connection.close()
        except sqlite3.DatabaseError as e:
            if "malformed" in str(e).lower():
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "locked" in msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

        album_dirs: set[str] = set()
        other_dirs: list[tuple[int, str]] = []
        for row in rows:
            abs_path = _to_abs(row["path"])
            if not abs_path:
                continue
            parent = os.path.dirname(abs_path)
            if row["album_id"] == album_id:
                album_dirs.add(parent)
            else:
                other_dirs.append((row["album_id"], parent))

        if not album_dirs:
            raise ValueError(f"Album {album_id} has no tracks on disk")
        if len(album_dirs) != 1:
            raise ValueError(
                f"Album {album_id} tracks span multiple folders: "
                f"{sorted(album_dirs)} — refusing."
            )
        album_folder = album_dirs.pop()

        if album_folder == root or not album_folder.startswith(root + os.sep):
            raise ValueError(
                f"Album {album_id} folder '{album_folder}' is not below the "
                f"library root '{root}' — refusing."
            )

        for other_id, other_dir in other_dirs:
            if other_dir == album_folder or other_dir.startswith(album_folder + os.sep):
                raise ValueError(
                    f"Folder '{album_folder}' also holds items from album "
                    f"{other_id}; refusing to remove a shared folder."
                )

        return album_folder

    def discover_cover_art(self, album_folder: str) -> Optional[str]:
        """Discover cover art in an album folder.

        Searches for common cover art filenames with supported image extensions.
        Search is case-insensitive and follows priority ordering.

        Args:
            album_folder: Path to the album folder to search.

        Returns:
            Full path to discovered cover art file, or None if not found.
        """
        if not os.path.isdir(album_folder):
            return None

        try:
            # Get list of files in directory (case-insensitive matching)
            files_in_dir = os.listdir(album_folder)
            files_lower_map = {f.lower(): f for f in files_in_dir}

            # Search in priority order
            for filename in self.COVER_ART_FILENAMES:
                for ext in self.COVER_ART_EXTENSIONS:
                    target = f"{filename}{ext}"
                    if target in files_lower_map:
                        return os.path.join(album_folder, files_lower_map[target])

            return None

        except (PermissionError, OSError):
            return None

    def get_album_cover_path_with_fallback(
        self,
        db_path: str,
        album_id: int,
        redis_manager: Optional["RedisKeyManager"] = None,
        library_root: Optional[str] = None,
    ) -> Optional[str]:
        """Get the cover art path with fallback discovery.

        First checks the beets database artpath field. If null or file doesn't
        exist, performs fallback discovery by searching the album folder.
        Results are cached in Redis to avoid repeated filesystem scans.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID in the beets database.
            redis_manager: Optional Redis manager for caching discovered paths.
            library_root: Optional library directory used to resolve relative
                artpath / item paths (lscr.io/linuxserver/beets stores them
                relative). Without this, relative paths fail os.path.exists
                because the backend container's CWD is not the library root.

        Returns:
            The cover art file path (absolute on disk), or None if not found.
        """
        def _resolve(path: Optional[str]) -> Optional[str]:
            if not path:
                return None
            if os.path.isabs(path):
                return path
            if not library_root:
                return path
            return os.path.join(library_root.rstrip("/"), path)

        # First, try the artpath from the database
        artpath = _resolve(self.get_album_cover_path(db_path, album_id))

        if artpath and os.path.exists(artpath):
            return artpath

        # Check Redis cache for discovered path
        if redis_manager:
            cached_path = redis_manager.get_discovered_cover_art(db_path, album_id)
            if cached_path is not None:
                # Empty string means "no cover art found" (negative cache)
                if cached_path == "":
                    return None
                resolved_cached = _resolve(cached_path)
                if resolved_cached and os.path.exists(resolved_cached):
                    return resolved_cached
                # Cached path no longer exists, need to re-discover

        # Perform fallback discovery
        album_folder = _resolve(self.get_album_folder_path(db_path, album_id))
        if not album_folder or not os.path.isdir(album_folder):
            # Cache negative result
            if redis_manager:
                redis_manager.set_discovered_cover_art(db_path, album_id, "")
            return None

        discovered_path = self.discover_cover_art(album_folder)

        # Cache the result (empty string for negative cache)
        if redis_manager:
            redis_manager.set_discovered_cover_art(
                db_path, album_id, discovered_path or ""
            )

        return discovered_path

    def get_album_letters(self, db_path: str) -> list[str]:
        """Query distinct starting letters from album titles.

        Retrieves unique first characters from all album titles in the library.
        Letters A-Z are returned as uppercase, sorted alphabetically.
        Non-alphabetic characters (numbers, special chars) are grouped under '#'.

        Args:
            db_path: Path to the beets SQLite database file.

        Returns:
            Sorted list of uppercase letters (A-Z) and '#' for non-alphabetic.
            Returns empty list if library has no albums.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            # Query distinct first characters from album titles
            cursor.execute("""
                SELECT DISTINCT UPPER(SUBSTR(album, 1, 1)) AS first_char
                FROM albums
                WHERE album IS NOT NULL AND album != ''
            """)

            # Collect and categorize letters
            alpha_letters = set()
            has_non_alpha = False

            for row in cursor.fetchall():
                char = row["first_char"]
                if char and char.isalpha():
                    alpha_letters.add(char.upper())
                elif char:
                    has_non_alpha = True

            connection.close()

            # Build sorted result: A-Z alphabetically, then '#' at end
            result = sorted(alpha_letters)
            if has_non_alpha:
                result.append("#")

            logger.debug(f"Retrieved {len(result)} distinct letters from {db_path}")
            return result

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_album_by_id(
        self, db_path: str, album_id: int, library_root: Optional[str] = None
    ) -> Optional[AlbumDetailData]:
        """Get detailed album data by ID.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID in the beets database.

        Returns:
            AlbumDetailData with full album metadata, or None if not found.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            # Query album with aggregated track info
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.album,
                    a.albumartist,
                    a.year,
                    COALESCE(NULLIF(a.genres, ''), a.genre) AS genre,
                    a.label,
                    a.artpath,
                    a.added,
                    a.albumtype,
                    a.mb_albumid,
                    COUNT(i.id) as track_count,
                    COALESCE(SUM(i.length), 0) as total_duration,
                    COALESCE(MAX(i.disc), 1) as disc_count
                FROM albums a
                LEFT JOIN items i ON a.id = i.album_id
                WHERE a.id = ?
                GROUP BY a.id
                """,
                (album_id,),
            )

            row = cursor.fetchone()

            if row is None:
                connection.close()
                return None

            # Find the dominant audio characteristics for the album. Most albums
            # are uniform, so GROUP BY + ORDER BY COUNT DESC returns one row that
            # represents the whole album.
            cursor.execute(
                """
                SELECT format, bitrate, samplerate, bitdepth, channels, COUNT(*) AS n
                FROM items
                WHERE album_id = ?
                GROUP BY format, bitrate, samplerate, bitdepth, channels
                ORDER BY n DESC
                LIMIT 1
                """,
                (album_id,),
            )
            quality = cursor.fetchone()

            connection.close()

            # Parse added timestamp (stored as float/epoch in beets)
            added = None
            if row["added"]:
                try:
                    added = datetime.fromtimestamp(row["added"])
                except (ValueError, OSError, TypeError):
                    pass

            fmt = None
            bitrate = None
            samplerate = None
            bitdepth = None
            channels = None
            if quality is not None:
                fmt = (quality["format"] or "").upper() or None
                bitrate = quality["bitrate"] if quality["bitrate"] else None
                samplerate = quality["samplerate"] if quality["samplerate"] else None
                bitdepth = quality["bitdepth"] if quality["bitdepth"] else None
                channels = quality["channels"] if quality["channels"] else None

            cover_art_path = self._decode_artpath(row["artpath"])

            return AlbumDetailData(
                id=row["id"],
                title=row["album"] or "",
                artist=row["albumartist"] or "",
                year=row["year"] if row["year"] and row["year"] > 0 else None,
                genre=row["genre"] if row["genre"] else None,
                label=row["label"] if row["label"] else None,
                total_tracks=row["track_count"],
                total_duration=row["total_duration"] or 0,
                cover_art_path=cover_art_path,
                cover_version=self._cover_version(cover_art_path, library_root),
                disc_count=row["disc_count"] or 1,
                added=added,
                album_type=row["albumtype"] if row["albumtype"] else None,
                mb_albumid=row["mb_albumid"] if row["mb_albumid"] else None,
                format=fmt,
                bitrate=bitrate,
                sample_rate=samplerate,
                bit_depth=bitdepth,
                channels=channels,
            )

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_item_ids_missing_bpm(self, db_path: str) -> list[int]:
        """IDs of items with no usable ``bpm`` (beets stores "unset" as 0/NULL)."""
        self._validate_database_path(db_path)
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM items WHERE bpm IS NULL OR bpm <= 0 ORDER BY id"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            connection.close()

    def count_items_with_bpm(self, db_path: str, item_ids: list[int]) -> int:
        """How many of ``item_ids`` now have a usable ``bpm`` stored."""
        return len(self.get_item_ids_with_bpm(db_path, item_ids))

    def get_item_ids_with_bpm(self, db_path: str, item_ids: list[int]) -> set[int]:
        """Which of ``item_ids`` now have a usable ``bpm`` stored."""
        if not item_ids:
            return set()
        self._validate_database_path(db_path)
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            placeholders = ",".join("?" for _ in item_ids)
            cursor.execute(
                f"SELECT id FROM items WHERE id IN ({placeholders}) AND bpm > 0",
                item_ids,
            )
            return {row[0] for row in cursor.fetchall()}
        finally:
            connection.close()

    @staticmethod
    def _titles_where(
        search: Optional[str],
        bpm_min: Optional[float],
        bpm_max: Optional[float],
        include_half_double: bool,
        album_artists: Optional[list[str]] = None,
    ) -> tuple[str, list]:
        """Shared WHERE clause for the titles listing/select-all queries.

        ``include_half_double`` also matches half and double tempo — beat
        detection routinely suffers octave errors (150 BPM detected as 75 and
        vice versa), so a 150-160 query optionally also catches 75-80/300-320.

        ``album_artists`` restricts to tracks whose album artist is one of the
        given names (the Titles page artist filter). Deliberately not applied
        when building the artist-list dropdown, so the choices stay stable.
        """
        clauses: list[str] = []
        params: list = []
        if search:
            like = f"%{search}%"
            clauses.append(
                "(i.title LIKE ? OR i.artist LIKE ? OR a.album LIKE ? OR a.albumartist LIKE ?)"
            )
            params += [like, like, like, like]
        if album_artists:
            placeholders = ",".join("?" for _ in album_artists)
            clauses.append(f"a.albumartist IN ({placeholders})")
            params += list(album_artists)
        if bpm_min is not None and bpm_max is not None:
            bpm = "(i.bpm >= ? AND i.bpm <= ?)"
            bpm_params: list[float] = [bpm_min, bpm_max]
            if include_half_double:
                bpm += " OR (i.bpm >= ? AND i.bpm <= ?) OR (i.bpm >= ? AND i.bpm <= ?)"
                bpm_params += [bpm_min / 2, bpm_max / 2, bpm_min * 2, bpm_max * 2]
            clauses.append(f"i.bpm IS NOT NULL AND i.bpm > 0 AND ({bpm})")
            params += bpm_params
        where = " AND ".join(clauses) if clauses else "1=1"
        return where, params

    def search_library_titles(
        self,
        db_path: str,
        *,
        search: Optional[str] = None,
        bpm_min: Optional[float] = None,
        bpm_max: Optional[float] = None,
        include_half_double: bool = False,
        album_artists: Optional[list[str]] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> tuple[list[dict], int]:
        """Search individual titles (tracks) with text + BPM filters, paginated.

        Backs the Titles page. Returns (rows, total) with each row carrying
        the display fields plus ``bpm``/``length`` for the filter columns.
        """
        self._validate_database_path(db_path)
        where, params = self._titles_where(
            search, bpm_min, bpm_max, include_half_double, album_artists
        )
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM items i LEFT JOIN albums a ON i.album_id = a.id
                WHERE {where}
                """,
                params,
            )
            total = cursor.fetchone()[0]

            offset = (max(page, 1) - 1) * per_page
            cursor.execute(
                f"""
                SELECT
                    i.id, i.title, i.artist, a.albumartist, a.album, i.album_id,
                    i.bpm, i.length, i.format, i.bitrate
                FROM items i LEFT JOIN albums a ON i.album_id = a.id
                WHERE {where}
                ORDER BY i.artist COLLATE NOCASE, i.title COLLATE NOCASE, i.id
                LIMIT ? OFFSET ?
                """,
                [*params, per_page, offset],
            )
            rows = [
                {
                    "id": r["id"],
                    "title": r["title"] or "",
                    "artist": r["artist"] or "",
                    "albumartist": r["albumartist"] or "",
                    "album": r["album"] or "",
                    "album_id": r["album_id"],
                    "bpm": r["bpm"] if r["bpm"] and r["bpm"] > 0 else None,
                    "length": r["length"],
                    "format": r["format"],
                    "bitrate": r["bitrate"],
                }
                for r in cursor.fetchall()
            ]
            return rows, total
        finally:
            connection.close()

    def search_library_title_ids(
        self,
        db_path: str,
        *,
        search: Optional[str] = None,
        bpm_min: Optional[float] = None,
        bpm_max: Optional[float] = None,
        include_half_double: bool = False,
        album_artists: Optional[list[str]] = None,
    ) -> list[dict]:
        """All titles matching the same filters, id + display fields only.

        Backs "select all results" for the download gather — kept minimal so
        even multi-thousand-track results stay a small payload.
        """
        self._validate_database_path(db_path)
        where, params = self._titles_where(
            search, bpm_min, bpm_max, include_half_double, album_artists
        )
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT i.id, i.title, i.artist
                FROM items i LEFT JOIN albums a ON i.album_id = a.id
                WHERE {where}
                ORDER BY i.artist COLLATE NOCASE, i.title COLLATE NOCASE, i.id
                """,
                params,
            )
            return [
                {"id": r["id"], "title": r["title"] or "", "artist": r["artist"] or ""}
                for r in cursor.fetchall()
            ]
        finally:
            connection.close()

    def list_library_artists(
        self,
        db_path: str,
        *,
        search: Optional[str] = None,
        bpm_min: Optional[float] = None,
        bpm_max: Optional[float] = None,
        include_half_double: bool = False,
    ) -> tuple[list[str], list[str]]:
        """Distinct album artists, split for the Titles page filter dropdown.

        Returns ``(in_result, others)``: album artists present in the current
        search + BPM result first, then the remaining library album artists —
        each alphabetical (case-insensitive). The artist selection itself is
        intentionally not a parameter here; the choices must stay stable as
        the user checks and unchecks them.
        """
        self._validate_database_path(db_path)
        where, params = self._titles_where(search, bpm_min, bpm_max, include_half_double)
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            # Every album artist in the library (skip NULL/blank — e.g. tracks
            # with no album row after the LEFT JOIN).
            cursor.execute(
                """
                SELECT DISTINCT a.albumartist
                FROM items i LEFT JOIN albums a ON i.album_id = a.id
                WHERE a.albumartist IS NOT NULL AND a.albumartist != ''
                ORDER BY a.albumartist COLLATE NOCASE
                """
            )
            all_artists = [r["albumartist"] for r in cursor.fetchall()]
            # Album artists present in the current search + BPM result.
            cursor.execute(
                f"""
                SELECT DISTINCT a.albumartist
                FROM items i LEFT JOIN albums a ON i.album_id = a.id
                WHERE a.albumartist IS NOT NULL AND a.albumartist != '' AND ({where})
                """,
                params,
            )
            in_set = {r["albumartist"] for r in cursor.fetchall()}
            in_result = [a for a in all_artists if a in in_set]
            others = [a for a in all_artists if a not in in_set]
            return in_result, others
        finally:
            connection.close()

    def get_tracks_by_ids(
        self, db_path: str, item_ids: list[int], library_root: Optional[str] = None
    ) -> list[TrackData]:
        """Fetch TrackData for specific item IDs (same shape as get_album_tracks).

        Order follows ``item_ids``. Unknown IDs are silently skipped. Items
        without an album row (singletons) still resolve, with an empty album.
        """
        if not item_ids:
            return []
        self._validate_database_path(db_path)
        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            found: dict[int, TrackData] = {}
            CHUNK = 500
            for start in range(0, len(item_ids), CHUNK):
                chunk = item_ids[start:start + CHUNK]
                placeholders = ",".join("?" * len(chunk))
                cursor.execute(
                    f"""
                    SELECT
                        i.id, i.title, i.artist, COALESCE(a.album, i.album) AS album,
                        i.album_id, i.track, i.disc, i.length, i.format,
                        i.bitrate, i.samplerate, i.channels, i.path, i.mb_trackid
                    FROM items i
                    LEFT JOIN albums a ON i.album_id = a.id
                    WHERE i.id IN ({placeholders})
                    """,
                    chunk,
                )
                for row in cursor.fetchall():
                    path = self._decode_artpath(row["path"]) or ""
                    resolved_path = self._resolve_against_root(path, library_root)
                    file_size = 0
                    if resolved_path and os.path.exists(resolved_path):
                        try:
                            file_size = os.path.getsize(resolved_path)
                        except OSError:
                            pass
                    fmt = row["format"] or ""
                    if not fmt and path:
                        _, ext = os.path.splitext(path)
                        fmt = ext.lstrip(".").lower() if ext else ""
                    found[row["id"]] = TrackData(
                        id=row["id"],
                        title=row["title"] or "",
                        artist=row["artist"] or "",
                        album=row["album"] or "",
                        album_id=row["album_id"] or 0,
                        track_number=row["track"] or 0,
                        disc_number=row["disc"] or 0,
                        duration=row["length"] or 0.0,
                        format=fmt,
                        bitrate=row["bitrate"] or 0,
                        sample_rate=row["samplerate"] or 0,
                        channels=row["channels"] or 0,
                        file_size=file_size,
                        path=path,
                        mb_trackid=row["mb_trackid"],
                    )
            return [found[i] for i in item_ids if i in found]
        finally:
            connection.close()

    def get_album_tracks(
        self, db_path: str, album_id: int, library_root: Optional[str] = None
    ) -> list[TrackData]:
        """Get all tracks for an album, ordered by disc and track number.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID in the beets database.
            library_root: Optional library ``directory:`` used to resolve
                relative beets paths so ``file_size`` can be read from disk.
                Without it, relative paths (lscr.io/linuxserver default) resolve
                against the container CWD and every track reports a size of 0.

        Returns:
            List of TrackData for the album, ordered by disc_number then track_number.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    i.id,
                    i.title,
                    i.artist,
                    a.album,
                    i.album_id,
                    i.track,
                    i.disc,
                    i.length,
                    i.format,
                    i.bitrate,
                    i.samplerate,
                    i.channels,
                    i.path,
                    i.mb_trackid
                FROM items i
                JOIN albums a ON i.album_id = a.id
                WHERE i.album_id = ?
                ORDER BY i.disc, i.track
                """,
                (album_id,),
            )

            tracks = []
            for row in cursor.fetchall():
                path = self._decode_artpath(row["path"]) or ""
                # Resolve relative paths against the library root for the
                # on-disk size lookup; keep `path` (stored on TrackData) as the
                # raw beets value so existing callers are unaffected.
                resolved_path = self._resolve_against_root(path, library_root)
                file_size = 0
                if resolved_path and os.path.exists(resolved_path):
                    try:
                        file_size = os.path.getsize(resolved_path)
                    except OSError:
                        pass

                # Extract format from path extension if not in DB
                fmt = row["format"] or ""
                if not fmt and path:
                    _, ext = os.path.splitext(path)
                    fmt = ext.lstrip(".").lower() if ext else ""

                tracks.append(TrackData(
                    id=row["id"],
                    title=row["title"] or "",
                    artist=row["artist"] or "",
                    album=row["album"] or "",
                    album_id=row["album_id"],
                    track_number=row["track"] or 0,
                    disc_number=row["disc"] or 1,
                    duration=row["length"] or 0,
                    format=fmt,
                    bitrate=row["bitrate"] or 0,
                    sample_rate=row["samplerate"] or 0,
                    channels=row["channels"] or 2,
                    file_size=file_size,
                    path=path,
                    mb_trackid=row["mb_trackid"] if row["mb_trackid"] else None,
                ))

            connection.close()
            logger.debug(f"Retrieved {len(tracks)} tracks for album {album_id} from {db_path}")
            return tracks

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_track_by_id(self, db_path: str, track_id: int) -> Optional[TrackData]:
        """Get a single track by ID.

        Args:
            db_path: Path to the beets SQLite database file.
            track_id: The item (track) ID in the beets database.

        Returns:
            TrackData for the track, or None if not found.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    i.id,
                    i.title,
                    i.artist,
                    a.album,
                    i.album_id,
                    i.track,
                    i.disc,
                    i.length,
                    i.format,
                    i.bitrate,
                    i.samplerate,
                    i.channels,
                    i.path,
                    i.mb_trackid
                FROM items i
                JOIN albums a ON i.album_id = a.id
                WHERE i.id = ?
                """,
                (track_id,),
            )

            row = cursor.fetchone()
            connection.close()

            if row is None:
                return None

            path = self._decode_artpath(row["path"]) or ""
            file_size = 0
            if path and os.path.exists(path):
                try:
                    file_size = os.path.getsize(path)
                except OSError:
                    pass

            # Extract format from path extension if not in DB
            fmt = row["format"] or ""
            if not fmt and path:
                _, ext = os.path.splitext(path)
                fmt = ext.lstrip(".").lower() if ext else ""

            return TrackData(
                id=row["id"],
                title=row["title"] or "",
                artist=row["artist"] or "",
                album=row["album"] or "",
                album_id=row["album_id"],
                track_number=row["track"] or 0,
                disc_number=row["disc"] or 1,
                duration=row["length"] or 0,
                format=fmt,
                bitrate=row["bitrate"] or 0,
                sample_rate=row["samplerate"] or 0,
                channels=row["channels"] or 2,
                file_size=file_size,
                path=path,
                mb_trackid=row["mb_trackid"] if row["mb_trackid"] else None,
            )

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def _connect_readwrite(self, db_path: str) -> sqlite3.Connection:
        """Create a read-write connection to the beets database.

        Args:
            db_path: Path to the beets SQLite database file.

        Returns:
            sqlite3.Connection in read-write mode.

        Raises:
            sqlite3.OperationalError: If the database cannot be opened.
        """
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def find_existing_album(
        self,
        db_path: str,
        mb_albumid: Optional[str] = None,
        albumartist: Optional[str] = None,
        album: Optional[str] = None,
    ) -> Optional[dict]:
        """Find an existing album in the beets library.

        Used before importing to detect duplicates. Preference order:
        1. Exact ``mb_albumid`` match (when the candidate came from MusicBrainz).
        2. Case-insensitive ``albumartist`` + ``album`` match as a fallback for
           non-MusicBrainz candidates.

        Returns None when no match is found, or a dict with album details and
        a ``match_reason`` indicating which branch matched.
        """
        if not mb_albumid and not (albumartist and album):
            return None

        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            if mb_albumid:
                cursor.execute(
                    "SELECT id, albumartist, album FROM albums WHERE mb_albumid = ? LIMIT 1",
                    (mb_albumid,),
                )
                row = cursor.fetchone()
                if row:
                    connection.close()
                    return {
                        "album_id": row["id"],
                        "artist": row["albumartist"] or "",
                        "album": row["album"] or "",
                        "match_reason": "mb_albumid",
                    }

            if albumartist and album:
                cursor.execute(
                    """
                    SELECT id, albumartist, album
                    FROM albums
                    WHERE LOWER(albumartist) = LOWER(?) AND LOWER(album) = LOWER(?)
                    LIMIT 1
                    """,
                    (albumartist, album),
                )
                row = cursor.fetchone()
                if row:
                    connection.close()
                    return {
                        "album_id": row["id"],
                        "artist": row["albumartist"] or "",
                        "album": row["album"] or "",
                        "match_reason": "artist_album",
                    }

            connection.close()
            return None

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def compute_album_stats(
        self,
        db_path: str,
        album_id: int,
        library_root: Optional[str] = None,
    ) -> dict:
        """Aggregate track_count / total_bytes / duration / dominant format /
        avg bitrate for an existing album.

        All fields fall back to zero / None if the data is missing, so callers
        can surface partial stats rather than failing the whole response.
        """
        self._validate_database_path(db_path)

        stats = {
            "track_count": 0,
            "total_bytes": 0,
            "total_duration_seconds": 0.0,
            "dominant_format": None,
            "avg_bitrate_kbps": None,
        }

        connection = self._connect_readonly(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT path, length, bitrate, format FROM items WHERE album_id = ?",
                (album_id,),
            )
            rows = cursor.fetchall()
        finally:
            connection.close()

        if not rows:
            return stats

        stats["track_count"] = len(rows)
        total_duration = 0.0
        total_bytes = 0
        weighted_bitrate_sum = 0.0
        weighted_bitrate_weight = 0.0
        fmt_counts: Dict[str, int] = {}

        normalised_root = (
            os.path.normpath(library_root).rstrip(os.sep) if library_root else None
        )

        for row in rows:
            length = row["length"] or 0
            total_duration += float(length)
            bitrate = row["bitrate"] or 0
            if bitrate and length:
                weighted_bitrate_sum += float(bitrate) * float(length)
                weighted_bitrate_weight += float(length)
            fmt = (row["format"] or "").upper()
            if fmt:
                fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1

            decoded_path = self._decode_artpath(row["path"])
            if not decoded_path:
                continue
            absolute = decoded_path
            if not os.path.isabs(absolute) and normalised_root:
                absolute = os.path.join(normalised_root, decoded_path)
            try:
                total_bytes += os.path.getsize(absolute)
            except OSError:
                pass

        stats["total_duration_seconds"] = total_duration
        stats["total_bytes"] = total_bytes
        if fmt_counts:
            stats["dominant_format"] = max(fmt_counts.items(), key=lambda kv: kv[1])[0]
        if weighted_bitrate_weight > 0:
            # beets stores bitrate in bits-per-second; surface kbps to the UI.
            stats["avg_bitrate_kbps"] = int(
                round(weighted_bitrate_sum / weighted_bitrate_weight / 1000)
            )

        return stats

    def delete_album(self, db_path: str, album_id: int) -> bool:
        """Remove an album, its items, and their flexible-attribute rows from
        the beets database.

        This only touches the DB — the audio files on disk are left in place
        (they will be overwritten by the subsequent import if the destination
        path matches). Used to clear the existing beets entry during an
        "upgrade" import so we don't end up with two rows for the same album.

        Returns True if a row was deleted, False if no such album existed.
        """
        self._validate_database_path(db_path)

        def _table_exists(cursor, name: str) -> bool:
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            )
            return cursor.fetchone() is not None

        try:
            connection = self._connect_readwrite(db_path)
            cursor = connection.cursor()

            # Flexible attributes live in side tables keyed by entity id; beets
            # has no FK cascade, so clean them explicitly (before the items go)
            # or they linger as orphans. Guarded: stripped-down DBs may lack
            # the tables.
            if _table_exists(cursor, "item_attributes"):
                cursor.execute(
                    "DELETE FROM item_attributes WHERE entity_id IN "
                    "(SELECT id FROM items WHERE album_id = ?)",
                    (album_id,),
                )
            if _table_exists(cursor, "album_attributes"):
                cursor.execute(
                    "DELETE FROM album_attributes WHERE entity_id = ?",
                    (album_id,),
                )
            cursor.execute("DELETE FROM items WHERE album_id = ?", (album_id,))
            cursor.execute("DELETE FROM albums WHERE id = ?", (album_id,))
            rows_affected = cursor.rowcount
            connection.commit()
            connection.close()

            return rows_affected > 0

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def update_album_artpath(self, db_path: str, album_id: int, artpath: str) -> bool:
        """Update the artpath field for an album.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID to update.
            artpath: The new cover art path.

        Returns:
            True if the album was updated, False if album not found.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not writable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readwrite(db_path)
            cursor = connection.cursor()

            # Encode path as bytes (how beets stores it)
            artpath_bytes = artpath.encode("utf-8")

            cursor.execute(
                "UPDATE albums SET artpath = ? WHERE id = ?",
                (artpath_bytes, album_id),
            )

            rows_affected = cursor.rowcount
            connection.commit()
            connection.close()

            if rows_affected > 0:
                logger.info(f"Updated artpath for album {album_id} to {artpath}")
                return True
            return False

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def relocate_cover_after_move(
        self,
        db_path: str,
        album_id: int,
        library_root: Optional[str],
        pre_move_cover_path: Optional[str],
    ) -> Optional[str]:
        """Keep an album's standalone cover with its tracks after a beets move.

        ``beet move`` only relocates album art that beets knows about — its
        ``artpath`` column. beet-it imports leave ``artpath`` null and rely on
        in-folder cover discovery, so when an album-artist (or other path
        template) edit moves the tracks to a new folder, the ``cover.jpg`` is
        left orphaned in the old folder. This reconciles that: given the cover
        path captured *before* the move, it ensures a cover ends up in the new
        album folder and points ``artpath`` at it.

        Idempotent and scoped to real moves — it no-ops when the album folder
        is unchanged or when beets (or anything else) already placed a cover in
        the new folder. Returns the final absolute cover path, or None when
        there was nothing to do.

        Args:
            db_path: Path to the beets SQLite database file.
            album_id: The album ID (stable across the move).
            library_root: Library ``directory:`` for resolving relative paths.
            pre_move_cover_path: Absolute cover path resolved *before* the move
                (e.g. via :meth:`get_album_cover_path_with_fallback`).
        """
        if not pre_move_cover_path:
            return None

        new_folder = self._resolve_against_root(
            self.get_album_folder_path(db_path, album_id), library_root
        )
        if not new_folder or not os.path.isdir(new_folder):
            return None

        old_folder = os.path.dirname(pre_move_cover_path)
        if os.path.normpath(old_folder) == os.path.normpath(new_folder):
            # Album folder didn't change — no relocation needed.
            return None

        existing = self.discover_cover_art(new_folder)
        if existing:
            # A cover already made it to the new folder (beets moved it, or it
            # was there all along). Just make sure artpath isn't dangling.
            final = existing
        elif os.path.exists(pre_move_cover_path):
            dest = os.path.join(new_folder, os.path.basename(pre_move_cover_path))
            if not os.path.exists(dest):
                try:
                    shutil.move(pre_move_cover_path, dest)
                except OSError as exc:
                    logger.warning(
                        f"Failed to relocate cover for album {album_id} "
                        f"({pre_move_cover_path} -> {dest}): {exc}"
                    )
                    return None
            final = dest
        else:
            # Cover vanished from the old folder and never reached the new one.
            return None

        try:
            self.update_album_artpath(db_path, album_id, final)
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            # The file is in the right place; a stale artpath only costs a
            # discovery fallback on the next read, so don't fail the move.
            logger.warning(
                f"Relocated cover for album {album_id} but failed to update "
                f"artpath to {final}: {exc}"
            )
        logger.info(f"Reconciled cover for album {album_id} -> {final}")
        return final

    # =========================================================================
    # Library Items Query Methods (for batch edit)
    # =========================================================================

    def get_library_items(
        self,
        db_path: str,
        album: Optional[str] = None,
        album_id: Optional[object] = None,
        page: int = 1,
        per_page: int = 100,
        page_size: Optional[int] = None,
    ) -> tuple[list["LibraryItemData"], int]:
        """Query library items (tracks) with optional album filter and pagination.

        Args:
            db_path: Path to the beets SQLite database file.
            album: Optional album title to filter by.
            album_id: Optional album id filter. Accepts:
                - ``int`` or ``str`` convertible to int: single-album filter.
                - ``list[int]``: multi-album filter; items from any of the
                  given albums are returned, ordered by album_id then track.
            page: Page number (1-indexed).
            per_page: Number of items per page.
            page_size: Alias for `per_page`; takes precedence when provided.

        Returns:
            Tuple of (list of LibraryItemData, total item count).

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        if page_size is not None:
            per_page = page_size

        # Normalise album_id into either None, a single int, or a list[int].
        album_ids: Optional[list[int]] = None
        single_album_id: Optional[int] = None
        if isinstance(album_id, (list, tuple, set)):
            ids = [int(x) for x in album_id if x is not None]
            if len(ids) == 1:
                single_album_id = ids[0]
            elif ids:
                album_ids = ids
        elif album_id is not None:
            single_album_id = int(album_id)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            # Build query based on whether we're filtering by album_id (preferred) or album name
            if album_ids is not None:
                placeholders = ",".join("?" for _ in album_ids)
                count_query = f"SELECT COUNT(*) FROM items WHERE album_id IN ({placeholders})"
                cursor.execute(count_query, album_ids)
            elif single_album_id is not None:
                count_query = "SELECT COUNT(*) FROM items WHERE album_id = ?"
                cursor.execute(count_query, (single_album_id,))
            elif album is not None:
                count_query = """
                    SELECT COUNT(*)
                    FROM items i
                    JOIN albums a ON i.album_id = a.id
                    WHERE a.album = ?
                """
                cursor.execute(count_query, (album,))
            else:
                count_query = "SELECT COUNT(*) FROM items"
                cursor.execute(count_query)

            total = cursor.fetchone()[0]

            # Calculate offset
            offset = (page - 1) * per_page

            # Query items with pagination
            if album_ids is not None:
                placeholders = ",".join("?" for _ in album_ids)
                items_query = f"""
                    SELECT
                        i.id,
                        i.path,
                        i.title,
                        i.artist,
                        a.album,
                        a.albumartist,
                        i.track,
                        i.disc,
                        COALESCE(NULLIF(i.genres, ''), i.genre) AS genre,
                        a.year,
                        i.format,
                        i.bitrate,
                        i.album_id
                    FROM items i
                    JOIN albums a ON i.album_id = a.id
                    WHERE i.album_id IN ({placeholders})
                    ORDER BY i.album_id, i.disc, i.track, i.title
                    LIMIT ? OFFSET ?
                """
                cursor.execute(items_query, [*album_ids, per_page, offset])
            elif single_album_id is not None:
                items_query = """
                    SELECT
                        i.id,
                        i.path,
                        i.title,
                        i.artist,
                        a.album,
                        a.albumartist,
                        i.track,
                        i.disc,
                        COALESCE(NULLIF(i.genres, ''), i.genre) AS genre,
                        a.year,
                        i.format,
                        i.bitrate,
                        i.album_id
                    FROM items i
                    JOIN albums a ON i.album_id = a.id
                    WHERE i.album_id = ?
                    ORDER BY i.disc, i.track, i.title
                    LIMIT ? OFFSET ?
                """
                cursor.execute(items_query, (single_album_id, per_page, offset))
            elif album is not None:
                items_query = """
                    SELECT
                        i.id,
                        i.path,
                        i.title,
                        i.artist,
                        a.album,
                        a.albumartist,
                        i.track,
                        i.disc,
                        COALESCE(NULLIF(i.genres, ''), i.genre) AS genre,
                        a.year,
                        i.format,
                        i.bitrate,
                        i.album_id
                    FROM items i
                    JOIN albums a ON i.album_id = a.id
                    WHERE a.album = ?
                    ORDER BY i.disc, i.track, i.title
                    LIMIT ? OFFSET ?
                """
                cursor.execute(items_query, (album, per_page, offset))
            else:
                items_query = """
                    SELECT
                        i.id,
                        i.path,
                        i.title,
                        i.artist,
                        a.album,
                        a.albumartist,
                        i.track,
                        i.disc,
                        COALESCE(NULLIF(i.genres, ''), i.genre) AS genre,
                        a.year,
                        i.format,
                        i.bitrate,
                        i.album_id
                    FROM items i
                    JOIN albums a ON i.album_id = a.id
                    ORDER BY a.albumartist, a.album, i.disc, i.track
                    LIMIT ? OFFSET ?
                """
                cursor.execute(items_query, (per_page, offset))

            items = []
            for row in cursor.fetchall():
                path = self._decode_artpath(row["path"]) or ""
                directory = os.path.dirname(path) if path else ""
                filename = os.path.basename(path) if path else ""

                items.append(LibraryItemData(
                    id=row["id"],
                    path=path,
                    filename=filename,
                    directory=directory,
                    album=row["album"] or "",
                    album_artist=row["albumartist"] or "",
                    artist=row["artist"] or "",
                    title=row["title"] or "",
                    track_number=row["track"] if row["track"] else None,
                    disc_number=row["disc"] if row["disc"] else None,
                    genre=row["genre"] if row["genre"] else None,
                    year=row["year"] if row["year"] and row["year"] > 0 else None,
                    album_id=row["album_id"],
                    format=(row["format"] or None),
                    bitrate=row["bitrate"] if row["bitrate"] else None,
                ))

            connection.close()
            logger.debug(f"Retrieved {len(items)} library items from {db_path} (total: {total})")
            return items, total

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_albums_for_picker(
        self,
        db_path: str,
    ) -> list[dict]:
        """Get list of albums for the album picker.

        Returns a list of all albums with their ID, title, artist, and track count.

        Args:
            db_path: Path to the beets SQLite database file.

        Returns:
            List of dictionaries with album id, title, artist, and track_count.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            query = """
                SELECT
                    a.id,
                    a.album AS title,
                    a.albumartist AS artist,
                    COUNT(i.id) AS track_count
                FROM albums a
                LEFT JOIN items i ON a.id = i.album_id
                GROUP BY a.id
                ORDER BY a.albumartist, a.album
            """
            cursor.execute(query)

            albums = []
            for row in cursor.fetchall():
                albums.append({
                    "id": row["id"],
                    "title": row["title"] or "",
                    "artist": row["artist"] or "",
                    "track_count": row["track_count"] or 0,
                })

            connection.close()
            logger.debug(f"Retrieved {len(albums)} albums from {db_path}")
            return albums

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_library_tree(
        self,
        db_path: str,
        library_root: str,
    ) -> dict:
        """Build a nested folder tree from the beets DB's item paths.

        Reads `SELECT path, album_id FROM items`, makes each item path relative
        to `library_root`, and walks the resulting path segments to build a
        tree. Each folder node carries the union of album_ids of the items at
        or below it, and an `is_album` flag that's true when the folder holds
        tracks directly (not just subfolders).

        Returns a dict with shape
            {"library_path": <library_root>, "root": <node dict>}
        where `<node dict>` is
            {"name": str, "path": str, "is_album": bool,
             "album_ids": [int], "children": [<node dict>]}.

        Args:
            db_path: Path to the beets SQLite database file.
            library_root: Absolute container path of the library's `directory:`
                (from the beets config). Item paths not under this prefix are
                skipped with a warning.
        """
        self._validate_database_path(db_path)

        normalised_root = os.path.normpath(library_root).rstrip(os.sep)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()
            cursor.execute("SELECT path, album_id FROM items")

            # Root node. The tree is built in a dict-of-dicts structure keyed
            # by folder basename, then converted to the wire format at the end.
            root = {
                "name": os.path.basename(normalised_root) or "/",
                "path": "",
                "is_album": False,
                "album_ids": set(),
                "_children": {},  # name -> subtree dict
            }

            for row in cursor.fetchall():
                decoded = self._decode_artpath(row["path"])
                if not decoded:
                    continue
                album_id = row["album_id"]
                if album_id is None:
                    # Orphan items with no album — nothing to attach to the tree.
                    continue

                # Strip the library prefix; warn and skip items that fell
                # outside it (e.g. stragglers from a previous library location).
                # Item paths may be absolute (standard beets) or relative
                # (lscr.io/linuxserver/beets image default).
                normalised_item = os.path.normpath(decoded)
                if os.path.isabs(normalised_item):
                    if not normalised_item.startswith(normalised_root + os.sep):
                        logger.warning(
                            "Item path %s is outside library root %s; skipping",
                            decoded,
                            library_root,
                        )
                        continue
                    relative = normalised_item[len(normalised_root) + 1 :]
                else:
                    relative = normalised_item
                segments = relative.split(os.sep)

                # The last segment is the filename; its parent folder is the
                # album-folder, so we drop the filename and walk the folder
                # segments.
                folder_segments = segments[:-1]

                node = root
                node["album_ids"].add(album_id)
                cumulative_path = []
                for seg in folder_segments:
                    cumulative_path.append(seg)
                    child = node["_children"].get(seg)
                    if child is None:
                        child = {
                            "name": seg,
                            "path": os.sep.join(cumulative_path),
                            "is_album": False,
                            "album_ids": set(),
                            "_children": {},
                        }
                        node["_children"][seg] = child
                    child["album_ids"].add(album_id)
                    node = child

                # `node` now points at the folder that contains the file;
                # that's an album-holding folder.
                node["is_album"] = True

            connection.close()

            def _to_wire(n: dict) -> dict:
                return {
                    "name": n["name"],
                    "path": n["path"],
                    "is_album": n["is_album"],
                    "album_ids": sorted(n["album_ids"]),
                    "children": [
                        _to_wire(c) for _, c in sorted(n["_children"].items())
                    ],
                }

            return {"library_path": library_root, "root": _to_wire(root)}

        except sqlite3.DatabaseError as e:
            if "malformed" in str(e).lower():
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_items_by_ids(
        self,
        db_path: str,
        item_ids: list[int],
    ) -> list["LibraryItemData"]:
        """Query specific library items by their IDs.

        Args:
            db_path: Path to the beets SQLite database file.
            item_ids: List of item IDs to retrieve.

        Returns:
            List of LibraryItemData for found items (may be fewer than requested).

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        if not item_ids:
            return []

        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            # Build placeholders for IN clause
            placeholders = ",".join("?" * len(item_ids))

            query = f"""
                SELECT
                    i.id,
                    i.path,
                    i.title,
                    i.artist,
                    a.album,
                    a.albumartist,
                    i.track,
                    i.disc,
                    COALESCE(NULLIF(i.genres, ''), i.genre) AS genre,
                    a.year,
                    i.album_id
                FROM items i
                JOIN albums a ON i.album_id = a.id
                WHERE i.id IN ({placeholders})
                ORDER BY i.id
            """
            cursor.execute(query, item_ids)

            items = []
            for row in cursor.fetchall():
                path = self._decode_artpath(row["path"]) or ""
                directory = os.path.dirname(path) if path else ""
                filename = os.path.basename(path) if path else ""

                items.append(LibraryItemData(
                    id=row["id"],
                    path=path,
                    filename=filename,
                    directory=directory,
                    album=row["album"] or "",
                    album_artist=row["albumartist"] or "",
                    artist=row["artist"] or "",
                    title=row["title"] or "",
                    track_number=row["track"] if row["track"] else None,
                    disc_number=row["disc"] if row["disc"] else None,
                    genre=row["genre"] if row["genre"] else None,
                    year=row["year"] if row["year"] and row["year"] > 0 else None,
                    album_id=row["album_id"],
                ))

            connection.close()
            logger.debug(f"Retrieved {len(items)} items by ID from {db_path}")
            return items

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise

    def get_original_album_tags(
        self,
        db_path: str,
        item_ids: list[int],
    ) -> dict[int, str]:
        """Get the original album tag value for each item ID.

        This method captures album names before any edits are applied,
        which is needed for the beets update command.

        Args:
            db_path: Path to the beets SQLite database file.
            item_ids: List of item IDs.

        Returns:
            Dict mapping item ID to original album name.

        Raises:
            FileNotFoundError: If the database file doesn't exist.
            PermissionError: If the database file is not readable.
            sqlite3.DatabaseError: If the database is corrupted or malformed.
            sqlite3.OperationalError: If the database is locked or inaccessible.
        """
        if not item_ids:
            return {}

        self._validate_database_path(db_path)

        try:
            connection = self._connect_readonly(db_path)
            cursor = connection.cursor()

            placeholders = ",".join("?" * len(item_ids))

            query = f"""
                SELECT i.id, a.album
                FROM items i
                JOIN albums a ON i.album_id = a.id
                WHERE i.id IN ({placeholders})
            """
            cursor.execute(query, item_ids)

            result = {}
            for row in cursor.fetchall():
                result[row["id"]] = row["album"] or ""

            connection.close()
            return result

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg:
                raise sqlite3.DatabaseError(f"Database is malformed: {db_path}")
            raise

        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise sqlite3.OperationalError(f"Database is locked: {db_path}")
            if "unable to open" in error_msg:
                raise sqlite3.OperationalError(f"Unable to open database: {db_path}")
            raise


@dataclass
class LibraryItemData:
    """Container for library item data from beets database."""
    id: int
    path: str
    filename: str
    directory: str
    album: str
    album_artist: str
    artist: str
    title: str
    track_number: Optional[int]
    disc_number: Optional[int]
    genre: Optional[str]
    year: Optional[int]
    album_id: int
    format: Optional[str] = None
    bitrate: Optional[int] = None