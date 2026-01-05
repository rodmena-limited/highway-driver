"""Main Highway Driver class with @task decorator.

This is the primary interface for the Highway Driver SDK.
Users import Driver and use @driver.task() to define workflows.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from highway.ast_utils import FunctionAnalyzer
from highway.builder import DriverWorkflowBuilder
from highway.exceptions import (
    ConfigurationError,
    ExecutionError,
    NotSupportedError,
    TaskDefinitionError,
)
from highway.result import TaskResult, WorkflowResult, WorkflowState
from highway.runner import StabilizeRunner
from highway.task import TaskDefinition, TaskType

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class Driver:
    """Highway Driver - Simple decorator SDK for Highway Workflow Engine.

    The Driver class provides a DBOS-style decorator interface for defining
    and executing workflows on Highway. It handles:

    - Task registration via @driver.task() decorator
    - Workflow DSL generation via highway_dsl
    - Direct execution via Highway API
    - Status polling and result retrieval

    Example:
        from highway import Driver

        driver = Driver()  # Uses HIGHWAY_API_KEY env var

        @driver.task(shell=True)
        def backup_db():
            return "pg_dump mydb > backup.sql"

        @driver.task(py=True, depends=["backup_db"])
        def verify_backup():
            import os
            return os.path.exists("backup.sql")

        result = driver.run()
        print(result.status)  # "completed"

    Attributes:
        api_key: Highway API key for authentication
        endpoint: Highway API endpoint URL
        tasks: Registered task definitions
    """

    def __init__(
        self,
        name: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        """Initialize Highway Driver.

        Args:
            name: Workflow name. If not provided, auto-generates from first task
                  or uses 'driver_workflow_<uuid>'.
            api_key: Highway API key. If not provided, reads from
                     HIGHWAY_API_KEY environment variable.
            endpoint: Highway API endpoint URL.
                      Defaults to https://highway.run

        Example:
            driver = Driver(name="payment-processor")  # Explicit name
            driver = Driver()  # Auto: 'workflow_<first_task>' or 'driver_workflow_<uuid>'
        """
        self._name = name
        self.api_key = api_key or os.environ.get("HIGHWAY_API_KEY", "")
        self.endpoint = endpoint or os.environ.get("HIGHWAY_API_ENDPOINT", "https://highway.run")
        self._tasks: dict[str, TaskDefinition] = {}
        self._analyzer = FunctionAnalyzer()
        self._runner: StabilizeRunner | None = None

    @property
    def tasks(self) -> dict[str, TaskDefinition]:
        """Get all registered tasks."""
        return self._tasks.copy()

    def _get_runner(self) -> StabilizeRunner:
        """Get or create the Stabilize runner."""
        if self._runner is None:
            if not self.api_key:
                raise ConfigurationError(
                    "HIGHWAY_API_KEY not configured. "
                    "Set environment variable or pass api_key to Driver()"
                )
            self._runner = StabilizeRunner(
                api_key=self.api_key,
                api_endpoint=self.endpoint,
            )
        return self._runner

    def task(
        self,
        shell: bool = False,
        py: bool = False,
        http: bool = False,
        tool: str | None = None,
        workflow: str | None = None,
        workflow_id: str | None = None,
        depends: list[str] | None = None,
        timeout: int = 300,
        schedule: str | timedelta | None = None,
        run_at: str | None = None,
        retries: int = 0,
        retry_delay: float = 1.0,
        backoff: float = 2.0,
        delay: timedelta | None = None,
        durable: bool = False,
        package: str | None = None,
        entrypoint: str | None = None,
        func_args: list[Any] | None = None,
        func_kwargs: dict[str, Any] | None = None,
    ) -> Callable[[F], F]:
        """Decorator to register a task with the Driver.

        Tasks are executed on Highway Workflow Engine. The function body
        defines what the task does:

        - shell=True: Function returns a shell command string
        - py=True: Function is executed as Python code via tools.python.run
        - http=True: Function returns HTTP request configuration
        - tool="tools.X.Y": Function returns kwargs for any Highway tool
        - workflow="name": Execute another workflow by name (latest version)
        - workflow_id="uuid": Execute specific workflow version by definition_id

        Args:
            shell: Execute as shell command (function returns command string)
            py: Execute as Python code on Highway via tools.python.run
            http: Execute as HTTP request (function returns config dict)
            tool: Highway tool name (e.g., "tools.llm.call", "tools.database.query")
            workflow: Execute workflow by name (uses latest version)
            workflow_id: Execute specific workflow version by definition_id (UUID)
            depends: List of task names this depends on
            timeout: Execution timeout in seconds
            schedule: Recurring schedule - cron expression string (e.g., "0 * * * *")
                      or timedelta for interval-based scheduling
            run_at: Specific execution time (NotImplemented)
            retries: Number of retry attempts on failure
            retry_delay: Initial delay between retries in seconds
            backoff: Multiplier for exponential backoff (default 2.0)
            delay: Durable delay before task execution. Uses Highway's native
                   WaitOperator which suspends the workflow consuming ZERO
                   worker resources during the wait period.
            durable: Use tools.python.run with DurableContext for mutable workflow
                     variables. Enables ctx.set_variable() / ctx.get_variable().
            package: Path to Python package directory to upload as artifact.
                     Requires durable=True. Package will be uploaded and available
                     to the function at runtime.
            entrypoint: Module:function path for package mode (e.g., "main:run").
                        Required when package is specified.

        Returns:
            Decorated function (unchanged)

        Raises:
            TaskDefinitionError: If task definition is invalid
            NotSupportedError: If unsupported parameter is used

        Example:
            @driver.task(shell=True)
            def list_files():
                return "ls -la /tmp"

            @driver.task(py=True, depends=["list_files"])
            def process_output(list_files):
                return {"processed": True}

            @driver.task(http=True, retries=3, retry_delay=2.0, backoff=2.0)
            def call_webhook():
                return {
                    "url": "https://api.example.com/webhook",
                    "method": "POST",
                    "json": {"status": "done"}
                }

            @driver.task(tool="tools.llm.call")
            def summarize():
                return {
                    "prompt": "Summarize: {{list_files_result.stdout}}",
                    "model": "claude-3-haiku-20240307"
                }

            @driver.task(workflow="send_report")
            def trigger_report():
                return {"inputs": {"date": "2024-01-01"}}
        """
        # Validate package/entrypoint requirements
        if package is not None and not durable:
            raise ValueError("package requires durable=True")
        if package is not None and entrypoint is None:
            raise ValueError("package requires entrypoint (e.g., 'main:run')")

        # Validate task type - exactly one must be specified
        type_flags = [
            shell,
            py,
            http,
            tool is not None,
            workflow is not None,
            workflow_id is not None,
            durable,
        ]
        if sum(type_flags) == 0:
            raise TaskDefinitionError(
                "Must specify exactly one task type: shell=True, py=True, http=True, "
                "durable=True, tool='...', workflow='...', or workflow_id='...'"
            )
        if sum(type_flags) > 1:
            specified = []
            if shell:
                specified.append("shell")
            if py:
                specified.append("py")
            if http:
                specified.append("http")
            if durable:
                specified.append("durable")
            if tool:
                specified.append(f"tool='{tool}'")
            if workflow:
                specified.append(f"workflow='{workflow}'")
            if workflow_id:
                specified.append(f"workflow_id='{workflow_id}'")
            raise TaskDefinitionError(f"Only one task type allowed. Got: {', '.join(specified)}")

        # Check for unsupported features
        if run_at is not None:
            raise NotSupportedError("run_at parameter", "issuedb DRIVER-015")

        # Validate delay + schedule combination
        if delay is not None and schedule is not None:
            raise TaskDefinitionError(
                "Cannot use both delay and schedule together. "
                "delay is for one-time delayed execution, "
                "schedule is for recurring execution."
            )

        # Convert timedelta schedule to cron-like interval string
        schedule_str: str | None = None
        if schedule is not None:
            if isinstance(schedule, timedelta):
                total_seconds = int(schedule.total_seconds())
                schedule_str = f"@every {total_seconds}s"
            else:
                schedule_str = schedule

        # Determine task type
        if shell:
            task_type = TaskType.SHELL
        elif py or durable:
            task_type = TaskType.PYTHON
        elif http:
            task_type = TaskType.HTTP
        elif tool:
            task_type = TaskType.TOOL
        else:
            task_type = TaskType.WORKFLOW

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError(f"Task '{func.__name__}' is already registered")

            analysis = self._analyzer.analyze(func)

            task_def = TaskDefinition(
                name=func.__name__,
                func=func,
                task_type=task_type,
                depends=depends or [],
                timeout=timeout,
                schedule=schedule_str,
                retries=retries,
                retry_delay=retry_delay,
                backoff_rate=backoff,
                delay=delay,
                tool_name=tool,
                workflow_name=workflow,
                workflow_definition_id=workflow_id,
                analysis=analysis,
                durable=durable,
                package=package,
                entrypoint=entrypoint,
                func_args=func_args,
                func_kwargs=func_kwargs,
            )

            self._tasks[func.__name__] = task_def
            logger.info(
                "Registered task '%s' (type=%s, durable=%s, depends=%s)",
                func.__name__,
                task_type.name,
                durable,
                depends or [],
            )
            return func

        return decorator

    def foreach(
        self,
        items: str,
        depends: list[str] | None = None,
        timeout: int = 300,
    ) -> Callable[[F], F]:
        """Decorator to define a ForEach loop over a collection.

        The decorated function is executed once for each item in the collection.
        The current item is available via {{current_item}} variable.

        Args:
            items: Variable reference for the collection (e.g., "{{item_list}}")
            depends: List of task names this depends on
            timeout: Execution timeout in seconds per iteration

        Returns:
            Decorated function

        Example:
            @driver.task(py=True)
            def get_items():
                return {"item_list": [1, 2, 3, 4, 5]}

            @driver.foreach(items="{{get_items_result.item_list}}", depends=["get_items"])
            def process_item():
                return "echo 'Processing item {{current_item}}'"

            @driver.task(py=True, depends=["process_item"])
            def verify_all():
                return {"all_processed": True}
        """

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError(f"Task '{func.__name__}' is already registered")

            analysis = self._analyzer.analyze(func)

            task_def = TaskDefinition(
                name=func.__name__,
                func=func,
                task_type=TaskType.FOREACH,
                depends=depends or [],
                timeout=timeout,
                items=items,
                analysis=analysis,
            )

            self._tasks[func.__name__] = task_def
            logger.info(
                "Registered foreach '%s' (items=%s, depends=%s)",
                func.__name__,
                items,
                depends or [],
            )
            return func

        return decorator

    def while_loop(
        self,
        condition: str,
        depends: list[str] | None = None,
        timeout: int = 300,
        max_iterations: int = 100,
    ) -> Callable[[F], F]:
        """Decorator to define a While loop with a condition.

        The decorated function is executed repeatedly while condition is true.

        Args:
            condition: Expression to evaluate (e.g., "{{counter}} < 10")
            depends: List of task names this depends on
            timeout: Execution timeout in seconds per iteration
            max_iterations: Safety limit on iterations (default 100)

        Returns:
            Decorated function

        Example:
            @driver.task(py=True)
            def init():
                return {"counter": 0, "limit": 5}

            @driver.while_loop(condition="{{init_result.counter}} < {{init_result.limit}}", depends=["init"])
            def increment():
                return "echo 'Iteration'"
        """

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError(f"Task '{func.__name__}' is already registered")

            analysis = self._analyzer.analyze(func)

            task_def = TaskDefinition(
                name=func.__name__,
                func=func,
                task_type=TaskType.WHILE,
                depends=depends or [],
                timeout=timeout,
                condition=condition,
                analysis=analysis,
            )

            self._tasks[func.__name__] = task_def
            logger.info(
                "Registered while_loop '%s' (condition=%s, max_iter=%d)",
                func.__name__,
                condition,
                max_iterations,
            )
            return func

        return decorator

    def emit(
        self,
        event: str,
        payload: dict[str, Any] | None = None,
        depends: list[str] | None = None,
    ) -> Callable[[F], F]:
        """Decorator to emit an event during workflow execution.

        Args:
            event: Name of the event to emit
            payload: Static payload for the event (can include variables)
            depends: List of task names this depends on

        Returns:
            Decorated function

        Example:
            @driver.task(py=True)
            def setup():
                return {"workflow_id": "123"}

            @driver.emit(event="workflow_ready", payload={"id": "{{setup_result.workflow_id}}"}, depends=["setup"])
            def signal_ready():
                pass  # Marker function - actual emission handled by Highway
        """

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError(f"Task '{func.__name__}' is already registered")

            task_def = TaskDefinition(
                name=func.__name__,
                func=func,
                task_type=TaskType.EMIT,
                depends=depends or [],
                event_name=event,
                event_payload=payload or {},
            )

            self._tasks[func.__name__] = task_def
            logger.info(
                "Registered emit '%s' (event=%s, depends=%s)",
                func.__name__,
                event,
                depends or [],
            )
            return func

        return decorator

    def wait_for(
        self,
        event: str,
        timeout: int = 30,
        depends: list[str] | None = None,
    ) -> Callable[[F], F]:
        """Decorator to wait for an event during workflow execution.

        Suspends workflow execution until the specified event is received
        or timeout is reached.

        Args:
            event: Name of the event to wait for
            timeout: Maximum wait time in seconds
            depends: List of task names this depends on

        Returns:
            Decorated function

        Example:
            @driver.emit(event="task_ready")
            def send_signal():
                pass

            @driver.wait_for(event="task_ready", timeout=60, depends=["send_signal"])
            def receive_signal():
                pass  # Marker function - actual wait handled by Highway
        """

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError(f"Task '{func.__name__}' is already registered")

            task_def = TaskDefinition(
                name=func.__name__,
                func=func,
                task_type=TaskType.WAIT_FOR,
                depends=depends or [],
                event_name=event,
                event_timeout=timeout,
            )

            self._tasks[func.__name__] = task_def
            logger.info(
                "Registered wait_for '%s' (event=%s, timeout=%ds)",
                func.__name__,
                event,
                timeout,
            )
            return func

        return decorator

    def run(
        self,
        wait: bool = True,
        timeout: float = 300,
        workflow_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Execute all registered tasks as a workflow.

        Args:
            wait: If True, wait for completion. If False, return immediately
                  with run_id for async polling.
            timeout: Maximum time to wait for completion in seconds
            workflow_id: Custom workflow ID for idempotency. If the same
                        workflow_id is used for multiple runs, Highway will
                        return the existing workflow instead of creating a new one.
                        If not provided, a unique ID is generated.
            inputs: Workflow input variables. These are available in tasks via
                   {{inputs.key}} syntax. Example: inputs={"email": "user@example.com"}

        Returns:
            WorkflowResult with execution status and task results

        Raises:
            ConfigurationError: If API key is missing
            TaskDefinitionError: If no tasks registered or invalid dependencies

        Example:
            # Idempotent execution - same workflow_id returns same result
            result1 = driver.run(workflow_id="order-12345")
            result2 = driver.run(workflow_id="order-12345")  # Returns cached result
        """
        if not self._tasks:
            raise TaskDefinitionError("No tasks registered. Use @driver.task()")

        # Validate all dependencies exist
        task_names = set(self._tasks.keys())
        for task in self._tasks.values():
            errors = task.validate_depends(task_names)
            if errors:
                raise TaskDefinitionError("; ".join(errors))

        # Build workflow using highway_dsl
        workflow_name = self._get_workflow_name()
        builder = DriverWorkflowBuilder(workflow_name, version="1.0.0")

        for task_def in self._tasks.values():
            builder.add_task(task_def)

        workflow_json = builder.build()
        workflow_json["timeout_seconds"] = int(timeout)

        # Add inputs as variables
        if inputs:
            workflow_json["variables"] = inputs

        # Submit via Stabilize (provides durability, crash recovery, monitoring)
        runner = self._get_runner()
        exec_id = runner.submit(
            workflow_definition=workflow_json,
            inputs=inputs,
            workflow_name=workflow_name,
        )

        if not wait:
            return WorkflowResult(
                run_id=exec_id,
                status="running",
                state=WorkflowState.RUNNING,
                tasks={},
            )

        # Wait for completion (polls local SQLite via Stabilize)
        try:
            result = runner.wait(exec_id, timeout=timeout)
            return self._parse_stabilize_result(exec_id, result)

        except ExecutionError as e:
            return WorkflowResult(
                run_id=exec_id,
                status="failed",
                state=WorkflowState.FAILED,
                error=str(e),
                tasks={},
            )

        except TimeoutError as e:
            return WorkflowResult(
                run_id=exec_id,
                status="running",
                state=WorkflowState.RUNNING,
                error=str(e),
                tasks={},
            )

    def _get_workflow_name(self) -> str:
        """Generate workflow name."""
        if self._name:
            return self._name.replace("-", "_")
        elif self._tasks:
            first_task = next(iter(self._tasks.keys()))
            return f"workflow_{first_task}"
        else:
            return f"driver_workflow_{uuid.uuid4().hex[:8]}"

    def _parse_stabilize_result(
        self, exec_id: str, stabilize_data: dict[str, Any]
    ) -> WorkflowResult:
        """Parse Stabilize runner result into WorkflowResult."""
        # Map Stabilize status to our enum
        status_str = stabilize_data.get("status", "unknown")
        highway_status = stabilize_data.get("highway_status", status_str)

        state_map = {
            "completed": WorkflowState.COMPLETED,
            "succeeded": WorkflowState.COMPLETED,
            "failed": WorkflowState.FAILED,
            "cancelled": WorkflowState.CANCELLED,
            "running": WorkflowState.RUNNING,
            "pending": WorkflowState.PENDING,
        }
        state = state_map.get(highway_status, WorkflowState.RUNNING)

        # Parse task results from Highway result stored in Stabilize
        tasks: dict[str, TaskResult] = {}
        highway_result = stabilize_data.get("highway_result", {})

        if isinstance(highway_result, dict):
            for task_name, task_data in highway_result.items():
                if isinstance(task_data, dict):
                    # Highway wraps code execution results in {'result': actual_result, ...}
                    actual_result = task_data
                    if "result" in task_data and isinstance(task_data.get("result"), dict):
                        actual_result = task_data["result"]
                    elif "result" in task_data and task_data.get("success"):
                        actual_result = task_data["result"]

                    tasks[task_name] = TaskResult(
                        name=task_name,
                        state=WorkflowState.COMPLETED,
                        result=actual_result,
                        error=task_data.get("error"),
                    )

        return WorkflowResult(
            run_id=exec_id,
            status=highway_status,
            state=state,
            tasks=tasks,
            error=stabilize_data.get("error"),
        )

    def status(self, run_id: str) -> WorkflowResult:
        """Get current status of a workflow from local store.

        This uses the local SQLite database via Stabilize, avoiding
        unnecessary Highway API calls.

        Args:
            run_id: Stabilize execution ID (returned from run())

        Returns:
            WorkflowResult with current state
        """
        runner = self._get_runner()
        result = runner.status(run_id)
        return self._parse_stabilize_result(run_id, result)

    def cancel(self, run_id: str) -> bool:
        """Cancel a running workflow.

        Args:
            run_id: Stabilize execution ID

        Returns:
            True if cancellation was initiated
        """
        runner = self._get_runner()
        return runner.cancel(run_id)

    def list_workflows(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[WorkflowResult]:
        """List workflows from local store.

        This uses the local SQLite database via Stabilize for fast
        queries without calling the Highway API.

        Args:
            status: Filter by status (running/succeeded/failed)
            limit: Maximum number of workflows to return

        Returns:
            List of WorkflowResult objects
        """
        runner = self._get_runner()
        workflows = runner.list_workflows(status=status, limit=limit)
        return [self._parse_stabilize_result(wf["execution_id"], wf) for wf in workflows]

    def logs(self, run_id: str) -> list[dict[str, Any]]:
        """Get logs for a workflow run.

        Note: Stabilize stores workflow state but not execution logs.
        This method returns an empty list. For detailed logs, check
        the Highway API directly or use Highway's dashboard.

        Args:
            run_id: Stabilize execution ID

        Returns:
            Empty list (logs not available via Stabilize)
        """
        return []

    def start_workflow(
        self,
        timeout: float = 300,
        workflow_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowHandle:
        """Start workflow and return handle immediately.

        This is the preferred way to run workflows asynchronously.
        Returns a WorkflowHandle that provides a simple interface for
        tracking and managing the workflow.

        Args:
            timeout: Default timeout for handle operations (seconds)
            workflow_id: Custom workflow ID for idempotency
            inputs: Workflow input variables

        Returns:
            WorkflowHandle for tracking the workflow

        Example:
            handle = driver.start_workflow()
            print(handle.status)      # Check status
            result = handle.result    # Wait for completion
        """
        from highway.handle import WorkflowHandle

        result = self.run(wait=False, timeout=timeout, workflow_id=workflow_id, inputs=inputs)
        return WorkflowHandle(run_id=result.run_id, driver=self, timeout=timeout)

    def retrieve_workflow(self, run_id: str, timeout: float = 300) -> WorkflowHandle:
        """Get handle for an existing workflow.

        Allows monitoring workflows started in previous sessions or
        by other processes.

        Args:
            run_id: The workflow run ID
            timeout: Default timeout for handle operations (seconds)

        Returns:
            WorkflowHandle for tracking the workflow

        Example:
            handle = driver.start_workflow()
            saved_run_id = handle.run_id

            # Later, retrieve it
            handle = driver.retrieve_workflow(saved_run_id)
            result = handle.result
        """
        from highway.handle import WorkflowHandle

        return WorkflowHandle(run_id=run_id, driver=self, timeout=timeout)

    def clear(self) -> None:
        """Clear all registered tasks.

        Useful for testing or reusing a Driver instance.
        """
        self._tasks.clear()

    def needs_artifact(self) -> bool:
        """Check if any tasks require artifact packaging.

        Returns:
            True if any tasks use durable=True
        """
        return any(t.durable for t in self._tasks.values())

    def get_durable_functions(self) -> dict[str, Callable[..., Any]]:
        """Get all durable functions that need packaging.

        Only returns functions for auto-packaged mode (no package= specified).

        Returns:
            Dict mapping function name to callable
        """
        return {t.name: t.func for t in self._tasks.values() if t.durable and not t.package}

    def get_package_dirs(self) -> dict[str, tuple[str, str]]:
        """Get package directories that need packaging.

        Returns:
            Dict mapping task name to (package_path, entrypoint)
        """
        return {
            t.name: (t.package, t.entrypoint)
            for t in self._tasks.values()
            if t.durable and t.package
        }

    def _build_workflow(
        self,
        workflow_timeout: int = 300,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build workflow JSON for testing.

        This method is primarily for testing compatibility.
        Use run() for actual execution.

        Args:
            workflow_timeout: Workflow-level timeout in seconds
            inputs: Workflow input variables

        Returns:
            Workflow definition dict
        """
        workflow_name = self._get_workflow_name()
        builder = DriverWorkflowBuilder(workflow_name, version="1.0.0")

        for task_def in self._tasks.values():
            builder.add_task(task_def)

        workflow_json = builder.build()
        workflow_json["timeout_seconds"] = workflow_timeout

        if inputs:
            workflow_json["variables"] = inputs

        return workflow_json
