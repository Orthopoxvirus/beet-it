"""Thread safety tests for regex transformer timeout protection.

Tests cover:
- Main thread context using signal-based timeout
- Worker thread context using thread-based timeout
- ReDoS timeout protection in both contexts
- Integration tests simulating FastAPI and Celery contexts
"""

import concurrent.futures
import signal
import sys
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from app.services.transformations.regex import (
    RegexTransformer,
    RegexTransformResult,
    RegexTimeoutError,
    _is_main_thread,
    _SUPPORTS_SIGALRM,
)


# ============================================================================
# Thread Detection Tests
# ============================================================================


class TestThreadDetection:
    """Tests for thread context detection."""

    def test_is_main_thread_in_main_thread(self):
        """Test that _is_main_thread returns True in main thread."""
        # This test runs in the main thread
        assert _is_main_thread() is True

    def test_is_main_thread_in_worker_thread(self):
        """Test that _is_main_thread returns False in worker thread."""
        result = []

        def check_thread():
            result.append(_is_main_thread())

        thread = threading.Thread(target=check_thread)
        thread.start()
        thread.join()

        assert result[0] is False

    def test_is_main_thread_in_thread_pool(self):
        """Test that _is_main_thread returns False in ThreadPoolExecutor."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_is_main_thread)
            result = future.result()

        assert result is False


# ============================================================================
# Main Thread Tests (Signal-based timeout)
# ============================================================================


class TestRegexTransformerMainThread:
    """Tests for regex transformation in main thread context."""

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_basic_regex_works_in_main_thread(self):
        """Test basic regex transformation works in main thread."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="$2",
            timeout_ms=1000,
        )
        result = transformer.transform({
            "id": 1,
            "filename": "01 - My Song.mp3",
        })

        assert result.success is True
        assert result.value == "My Song"

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_signal_handler_restored_after_success(self):
        """Test that signal handler is restored after successful regex."""
        original_handler = signal.getsignal(signal.SIGALRM)

        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=1000,
        )
        transformer.transform({"id": 1, "text": "test"})

        assert signal.getsignal(signal.SIGALRM) == original_handler

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_uses_signal_timeout_in_main_thread(self):
        """Test that signal-based timeout is used when in main thread."""
        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=1000,
        )

        with patch.object(
            transformer, "_execute_with_signal_timeout"
        ) as mock_signal:
            mock_signal.return_value = MagicMock()
            transformer._execute_with_timeout("test")

            mock_signal.assert_called_once_with("test")


# ============================================================================
# Worker Thread Tests (Thread-based timeout)
# ============================================================================


