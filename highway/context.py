"""Execution context for Highway Driver tasks.

Provides access to workflow and task metadata during execution.
Uses contextvars for thread-safe context management.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionContext:
    """Internal execution context data.

    This dataclass holds the actual context values that are set
    during task execution.
    """

    workflow_id: str | None = None
    task_name: str | None = None
    attempt: int = 1
    outputs: dict[str, Any] | None = None


# Context variable for storing execution context
_context: ContextVar[ExecutionContext | None] = ContextVar(
    "highway_execution_context", default=None
)


class _ContextMeta(type):
    """Metaclass to enable property-like access on Context class."""

    @property
    def workflow_id(cls) -> str | None:
        """Get the current workflow ID (if set via driver.run(workflow_id=...))."""
        ctx = _context.get()
        return ctx.workflow_id if ctx else None

    @property
    def task_name(cls) -> str | None:
        """Get the name of the currently executing task."""
        ctx = _context.get()
        return ctx.task_name if ctx else None

    @property
    def attempt(cls) -> int:
        """Get the current attempt number (1-indexed)."""
        ctx = _context.get()
        return ctx.attempt if ctx else 1

    @property
    def outputs(cls) -> dict[str, Any] | None:
        """Get outputs from completed dependency tasks."""
        ctx = _context.get()
        return ctx.outputs if ctx else None


class Context(metaclass=_ContextMeta):
    """Access execution context within tasks.

    This class provides a static interface for tasks to access
    information about the current execution environment.

    All properties are read-only and return None if accessed
    outside of task execution.

    Example:
        from highway import Context

        @driver.task(py=True)
        def my_task():
            print("Workflow:", Context.workflow_id)
            print("Task:", Context.task_name)
            print("Attempt:", Context.attempt)
            return {"context_test": True}
    """

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a specific output from a dependency task.

        Args:
            key: The task name to get output from
            default: Default value if not found

        Returns:
            The task output or default
        """
        outputs = cls.outputs
        if outputs is None:
            return default
        return outputs.get(key, default)


def set_context(
    workflow_id: str | None = None,
    task_name: str | None = None,
    attempt: int = 1,
    outputs: dict[str, Any] | None = None,
) -> Any:
    """Set execution context (internal use).

    Args:
        workflow_id: Current workflow ID
        task_name: Current task name
        attempt: Current attempt number
        outputs: Outputs from completed dependencies

    Returns:
        Token for resetting context
    """
    ctx = ExecutionContext(
        workflow_id=workflow_id,
        task_name=task_name,
        attempt=attempt,
        outputs=outputs,
    )
    return _context.set(ctx)


def reset_context(token: Any) -> None:
    """Reset execution context (internal use).

    Args:
        token: Token from set_context
    """
    _context.reset(token)
