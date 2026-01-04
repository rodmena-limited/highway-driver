"""Unit tests for local task execution via Stabilize native tasks."""

import pytest

from highway import Driver
from highway.exceptions import NotSupportedError
from highway.task import TaskType


class TestLocalTaskRegistration:
    """Tests for registering local tasks."""

    def test_local_shell_task_registration(self):
        """Local shell task registers with local=True."""
        driver = Driver()

        @driver.task(shell=True, local=True)
        def echo_hello():
            return "echo 'hello'"

        task = driver.tasks["echo_hello"]
        assert task.local is True
        assert task.task_type == TaskType.SHELL

    def test_local_http_task_registration(self):
        """Local http task registers with local=True."""
        driver = Driver()

        @driver.task(http=True, local=True)
        def check_health():
            return {"url": "http://localhost:8080/health"}

        task = driver.tasks["check_health"]
        assert task.local is True
        assert task.task_type == TaskType.HTTP

    def test_local_python_task_registration(self):
        """Local python task registers with local=True."""
        driver = Driver()

        @driver.task(py=True, local=True)
        def calculate():
            return {"result": 42}

        task = driver.tasks["calculate"]
        assert task.local is True
        assert task.task_type == TaskType.PYTHON

    def test_has_local_tasks(self):
        """has_local_tasks returns True when local tasks exist."""
        driver = Driver()

        @driver.task(shell=True, local=True)
        def local_task():
            return "echo 'local'"

        assert driver.has_local_tasks() is True
        assert driver.has_highway_tasks() is False

    def test_has_highway_tasks(self):
        """has_highway_tasks returns True when Highway tasks exist."""
        driver = Driver(api_key="test")

        @driver.task(shell=True)
        def highway_task():
            return "echo 'highway'"

        assert driver.has_local_tasks() is False
        assert driver.has_highway_tasks() is True

    def test_get_local_tasks(self):
        """get_local_tasks returns only local tasks."""
        driver = Driver(api_key="test")

        @driver.task(shell=True, local=True)
        def local_task():
            return "echo 'local'"

        @driver.task(shell=True)
        def highway_task():
            return "echo 'highway'"

        local = driver.get_local_tasks()
        assert len(local) == 1
        assert "local_task" in local

    def test_get_highway_tasks(self):
        """get_highway_tasks returns only Highway tasks."""
        driver = Driver(api_key="test")

        @driver.task(shell=True, local=True)
        def local_task():
            return "echo 'local'"

        @driver.task(shell=True)
        def highway_task():
            return "echo 'highway'"

        highway = driver.get_highway_tasks()
        assert len(highway) == 1
        assert "highway_task" in highway


class TestLocalTaskValidation:
    """Tests for validation of local tasks."""

    def test_local_cannot_use_durable(self):
        """local=True cannot be combined with durable=True."""
        # Test at TaskDefinition level since driver.task() catches py+durable conflict first
        from highway.task import TaskDefinition

        with pytest.raises(ValueError, match="local=True cannot be used with durable=True"):
            TaskDefinition(
                name="invalid",
                func=lambda: None,
                task_type=TaskType.PYTHON,
                local=True,
                durable=True,
            )

    def test_local_cannot_use_schedule(self):
        """local=True cannot be combined with schedule."""
        driver = Driver()

        with pytest.raises(ValueError, match="local=True cannot be used with schedule="):
            @driver.task(shell=True, local=True, schedule="0 * * * *")
            def invalid_task():
                return "echo 'scheduled'"

    def test_local_cannot_use_delay(self):
        """local=True cannot be combined with delay."""
        from datetime import timedelta

        driver = Driver()

        with pytest.raises(ValueError, match="local=True cannot be used with delay="):
            @driver.task(shell=True, local=True, delay=timedelta(seconds=5))
            def invalid_task():
                return "echo 'delayed'"

    def test_local_only_supports_shell_py_http(self):
        """local=True only supports shell, py, http task types."""
        driver = Driver()

        # Control flow operators not supported with local
        # Note: foreach/while decorators don't have local parameter,
        # so this is enforced at TaskDefinition level
        from highway.task import TaskDefinition

        with pytest.raises(ValueError, match="local=True only supports shell, py, http"):
            TaskDefinition(
                name="invalid",
                func=lambda: None,
                task_type=TaskType.FOREACH,
                local=True,
            )


