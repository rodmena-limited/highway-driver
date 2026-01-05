"""Type definitions for Highway Driver.

This module provides typed dictionaries and type aliases for improved
type safety across the codebase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict


class WorkflowStatusDict(TypedDict, total=False):
    """Status of a workflow execution from Stabilize."""

    execution_id: str
    status: str
    is_complete: bool
    is_halt: bool
    highway_run_id: str | None
    highway_status: str | None
    highway_result: dict[str, Any] | None
    highway_current_step: str | None
    highway_progress: float | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None


class WorkflowListItem(TypedDict, total=False):
    """Item in a workflow list response."""

    execution_id: str
    status: str
    is_complete: bool
    highway_run_id: str | None
    highway_status: str | None
    started_at: datetime | None
    completed_at: datetime | None


class TaskDefinitionDict(TypedDict, total=False):
    """Highway DSL task definition."""

    type: str
    command: str | None
    code: str | None
    url: str | None
    method: str | None
    json: dict[str, Any] | None
    headers: dict[str, str] | None
    timeout: int
    retries: int
    retry_delay: float
    backoff: float
    depends: list[str]


class WorkflowDefinitionDict(TypedDict, total=False):
    """Highway DSL workflow definition."""

    name: str
    version: str
    tasks: dict[str, TaskDefinitionDict]
    timeout_seconds: int
    variables: dict[str, Any]


class HighwayResultDict(TypedDict, total=False):
    """Result from Highway API execution."""

    run_id: str
    status: str
    result: dict[str, Any] | None
    error: str | None
    current_step: str | None
    progress: float | None


class StabilizeContextDict(TypedDict, total=False):
    """Context passed to Stabilize stage."""

    highway_workflow_definition: WorkflowDefinitionDict
    highway_inputs: dict[str, Any]
    highway_api_key: str
    highway_api_endpoint: str
