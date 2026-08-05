"""Integration tests for library API verification status."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.api.libraries import router, get_provisioning_service
from app.services.library_provisioning import (
    LibraryProvisioningService,
    LibraryPaths,
    ProvisioningResult,
    VerificationResult,
)


# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def test_app():
    """Create a test FastAPI application with test database."""
    # Create tables
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override database dependency
    app.dependency_overrides[get_db] = override_get_db

    yield app

    # Clean up
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return TestClient(test_app)


@pytest.fixture
def mock_provisioning_service():
    """Create a mock provisioning service."""
    service = MagicMock(spec=LibraryProvisioningService)
    return service


class TestCreateLibraryWithVerification:
    """Test cases for library creation with verification status."""

    def test_create_library_returns_verification_status_on_success(
        self, test_app, client, mock_provisioning_service
    ):
        """POST /libraries should return verification_status in response."""
        # Setup mock
        mock_paths = LibraryPaths(
            slug="jazz-collection",
            config_path="/config/jazz-collection.yaml",
            database_path="/data/databases/jazz-collection.db",
            library_path="/data/libraries/jazz-collection/",
            import_path="/data/import/jazz-collection/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/jazz-collection.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        response = client.post(
            "/api/v1/libraries/",
            json={"name": "Jazz Collection", "description": "My jazz music"},
        )

        assert response.status_code == 201
        data = response.json()

        # Verify verification_status is present
        assert "verification_status" in data
        assert data["verification_status"]["verified"] is True
        assert data["verification_status"]["config_path"] == "/config/jazz-collection.yaml"
        assert data["verification_status"]["error"] is None
        assert data["verification_status"]["timed_out"] is False

    def test_create_library_returns_verification_failed_status(
        self, test_app, client, mock_provisioning_service
    ):
        """POST /libraries should return failed verification status when verification fails."""
        mock_paths = LibraryPaths(
            slug="rock-collection",
            config_path="/config/rock-collection.yaml",
            database_path="/data/databases/rock-collection.db",
            library_path="/data/libraries/rock-collection/",
            import_path="/data/import/rock-collection/",
        )
        mock_verification = VerificationResult(
            success=False,
            config_path=None,
            error="configuration error: invalid YAML syntax at line 5",
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        response = client.post(
            "/api/v1/libraries/",
            json={"name": "Rock Collection"},
        )

        # Library should still be created (201)
        assert response.status_code == 201
        data = response.json()

        # Verify library was created
        assert data["name"] == "Rock Collection"
        assert data["slug"] == "rock-collection"

        # Verify verification_status shows failure
        assert data["verification_status"]["verified"] is False
        assert data["verification_status"]["config_path"] is None
        assert data["verification_status"]["error"] == "configuration error: invalid YAML syntax at line 5"
        assert data["verification_status"]["timed_out"] is False

    def test_create_library_returns_verification_timeout_status(
        self, test_app, client, mock_provisioning_service
    ):
        """POST /libraries should return timeout status when verification times out."""
        mock_paths = LibraryPaths(
            slug="classical-collection",
            config_path="/config/classical-collection.yaml",
            database_path="/data/databases/classical-collection.db",
            library_path="/data/libraries/classical-collection/",
            import_path="/data/import/classical-collection/",
        )
        mock_verification = VerificationResult(
            success=False,
            config_path=None,
            error=None,
            timed_out=True,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        response = client.post(
            "/api/v1/libraries/",
            json={"name": "Classical Collection"},
        )

        # Library should still be created (201)
        assert response.status_code == 201
        data = response.json()

        # Verify verification_status shows timeout
        assert data["verification_status"]["verified"] is False
        assert data["verification_status"]["config_path"] is None
        assert data["verification_status"]["error"] is None
        assert data["verification_status"]["timed_out"] is True

    def test_library_creation_succeeds_even_when_verification_fails(
        self, test_app, client, mock_provisioning_service
    ):
        """Library should be created successfully even when verification fails."""
        mock_paths = LibraryPaths(
            slug="failed-verify-library",
            config_path="/config/failed-verify-library.yaml",
            database_path="/data/databases/failed-verify-library.db",
            library_path="/data/libraries/failed-verify-library/",
            import_path="/data/import/failed-verify-library/",
        )
        mock_verification = VerificationResult(
            success=False,
            config_path=None,
            error="Beets executable not found",
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        response = client.post(
            "/api/v1/libraries/",
            json={"name": "Failed Verify Library"},
        )

        # Should be 201 Created, not an error
        assert response.status_code == 201
        data = response.json()

        # Library should be fully created
        assert data["id"] is not None
        assert data["name"] == "Failed Verify Library"
        assert data["slug"] == "failed-verify-library"
        assert data["config_path"] == "/config/failed-verify-library.yaml"
        assert data["database_path"] == "/data/databases/failed-verify-library.db"
        assert data["library_path"] == "/data/libraries/failed-verify-library/"
        assert data["import_path"] == "/data/import/failed-verify-library/"

        # But verification should show the failure
        assert data["verification_status"]["verified"] is False
        assert data["verification_status"]["error"] == "Beets executable not found"

    def test_get_library_has_null_verification_status(
        self, test_app, client, mock_provisioning_service
    ):
        """GET /libraries/{slug} should return null verification_status."""
        # First create a library
        mock_paths = LibraryPaths(
            slug="get-test-library",
            config_path="/config/get-test-library.yaml",
            database_path="/data/databases/get-test-library.db",
            library_path="/data/libraries/get-test-library/",
            import_path="/data/import/get-test-library/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/get-test-library.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        create_response = client.post(
            "/api/v1/libraries/",
            json={"name": "Get Test Library"},
        )
        assert create_response.status_code == 201
        library_slug = create_response.json()["slug"]

        # Now get the library by slug
        get_response = client.get(f"/api/v1/libraries/{library_slug}")
        assert get_response.status_code == 200
        data = get_response.json()

        # verification_status should be null for GET requests
        assert data["verification_status"] is None

    def test_list_libraries_has_null_verification_status(
        self, test_app, client, mock_provisioning_service
    ):
        """GET /libraries should return null verification_status for all items."""
        # Create a library
        mock_paths = LibraryPaths(
            slug="list-test-library",
            config_path="/config/list-test-library.yaml",
            database_path="/data/databases/list-test-library.db",
            library_path="/data/libraries/list-test-library/",
            import_path="/data/import/list-test-library/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/list-test-library.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        client.post(
            "/api/v1/libraries/",
            json={"name": "List Test Library"},
        )

        # List libraries
        list_response = client.get("/api/v1/libraries/")
        assert list_response.status_code == 200
        data = list_response.json()

        # All items should have null verification_status
        for item in data["items"]:
            assert item["verification_status"] is None


class TestVerificationStatusSchema:
    """Test verification status schema validation."""

    def test_verification_status_all_fields_present(
        self, test_app, client, mock_provisioning_service
    ):
        """All verification_status fields should be present in response."""
        mock_paths = LibraryPaths(
            slug="schema-test",
            config_path="/config/schema-test.yaml",
            database_path="/data/databases/schema-test.db",
            library_path="/data/libraries/schema-test/",
            import_path="/data/import/schema-test/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/schema-test.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        response = client.post(
            "/api/v1/libraries/",
            json={"name": "Schema Test"},
        )

        assert response.status_code == 201
        verification_status = response.json()["verification_status"]

        # All four fields should be present
        assert "verified" in verification_status
        assert "config_path" in verification_status
        assert "error" in verification_status
        assert "timed_out" in verification_status

        # Correct types
        assert isinstance(verification_status["verified"], bool)
        assert verification_status["config_path"] is None or isinstance(
            verification_status["config_path"], str
        )
        assert verification_status["error"] is None or isinstance(
            verification_status["error"], str
        )
        assert isinstance(verification_status["timed_out"], bool)
