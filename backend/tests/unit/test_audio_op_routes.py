"""Unit tests for the audio-op convert/dedupe route handlers.

Focus: the job is enqueued as ``queued`` (not ``running``) so the frontend can
show each album's spinner the instant it's dispatched — the worker flips it to
``running`` once it actually starts. This is what keeps a burst of conversions
from looking hung (issue #130).
"""

from unittest.mock import Mock, patch

import pytest

from app.api.routes.beets_autotag import convert_audio, dedupe_wav
from app.schemas.beets_autotag import ConvertAudioRequest, DedupeWavRequest


@pytest.fixture
def mock_library():
    library = Mock()
    library.id = 1
    library.slug = "test-library"
    library.import_path = "/data/import/test"
    return library


@pytest.fixture
def mock_autotag_service():
    service = Mock()
    service.validate_album_path.return_value = "/data/import/test/Artist/Album"
    return service


@pytest.fixture
def mock_redis_manager():
    redis_manager = Mock()
    redis_manager.acquire_audio_op_lock.return_value = True
    return redis_manager


def test_convert_audio_enqueues_as_queued(
    mock_library, mock_autotag_service, mock_redis_manager
):
    request = ConvertAudioRequest(
        album_path="Artist/Album",
        source_format="wav",
        target_format="flac",
        delete_originals=False,
    )

    with patch(
        "app.api.routes.beets_autotag.get_library_by_slug",
        return_value=mock_library,
    ), patch(
        "app.api.routes.beets_autotag.get_redis_key_manager",
        return_value=mock_redis_manager,
    ), patch(
        "app.api.routes.beets_autotag.wav_flac_service"
    ) as mock_service, patch(
        "app.api.routes.beets_autotag.convert_audio_task"
    ) as mock_task, patch(
        "os.path.isdir", return_value=True
    ):
        mock_service.SOURCE_EXTS = {"wav": ".wav", "wma": ".wma"}
        mock_service.find_audio_files.return_value = ["/data/import/test/Artist/Album/01.wav"]

        response = convert_audio(
            slug="test-library",
            request=request,
            db=Mock(),
            autotag_service=mock_autotag_service,
        )

    # Response advertises the queued state, not running.
    assert response.status == "queued"
    # Redis was seeded as queued (the task itself flips it to running later).
    statuses = [
        call.kwargs.get("status", call.args[1] if len(call.args) > 1 else None)
        for call in mock_redis_manager.set_audio_op_status.call_args_list
    ]
    assert statuses == ["queued"]
    # The task was actually dispatched.
    mock_task.delay.assert_called_once()


def test_dedupe_wav_enqueues_as_queued(
    mock_library, mock_autotag_service, mock_redis_manager
):
    request = DedupeWavRequest(album_path="Artist/Album")

    with patch(
        "app.api.routes.beets_autotag.get_library_by_slug",
        return_value=mock_library,
    ), patch(
        "app.api.routes.beets_autotag.get_redis_key_manager",
        return_value=mock_redis_manager,
    ), patch(
        "app.api.routes.beets_autotag.wav_flac_service"
    ) as mock_service, patch(
        "app.api.routes.beets_autotag.remove_duplicate_wavs_task"
    ) as mock_task, patch(
        "os.path.isdir", return_value=True
    ):
        mock_service.find_duplicate_wavs.return_value = [
            "/data/import/test/Artist/Album/01.wav"
        ]

        response = dedupe_wav(
            slug="test-library",
            request=request,
            db=Mock(),
            autotag_service=mock_autotag_service,
        )

    assert response.status == "queued"
    statuses = [
        call.kwargs.get("status", call.args[1] if len(call.args) > 1 else None)
        for call in mock_redis_manager.set_audio_op_status.call_args_list
    ]
    assert statuses == ["queued"]
    mock_task.delay.assert_called_once()


# ============================================================================
# In-place WAV→FLAC conversion for imported albums (albums/{id}/convert-wav)
# ============================================================================


@pytest.fixture
def mock_imported_library():
    library = Mock()
    library.id = 1
    library.slug = "test-library"
    library.database_path = "/data/databases/test-library.db"
    library.library_path = "/data/libraries/test-library"
    return library


def _make_track(track_id: int, path: str) -> Mock:
    track = Mock()
    track.id = track_id
    track.path = path
    return track


