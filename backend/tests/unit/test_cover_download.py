"""Unit tests for the synchronous cover-download service (SSRF guard,
format validation, download, and persistence)."""
import os
import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services import cover_download
from app.services.cover_download import (
    CoverDownloadError,
    assert_url_is_safe,
    download_cover_to_album,
    fetch_cover_bytes,
    validate_image_format,
    write_cover_file,
)

JPEG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _public_addrinfo(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def _private_addrinfo(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]


def _stream_response(content=JPEG, raise_status=None, redirect_to=None):
    """Context-manager mock for one client.stream(...) call."""
    response = MagicMock()
    response.is_redirect = redirect_to is not None
    response.headers = {"location": redirect_to} if redirect_to else {}
    response.iter_bytes.return_value = [content] if content else []
    if raise_status is not None:
        response.raise_for_status.side_effect = raise_status
    else:
        response.raise_for_status.return_value = None

    cm = MagicMock()
    cm.__enter__.return_value = response
    cm.__exit__.return_value = False
    return cm


def _mock_client(*responses):
    """Build a context-manager mock standing in for httpx.Client(...);
    each element of *responses* answers one client.stream(...) call."""
    client = MagicMock()
    client.stream.side_effect = list(responses)

    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    return cm


class TestValidateImageFormat:
    def test_jpeg(self):
        assert validate_image_format(JPEG) == "image/jpeg"

    def test_png(self):
        assert validate_image_format(PNG) == "image/png"

    def test_webp_requires_marker(self):
        assert validate_image_format(b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8) == "image/webp"
        # RIFF container that is not WebP (e.g. AVI) must be rejected.
        assert validate_image_format(b"RIFF" + b"\x00" * 4 + b"AVI " + b"\x00" * 8) is None

    def test_unknown(self):
        assert validate_image_format(b"this is not an image") is None


class TestAssertUrlIsSafe:
    def test_rejects_non_http_scheme(self):
        with pytest.raises(CoverDownloadError):
            assert_url_is_safe("ftp://example.com/cover.jpg")

    def test_rejects_missing_hostname(self):
        with pytest.raises(CoverDownloadError):
            assert_url_is_safe("http:///cover.jpg")

    def test_rejects_private_ip_literal(self):
        with pytest.raises(CoverDownloadError):
            assert_url_is_safe("http://10.0.0.5/cover.jpg")

    def test_rejects_hostname_resolving_to_private(self):
        with patch.object(cover_download.socket, "getaddrinfo", _private_addrinfo):
            with pytest.raises(CoverDownloadError):
                assert_url_is_safe("http://evil.example.com/cover.jpg")

    def test_rejects_unresolvable_hostname(self):
        with patch.object(cover_download.socket, "getaddrinfo", side_effect=socket.gaierror):
            with pytest.raises(CoverDownloadError):
                assert_url_is_safe("http://nope.example.com/cover.jpg")

    def test_allows_public_hostname(self):
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo):
            assert_url_is_safe("https://example.com/cover.jpg")  # no raise


class TestFetchCoverBytes:
    def test_happy_path(self):
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(_stream_response(JPEG))):
            content, mime = fetch_cover_bytes("https://example.com/c.jpg")
        assert content == JPEG
        assert mime == "image/jpeg"

    def test_oversized_rejected(self):
        big = b"\xFF\xD8\xFF" + b"\x00" * (cover_download.MAX_COVER_ART_SIZE + 1)
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(_stream_response(big))):
            with pytest.raises(CoverDownloadError) as exc_info:
                fetch_cover_bytes("https://example.com/c.jpg")
        assert exc_info.value.status_code == 413

    def test_non_image_rejected(self):
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(_stream_response(b"<html>"))):
            with pytest.raises(CoverDownloadError):
                fetch_cover_bytes("https://example.com/c.jpg")

    def test_http_error_rejected(self):
        err = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock(status_code=404)
        )
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(_stream_response(raise_status=err))):
            with pytest.raises(CoverDownloadError):
                fetch_cover_bytes("https://example.com/c.jpg")

    def test_timeout_maps_to_504(self):
        client = MagicMock()
        client.stream.side_effect = httpx.ConnectTimeout("slow")
        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client", return_value=cm):
            with pytest.raises(CoverDownloadError) as exc_info:
                fetch_cover_bytes("https://example.com/c.jpg")
        assert exc_info.value.status_code == 504

    def test_ssrf_blocks_before_any_request(self):
        # A private IP literal must be rejected before httpx is ever touched.
        with patch.object(cover_download.httpx, "Client") as mock_client:
            with pytest.raises(CoverDownloadError):
                fetch_cover_bytes("http://192.168.1.10/c.jpg")
        mock_client.assert_not_called()

    def test_redirect_to_private_blocked(self):
        # Public host answers with a redirect to a private address — the hop
        # must be validated and rejected.
        redirect = _stream_response(content=None, redirect_to="http://192.168.1.10/c.jpg")
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(redirect)):
            with pytest.raises(CoverDownloadError):
                fetch_cover_bytes("https://example.com/c.jpg")

    def test_redirect_to_public_followed(self):
        redirect = _stream_response(content=None, redirect_to="https://cdn.example.com/c.jpg")
        final = _stream_response(JPEG)
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(redirect, final)):
            content, mime = fetch_cover_bytes("https://example.com/c.jpg")
        assert content == JPEG
        assert mime == "image/jpeg"

    def test_too_many_redirects_rejected(self):
        hops = [
            _stream_response(content=None, redirect_to=f"https://example.com/{i}.jpg")
            for i in range(cover_download.MAX_REDIRECT_HOPS + 1)
        ]
        with patch.object(cover_download.socket, "getaddrinfo", _public_addrinfo), \
                patch.object(cover_download.httpx, "Client",
                             return_value=_mock_client(*hops)):
            with pytest.raises(CoverDownloadError):
                fetch_cover_bytes("https://example.com/c.jpg")


