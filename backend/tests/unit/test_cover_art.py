"""Unit tests for app.services.cover_art — cover materialisation helpers."""

import os

import pytest

from app.services import cover_art
from app.services.cover_art import (
    detect_image_ext,
    ensure_album_cover,
    find_normalizable_cover,
    recognised_cover_in,
)

# A 1x1 transparent PNG (valid magic bytes + minimal body).
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
GIF_BYTES = b"GIF89a" + b"\x00" * 16
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16


def _write(path: str, data: bytes = JPG_BYTES) -> str:
    with open(path, "wb") as fh:
        fh.write(data)
    return path


class TestDetectImageExt:
    def test_jpg(self):
        assert detect_image_ext(JPG_BYTES) == ".jpg"

    def test_png(self):
        assert detect_image_ext(PNG_BYTES) == ".png"

    def test_gif(self):
        assert detect_image_ext(GIF_BYTES) == ".gif"

    def test_webp(self):
        assert detect_image_ext(WEBP_BYTES) == ".webp"

    def test_unknown_and_empty(self):
        assert detect_image_ext(b"not an image") is None
        assert detect_image_ext(b"") is None


class TestRecognisedCover:
    def test_finds_cover(self, tmp_path):
        _write(str(tmp_path / "cover.jpg"))
        assert recognised_cover_in(str(tmp_path)) == str(tmp_path / "cover.jpg")

    def test_case_insensitive(self, tmp_path):
        _write(str(tmp_path / "Folder.PNG"), PNG_BYTES)
        assert recognised_cover_in(str(tmp_path)) == str(tmp_path / "Folder.PNG")

    def test_none_when_only_stray(self, tmp_path):
        _write(str(tmp_path / "00-scene.jpg"))
        assert recognised_cover_in(str(tmp_path)) is None


class TestFindNormalizableCover:
    def test_scene_art(self, tmp_path):
        _write(str(tmp_path / "00-holy_klassiker-folge_1.jpg"))
        assert find_normalizable_cover(str(tmp_path)) == str(
            tmp_path / "00-holy_klassiker-folge_1.jpg"
        )

    def test_single_stray_image(self, tmp_path):
        _write(str(tmp_path / "scan001.png"), PNG_BYTES)
        assert find_normalizable_cover(str(tmp_path)) == str(tmp_path / "scan001.png")

    def test_ambiguous_multiple_non_scene_returns_none(self, tmp_path):
        _write(str(tmp_path / "a.jpg"))
        _write(str(tmp_path / "b.jpg"))
        assert find_normalizable_cover(str(tmp_path)) is None

    def test_scene_wins_over_other_strays(self, tmp_path):
        _write(str(tmp_path / "00-release.jpg"))
        _write(str(tmp_path / "booklet.jpg"))
        assert find_normalizable_cover(str(tmp_path)) == str(tmp_path / "00-release.jpg")

    def test_recognised_name_excluded(self, tmp_path):
        # A folder whose only image is already a recognised cover has nothing
        # to normalise.
        _write(str(tmp_path / "cover.jpg"))
        assert find_normalizable_cover(str(tmp_path)) is None

    def test_empty_folder(self, tmp_path):
        assert find_normalizable_cover(str(tmp_path)) is None


class TestEnsureAlbumCover:
    def test_existing_recognised_cover_returned_untouched(self, tmp_path):
        cover = _write(str(tmp_path / "cover.jpg"))
        before = sorted(os.listdir(tmp_path))
        result = ensure_album_cover(str(tmp_path), "albumart")
        assert result == cover
        # No new file created.
        assert sorted(os.listdir(tmp_path)) == before

    def test_never_overwrites_existing_recognised_cover(self, tmp_path):
        # Even with a tempting scene file present, an existing recognised cover
        # short-circuits and is left alone.
        _write(str(tmp_path / "front.jpg"), JPG_BYTES)
        _write(str(tmp_path / "00-release.jpg"), PNG_BYTES)
        result = ensure_album_cover(str(tmp_path), "albumart")
        assert result == str(tmp_path / "front.jpg")
        assert not os.path.exists(tmp_path / "albumart.jpg")

    def test_promotes_scene_art_to_art_filename(self, tmp_path):
        src = _write(str(tmp_path / "00-release-name.jpg"))
        result = ensure_album_cover(str(tmp_path), "albumart")
        assert result == str(tmp_path / "albumart.jpg")
        assert os.path.exists(result)
        # Original is copied, not moved.
        assert os.path.exists(src)

    def test_promotes_single_stray_preserving_extension(self, tmp_path):
        _write(str(tmp_path / "scan.png"), PNG_BYTES)
        result = ensure_album_cover(str(tmp_path), "albumart")
        assert result == str(tmp_path / "albumart.png")
        assert os.path.exists(result)

    def test_ambiguous_no_embedded_returns_none(self, tmp_path):
        _write(str(tmp_path / "a.jpg"))
        _write(str(tmp_path / "b.jpg"))
        result = ensure_album_cover(str(tmp_path), "albumart")
        assert result is None
        assert not os.path.exists(tmp_path / "albumart.jpg")

    def test_source_folder_fallback(self, tmp_path):
        # Album folder has only audio; the cover sits in the (import) source.
        album = tmp_path / "dest"
        source = tmp_path / "src"
        album.mkdir()
        source.mkdir()
        open(album / "01 - track.flac", "wb").close()
        _write(str(source / "00-release.jpg"))
        result = ensure_album_cover(str(album), "albumart", source_folder=str(source))
        assert result == str(album / "albumart.jpg")
        assert os.path.exists(result)

    def test_embedded_extraction(self, tmp_path, monkeypatch):
        # No image anywhere → fall back to embedded art from the first track.
        audio = str(tmp_path / "01 - track.flac")
        open(audio, "wb").close()
        monkeypatch.setattr(cover_art, "read_embedded_art", lambda p: PNG_BYTES)
        result = ensure_album_cover(str(tmp_path), "myart", audio_files=[audio])
        assert result == str(tmp_path / "myart.png")
        with open(result, "rb") as fh:
            assert fh.read() == PNG_BYTES

    def test_embedded_extraction_none_when_no_art(self, tmp_path, monkeypatch):
        audio = str(tmp_path / "01 - track.flac")
        open(audio, "wb").close()
        monkeypatch.setattr(cover_art, "read_embedded_art", lambda p: None)
        assert ensure_album_cover(str(tmp_path), "albumart", audio_files=[audio]) is None

    def test_image_preferred_over_embedded(self, tmp_path, monkeypatch):
        # A folder image is used even if tracks also carry embedded art —
        # extraction must not run (would be wasteful and could clobber).
        _write(str(tmp_path / "00-release.jpg"))
        audio = str(tmp_path / "01 - track.flac")
        open(audio, "wb").close()

        def _boom(_):
            raise AssertionError("embedded extraction should not run")

        monkeypatch.setattr(cover_art, "read_embedded_art", _boom)
        result = ensure_album_cover(str(tmp_path), "albumart", audio_files=[audio])
        assert result == str(tmp_path / "albumart.jpg")

    def test_nonexistent_folder(self):
        assert ensure_album_cover("/no/such/folder", "albumart") is None
