"""Service for testing Emby server connectivity."""

import logging
from typing import Optional

import httpx

from app.schemas.beets_config import EmbyRefreshResponse, EmbyTestResponse

logger = logging.getLogger(__name__)


class EmbyConnectionService:
    """Service for testing Emby server connections.

    This service validates Emby server connectivity and authentication
    by making API requests to the server.
    """

    def __init__(self, timeout: float = 10.0):
        """Initialize the Emby connection service.

        Args:
            timeout: Request timeout in seconds.
        """
        self.timeout = timeout

    async def test_connection(
        self, host: str, port: int, userid: str, apikey: str
    ) -> EmbyTestResponse:
        """Test the connection to an Emby server.

        Makes a request to the Emby server's System/Info endpoint to verify
        connectivity and authentication.

        Args:
            host: Emby server hostname or IP address.
            port: Emby server port.
            userid: Emby user ID.
            apikey: Emby API key.

        Returns:
            EmbyTestResponse with connection status and server info.
        """
        # Validate inputs
        if not host:
            return EmbyTestResponse(
                success=False,
                message="Host is required",
            )

        if not apikey:
            return EmbyTestResponse(
                success=False,
                message="API key is required",
            )

        # Build the base URL
        # Try HTTPS first, fallback to HTTP if needed
        base_url = f"http://{host}:{port}"

        # Emby API endpoint for system info
        endpoint = f"{base_url}/emby/System/Info"

        # Headers for Emby authentication
        headers = {
            "X-Emby-Token": apikey,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint, headers=headers)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        server_name = data.get("ServerName", "Unknown")
                        server_version = data.get("Version", "Unknown")

                        return EmbyTestResponse(
                            success=True,
                            message="Successfully connected to Emby server",
                            server_name=server_name,
                            server_version=server_version,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse Emby response: {e}")
                        return EmbyTestResponse(
                            success=True,
                            message="Connected to server but could not parse response",
                        )

                elif response.status_code == 401:
                    return EmbyTestResponse(
                        success=False,
                        message="Authentication failed: Invalid API key",
                    )

                elif response.status_code == 403:
                    return EmbyTestResponse(
                        success=False,
                        message="Access forbidden: Check API key permissions",
                    )

                else:
                    return EmbyTestResponse(
                        success=False,
                        message=f"Server returned unexpected status code: {response.status_code}",
                    )

        except httpx.ConnectTimeout:
            return EmbyTestResponse(
                success=False,
                message=f"Connection timed out: Unable to reach server at {host}:{port}",
            )

        except httpx.ConnectError as e:
            return EmbyTestResponse(
                success=False,
                message=f"Connection refused: Unable to reach server at {host}:{port}",
            )

        except httpx.RequestError as e:
            logger.error(f"Request error testing Emby connection: {e}")
            return EmbyTestResponse(
                success=False,
                message=f"Connection error: {str(e)}",
            )

        except Exception as e:
            logger.error(f"Unexpected error testing Emby connection: {e}")
            return EmbyTestResponse(
                success=False,
                message=f"Unexpected error: {str(e)}",
            )

    async def refresh_library(
        self, host: str, port: int, apikey: str
    ) -> EmbyRefreshResponse:
        """Trigger an Emby library scan via ``POST /Library/Refresh``.

        Used as a post-import side effect to replace the third-party
        ``embyupdate`` beets plugin: same ``X-Emby-Token`` auth and the same
        bounded-timeout / mapped-exception handling as :meth:`test_connection`,
        so an unreachable Emby returns ``success=False`` instead of letting a
        ``ConnectTimeout`` traceback propagate into the import.

        Args:
            host: Emby server hostname or IP address.
            port: Emby server port.
            apikey: Emby API key.

        Returns:
            EmbyRefreshResponse — ``skipped=True`` when Emby is not configured,
            ``success=True`` when the refresh was accepted, otherwise
            ``success=False`` with a human-readable message. Never raises.
        """
        # Not configured — nothing to refresh, and not an error.
        if not host:
            return EmbyRefreshResponse(
                success=False, skipped=True, message="Emby host not configured"
            )
        if not apikey:
            return EmbyRefreshResponse(
                success=False, skipped=True, message="Emby API key not configured"
            )

        base_url = f"http://{host}:{port}"
        endpoint = f"{base_url}/emby/Library/Refresh"
        headers = {
            "X-Emby-Token": apikey,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, headers=headers)

            # Emby answers a refresh with 204 No Content (200 on some builds).
            if response.status_code in (200, 204):
                return EmbyRefreshResponse(
                    success=True, message="Emby library refresh triggered"
                )
            elif response.status_code == 401:
                return EmbyRefreshResponse(
                    success=False,
                    message="Authentication failed: Invalid API key",
                )
            elif response.status_code == 403:
                return EmbyRefreshResponse(
                    success=False,
                    message="Access forbidden: Check API key permissions",
                )
            else:
                return EmbyRefreshResponse(
                    success=False,
                    message=f"Server returned unexpected status code: {response.status_code}",
                )

        except httpx.ConnectTimeout:
            return EmbyRefreshResponse(
                success=False,
                message=f"Connection timed out: Unable to reach server at {host}:{port}",
            )

        except httpx.ConnectError:
            return EmbyRefreshResponse(
                success=False,
                message=f"Connection refused: Unable to reach server at {host}:{port}",
            )

        except httpx.RequestError as e:
            logger.warning(f"Request error during Emby library refresh: {e}")
            return EmbyRefreshResponse(
                success=False,
                message=f"Connection error: {str(e)}",
            )

        except Exception as e:
            logger.warning(f"Unexpected error during Emby library refresh: {e}")
            return EmbyRefreshResponse(
                success=False,
                message=f"Unexpected error: {str(e)}",
            )
