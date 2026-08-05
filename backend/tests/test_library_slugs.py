"""Tests for library slug functionality."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.api.libraries import router, get_provisioning_service
from app.schemas.library import (
    LibraryCreate,
    LibraryUpdate,
    validate_slug_format,
    SLUG_PATTERN,
    SLUG_REGEX,
)
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


class TestSlugValidation:
    """Test cases for slug format validation."""

    def test_valid_simple_slug(self):
        """Valid simple slug should pass."""
        assert validate_slug_format("my-library") == "my-library"

    def test_valid_slug_with_numbers(self):
        """Valid slug with numbers should pass."""
        assert validate_slug_format("jazz-2024") == "jazz-2024"

    def test_valid_slug_single_word(self):
        """Valid single-word slug should pass."""
        assert validate_slug_format("rock") == "rock"

    def test_valid_slug_numbers_only(self):
        """Valid slug with numbers only should pass."""
        assert validate_slug_format("123") == "123"

    def test_valid_alphanumeric_mix(self):
        """Valid alphanumeric mix should pass."""
        assert validate_slug_format("a1b2c3") == "a1b2c3"

    def test_invalid_uppercase(self):
        """Uppercase letters should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("My-Library")

    def test_invalid_spaces(self):
        """Spaces should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("my library")

    def test_invalid_underscores(self):
        """Underscores should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("my_library")

    def test_invalid_leading_hyphen(self):
        """Leading hyphen should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("-my-library")

    def test_invalid_trailing_hyphen(self):
        """Trailing hyphen should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("my-library-")

    def test_invalid_consecutive_hyphens(self):
        """Consecutive hyphens should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("my--library")

    def test_invalid_special_characters(self):
        """Special characters should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("my-library!")

    def test_empty_slug(self):
        """Empty slug should fail."""
        with pytest.raises(ValueError):
            validate_slug_format("")

    def test_slug_regex_pattern(self):
        """SLUG_REGEX should match valid slugs."""
        assert SLUG_REGEX.match("my-library")
        assert SLUG_REGEX.match("jazz-2024")
        assert SLUG_REGEX.match("rock")
        assert not SLUG_REGEX.match("My-Library")
        assert not SLUG_REGEX.match("-my-library")
        assert not SLUG_REGEX.match("my--library")


