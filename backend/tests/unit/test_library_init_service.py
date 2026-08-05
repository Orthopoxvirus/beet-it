"""Unit tests for library initialization service methods."""

import os
import subprocess
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from app.services.library_provisioning import (
    LibraryProvisioningService,
    verify_library_config,
    VerificationResult,
    VERIFICATION_TIMEOUT_SECONDS,
)


class TestGetPathStatus:
    """Test cases for get_path_status method."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a provisioning service with temporary directories."""
        mock_settings = MagicMock()
        mock_settings.config_path = str(tmp_path / "config")
        mock_settings.databases_path = str(tmp_path / "databases")
        mock_settings.libraries_path = str(tmp_path / "libraries")
        mock_settings.import_path = str(tmp_path / "import")
        return LibraryProvisioningService(settings=mock_settings)

    def test_both_paths_exist(self, service, tmp_path):
        """Should return True for both when directory and database exist."""
        # Create test directory and file
        test_dir = tmp_path / "test-library"
        test_dir.mkdir()
        test_db = tmp_path / "test.db"
        test_db.touch()

        dir_exists, db_exists = service.get_path_status(
            str(test_dir), str(test_db)
        )

        assert dir_exists is True
        assert db_exists is True

    def test_directory_missing(self, service, tmp_path):
        """Should return False for directory when it doesn't exist."""
        test_db = tmp_path / "test.db"
        test_db.touch()
        missing_dir = tmp_path / "nonexistent"

        dir_exists, db_exists = service.get_path_status(
            str(missing_dir), str(test_db)
        )

        assert dir_exists is False
        assert db_exists is True

    def test_database_missing(self, service, tmp_path):
        """Should return False for database when it doesn't exist."""
        test_dir = tmp_path / "test-library"
        test_dir.mkdir()
        missing_db = tmp_path / "nonexistent.db"

        dir_exists, db_exists = service.get_path_status(
            str(test_dir), str(missing_db)
        )

        assert dir_exists is True
        assert db_exists is False

    def test_both_missing(self, service, tmp_path):
        """Should return False for both when neither exists."""
        missing_dir = tmp_path / "nonexistent"
        missing_db = tmp_path / "nonexistent.db"

        dir_exists, db_exists = service.get_path_status(
            str(missing_dir), str(missing_db)
        )

        assert dir_exists is False
        assert db_exists is False

    def test_null_directory_path(self, service, tmp_path):
        """Should return False for directory when path is None."""
        test_db = tmp_path / "test.db"
        test_db.touch()

        dir_exists, db_exists = service.get_path_status(None, str(test_db))

        assert dir_exists is False
        assert db_exists is True

    def test_null_database_path(self, service, tmp_path):
        """Should return False for database when path is None."""
        test_dir = tmp_path / "test-library"
        test_dir.mkdir()

        dir_exists, db_exists = service.get_path_status(str(test_dir), None)

        assert dir_exists is True
        assert db_exists is False

    def test_both_paths_null(self, service):
        """Should return False for both when paths are None."""
        dir_exists, db_exists = service.get_path_status(None, None)

        assert dir_exists is False
        assert db_exists is False

    def test_empty_string_paths(self, service):
        """Should return False for empty string paths."""
        dir_exists, db_exists = service.get_path_status("", "")

        assert dir_exists is False
        assert db_exists is False

    def test_directory_path_is_file(self, service, tmp_path):
        """Should return False for directory when path is a file."""
        test_file = tmp_path / "some_file"
        test_file.touch()

        dir_exists, db_exists = service.get_path_status(str(test_file), None)

        assert dir_exists is False

    def test_database_path_is_directory(self, service, tmp_path):
        """Should return False for database when path is a directory."""
        test_dir = tmp_path / "some_dir"
        test_dir.mkdir()

        dir_exists, db_exists = service.get_path_status(None, str(test_dir))

        assert db_exists is False


