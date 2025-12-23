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
