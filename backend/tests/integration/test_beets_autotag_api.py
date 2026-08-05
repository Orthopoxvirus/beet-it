"""Integration tests for beets autotag API endpoints."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from app.models.library import Library
from app.schemas.beets_autotag import (
    AnalyzeAlbumRequest,
    AnalyzeAlbumResponse,
    BeetsAutotagErrorCodes,
    Candidate,
    CandidateTrack,
    LocalAlbumInfo,
    LocalTrackInfo,
    ManualCandidateRequest,
    ManualCandidateResponse,
    MetadataChange,
    TrackChange,
    detect_provider,
    extract_id_from_link,
)
from app.services.beets_autotag_service import (
    AnalysisTimeoutError,
    BeetsAnalysisError,
    CandidateData,
    CandidateTrackData,
    LocalAlbumData,
    LocalTrackData,
    MusicBrainzError,
)


@pytest.fixture
def mock_library():
    """Create a mock library."""
    library = Mock(spec=Library)
    library.id = 1
    library.name = "Test Library"
    library.slug = "test-library"
    library.import_path = "/data/import/test"
    library.config_path = "/data/config/test.yaml"
    return library


@pytest.fixture
def mock_library_no_import():
    """Create a mock library without import path."""
    library = Mock(spec=Library)
    library.id = 2
    library.name = "No Import Library"
    library.slug = "no-import"
    library.import_path = None
    library.config_path = None
    return library


@pytest.fixture
def mock_local_album():
    """Create mock local album data."""
    return LocalAlbumData(
        path="/data/import/test/Artist/Album",
        artist="Test Artist",
        album="Test Album",
        tracks=[
            LocalTrackData(
                path="/data/import/test/Artist/Album/01 - Track 1.mp3",
                title="Track 1",
                track_num=1,
                length=180.5,
            ),
            LocalTrackData(
                path="/data/import/test/Artist/Album/02 - Track 2.mp3",
                title="Track 2",
                track_num=2,
                length=200.0,
            ),
        ],
    )


@pytest.fixture
def mock_candidates():
    """Create mock candidate data."""
    return [
        CandidateData(
            source="MusicBrainz",
            source_id="mb-release-123",
            similarity=0.952,
            artist="Test Artist",
            album="Test Album (Remastered)",
            year=2020,
            label="Test Label",
            country="US",
            media="CD",
            tracks=[
                CandidateTrackData(
                    index=1,
                    title="Track 1 (Remastered)",
                    length=181.0,
                    changes=[
                        {"field": "title", "from_value": "Track 1", "to_value": "Track 1 (Remastered)"}
                    ],
                ),
                CandidateTrackData(
                    index=2,
                    title="Track 2 (Remastered)",
                    length=200.5,
                    changes=[
                        {"field": "title", "from_value": "Track 2", "to_value": "Track 2 (Remastered)"}
                    ],
                ),
            ],
            changes=[
                {"field": "album", "from_value": "Test Album", "to_value": "Test Album (Remastered)"},
                {"field": "year", "from_value": None, "to_value": "2020"},
            ],
            track_changes=[
                {"index": 1, "local_title": "Track 1", "candidate_title": "Track 1 (Remastered)"},
                {"index": 2, "local_title": "Track 2", "candidate_title": "Track 2 (Remastered)"},
            ],
        ),
        CandidateData(
            source="MusicBrainz",
            source_id="mb-release-456",
            similarity=0.891,
            artist="Test Artist",
            album="Test Album",
            year=2010,
            label="Original Label",
            country="UK",
            media="Vinyl",
            tracks=[
                CandidateTrackData(index=1, title="Track 1", length=180.0, changes=[]),
                CandidateTrackData(index=2, title="Track 2", length=199.0, changes=[]),
            ],
            changes=[{"field": "year", "from_value": None, "to_value": "2010"}],
            track_changes=[],
        ),
    ]


class TestAnalyzeAlbumRequestSchema:
    """Tests for AnalyzeAlbumRequest schema validation."""

    def test_valid_request(self):
        """Test valid request passes validation."""
        request = AnalyzeAlbumRequest(album_path="Artist/Album")
        assert request.album_path == "Artist/Album"

    def test_valid_request_absolute_path(self):
        """Test valid absolute path passes validation."""
        request = AnalyzeAlbumRequest(album_path="/data/import/Artist/Album")
        assert request.album_path == "/data/import/Artist/Album"

    def test_invalid_empty_path(self):
        """Test empty path fails validation."""
        with pytest.raises(ValueError):
            AnalyzeAlbumRequest(album_path="")

    def test_invalid_whitespace_path(self):
        """Test whitespace path fails validation."""
        with pytest.raises(ValueError):
            AnalyzeAlbumRequest(album_path="   ")

    def test_invalid_null_byte(self):
        """Test path with null byte fails validation."""
        with pytest.raises(ValueError, match="invalid characters"):
            AnalyzeAlbumRequest(album_path="path\x00with\x00nulls")

    def test_invalid_path_traversal(self):
        """Test path traversal attempt fails validation."""
        with pytest.raises(ValueError, match="parent directory references"):
            AnalyzeAlbumRequest(album_path="../../../etc/passwd")

    def test_path_traversal_in_middle(self):
        """Test path traversal in middle fails validation."""
        with pytest.raises(ValueError, match="parent directory references"):
            AnalyzeAlbumRequest(album_path="Artist/../../../etc/passwd")


class TestAnalyzeAlbumResponseSchema:
    """Tests for AnalyzeAlbumResponse schema."""

    def test_response_creation(self):
        """Test creating a response object."""
        response = AnalyzeAlbumResponse(
            album_path="Artist/Album",
            local_album=LocalAlbumInfo(
                path="/data/import/Artist/Album",
                artist="Artist",
                album="Album",
                tracks=[],
            ),
            candidates=[],
            analyzed_at=datetime.now(timezone.utc),
        )
        assert response.album_path == "Artist/Album"
        assert response.local_album.artist == "Artist"
        assert response.candidates == []

    def test_response_with_candidates(
        self, mock_local_album, mock_candidates
    ):
        """Test response with candidate data."""
        local_album_info = LocalAlbumInfo(
            path=mock_local_album.path,
            artist=mock_local_album.artist,
            album=mock_local_album.album,
            tracks=[
                LocalTrackInfo(
                    path=t.path,
                    title=t.title,
                    track_num=t.track_num,
                    length=t.length,
                )
                for t in mock_local_album.tracks
            ],
        )

        candidates_response = [
            Candidate(
                source=c.source,
                source_id=c.source_id,
                similarity=c.similarity,
                artist=c.artist,
                album=c.album,
                year=c.year,
                label=c.label,
                country=c.country,
                media=c.media,
                tracks=[
                    CandidateTrack(
                        index=t.index,
                        title=t.title,
                        length=t.length,
                        changes=[
                            MetadataChange(
                                field=ch["field"],
                                from_value=ch.get("from_value"),
                                to_value=ch.get("to_value"),
                            )
                            for ch in t.changes
                        ],
                    )
                    for t in c.tracks
                ],
                changes=[
                    MetadataChange(
                        field=ch["field"],
                        from_value=ch.get("from_value"),
                        to_value=ch.get("to_value"),
                    )
                    for ch in c.changes
                ],
                track_changes=[
                    TrackChange(
                        index=tc["index"],
                        local_title=tc.get("local_title"),
                        candidate_title=tc.get("candidate_title"),
                    )
                    for tc in c.track_changes
                ],
            )
            for c in mock_candidates
        ]

        response = AnalyzeAlbumResponse(
            album_path="Artist/Album",
            local_album=local_album_info,
            candidates=candidates_response,
            analyzed_at=datetime.now(timezone.utc),
        )

        assert len(response.candidates) == 2
        assert response.candidates[0].similarity == 0.952
        assert response.candidates[0].source == "MusicBrainz"
        assert len(response.candidates[0].tracks) == 2
        assert len(response.candidates[0].changes) == 2
        assert len(response.candidates[0].track_changes) == 2


class TestLocalTrackInfoSchema:
    """Tests for LocalTrackInfo schema."""

    def test_valid_track_info(self):
        """Test creating valid track info."""
        track = LocalTrackInfo(
            path="/data/import/track.mp3",
            title="Track Title",
            track_num=1,
            length=180.5,
        )
        assert track.path == "/data/import/track.mp3"
        assert track.title == "Track Title"
        assert track.track_num == 1
        assert track.length == 180.5

    def test_optional_fields(self):
        """Test track info with optional fields as None."""
        track = LocalTrackInfo(
            path="/data/import/track.mp3",
            title=None,
            track_num=None,
            length=None,
        )
        assert track.path == "/data/import/track.mp3"
        assert track.title is None

    def test_invalid_track_num(self):
        """Test track number must be >= 1."""
        with pytest.raises(ValueError):
            LocalTrackInfo(
                path="/data/import/track.mp3",
                title="Title",
                track_num=0,
                length=180.0,
            )


class TestCandidateSchema:
    """Tests for Candidate schema."""

    def test_valid_candidate(self):
        """Test creating valid candidate."""
        candidate = Candidate(
            source="MusicBrainz",
            source_id="mb-123",
            similarity=0.95,
            artist="Artist",
            album="Album",
            year=2020,
            label="Label",
            country="US",
            media="CD",
            tracks=[],
            changes=[],
            track_changes=[],
        )
        assert candidate.source == "MusicBrainz"
        assert candidate.similarity == 0.95

    def test_similarity_bounds(self):
        """Test similarity must be between 0 and 1."""
        # Valid at boundaries
        Candidate(
            source="MusicBrainz",
            source_id=None,
            similarity=0.0,
            artist="Artist",
            album="Album",
            year=None,
            label=None,
            country=None,
            media=None,
            tracks=[],
            changes=[],
            track_changes=[],
        )
        Candidate(
            source="MusicBrainz",
            source_id=None,
            similarity=1.0,
            artist="Artist",
            album="Album",
            year=None,
            label=None,
            country=None,
            media=None,
            tracks=[],
            changes=[],
            track_changes=[],
        )

        # Invalid below 0
        with pytest.raises(ValueError):
            Candidate(
                source="MusicBrainz",
                source_id=None,
                similarity=-0.1,
                artist="Artist",
                album="Album",
                year=None,
                label=None,
                country=None,
                media=None,
                tracks=[],
                changes=[],
                track_changes=[],
            )

        # Invalid above 1
        with pytest.raises(ValueError):
            Candidate(
                source="MusicBrainz",
                source_id=None,
                similarity=1.1,
                artist="Artist",
                album="Album",
                year=None,
                label=None,
                country=None,
                media=None,
                tracks=[],
                changes=[],
                track_changes=[],
            )


class TestMetadataChangeSchema:
    """Tests for MetadataChange schema."""

    def test_valid_change(self):
        """Test creating valid metadata change."""
        change = MetadataChange(
            field="artist",
            from_value="Old Artist",
            to_value="New Artist",
        )
        assert change.field == "artist"
        assert change.from_value == "Old Artist"
        assert change.to_value == "New Artist"

    def test_null_values(self):
        """Test change with null values."""
        change = MetadataChange(
            field="year",
            from_value=None,
            to_value="2020",
        )
        assert change.from_value is None
        assert change.to_value == "2020"


class TestTrackChangeSchema:
    """Tests for TrackChange schema."""

    def test_valid_track_change(self):
        """Test creating valid track change."""
        change = TrackChange(
            index=1,
            local_title="Old Title",
            candidate_title="New Title",
        )
        assert change.index == 1
        assert change.local_title == "Old Title"
        assert change.candidate_title == "New Title"

    def test_invalid_index(self):
        """Test index must be >= 1."""
        with pytest.raises(ValueError):
            TrackChange(
                index=0,
                local_title="Title",
                candidate_title="Title",
            )


class TestErrorCodes:
    """Tests for BeetsAutotagErrorCodes."""

    def test_error_codes_exist(self):
        """Test all expected error codes exist."""
        assert BeetsAutotagErrorCodes.INVALID_ALBUM_PATH == "INVALID_ALBUM_PATH"
        assert BeetsAutotagErrorCodes.PATH_OUTSIDE_IMPORT == "PATH_OUTSIDE_IMPORT"
        assert BeetsAutotagErrorCodes.NO_IMPORT_PATH == "NO_IMPORT_PATH"
        assert BeetsAutotagErrorCodes.LIBRARY_NOT_FOUND == "LIBRARY_NOT_FOUND"
        assert BeetsAutotagErrorCodes.ALBUM_NOT_FOUND == "ALBUM_NOT_FOUND"
        assert BeetsAutotagErrorCodes.NO_AUDIO_FILES == "NO_AUDIO_FILES"
        assert BeetsAutotagErrorCodes.ANALYSIS_TIMEOUT == "ANALYSIS_TIMEOUT"
        assert BeetsAutotagErrorCodes.BEETS_ERROR == "BEETS_ERROR"
        assert BeetsAutotagErrorCodes.MUSICBRAINZ_ERROR == "MUSICBRAINZ_ERROR"


class TestCandidateTrackSchema:
    """Tests for CandidateTrack schema."""

    def test_valid_candidate_track(self):
        """Test creating valid candidate track."""
        track = CandidateTrack(
            index=1,
            title="Track Title",
            length=180.5,
            changes=[],
        )
        assert track.index == 1
        assert track.title == "Track Title"
        assert track.length == 180.5

    def test_invalid_index(self):
        """Test index must be >= 1."""
        with pytest.raises(ValueError):
            CandidateTrack(
                index=0,
                title="Title",
                length=180.0,
                changes=[],
            )

    def test_with_changes(self):
        """Test candidate track with changes."""
        track = CandidateTrack(
            index=1,
            title="New Title",
            length=180.5,
            changes=[
                MetadataChange(field="title", from_value="Old", to_value="New Title")
            ],
        )
        assert len(track.changes) == 1
        assert track.changes[0].field == "title"

    def test_local_pairing_fields_default_none(self):
        """local_title/local_path default to None and are optional."""
        track = CandidateTrack(index=1, title="T", length=None, changes=[])
        assert track.local_title is None
        assert track.local_path is None

    def test_local_pairing_fields_serialize_camel_case(self):
        """The paired local title/path round-trip through the camelCase alias."""
        track = CandidateTrack(
            index=1,
            title="Stay",
            length=180.0,
            local_title="Stay",
            local_path="/import/ezra/01.flac",
            changes=[],
        )
        dumped = track.model_dump(by_alias=True)
        assert dumped["localTitle"] == "Stay"
        assert dumped["localPath"] == "/import/ezra/01.flac"


class TestStoreManualCandidateInCache:
    """Regression for #27: caching a manual candidate must preserve the
    local↔candidate pairing, otherwise the Local column goes empty again the
    moment the cached copy is re-read."""

    def test_cached_manual_candidate_keeps_local_pairing(self):
        from app.api.routes.beets_autotag import store_manual_candidate_in_cache

        captured = {}
        redis_manager = Mock()
        redis_manager.get_beets_album_result.return_value = None

        def _capture(library_id, album_path, result, *args, **kwargs):
            captured["result"] = result

        redis_manager.set_beets_album_result.side_effect = _capture

        candidate = Candidate(
            source="Deezer",
            source_id="123",
            similarity=1.0,
            artist="Ezra George",
            album="Photobook",
            year=2020,
            tracks=[
                CandidateTrack(
                    index=1,
                    title="Stay",
                    length=180.0,
                    local_title="Stay",
                    local_path="/import/ezra/01.flac",
                    changes=[],
                )
            ],
            changes=[],
            track_changes=[],
            is_manual=True,
        )

        store_manual_candidate_in_cache(
            redis_manager, library_id=1, album_path="/import/ezra", candidate=candidate, provider="deezer"
        )

        stored_track = captured["result"]["manual_candidates"][0]["tracks"][0]
        assert stored_track["local_title"] == "Stay"
        assert stored_track["local_path"] == "/import/ezra/01.flac"


class TestManualCandidateRequestSchema:
    """Tests for ManualCandidateRequest schema validation."""

    def test_valid_spotify_link(self):
        """Test valid Spotify link passes validation."""
        request = ManualCandidateRequest(
            album_path="Artist/Album",
            link="https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv"
        )
        assert request.album_path == "Artist/Album"
        assert "spotify.com" in request.link

    def test_valid_deezer_link(self):
        """Test valid Deezer link passes validation."""
        request = ManualCandidateRequest(
            album_path="Artist/Album",
            link="https://www.deezer.com/album/12345"
        )
        assert "deezer.com" in request.link

    def test_valid_discogs_link(self):
        """Test valid Discogs link passes validation."""
        request = ManualCandidateRequest(
            album_path="Artist/Album",
            link="https://www.discogs.com/release/12345"
        )
        assert "discogs.com" in request.link

    def test_valid_musicbrainz_link(self):
        """Test valid MusicBrainz link passes validation."""
        request = ManualCandidateRequest(
            album_path="Artist/Album",
            link="https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert "musicbrainz.org" in request.link

    def test_valid_musicbrainz_uuid(self):
        """Test valid MusicBrainz UUID passes validation."""
        request = ManualCandidateRequest(
            album_path="Artist/Album",
            link="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert request.link == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_invalid_link_format(self):
        """Test invalid link format fails validation."""
        with pytest.raises(ValueError, match="Link must be a valid URL"):
            ManualCandidateRequest(
                album_path="Artist/Album",
                link="https://example.com/album/123"
            )

    def test_invalid_empty_link(self):
        """Test empty link fails validation."""
        with pytest.raises(ValueError):
            ManualCandidateRequest(
                album_path="Artist/Album",
                link=""
            )

    def test_invalid_empty_album_path(self):
        """Test empty album path fails validation."""
        with pytest.raises(ValueError):
            ManualCandidateRequest(
                album_path="",
                link="https://open.spotify.com/album/abc123"
            )

    def test_invalid_path_traversal(self):
        """Test path traversal in album_path fails validation."""
        with pytest.raises(ValueError, match="parent directory references"):
            ManualCandidateRequest(
                album_path="../../../etc/passwd",
                link="https://open.spotify.com/album/abc123"
            )

    def test_invalid_null_byte_in_path(self):
        """Test null byte in album_path fails validation."""
        with pytest.raises(ValueError, match="invalid characters"):
            ManualCandidateRequest(
                album_path="path\x00with\x00nulls",
                link="https://open.spotify.com/album/abc123"
            )


class TestDetectProvider:
    """Tests for detect_provider function."""

    def test_detect_deezer(self):
        """Test detecting Deezer links."""
        assert detect_provider("https://www.deezer.com/album/12345") == "deezer"
        assert detect_provider("https://deezer.com/us/album/12345") == "deezer"
        assert detect_provider("https://www.deezer.com/fr/album/98765432") == "deezer"

    def test_detect_spotify(self):
        """Test detecting Spotify links."""
        assert detect_provider("https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv") == "spotify"
        assert detect_provider("https://open.spotify.com/intl-de/album/4LH4d3cOWNNsVw41Gqt2kv") == "spotify"

    def test_detect_discogs(self):
        """Test detecting Discogs links."""
        assert detect_provider("https://www.discogs.com/release/12345") == "discogs"
        assert detect_provider("https://discogs.com/release/98765432") == "discogs"
        assert detect_provider("https://www.discogs.com/master/12345") == "discogs"

    def test_detect_musicbrainz_url(self):
        """Test detecting MusicBrainz URLs."""
        assert detect_provider("https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890") == "musicbrainz"
        assert detect_provider("https://www.musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890") == "musicbrainz"

    def test_detect_musicbrainz_uuid(self):
        """Test detecting MusicBrainz UUIDs."""
        assert detect_provider("a1b2c3d4-e5f6-7890-abcd-ef1234567890") == "musicbrainz"

    def test_detect_invalid_link(self):
        """Test detecting invalid links returns None."""
        assert detect_provider("https://example.com/album/123") is None
        assert detect_provider("not-a-url") is None
        assert detect_provider("") is None

    def test_detect_whitespace_trimmed(self):
        """Test that whitespace is trimmed."""
        assert detect_provider("  https://open.spotify.com/album/abc123  ") == "spotify"


class TestExtractIdFromLink:
    """Tests for extract_id_from_link function."""

    def test_extract_deezer_id(self):
        """Test extracting Deezer album ID."""
        assert extract_id_from_link("https://www.deezer.com/album/12345", "deezer") == "12345"
        assert extract_id_from_link("https://deezer.com/us/album/98765432", "deezer") == "98765432"

    def test_extract_spotify_id(self):
        """Test extracting Spotify album ID."""
        assert extract_id_from_link("https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv", "spotify") == "4LH4d3cOWNNsVw41Gqt2kv"
        assert extract_id_from_link("https://open.spotify.com/intl-de/album/abc123", "spotify") == "abc123"

    def test_extract_discogs_id(self):
        """Test extracting Discogs release ID."""
        assert extract_id_from_link("https://www.discogs.com/release/12345", "discogs") == "12345"
        assert extract_id_from_link("https://www.discogs.com/master/98765", "discogs") == "98765"

    def test_extract_musicbrainz_id_from_url(self):
        """Test extracting MusicBrainz UUID from URL."""
        assert extract_id_from_link(
            "https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "musicbrainz"
        ) == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_extract_musicbrainz_id_from_uuid(self):
        """Test extracting MusicBrainz UUID when link is just UUID."""
        assert extract_id_from_link(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "musicbrainz"
        ) == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_extract_unknown_provider(self):
        """Test extracting from unknown provider returns None."""
        assert extract_id_from_link("https://example.com/123", "unknown") is None


class TestCandidateWithIsManual:
    """Tests for Candidate schema with is_manual field."""

    def test_candidate_default_is_manual_false(self):
        """Test that is_manual defaults to False."""
        candidate = Candidate(
            source="MusicBrainz",
            source_id="mb-123",
            similarity=0.95,
            artist="Artist",
            album="Album",
            year=2020,
            label="Label",
            country="US",
            media="CD",
            tracks=[],
            changes=[],
            track_changes=[],
        )
        assert candidate.is_manual is False

    def test_candidate_is_manual_true(self):
        """Test setting is_manual to True."""
        candidate = Candidate(
            source="Spotify",
            source_id="spotify-123",
            similarity=1.0,
            artist="Artist",
            album="Album",
            year=2020,
            label="Label",
            country="US",
            media="Digital Media",
            tracks=[],
            changes=[],
            track_changes=[],
            is_manual=True,
        )
        assert candidate.is_manual is True


class TestManualCandidateResponseSchema:
    """Tests for ManualCandidateResponse schema."""

    def test_response_creation(self):
        """Test creating a ManualCandidateResponse."""
        candidate = Candidate(
            source="MusicBrainz",
            source_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            similarity=1.0,
            artist="Artist",
            album="Album",
            year=2020,
            label="Label",
            country="US",
            media="CD",
            tracks=[],
            changes=[],
            track_changes=[],
            is_manual=True,
        )
        response = ManualCandidateResponse(
            candidate=candidate,
            provider="musicbrainz",
        )
        assert response.provider == "musicbrainz"
        assert response.candidate.is_manual is True
        assert response.candidate.source == "MusicBrainz"


class TestAnalyzeAlbumResponseWithManualCandidates:
    """Tests for AnalyzeAlbumResponse with manual_candidates field."""

    def test_response_with_manual_candidates(self):
        """Test AnalyzeAlbumResponse includes manual_candidates."""
        manual_candidate = Candidate(
            source="Spotify",
            source_id="spotify-123",
            similarity=1.0,
            artist="Artist",
            album="Album (Deluxe)",
            year=2022,
            label="Label",
            country="US",
            media="Digital Media",
            tracks=[],
            changes=[],
            track_changes=[],
            is_manual=True,
        )

        response = AnalyzeAlbumResponse(
            album_path="Artist/Album",
            local_album=LocalAlbumInfo(
                path="/data/import/Artist/Album",
                artist="Artist",
                album="Album",
                tracks=[],
            ),
            candidates=[],
            manual_candidates=[manual_candidate],
            analyzed_at=datetime.now(timezone.utc),
        )

        assert len(response.manual_candidates) == 1
        assert response.manual_candidates[0].is_manual is True
        assert response.manual_candidates[0].source == "Spotify"

    def test_response_default_empty_manual_candidates(self):
        """Test AnalyzeAlbumResponse defaults to empty manual_candidates."""
        response = AnalyzeAlbumResponse(
            album_path="Artist/Album",
            local_album=LocalAlbumInfo(
                path="/data/import/Artist/Album",
                artist="Artist",
                album="Album",
                tracks=[],
            ),
            candidates=[],
            analyzed_at=datetime.now(timezone.utc),
        )

        assert response.manual_candidates == []


class TestNewErrorCodes:
    """Tests for new manual candidate error codes."""

    def test_manual_candidate_error_codes_exist(self):
        """Test all new manual candidate error codes exist."""
        assert BeetsAutotagErrorCodes.INVALID_LINK == "INVALID_LINK"
        assert BeetsAutotagErrorCodes.RELEASE_NOT_FOUND == "RELEASE_NOT_FOUND"
        assert BeetsAutotagErrorCodes.PLUGIN_NOT_AVAILABLE == "PLUGIN_NOT_AVAILABLE"
        assert BeetsAutotagErrorCodes.PROVIDER_ERROR == "PROVIDER_ERROR"
        assert BeetsAutotagErrorCodes.RESOLUTION_TIMEOUT == "RESOLUTION_TIMEOUT"

    def test_queue_error_codes_exist(self):
        """Test all queue-related error codes exist."""
        assert BeetsAutotagErrorCodes.ALREADY_QUEUED == "ALREADY_QUEUED"
        assert BeetsAutotagErrorCodes.ALREADY_ANALYZING == "ALREADY_ANALYZING"


class TestAnalyzeJobResponseSchema:
    """Tests for AnalyzeJobResponse schema with queue support."""

    def test_analyzing_status(self):
        """Test response with analyzing status."""
        from app.schemas.beets_autotag import AnalyzeJobResponse

        response = AnalyzeJobResponse(
            job_id="job-uuid-123",
            album_path="Artist/Album",
            status="analyzing",
            message="Analysis started",
        )
        assert response.status == "analyzing"
        assert response.queue_position is None

    def test_queued_status(self):
        """Test response with queued status."""
        from app.schemas.beets_autotag import AnalyzeJobResponse

        response = AnalyzeJobResponse(
            job_id="job-uuid-123",
            album_path="Artist/Album",
            status="queued",
            queue_position=3,
            message="Analysis queued at position 3",
        )
        assert response.status == "queued"
        assert response.queue_position == 3

    def test_completed_status(self):
        """Test response with completed status (cached)."""
        from app.schemas.beets_autotag import AnalyzeJobResponse

        response = AnalyzeJobResponse(
            job_id="job-uuid-123",
            album_path="Artist/Album",
            status="completed",
            message="Cached analysis result",
        )
        assert response.status == "completed"
        assert response.queue_position is None


class TestAnalyzeQueueResponseSchema:
    """Tests for AnalyzeQueueResponse schema."""

    def test_empty_queue_response(self):
        """Test response with empty queue."""
        from app.schemas.beets_autotag import AnalyzeQueueResponse

        response = AnalyzeQueueResponse(
            queue_depth=0,
            active_count=0,
            max_concurrent=2,
            queued_items=[],
            active_items=[],
        )
        assert response.queue_depth == 0
        assert response.active_count == 0
        assert response.max_concurrent == 2

    def test_queue_with_items(self):
        """Test response with queued items."""
        from app.schemas.beets_autotag import (
            AnalyzeQueueResponse,
            QueuedItem,
            ActiveItem,
        )

        response = AnalyzeQueueResponse(
            queue_depth=2,
            active_count=2,
            max_concurrent=2,
            queued_items=[
                QueuedItem(
                    album_path="/import/Artist1/Album1",
                    position=1,
                    queued_at=datetime.now(timezone.utc),
                ),
                QueuedItem(
                    album_path="/import/Artist2/Album2",
                    position=2,
                    queued_at=datetime.now(timezone.utc),
                ),
            ],
            active_items=[
                ActiveItem(
                    album_path="/import/Artist3/Album3",
                    job_id="job-1",
                    started_at=datetime.now(timezone.utc),
                ),
                ActiveItem(
                    album_path="/import/Artist4/Album4",
                    job_id="job-2",
                    started_at=datetime.now(timezone.utc),
                ),
            ],
        )
        assert response.queue_depth == 2
        assert response.active_count == 2
        assert len(response.queued_items) == 2
        assert len(response.active_items) == 2


class TestAnalyzeFolderResponseSchema:
    """Tests for AnalyzeFolderResponse schema."""

    def test_response_creation(self):
        """Test creating AnalyzeFolderResponse."""
        from app.schemas.beets_autotag import AnalyzeFolderResponse

        response = AnalyzeFolderResponse(
            enqueued=15,
            dispatched=2,
            already_cached=8,
            already_queued=3,
            total=28,
            message="Enqueued 15 albums for analysis",
        )
        assert response.enqueued == 15
        assert response.dispatched == 2
        assert response.already_cached == 8
        assert response.already_queued == 3
        assert response.total == 28


class TestAutoAnalyzeSettingSchemas:
    """Tests for auto-analyze setting schemas."""

    def test_request_schema(self):
        """Test AutoAnalyzeSettingRequest schema."""
        from app.schemas.beets_autotag import AutoAnalyzeSettingRequest

        request = AutoAnalyzeSettingRequest(auto_analyze_after_scan=True)
        assert request.auto_analyze_after_scan is True

        request = AutoAnalyzeSettingRequest(auto_analyze_after_scan=False)
        assert request.auto_analyze_after_scan is False

    def test_response_schema(self):
        """Test AutoAnalyzeSettingResponse schema."""
        from app.schemas.beets_autotag import AutoAnalyzeSettingResponse

        response = AutoAnalyzeSettingResponse(
            auto_analyze_after_scan=True,
            message="Auto-analyze after scan enabled",
        )
        assert response.auto_analyze_after_scan is True
        assert response.message == "Auto-analyze after scan enabled"

    def test_response_without_message(self):
        """Test AutoAnalyzeSettingResponse without optional message."""
        from app.schemas.beets_autotag import AutoAnalyzeSettingResponse

        response = AutoAnalyzeSettingResponse(auto_analyze_after_scan=False)
        assert response.auto_analyze_after_scan is False
        assert response.message is None


class TestImportCleanupSettingSchemas:
    """Tests for the per-library import-cleanup setting schemas (issue #137)."""

    def test_request_is_fully_optional(self):
        from app.schemas.beets_autotag import ImportCleanupSettingRequest

        # An empty body is valid — it clears the override.
        assert ImportCleanupSettingRequest().enabled is None

        req = ImportCleanupSettingRequest(enabled=False)
        assert req.enabled is False
        assert req.sidecar_extensions is None

    def test_request_camelcase_aliases(self):
        from app.schemas.beets_autotag import ImportCleanupSettingRequest

        req = ImportCleanupSettingRequest.model_validate(
            {"deleteRedundantImages": False, "promoteOrphanCover": False}
        )
        assert req.delete_redundant_images is False
        assert req.promote_orphan_cover is False

    def test_response_schema(self):
        from app.schemas.beets_autotag import ImportCleanupSettingResponse

        resp = ImportCleanupSettingResponse(
            enabled=True,
            sidecar_extensions=[".nfo", ".m3u"],
            delete_redundant_images=True,
            promote_orphan_cover=True,
            overridden=False,
        )
        data = resp.model_dump(by_alias=True)
        assert data["sidecarExtensions"] == [".nfo", ".m3u"]
        assert data["overridden"] is False


class TestImportCleanupSettingHelpers:
    """Round-trip the storage contract: what PUT writes, the resolver reads."""

    class _FakeDB:
        def __init__(self, settings_obj=None):
            self._settings = settings_obj
            self.commits = 0

        def query(self, _model):
            db = self

            class _Q:
                def first(self_inner):
                    return db._settings

            return _Q()

        def add(self, obj):
            self._settings = obj

        def commit(self):
            self.commits += 1

    def test_set_then_resolve_round_trip(self):
        from app.api.routes.beets_autotag import (
            _get_import_cleanup_override,
            _set_import_cleanup_override,
        )
        from app.services.import_cleanup import resolve_import_cleanup_config

        db = self._FakeDB()  # no settings row yet
        _set_import_cleanup_override(
            db, library_id=4, override={"enabled": False}
        )

        # Stored under the per-library key and read back by the resolver.
        assert _get_import_cleanup_override(db, 4) == {"enabled": False}
        cfg = resolve_import_cleanup_config(db._settings.preferences, 4)
        assert cfg.enabled is False
        # A different library still inherits the default.
        assert resolve_import_cleanup_config(db._settings.preferences, 5).enabled is True

    def test_empty_override_clears_entry(self):
        from app.api.routes.beets_autotag import (
            _get_import_cleanup_override,
            _set_import_cleanup_override,
        )

        db = self._FakeDB()
        _set_import_cleanup_override(db, 4, {"enabled": False})
        assert _get_import_cleanup_override(db, 4) == {"enabled": False}

        # An all-empty PUT clears the override → back to inheriting defaults.
        _set_import_cleanup_override(db, 4, {})
        assert _get_import_cleanup_override(db, 4) == {}


class TestBuildManualTrackChange:
    """Tests for the shared manual-candidate comparison-row builder.

    Pairing itself is covered in tests/unit/test_manual_candidate_pairing.py;
    here we check the paired rows that the resolvers emit.
    """

    def _album(self):
        return LocalAlbumData(
            path="/album",
            artist="A",
            album="B",
            tracks=[
                LocalTrackData(
                    path="/album/01 - song.flac",
                    title="Local Song",
                    track_num=1,
                    length=200.0,
                )
            ],
        )

    def test_carries_local_length_path_and_candidate_length(self):
        from app.api.routes.beets_autotag import (
            _build_manual_track_change,
            _pair_local_tracks,
        )

        album = self._album()
        paired = _pair_local_tracks(
            album, [{"title": "Candidate Song", "length": 205.0, "index": 1}]
        )
        tc = _build_manual_track_change(
            index=1,
            candidate_title="Candidate Song",
            candidate_length=205.0,
            local_track=paired[0],
        )
        assert tc.local_title == "Local Song"
        assert tc.candidate_title == "Candidate Song"
        assert tc.local_length == 200.0
        assert tc.candidate_length == 205.0
        assert tc.local_path == "/album/01 - song.flac"

    def test_emitted_even_when_title_unchanged(self):
        from app.api.routes.beets_autotag import _build_manual_track_change

        tc = _build_manual_track_change(
            index=1,
            candidate_title="Local Song",  # same as local title
            candidate_length=205.0,
            local_track=self._album().tracks[0],
        )
        # Row is still produced (durations/filename are useful without a rename).
        assert tc.local_title == tc.candidate_title == "Local Song"
        assert tc.local_length == 200.0
        assert tc.candidate_length == 205.0

    def test_no_local_match_leaves_local_fields_none(self):
        from app.api.routes.beets_autotag import _build_manual_track_change

        tc = _build_manual_track_change(
            index=99,
            candidate_title="Candidate Only",
            candidate_length=180.0,
            local_track=None,  # no local counterpart
        )
        assert tc.local_title is None
        assert tc.local_length is None
        assert tc.local_path is None
        assert tc.candidate_length == 180.0
