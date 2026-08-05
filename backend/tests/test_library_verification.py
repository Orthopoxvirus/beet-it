"""Unit tests for library configuration verification functionality."""

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from app.services.library_provisioning import (
    verify_library_config,
    _parse_config_path,
    VerificationResult,
    ProvisioningResult,
    LibraryPaths,
    LibraryProvisioningService,
    VERIFICATION_TIMEOUT_SECONDS,
)


class TestParseConfigPath:
    """Test cases for _parse_config_path helper function."""

    def test_parse_single_yaml_path(self):
        """Should extract a single YAML path from output."""
        stdout = "/config/test-library.yaml\n"
        result = _parse_config_path(stdout)
        assert result == "/config/test-library.yaml"

    def test_parse_multiple_lines_returns_first_yaml(self):
        """Should return the first YAML path when multiple lines present."""
        stdout = "/config/test-library.yaml\n/config/default.yaml\n"
        result = _parse_config_path(stdout)
        assert result == "/config/test-library.yaml"

    def test_parse_with_whitespace(self):
        """Should handle whitespace in output."""
        stdout = "  /config/test-library.yaml  \n"
        result = _parse_config_path(stdout)
        assert result == "/config/test-library.yaml"

    def test_parse_empty_string(self):
        """Should return None for empty string."""
        result = _parse_config_path("")
        assert result is None

    def test_parse_none_returns_none(self):
        """Should return None for None input."""
        result = _parse_config_path(None)
        assert result is None

    def test_parse_non_yaml_path(self):
        """Should return first non-empty line if no YAML path found."""
        stdout = "/some/other/path\n"
        result = _parse_config_path(stdout)
        assert result == "/some/other/path"

    def test_parse_only_whitespace(self):
        """Should return None for whitespace-only output."""
        result = _parse_config_path("   \n  \n")
        assert result is None


