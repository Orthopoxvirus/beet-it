"""Integration tests for library initialization API endpoints."""

import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.library import Library
from app.schemas.library_init import PathStatusResponse, InitializeResponse


@pytest.fixture
def mock_library():
    """Create a mock library."""
    library = Mock(spec=Library)
    library.id = 1
    library.name = "Test Library"
    library.slug = "test-library"
    library.import_path = "/data/import/test"
    library.config_path = "/config/test.yaml"
    library.database_path = "/data/databases/test.db"
    library.library_path = "/data/libraries/test"
    library.created_at = datetime(2024, 1, 1, 0, 0, 0)
    library.updated_at = None
    return library


class TestPathStatusResponseSchema:
    """Tests for PathStatusResponse schema."""

    def test_path_status_response_both_exist(self):
        """Test PathStatusResponse when both paths exist."""
        response = PathStatusResponse(
            directory_exists=True,
            database_exists=True,
            directory_path="/data/libraries/jazz",
            database_path="/data/databases/jazz.db",
        )

        assert response.directory_exists is True
        assert response.database_exists is True
        assert response.directory_path == "/data/libraries/jazz"
        assert response.database_path == "/data/databases/jazz.db"

    def test_path_status_response_both_missing(self):
        """Test PathStatusResponse when both paths are missing."""
        response = PathStatusResponse(
            directory_exists=False,
            database_exists=False,
            directory_path="/data/libraries/new",
            database_path="/data/databases/new.db",
        )

        assert response.directory_exists is False
        assert response.database_exists is False

    def test_path_status_response_null_paths(self):
        """Test PathStatusResponse with null paths."""
        response = PathStatusResponse(
            directory_exists=False,
            database_exists=False,
            directory_path=None,
            database_path=None,
        )

        assert response.directory_path is None
        assert response.database_path is None


class TestInitializeResponseSchema:
    """Tests for InitializeResponse schema."""

    def test_initialize_response_success(self):
        """Test InitializeResponse for successful initialization."""
        response = InitializeResponse(
            success=True,
            directory_created=True,
            database_initialized=True,
            message="Library resources initialized successfully",
        )

        assert response.success is True
        assert response.directory_created is True
        assert response.database_initialized is True
        assert "successfully" in response.message

    def test_initialize_response_already_initialized(self):
        """Test InitializeResponse when already initialized."""
        response = InitializeResponse(
            success=True,
            directory_created=False,
            database_initialized=False,
            message="Library resources already initialized",
        )

        assert response.success is True
        assert response.directory_created is False
        assert response.database_initialized is False
        assert "already initialized" in response.message


