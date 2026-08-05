"""Regex transformer implementation with timeout protection.

This module provides regex transformation capabilities with protection against
ReDoS (Regular Expression Denial of Service) attacks through signal-based
timeout on Unix systems (in main thread) or thread-based timeout in worker
threads (e.g., FastAPI handlers, Celery workers).
"""

import concurrent.futures
import logging
import os
import re
import signal
import sys
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default regex timeout in milliseconds
DEFAULT_REGEX_TIMEOUT_MS = 100

# Check if we're on a Unix system that supports SIGALRM
_SUPPORTS_SIGALRM = hasattr(signal, "SIGALRM") and sys.platform != "win32"


def _is_main_thread() -> bool:
    """Check if currently running in the main thread.

    Returns:
        True if running in the main thread, False otherwise.
    """
    return threading.current_thread() is threading.main_thread()


class RegexTimeoutError(Exception):
    """Raised when a regex operation times out."""

    pass


class RegexPatternError(Exception):
    """Raised when a regex pattern is invalid."""

    pass


@dataclass
class RegexTransformResult:
    """Result of a regex transformation."""

    success: bool
    value: Optional[str]
    error: Optional[str] = None
    warning: Optional[str] = None
    warning_code: Optional[str] = None


def _timeout_handler(signum, frame):
    """Signal handler for regex timeout."""
    raise RegexTimeoutError("Regex execution timed out")


