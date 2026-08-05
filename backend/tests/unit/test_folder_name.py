"""Unit tests for folder-name / filename metadata fallback parsing (issue #138)."""

import pytest

from app.services.scanner.folder_name import (
    parse_album_folder_name,
    parse_title_from_filename,
)


class TestParseAlbumFolderName:
    """parse_album_folder_name derives (artist, album) hints from a dir name."""

    def test_reported_scene_release(self):
        """The Holy Klassiker example: scene suffix stripped, double space
        collapsed, artist/album split on the first '-'."""
        artist, album = parse_album_folder_name(
            "Holy Klassiker-Folge 1  Der kleine Prinz"
            "-16BIT-44-KHZ-WEB-FLAC-2021-WALKMAN"
        )
        assert artist == "Holy Klassiker"
        assert album == "Folge 1 Der kleine Prinz"

    def test_spaced_hyphen_separator(self):
        artist, album = parse_album_folder_name("Pink Floyd - The Wall")
        assert artist == "Pink Floyd"
        assert album == "The Wall"

    def test_html_entity_decoded(self):
        artist, album = parse_album_folder_name(
            "Simon &amp; Garfunkel-Bookends-WEB-FLAC-1968-GRP"
        )
        assert artist == "Simon & Garfunkel"
        assert album == "Bookends"

    def test_single_token_is_album_only(self):
        artist, album = parse_album_folder_name("The Wall")
        assert artist is None
        assert album == "The Wall"

    def test_numeric_album_not_treated_as_year(self):
        """A bare '25' is not a 19xx/20xx year, so it survives as the album."""
        artist, album = parse_album_folder_name("Adele-25")
        assert artist == "Adele"
        assert album == "25"

    def test_trailing_year_stripped(self):
        artist, album = parse_album_folder_name("Sigur Ros-Takk-2005-WEB-FLAC-GRP")
        assert artist == "Sigur Ros"
        assert album == "Takk"

    def test_album_with_internal_hyphen_rejoined(self):
        artist, album = parse_album_folder_name("Artist-Some-Long-Album-FLAC")
        assert artist == "Artist"
        assert album == "Some - Long - Album"

    @pytest.mark.parametrize("name", ["", None])
    def test_empty_input(self, name):
        assert parse_album_folder_name(name) == (None, None)

    def test_leading_scene_token_not_cut(self):
        """A scene token at index 0 must not wipe the whole name."""
        artist, album = parse_album_folder_name("WEB-Only-Album")
        # index 0 ('WEB') is never a cut point, so 'WEB' stays the artist.
        assert artist == "WEB"
        assert album == "Only - Album"


class TestParseTitleFromFilename:
    """parse_title_from_filename derives a track-title hint from a filename."""

    def test_scene_filename_with_artist_hint(self):
        title = parse_title_from_filename(
            "01-holy_klassiker-teil_1_-_folge_1__der_kleine_prinz.flac",
            artist_hint="Holy Klassiker",
        )
        assert title == "teil 1 - folge 1 der kleine prinz"

    def test_track_number_prefix_dropped(self):
        assert parse_title_from_filename("03 - Some Title.mp3") == "Some Title"

    def test_four_digit_prefix_is_not_a_track_number(self):
        """A year-like prefix must survive (mirrors the track-number parser)."""
        assert (
            parse_title_from_filename("2020 - New Year Song.flac")
            == "2020 - New Year Song"
        )

    def test_underscores_become_spaces(self):
        assert (
            parse_title_from_filename("05_artist_name_-_real_title.flac",
                                      artist_hint="Artist Name")
            == "real title"
        )

    def test_artist_strip_skipped_when_it_eats_whole_title(self):
        """If stripping the artist leaves nothing, keep the original."""
        title = parse_title_from_filename("01-coldplay.flac", artist_hint="Coldplay")
        assert title == "coldplay"

    @pytest.mark.parametrize("name", ["", None])
    def test_empty_input(self, name):
        assert parse_title_from_filename(name) is None
