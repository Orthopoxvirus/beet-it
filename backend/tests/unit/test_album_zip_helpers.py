"""Unit tests for the album-download zip helpers in app.api.libraries."""

import io
import os
import tempfile
import zipfile

from app.api.libraries import (
    iter_album_zip,
    resolve_track_path,
    sanitize_filename_component,
)


class TestSanitizeFilenameComponent:
    def test_strips_path_separators(self):
        assert "/" not in sanitize_filename_component("AC/DC", "fallback")
        assert "\\" not in sanitize_filename_component("a\\b", "fallback")

    def test_drops_null_and_control_bytes(self):
        result = sanitize_filename_component("ti\x00tle\x07", "fallback")
        assert "\x00" not in result and "\x07" not in result

    def test_keeps_unicode(self):
        # Umlauts must survive — they're valid in zip entries and filename*.
        assert sanitize_filename_component("Grüße", "fallback") == "Grüße"

    def test_falls_back_when_empty(self):
        assert sanitize_filename_component("", "fallback") == "fallback"
        assert sanitize_filename_component("   ", "fallback") == "fallback"
        # Separators become underscores rather than vanishing entirely.
        assert sanitize_filename_component("///", "fallback") == "___"

    def test_trims_trailing_dots_and_spaces(self):
        assert sanitize_filename_component("name.  ", "fallback") == "name"


class TestResolveTrackPath:
    def test_absolute_path_unchanged(self):
        assert resolve_track_path("/music/a.flac", "/library") == "/music/a.flac"

    def test_relative_path_joined_to_library(self):
        assert resolve_track_path("Artist/a.flac", "/library/") == "/library/Artist/a.flac"

    def test_relative_path_without_library_unchanged(self):
        assert resolve_track_path("Artist/a.flac", None) == "Artist/a.flac"

    def test_empty_path_unchanged(self):
        assert resolve_track_path("", "/library") == ""


class TestIterAlbumZip:
    def _build(self, files):
        return b"".join(iter_album_zip(files))

    def test_produces_valid_zip_with_all_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i in range(3):
                p = os.path.join(tmp, f"track{i}.flac")
                with open(p, "wb") as f:
                    f.write(b"fLaC" + bytes([i]) * 5000)
                paths.append(p)
            files = [(p, f"{i + 1:02d} - Track.flac") for i, p in enumerate(paths)]

            data = self._build(files)
            zf = zipfile.ZipFile(io.BytesIO(data))

            assert zf.testzip() is None  # CRCs all valid
            assert zf.namelist() == ["01 - Track.flac", "02 - Track.flac", "03 - Track.flac"]
            # Round-trips the exact bytes.
            for i, p in enumerate(paths):
                with open(p, "rb") as f:
                    assert zf.read(zf.namelist()[i]) == f.read()

    def test_stored_not_deflated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.flac")
            with open(p, "wb") as f:
                f.write(b"\x00" * 10000)
            data = self._build([(p, "a.flac")])
            zf = zipfile.ZipFile(io.BytesIO(data))
            assert zf.getinfo("a.flac").compress_type == zipfile.ZIP_STORED

    def test_skips_missing_files_without_aborting(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.flac")
            with open(good, "wb") as f:
                f.write(b"data" * 100)
            files = [
                (os.path.join(tmp, "gone.flac"), "01 - Gone.flac"),
                (good, "02 - Good.flac"),
            ]
            data = self._build(files)
            zf = zipfile.ZipFile(io.BytesIO(data))
            assert zf.namelist() == ["02 - Good.flac"]
            assert zf.testzip() is None

    def test_empty_file_list_is_valid_empty_zip(self):
        data = self._build([])
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert zf.namelist() == []