def _convert_album_wav_patches(mock_imported_library, mock_redis_manager):
    """Common patch stack for the imported-album convert route."""
    return (
        patch(
            "app.api.libraries.get_library_by_slug",
            return_value=mock_imported_library,
        ),
        patch(
            "app.api.libraries.get_redis_key_manager",
            return_value=mock_redis_manager,
        ),
        patch("app.tasks.beets_tasks.convert_imported_album_task"),
    )


def test_convert_album_wav_enqueues_as_queued(
    mock_imported_library, mock_redis_manager
):
    from fastapi import HTTPException  # noqa: F401 - parity with error tests

    from app.api.libraries import convert_album_wav
    from app.schemas.album import ConvertAlbumWavRequest

    beets_service = Mock()
    beets_service.album_exists.return_value = True
    beets_service.get_album_tracks.return_value = [
        _make_track(11, "/data/libraries/test-library/Artist/Album/01.wav"),
        _make_track(12, "/data/libraries/test-library/Artist/Album/02.flac"),
    ]

    p1, p2, p3 = _convert_album_wav_patches(mock_imported_library, mock_redis_manager)
    with p1, p2, p3 as mock_task:
        response = convert_album_wav(
            slug="test-library",
            album_id=42,
            request=ConvertAlbumWavRequest(delete_originals=True),
            db=Mock(),
            beets_service=beets_service,
        )

    assert response.status == "queued"
    assert response.album_id == 42
    # Only the .wav track counts.
    assert response.wav_track_count == 1
    statuses = [
        call.kwargs.get("status", call.args[1] if len(call.args) > 1 else None)
        for call in mock_redis_manager.set_audio_op_status.call_args_list
    ]
    assert statuses == ["queued"]
    mock_task.delay.assert_called_once_with(
        job_id=response.job_id,
        library_id=1,
        album_id=42,
        delete_originals=True,
    )
    # The lock is keyed by album id, not folder path.
    lock_call = mock_redis_manager.acquire_audio_op_lock.call_args
    assert lock_call.args[:2] == (1, "imported-album:42")


def test_convert_album_wav_rejects_album_without_wavs(
    mock_imported_library, mock_redis_manager
):
    from fastapi import HTTPException

    from app.api.libraries import convert_album_wav
    from app.schemas.album import ConvertAlbumWavRequest

    beets_service = Mock()
    beets_service.album_exists.return_value = True
    beets_service.get_album_tracks.return_value = [
        _make_track(11, "/data/libraries/test-library/Artist/Album/01.flac"),
    ]

    p1, p2, p3 = _convert_album_wav_patches(mock_imported_library, mock_redis_manager)
    with p1, p2, p3:
        with pytest.raises(HTTPException) as exc_info:
            convert_album_wav(
                slug="test-library",
                album_id=42,
                request=ConvertAlbumWavRequest(),
                db=Mock(),
                beets_service=beets_service,
            )

    assert exc_info.value.status_code == 400
    mock_redis_manager.acquire_audio_op_lock.assert_not_called()


def test_convert_album_wav_missing_album_is_404(
    mock_imported_library, mock_redis_manager
):
    from fastapi import HTTPException

    from app.api.libraries import convert_album_wav
    from app.schemas.album import ConvertAlbumWavRequest

    beets_service = Mock()
    beets_service.album_exists.return_value = False

    p1, p2, p3 = _convert_album_wav_patches(mock_imported_library, mock_redis_manager)
    with p1, p2, p3:
        with pytest.raises(HTTPException) as exc_info:
            convert_album_wav(
                slug="test-library",
                album_id=42,
                request=ConvertAlbumWavRequest(),
                db=Mock(),
                beets_service=beets_service,
            )

    assert exc_info.value.status_code == 404


def test_convert_album_wav_concurrent_op_is_409(
    mock_imported_library, mock_redis_manager
):
    from fastapi import HTTPException

    from app.api.libraries import convert_album_wav
    from app.schemas.album import ConvertAlbumWavRequest

    beets_service = Mock()
    beets_service.album_exists.return_value = True
    beets_service.get_album_tracks.return_value = [
        _make_track(11, "/data/libraries/test-library/Artist/Album/01.wav"),
    ]
    mock_redis_manager.acquire_audio_op_lock.return_value = False

    p1, p2, p3 = _convert_album_wav_patches(mock_imported_library, mock_redis_manager)
    with p1, p2, p3 as mock_task:
        with pytest.raises(HTTPException) as exc_info:
            convert_album_wav(
                slug="test-library",
                album_id=42,
                request=ConvertAlbumWavRequest(),
                db=Mock(),
                beets_service=beets_service,
            )

    assert exc_info.value.status_code == 409
    mock_task.delay.assert_not_called()