class TestWriteCoverFile:
    def test_writes_atomically(self, tmp_path):
        result = write_cover_file(str(tmp_path), JPEG, "image/jpeg")
        assert result == str(tmp_path / "cover.jpg")
        assert (tmp_path / "cover.jpg").read_bytes() == JPEG
        assert not (tmp_path / "cover.jpg.tmp").exists()

    def test_removes_stale_variants_on_format_change(self, tmp_path):
        (tmp_path / "cover.jpg").write_bytes(JPEG)
        (tmp_path / "cover.jpeg").write_bytes(JPEG)
        result = write_cover_file(str(tmp_path), PNG, "image/png")
        assert result == str(tmp_path / "cover.png")
        assert (tmp_path / "cover.png").read_bytes() == PNG
        assert not (tmp_path / "cover.jpg").exists()
        assert not (tmp_path / "cover.jpeg").exists()

    def test_removes_other_recognised_cover_stems(self, tmp_path):
        # A replace must leave exactly one cover file — albumart/folder/front
        # variants (any case) go too, or discovery/maintenance resurface them.
        (tmp_path / "albumart.jpg").write_bytes(JPEG)
        (tmp_path / "Folder.PNG").write_bytes(PNG)
        (tmp_path / "front.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
        result = write_cover_file(str(tmp_path), PNG, "image/png")
        assert result == str(tmp_path / "cover.png")
        assert not (tmp_path / "albumart.jpg").exists()
        assert not (tmp_path / "Folder.PNG").exists()
        assert not (tmp_path / "front.webp").exists()

    def test_custom_stem_from_art_filename(self, tmp_path):
        (tmp_path / "cover.png").write_bytes(PNG)
        result = write_cover_file(str(tmp_path), JPEG, "image/jpeg", stem="albumart")
        assert result == str(tmp_path / "albumart.jpg")
        assert (tmp_path / "albumart.jpg").read_bytes() == JPEG
        assert not (tmp_path / "cover.png").exists()

    def test_leaves_unrelated_files_alone(self, tmp_path):
        (tmp_path / "back.jpg").write_bytes(JPEG)
        (tmp_path / "01 track.flac").write_bytes(b"audio")
        write_cover_file(str(tmp_path), PNG, "image/png")
        assert (tmp_path / "back.jpg").exists()
        assert (tmp_path / "01 track.flac").exists()


class TestDownloadCoverToAlbum:
    def test_writes_cover_and_sets_artpath(self, tmp_path):
        album_dir = tmp_path / "Artist - Album"
        album_dir.mkdir()
        service = MagicMock()
        service.get_album_folder_path.return_value = str(album_dir)

        with patch.object(cover_download, "fetch_cover_bytes", return_value=(JPEG, "image/jpeg")):
            result = download_cover_to_album(
                "https://example.com/c.jpg",
                database_path="/db.blb",
                album_id=7,
                beets_service=service,
            )

        expected = str(album_dir / "cover.jpg")
        assert result == expected
        assert (album_dir / "cover.jpg").read_bytes() == JPEG
        service.update_album_artpath.assert_called_once_with("/db.blb", 7, expected)

    def test_relative_folder_resolved_against_library_path(self, tmp_path):
        lib = tmp_path / "library"
        rel = os.path.join("Artist", "Album")
        (lib / rel).mkdir(parents=True)
        service = MagicMock()
        service.get_album_folder_path.return_value = rel

        with patch.object(cover_download, "fetch_cover_bytes", return_value=(PNG, "image/png")):
            result = download_cover_to_album(
                "https://example.com/c.png",
                database_path="/db.blb",
                album_id=3,
                library_path=str(lib),
                beets_service=service,
            )

        assert result == os.path.join(str(lib), rel, "cover.png")
        assert os.path.exists(result)

    def test_rejected_url_returns_none_without_writing(self):
        service = MagicMock()
        with patch.object(cover_download, "fetch_cover_bytes", side_effect=CoverDownloadError("blocked")):
            result = download_cover_to_album(
                "http://10.0.0.1/c.jpg",
                database_path="/db.blb",
                album_id=7,
                beets_service=service,
            )
        assert result is None
        service.update_album_artpath.assert_not_called()

    def test_missing_album_folder_returns_none(self):
        service = MagicMock()
        service.get_album_folder_path.return_value = None
        with patch.object(cover_download, "fetch_cover_bytes", return_value=(JPEG, "image/jpeg")):
            result = download_cover_to_album(
                "https://example.com/c.jpg",
                database_path="/db.blb",
                album_id=7,
                beets_service=service,
            )
        assert result is None
        service.update_album_artpath.assert_not_called()
