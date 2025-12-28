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
