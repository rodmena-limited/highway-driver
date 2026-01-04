"""Main Highway Driver class with @task decorator.

This is the primary interface for the Highway Driver SDK.
Users import Driver and use @driver.task() to define workflows.
"""

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

logger = logging.getLogger(__name__)

from highway.ast_utils import FunctionAnalyzer

if TYPE_CHECKING:
    from highway.runner import HighwayRunner

from highway.exceptions import (
    ConfigurationError,
    NotSupportedError,
    TaskDefinitionError,
)
from highway.result import WorkflowResult
from highway.task import TaskDefinition, TaskType

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

    @property
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

    def _timedelta_to_iso8601(self, td: timedelta) -> str:
        """Convert timedelta to ISO 8601 duration format.

        Highway's WaitOperator expects durations in ISO 8601 format.

        Args:
            td: timedelta to convert

        Returns:
            ISO 8601 duration string (e.g., "PT3S", "PT7200S")

        Examples:
            timedelta(seconds=3) -> "PT3S"
            timedelta(hours=2) -> "PT7200S"
            timedelta(days=1) -> "PT86400S"
        """
        total_seconds = int(td.total_seconds())
        return "PT%dS" % total_seconds

    def _build_workflow(
        self,
        workflow_timeout: int = 300,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build Highway DSL workflow JSON from registered tasks.

        Args:
            workflow_timeout: Workflow-level timeout in seconds
            inputs: Workflow input variables

        Returns:
            Workflow definition dict for Highway API
        """
        # Determine workflow name: explicit > derived from first task > uuid fallback
        # Note: Highway DB constraint requires underscores, not dashes
        if self._name:
            workflow_name = self._name.replace("-", "_")
        elif self._tasks:
            first_task = next(iter(self._tasks.keys()))
            workflow_name = "workflow_%s" % first_task
        else:
            workflow_name = "driver_workflow_%s" % uuid.uuid4().hex[:8]

        logger.debug(
            "Building workflow '%s' with %d tasks",
            workflow_name,
            len(self._tasks),
        )

        tasks_json: dict[str, Any] = {}

        for name, task in self._tasks.items():
            # If task has delay, insert a wait task first
            if task.delay is not None:
                wait_task_id = "%s_wait" % name
                wait_duration = self._timedelta_to_iso8601(task.delay)

                tasks_json[wait_task_id] = {
                    "task_id": wait_task_id,
                    "operator_type": "wait",
                    "dependencies": task.depends,  # Wait inherits original deps
                    "trigger_rule": "all_success",
                    "wait_for": wait_duration,
                }

                # Actual task depends on wait task instead of original deps
                actual_deps = [wait_task_id]
            else:
                actual_deps = task.depends

            task_json: dict[str, Any] = {
                "task_id": name,
                "operator_type": "task",
                "dependencies": actual_deps,
                "trigger_rule": "all_success",
                "result_key": task.get_result_key(),
            }

            # Add timeout for the task
            if task.timeout > 0:
                task_json["timeout_seconds"] = task.timeout

            # Add retry configuration if specified
            if task.retries > 0:
                task_json["retry_policy"] = {
                    "max_attempts": task.retries + 1,  # +1 for initial attempt
                    "initial_interval_seconds": task.retry_delay,
                    "backoff_coefficient": task.backoff_rate,
                }

            if task.task_type == TaskType.SHELL:
                # Get command from function
                command = task.func()
                task_json["function"] = "tools.shell.run"
                task_json["args"] = [command]
                task_json["kwargs"] = {}

            elif task.task_type == TaskType.HTTP:
                # Get config from function
                config = task.func()
                task_json["function"] = "tools.http.request"
                task_json["kwargs"] = config

            elif task.task_type == TaskType.PYTHON:
                if task.durable:
                    # Use tools.python.run with DurableContext
                    task_json["function"] = "tools.python.run"

                    if task.package:
                        # External package mode: use specified entrypoint
                        # entrypoint format: "cli:main" -> "issuedb.cli.main"
                        package_name = os.path.basename(task.package.rstrip("/"))
                        module_path, func_name = task.entrypoint.split(":")
                        task_json["args"] = ["%s.%s.%s" % (package_name, module_path, func_name)]
                    else:
                        # Auto-packaged function mode
                        # Uses wrapper: driver_tasks.tasks._hw_<func_name>
                        # Wrapper handles ctx injection for existing code compatibility
                        task_json["args"] = ["driver_tasks.tasks._hw_%s" % task.func.__name__]

                    # Add function positional args if specified
                    if task.func_args:
                        task_json["args"].extend(task.func_args)

                    # Artifact ID will be injected by runner after upload
                    task_json["kwargs"] = {"artifact_id": "{{_artifact_id}}"}

                    # Add function keyword args if specified
                    if task.func_kwargs:
                        task_json["kwargs"].update(task.func_kwargs)
                else:
                    # Get function source code for remote execution
                    source = inspect.getsource(task.func)
                    source = textwrap.dedent(source)

                    # Use AST to strip top-level decorators properly
                    tree = ast.parse(source)
                    func_def = tree.body[0]
                    if isinstance(func_def, ast.FunctionDef):
                        func_def.decorator_list = []  # Remove decorators
                    source = ast.unparse(tree)

                    # Generate wrapper that executes function and returns result as JSON
                    # Highway's tools.code.exec runs this in a sandboxed environment
                    wrapper = """
import json

%s

_result = %s()
# Output result in Highway-recognized format
print("__HIGHWAY_RESULT__:" + json.dumps(_result))
""" % (source, task.func.__name__)

                    task_json["function"] = "tools.code.exec"
                    task_json["kwargs"] = {
                        "code": wrapper,
                        "timeout": task.timeout,
                    }

            elif task.task_type == TaskType.TOOL:
                # Generic Highway tool - function returns kwargs
                config = task.func()
                task_json["function"] = task.tool_name
                task_json["kwargs"] = config if isinstance(config, dict) else {}

            elif task.task_type == TaskType.WORKFLOW:
                # Execute another workflow via tools.workflow.execute
                config = task.func()
                workflow_kwargs: dict[str, Any] = {}

                # Set workflow identifier (name or definition_id)
                if task.workflow_definition_id:
                    workflow_kwargs["definition_id"] = task.workflow_definition_id
                elif task.workflow_name:
                    workflow_kwargs["workflow_name"] = task.workflow_name

                # Include inputs from function return value
                if isinstance(config, dict) and "inputs" in config:
                    workflow_kwargs["inputs"] = config["inputs"]

                task_json["function"] = "tools.workflow.execute"
                task_json["kwargs"] = workflow_kwargs

            elif task.task_type == TaskType.FOREACH:
                # ForEach loop over a collection
                source = inspect.getsource(task.func)
                source = textwrap.dedent(source)

                # Use AST to strip top-level decorators
                tree = ast.parse(source)
                func_def = tree.body[0]
                if isinstance(func_def, ast.FunctionDef):
                    func_def.decorator_list = []
                source = ast.unparse(tree)

                # Generate wrapper for loop body
                wrapper = """
import json

%s

_result = %s()
print("__HIGHWAY_RESULT__:" + json.dumps(_result))
""" % (source, task.func.__name__)

                # Build loop body task (must match WorkflowBuilder format)
                body_task_id = "%s_body" % name
                body_task: dict[str, Any] = {
                    "task_id": body_task_id,
                    "operator_type": "task",
                    "dependencies": [name],  # Loop body depends on foreach parent
                    "trigger_rule": "all_success",
                    "function": "tools.code.exec",
                    "kwargs": {
                        "code": wrapper,
                        "timeout": task.timeout,
                    },
                    "result_key": "%s_item_result" % name,
                    "is_internal_loop_task": True,  # Mark as internal loop task
                }

                # Override task_json for foreach operator
                task_json = {
                    "task_id": name,
                    "operator_type": "foreach",
                    "dependencies": actual_deps,
                    "trigger_rule": "all_success",
                    "items": task.items,
                    "loop_body": [body_task],  # Must be a list
                    "parallel": False,  # Sequential by default
                    "result_key": task.get_result_key(),
                }

                # Also register the loop body as a top-level task
                tasks_json[body_task_id] = body_task

            elif task.task_type == TaskType.WHILE:
                # While loop with condition
                body_task_id = "%s_body" % name

                if task.durable:
                    # Use tools.python.run with DurableContext
                    body_task: dict[str, Any] = {
                        "task_id": body_task_id,
                        "operator_type": "task",
                        "dependencies": [name],
                        "trigger_rule": "all_success",
                        "function": "tools.python.run",
                        "args": ["driver_tasks.tasks._hw_%s" % task.func.__name__],
                        "kwargs": {"artifact_id": "{{_artifact_id}}"},
                        "result_key": "%s_iteration_result" % name,
                        "is_internal_loop_task": True,
                    }
                else:
                    # Fall back to tools.code.exec (no DurableContext)
                    source = inspect.getsource(task.func)
                    source = textwrap.dedent(source)

                    tree = ast.parse(source)
                    func_def = tree.body[0]
                    if isinstance(func_def, ast.FunctionDef):
                        func_def.decorator_list = []
                    source = ast.unparse(tree)

                    wrapper = """
import json

%s

_result = %s()
print("__HIGHWAY_RESULT__:" + json.dumps(_result))
""" % (source, task.func.__name__)

                    body_task = {
                        "task_id": body_task_id,
                        "operator_type": "task",
                        "dependencies": [name],
                        "trigger_rule": "all_success",
                        "function": "tools.code.exec",
                        "kwargs": {
                            "code": wrapper,
                            "timeout": task.timeout,
                        },
                        "result_key": "%s_iteration_result" % name,
                        "is_internal_loop_task": True,
                    }

                # Override task_json for while operator
                task_json = {
                    "task_id": name,
                    "operator_type": "while",
                    "dependencies": actual_deps,
                    "trigger_rule": "all_success",
                    "condition": task.condition,
                    "loop_body": [body_task],  # Must be a list
                    "result_key": task.get_result_key(),
                }

                # Also register the loop body as a top-level task
                tasks_json[body_task_id] = body_task

            elif task.task_type == TaskType.EMIT:
                # Emit event operator
                task_json = {
                    "task_id": name,
                    "operator_type": "emit_event",
                    "dependencies": actual_deps,
                    "trigger_rule": "all_success",
                    "event_name": task.event_name,
                    "payload": task.event_payload or {},
                    "result_key": task.get_result_key(),
                }

            elif task.task_type == TaskType.WAIT_FOR:
                # Wait for event operator
                task_json = {
                    "task_id": name,
                    "operator_type": "wait_for_event",
                    "dependencies": actual_deps,
                    "trigger_rule": "all_success",
                    "event_name": task.event_name,
                    "timeout_seconds": task.event_timeout or 30,
                    "result_key": task.get_result_key(),
                }

            tasks_json[name] = task_json

        # Find start_task from generated tasks (tasks with no dependencies)
        start_task: str | None = None
        no_deps = [
            task_id for task_id, task_def in tasks_json.items() if not task_def.get("dependencies")
        ]
        if no_deps:
            start_task = sorted(no_deps)[0]

        # Check for workflow-level schedule (from first scheduled task)
        scheduled_tasks = [t for t in self._tasks.values() if t.schedule]
        workflow_schedule: str | None = None
        if scheduled_tasks:
            # Use schedule from first scheduled task for workflow
            workflow_schedule = scheduled_tasks[0].schedule

        workflow_def: dict[str, Any] = {
            "name": workflow_name,
            "version": "1.0.0",
            "description": "Workflow generated by Highway Driver SDK",
            "start_task": start_task,
            "tasks": tasks_json,
            "variables": inputs or {},
            "max_active_runs": 1,
            "timeout_seconds": workflow_timeout,
        }

        # Add schedule if any tasks are scheduled
        if workflow_schedule:
            workflow_def["schedule"] = workflow_schedule

        logger.info(
            "Workflow '%s' built: %d tasks, start_task=%s",
            workflow_name,
            len(tasks_json),
            start_task,
        )
        return workflow_def

    def status(self, run_id: str) -> WorkflowResult:
        """Get current status of a workflow.

        Args:
            run_id: Highway workflow run ID

        Returns:
            WorkflowResult with current state
        """
        if not self.api_key:
            raise ConfigurationError("API key required for status()")

        runner = self._get_runner()
        return runner.status(run_id)

    def cancel(self, run_id: str) -> bool:
        """Cancel a running workflow via Stabilize.

        Args:
            run_id: Stabilize workflow run ID

        Returns:
            True if cancellation was successful
        """
        if not self.api_key:
            raise ConfigurationError("API key required for cancel()")

        runner = self._get_runner()
        return runner.cancel(run_id)

    def logs(self, run_id: str) -> list[dict[str, Any]]:
        """Get execution logs for a workflow.

        Args:
            run_id: Workflow run ID (Stabilize execution ID or Highway run ID)

        Returns:
            List of log entries from the workflow execution
        """
        if not self.api_key:
            raise ConfigurationError("API key required for logs()")

        runner = self._get_runner()
        return runner.logs(run_id)

    def start_workflow(
        self,
        timeout: float = 300,
        workflow_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> "WorkflowHandle":
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
            # or: result = await handle  # Async wait
        """
        from highway.handle import WorkflowHandle

        result = self.run(wait=False, timeout=timeout, workflow_id=workflow_id, inputs=inputs)
        return WorkflowHandle(run_id=result.run_id, driver=self, timeout=timeout)

    def retrieve_workflow(self, run_id: str, timeout: float = 300) -> "WorkflowHandle":
        """Get handle for an existing workflow.

        Allows monitoring workflows started in previous sessions or
        by other processes.

        Args:
            run_id: The workflow run ID
            timeout: Default timeout for handle operations (seconds)

        Returns:
            WorkflowHandle for tracking the workflow

        Example:
            # Save run_id somewhere
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
        return {
            t.name: t.func
            for t in self._tasks.values()
            if t.durable and not t.package
        }

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
