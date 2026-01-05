#!/usr/bin/env python3
"""Unit tests for workflow building and validation.

These tests verify workflow building and parameter validation
without requiring Highway API or execution.
"""

from datetime import timedelta

import pytest

from highway import Driver, TaskDefinitionError

# =============================================================================
# TaskDefinition Validation Tests
# =============================================================================


def test_schedule_with_timedelta() -> None:
    """Verify timedelta schedule is converted to interval string."""
    driver = Driver()

    @driver.task(shell=True, schedule=timedelta(hours=1))
    def hourly_task():
        return "echo 'hourly'"

    task_def = driver.tasks["hourly_task"]
    assert task_def.schedule == "@every 3600s"


def test_delay_and_schedule_not_allowed() -> None:
    """Verify delay and schedule cannot be used together."""
    driver = Driver()

    with pytest.raises(TaskDefinitionError) as exc_info:

        @driver.task(shell=True, delay=timedelta(hours=1), schedule="0 * * * *")
        def bad_task():
            return "echo 'bad'"

    assert "delay and schedule" in str(exc_info.value).lower()


def test_delay_negative_validation() -> None:
    """Verify negative delay raises error."""
    driver = Driver()

    with pytest.raises(ValueError) as exc_info:

        @driver.task(shell=True, delay=timedelta(seconds=-1))
        def negative_delay_task():
            return "echo 'bad'"

    assert "delay must be positive" in str(exc_info.value)


def test_dependency_validation() -> None:
    """Verify missing dependencies are caught."""
    driver = Driver()

    @driver.task(shell=True, depends=["nonexistent"])
    def dependent_task():
        return "echo 'depends'"

    with pytest.raises(TaskDefinitionError) as exc_info:
        driver.run()

    assert "nonexistent" in str(exc_info.value)


def test_duplicate_task_registration() -> None:
    """Verify duplicate task names are caught."""
    driver = Driver()

    @driver.task(shell=True)
    def my_task():
        return "echo 'first'"

    with pytest.raises(TaskDefinitionError) as exc_info:

        @driver.task(shell=True)
        def my_task():
            return "echo 'second'"

    assert "already registered" in str(exc_info.value)


def test_no_tasks_error() -> None:
    """Verify error when running with no tasks."""
    driver = Driver()

    with pytest.raises(TaskDefinitionError) as exc_info:
        driver.run()

    assert "No tasks registered" in str(exc_info.value)


def test_task_type_validation() -> None:
    """Verify exactly one task type must be specified."""
    driver = Driver()

    # No type specified
    with pytest.raises(TaskDefinitionError) as exc_info:

        @driver.task()
        def no_type():
            return "echo 'bad'"

    assert "Must specify exactly one task type" in str(exc_info.value)

    # Multiple types
    driver2 = Driver()
    with pytest.raises(TaskDefinitionError) as exc_info:

        @driver2.task(shell=True, py=True)
        def multi_type():
            return "echo 'bad'"

    assert "Only one task type" in str(exc_info.value)

    # Multiple new types
    driver3 = Driver()
    with pytest.raises(TaskDefinitionError) as exc_info:

        @driver3.task(tool="tools.llm.call", workflow="my_workflow")
        def multi_new_type():
            return {}

    assert "Only one task type" in str(exc_info.value)


def test_package_requires_durable() -> None:
    """Verify package= requires durable=True."""
    driver = Driver()

    with pytest.raises(ValueError) as exc_info:

        @driver.task(package="./my_package", entrypoint="main:run")
        def bad_task():
            pass

    assert "durable=True" in str(exc_info.value)


def test_package_requires_entrypoint() -> None:
    """Verify package= requires entrypoint=."""
    driver = Driver()

    with pytest.raises(ValueError) as exc_info:

        @driver.task(durable=True, package="./my_package")
        def bad_task():
            pass

    assert "entrypoint" in str(exc_info.value)


# =============================================================================
# Workflow Building Tests
# =============================================================================


def test_workflow_json_structure() -> None:
    """Verify basic workflow JSON structure."""
    driver = Driver()

    @driver.task(shell=True)
    def echo_task():
        return "echo 'hello'"

    workflow_json = driver._build_workflow(workflow_timeout=300)

    assert "name" in workflow_json
    assert "version" in workflow_json
    assert "tasks" in workflow_json
    assert workflow_json["timeout_seconds"] == 300


def test_inputs_in_workflow_json() -> None:
    """Verify inputs are included in workflow JSON variables."""
    driver = Driver()

    @driver.task(shell=True)
    def echo_input():
        return "echo '{{inputs.message}}'"

    workflow_json = driver._build_workflow(
        workflow_timeout=300, inputs={"message": "hello", "count": 42}
    )

    assert workflow_json["variables"] == {"message": "hello", "count": 42}


def test_multiple_tasks_build() -> None:
    """Verify multiple tasks can be built."""
    driver = Driver()

    @driver.task(shell=True)
    def task1():
        return "echo 'one'"

    @driver.task(shell=True, depends=["task1"])
    def task2():
        return "echo 'two'"

    @driver.task(py=True, depends=["task2"])
    def task3():
        return {"result": 3}

    workflow_json = driver._build_workflow(workflow_timeout=300)

    assert "task1" in workflow_json["tasks"]
    assert "task2" in workflow_json["tasks"]
    assert "task3" in workflow_json["tasks"]


