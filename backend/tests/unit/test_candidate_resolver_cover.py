"""The manual-candidate resolvers surface a remote cover URL so the import
pipeline can persist it. Covers the Discogs REST image extraction in detail
and the Deezer/Spotify ``cover_art_url`` pass-through."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import candidate_resolvers
from app.services.beets_autotag_service import LocalAlbumData


def _local_album():
    return LocalAlbumData(path="/imports/x", artist="Artist", album="Album", tracks=[])


def _discogs_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


class TestDiscogsCover:
    def test_prefers_primary_image(self):
        payload = {
            "id": 123,
            "title": "Album",
            "artists": [{"name": "Artist"}],
            "tracklist": [{"type_": "track", "title": "T1", "duration": "3:00"}],
            "images": [
                {"type": "secondary", "uri": "https://img/secondary.jpg"},
                {"type": "primary", "uri": "https://img/primary.jpg"},
            ],
        }
        with patch("httpx.get", return_value=_discogs_response(payload)):
            candidate = candidate_resolvers.resolve_discogs_candidate("123", _local_album())
        assert candidate.cover_url == "https://img/primary.jpg"

    def test_falls_back_to_first_image(self):
        payload = {
            "id": 123,
            "title": "Album",
            "artists": [{"name": "Artist"}],
            "tracklist": [{"type_": "track", "title": "T1", "duration": "3:00"}],
            "images": [
                {"type": "secondary", "resource_url": "https://img/only.jpg"},
            ],
        }
        with patch("httpx.get", return_value=_discogs_response(payload)):
            candidate = candidate_resolvers.resolve_discogs_candidate("123", _local_album())
        assert candidate.cover_url == "https://img/only.jpg"

    def test_no_images_yields_none(self):
        payload = {
            "id": 123,
            "title": "Album",
            "artists": [{"name": "Artist"}],
            "tracklist": [{"type_": "track", "title": "T1", "duration": "3:00"}],
        }
        with patch("httpx.get", return_value=_discogs_response(payload)):
            candidate = candidate_resolvers.resolve_discogs_candidate("123", _local_album())
        assert candidate.cover_url is None


class TestDeezerCover:
    def test_passes_through_cover_art_url(self):
        info = SimpleNamespace(
            album_id=42,
            artist="Artist",
            album="Album",
            year=2020,
            label="Label",
            country="US",
            media="Digital Media",
            tracks=[SimpleNamespace(title="T1", length=180.0, index=1)],
            cover_art_url="https://e-cdns-images.dzcdn.net/cover_xl.jpg",
        )
        plugin = MagicMock()
        plugin.album_for_id.return_value = info
        with patch("beetsplug.deezer.DeezerPlugin", return_value=plugin):
            candidate = candidate_resolvers.resolve_deezer_candidate("42", _local_album())
        assert candidate.cover_url == "https://e-cdns-images.dzcdn.net/cover_xl.jpg"

    def test_missing_cover_art_url_yields_none(self):
        info = SimpleNamespace(
            album_id=42,
            artist="Artist",
            album="Album",
            year=2020,
            label=None,
            country=None,
            media=None,
            tracks=[SimpleNamespace(title="T1", length=180.0, index=1)],
        )  # no cover_art_url attribute
        plugin = MagicMock()
        plugin.album_for_id.return_value = info
        with patch("beetsplug.deezer.DeezerPlugin", return_value=plugin):
            candidate = candidate_resolvers.resolve_deezer_candidate("42", _local_album())
        assert candidate.cover_url is None
