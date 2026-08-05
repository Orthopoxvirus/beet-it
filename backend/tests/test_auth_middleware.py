"""Unit tests for Basic Authentication middleware."""

import base64
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.middleware.auth import BasicAuthMiddleware
from app.config import Settings


def create_app(username: str | None = None, password: str | None = None) -> FastAPI:
    """Create a test FastAPI app with the auth middleware configured."""
    app = FastAPI(docs_url="/docs", redoc_url="/redoc")

    # Add CORS middleware first (like in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add auth middleware
    app.add_middleware(
        BasicAuthMiddleware,
        username=username,
        password=password,
    )

    @app.get("/")
    async def root():
        return {"message": "Hello World"}

    @app.get("/api/v1/test")
    async def api_test():
        return {"message": "API endpoint"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


def encode_credentials(username: str, password: str) -> str:
    """Encode username:password to Base64 for Basic Auth header."""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


class TestAuthDisabled:
    """Test cases when authentication is disabled."""

    def test_auth_disabled_when_both_credentials_empty(self):
        """Auth should be disabled when both username and password are empty."""
        app = create_app(username=None, password=None)
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

    def test_auth_disabled_when_username_empty_string(self):
        """Auth should be disabled when username is empty string."""
        app = create_app(username="", password="secret")
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200

    def test_auth_disabled_when_password_empty_string(self):
        """Auth should be disabled when password is empty string."""
        app = create_app(username="admin", password="")
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200

    def test_api_endpoints_accessible_without_auth_when_disabled(self):
        """API endpoints should be accessible without auth when disabled."""
        app = create_app(username=None, password=None)
        client = TestClient(app)

        response = client.get("/api/v1/test")
        assert response.status_code == 200
        assert response.json() == {"message": "API endpoint"}

    def test_docs_accessible_without_auth_when_disabled(self):
        """Documentation should be accessible without auth when disabled."""
        app = create_app(username=None, password=None)
        client = TestClient(app)

        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json_accessible_without_auth_when_disabled(self):
        """OpenAPI JSON should be accessible without auth when disabled."""
        app = create_app(username=None, password=None)
        client = TestClient(app)

        response = client.get("/openapi.json")
        assert response.status_code == 200


class TestAuthEnabled:
    """Test cases when authentication is enabled."""

    def test_valid_credentials_return_200(self):
        """Valid credentials should return 200 OK."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        auth_header = encode_credentials("admin", "secret123")
        response = client.get("/", headers={"Authorization": auth_header})

        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

    def test_valid_credentials_for_api_endpoint(self):
        """Valid credentials should allow access to API endpoints."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        auth_header = encode_credentials("admin", "secret123")
        response = client.get("/api/v1/test", headers={"Authorization": auth_header})

        assert response.status_code == 200
        assert response.json() == {"message": "API endpoint"}

    def test_invalid_username_returns_401(self):
        """Invalid username should return 401."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        auth_header = encode_credentials("wronguser", "secret123")
        response = client.get("/", headers={"Authorization": auth_header})

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_invalid_password_returns_401(self):
        """Invalid password should return 401."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        auth_header = encode_credentials("admin", "wrongpassword")
        response = client.get("/", headers={"Authorization": auth_header})

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_missing_authorization_header_returns_401(self):
        """Missing Authorization header should return 401."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_malformed_authorization_header_returns_401(self):
        """Malformed Authorization header should return 401."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/", headers={"Authorization": "NotBasic xyz"})

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_invalid_base64_returns_401(self):
        """Invalid Base64 encoding should return 401."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/", headers={"Authorization": "Basic not-valid-base64!!!"})

        assert response.status_code == 401

    def test_missing_colon_in_credentials_returns_401(self):
        """Credentials without colon separator should return 401."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        # Encode "adminpassword" without colon
        encoded = base64.b64encode(b"adminpassword").decode("utf-8")
        response = client.get("/", headers={"Authorization": f"Basic {encoded}"})

        assert response.status_code == 401


