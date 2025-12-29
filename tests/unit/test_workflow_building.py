#!/usr/bin/env python3
"""Unit tests for workflow building and validation.

These tests verify workflow JSON generation and parameter validation
without requiring Highway API or execution.
"""

from datetime import timedelta

import pytest

from highway import Driver, TaskDefinitionError


def test_schedule_with_timedelta() -> None:
    """Verify timedelta schedule is converted to interval string."""
    driver = Driver()

    @driver.task(shell=True, schedule=timedelta(hours=1))
    def hourly_task():
        return "echo 'hourly'"

    task_def = driver.tasks["hourly_task"]
    assert task_def.schedule == "@every 3600s"


def test_delay_workflow_json_generation() -> None:
    """Verify delay generates correct wait task in workflow JSON."""
    driver = Driver()

    @driver.task(shell=True)
    def initial_task():
        return "echo 'initial'"

    @driver.task(shell=True, delay=timedelta(hours=2), depends=["initial_task"])
    def delayed_task():
        return "echo 'delayed'"

    workflow_json = driver._build_workflow(workflow_timeout=300)

    # Should have 3 tasks: initial_task, delayed_task_wait, delayed_task
    assert "initial_task" in workflow_json["tasks"]
    assert "delayed_task_wait" in workflow_json["tasks"]
    assert "delayed_task" in workflow_json["tasks"]

    # Verify wait task structure
    wait_task = workflow_json["tasks"]["delayed_task_wait"]
    assert wait_task["operator_type"] == "wait"
    assert wait_task["wait_for"] == "PT7200S"  # 2 hours = 7200 seconds
    assert wait_task["dependencies"] == ["initial_task"]

    # Verify delayed task depends on wait task, not original
    delayed_task = workflow_json["tasks"]["delayed_task"]
    assert delayed_task["dependencies"] == ["delayed_task_wait"]


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


def test_delay_start_task_no_dependencies() -> None:
    """Verify delay works on start task with no dependencies."""
    driver = Driver()

    @driver.task(shell=True, delay=timedelta(seconds=1))
    def delayed_start():
        return "echo 'delayed start'"

    workflow_json = driver._build_workflow(workflow_timeout=300)

    # Wait task should have no dependencies (empty list)
    wait_task = workflow_json["tasks"]["delayed_start_wait"]
    assert wait_task["dependencies"] == []
    assert wait_task["operator_type"] == "wait"
    assert wait_task["wait_for"] == "PT1S"

    # start_task should be the wait task, not the original
    assert workflow_json["start_task"] == "delayed_start_wait"


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
    assert "start_task" in workflow_json
    assert workflow_json["timeout_seconds"] == 300


def test_retry_configuration_in_json() -> None:
    """Verify retry config is correctly added to workflow JSON."""
    driver = Driver()

    @driver.task(shell=True, retries=3, retry_delay=2.0, backoff=1.5)
    def retryable_task():
        return "echo 'retry'"

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["retryable_task"]

    assert "retry_policy" in task_json
    assert task_json["retry_policy"]["max_attempts"] == 4  # 3 retries + 1 initial
    assert task_json["retry_policy"]["initial_interval_seconds"] == 2.0
    assert task_json["retry_policy"]["backoff_coefficient"] == 1.5


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


def test_python_task_generates_code_exec() -> None:
    """Verify py=True generates tools.code.exec with wrapped source."""
    driver = Driver()

    @driver.task(py=True)
    def compute_sum():
        return {"sum": 1 + 2}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["compute_sum"]

    assert task_json["function"] == "tools.code.exec"
    assert "code" in task_json["kwargs"]
    assert "compute_sum" in task_json["kwargs"]["code"]
    assert "__HIGHWAY_RESULT__" in task_json["kwargs"]["code"]
    assert task_json["kwargs"]["timeout"] == 300