class TestValidatePathBoundaries:
    """Test cases for validate_path_boundaries method."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a provisioning service with specific allowed paths."""
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

        return LibraryProvisioningService(settings=mock_settings)

    def test_valid_path_within_libraries(self, service, tmp_path):
        """Should return True for path within libraries_path."""
        valid_path = str(tmp_path / "libraries" / "my-library")
        result = service.validate_path_boundaries(valid_path)
        assert result is True

    def test_valid_path_within_databases(self, service, tmp_path):
        """Should return True for path within databases_path."""
        valid_path = str(tmp_path / "databases" / "my-library.db")
        result = service.validate_path_boundaries(valid_path)
        assert result is True

    def test_valid_nested_path_within_libraries(self, service, tmp_path):
        """Should return True for nested path within libraries_path."""
        valid_path = str(tmp_path / "libraries" / "artist" / "album")
        result = service.validate_path_boundaries(valid_path)
        assert result is True

    def test_invalid_path_outside_allowed(self, service, tmp_path):
        """Should raise ValueError for path outside allowed boundaries."""
        invalid_path = "/unauthorized/path"

        with pytest.raises(ValueError) as exc_info:
            service.validate_path_boundaries(invalid_path)

        assert "outside allowed mount boundaries" in str(exc_info.value)

    def test_invalid_path_sibling_directory(self, service, tmp_path):
        """Should raise ValueError for sibling directory path."""
        invalid_path = str(tmp_path / "unauthorized" / "path")

        with pytest.raises(ValueError) as exc_info:
            service.validate_path_boundaries(invalid_path)

        assert "outside allowed mount boundaries" in str(exc_info.value)

    def test_invalid_path_parent_traversal(self, service, tmp_path):
        """Should raise ValueError for parent traversal path."""
        invalid_path = str(tmp_path / "libraries" / ".." / ".." / "etc")

        with pytest.raises(ValueError) as exc_info:
            service.validate_path_boundaries(invalid_path)

        assert "outside allowed mount boundaries" in str(exc_info.value)

    def test_path_normalization(self, service, tmp_path):
        """Should normalize path before validation."""
        # Path with relative components that resolves to valid path
        valid_path = str(tmp_path / "libraries" / "subdir" / ".." / "my-library")
        result = service.validate_path_boundaries(valid_path)
        assert result is True


