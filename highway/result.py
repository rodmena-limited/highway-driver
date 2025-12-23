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