def test_generic_tool_task() -> None:
    """Verify tool= parameter generates correct workflow JSON."""
    driver = Driver()

    @driver.task(tool="tools.llm.call")
    def summarize():
        return {
            "prompt": "Summarize this",
            "model": "claude-3-haiku-20240307",
        }

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["summarize"]

    assert task_json["function"] == "tools.llm.call"
    assert task_json["kwargs"]["prompt"] == "Summarize this"
    assert task_json["kwargs"]["model"] == "claude-3-haiku-20240307"


def test_workflow_execution_by_name() -> None:
    """Verify workflow= parameter generates tools.workflow.execute."""
    driver = Driver()

    @driver.task(workflow="daily_report")
    def run_report():
        return {"inputs": {"date": "2024-01-01"}}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["run_report"]

    assert task_json["function"] == "tools.workflow.execute"
    assert task_json["kwargs"]["workflow_name"] == "daily_report"
    assert task_json["kwargs"]["inputs"] == {"date": "2024-01-01"}


def test_workflow_execution_by_id() -> None:
    """Verify workflow_id= parameter generates tools.workflow.execute with definition_id."""
    driver = Driver()

    @driver.task(workflow_id="550e8400-e29b-41d4-a716-446655440000")
    def run_specific():
        return {"inputs": {"mode": "production"}}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["run_specific"]

    assert task_json["function"] == "tools.workflow.execute"
    assert task_json["kwargs"]["definition_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert task_json["kwargs"]["inputs"] == {"mode": "production"}


def test_tool_with_variable_interpolation() -> None:
    """Verify {{variable}} syntax passes through for Highway resolution."""
    driver = Driver()

    @driver.task(shell=True)
    def backup():
        return "pg_dump > backup.sql"

    @driver.task(tool="tools.llm.call", depends=["backup"])
    def analyze():
        return {
            "prompt": "Analyze: {{backup_result.stdout}}",
            "model": "gpt-4",
        }

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["analyze"]

    # Verify variable syntax is preserved for Highway
    assert task_json["kwargs"]["prompt"] == "Analyze: {{backup_result.stdout}}"


# =============================================================================
# Control Flow Decorator Tests
# =============================================================================


def test_foreach_decorator_generates_foreach_operator() -> None:
    """Verify @driver.foreach generates correct foreach operator JSON."""
    driver = Driver()

    @driver.task(py=True)
    def get_items():
        return {"items": [1, 2, 3]}

    @driver.foreach(items="{{get_items_result.items}}", depends=["get_items"])
    def process_item():
        return {"processed": True}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["process_item"]

    assert task_json["operator_type"] == "foreach"
    assert task_json["items"] == "{{get_items_result.items}}"
    assert "loop_body" in task_json
    assert isinstance(task_json["loop_body"], list)
    assert task_json["loop_body"][0]["function"] == "tools.code.exec"
    assert "process_item" in task_json["loop_body"][0]["kwargs"]["code"]
    assert task_json["loop_body"][0]["is_internal_loop_task"] is True
    assert task_json["parallel"] is False


def test_while_loop_decorator_generates_while_operator() -> None:
    """Verify @driver.while_loop generates correct while operator JSON.

    Note: while_loop defaults to durable=True for DurableContext support.
    """
    driver = Driver()

    @driver.task(py=True)
    def init():
        return {"counter": 0, "limit": 5}

    @driver.while_loop(condition="{{counter}} < {{limit}}", depends=["init"])
    def increment():
        return {"incremented": True}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["increment"]

    assert task_json["operator_type"] == "while"
    assert task_json["condition"] == "{{counter}} < {{limit}}"
    assert "loop_body" in task_json
    assert isinstance(task_json["loop_body"], list)
    # Default durable=True uses tools.python.run
    assert task_json["loop_body"][0]["function"] == "tools.python.run"
    assert task_json["loop_body"][0]["is_internal_loop_task"] is True


def test_while_loop_non_durable_uses_code_exec() -> None:
    """Verify @driver.while_loop with durable=False uses tools.code.exec."""
    driver = Driver()

    @driver.task(py=True)
    def init():
        return {"counter": 0, "limit": 5}

    @driver.while_loop(condition="{{counter}} < {{limit}}", depends=["init"], durable=False)
    def increment():
        return {"incremented": True}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["increment"]

    assert task_json["operator_type"] == "while"
    assert task_json["loop_body"][0]["function"] == "tools.code.exec"
    assert "code" in task_json["loop_body"][0]["kwargs"]


def test_emit_decorator_generates_emit_event_operator() -> None:
    """Verify @driver.emit generates correct emit_event operator JSON."""
    driver = Driver()

    @driver.emit(event="workflow_ready", payload={"status": "ready"})
    def send_signal():
        pass

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["send_signal"]

    assert task_json["operator_type"] == "emit_event"
    assert task_json["event_name"] == "workflow_ready"
    assert task_json["payload"] == {"status": "ready"}


def test_wait_for_decorator_generates_wait_for_event_operator() -> None:
    """Verify @driver.wait_for generates correct wait_for_event operator JSON."""
    driver = Driver()

    @driver.wait_for(event="external_signal", timeout=60)
    def receive_signal():
        pass

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["receive_signal"]

    assert task_json["operator_type"] == "wait_for_event"
    assert task_json["event_name"] == "external_signal"
    assert task_json["timeout_seconds"] == 60


def test_emit_wait_for_chain() -> None:
    """Verify emit -> wait_for chain works correctly."""
    driver = Driver()

    @driver.emit(event="task_complete", payload={"id": "123"})
    def emit_completion():
        pass

    @driver.wait_for(event="task_complete", timeout=30, depends=["emit_completion"])
    def wait_completion():
        pass

    @driver.task(py=True, depends=["wait_completion"])
    def verify():
        return {"chain_complete": True}

    workflow_json = driver._build_workflow(workflow_timeout=300)

    emit_task = workflow_json["tasks"]["emit_completion"]
    wait_task = workflow_json["tasks"]["wait_completion"]
    verify_task = workflow_json["tasks"]["verify"]

    assert emit_task["operator_type"] == "emit_event"
    assert wait_task["operator_type"] == "wait_for_event"
    assert wait_task["dependencies"] == ["emit_completion"]
    assert verify_task["dependencies"] == ["wait_completion"]


def test_foreach_with_timeout() -> None:
    """Verify foreach respects timeout parameter."""
    driver = Driver()

    @driver.foreach(items="{{items}}", timeout=60)
    def process():
        return {"done": True}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["process"]

    assert task_json["loop_body"][0]["kwargs"]["timeout"] == 60


# =============================================================================
# Durable Python Task Tests (tools.python.run)
# =============================================================================


def test_durable_task_generates_python_run() -> None:
    """Verify durable=True generates tools.python.run DSL."""
    driver = Driver()

    @driver.task(durable=True)
    def my_durable_func():
        return {"result": 42}

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["my_durable_func"]

    assert task_json["function"] == "tools.python.run"
    # Uses wrapper function for ctx injection
    assert task_json["args"] == ["driver_tasks.tasks._hw_my_durable_func"]
    assert task_json["kwargs"] == {"artifact_id": "{{_artifact_id}}"}


def test_durable_task_with_package() -> None:
    """Verify package= parameter generates correct entrypoint."""
    driver = Driver()

    @driver.task(durable=True, package="./my_package", entrypoint="main:run")
    def my_task():
        pass

    workflow_json = driver._build_workflow(workflow_timeout=300)
    task_json = workflow_json["tasks"]["my_task"]

    assert task_json["function"] == "tools.python.run"
    assert task_json["args"] == ["my_package.main.run"]
    assert task_json["kwargs"] == {"artifact_id": "{{_artifact_id}}"}


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
    result = package_functions({
        "without_ctx": without_ctx,
        "with_ctx": with_ctx,
    })

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
