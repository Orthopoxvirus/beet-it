"""Unit tests for the online cover-art search service (issue #147).

Covers the CAA http→https upgrade (the API returns http:// links which the
https-only measure step would otherwise silently drop) and the per-hop
redirect validation in the measure fetch.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import cover_search_service
from app.services.cover_search_service import _caa_candidates, _measure

JPEG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 32


def _response(json_data=None, content=b"", is_redirect=False, location=None):
    resp = MagicMock()
    resp.is_redirect = is_redirect
    resp.headers = {"location": location} if location else {}
    resp.content = content
    resp.raise_for_status.return_value = None
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _client(*responses):
    client = MagicMock()
    client.get = AsyncMock(side_effect=list(responses))
    return client


class TestCaaCandidates:
    def test_upgrades_http_urls_to_https(self):
        data = {
            "images": [
                {"front": True, "image": "http://coverartarchive.org/release/x/1.jpg"},
                {"front": False, "image": "http://coverartarchive.org/release/x/2.jpg"},
            ]
        }
        client = _client(_response(json_data=data))
        urls = asyncio.run(_caa_candidates(client, "some-mbid"))
        assert urls == ["https://coverartarchive.org/release/x/1.jpg"]

    def test_empty_mbid_returns_nothing(self):
        client = _client()
        assert asyncio.run(_caa_candidates(client, "")) == []
        client.get.assert_not_called()


class TestMeasureRedirects:
    def test_rejects_non_https_url(self):
        client = _client()
        result = asyncio.run(_measure(client, "http://example.com/c.jpg"))
        assert result is None
        client.get.assert_not_called()

    def test_rejects_redirect_to_plain_http(self):
        client = _client(
            _response(is_redirect=True, location="http://internal.lan/c.jpg")
        )
        with patch.object(cover_search_service, "_host_is_public", return_value=True):
            result = asyncio.run(_measure(client, "https://example.com/c.jpg"))
        assert result is None

    def test_follows_https_redirect_and_keeps_original_url(self):
        client = _client(
            _response(is_redirect=True, location="https://cdn.example.com/c.jpg"),
            _response(content=JPEG),
        )
        with patch.object(cover_search_service, "_host_is_public", return_value=True), \
                patch.object(cover_search_service, "Image", None):
            result = asyncio.run(_measure(client, "https://example.com/c.jpg"))
        assert result is not None
        assert result["url"] == "https://example.com/c.jpg"
        assert result["source"] == "example.com"

    def test_rejects_redirect_to_private_host(self):
        client = _client(
            _response(is_redirect=True, location="https://internal.lan/c.jpg")
        )

        def host_public(host):
            return host != "internal.lan"

        with patch.object(cover_search_service, "_host_is_public", side_effect=host_public):
            result = asyncio.run(_measure(client, "https://example.com/c.jpg"))
        assert result is None