class TestPathStatusEndpointBehavior:
    """Tests for path status endpoint behavior."""

    def test_library_not_found_returns_404(self):
        """Test that 404 is returned when library ID doesn't exist."""
        from app.api.config import get_path_status
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_config_service = Mock()
        mock_provisioning_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            get_path_status(
                library_id=999,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 404
        assert "Library not found" in exc_info.value.detail

    def test_config_not_found_returns_404(self, mock_library):
        """Test that 404 is returned when config path is not set."""
        from app.api.config import get_path_status
        from fastapi import HTTPException

        mock_library.config_path = None

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config_service = Mock()
        mock_provisioning_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            get_path_status(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 404
        assert "CONFIG_NOT_FOUND" in exc_info.value.headers.get("X-Error-Code", "")

    def test_config_file_not_found_returns_404(self, mock_library):
        """Test that 404 is returned when config file doesn't exist on disk."""
        from app.api.config import get_path_status
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.side_effect = FileNotFoundError(
            "Config file not found"
        )

        mock_provisioning_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            get_path_status(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 404

    def test_config_parse_error_returns_500(self, mock_library):
        """Test that 500 is returned when config cannot be parsed."""
        from app.api.config import get_path_status
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.side_effect = ValueError(
            "Invalid YAML"
        )

        mock_provisioning_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            get_path_status(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 500
        assert "CONFIG_PARSE_ERROR" in exc_info.value.headers.get("X-Error-Code", "")

    def test_successful_path_status_response(self, mock_library):
        """Test successful path status response."""
        from app.api.config import get_path_status
        from app.schemas.beets_config import BeetsConfigSchema

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/data/libraries/test"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (True, False)

        result = get_path_status(
            library_id=1,
            db=mock_db,
            config_service=mock_config_service,
            provisioning_service=mock_provisioning_service,
        )

        assert result.directory_exists is True
        assert result.database_exists is False
        assert result.directory_path == "/data/libraries/test"
        assert result.database_path == "/data/databases/test.db"


class TestInitializeEndpointBehavior:
    """Tests for initialize endpoint behavior."""

    def test_library_not_found_returns_404(self):
        """Test that 404 is returned when library ID doesn't exist."""
        from app.api.config import initialize_library
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_config_service = Mock()
        mock_provisioning_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            initialize_library(
                library_id=999,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 404

    def test_paths_not_configured_returns_500(self, mock_library):
        """Test that 500 is returned when paths are not configured in beets config."""
        from app.api.config import initialize_library
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = ""
        mock_config.library = ""

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            initialize_library(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 500
        assert "PATHS_NOT_CONFIGURED" in exc_info.value.headers.get("X-Error-Code", "")

    def test_already_initialized_returns_success(self, mock_library):
        """Test that success is returned when library is already initialized."""
        from app.api.config import initialize_library

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/data/libraries/test"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (True, True)

        result = initialize_library(
            library_id=1,
            db=mock_db,
            config_service=mock_config_service,
            provisioning_service=mock_provisioning_service,
        )

        assert result.success is True
        assert result.directory_created is False
        assert result.database_initialized is False
        assert "already initialized" in result.message

    def test_successful_initialization(self, mock_library):
        """Test successful library initialization."""
        from app.api.config import initialize_library

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/data/libraries/test"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (False, False)
        mock_provisioning_service.initialize_library_resources.return_value = (True, True)

        result = initialize_library(
            library_id=1,
            db=mock_db,
            config_service=mock_config_service,
            provisioning_service=mock_provisioning_service,
        )

        assert result.success is True
        assert result.directory_created is True
        assert result.database_initialized is True
        assert "successfully" in result.message

    def test_path_outside_boundary_returns_403(self, mock_library):
        """Test that 403 is returned when path is outside allowed boundaries."""
        from app.api.config import initialize_library
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/unauthorized/path"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (False, False)
        mock_provisioning_service.initialize_library_resources.side_effect = ValueError(
            "Path '/unauthorized/path' is outside allowed mount boundaries"
        )

        with pytest.raises(HTTPException) as exc_info:
            initialize_library(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 403
        assert "PATH_OUTSIDE_BOUNDARY" in exc_info.value.headers.get("X-Error-Code", "")

    def test_directory_creation_failed_returns_500(self, mock_library):
        """Test that 500 is returned when directory creation fails."""
        from app.api.config import initialize_library
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/data/libraries/test"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (False, False)
        mock_provisioning_service.initialize_library_resources.side_effect = OSError(
            "Permission denied"
        )

        with pytest.raises(HTTPException) as exc_info:
            initialize_library(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 500
        assert "DIRECTORY_CREATION_FAILED" in exc_info.value.headers.get(
            "X-Error-Code", ""
        )

    def test_database_init_timeout_returns_500(self, mock_library):
        """Test that 500 is returned when database initialization times out."""
        from app.api.config import initialize_library
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/data/libraries/test"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (False, False)
        mock_provisioning_service.initialize_library_resources.side_effect = RuntimeError(
            "Initialization timed out after 30s"
        )

        with pytest.raises(HTTPException) as exc_info:
            initialize_library(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 500
        assert "INIT_TIMEOUT" in exc_info.value.headers.get("X-Error-Code", "")

    def test_database_init_failed_returns_500(self, mock_library):
        """Test that 500 is returned when database initialization fails."""
        from app.api.config import initialize_library
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_library

        mock_config = Mock()
        mock_config.directory = "/data/libraries/test"
        mock_config.library = "/data/databases/test.db"

        mock_config_service = Mock()
        mock_config_service.parse_yaml_config.return_value = mock_config

        mock_provisioning_service = Mock()
        mock_provisioning_service.get_path_status.return_value = (False, False)
        mock_provisioning_service.initialize_library_resources.side_effect = RuntimeError(
            "Database initialization failed: Invalid config"
        )

        with pytest.raises(HTTPException) as exc_info:
            initialize_library(
                library_id=1,
                db=mock_db,
                config_service=mock_config_service,
                provisioning_service=mock_provisioning_service,
            )

        assert exc_info.value.status_code == 500
        assert "DATABASE_INIT_FAILED" in exc_info.value.headers.get("X-Error-Code", "")
