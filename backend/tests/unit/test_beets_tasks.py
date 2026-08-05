"""Unit tests for beets Celery tasks.

Tests cover:
- beets_update_albums task for library batch edit synchronization
"""

import subprocess
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis manager."""
    redis_manager = Mock()
    redis_manager.set_batch_update_status = Mock()
    redis_manager.update_batch_update_album_status = Mock()
    return redis_manager


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock()
    return session


@pytest.fixture
def mock_task_event_service():
    """Create a mock task event service."""
    service = Mock()
    service.record_completion = Mock()
    return service


# ============================================================================
# beets_update_albums Task Tests
# ============================================================================


class TestBeetsUpdateAlbumsTask:
    """Tests for the beets_update_albums Celery task."""

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_single_album_success(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test successful update of a single album."""
        # Import here to avoid Celery initialization issues
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # Mock successful subprocess run
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated album",
            stderr="",
        )

        # Call the task using .run() to bypass Celery's binding
        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path="/path/to/config.yaml",
            activity_event_id=1,
        )

        assert result["status"] == "completed"
        assert result["albums_succeeded"] == 1
        assert result["albums_failed"] == 0
        assert result["job_id"] == "test-job-123"

        # The task invokes `python -m beets ... update` and then, on success,
        # `python -m beets ... move` so files relocate when path-template
        # fields change. Two subprocess calls per successful album.
        assert mock_subprocess_run.call_count == 2
        update_cmd = mock_subprocess_run.call_args_list[0][0][0]
        assert update_cmd[:3] == ["python", "-m", "beets"]
        assert "-c" in update_cmd
        assert "/path/to/config.yaml" in update_cmd
        assert "update" in update_cmd
        assert "-a" in update_cmd
        assert "Test Album" in update_cmd
        move_cmd = mock_subprocess_run.call_args_list[1][0][0]
        assert move_cmd[:3] == ["python", "-m", "beets"]
        assert "move" in move_cmd

        # Verify Redis status was updated
        mock_redis_manager.set_batch_update_status.assert_called()
        mock_redis_manager.update_batch_update_album_status.assert_called_with(
            job_id="test-job-123",
            album="Test Album",
            status="completed",
            error=None,
        )

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_multiple_albums_all_success(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test successful update of multiple albums."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # Mock successful subprocess run for all albums
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated",
            stderr="",
        )

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Album 1", "Album 2", "Album 3"],
            config_path=None,
            activity_event_id=1,
        )

        assert result["status"] == "completed"
        assert result["albums_succeeded"] == 3
        assert result["albums_failed"] == 0

        # Verify subprocess was called 6 times: each successful album triggers
        # both `beet update` and a follow-up `beet move`.
        assert mock_subprocess_run.call_count == 6

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_multiple_albums_partial_success(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test partial success when some albums fail."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # First succeeds (update + move --pretend showing nothing to move),
        # second fails at the update step
        mock_subprocess_run.side_effect = [
            Mock(returncode=0, stdout="Updated", stderr=""),
            Mock(returncode=0, stdout="Moving 0 items.", stderr=""),
            Mock(returncode=1, stdout="", stderr="Album not found"),
        ]

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Album 1", "Album 2"],
            config_path=None,
            activity_event_id=1,
        )

        assert result["status"] == "partial"
        assert result["albums_succeeded"] == 1
        assert result["albums_failed"] == 1

        # Verify both status updates were made
        assert mock_redis_manager.update_batch_update_album_status.call_count == 2

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_all_albums_fail(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test when all albums fail."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # All fail
        mock_subprocess_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error",
        )

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Album 1", "Album 2"],
            config_path=None,
            activity_event_id=1,
        )

        assert result["status"] == "failed"
        assert result["albums_succeeded"] == 0
        assert result["albums_failed"] == 2

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_subprocess_timeout(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test handling of subprocess timeout."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # Simulate timeout
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd="beet update",
            timeout=120,
        )

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path=None,
            activity_event_id=1,
        )

        assert result["status"] == "failed"
        assert result["albums_failed"] == 1
        assert "timed out" in result["results"]["Test Album"]["error"].lower()

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_subprocess_exception(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test handling of general subprocess exceptions."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # Simulate exception
        mock_subprocess_run.side_effect = Exception("Unexpected error")

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path=None,
            activity_event_id=1,
        )

        assert result["status"] == "failed"
        assert result["albums_failed"] == 1
        assert "Unexpected error" in result["results"]["Test Album"]["error"]

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_no_config_path(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test that command works without config path."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated",
            stderr="",
        )

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path=None,  # No config
            activity_event_id=None,
        )

        assert result["status"] == "completed"

        # Verify subprocess was called without -c flag
        call_args = mock_subprocess_run.call_args
        cmd = call_args[0][0]
        assert "-c" not in cmd

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_activity_event_recorded(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test that activity event is recorded on completion."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated",
            stderr="",
        )

        beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path=None,
            activity_event_id=123,
        )

        # Verify activity completion was recorded
        mock_task_event_service.record_completion.assert_called_once()
        call_kwargs = mock_task_event_service.record_completion.call_args[1]
        assert call_kwargs["event_id"] == 123
        assert call_kwargs["status"] == "completed"

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_activity_event_records_failure(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test that activity event records failure status."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        mock_subprocess_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error",
        )

        beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path=None,
            activity_event_id=123,
        )

        # Verify activity failure was recorded
        mock_task_event_service.record_completion.assert_called_once()
        call_kwargs = mock_task_event_service.record_completion.call_args[1]
        assert call_kwargs["event_id"] == 123
        assert call_kwargs["status"] == "failed"

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_redis_status_updates(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test that Redis status is updated at each stage."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated",
            stderr="",
        )

        beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Album 1", "Album 2"],
            config_path=None,
            activity_event_id=None,
        )

        # Verify set_batch_update_status was called:
        # 1. Initially to set running
        # 2. Finally to set completed
        assert mock_redis_manager.set_batch_update_status.call_count == 2

        # Check first call was for running
        first_call = mock_redis_manager.set_batch_update_status.call_args_list[0]
        assert first_call[1]["status"] == "running"

        # Check second call was for completed
        second_call = mock_redis_manager.set_batch_update_status.call_args_list[1]
        assert second_call[1]["status"] == "completed"

        # Verify update_batch_update_album_status was called for each album
        assert mock_redis_manager.update_batch_update_album_status.call_count == 2

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_album_name_with_special_characters(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test handling album names with special characters."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated",
            stderr="",
        )

        # Album name with special characters
        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Album's Name (Special Edition) [Disc 1]"],
            config_path=None,
            activity_event_id=None,
        )

        assert result["status"] == "completed"

        # Verify the album name was passed correctly
        call_args = mock_subprocess_run.call_args
        cmd = call_args[0][0]
        assert "Album's Name (Special Edition) [Disc 1]" in cmd

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_results_structure(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test that results dictionary has correct structure."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        # Sequence: update Success Album, move Success Album (no-op), update
        # Failed Album. Failed update doesn't trigger a move.
        mock_subprocess_run.side_effect = [
            Mock(returncode=0, stdout="Updated", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=1, stdout="", stderr="Error message"),
        ]

        result = beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Success Album", "Failed Album"],
            config_path=None,
            activity_event_id=None,
        )

        # Check results structure
        assert "results" in result
        assert "Success Album" in result["results"]
        assert "Failed Album" in result["results"]

        # Check successful album result
        success_result = result["results"]["Success Album"]
        assert success_result["status"] == "completed"
        assert success_result["error"] is None

        # Check failed album result
        failed_result = result["results"]["Failed Album"]
        assert failed_result["status"] == "failed"
        assert "Error message" in failed_result["error"]

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_db_session_closed(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Test that database session is properly closed."""
        from app.tasks.beets_tasks import beets_update_albums

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="Updated",
            stderr="",
        )

        beets_update_albums.run(
            job_id="test-job-123",
            library_id=1,
            albums=["Test Album"],
            config_path=None,
            activity_event_id=None,
        )

        # Verify db.close() was called
        mock_db_session.close.assert_called_once()


# ============================================================================
# Batch-edit move robustness tests (issue #188)
# ============================================================================


def _proc(stdout="", returncode=0, stderr=""):
    """Build a subprocess.run result mock."""
    return Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestBatchEditMoveRobustness:
    """Regression tests for the half-moved-album failure (issue #188).

    A `beet move` that dies partway through a large album must surface as a
    failed album — never as a silent success. The move step counts pending
    relocations via `beet move --pretend`, retries after timeouts while
    progress is being made, and verifies a final pending count of 0.
    """

    def _run(self, mock_subprocess_run, side_effects, albums=None):
        from app.tasks.beets_tasks import beets_update_albums

        mock_subprocess_run.side_effect = side_effects
        return beets_update_albums.run(
            job_id="test-job-188",
            library_id=1,
            albums=albums or ["Tintenherz"],
            config_path=None,
            activity_event_id=1,
        )

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_move_failure_marks_album_failed(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """A non-zero `beet move` exit fails the album (was: silent warning)."""
        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        result = self._run(
            mock_subprocess_run,
            [
                _proc(stdout="Updated"),          # beet update
                _proc(stdout="Moving 5 items."),  # move --pretend
                _proc(returncode=1, stderr="disk full"),  # beet move
            ],
        )

        assert result["status"] == "failed"
        assert result["albums_failed"] == 1
        error = result["results"]["Tintenherz"]["error"]
        assert "file move failed" in error
        assert "disk full" in error

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_move_timeout_without_progress_fails(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """A move timeout with no progress fails loudly with the pending count."""
        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        result = self._run(
            mock_subprocess_run,
            [
                _proc(stdout="Updated"),                       # beet update
                _proc(stdout="Moving 165 items."),             # pretend
                subprocess.TimeoutExpired(cmd="beet move", timeout=600),
                _proc(stdout="Moving 165 items."),             # pretend: no progress
            ],
        )

        assert result["status"] == "failed"
        error = result["results"]["Tintenherz"]["error"]
        assert "without progress" in error
        assert "165" in error

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_move_timeout_with_progress_resumes_and_succeeds(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """A timeout after partial progress retries; the resumed move completes."""
        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        result = self._run(
            mock_subprocess_run,
            [
                _proc(stdout="Updated"),                       # beet update
                _proc(stdout="Moving 100 items."),             # pretend
                subprocess.TimeoutExpired(cmd="beet move", timeout=1000),
                _proc(stdout="Moving 40 items."),              # pretend: progress
                _proc(stdout="Moving 40 items."),              # resumed move OK
                _proc(stdout="Moving 0 items."),               # verify: done
            ],
        )

        assert result["status"] == "completed"
        assert result["albums_succeeded"] == 1
        assert result["results"]["Tintenherz"]["status"] == "completed"

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_move_verification_mismatch_fails(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """`beet move` exiting 0 with files still misplaced is not success."""
        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        result = self._run(
            mock_subprocess_run,
            [
                _proc(stdout="Updated"),            # beet update
                _proc(stdout="Moving 10 items."),   # pretend
                _proc(stdout="Moving 10 items."),   # move exits 0...
                _proc(stdout="Moving 3 items."),    # ...but 3 still misplaced
            ],
        )

        assert result["status"] == "failed"
        error = result["results"]["Tintenherz"]["error"]
        assert "move incomplete" in error
        assert "3 of 10" in error

    @patch("app.tasks.beets_tasks.get_db")
    @patch("app.tasks.beets_tasks.get_redis_manager")
    @patch("app.tasks.beets_tasks.get_task_event_service")
    @patch("subprocess.run")
    def test_soft_time_limit_marks_unfinished_albums_failed(
        self,
        mock_subprocess_run,
        mock_get_task_event_service,
        mock_get_redis_manager,
        mock_get_db,
        mock_redis_manager,
        mock_db_session,
        mock_task_event_service,
    ):
        """Celery's soft time limit leaves a final failed state, not 'running'."""
        from celery.exceptions import SoftTimeLimitExceeded

        mock_get_db.return_value = mock_db_session
        mock_get_redis_manager.return_value = mock_redis_manager
        mock_get_task_event_service.return_value = mock_task_event_service

        result = self._run(
            mock_subprocess_run,
            [SoftTimeLimitExceeded()],
            albums=["Album 1", "Album 2"],
        )

        assert result["status"] == "failed"
        assert result["albums_failed"] == 2
        for album in ("Album 1", "Album 2"):
            assert result["results"][album]["status"] == "failed"
            assert "time limit" in result["results"][album]["error"]

        # The final job status must be written so the frontend stops polling.
        final_call = mock_redis_manager.set_batch_update_status.call_args_list[-1]
        assert final_call.kwargs["status"] == "failed"
        assert final_call.kwargs["completed_at"] is not None


# ============================================================================
# _trigger_emby_refresh helper tests
# ============================================================================


class TestTriggerEmbyRefresh:
    """Tests for the post-import Emby refresh helper.

    Contract: best-effort, never raises, and reduces every outcome to a small
    status dict the import task attaches to its completion metadata.
    """

    def test_no_config_path_skips(self):
        from app.tasks.beets_tasks import _trigger_emby_refresh

        result = _trigger_emby_refresh(None)
        assert result["status"] == "skipped"

    @patch("app.tasks.beets_tasks.os.path.exists", return_value=True)
    @patch("app.services.beets_config_service.BeetsConfigService")
    def test_emby_not_configured_skips(self, mock_config_service, _exists):
        from app.tasks.beets_tasks import _trigger_emby_refresh

        parsed = Mock(emby=Mock(host="", port=8096, apikey=""))
        mock_config_service.return_value.parse_yaml_config.return_value = parsed

        result = _trigger_emby_refresh("/cfg.yaml")
        assert result["status"] == "skipped"

    @patch("app.tasks.beets_tasks.os.path.exists", return_value=True)
    @patch("app.services.emby_service.EmbyConnectionService")
    @patch("app.services.beets_config_service.BeetsConfigService")
    def test_configured_success_returns_ok(
        self, mock_config_service, mock_emby_service, _exists
    ):
        from app.tasks.beets_tasks import _trigger_emby_refresh
        from app.schemas.beets_config import EmbyRefreshResponse, EmbyTestResponse

        parsed = Mock(emby=Mock(host="emby.local", port=8096, userid="u", apikey="key"))
        mock_config_service.return_value.parse_yaml_config.return_value = parsed
        # Pre-flight reachable -> refresh runs.
        mock_emby_service.return_value.test_connection = AsyncMock(
            return_value=EmbyTestResponse(success=True, message="ok")
        )
        mock_emby_service.return_value.refresh_library = AsyncMock(
            return_value=EmbyRefreshResponse(success=True, message="ok")
        )

        result = _trigger_emby_refresh("/cfg.yaml")
        assert result["status"] == "ok"

    @patch("app.tasks.beets_tasks.os.path.exists", return_value=True)
    @patch("app.services.emby_service.EmbyConnectionService")
    @patch("app.services.beets_config_service.BeetsConfigService")
    def test_configured_failure_returns_failed(
        self, mock_config_service, mock_emby_service, _exists
    ):
        from app.tasks.beets_tasks import _trigger_emby_refresh
        from app.schemas.beets_config import EmbyRefreshResponse, EmbyTestResponse

        parsed = Mock(emby=Mock(host="emby.local", port=8096, userid="u", apikey="key"))
        mock_config_service.return_value.parse_yaml_config.return_value = parsed
        # Reachable pre-flight, but the refresh call itself fails.
        mock_emby_service.return_value.test_connection = AsyncMock(
            return_value=EmbyTestResponse(success=True, message="ok")
        )
        mock_emby_service.return_value.refresh_library = AsyncMock(
            return_value=EmbyRefreshResponse(
                success=False, message="Connection timed out"
            )
        )

        result = _trigger_emby_refresh("/cfg.yaml")
        assert result["status"] == "failed"
        assert "timed out" in result["message"].lower()

    @patch("app.tasks.beets_tasks.os.path.exists", return_value=True)
    @patch("app.services.emby_service.EmbyConnectionService")
    @patch("app.services.beets_config_service.BeetsConfigService")
    def test_unreachable_preflight_skips_refresh(
        self, mock_config_service, mock_emby_service, _exists
    ):
        from app.tasks.beets_tasks import _trigger_emby_refresh
        from app.schemas.beets_config import EmbyTestResponse

        parsed = Mock(emby=Mock(host="emby.local", port=8096, userid="u", apikey="key"))
        mock_config_service.return_value.parse_yaml_config.return_value = parsed
        # Pre-flight says Emby is down.
        mock_emby_service.return_value.test_connection = AsyncMock(
            return_value=EmbyTestResponse(
                success=False, message="Connection timed out: Unable to reach server"
            )
        )
        mock_emby_service.return_value.refresh_library = AsyncMock()

        result = _trigger_emby_refresh("/cfg.yaml")
        assert result["status"] == "skipped_unreachable"
        assert "timed out" in result["message"].lower()
        # The whole point: an unreachable Emby never gets the refresh fired at it.
        mock_emby_service.return_value.refresh_library.assert_not_called()

    @patch("app.tasks.beets_tasks.os.path.exists", return_value=True)
    @patch("app.services.beets_config_service.BeetsConfigService")
    def test_config_parse_error_is_swallowed(self, mock_config_service, _exists):
        from app.tasks.beets_tasks import _trigger_emby_refresh

        mock_config_service.return_value.parse_yaml_config.side_effect = ValueError(
            "bad yaml"
        )

        result = _trigger_emby_refresh("/cfg.yaml")  # must not raise
        assert result["status"] == "failed"


class TestResolveImportCleanupConfig:
    """The Step 5 config resolver must never fail an already-successful import."""

    def test_db_error_returns_disabled_config_without_raising(self):
        from app.tasks.beets_tasks import _resolve_import_cleanup_config

        db = Mock()
        # Simulate a transient DB failure during the UserSettings read.
        db.query.side_effect = RuntimeError("connection reset")

        config = _resolve_import_cleanup_config(db, library_id=1)

        # Skip cleanup (don't delete under uncertainty), and crucially: no raise.
        assert config.enabled is False

    def test_resolves_per_library_override_from_settings(self):
        from app.tasks.beets_tasks import _resolve_import_cleanup_config

        settings_row = Mock()
        settings_row.preferences = {
            "import_cleanup_by_library": {"1": {"enabled": False}}
        }
        db = Mock()
        db.query.return_value.first.return_value = settings_row

        config = _resolve_import_cleanup_config(db, library_id=1)
        assert config.enabled is False
        # A different library still inherits the (enabled) default.
        assert _resolve_import_cleanup_config(db, library_id=2).enabled is True

    def test_no_settings_row_uses_defaults(self):
        from app.tasks.beets_tasks import _resolve_import_cleanup_config

        db = Mock()
        db.query.return_value.first.return_value = None

        config = _resolve_import_cleanup_config(db, library_id=1)
        assert config.enabled is True


# ============================================================================
# _read_album_metadata — import-as-is folder-name reconciliation (issue #138)
# ============================================================================


class TestReadAlbumMetadata:
    """import-as-is parses the folder name into separate artist/album hints
    instead of dumping the raw scene name into both fields."""

    def _fake_item_cls(self, artist="", album="", year=0):
        item = Mock()
        item.albumartist = ""
        item.artist = artist
        item.album = album
        item.year = year
        return Mock(from_path=Mock(return_value=item))

    def test_untagged_uses_parsed_folder_name(self):
        from app.tasks.beets_tasks import _read_album_metadata

        folder = "Holy Klassiker-Folge 1  Der kleine Prinz-WEB-FLAC-2021-GRP"
        with patch("beets.library.Item", self._fake_item_cls()):
            meta = _read_album_metadata(["/x/01.flac"], folder)

        # Parsed into separate fields, scene suffix stripped — not the raw name.
        assert meta["artist"] == "Holy Klassiker"
        assert meta["album"] == "Folge 1 Der kleine Prinz"

    def test_embedded_tags_take_precedence(self):
        from app.tasks.beets_tasks import _read_album_metadata

        with patch(
            "beets.library.Item",
            self._fake_item_cls(artist="Tag Artist", album="Tag Album", year=1999),
        ):
            meta = _read_album_metadata(["/x/01.flac"], "Folder-Name-FLAC-GRP")

        assert meta["artist"] == "Tag Artist"
        assert meta["album"] == "Tag Album"
        assert meta["year"] == 1999

    def test_unparseable_folder_falls_back_to_raw_name(self):
        from app.tasks.beets_tasks import _read_album_metadata

        with patch("beets.library.Item", self._fake_item_cls()):
            meta = _read_album_metadata(["/x/01.flac"], "-")

        # Nothing parseable → raw fallback name, never empty.
        assert meta["artist"] == "-"
        assert meta["album"] == "-"


# ============================================================================
# In-place WAV→FLAC conversion of imported albums
# ============================================================================


class TestConvertImportedWavItems:
    """Unit tests for _convert_imported_wav_items — the per-item convert +
    beets-DB-sync loop behind convert_imported_album_task."""

    @pytest.fixture
    def library(self, tmp_path):
        library = Mock()
        library.database_path = str(tmp_path / "beets.db")
        library.library_path = str(tmp_path / "library")
        return library

    @pytest.fixture
    def album_dir(self, tmp_path):
        album_dir = tmp_path / "library" / "Artist" / "Album"
        album_dir.mkdir(parents=True)
        return album_dir

    @staticmethod
    def _track(track_id: int) -> Mock:
        track = Mock()
        track.id = track_id
        return track

    @staticmethod
    def _fake_transcode(src_path, target_path, **kwargs):
        with open(target_path, "wb") as fh:
            fh.write(b"flac-bytes")

    def test_converts_updates_db_and_deletes_wav(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        wav_path = album_dir / "01 Song.wav"
        wav_path.write_bytes(b"wav-bytes")

        mock_item = Mock()
        mock_lib = Mock()
        mock_lib.get_item.return_value = mock_item

        with patch(
            "app.services.wav_flac_service.transcode_file",
            side_effect=self._fake_transcode,
        ) as mock_transcode, patch("beets.library.Library", return_value=mock_lib):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[(self._track(7), str(wav_path))],
                delete_originals=True,
                file_perm=664,
            )

        assert result.converted == 1
        assert result.failed == 0
        assert result.deleted == 1
        # The transcode targeted a sibling .flac and carried the permission.
        flac_path = str(album_dir / "01 Song.flac")
        assert mock_transcode.call_args.args == (str(wav_path), flac_path)
        assert mock_transcode.call_args.kwargs["file_perm"] == 664
        # The beets item was repointed, tag-synced, and stored.
        mock_lib.get_item.assert_called_once_with(7)
        assert mock_item.path == flac_path.encode()
        mock_item.write.assert_called_once()
        mock_item.read.assert_called_once()
        mock_item.store.assert_called_once()
        # Original gone, FLAC in place.
        assert not wav_path.exists()
        assert (album_dir / "01 Song.flac").exists()

    def test_keep_originals_leaves_wav_on_disk(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        wav_path = album_dir / "01 Song.wav"
        wav_path.write_bytes(b"wav-bytes")

        mock_lib = Mock()
        mock_lib.get_item.return_value = Mock()

        with patch(
            "app.services.wav_flac_service.transcode_file",
            side_effect=self._fake_transcode,
        ), patch("beets.library.Library", return_value=mock_lib):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[(self._track(7), str(wav_path))],
                delete_originals=False,
                file_perm=None,
            )

        assert result.converted == 1
        assert result.deleted == 0
        assert wav_path.exists()

    def test_existing_flac_twin_is_skipped_untouched(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        wav_path = album_dir / "01 Song.wav"
        wav_path.write_bytes(b"wav-bytes")
        (album_dir / "01 Song.flac").write_bytes(b"pre-existing")

        mock_lib = Mock()

        with patch(
            "app.services.wav_flac_service.transcode_file"
        ) as mock_transcode, patch("beets.library.Library", return_value=mock_lib):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[(self._track(7), str(wav_path))],
                delete_originals=True,
                file_perm=None,
            )

        assert result.skipped == 1
        assert result.converted == 0
        mock_transcode.assert_not_called()
        mock_lib.get_item.assert_not_called()
        # Neither file was touched.
        assert wav_path.exists()
        assert (album_dir / "01 Song.flac").read_bytes() == b"pre-existing"

    def test_transcode_failure_keeps_wav_and_db_row(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        wav_path = album_dir / "01 Song.wav"
        wav_path.write_bytes(b"wav-bytes")

        mock_lib = Mock()

        with patch(
            "app.services.wav_flac_service.transcode_file",
            side_effect=RuntimeError("ffmpeg exploded"),
        ), patch("beets.library.Library", return_value=mock_lib):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[(self._track(7), str(wav_path))],
                delete_originals=True,
                file_perm=None,
            )

        assert result.failed == 1
        assert result.converted == 0
        assert result.failures[0]["file"] == str(wav_path)
        mock_lib.get_item.assert_not_called()
        assert wav_path.exists()

    def test_db_failure_removes_orphan_flac_and_keeps_wav(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        wav_path = album_dir / "01 Song.wav"
        wav_path.write_bytes(b"wav-bytes")

        mock_lib = Mock()
        mock_lib.get_item.return_value = None  # item vanished from the DB

        with patch(
            "app.services.wav_flac_service.transcode_file",
            side_effect=self._fake_transcode,
        ), patch("beets.library.Library", return_value=mock_lib):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[(self._track(7), str(wav_path))],
                delete_originals=True,
                file_perm=None,
            )

        assert result.failed == 1
        assert result.converted == 0
        # The orphan FLAC was cleaned up so disk matches the untouched DB row.
        assert not (album_dir / "01 Song.flac").exists()
        assert wav_path.exists()

    def test_tag_sync_failure_falls_back_to_audio_props(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        wav_path = album_dir / "01 Song.wav"
        wav_path.write_bytes(b"wav-bytes")

        mock_item = MagicMock()
        mock_item.write.side_effect = RuntimeError("unwritable tag")
        mock_lib = Mock()
        mock_lib.get_item.return_value = mock_item

        mock_mediafile = Mock()
        mock_mediafile.format = "FLAC"
        mock_mediafile.bitrate = 900000
        mock_mediafile.bitdepth = 16
        mock_mediafile.samplerate = 44100
        mock_mediafile.channels = 2
        mock_mediafile.length = 123.4

        with patch(
            "app.services.wav_flac_service.transcode_file",
            side_effect=self._fake_transcode,
        ), patch("beets.library.Library", return_value=mock_lib), patch(
            "mediafile.MediaFile", return_value=mock_mediafile
        ):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[(self._track(7), str(wav_path))],
                delete_originals=True,
                file_perm=None,
            )

        # A tag-sync failure is not fatal: the item is still repointed and the
        # stream facts are refreshed from the file directly.
        assert result.converted == 1
        assert result.failed == 0
        mock_item.read.assert_not_called()
        mock_item.__setitem__.assert_any_call("format", "FLAC")
        mock_item.__setitem__.assert_any_call("bitrate", 900000)
        mock_item.store.assert_called_once()
        assert not wav_path.exists()

    def test_one_bad_track_does_not_abort_the_album(self, library, album_dir):
        from app.tasks.beets_tasks import _convert_imported_wav_items

        good_wav = album_dir / "01 Good.wav"
        bad_wav = album_dir / "02 Bad.wav"
        good_wav.write_bytes(b"wav-bytes")
        bad_wav.write_bytes(b"wav-bytes")

        def flaky_transcode(src_path, target_path, **kwargs):
            if "Bad" in src_path:
                raise RuntimeError("corrupt input")
            self._fake_transcode(src_path, target_path, **kwargs)

        mock_lib = Mock()
        mock_lib.get_item.return_value = Mock()

        with patch(
            "app.services.wav_flac_service.transcode_file",
            side_effect=flaky_transcode,
        ), patch("beets.library.Library", return_value=mock_lib):
            result = _convert_imported_wav_items(
                library=library,
                wav_items=[
                    (self._track(1), str(good_wav)),
                    (self._track(2), str(bad_wav)),
                ],
                delete_originals=True,
                file_perm=None,
            )

        assert result.converted == 1
        assert result.failed == 1
        assert not good_wav.exists()
        assert bad_wav.exists()
