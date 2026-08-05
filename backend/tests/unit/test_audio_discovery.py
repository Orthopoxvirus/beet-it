"""Unit tests for the shared audio discovery helpers (issue #180)."""

import os

from app.services.audio_discovery import (
    find_audio_files,
    has_audio_files,
    infer_disc_number,
)


def _touch(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")
    return path


class TestFindAudioFiles:
    def test_descends_into_disc_subfolders(self, tmp_path):
        album = str(tmp_path / "Inferno (Ungekürzt)")
        _touch(album, "CD 01", "01 - Kapitel 1.mp3")
        _touch(album, "CD 01", "02 - Kapitel 2.mp3")
        _touch(album, "CD 02", "01 - Kapitel 3.mp3")
        _touch(album, "cover.jpg")

        files = find_audio_files(album)

        assert [os.path.relpath(f, album) for f in files] == [
            os.path.join("CD 01", "01 - Kapitel 1.mp3"),
            os.path.join("CD 01", "02 - Kapitel 2.mp3"),
            os.path.join("CD 02", "01 - Kapitel 3.mp3"),
        ]

    def test_flat_folder(self, tmp_path):
        album = str(tmp_path / "Album")
        _touch(album, "01.flac")
        _touch(album, "02.flac")
        _touch(album, "notes.txt")

        files = find_audio_files(album)

        assert [os.path.basename(f) for f in files] == ["01.flac", "02.flac"]

    def test_skips_hidden_directories(self, tmp_path):
        album = str(tmp_path / "Album")
        _touch(album, "01.mp3")
        _touch(album, ".hidden", "ghost.mp3")

        assert [os.path.basename(f) for f in find_audio_files(album)] == ["01.mp3"]


class TestHasAudioFiles:
    def test_audio_only_in_disc_subfolder(self, tmp_path):
        album = str(tmp_path / "Origin")
        _touch(album, "CD 01", "01.mp3")
        _touch(album, "cover.jpg")

        assert has_audio_files(album) is True

    def test_no_audio_anywhere(self, tmp_path):
        album = str(tmp_path / "Empty")
        _touch(album, "Scans", "front.jpg")

        assert has_audio_files(album) is False


class TestInferDiscNumber:
    def test_cd_folder_with_leading_zero(self):
        assert infer_disc_number("/imp/Box/CD 01/a.mp3", "/imp/Box") == 1

    def test_disc_folder(self):
        assert infer_disc_number("/imp/Box/Disc 2/a.mp3", "/imp/Box") == 2

    def test_prefixed_disc_folder(self):
        assert infer_disc_number("/imp/Box/Die Box CD 12/a.mp3", "/imp/Box") == 12

    def test_top_level_file_has_no_disc(self):
        assert infer_disc_number("/imp/Box/a.mp3", "/imp/Box") is None

    def test_non_disc_subfolder_has_no_disc(self):
        assert infer_disc_number("/imp/Box/Bonus/a.mp3", "/imp/Box") is None
