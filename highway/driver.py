from __future__ import annotations
import ast
import inspect
import logging
import os
import textwrap
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypeVar
from highway.ast_utils import FunctionAnalyzer
from highway.exceptions import (
    ConfigurationError,
    NotSupportedError,
    TaskDefinitionError,
)
from highway.result import WorkflowResult
from highway.task import TaskDefinition, TaskType
logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])

class Driver:
    """Highway Driver - Simple decorator SDK for Highway Workflow Engine.

    The Driver class provides a DBOS-style decorator interface for defining
    and executing workflows on Highway. It handles:

    - Task registration via @driver.task() decorator
    - Workflow DSL generation
    - Execution via Stabilize orchestration layer
    - Status polling and result retrieval

    Architecture (Golden Rule - Driver NEVER talks directly to Highway):
        Driver -> Stabilize (HighwayTask) -> Highway API

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
                      Defaults to https://highway.solutions

        Note:
            API key is required. All execution goes through
            Stabilize -> Highway API.

        Example:
            driver = Driver(name="payment-processor")  # Explicit name
            driver = Driver()  # Auto: 'workflow_<first_task>' or 'driver_workflow_<uuid>'
        """
        self._name = name
        self.api_key = api_key or os.environ.get("HIGHWAY_API_KEY", "")
        self.endpoint = endpoint or os.environ.get("HIGHWAY_API_ENDPOINT", "https://highway.solutions")
        self._tasks: dict[str, TaskDefinition] = {}
        self._analyzer = FunctionAnalyzer()

    def tasks(self) -> dict[str, TaskDefinition]:
        """Get all registered tasks."""
        return self._tasks.copy()

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
        - py=True: Function is executed as Python code via tools.code.exec
        - http=True: Function returns HTTP request configuration
        - tool="tools.X.Y": Function returns kwargs for any Highway tool
        - workflow="name": Execute another workflow by name (latest version)
        - workflow_id="uuid": Execute specific workflow version by definition_id

        Args:
            shell: Execute as shell command (function returns command string)
            py: Execute as Python code on Highway via tools.code.exec
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
        # Validate package/entrypoint requirements BEFORE task type check
        # This gives more helpful error messages
        if package is not None and not durable:
            raise ValueError("package requires durable=True")
        if package is not None and entrypoint is None:
            raise ValueError("package requires entrypoint (e.g., 'main:run')")

        # Validate task type - exactly one must be specified
        # durable=True implies Python execution (tools.python.run instead of tools.code.exec)
        type_flags = [
            shell,
            py,
            http,
            tool is not None,
            workflow is not None,
            workflow_id is not None,
            durable,  # durable=True is a Python task type variant
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
                specified.append("tool='%s'" % tool)
            if workflow:
                specified.append("workflow='%s'" % workflow)
            if workflow_id:
                specified.append("workflow_id='%s'" % workflow_id)
            raise TaskDefinitionError("Only one task type allowed. Got: %s" % ", ".join(specified))

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
                # Convert timedelta to seconds for interval scheduling
                total_seconds = int(schedule.total_seconds())
                schedule_str = "@every %ds" % total_seconds
            else:
                schedule_str = schedule

        # Determine task type
        if shell:
            task_type = TaskType.SHELL
        elif py or durable:
            # Both py=True and durable=True are Python execution
            # py=True → tools.code.exec (isolated, no DurableContext)
            # durable=True → tools.python.run (with DurableContext)
            task_type = TaskType.PYTHON
        elif http:
            task_type = TaskType.HTTP
        elif tool:
            task_type = TaskType.TOOL
        else:
            # workflow or workflow_id
            task_type = TaskType.WORKFLOW

        def decorator(func: F) -> F:
            # Check for duplicate registration
            if func.__name__ in self._tasks:
                raise TaskDefinitionError("Task '%s' is already registered" % func.__name__)

            # Analyze function with AST
            analysis = self._analyzer.analyze(func)

            # Create task definition
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
                # {{current_item}} available here
                return "echo 'Processing item'"

            @driver.task(py=True, depends=["process_item"])
            def verify_all():
                return {"all_processed": True}
        """

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError("Task '%s' is already registered" % func.__name__)

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
        durable: bool = True,
    ) -> Callable[[F], F]:
        """Decorator to define a While loop with a condition.

        The decorated function is executed repeatedly while condition is true.
        Defaults to durable=True to enable mutable workflow variables via
        ctx.set_variable() / ctx.get_variable().

        Args:
            condition: Expression to evaluate (e.g., "{{counter}} < 10")
            depends: List of task names this depends on
            timeout: Execution timeout in seconds per iteration
            max_iterations: Safety limit on iterations (default 100)
            durable: Use tools.python.run with DurableContext (default True)

        Returns:
            Decorated function

        Example:
            @driver.task(durable=True)
            def init(ctx):
                ctx.set_variable("counter", 0)
                ctx.set_variable("limit", 5)
                return {"initialized": True}

            @driver.while_loop(condition="{{counter}} < {{limit}}", depends=["init"])
            def increment(ctx):
                counter = ctx.get_variable("counter", 0)
                ctx.set_variable("counter", counter + 1)
                return {"iteration": counter + 1}
        """

        def decorator(func: F) -> F:
            if func.__name__ in self._tasks:
                raise TaskDefinitionError("Task '%s' is already registered" % func.__name__)

            analysis = self._analyzer.analyze(func)

            task_def = TaskDefinition(
                name=func.__name__,
                func=func,
                task_type=TaskType.WHILE,
                depends=depends or [],
                timeout=timeout,
                condition=condition,
                analysis=analysis,
                durable=durable,
            )

            self._tasks[func.__name__] = task_def
            logger.info(
                "Registered while_loop '%s' (condition=%s, max_iter=%d, durable=%s)",
                func.__name__,
                condition,
                max_iterations,
                durable,
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
                raise TaskDefinitionError("Task '%s' is already registered" % func.__name__)

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
                raise TaskDefinitionError("Task '%s' is already registered" % func.__name__)

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

        All execution goes through Stabilize -> Highway API.

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

        return self._run_via_stabilize(
            wait=wait, timeout=timeout, workflow_id=workflow_id, inputs=inputs
        )

    def _run_via_stabilize(
        self,
        wait: bool = True,
        timeout: float = 300,
        workflow_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Execute tasks via Stabilize orchestration layer.

        Flow:
        1. Build Highway workflow JSON from registered tasks
        2. If durable tasks exist, package functions and create multi-stage workflow
        3. Stabilize's HighwayTask submits to Highway API
        4. Stabilize polls and manages state
        5. Return results from Stabilize store

        Args:
            wait: If True, wait for completion
            timeout: Maximum wait time in seconds
            workflow_id: Optional workflow ID for idempotency
            inputs: Workflow input variables

        Returns:
            WorkflowResult with execution status
        """
        if not self.api_key:
            raise ConfigurationError(
                "HIGHWAY_API_KEY not configured. "
                "Set environment variable or pass api_key to Driver()"
            )

        inputs = inputs or {}

        # Build workflow JSON with workflow-level timeout and inputs
        workflow_json = self._build_workflow(workflow_timeout=int(timeout), inputs=inputs)

        # Use Stabilize runner for execution
        runner = self._get_runner()

        # Collect durable task info for artifact packaging
        durable_functions = self.get_durable_functions() if self.needs_artifact() else None
        package_dirs = self.get_package_dirs() if self.needs_artifact() else None

        if wait:
            return runner.run(
                workflow_json,
                inputs={},
                timeout=timeout,
                workflow_id=workflow_id,
                durable_functions=durable_functions,
                package_dirs=package_dirs,
            )
        else:
            return runner.submit(
                workflow_json,
                inputs={},
                workflow_id=workflow_id,
                durable_functions=durable_functions,
                package_dirs=package_dirs,
            )

    def _get_runner(self) -> HighwayRunner:
        """Get or create the Highway runner instance.

        Returns:
            HighwayRunner for Highway API communication
        """
        from highway.runner import HighwayRunner

        return HighwayRunner(
            api_key=self.api_key,
            endpoint=self.endpoint,
        )
