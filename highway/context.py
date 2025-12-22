from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
_context: ContextVar[ExecutionContext | None] = ContextVar(
    "highway_execution_context", default=None
)
