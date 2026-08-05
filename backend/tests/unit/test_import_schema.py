"""Unit tests for the ImportAlbumRequest candidate / import-as-is contract."""

import pytest
from pydantic import ValidationError

from app.schemas.beets_import import ImportAlbumRequest, ImportCandidate


def _candidate() -> ImportCandidate:
    return ImportCandidate(
        source="MusicBrainz",
        source_id="mb-123",
        artist="Test Artist",
        album="Test Album",
        year=2020,
        tracks=[{"index": 1, "title": "Track 1", "length": 100.0}],
    )


class TestImportAlbumRequestContract:
    """A normal import needs a candidate; an as-is import must omit it."""

    def test_normal_import_accepts_candidate(self):
        req = ImportAlbumRequest(album_path="/import/Artist/Album", candidate=_candidate())
        assert req.import_as_is is False
        assert req.candidate is not None

    def test_normal_import_requires_candidate(self):
        with pytest.raises(ValidationError, match="candidate is required"):
            ImportAlbumRequest(album_path="/import/Artist/Album")

    def test_import_as_is_without_candidate(self):
        req = ImportAlbumRequest(album_path="/import/Artist/Album", import_as_is=True)
        assert req.import_as_is is True
        assert req.candidate is None

    def test_import_as_is_rejects_candidate(self):
        with pytest.raises(ValidationError, match="candidate must be omitted"):
            ImportAlbumRequest(
                album_path="/import/Artist/Album",
                import_as_is=True,
                candidate=_candidate(),
            )

    def test_camel_case_alias(self):
        """Frontend sends importAsIs in camelCase."""
        req = ImportAlbumRequest.model_validate(
            {"albumPath": "/import/Artist/Album", "importAsIs": True}
        )
        assert req.import_as_is is True
