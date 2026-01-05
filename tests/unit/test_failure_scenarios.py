"""Unit tests for failure scenarios and error handling.

These tests verify highway-driver handles failures correctly:
1. Timeout handling
2. Error propagation from Stabilize
3. Concurrent execution safety
4. Configuration errors
5. Network/API failure simulation
"""

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

from highway import Driver
from highway.exceptions import ConfigurationError, ExecutionError
from highway.result import WorkflowResult, WorkflowState
from highway.runner import StabilizeRunner

# =============================================================================
# Timeout Handling Tests
# =============================================================================


class TestTimeoutHandling:
    """Tests for timeout handling in Driver and Runner."""

    def test_timeout_returns_timed_out_state(self):
        """Verify timeout returns TIMED_OUT state, not RUNNING."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            # Submit a workflow
            workflow_def = {
                "name": "test_workflow",
                "version": "1.0.0",
                "tasks": {
                    "test": {
                        "type": "shell",
                        "command": "sleep 100",
                    }
                },
            }

            exec_id = runner.submit(workflow_def)

            # Wait with very short timeout should raise TimeoutError
            with pytest.raises(TimeoutError) as exc_info:
                runner.wait(exec_id, timeout=0.1, poll_interval=0.05)

            assert exec_id in str(exc_info.value)

    def test_driver_timeout_returns_correct_result(self):
        """Verify Driver.run() returns TIMED_OUT result on timeout."""
        driver = Driver(api_key="test_key", endpoint="http://test")

        @driver.task(shell=True)
        def slow_task():
            return "sleep 100"

        # Mock the runner to raise TimeoutError
        with patch.object(driver, "_get_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_runner.submit.return_value = "exec-123"
            mock_runner.wait.side_effect = TimeoutError("timed out")
            mock_get_runner.return_value = mock_runner

            result = driver.run(wait=True, timeout=1)

            assert result.state == WorkflowState.TIMED_OUT
            assert result.status == "timed_out"
            assert "timed out" in result.error.lower()


# =============================================================================
# Error Propagation Tests
# =============================================================================


class TestErrorPropagation:
    """Tests for error propagation from Stabilize layer."""

    def test_execution_error_propagates(self):
        """Verify ExecutionError is caught and converted to failed result."""
        driver = Driver(api_key="test_key", endpoint="http://test")

        @driver.task(shell=True)
        def failing_task():
            return "exit 1"

        with patch.object(driver, "_get_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_runner.submit.return_value = "exec-123"
            mock_runner.wait.side_effect = ExecutionError("Task failed")
            mock_get_runner.return_value = mock_runner

            result = driver.run(wait=True)

            assert result.state == WorkflowState.FAILED
            assert result.status == "failed"
            assert "Task failed" in result.error

    def test_missing_api_key_raises_configuration_error(self):
        """Verify missing API key raises ConfigurationError."""
        driver = Driver()  # No api_key, env var not set

        @driver.task(shell=True)
        def my_task():
            return "echo test"

        # Clear env var to ensure no fallback
        with patch.dict("os.environ", {"HIGHWAY_API_KEY": ""}, clear=True):
            # Re-create driver to pick up empty env
            driver2 = Driver()

            @driver2.task(shell=True)
            def my_task():
                return "echo test"

            with pytest.raises(ConfigurationError) as exc_info:
                driver2.run()

            assert "HIGHWAY_API_KEY" in str(exc_info.value)


# =============================================================================
# Concurrent Execution Tests
# =============================================================================


class TestConcurrentExecution:
    """Tests for concurrent workflow execution safety."""

    def test_concurrent_driver_instances(self):
        """Verify multiple Driver instances can run concurrently."""
        results = []
        errors = []

        def run_workflow(idx: int):
            try:
                driver = Driver(api_key="test_key", endpoint="http://test")

                @driver.task(shell=True)
                def task():
                    return f"echo 'workflow {idx}'"

                with patch.object(driver, "_get_runner") as mock_get_runner:
                    mock_runner = MagicMock()
                    mock_runner.submit.return_value = f"exec-{idx}"
                    mock_runner.wait.return_value = {
                        "status": "succeeded",
                        "highway_status": "completed",
                        "highway_result": {"task_result": idx},
                    }
                    mock_get_runner.return_value = mock_runner

                    result = driver.run(wait=True)
                    results.append((idx, result))
            except Exception as e:
                errors.append((idx, e))

        # Run 10 workflows concurrently
        threads = []
        for i in range(10):
            t = threading.Thread(target=run_workflow, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10

    def test_concurrent_runner_operations(self):
        """Verify StabilizeRunner handles concurrent operations safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"

            # Single runner, multiple concurrent submits
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            exec_ids = []
            errors = []

            def submit_workflow(idx: int):
                try:
                    workflow_def = {
                        "name": f"workflow_{idx}",
                        "version": "1.0.0",
                        "tasks": {"test": {"type": "shell", "command": f"echo {idx}"}},
                    }
                    exec_id = runner.submit(workflow_def)
                    exec_ids.append(exec_id)
                except Exception as e:
                    errors.append((idx, e))

            # Submit 5 workflows concurrently
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(submit_workflow, i) for i in range(5)]
                for future in as_completed(futures):
                    pass  # Wait for all

            assert len(errors) == 0, f"Errors: {errors}"
            assert len(exec_ids) == 5
            # All IDs should be unique
            assert len(set(exec_ids)) == 5


# =============================================================================
# Runner Status Tests
# =============================================================================


