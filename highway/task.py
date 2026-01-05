"""Task definition dataclass for Highway Driver.

A TaskDefinition captures all metadata about a decorated function
that will be converted to a Highway workflow task.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from highway.ast_utils import FunctionAnalysis


class TaskType(Enum):
    """Type of task execution."""

    SHELL = "shell"
    PYTHON = "python"
    HTTP = "http"
    TOOL = "tool"  # Generic Highway tool (e.g., tools.llm.call)
    WORKFLOW = "workflow"  # Execute another workflow
    # Control flow operators
    FOREACH = "foreach"  # ForEach loop over collection
    WHILE = "while"  # While loop with condition
    EMIT = "emit"  # Emit event
    WAIT_FOR = "wait_for"  # Wait for event


@dataclass
class TaskDefinition:
    """Definition of a task registered with the Driver.

    Attributes:
        name: Function name (auto-extracted)
        func: The decorated function
        task_type: Type of task (shell, python, http, tool, workflow)
        depends: List of task names this depends on
        timeout: Execution timeout in seconds
        schedule: Cron expression or interval string (e.g., "0 * * * *" or "@every 60s")
        run_at: Specific execution time (NotImplemented)
        retries: Number of retry attempts on failure
        retry_delay: Initial delay between retries in seconds
        backoff_rate: Multiplier for exponential backoff (e.g., 2.0)
        delay: Durable delay before task execution (uses Highway's WaitOperator)
        tool_name: Highway tool name for TOOL type (e.g., "tools.llm.call")
        workflow_name: Workflow name for WORKFLOW type (uses latest version)
        workflow_definition_id: Specific workflow definition ID for WORKFLOW type
        analysis: AST analysis of the function (populated by Driver)
    """

    name: str
    func: Callable[..., Any]
    task_type: TaskType
    depends: list[str] = field(default_factory=list)
    timeout: int = 300
    schedule: str | None = None
    run_at: str | None = None
    retries: int = 0
    retry_delay: float = 1.0
    backoff_rate: float = 2.0
    delay: timedelta | None = None
    tool_name: str | None = None
    workflow_name: str | None = None
    workflow_definition_id: str | None = None
    analysis: FunctionAnalysis | None = None
    # Control flow fields
    items: str | None = None  # ForEach: variable reference for collection (e.g., "{{my_list}}")
    condition: str | None = None  # While/Condition: expression (e.g., "{{counter}} < 10")
    event_name: str | None = None  # Emit/WaitFor: event name
    event_payload: dict[str, Any] | None = None  # Emit: event payload
    event_timeout: int | None = None  # WaitFor: timeout in seconds
    # Durable Python execution fields (tools.python.run)
    durable: bool = False  # Use tools.python.run with DurableContext
    package: str | None = None  # Path to Python package directory
    entrypoint: str | None = None  # Module:function path (e.g., "main:run_calculation")
    func_args: list[Any] | None = None  # Positional args to pass to entrypoint function
    func_kwargs: dict[str, Any] | None = None  # Keyword args to pass to entrypoint function

    def __post_init__(self) -> None:
        """Validate task definition after creation."""
        if self.timeout <= 0:
            raise ValueError("timeout must be positive, got %d" % self.timeout)
        if self.retries < 0:
            raise ValueError("retries must be non-negative, got %d" % self.retries)
        if self.retry_delay < 0:
            raise ValueError(f"retry_delay must be non-negative, got {self.retry_delay}")
        if self.backoff_rate < 1.0:
            raise ValueError(f"backoff_rate must be >= 1.0, got {self.backoff_rate}")
        if self.delay is not None and self.delay.total_seconds() <= 0:
            raise ValueError(f"delay must be positive, got {self.delay}")
        # Validate durable/package/entrypoint
        if self.package is not None:
            if not self.durable:
                raise ValueError("package= requires durable=True")
            if not self.entrypoint:
                raise ValueError("package= requires entrypoint= (e.g., 'main:run_func')")
            if ":" not in self.entrypoint:
                raise ValueError(
                    f"entrypoint must be in 'module:function' format, got '{self.entrypoint}'"
                )

    def get_result_key(self) -> str:
        """Get the result key for this task in Highway workflow."""
        return f"{self.name}_result"

    def validate_depends(self, available_tasks: set[str]) -> list[str]:
        """Validate that all dependencies exist.

        Args:
            available_tasks: Set of registered task names

        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        for dep in self.depends:
            if dep not in available_tasks:
                errors.append(
                    f"Task '{self.name}' depends on '{dep}' which is not registered"
                )
        return errors
