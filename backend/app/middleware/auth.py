"""Basic Authentication middleware for protecting all endpoints."""

import base64
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """
    HTTP Basic Authentication middleware.

    When both username and password are configured, all requests must include
    valid Basic Auth credentials. When either is empty, authentication is disabled.
    """

    WWW_AUTHENTICATE_HEADER = 'Basic realm="Beets Manager"'

    def __init__(self, app, username: str | None, password: str | None):
        """
        Initialize the middleware.

        Args:
            app: The ASGI application
            username: Expected username (or None to disable auth)
            password: Expected password (or None to disable auth)
        """
        super().__init__(app)
        self.username = username
        self.password = password
        self.auth_enabled = bool(username and password)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request and check authentication if enabled.

        Args:
            request: The incoming request
            call_next: The next middleware/route handler

        Returns:
            Response: Either the actual response or a 401 Unauthorized response
        """
        # If auth is disabled, pass request through
        if not self.auth_enabled:
            return await call_next(request)

        # Get Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return self._unauthorized_response()

        # Validate the auth header format and credentials
        if not self._validate_credentials(auth_header):
            return self._unauthorized_response()

        # Credentials valid, continue to the route handler
        return await call_next(request)

    def _validate_credentials(self, auth_header: str) -> bool:
        """
        Validate the Authorization header credentials.

        Args:
            auth_header: The Authorization header value

        Returns:
            bool: True if credentials are valid, False otherwise
        """
        # Check for Basic auth scheme
        if not auth_header.startswith("Basic "):
            return False

        try:
            # Decode Base64 credentials
            encoded_credentials = auth_header[6:]  # Remove "Basic " prefix
            decoded_bytes = base64.b64decode(encoded_credentials)
            decoded_str = decoded_bytes.decode("utf-8")

            # Split into username:password
            if ":" not in decoded_str:
                return False

            provided_username, provided_password = decoded_str.split(":", 1)

            # Use timing-safe comparison to prevent timing attacks
            username_valid = secrets.compare_digest(
                provided_username.encode("utf-8"),
                self.username.encode("utf-8")
            )
            password_valid = secrets.compare_digest(
                provided_password.encode("utf-8"),
                self.password.encode("utf-8")
            )

            return username_valid and password_valid

        except (ValueError, UnicodeDecodeError, base64.binascii.Error):
            return False

    def _unauthorized_response(self) -> Response:
        """
        Create a 401 Unauthorized response with WWW-Authenticate header.

        Returns:
            Response: A 401 response that triggers browser's auth dialog
        """
        return Response(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": self.WWW_AUTHENTICATE_HEADER},
            media_type="text/plain",
        )