class TestRunnerStatus:
    """Tests for runner status operations."""

    def test_status_after_submit(self):
        """Verify status can be retrieved after submit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            workflow_def = {
                "name": "test_workflow",
                "version": "1.0.0",
                "tasks": {"test": {"type": "shell", "command": "echo test"}},
            }

            exec_id = runner.submit(workflow_def)
            status = runner.status(exec_id, process_pending=False)

            assert status["execution_id"] == exec_id
            assert status["status"] in ("not_started", "running", "succeeded")

    def test_status_with_invalid_id_raises(self):
        """Verify status with invalid ID raises appropriate error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            # This should raise an error (workflow not found)
            with pytest.raises(Exception):
                runner.status("nonexistent-id")


# =============================================================================
# Configuration Error Tests
# =============================================================================


class TestConfigurationErrors:
    """Tests for configuration validation."""

    def test_empty_endpoint_uses_env_or_default(self):
        """Verify empty endpoint uses env var or default."""
        with patch.dict("os.environ", {"HIGHWAY_API_ENDPOINT": ""}, clear=False):
            # Clear only the endpoint env var
            import os

            old_val = os.environ.pop("HIGHWAY_API_ENDPOINT", None)
            try:
                driver = Driver(api_key="test_key")
                assert driver.endpoint == "https://highway.run"
            finally:
                if old_val:
                    os.environ["HIGHWAY_API_ENDPOINT"] = old_val

    def test_driver_with_explicit_endpoint(self):
        """Verify explicit endpoint is used."""
        driver = Driver(api_key="test_key", endpoint="http://custom:8080")
        assert driver.endpoint == "http://custom:8080"


# =============================================================================
# Workflow Result State Tests
# =============================================================================


class TestWorkflowResultStates:
    """Tests for WorkflowResult state handling."""

    def test_workflow_result_is_terminal_for_completed(self):
        """Verify is_terminal returns True for completed states."""
        result = WorkflowResult(
            run_id="test",
            status="completed",
            state=WorkflowState.COMPLETED,
        )
        assert result.is_terminal()
        assert result.is_success()

    def test_workflow_result_is_terminal_for_failed(self):
        """Verify is_terminal returns True for failed state."""
        result = WorkflowResult(
            run_id="test",
            status="failed",
            state=WorkflowState.FAILED,
            error="Something went wrong",
        )
        assert result.is_terminal()
        assert not result.is_success()

    def test_workflow_result_is_terminal_for_timed_out(self):
        """Verify is_terminal returns True for timed_out state."""
        result = WorkflowResult(
            run_id="test",
            status="timed_out",
            state=WorkflowState.TIMED_OUT,
            error="Workflow timed out",
        )
        assert result.is_terminal()
        assert not result.is_success()

    def test_workflow_result_is_not_terminal_for_running(self):
        """Verify is_terminal returns False for running state."""
        result = WorkflowResult(
            run_id="test",
            status="running",
            state=WorkflowState.RUNNING,
        )
        assert not result.is_terminal()
        assert not result.is_success()


# =============================================================================
# Cancel Operation Tests
# =============================================================================


class TestCancelOperation:
    """Tests for workflow cancellation."""

    def test_cancel_running_workflow(self):
        """Verify cancel returns True for running workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            workflow_def = {
                "name": "test_workflow",
                "version": "1.0.0",
                "tasks": {"test": {"type": "shell", "command": "sleep 100"}},
            }

            exec_id = runner.submit(workflow_def)

            # Cancel should return True
            cancelled = runner.cancel(exec_id)
            assert cancelled is True


# =============================================================================
# List Workflows Tests
# =============================================================================


class TestListWorkflows:
    """Tests for listing workflows."""

    def test_list_workflows_empty(self):
        """Verify list_workflows returns empty list initially."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            workflows = runner.list_workflows()
            assert workflows == []

    def test_list_workflows_after_submit(self):
        """Verify list_workflows includes submitted workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            runner = StabilizeRunner(
                db_path=db_path,
                api_key="test_key",
                api_endpoint="http://test",
            )

            workflow_def = {
                "name": "test_workflow",
                "version": "1.0.0",
                "tasks": {"test": {"type": "shell", "command": "echo test"}},
            }

            exec_id = runner.submit(workflow_def)
            workflows = runner.list_workflows()

            assert len(workflows) == 1
            assert workflows[0]["execution_id"] == exec_id


# =============================================================================
# Async (wait=False) Tests
# =============================================================================


class TestAsyncExecution:
    """Tests for async (wait=False) execution."""

    def test_run_without_wait_returns_immediately(self):
        """Verify run(wait=False) returns immediately with running status."""
        driver = Driver(api_key="test_key", endpoint="http://test")

        @driver.task(shell=True)
        def my_task():
            return "echo test"

        with patch.object(driver, "_get_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_runner.submit.return_value = "exec-123"
            mock_get_runner.return_value = mock_runner

            result = driver.run(wait=False)

            assert result.run_id == "exec-123"
            assert result.state == WorkflowState.RUNNING
            assert result.status == "running"
            # wait() should not be called
            mock_runner.wait.assert_not_called()

    def test_status_after_async_run(self):
        """Verify status can be checked after async run."""
        driver = Driver(api_key="test_key", endpoint="http://test")

        @driver.task(shell=True)
        def my_task():
            return "echo test"

        with patch.object(driver, "_get_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_runner.submit.return_value = "exec-123"
            mock_runner.status.return_value = {
                "status": "running",
                "highway_status": "running",
                "is_complete": False,
            }
            mock_get_runner.return_value = mock_runner

            # Start async
            result = driver.run(wait=False)

            # Check status
            status_result = driver.status(result.run_id)
            assert status_result.state == WorkflowState.RUNNING