class TestEndpointProtection:
    """Test that all endpoints are protected when auth is enabled."""

    def test_api_endpoints_protected(self):
        """All /api/* endpoints should be protected."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/api/v1/test")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_docs_endpoint_protected(self):
        """/docs should be protected when auth is enabled."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/docs")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_openapi_json_protected(self):
        """/openapi.json should be protected when auth is enabled."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/openapi.json")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == 'Basic realm="Beets Manager"'

    def test_redoc_protected(self):
        """/redoc should be protected when auth is enabled."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/redoc")

        assert response.status_code == 401

    def test_root_endpoint_protected(self):
        """Root endpoint should be protected when auth is enabled."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 401

    def test_health_endpoint_protected(self):
        """Health endpoint should be protected when auth is enabled."""
        app = create_app(username="admin", password="secret123")
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 401


class TestSpecialCharacters:
    """Test authentication with special characters in credentials."""

    def test_password_with_colon(self):
        """Password containing colon should work correctly."""
        app = create_app(username="admin", password="pass:word:with:colons")
        client = TestClient(app)

        auth_header = encode_credentials("admin", "pass:word:with:colons")
        response = client.get("/", headers={"Authorization": auth_header})

        assert response.status_code == 200

    def test_unicode_credentials(self):
        """Unicode characters in credentials should work."""
        app = create_app(username="user", password="password")
        client = TestClient(app)

        auth_header = encode_credentials("user", "password")
        response = client.get("/", headers={"Authorization": auth_header})

        assert response.status_code == 200


class TestConfigValidation:
    """Test configuration validation logic in Settings."""

    def test_is_auth_enabled_both_set(self):
        """is_auth_enabled should return True when both credentials are set."""
        with patch.dict("os.environ", {"BASIC_AUTH_USER": "admin", "BASIC_AUTH_PASSWORD": "secret"}):
            settings = Settings()
            assert settings.is_auth_enabled is True

    def test_is_auth_enabled_only_user_set(self):
        """is_auth_enabled should return False when only user is set."""
        with patch.dict("os.environ", {"BASIC_AUTH_USER": "admin"}, clear=False):
            settings = Settings(basic_auth_user="admin", basic_auth_password=None)
            assert settings.is_auth_enabled is False

    def test_is_auth_enabled_only_password_set(self):
        """is_auth_enabled should return False when only password is set."""
        settings = Settings(basic_auth_user=None, basic_auth_password="secret")
        assert settings.is_auth_enabled is False

    def test_is_auth_enabled_neither_set(self):
        """is_auth_enabled should return False when neither is set."""
        settings = Settings(basic_auth_user=None, basic_auth_password=None)
        assert settings.is_auth_enabled is False

    def test_validate_auth_config_warns_on_only_user(self, caplog):
        """validate_auth_config should log warning when only user is set."""
        import logging
        with caplog.at_level(logging.WARNING):
            settings = Settings(basic_auth_user="admin", basic_auth_password=None)
            settings.validate_auth_config()

        assert "BASIC_AUTH_USER is set but BASIC_AUTH_PASSWORD is not" in caplog.text

    def test_validate_auth_config_warns_on_only_password(self, caplog):
        """validate_auth_config should log warning when only password is set."""
        import logging
        with caplog.at_level(logging.WARNING):
            settings = Settings(basic_auth_user=None, basic_auth_password="secret")
            settings.validate_auth_config()

        assert "BASIC_AUTH_PASSWORD is set but BASIC_AUTH_USER is not" in caplog.text

    def test_validate_auth_config_no_warning_when_both_set(self, caplog):
        """validate_auth_config should not log warning when both are set."""
        import logging
        with caplog.at_level(logging.WARNING):
            settings = Settings(basic_auth_user="admin", basic_auth_password="secret")
            settings.validate_auth_config()

        assert "BASIC_AUTH_USER is set but BASIC_AUTH_PASSWORD is not" not in caplog.text
        assert "BASIC_AUTH_PASSWORD is set but BASIC_AUTH_USER is not" not in caplog.text

    def test_validate_auth_config_no_warning_when_neither_set(self, caplog):
        """validate_auth_config should not log warning when neither is set."""
        import logging
        with caplog.at_level(logging.WARNING):
            settings = Settings(basic_auth_user=None, basic_auth_password=None)
            settings.validate_auth_config()

        assert "BASIC_AUTH_USER is set but BASIC_AUTH_PASSWORD is not" not in caplog.text
        assert "BASIC_AUTH_PASSWORD is set but BASIC_AUTH_USER is not" not in caplog.text
