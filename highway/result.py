from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

class WorkflowState(Enum):
    """State of a workflow execution."""
    PENDING = 'pending'
    SUBMITTED = 'submitted'
    RUNNING = 'running'
    SCHEDULED = 'scheduled'
    SLEEPING = 'sleeping'
    WAITING = 'waiting'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    TIMED_OUT = 'timed_out'

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (
            WorkflowState.COMPLETED,
            WorkflowState.FAILED,
            WorkflowState.CANCELLED,
            WorkflowState.TIMED_OUT,
        )

@dataclass
class TaskResult:
    """Result of a single task execution.

    Attributes:
        name: Task name
        state: Current state
        result: Return value (if completed)
        error: Error message (if failed)
        started_at: When execution started
        completed_at: When execution completed
        stdout: Standard output (for shell tasks)
        stderr: Standard error (for shell tasks)
        returncode: Exit code (for shell tasks)
    """
    name: str
    state: WorkflowState
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stdout: str | None = None
    stderr: str | None = None
    returncode: int | None = None

    def is_success(self) -> bool:
        """Check if task completed successfully."""
        return self.state == WorkflowState.COMPLETED and self.error is None
