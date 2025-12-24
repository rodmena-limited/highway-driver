from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

class TaskType(Enum):
    """Type of task execution."""
    SHELL = 'shell'
    PYTHON = 'python'
    HTTP = 'http'
    TOOL = 'tool'
    WORKFLOW = 'workflow'
    FOREACH = 'foreach'
    WHILE = 'while'
    EMIT = 'emit'
    WAIT_FOR = 'wait_for'

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
    items: str | None = None
    condition: str | None = None
    event_name: str | None = None
    event_payload: dict[str, Any] | None = None
    event_timeout: int | None = None
    durable: bool = False
    package: str | None = None
    entrypoint: str | None = None
    func_args: list[Any] | None = None
    func_kwargs: dict[str, Any] | None = None
