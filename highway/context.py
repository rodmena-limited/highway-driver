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