class RegexTransformer:
    """Transformer that applies regex pattern matching with capture group substitution.

    This transformer extracts a value from a source field using a regex pattern,
    then constructs a replacement value using capture group substitution.

    The replacement template uses $1, $2, etc. for numbered capture groups,
    and $0 for the entire match.
    """

    def __init__(
        self,
        source_field: str,
        pattern: str,
        replacement: str,
        timeout_ms: int = DEFAULT_REGEX_TIMEOUT_MS,
    ):
        """Initialize the regex transformer.

        Args:
            source_field: Name of the field to apply the pattern to.
            pattern: Python-compatible regex pattern.
            replacement: Replacement template with capture groups ($1, $2, etc.).
            timeout_ms: Timeout for regex execution in milliseconds.

        Raises:
            RegexPatternError: If the pattern is invalid.
        """
        self.source_field = source_field
        self.pattern_str = pattern
        self.replacement = replacement
        self.timeout_ms = timeout_ms

        # Compile the pattern to validate it
        try:
            self.pattern = re.compile(pattern)
        except re.error as e:
            raise RegexPatternError(f"Invalid regex pattern: {e}")

    def _apply_replacement(self, match: re.Match) -> str:
        """Apply the replacement template to a match.

        Substitutes $0 with the entire match, $1 with group 1, etc.

        Args:
            match: The regex match object.

        Returns:
            The replacement string with groups substituted.
        """
        result = self.replacement

        # Replace $0 with the entire match
        result = result.replace("$0", match.group(0))

        # Replace $1, $2, etc. with capture groups
        for i, group in enumerate(match.groups(), start=1):
            placeholder = f"${i}"
            if group is not None:
                result = result.replace(placeholder, group)
            else:
                result = result.replace(placeholder, "")

        return result

    def transform(self, item: Dict[str, Any]) -> RegexTransformResult:
        """Transform an item by applying the regex pattern.

        Args:
            item: The import item data containing the source field.

        Returns:
            RegexTransformResult with the transformed value or error/warning.
        """
        # Get the source field value
        source_value = item.get(self.source_field)

        # Handle empty/missing source
        if source_value is None or source_value == "":
            return RegexTransformResult(
                success=True,
                value=None,
                warning="Source field value is empty or null",
                warning_code="EMPTY_SOURCE",
            )

        # Convert to string if necessary
        source_value = str(source_value)

        try:
            # Apply regex with timeout protection
            match = self._execute_with_timeout(source_value)

            if match is None:
                return RegexTransformResult(
                    success=True,
                    value=None,
                    warning="Pattern did not match source field value",
                    warning_code="NO_REGEX_MATCH",
                )

            # Apply the replacement template
            result_value = self._apply_replacement(match)

            return RegexTransformResult(
                success=True,
                value=result_value,
            )

        except RegexTimeoutError:
            return RegexTransformResult(
                success=False,
                value=None,
                error="Regex execution timed out (possible ReDoS pattern)",
            )

        except Exception as e:
            logger.error(f"Unexpected error in regex transform: {e}")
            return RegexTransformResult(
                success=False,
                value=None,
                error=f"Regex transformation failed: {e}",
            )

    def _execute_with_timeout(self, source_value: str) -> Optional[re.Match]:
        """Execute regex search with timeout protection.

        Uses a hybrid approach based on execution context:
        - Main thread on Unix: Uses signal.SIGALRM (more efficient)
        - Worker threads: Uses ThreadPoolExecutor with Future.result(timeout=...)
        - Windows: No timeout protection (warning logged)

        Args:
            source_value: The string to search.

        Returns:
            The match object, or None if no match.

        Raises:
            RegexTimeoutError: If the regex execution exceeds the timeout.
        """
        if not _SUPPORTS_SIGALRM:
            # Windows or other platform without SIGALRM support
            # Execute without timeout protection but log a warning
            logger.warning(
                "Regex timeout protection not available on this platform. "
                "Running regex without timeout (potential ReDoS vulnerability)."
            )
            return self.pattern.search(source_value)

        # Choose strategy based on thread context
        if _is_main_thread():
            return self._execute_with_signal_timeout(source_value)
        else:
            logger.debug(
                "Running regex in worker thread, using thread-based timeout"
            )
            return self._execute_with_thread_timeout(source_value)

    def _execute_with_signal_timeout(self, source_value: str) -> Optional[re.Match]:
        """Execute regex with signal-based timeout (main thread only).

        Args:
            source_value: The string to search.

        Returns:
            The match object, or None if no match.

        Raises:
            RegexTimeoutError: If the regex execution exceeds the timeout.
        """
        # Convert milliseconds to seconds (minimum 1 second for signal.alarm)
        timeout_seconds = max(1, self.timeout_ms // 1000)

        # Store the old handler so we can restore it
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)

        try:
            # Set the alarm
            signal.alarm(timeout_seconds)

            # Execute the regex
            result = self.pattern.search(source_value)

            # Cancel the alarm
            signal.alarm(0)

            return result

        except RegexTimeoutError:
            # Re-raise the timeout error
            raise

        finally:
            # Always restore the old handler and cancel any pending alarm
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def _execute_with_thread_timeout(self, source_value: str) -> Optional[re.Match]:
        """Execute regex with thread-based timeout (for worker threads).

        Uses a ThreadPoolExecutor to run the regex in a separate daemon thread,
        allowing timeout even when not in the main thread.

        Supports millisecond precision timeout (unlike signal.alarm which only
        supports integer seconds).

        Args:
            source_value: The string to search.

        Returns:
            The match object, or None if no match.

        Raises:
            RegexTimeoutError: If the regex execution exceeds the timeout.
        """
        # Convert milliseconds to seconds for Future.result()
        # Use direct conversion for millisecond precision
        timeout_seconds = self.timeout_ms / 1000.0

        # Create a single-use executor with daemon threads
        # Using daemon threads ensures the executor won't block process exit
        # if a regex operation times out and continues running
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="regex_timeout",
        ) as executor:
            # Submit the regex search to the thread pool
            future = executor.submit(self.pattern.search, source_value)

            try:
                # Wait for the result with timeout
                return future.result(timeout=timeout_seconds)

            except concurrent.futures.TimeoutError:
                # Convert to our custom timeout error for consistent handling
                raise RegexTimeoutError("Regex execution timed out")


def validate_regex_pattern(pattern: str) -> tuple[bool, Optional[str]]:
    """Validate a regex pattern.

    Args:
        pattern: The regex pattern to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    try:
        re.compile(pattern)
        return True, None
    except re.error as e:
        return False, str(e)
