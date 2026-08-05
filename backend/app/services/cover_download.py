"""Synchronous cover-art download with SSRF protection.

Single source of truth for the cover-from-URL validators and the SSRF guard.
Two callers share this module:

* the async API endpoint ``download_album_cover_from_url`` (``app.api.libraries``)
  re-exports the validators/constants from here, and
* the synchronous import pipeline (``app.tasks.beets_tasks``) calls
  :func:`download_cover_to_album` to persist a candidate's remote cover as a
  best-effort post-import step.

Keeping the download core here (rather than in the API module) avoids pulling
the FastAPI router into the Celery worker and keeps the api -> services import
direction intact.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

import httpx

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from app.services.beets_library_service import BeetsLibraryService

logger = logging.getLogger(__name__)

# Image magic bytes for format validation.
IMAGE_MAGIC_BYTES = {
    b"\xFF\xD8\xFF": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",  # WebP starts with RIFF...WEBP
}

# Extension mapping for image formats.
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Maximum cover art file size (10 MB).
MAX_COVER_ART_SIZE = 10 * 1024 * 1024

# Download timeout for a single cover fetch.
DOWNLOAD_TIMEOUT_SECONDS = 10.0

# Redirect hops we are willing to follow (each hop is re-validated).
MAX_REDIRECT_HOPS = 5

# Discogs and some CDNs reject requests without a User-Agent.
_USER_AGENT = "beet-it/1.0 (+https://github.com/Orthopoxvirus/beet-it)"

# Blocked IP ranges for SSRF protection.
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
]


class CoverDownloadError(Exception):
    """Raised when a cover URL is rejected or cannot be downloaded safely.

    ``status_code`` is a hint for API callers mapping the error onto an HTTP
    response (400 bad request, 413 too large, 504 timeout).
    """

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def validate_image_format(data: bytes) -> Optional[str]:
    """Validate image format by checking magic bytes.

    Args:
        data: The image data bytes.

    Returns:
        MIME type string if valid, None if unrecognized format.
    """
    for magic, mime_type in IMAGE_MAGIC_BYTES.items():
        if data.startswith(magic):
            # Special check for WebP: RIFF....WEBP
            if magic == b"RIFF" and len(data) >= 12:
                if data[8:12] != b"WEBP":
                    continue
            return mime_type
    return None


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a blocked private range.

    Args:
        ip_str: IP address as string.

    Returns:
        True if the string is a valid IP in a blocked range.
        False for public IPs, or for non-IP strings (e.g. DNS hostnames)
        which should be resolved via DNS before a block decision is made.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for network in BLOCKED_IP_RANGES:
        if ip in network:
            return True
    return False


def assert_url_is_safe(url: str) -> None:
    """Validate the URL scheme and guard against SSRF.

    Only http/https are allowed, and the hostname must not resolve to a
    private/loopback/link-local address. Raises :class:`CoverDownloadError`
    when the URL is unsafe. :func:`fetch_cover_bytes` re-applies this check
    to every redirect hop, so a public host redirecting to a private one is
    blocked too.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise CoverDownloadError("Invalid URL")

    if parsed.scheme not in ("http", "https"):
        raise CoverDownloadError("Only HTTP/HTTPS URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise CoverDownloadError("Invalid URL: missing hostname")

    # Block IP-literal hosts directly.
    if is_private_ip(hostname):
        raise CoverDownloadError("URL points to a blocked address")

    # Resolve DNS and block if any resolved address is private.
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise CoverDownloadError("Cannot resolve URL hostname")
    for result in results:
        ip = result[4][0]
        if is_private_ip(ip):
            raise CoverDownloadError("URL points to a blocked address")


def fetch_cover_bytes(url: str) -> tuple[bytes, str]:
    """Download and validate an image from ``url`` (synchronous).

    Redirects are followed manually so every hop passes the SSRF guard (a
    public host 302'ing to an internal address is blocked). The body is
    streamed and aborted as soon as it exceeds :data:`MAX_COVER_ART_SIZE`,
    so a huge or malicious response can't balloon worker memory.

    Returns:
        A ``(content, mime_type)`` tuple.

    Raises:
        CoverDownloadError: on an unsafe URL, network error, oversized
            response, or unrecognised image format.
    """
    assert_url_is_safe(url)

    try:
        with httpx.Client(
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            for _ in range(MAX_REDIRECT_HOPS + 1):
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise CoverDownloadError(
                                "Failed to download image: redirect without location"
                            )
                        url = str(httpx.URL(url).join(location))
                        assert_url_is_safe(url)
                        continue
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    received = 0
                    for chunk in response.iter_bytes():
                        received += len(chunk)
                        if received > MAX_COVER_ART_SIZE:
                            raise CoverDownloadError(
                                "Downloaded file too large (max 10 MB)",
                                status_code=413,
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    break
            else:
                raise CoverDownloadError("Failed to download image: too many redirects")
    except httpx.TimeoutException:
        raise CoverDownloadError(
            "Failed to download image: request timed out", status_code=504
        )
    except httpx.HTTPStatusError as e:
        raise CoverDownloadError(
            f"Failed to download image: HTTP {e.response.status_code}"
        )
    except httpx.HTTPError as e:
        raise CoverDownloadError(f"Failed to download image: {e}")

    mime_type = validate_image_format(content)
    if not mime_type:
        raise CoverDownloadError(
            "URL did not return a valid image (JPEG, PNG, GIF, WebP)"
        )

    return content, mime_type


# Filename stems + extensions the folder-discovery fallback recognises as
# covers. Mirrors ``BeetsLibraryService.COVER_ART_FILENAMES`` /
# ``COVER_ART_EXTENSIONS`` — keep in sync.
RECOGNISED_COVER_STEMS = ("cover", "albumart", "folder", "front")
RECOGNISED_COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def write_cover_file(
    album_folder: str, content: bytes, mime_type: str, stem: str = "cover"
) -> str:
    """Atomically write ``content`` as ``<stem><ext>`` into *album_folder*.

    Writes to a temp file and ``os.replace``s it into place so a concurrent
    reader never sees a torn/partial image. Afterwards removes every *other*
    recognised cover variant (``cover``/``albumart``/``folder``/``front`` ×
    image extensions, case-insensitive) so a replace leaves exactly one cover
    file — a stale ``albumart.jpg`` next to a new ``cover.png`` would
    otherwise linger, get picked up by folder discovery, and show up as a
    stray file under maintenance.

    Returns the final cover path. Raises OSError on write failure.
    """
    ext = IMAGE_EXTENSIONS.get(mime_type, ".jpg")
    cover_path = os.path.join(album_folder, f"{stem}{ext}")
    tmp_path = cover_path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
        os.replace(tmp_path, cover_path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    recognised = set(RECOGNISED_COVER_STEMS) | {stem.lower()}
    try:
        names = os.listdir(album_folder)
    except OSError:
        names = []
    for name in names:
        base, name_ext = os.path.splitext(name)
        if base.lower() not in recognised or name_ext.lower() not in RECOGNISED_COVER_EXTS:
            continue
        stale = os.path.join(album_folder, name)
        if os.path.abspath(stale) == os.path.abspath(cover_path):
            continue
        try:
            os.unlink(stale)
            logger.info(f"Removed stale cover variant {stale}")
        except OSError as e:
            logger.warning(f"Could not remove stale cover variant {stale}: {e}")

    return cover_path


def download_cover_to_album(
    url: str,
    *,
    database_path: str,
    album_id: int,
    library_path: Optional[str] = None,
    beets_service: Optional["BeetsLibraryService"] = None,
    art_filename: str = "cover",
) -> Optional[str]:
    """Download ``url`` and persist it as album ``album_id``'s cover art.

    Writes ``<art_filename><ext>`` into the album folder and points the beets
    ``artpath`` at it. This is **best-effort**: any failure (rejected URL,
    download error, missing folder, write error) is logged and returns
    ``None`` so callers in the import pipeline never fail an import over cover
    art.

    Args:
        url: The remote image URL (validated for SSRF before download).
        database_path: Path to the beets SQLite database.
        album_id: The beets album id to attach the cover to.
        library_path: Library root, used to resolve a relative album folder.
        beets_service: Optional pre-built service (for tests / reuse).

    Returns:
        The saved cover path on success, otherwise ``None``.
    """
    from app.services.beets_library_service import BeetsLibraryService

    service = beets_service or BeetsLibraryService()

    try:
        content, mime_type = fetch_cover_bytes(url)
    except CoverDownloadError as e:
        logger.warning(f"Candidate cover rejected for album {album_id}: {e}")
        return None

    album_folder = service.get_album_folder_path(database_path, album_id)
    if not album_folder:
        logger.warning(
            f"Cannot determine album folder for album {album_id}; "
            "skipping candidate cover"
        )
        return None

    # Resolve relative item paths against the library root.
    if not os.path.isabs(album_folder) and library_path:
        album_folder = os.path.normpath(os.path.join(library_path, album_folder))

    if not os.path.isdir(album_folder):
        logger.warning(
            f"Album {album_id} folder not on disk ({album_folder}); "
            "skipping candidate cover"
        )
        return None

    try:
        cover_path = write_cover_file(album_folder, content, mime_type, stem=art_filename)
    except OSError as e:
        logger.warning(f"Failed to write candidate cover for album {album_id}: {e}")
        return None

    service.update_album_artpath(database_path, album_id, cover_path)
    logger.info(f"Persisted candidate cover for album {album_id} at {cover_path}")
    return cover_path
