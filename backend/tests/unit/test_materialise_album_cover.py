"""The import-time cover step prefers a local/embedded cover and only falls
back to downloading the candidate's remote cover when none is found (#148)."""
from unittest.mock import MagicMock, patch

from app.tasks import beets_tasks


COMMON = dict(
    album_id=5,
    database_path="/db.blb",
    destination_path="/lib/Artist/Album",
    art_filename="albumart",
    source_folder="/imports/Album",
    audio_files=["/imports/Album/01.flac"],
    library_path="/lib",
)


def test_local_cover_wins_no_download():
    svc = MagicMock()
    with patch.object(beets_tasks, "ensure_album_cover", return_value="/lib/Artist/Album/cover.jpg"), \
            patch.object(beets_tasks, "BeetsLibraryService", return_value=svc), \
            patch("app.services.cover_download.download_cover_to_album") as mock_dl:
        beets_tasks._materialise_album_cover(cover_url="https://e/c.jpg", **COMMON)

    svc.update_album_artpath.assert_called_once_with("/db.blb", 5, "/lib/Artist/Album/cover.jpg")
    mock_dl.assert_not_called()


def test_falls_back_to_remote_cover_when_no_local():
    svc = MagicMock()
    with patch.object(beets_tasks, "ensure_album_cover", return_value=None), \
            patch.object(beets_tasks, "BeetsLibraryService", return_value=svc), \
            patch("app.services.cover_download.download_cover_to_album") as mock_dl:
        beets_tasks._materialise_album_cover(cover_url="https://e/c.jpg", **COMMON)

    mock_dl.assert_called_once_with(
        "https://e/c.jpg",
        database_path="/db.blb",
        album_id=5,
        library_path="/lib",
        art_filename="albumart",
    )
    svc.update_album_artpath.assert_not_called()


def test_no_local_and_no_cover_url_does_nothing():
    svc = MagicMock()
    with patch.object(beets_tasks, "ensure_album_cover", return_value=None), \
            patch.object(beets_tasks, "BeetsLibraryService", return_value=svc), \
            patch("app.services.cover_download.download_cover_to_album") as mock_dl:
        beets_tasks._materialise_album_cover(cover_url=None, **COMMON)

    mock_dl.assert_not_called()
    svc.update_album_artpath.assert_not_called()


def test_cover_failure_is_swallowed():
    # A failure in the cover step must never propagate (it would fail the import).
    with patch.object(beets_tasks, "ensure_album_cover", side_effect=RuntimeError("boom")), \
            patch.object(beets_tasks, "BeetsLibraryService", return_value=MagicMock()):
        beets_tasks._materialise_album_cover(cover_url="https://e/c.jpg", **COMMON)  # no raise
