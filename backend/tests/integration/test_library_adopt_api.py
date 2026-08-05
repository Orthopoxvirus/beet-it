"""Integration tests for POST /api/v1/libraries/adopt.

Adoption registers a pre-existing beets library (config + DB + directories
already on disk from a migration) without the filesystem-collision veto the
normal POST /libraries/ applies.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from app.database import get_db
from app.models.library import Library
from app.services.library_provisioning import VerificationResult


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    # No existing libraries by default — uniqueness checks pass.
    session.query.return_value.filter.return_value.first.return_value = None

    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(mock_db_session):
    return TestClient(app)


@pytest.fixture
def valid_payload():
    return {
        "name": "Rock",
        "slug": "rock",
        "description": "My existing rock collection",
        "database_path": "/data/databases/rock.db",
        "library_path": "/data/libraries/rock",
        "import_path": "/data/import/rock",
        "config_path": "/config/rock.yaml",
    }


class TestAdoptEndpoint:
    @patch("app.api.libraries.verify_library_config")
    def test_adopt_happy_path(self, mock_verify, client, mock_db_session, valid_payload):
        """Successful adoption returns 201 and the created library record."""
        mock_verify.return_value = VerificationResult(
            success=True, config_path=valid_payload["config_path"], error=None, timed_out=False
        )

        # Simulate db.refresh assigning an id + timestamps.
        def refresh(obj):
            obj.id = 42
            from datetime import datetime, timezone
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = None

        mock_db_session.refresh.side_effect = refresh

        response = client.post("/api/v1/libraries/adopt", json=valid_payload)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["name"] == "Rock"
        assert body["slug"] == "rock"
        assert body["database_path"] == "/data/databases/rock.db"
        assert body["verification_status"]["verified"] is True

        # The DB record should have been committed with the exact paths we sent.
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    @patch("app.api.libraries.verify_library_config")
    def test_adopt_path_outside_mount_is_rejected(
        self, mock_verify, client, mock_db_session, valid_payload
    ):
        """Adopting a library with a path outside the allowed mounts returns 400."""
        mock_verify.return_value = VerificationResult(
            success=True, config_path=valid_payload["config_path"], error=None, timed_out=False
        )

        valid_payload["database_path"] = "/etc/passwd"

        response = client.post("/api/v1/libraries/adopt", json=valid_payload)

        assert response.status_code == 400
        assert response.headers["X-Error-Code"] == "PATH_OUT_OF_BOUNDS"
        assert "database_path" in response.json()["detail"]
        # Must NOT have touched the DB.
        mock_db_session.add.assert_not_called()

    @patch("app.api.libraries.verify_library_config")
    def test_adopt_path_traversal_is_rejected(
        self, mock_verify, client, mock_db_session, valid_payload
    ):
        """Paths with ../ escaping the allowed mounts are normalised and rejected."""
        mock_verify.return_value = VerificationResult(
            success=True, config_path=valid_payload["config_path"], error=None, timed_out=False
        )

        valid_payload["library_path"] = "/data/libraries/../../../etc"

        response = client.post("/api/v1/libraries/adopt", json=valid_payload)
        assert response.status_code == 400
        assert response.headers["X-Error-Code"] == "PATH_OUT_OF_BOUNDS"

    @patch("app.api.libraries.verify_library_config")
    def test_adopt_with_duplicate_name_conflicts(
        self, mock_verify, client, mock_db_session, valid_payload
    ):
        """Adopting a library whose name is already taken returns 409."""
        mock_verify.return_value = VerificationResult(
            success=True, config_path=valid_payload["config_path"], error=None, timed_out=False
        )

        existing = MagicMock(spec=Library)
        existing.name = "Rock"
        # First query (by name) returns the duplicate; subsequent queries irrelevant.
        mock_db_session.query.return_value.filter.return_value.first.return_value = existing

        response = client.post("/api/v1/libraries/adopt", json=valid_payload)

        assert response.status_code == 409
        assert response.headers["X-Error-Code"] == "DUPLICATE_NAME"

    @patch("app.api.libraries.verify_library_config")
    def test_adopt_still_proceeds_when_beets_config_verification_fails(
        self, mock_verify, client, mock_db_session, valid_payload
    ):
        """If `beet config -p` fails, we still create the record so the user can fix it in the UI."""
        mock_verify.return_value = VerificationResult(
            success=False,
            config_path=valid_payload["config_path"],
            error="syntax error at line 5",
            timed_out=False,
        )

        def refresh(obj):
            obj.id = 1
            from datetime import datetime, timezone
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = None

        mock_db_session.refresh.side_effect = refresh

        response = client.post("/api/v1/libraries/adopt", json=valid_payload)

        assert response.status_code == 201
        assert response.json()["verification_status"]["verified"] is False
        assert "syntax error" in response.json()["verification_status"]["error"]
        mock_db_session.add.assert_called_once()

    def test_adopt_missing_required_field(self, client, valid_payload):
        """Schema validation: adoption requires all path fields."""
        del valid_payload["database_path"]
        response = client.post("/api/v1/libraries/adopt", json=valid_payload)
        assert response.status_code == 422

    def test_adopt_invalid_slug(self, client, valid_payload):
        """Slug must match the usual format rules."""
        valid_payload["slug"] = "Rock With Spaces"
        response = client.post("/api/v1/libraries/adopt", json=valid_payload)
        assert response.status_code == 422
