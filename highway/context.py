from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
_context: ContextVar[ExecutionContext | None] = ContextVar(
    "highway_execution_context", default=None
)

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

class _ContextMeta(type):
    """Metaclass to enable property-like access on Context class."""

    def workflow_id(cls) -> str | None:
        """Get the current workflow ID (if set via driver.run(workflow_id=...))."""
        ctx = _context.get()
        return ctx.workflow_id if ctx else None

    def task_name(cls) -> str | None:
        """Get the name of the currently executing task."""
        ctx = _context.get()
        return ctx.task_name if ctx else None