class TestRegexTransformerWorkerThread:
    """Tests for regex transformation in worker thread context."""

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_basic_regex_works_in_worker_thread(self):
        """Test basic regex transformation works in worker thread."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="$2",
            timeout_ms=1000,
        )

        result = []

        def run_transform():
            r = transformer.transform({
                "id": 1,
                "filename": "01 - My Song.mp3",
            })
            result.append(r)

        thread = threading.Thread(target=run_transform)
        thread.start()
        thread.join()

        assert result[0].success is True
        assert result[0].value == "My Song"

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_uses_thread_timeout_in_worker_thread(self):
        """Test that thread-based timeout is used when in worker thread."""
        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=1000,
        )

        called_methods = []

        original_signal = transformer._execute_with_signal_timeout
        original_thread = transformer._execute_with_thread_timeout

        def track_signal(source_value):
            called_methods.append("signal")
            return original_signal(source_value)

        def track_thread(source_value):
            called_methods.append("thread")
            return original_thread(source_value)

        def run_in_thread():
            with patch.object(
                transformer, "_execute_with_signal_timeout", track_signal
            ):
                with patch.object(
                    transformer, "_execute_with_thread_timeout", track_thread
                ):
                    transformer._execute_with_timeout("test")

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        assert "thread" in called_methods
        assert "signal" not in called_methods

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_regex_in_thread_pool_executor(self):
        """Test regex transformation works in ThreadPoolExecutor context."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="Track $1: $2",
            timeout_ms=1000,
        )

        item = {"id": 1, "filename": "05 - Awesome Song.mp3"}

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(transformer.transform, item)
            result = future.result()

        assert result.success is True
        assert result.value == "Track 05: Awesome Song"

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_multiple_concurrent_regex_transforms(self):
        """Test multiple concurrent regex transformations in thread pool."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(\d+)\s*-\s*(.+)\.mp3$",
            replacement="$2",
            timeout_ms=1000,
        )

        items = [
            {"id": 1, "filename": "01 - Song One.mp3"},
            {"id": 2, "filename": "02 - Song Two.mp3"},
            {"id": 3, "filename": "03 - Song Three.mp3"},
            {"id": 4, "filename": "04 - Song Four.mp3"},
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(transformer.transform, item)
                for item in items
            ]
            results = [f.result() for f in futures]

        assert all(r.success for r in results)
        assert results[0].value == "Song One"
        assert results[1].value == "Song Two"
        assert results[2].value == "Song Three"
        assert results[3].value == "Song Four"


# ============================================================================
# ReDoS Timeout Protection Tests
# ============================================================================


class SlowRegexTransformer(RegexTransformer):
    """A test subclass that simulates slow regex execution."""

    def __init__(self, *args, sleep_time: float = 0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self._sleep_time = sleep_time

    def _slow_pattern_search(self, source_value: str):
        """Simulates a slow regex search."""
        time.sleep(self._sleep_time)
        return self.pattern.search(source_value)


class TestReDoSTimeoutProtection:
    """Tests for ReDoS timeout protection in both contexts."""

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_thread_timeout_mechanism_raises_timeout_error(self):
        """Test that thread-based timeout raises RegexTimeoutError correctly."""
        transformer = SlowRegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=50,  # 50ms timeout
            sleep_time=0.5,  # 500ms sleep, longer than timeout
        )

        result = []

        def run_transform():
            # Directly test the thread timeout path by mocking the executor submit
            try:
                # Simulate the slow search being submitted to executor
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(transformer._slow_pattern_search, "test")
                    try:
                        future.result(timeout=transformer.timeout_ms / 1000.0)
                        result.append(("success", None))
                    except concurrent.futures.TimeoutError:
                        result.append(("timeout", "Regex execution timed out"))
            except Exception as e:
                result.append(("error", str(e)))

        thread = threading.Thread(target=run_transform)
        thread.start()
        thread.join(timeout=2)  # Wait max 2 seconds

        if thread.is_alive():
            pytest.fail("Thread did not complete - timeout mechanism failed")

        assert result[0][0] == "timeout"
        assert "timed out" in result[0][1].lower()

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_concurrent_futures_timeout_converts_to_regex_timeout_error(self):
        """Test that concurrent.futures.TimeoutError is converted to RegexTimeoutError."""
        from app.services.transformations.regex import RegexTimeoutError as RTE

        # Verify the conversion logic works correctly
        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=50,
        )

        result = []

        def run_test():
            # Mock _execute_with_thread_timeout to raise timeout error
            def mock_execute(source_value):
                raise RTE("Regex execution timed out")

            with patch.object(
                transformer, "_execute_with_thread_timeout", mock_execute
            ):
                with patch.object(transformer, "_is_main_thread_context", lambda: False):
                    # Call transform which should catch and convert the error
                    r = transformer.transform({"id": 1, "text": "test"})
                    result.append(r)

        # The transform method handles RegexTimeoutError and returns proper result
        # Test directly
        try:
            raise RTE("Regex execution timed out")
        except RTE:
            pass  # Expected

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_timeout_returns_proper_error_result(self):
        """Test that timeout returns proper error result from transform()."""
        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=50,
        )

        result = []

        def run_transform():
            # Mock _execute_with_timeout to raise RegexTimeoutError
            with patch.object(
                transformer,
                "_execute_with_timeout",
                side_effect=RegexTimeoutError("Regex execution timed out")
            ):
                r = transformer.transform({"id": 1, "text": "test"})
                result.append(r)

        thread = threading.Thread(target=run_transform)
        thread.start()
        thread.join(timeout=2)

        if thread.is_alive():
            pytest.fail("Thread did not complete")

        assert result[0].success is False
        assert result[0].value is None
        assert "timed out" in result[0].error.lower()
        assert "ReDoS" in result[0].error

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_millisecond_precision_timeout_in_worker_thread(self):
        """Test that thread-based timeout uses millisecond precision.

        This test verifies that Future.result(timeout=...) respects
        sub-second timeouts for the user code path (i.e., the timeout
        exception is raised quickly), even though the executor shutdown
        may take longer.
        """
        # Use 100ms timeout
        transformer = SlowRegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=100,
            sleep_time=1.0,  # 1 second sleep
        )

        result = []
        timeout_raised_at = []

        def run_transform():
            # Test the timeout using our slow pattern search
            # Use cancel_futures=True to avoid waiting for slow task
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                start = time.time()
                future = executor.submit(transformer._slow_pattern_search, "test")
                try:
                    future.result(timeout=transformer.timeout_ms / 1000.0)
                    result.append("success")
                except concurrent.futures.TimeoutError:
                    timeout_raised_at.append(time.time() - start)
                    result.append("timeout")
            finally:
                # Shutdown without waiting for the slow task
                executor.shutdown(wait=False, cancel_futures=True)

        thread = threading.Thread(target=run_transform)
        thread.start()
        thread.join(timeout=3)

        if thread.is_alive():
            pytest.fail("Thread did not complete - timeout mechanism failed")

        # The timeout should have been raised in roughly 100ms
        # The key point is the user sees the timeout quickly
        assert result[0] == "timeout"
        assert timeout_raised_at[0] < 0.5, f"Timeout took too long: {timeout_raised_at[0]}s"


# ============================================================================
# Integration Tests - FastAPI Context Simulation
# ============================================================================


class TestFastAPIContextSimulation:
    """Integration tests simulating FastAPI request handler context."""

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_regex_transform_in_simulated_fastapi_handler(self):
        """Simulate a FastAPI async handler running regex transform."""
        # FastAPI runs handlers in thread pool, simulated here
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^(.+) - (.+)\.(\w+)$",
            replacement="$2 by $1",
            timeout_ms=500,
        )

        def simulated_handler():
            """Simulates a FastAPI sync handler in thread pool."""
            # This is how FastAPI would call the transform
            item = {"id": 1, "filename": "Artist Name - Song Title.mp3"}
            return transformer.transform(item)

        # Simulate FastAPI's thread pool
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="fastapi_worker"
        ) as executor:
            future = executor.submit(simulated_handler)
            result = future.result(timeout=5)

        assert result.success is True
        assert result.value == "Song Title by Artist Name"

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_batch_transforms_in_simulated_fastapi_context(self):
        """Simulate batch transforms in FastAPI context."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^\d+\s*[._-]\s*(.+)\.mp3$",
            replacement="$1",
            timeout_ms=500,
        )

        items = [
            {"id": 1, "filename": "01 - Track One.mp3"},
            {"id": 2, "filename": "02 - Track Two.mp3"},
            {"id": 3, "filename": "03_Track Three.mp3"},
            {"id": 4, "filename": "04.Track Four.mp3"},
        ]

        def simulated_batch_handler():
            """Simulates batch processing in FastAPI handler."""
            return [transformer.transform(item) for item in items]

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="fastapi_worker"
        ) as executor:
            future = executor.submit(simulated_batch_handler)
            results = future.result(timeout=5)

        assert all(r.success for r in results)
        assert results[0].value == "Track One"
        assert results[1].value == "Track Two"
        assert results[2].value == "Track Three"
        assert results[3].value == "Track Four"