def test_foreach_builds() -> None:
    """Verify foreach decorator creates task."""
    driver = Driver()

    @driver.task(py=True)
    def get_items():
        return {"items": [1, 2, 3]}

    @driver.foreach(items="{{get_items_result.items}}", depends=["get_items"])
    def process_item():
        return "echo 'item'"

    workflow_json = driver._build_workflow(workflow_timeout=300)

    assert "get_items" in workflow_json["tasks"]
    assert "process_item" in workflow_json["tasks"]


def test_while_loop_builds() -> None:
    """Verify while_loop decorator creates task."""
    driver = Driver()

    @driver.task(py=True)
    def init():
        return {"counter": 0}

    @driver.while_loop(condition="{{counter}} < 5", depends=["init"])
    def loop_body():
        return "echo 'loop'"

    workflow_json = driver._build_workflow(workflow_timeout=300)

    assert "init" in workflow_json["tasks"]
    assert "loop_body" in workflow_json["tasks"]


def test_emit_builds() -> None:
    """Verify emit decorator creates task."""
    driver = Driver()

    @driver.emit(event="my_event", payload={"key": "value"})
    def emit_task():
        pass

    workflow_json = driver._build_workflow(workflow_timeout=300)

    assert "emit_task" in workflow_json["tasks"]


def test_wait_for_builds() -> None:
    """Verify wait_for decorator creates task."""
    driver = Driver()

    @driver.wait_for(event="my_event", timeout=60)
    def wait_task():
        pass

    workflow_json = driver._build_workflow(workflow_timeout=300)

    assert "wait_task" in workflow_json["tasks"]


# =============================================================================
# Driver Configuration Tests
# =============================================================================


def test_needs_artifact_returns_true_for_durable() -> None:
    """Verify needs_artifact() returns True when durable tasks exist."""
    driver = Driver()

    @driver.task(py=True)
    def regular_task():
        return {"result": 1}

    assert driver.needs_artifact() is False

    @driver.task(durable=True)
    def durable_task():
        return {"result": 2}

    assert driver.needs_artifact() is True


def test_get_durable_functions_returns_only_durable() -> None:
    """Verify get_durable_functions() returns only durable functions."""
    driver = Driver()

    @driver.task(py=True)
    def regular():
        return {"a": 1}

    @driver.task(durable=True)
    def durable():
        return {"b": 2}

    funcs = driver.get_durable_functions()
    assert "regular" not in funcs
    assert "durable" in funcs
    assert funcs["durable"].__name__ == "durable"


def test_wrapper_generation_handles_ctx_detection() -> None:
    """Verify wrapper functions correctly detect ctx parameter.

    Tests the critical ctx injection fix:
    - Functions WITH ctx param: wrapper passes ctx through
    - Functions WITHOUT ctx param: wrapper sets thread-local for get_context()
    """
    import sys
    import tempfile
    import zipfile

    from highway.artifact import package_functions

    # Function WITHOUT ctx - should use get_context()
    def without_ctx(order_id: int):
        return {"order_id": order_id}

    # Function WITH ctx - should get ctx passed through
    def with_ctx(ctx, order_id: int):
        return {"order_id": order_id, "ctx_present": True}

    # Package them
    result = package_functions(
        {
            "without_ctx": without_ctx,
            "with_ctx": with_ctx,
        }
    )

    # Extract and test
    tmpdir = tempfile.mkdtemp()
    with zipfile.ZipFile(result.file_path, "r") as zf:
        zf.extractall(tmpdir)

    sys.path.insert(0, tmpdir)
    try:
        from driver_tasks import tasks

        # Mock DurableContext
        class MockCtx:
            def __init__(self):
                self.variables = {}

            def set_variable(self, k, v):
                self.variables[k] = v

            def get_variable(self, k):
                return self.variables.get(k)

        mock_ctx = MockCtx()

        # Test wrapper for function WITHOUT ctx
        result1 = tasks._hw_without_ctx(mock_ctx, 123)
        assert result1 == {"order_id": 123}

        # Test wrapper for function WITH ctx
        result2 = tasks._hw_with_ctx(mock_ctx, 456)
        assert result2 == {"order_id": 456, "ctx_present": True}

    finally:
        sys.path.remove(tmpdir)


def test_driver_name_parameter() -> None:
    """Verify Driver name parameter sets workflow name."""
    driver = Driver(name="my_custom_workflow")

    @driver.task(shell=True)
    def my_task():
        return "echo test"

    workflow = driver._build_workflow()
    assert workflow["name"] == "my_custom_workflow"


def test_driver_name_auto_derived() -> None:
    """Verify workflow name auto-derives from first task when not specified."""
    driver = Driver()

    @driver.task(shell=True)
    def process_orders():
        return "echo orders"

    workflow = driver._build_workflow()
    assert workflow["name"] == "workflow_process_orders"


def test_driver_name_converts_dashes_to_underscores() -> None:
    """Verify dashes in workflow name are converted to underscores."""
    driver = Driver(name="my-workflow-name")

    @driver.task(shell=True)
    def my_task():
        return "echo test"

    workflow = driver._build_workflow()
    assert workflow["name"] == "my_workflow_name"


def test_clear_removes_all_tasks() -> None:
    """Verify clear() removes all registered tasks."""
    driver = Driver()

    @driver.task(shell=True)
    def task1():
        return "echo 1"

    @driver.task(shell=True)
    def task2():
        return "echo 2"

    assert len(driver.tasks) == 2
    driver.clear()
    assert len(driver.tasks) == 0