class TestSlugBasedRoutes:
    """Test cases for slug-based API routes."""

    def test_get_library_by_slug(self, test_app, client, mock_provisioning_service):
        """GET /libraries/{slug} should return library by slug."""
        # Create a library first
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

        # Create library
        create_response = client.post(
            "/api/v1/libraries/",
            json={"name": "Jazz Collection"},
        )
        assert create_response.status_code == 201

        # Get library by slug
        get_response = client.get("/api/v1/libraries/jazz-collection")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["name"] == "Jazz Collection"
        assert data["slug"] == "jazz-collection"

    def test_get_library_by_invalid_slug_returns_404(self, test_app, client):
        """GET /libraries/{slug} should return 404 for non-existent slug."""
        response = client.get("/api/v1/libraries/nonexistent-library")
        assert response.status_code == 404
        assert response.json()["detail"] == "Library not found"

    def test_update_library_by_slug(self, test_app, client, mock_provisioning_service):
        """PUT /libraries/{slug} should update library found by slug."""
        # Create a library first
        mock_paths = LibraryPaths(
            slug="update-test",
            config_path="/config/update-test.yaml",
            database_path="/data/databases/update-test.db",
            library_path="/data/libraries/update-test/",
            import_path="/data/import/update-test/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/update-test.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        # Create library
        create_response = client.post(
            "/api/v1/libraries/",
            json={"name": "Update Test"},
        )
        assert create_response.status_code == 201

        # Update library by slug
        update_response = client.put(
            "/api/v1/libraries/update-test",
            json={"name": "Updated Name"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Name"

    def test_update_library_slug(self, test_app, client, mock_provisioning_service):
        """PUT /libraries/{slug} should allow updating the slug itself."""
        # Create a library first
        mock_paths = LibraryPaths(
            slug="old-slug",
            config_path="/config/old-slug.yaml",
            database_path="/data/databases/old-slug.db",
            library_path="/data/libraries/old-slug/",
            import_path="/data/import/old-slug/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/old-slug.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        # Create library
        create_response = client.post(
            "/api/v1/libraries/",
            json={"name": "Old Slug"},
        )
        assert create_response.status_code == 201

        # Update library slug
        update_response = client.put(
            "/api/v1/libraries/old-slug",
            json={"slug": "new-slug"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["slug"] == "new-slug"

        # Old slug should now return 404
        old_response = client.get("/api/v1/libraries/old-slug")
        assert old_response.status_code == 404

        # New slug should work
        new_response = client.get("/api/v1/libraries/new-slug")
        assert new_response.status_code == 200

    def test_delete_library_by_slug(self, test_app, client, mock_provisioning_service):
        """DELETE /libraries/{slug} should delete library found by slug."""
        # Create a library first
        mock_paths = LibraryPaths(
            slug="delete-test",
            config_path="/config/delete-test.yaml",
            database_path="/data/databases/delete-test.db",
            library_path="/data/libraries/delete-test/",
            import_path="/data/import/delete-test/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/delete-test.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )
        mock_provisioning_service.cleanup_resources.return_value = {
            "config": False,
            "database": False,
            "folders": False,
        }

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        # Create library
        create_response = client.post(
            "/api/v1/libraries/",
            json={"name": "Delete Test"},
        )
        assert create_response.status_code == 201

        # Delete library by slug
        delete_response = client.delete("/api/v1/libraries/delete-test")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

        # Should return 404 now
        get_response = client.get("/api/v1/libraries/delete-test")
        assert get_response.status_code == 404


class TestCreateLibraryWithSlug:
    """Test cases for creating libraries with custom slugs."""

    def test_create_library_with_custom_slug(self, test_app, client, mock_provisioning_service):
        """POST /libraries with custom slug should use provided slug."""
        mock_paths = LibraryPaths(
            slug="custom-slug",
            config_path="/config/custom-slug.yaml",
            database_path="/data/databases/custom-slug.db",
            library_path="/data/libraries/custom-slug/",
            import_path="/data/import/custom-slug/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/custom-slug.yaml",
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
            json={
                "name": "My Custom Library",
                "slug": "custom-slug",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "custom-slug"

        # Verify provision_library was called with user_slug
        mock_provisioning_service.provision_library.assert_called_once()
        call_kwargs = mock_provisioning_service.provision_library.call_args
        assert call_kwargs[1]["user_slug"] == "custom-slug"

    def test_create_library_without_slug_auto_generates(self, test_app, client, mock_provisioning_service):
        """POST /libraries without slug should auto-generate from name."""
        mock_paths = LibraryPaths(
            slug="my-jazz-collection",
            config_path="/config/my-jazz-collection.yaml",
            database_path="/data/databases/my-jazz-collection.db",
            library_path="/data/libraries/my-jazz-collection/",
            import_path="/data/import/my-jazz-collection/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/my-jazz-collection.yaml",
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
            json={"name": "My Jazz Collection"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "my-jazz-collection"

    def test_create_library_with_invalid_slug_format(self, test_app, client):
        """POST /libraries with invalid slug format should return 422."""
        response = client.post(
            "/api/v1/libraries/",
            json={
                "name": "Test Library",
                "slug": "Invalid Slug!",
            },
        )

        assert response.status_code == 422

    def test_create_library_with_duplicate_slug(self, test_app, client, mock_provisioning_service):
        """POST /libraries with duplicate slug should return 409."""
        mock_paths = LibraryPaths(
            slug="duplicate-slug",
            config_path="/config/duplicate-slug.yaml",
            database_path="/data/databases/duplicate-slug.db",
            library_path="/data/libraries/duplicate-slug/",
            import_path="/data/import/duplicate-slug/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/duplicate-slug.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        # Create first library
        response1 = client.post(
            "/api/v1/libraries/",
            json={
                "name": "First Library",
                "slug": "duplicate-slug",
            },
        )
        assert response1.status_code == 201

        # Try to create second library with same slug
        response2 = client.post(
            "/api/v1/libraries/",
            json={
                "name": "Second Library",
                "slug": "duplicate-slug",
            },
        )
        assert response2.status_code == 409
        assert "SLUG_COLLISION" in response2.headers.get("X-Error-Code", "")


class TestSlugCollisionHandling:
    """Test cases for slug collision handling with numeric suffixes."""

    def test_auto_slug_collision_adds_suffix(self, tmp_path):
        """Auto-generated slug collision should add numeric suffix."""
        mock_settings = MagicMock()
        mock_settings.config_path = str(tmp_path / "config")
        mock_settings.databases_path = str(tmp_path / "databases")
        mock_settings.libraries_path = str(tmp_path / "libraries")
        mock_settings.import_path = str(tmp_path / "import")

        # Create directories
        (tmp_path / "config").mkdir()
        (tmp_path / "databases").mkdir()
        (tmp_path / "libraries").mkdir()
        (tmp_path / "import").mkdir()

        service = LibraryProvisioningService(settings=mock_settings)

        # Test unique slug generation with existing slugs
        existing_slugs = {"my-library", "my-library-2"}
        unique_slug = service.generate_unique_slug("my-library", existing_slugs)
        assert unique_slug == "my-library-3"

    def test_unique_slug_when_no_collision(self, tmp_path):
        """Unique slug should be returned when no collision."""
        mock_settings = MagicMock()
        mock_settings.config_path = str(tmp_path / "config")
        mock_settings.databases_path = str(tmp_path / "databases")
        mock_settings.libraries_path = str(tmp_path / "libraries")
        mock_settings.import_path = str(tmp_path / "import")

        # Create directories
        (tmp_path / "config").mkdir()
        (tmp_path / "databases").mkdir()
        (tmp_path / "libraries").mkdir()
        (tmp_path / "import").mkdir()

        service = LibraryProvisioningService(settings=mock_settings)

        existing_slugs = {"other-library"}
        unique_slug = service.generate_unique_slug("my-library", existing_slugs)
        assert unique_slug == "my-library"


class TestUpdateSlugValidation:
    """Test cases for slug validation on update."""

    def test_update_slug_with_invalid_format(self, test_app, client, mock_provisioning_service):
        """PUT /libraries/{slug} with invalid new slug should return 422."""
        # Create a library first
        mock_paths = LibraryPaths(
            slug="valid-slug",
            config_path="/config/valid-slug.yaml",
            database_path="/data/databases/valid-slug.db",
            library_path="/data/libraries/valid-slug/",
            import_path="/data/import/valid-slug/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/valid-slug.yaml",
            error=None,
            timed_out=False,
        )
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths,
            verification=mock_verification,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        # Create library
        create_response = client.post(
            "/api/v1/libraries/",
            json={"name": "Valid Slug"},
        )
        assert create_response.status_code == 201

        # Try to update with invalid slug
        update_response = client.put(
            "/api/v1/libraries/valid-slug",
            json={"slug": "Invalid Slug!"},
        )
        assert update_response.status_code == 422

    def test_update_slug_to_existing_slug(self, test_app, client, mock_provisioning_service):
        """PUT /libraries/{slug} with slug that exists should return 409."""
        # Create two libraries
        mock_paths1 = LibraryPaths(
            slug="library-one",
            config_path="/config/library-one.yaml",
            database_path="/data/databases/library-one.db",
            library_path="/data/libraries/library-one/",
            import_path="/data/import/library-one/",
        )
        mock_paths2 = LibraryPaths(
            slug="library-two",
            config_path="/config/library-two.yaml",
            database_path="/data/databases/library-two.db",
            library_path="/data/libraries/library-two/",
            import_path="/data/import/library-two/",
        )
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/test.yaml",
            error=None,
            timed_out=False,
        )

        test_app.dependency_overrides[get_provisioning_service] = lambda: mock_provisioning_service

        # Create first library
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths1,
            verification=mock_verification,
        )
        client.post("/api/v1/libraries/", json={"name": "Library One"})

        # Create second library
        mock_provisioning_service.provision_library.return_value = ProvisioningResult(
            paths=mock_paths2,
            verification=mock_verification,
        )
        client.post("/api/v1/libraries/", json={"name": "Library Two"})

        # Try to update second library's slug to first library's slug
        update_response = client.put(
            "/api/v1/libraries/library-two",
            json={"slug": "library-one"},
        )
        assert update_response.status_code == 409
        assert "SLUG_COLLISION" in update_response.headers.get("X-Error-Code", "")
