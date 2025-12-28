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
