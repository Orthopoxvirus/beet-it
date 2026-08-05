"""Unit tests for EmbyConnectionService.refresh_library.

The refresh is a best-effort post-import side effect (it replaced the
``embyupdate`` beets plugin). The contract under test: it triggers
``POST /emby/Library/Refresh`` with ``X-Emby-Token`` auth, maps every
transport failure to ``success=False`` and **never raises** — an unreachable
Emby must not be able to crash an import.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.emby_service import EmbyConnectionService


def _client_cm(response=None, exc=None):
    """Build a mock that stands in for ``httpx.AsyncClient(...)``.

    Returns an object usable as an async context manager whose ``post`` either
    yields ``response`` or raises ``exc``.
    """
    client = AsyncMock()
    if exc is not None:
        client.post.side_effect = exc
    else:
        client.post.return_value = response

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def _run_refresh(cm, host="emby.local", port=8096, apikey="secret"):
    with patch("app.services.emby_service.httpx.AsyncClient", return_value=cm):
        service = EmbyConnectionService(timeout=5.0)
        return asyncio.run(service.refresh_library(host=host, port=port, apikey=apikey))


class TestEmbyRefreshLibrary:
    @pytest.mark.parametrize("status_code", [200, 204])
    def test_success_status_codes(self, status_code):
        cm, client = _client_cm(response=MagicMock(status_code=status_code))
        result = _run_refresh(cm)

        assert result.success is True
        assert result.skipped is False
        # Correct endpoint + auth header.
        client.post.assert_awaited_once()
        url = client.post.call_args[0][0]
        headers = client.post.call_args.kwargs["headers"]
        assert url == "http://emby.local:8096/emby/Library/Refresh"
        assert headers["X-Emby-Token"] == "secret"

    def test_missing_host_is_skipped_not_called(self):
        cm, client = _client_cm(response=MagicMock(status_code=204))
        result = _run_refresh(cm, host="")

        assert result.skipped is True
        assert result.success is False
        client.post.assert_not_called()

    def test_missing_apikey_is_skipped_not_called(self):
        cm, client = _client_cm(response=MagicMock(status_code=204))
        result = _run_refresh(cm, apikey="")

        assert result.skipped is True
        assert result.success is False
        client.post.assert_not_called()

    def test_401_is_failure(self):
        cm, _ = _client_cm(response=MagicMock(status_code=401))
        result = _run_refresh(cm)

        assert result.success is False
        assert result.skipped is False
        assert "Authentication failed" in result.message

    def test_unexpected_status_is_failure(self):
        cm, _ = _client_cm(response=MagicMock(status_code=500))
        result = _run_refresh(cm)

        assert result.success is False
        assert "500" in result.message

    def test_connect_timeout_is_soft_failure(self):
        cm, _ = _client_cm(exc=httpx.ConnectTimeout("timed out"))
        result = _run_refresh(cm)  # must not raise

        assert result.success is False
        assert result.skipped is False
        assert "timed out" in result.message.lower()

    def test_connect_error_is_soft_failure(self):
        cm, _ = _client_cm(exc=httpx.ConnectError("refused"))
        result = _run_refresh(cm)

        assert result.success is False
        assert "refused" in result.message.lower()

    def test_request_error_is_soft_failure(self):
        cm, _ = _client_cm(exc=httpx.RequestError("boom"))
        result = _run_refresh(cm)

        assert result.success is False
