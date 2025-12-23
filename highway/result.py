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

@dataclass
class WorkflowResult:
    """Result of a workflow execution.

    Attributes:
        run_id: Highway workflow run ID
        workflow_id: User-provided workflow ID for idempotency
        status: Overall workflow status string
        state: Workflow state enum
        tasks: Results for each task by name
        started_at: When workflow started
        completed_at: When workflow completed
        error: Error message if failed
        stabilize_execution_id: Stabilize orchestration execution ID
    """
    run_id: str | None = None
    workflow_id: str | None = None
    status: str = 'pending'
    state: WorkflowState = WorkflowState.PENDING
    tasks: dict[str, TaskResult] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    stabilize_execution_id: str | None = None

    def __post_init__(self) -> None:
        """Sync status string with state enum."""
        if isinstance(self.state, str):
            self.state = WorkflowState(self.state)
        if self.status == "pending":
            self.status = self.state.value