class TestVerifyLibraryConfig:
    """Test cases for verify_library_config function."""

    def test_successful_verification(self):
        """Should return success with config path when command succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/config/test-library.yaml\n"
        mock_result.stderr = ""

        with patch("app.services.library_provisioning.subprocess.run", return_value=mock_result):
            result = verify_library_config("/config/test-library.yaml")

        assert result.success is True
        assert result.config_path == "/config/test-library.yaml"
        assert result.error is None
        assert result.timed_out is False

    def test_command_called_with_correct_arguments(self):
        """Should call subprocess.run with correct command arguments."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/config/test.yaml"
        mock_result.stderr = ""

        with patch("app.services.library_provisioning.subprocess.run", return_value=mock_result) as mock_run:
            verify_library_config("/config/test.yaml")

        mock_run.assert_called_once_with(
            ["python", "-m", "beets", "-c", "/config/test.yaml", "config", "-p"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )

    def test_failed_verification_with_error(self):
        """Should return failure with error message when command fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "configuration error: invalid YAML syntax"

        with patch("app.services.library_provisioning.subprocess.run", return_value=mock_result):
            result = verify_library_config("/config/invalid.yaml")

        assert result.success is False
        assert result.config_path is None
        assert result.error == "configuration error: invalid YAML syntax"
        assert result.timed_out is False

    def test_failed_verification_without_stderr(self):
        """Should return generic error when command fails without stderr."""
        mock_result = MagicMock()
        mock_result.returncode = 2
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("app.services.library_provisioning.subprocess.run", return_value=mock_result):
            result = verify_library_config("/config/test.yaml")

        assert result.success is False
        assert result.config_path is None
        assert result.error == "Command exited with code 2"
        assert result.timed_out is False

    def test_timeout_handling(self):
        """Should return timed_out=True when command times out."""
        with patch(
            "app.services.library_provisioning.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=30),
        ):
            result = verify_library_config("/config/test.yaml")

        assert result.success is False
        assert result.config_path is None
        assert result.error is None
        assert result.timed_out is True

    def test_beets_not_found(self):
        """Should return error when beets executable not found."""
        with patch(
            "app.services.library_provisioning.subprocess.run",
            side_effect=FileNotFoundError("python not found"),
        ):
            result = verify_library_config("/config/test.yaml")

        assert result.success is False
        assert result.config_path is None
        assert result.error == "Beets executable not found. Ensure beets is installed."
        assert result.timed_out is False

    def test_generic_exception_handling(self):
        """Should return error when unexpected exception occurs."""
        with patch(
            "app.services.library_provisioning.subprocess.run",
            side_effect=Exception("Unexpected error"),
        ):
            result = verify_library_config("/config/test.yaml")

        assert result.success is False
        assert result.config_path is None
        assert result.error == "Unexpected error"
        assert result.timed_out is False


class TestProvisionLibraryWithVerification:
    """Test cases for provision_library with verification integration."""

    @pytest.fixture
    def mock_service(self, tmp_path):
        """Create a provisioning service with temporary directories."""
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

    def test_provision_library_returns_provisioning_result(self, mock_service):
        """provision_library should return ProvisioningResult with paths and verification."""
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/test-library.yaml",
            error=None,
            timed_out=False,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ):
            result = mock_service.provision_library("Test Library")

        assert isinstance(result, ProvisioningResult)
        assert isinstance(result.paths, LibraryPaths)
        assert isinstance(result.verification, VerificationResult)
        assert result.paths.slug == "test-library"
        assert result.verification.success is True

    def test_provision_library_with_successful_verification(self, mock_service):
        """provision_library should include successful verification in result."""
        mock_verification = VerificationResult(
            success=True,
            config_path="/config/my-library.yaml",
            error=None,
            timed_out=False,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ):
            result = mock_service.provision_library("My Library")

        assert result.verification.success is True
        assert result.verification.config_path == "/config/my-library.yaml"
        assert result.verification.error is None
        assert result.verification.timed_out is False

    def test_provision_library_with_failed_verification(self, mock_service):
        """provision_library should succeed even when verification fails."""
        mock_verification = VerificationResult(
            success=False,
            config_path=None,
            error="Invalid config",
            timed_out=False,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ):
            result = mock_service.provision_library("Failed Verification Library")

        # Library should still be provisioned
        assert result.paths.slug == "failed-verification-library"
        # But verification should show failure
        assert result.verification.success is False
        assert result.verification.error == "Invalid config"

    def test_provision_library_with_verification_timeout(self, mock_service):
        """provision_library should succeed even when verification times out."""
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
            result = mock_service.provision_library("Timeout Library")

        # Library should still be provisioned
        assert result.paths.slug == "timeout-library"
        # But verification should show timeout
        assert result.verification.success is False
        assert result.verification.timed_out is True

    def test_provision_library_calls_verify_with_correct_path(self, mock_service):
        """provision_library should call verify_library_config with the config path."""
        mock_verification = VerificationResult(
            success=True,
            config_path=None,
            error=None,
            timed_out=False,
        )

        with patch(
            "app.services.library_provisioning.verify_library_config",
            return_value=mock_verification,
        ) as mock_verify:
            result = mock_service.provision_library("Verify Path Test")

        # Verify was called with the correct config path
        mock_verify.assert_called_once()
        call_args = mock_verify.call_args[0][0]
        assert call_args.endswith("verify-path-test.yaml")

    def test_provision_library_creates_files_before_verification(self, mock_service, tmp_path):
        """Config file and directories should exist before verification is called."""
        files_exist_during_verify = {}

        def capture_state(config_path):
            files_exist_during_verify["config"] = (tmp_path / "config" / "check-order.yaml").exists()
            files_exist_during_verify["library"] = (tmp_path / "libraries" / "check-order").exists()
            files_exist_during_verify["import"] = (tmp_path / "import" / "check-order").exists()
            return VerificationResult(success=True, config_path=config_path, error=None, timed_out=False)

        with patch(
            "app.services.library_provisioning.verify_library_config",
            side_effect=capture_state,
        ):
            mock_service.provision_library("Check Order")

        assert files_exist_during_verify["config"] is True
        assert files_exist_during_verify["library"] is True
        assert files_exist_during_verify["import"] is True