class TestInitializeLibraryResources:
    """Test cases for initialize_library_resources method."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a provisioning service with temporary directories."""
        mock_settings = MagicMock()
        mock_settings.config_path = str(tmp_path / "config")
        mock_settings.databases_path = str(tmp_path / "databases")
        mock_settings.libraries_path = str(tmp_path / "libraries")
        mock_settings.import_path = str(tmp_path / "import")

        # Create base directories
        (tmp_path / "config").mkdir()
        (tmp_path / "databases").mkdir()
        (tmp_path / "libraries").mkdir()
        (tmp_path / "import").mkdir()

        return LibraryProvisioningService(settings=mock_settings)

    def test_creates_directory_when_missing(self, service, tmp_path):
        """Should create library directory when it doesn't exist."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "new-library")
        db_path = str(tmp_path / "databases" / "test.db")

        # Create config file and database so only directory creation is tested
        (tmp_path / "config").mkdir(exist_ok=True)
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "databases" / "test.db").touch()

        dir_created, db_initialized = service.initialize_library_resources(
            config_path=config_path,
            directory_path=dir_path,
            database_path=db_path,
        )

        assert dir_created is True
        assert db_initialized is False
        assert os.path.isdir(dir_path)

    def test_skips_directory_when_exists(self, service, tmp_path):
        """Should not create directory when it already exists."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "existing-library")
        db_path = str(tmp_path / "databases" / "test.db")

        # Create all resources
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "libraries" / "existing-library").mkdir()
        (tmp_path / "databases" / "test.db").touch()

        dir_created, db_initialized = service.initialize_library_resources(
            config_path=config_path,
            directory_path=dir_path,
            database_path=db_path,
        )

        assert dir_created is False
        assert db_initialized is False

    def test_initializes_database_when_missing(self, service, tmp_path):
        """Should initialize database when it doesn't exist."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "test-library")
        db_path = str(tmp_path / "databases" / "test.db")

        # Create directory and config
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "libraries" / "test-library").mkdir()

        # Mock verify_library_config to succeed
        mock_verification = VerificationResult(
            success=True,
            config_path=config_path,
            error=None,
            timed_out=False,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ):
            dir_created, db_initialized = service.initialize_library_resources(
                config_path=config_path,
                directory_path=dir_path,
                database_path=db_path,
            )

        assert dir_created is False
        assert db_initialized is True

    def test_raises_error_for_path_outside_boundaries(self, service, tmp_path):
        """Should raise ValueError for path outside allowed boundaries."""
        config_path = str(tmp_path / "config" / "test.yaml")
        invalid_dir = "/unauthorized/path"
        db_path = str(tmp_path / "databases" / "test.db")

        with pytest.raises(ValueError) as exc_info:
            service.initialize_library_resources(
                config_path=config_path,
                directory_path=invalid_dir,
                database_path=db_path,
            )

        assert "outside allowed mount boundaries" in str(exc_info.value)

    def test_raises_error_on_verification_timeout(self, service, tmp_path):
        """Should raise RuntimeError when verification times out."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "test-library")
        db_path = str(tmp_path / "databases" / "test.db")

        # Create directory and config
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "libraries" / "test-library").mkdir()

        # Mock verify_library_config to timeout
        mock_verification = VerificationResult(
            success=False,
            config_path=None,
            error=None,
            timed_out=True,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                service.initialize_library_resources(
                    config_path=config_path,
                    directory_path=dir_path,
                    database_path=db_path,
                )

        assert "timed out" in str(exc_info.value)

    def test_raises_error_on_verification_failure(self, service, tmp_path):
        """Should raise RuntimeError when verification fails."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "test-library")
        db_path = str(tmp_path / "databases" / "test.db")

        # Create directory and config
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "libraries" / "test-library").mkdir()

        # Mock verify_library_config to fail
        mock_verification = VerificationResult(
            success=False,
            config_path=None,
            error="Invalid configuration",
            timed_out=False,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                service.initialize_library_resources(
                    config_path=config_path,
                    directory_path=dir_path,
                    database_path=db_path,
                )

        assert "Database initialization failed" in str(exc_info.value)
        assert "Invalid configuration" in str(exc_info.value)

    def test_idempotent_when_both_exist(self, service, tmp_path):
        """Should return False for both when resources already exist."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "existing")
        db_path = str(tmp_path / "databases" / "existing.db")

        # Create all resources
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "libraries" / "existing").mkdir()
        (tmp_path / "databases" / "existing.db").touch()

        dir_created, db_initialized = service.initialize_library_resources(
            config_path=config_path,
            directory_path=dir_path,
            database_path=db_path,
        )

        assert dir_created is False
        assert db_initialized is False

    def test_creates_databases_directory_if_missing(self, service, tmp_path):
        """Should create databases directory if it doesn't exist."""
        config_path = str(tmp_path / "config" / "test.yaml")
        dir_path = str(tmp_path / "libraries" / "test-library")
        # Use a nested database path
        db_path = str(tmp_path / "databases" / "nested" / "test.db")

        # Create directory and config
        (tmp_path / "config" / "test.yaml").touch()
        (tmp_path / "libraries" / "test-library").mkdir()
        (tmp_path / "databases" / "nested" / "test.db").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "databases" / "nested" / "test.db").touch()

        # Should not raise even with nested db directory
        dir_created, db_initialized = service.initialize_library_resources(
            config_path=config_path,
            directory_path=dir_path,
            database_path=db_path,
        )

        assert dir_created is False
        assert db_initialized is False