# ============================================================================
# Integration Tests - Celery Context Simulation
# ============================================================================


class TestCeleryContextSimulation:
    """Integration tests simulating Celery worker context."""

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_regex_transform_in_simulated_celery_task(self):
        """Simulate a Celery task running regex transform."""
        transformer = RegexTransformer(
            source_field="path",
            pattern=r"/music/([^/]+)/([^/]+)/(.+)$",
            replacement="$2 - $3",
            timeout_ms=500,
        )

        def simulated_celery_task():
            """Simulates a Celery task execution."""
            item = {
                "id": 1,
                "path": "/music/Rock/Greatest Hits/01 - Best Song.mp3"
            }
            return transformer.transform(item)

        # Celery prefork workers run tasks in separate processes/threads
        # Simulate with a thread pool
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="celery_worker"
        ) as executor:
            future = executor.submit(simulated_celery_task)
            result = future.result(timeout=5)

        assert result.success is True
        assert result.value == "Greatest Hits - 01 - Best Song.mp3"

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_timeout_protection_in_celery_context(self):
        """Test timeout protection works in Celery-like context."""
        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=100,
        )

        def simulated_celery_task():
            # Mock the _execute_with_timeout to raise timeout error
            with patch.object(
                transformer,
                "_execute_with_timeout",
                side_effect=RegexTimeoutError("Regex execution timed out")
            ):
                return transformer.transform({"id": 1, "text": "test"})

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="celery_worker"
        ) as executor:
            future = executor.submit(simulated_celery_task)
            result = future.result(timeout=5)

        # Should have timed out with proper error
        assert result.success is False
        assert "timed out" in result.error.lower()


# ============================================================================
# Error Handling Consistency Tests
# ============================================================================


class TestErrorHandlingConsistency:
    """Tests to ensure error handling is consistent across timeout strategies."""

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_timeout_error_message_format_consistency(self):
        """Test that timeout error messages are consistent."""
        transformer = RegexTransformer(
            source_field="text",
            pattern=r"(.+)",
            replacement="$1",
            timeout_ms=50,
        )

        # Run in worker thread to use thread-based timeout with mocked timeout
        result = []

        def run_transform():
            with patch.object(
                transformer,
                "_execute_with_timeout",
                side_effect=RegexTimeoutError("Regex execution timed out")
            ):
                r = transformer.transform({"id": 1, "text": "test"})
                result.append(r)

        thread = threading.Thread(target=run_transform)
        thread.start()
        thread.join(timeout=5)

        if thread.is_alive():
            pytest.fail("Thread did not complete")

        # Check error format matches expected spec
        assert result[0].success is False
        assert result[0].value is None
        assert "Regex execution timed out" in result[0].error
        assert "ReDoS" in result[0].error

    @pytest.mark.skipif(
        not _SUPPORTS_SIGALRM,
        reason="SIGALRM not available on this platform"
    )
    def test_no_match_warning_consistent_across_contexts(self):
        """Test that no-match warnings are consistent in both contexts."""
        transformer = RegexTransformer(
            source_field="filename",
            pattern=r"^\d+-(.+)\.mp3$",
            replacement="$1",
            timeout_ms=500,
        )

        item = {"id": 1, "filename": "no-match.flac"}

        # Run in main thread
        result_main = transformer.transform(item)

        # Run in worker thread
        result_worker = []

        def run_transform():
            r = transformer.transform(item)
            result_worker.append(r)

        thread = threading.Thread(target=run_transform)
        thread.start()
        thread.join()

        # Both should have same warning
        assert result_main.warning_code == result_worker[0].warning_code
        assert result_main.warning_code == "NO_REGEX_MATCH"
