"""Online album-art search across keyless public sources (issue #147).

Aggregates cover-art candidates from iTunes, Deezer and the Cover Art Archive
(the latter only when the album has a MusicBrainz release id), measures each
candidate's real pixel size, and returns them largest-first. Used by the
"Search online" tab of the cover-art dialog; the chosen URL is then applied
through the existing SSRF-guarded ``/cover/url`` endpoint.
"""
import asyncio
import io
import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow is a backend dependency
    Image = None  # type: ignore

logger = logging.getLogger(__name__)

# Cap candidates we measure so a search can't fan out into dozens of downloads.
MAX_CANDIDATES = 12
# Per-source result cap before measuring.
PER_SOURCE_LIMIT = 6
_MEASURE_MAX_BYTES = 12 * 1024 * 1024
_TIMEOUT = httpx.Timeout(8.0)
_HEADERS = {"User-Agent": "beet-it/maintenance (+https://github.com/Orthopoxvirus/beet-it)"}


def _source_domain(url: str) -> str:
    try:
        return urlparse(url).hostname or "unknown"
    except ValueError:
        return "unknown"


def _host_is_public(host: str) -> bool:
    """Resolve a hostname and confirm every address is a routable public IP.

    Mirrors the SSRF guard the /cover/url endpoint applies, so the server-side
    measure-fetch can't be pointed at internal/loopback/link-local hosts.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True


async def _itunes_candidates(
    client: httpx.AsyncClient, artist: str, album: str, limit: int
) -> list[str]:
    term = f"{artist} {album}".strip()
    if not term:
        return []
    try:
        resp = await client.get(
            "https://itunes.apple.com/search",
            params={"term": term, "entity": "album", "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("iTunes cover search failed: %s", e)
        return []
    urls: list[str] = []
    for item in data.get("results", []):
        art = item.get("artworkUrl100")
        if art:
            # iTunes serves a larger render when the size token is swapped.
            urls.append(art.replace("100x100bb", "1200x1200bb"))
    return urls


async def _deezer_candidates(
    client: httpx.AsyncClient, artist: str, album: str, limit: int
) -> list[str]:
    term = f"{artist} {album}".strip()
    if not term:
        return []
    try:
        resp = await client.get(
            "https://api.deezer.com/search/album",
            params={"q": term, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Deezer cover search failed: %s", e)
        return []
    urls: list[str] = []
    for item in data.get("data", []):
        art = item.get("cover_xl") or item.get("cover_big")
        if art:
            urls.append(art)
    return urls


async def _caa_candidates(client: httpx.AsyncClient, mb_albumid: str) -> list[str]:
    if not mb_albumid:
        return []
    # mb_albumid comes from the local beets DB; encode it so it can't reshape
    # the request path.
    safe_id = quote(mb_albumid, safe="")
    try:
        resp = await client.get(f"https://coverartarchive.org/release/{safe_id}")
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.info("Cover Art Archive lookup failed for %s: %s", mb_albumid, e)
        return []
    urls: list[str] = []
    for image in data.get("images", []):
        if image.get("front") and image.get("image"):
            url = image["image"]
            # CAA returns http:// links in its JSON; the measure step only
            # accepts https, so upgrade (both CAA and archive.org serve TLS).
            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]
            urls.append(url)
    return urls


async def _measure(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """Download a candidate and return its size + dimensions, or None on failure."""
    # Only ever fetch https candidates (the public sources always return https)
    # and only when the host resolves to a public IP — defense in depth against
    # a poisoned listing pointing the fetch at an internal address.
    if not url.lower().startswith("https://"):
        return None
    original_url = url
    try:
        # Follow redirects manually so every hop is re-checked — CAA image
        # URLs redirect to archive.org, and a hop must never reach an
        # internal host or drop to plain http.
        for _ in range(5):
            host = _source_domain(url)
            if host == "unknown" or not await asyncio.to_thread(_host_is_public, host):
                return None
            resp = await client.get(url, follow_redirects=False)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    return None
                url = str(httpx.URL(url).join(location))
                if not url.lower().startswith("https://"):
                    return None
                continue
            resp.raise_for_status()
            content = resp.content
            break
        else:
            return None
    except httpx.HTTPError as e:
        logger.debug("Could not fetch candidate %s: %s", original_url, e)
        return None
    if not content or len(content) > _MEASURE_MAX_BYTES:
        return None
    width: Optional[int] = None
    height: Optional[int] = None
    if Image is not None:
        try:
            with Image.open(io.BytesIO(content)) as img:
                width, height = img.size
        except Exception as e:  # noqa: BLE001 - any decode error → drop candidate
            logger.debug("Could not measure candidate %s: %s", original_url, e)
            return None
    return {
        "url": original_url,
        "source": _source_domain(original_url),
        "width": width,
        "height": height,
    }


async def search_cover_art(
    artist: str,
    album: str,
    mb_albumid: Optional[str] = None,
) -> list[dict]:
    """Return cover-art candidates (largest first) from the public sources."""
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
    ) as client:
        gathered = await asyncio.gather(
            _itunes_candidates(client, artist, album, PER_SOURCE_LIMIT),
            _deezer_candidates(client, artist, album, PER_SOURCE_LIMIT),
            _caa_candidates(client, mb_albumid or ""),
            return_exceptions=True,
        )

        urls: list[str] = []
        seen: set[str] = set()
        for group in gathered:
            if isinstance(group, BaseException):
                logger.warning("A cover source failed: %s", group)
                continue
            for url in group:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        urls = urls[:MAX_CANDIDATES]

        measured = await asyncio.gather(*(_measure(client, url) for url in urls))

    results = [m for m in measured if m]
    # Largest resolution first; unmeasured (None dims) sink to the bottom.
    results.sort(key=lambda r: (r["width"] or 0) * (r["height"] or 0), reverse=True)
    return results