class TestMixedWorkflowValidation:
    """Tests for mixed local + Highway workflow validation."""

    def test_mixed_workflow_raises_not_supported(self):
        """Mixed local and Highway tasks raise NotSupportedError."""
        driver = Driver(api_key="test")

        @driver.task(shell=True, local=True)
        def local_task():
            return "echo 'local'"

        @driver.task(shell=True)
        def highway_task():
            return "echo 'highway'"

        with pytest.raises(NotSupportedError) as exc_info:
            driver.run(timeout=10)

        assert "Mixed local and Highway tasks" in str(exc_info.value)


class TestLocalTaskExecution:
    """Tests for actual local task execution."""

    def test_local_shell_task_executes(self):
        """Local shell task executes via Stabilize ShellTask."""
        driver = Driver()

        @driver.task(shell=True, local=True)
        def echo_hello():
            return "echo 'hello world'"

        result = driver.run(timeout=30)

        assert result.status == "completed"
        assert "echo_hello" in result.tasks
        task_result = result.tasks["echo_hello"]
        assert task_result.result["stdout"] == "hello world"
        assert task_result.result["returncode"] == 0

    def test_local_shell_task_with_dependencies(self):
        """Local shell tasks can have dependencies."""
        driver = Driver()

        @driver.task(shell=True, local=True)
        def step1():
            return "echo 'step1'"

        @driver.task(shell=True, local=True, depends=["step1"])
        def step2():
            return "echo 'step2'"

        result = driver.run(timeout=30)

        assert result.status == "completed"
        assert "step1" in result.tasks
        assert "step2" in result.tasks

    def test_local_shell_task_failure(self):
        """Local shell task failure is reported correctly."""
        driver = Driver()

        @driver.task(shell=True, local=True)
        def fail_task():
            return "exit 1"

        result = driver.run(timeout=30)

        assert result.status == "failed"
        assert "fail_task" in result.tasks
        task_result = result.tasks["fail_task"]
        assert task_result.state.name == "FAILED"
        assert task_result.result["returncode"] == 1
        assert "exited with code 1" in task_result.error

    def test_local_http_task_executes(self):
        """Local HTTP task executes via Stabilize HTTPTask."""
        driver = Driver()

        @driver.task(http=True, local=True)
        def http_get():
            return {
                "url": "https://httpbin.org/get",
                "method": "GET",
            }

        result = driver.run(timeout=30)

        assert result.status == "completed"
        assert "http_get" in result.tasks
        task_result = result.tasks["http_get"]
        assert task_result.result["status_code"] == 200


class TestLocalTaskParallelism:
    """Tests for parallel local task execution via DAG."""

    def test_parallel_dag_structure(self):
        """Parallel tasks have correct DAG dependencies."""
        from highway.runner import HighwayRunner

        driver = Driver()

        @driver.task(shell=True, local=True)
        def setup():
            return "echo 'setup'"

        @driver.task(shell=True, local=True, depends=["setup"])
        def task_a():
            return "echo 'A'"

        @driver.task(shell=True, local=True, depends=["setup"])
        def task_b():
            return "echo 'B'"

        @driver.task(shell=True, local=True, depends=["task_a", "task_b"])
        def finalize():
            return "echo 'done'"

        local_tasks = driver.get_local_tasks()
        runner = HighwayRunner()
        workflow = runner._create_local_workflow(local_tasks, {})

        # Verify DAG structure
        stages_by_ref = {s.ref_id: s for s in workflow.stages}

        assert stages_by_ref["setup"].requisite_stage_ref_ids == set()
        assert stages_by_ref["task_a"].requisite_stage_ref_ids == {"setup"}
        assert stages_by_ref["task_b"].requisite_stage_ref_ids == {"setup"}
        assert stages_by_ref["finalize"].requisite_stage_ref_ids == {"task_a", "task_b"}
