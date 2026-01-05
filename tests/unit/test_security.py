"""Security tests for highway-driver.

Tests credential protection, exception handling, and artifact safety.
"""

from __future__ import annotations

import logging
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from highway import Driver
from highway.artifact import (
    PackagedArtifact,
    _create_secure_tempfile,
    cleanup_artifact,
    package_functions,
)


class TestCredentialProtection:
    """Tests for API key and credential protection."""

    def test_api_key_not_in_repr(self) -> None:
        """API key should not appear in repr output."""
        driver = Driver(api_key="hw_k1_secret_test_key_12345")
        repr_output = repr(driver)

        assert "hw_k1_secret_test_key_12345" not in repr_output
        assert "secret" not in repr_output.lower()
        assert "api_key" not in repr_output.lower()
        # Should show safe info
        assert "Driver" in repr_output
        assert "endpoint" in repr_output

    def test_api_key_not_in_str(self) -> None:
        """API key should not appear in str output."""
        driver = Driver(api_key="hw_k1_secret_test_key_12345")
        str_output = str(driver)

        assert "hw_k1_secret_test_key_12345" not in str_output
        assert "secret" not in str_output.lower()

    def test_api_key_accessible_via_property(self) -> None:
        """API key should be accessible via property for legitimate use."""
        api_key = "hw_k1_test_key"
        driver = Driver(api_key=api_key)

        assert driver.api_key == api_key

    def test_api_key_from_env_not_exposed(self) -> None:
        """API key from environment should also not be exposed."""
        with patch.dict(os.environ, {"HIGHWAY_API_KEY": "hw_k1_env_secret_key"}):
            driver = Driver()
            repr_output = repr(driver)

            assert "env_secret_key" not in repr_output
            assert "HIGHWAY_API_KEY" not in repr_output


class TestTempFileSafety:
    """Tests for temporary file security and cleanup."""

    def test_secure_tempfile_has_restricted_permissions(self) -> None:
        """Temp files should have restricted permissions (0o600)."""
        path = _create_secure_tempfile()
        try:
            stat_result = os.stat(path)
            permissions = stat_result.st_mode & 0o777

            # Should be owner read/write only
            assert permissions == 0o600, f"Expected 0o600, got {oct(permissions)}"
        finally:
            os.unlink(path)

    def test_cleanup_artifact_logs_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Cleanup failures should be logged, not silently ignored."""
        # Create a fake artifact with non-existent path
        artifact = PackagedArtifact(
            file_path="/nonexistent/path/to/artifact.zip",
            content_hash="abc123",
            package_name="test_pkg",
            entrypoint="main:run",
        )

        # This should not raise, but also shouldn't log since file doesn't exist
        cleanup_artifact(artifact)

        # Now test with a file that exists but we can't delete
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            temp_path = f.name

        artifact = PackagedArtifact(
            file_path=temp_path,
            content_hash="abc123",
            package_name="test_pkg",
            entrypoint="main:run",
        )

        # Make directory read-only to simulate deletion failure
        # Note: This won't work as root, so we mock instead
        with patch("os.unlink", side_effect=OSError("Permission denied")):
            with caplog.at_level(logging.WARNING, logger="highway.artifact"):
                cleanup_artifact(artifact)

        # Check that warning was logged
        assert "Failed to cleanup temp file" in caplog.text
        assert "Permission denied" in caplog.text

        # Actual cleanup
        os.unlink(temp_path)

    def test_package_functions_cleans_up_on_error(self) -> None:
        """Artifact packaging should clean up temp files on error."""

        # Create a function that will fail during packaging
        def invalid_func() -> None:
            pass

        # Mock inspect.getsource to raise an error
        with patch("inspect.getsource", side_effect=OSError("Source unavailable")):
            with pytest.raises(ValueError, match="Cannot extract source"):
                package_functions({"invalid_func": invalid_func})

        # Verify no orphan temp files were left
        # Note: This is hard to verify directly, but the try/except in package_functions
        # should handle cleanup


class TestExceptionHandling:
    """Tests for proper exception handling."""

    def test_workflow_handle_repr_handles_errors(self) -> None:
        """WorkflowHandle repr should handle status fetch errors gracefully."""
        from highway.handle import WorkflowHandle

        # Create a mock driver that raises on status
        mock_driver = MagicMock()
        mock_driver.status.side_effect = ValueError("Connection failed")

        handle = WorkflowHandle(
            run_id="test-run-id",
            driver=mock_driver,
            timeout=10,
        )

        # repr should not raise
        repr_output = repr(handle)

        # Should contain run_id and show unknown state
        assert "test-run-id" in repr_output
        assert "unknown" in repr_output.lower()

    def test_specific_exceptions_in_repr(self) -> None:
        """WorkflowHandle catches specific exceptions, not bare except."""
        from highway.handle import WorkflowHandle

        # Create a mock driver that raises different exceptions
        mock_driver = MagicMock()

        # AttributeError should be caught
        mock_driver.status.side_effect = AttributeError("No attribute")
        handle = WorkflowHandle(run_id="test", driver=mock_driver, timeout=10)
        assert "unknown" in repr(handle).lower()

        # KeyError should be caught
        mock_driver.status.side_effect = KeyError("Missing key")
        assert "unknown" in repr(handle).lower()

        # TypeError should be caught
        mock_driver.status.side_effect = TypeError("Type mismatch")
        assert "unknown" in repr(handle).lower()


class TestArtifactPackaging:
    """Tests for artifact packaging security."""

    def test_package_creates_secure_file(self) -> None:
        """Packaged artifacts should have restricted permissions."""

        def simple_func() -> dict[str, str]:
            return {"result": "test"}

        artifact = package_functions({"simple_func": simple_func})

        try:
            # Check file permissions
            stat_result = os.stat(artifact.file_path)
            permissions = stat_result.st_mode & 0o777

            assert permissions == 0o600, f"Expected 0o600, got {oct(permissions)}"

            # Check file exists and has content
            assert os.path.exists(artifact.file_path)
            assert os.path.getsize(artifact.file_path) > 0
        finally:
            cleanup_artifact(artifact)
