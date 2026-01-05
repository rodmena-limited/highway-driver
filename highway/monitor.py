"""Monitoring API for Highway workflows.

This module provides the WorkflowMonitor class for querying local
SQLite storage to get workflow status without calling the Highway API.

Example:
    monitor = WorkflowMonitor()

    # List all workflows
    for wf in monitor.list_workflows():
        print(f"{wf['id']} {wf['status']}")

    # Get specific workflow
    wf = monitor.get_workflow(execution_id)
    print(f"Status: {wf['status']}, Progress: {wf['progress']}")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from stabilize import SqliteQueue, SqliteWorkflowStore
from stabilize.monitor.data import (
    MonitorDataFetcher,
    WorkflowView,
    format_duration,
)


@dataclass
class WorkflowInfo:
    """Information about a Highway workflow execution."""

    execution_id: str
    name: str
    status: str
    is_complete: bool
    started_at: datetime | None
    completed_at: datetime | None
    duration: str
    highway_run_id: str | None
    highway_status: str | None
    highway_current_step: str | None
    progress: tuple[int, int]  # (completed, total)
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "name": self.name,
            "status": self.status,
            "is_complete": self.is_complete,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration": self.duration,
            "highway_run_id": self.highway_run_id,
            "highway_status": self.highway_status,
            "highway_current_step": self.highway_current_step,
            "progress": self.progress,
            "error": self.error,
        }


class WorkflowMonitor:
    """Query local SQLite for workflow status.

    This class provides monitoring without calling the Highway API,
    using the local Stabilize SQLite database for all queries.

    Example:
        monitor = WorkflowMonitor()

        # List running workflows
        running = monitor.list_workflows(status="running")

        # Get progress
        completed, total = monitor.get_progress(execution_id)
    """

    DEFAULT_DB_PATH = "~/.highway/workflows.db"

    def __init__(self, db_path: str | None = None):
        """Initialize the monitor.

        Args:
            db_path: Path to SQLite database (default: ~/.highway/workflows.db)
        """
        self._db_path = os.path.expanduser(db_path or self.DEFAULT_DB_PATH)

        if not Path(self._db_path).exists():
            raise FileNotFoundError(
                f"Database not found: {self._db_path}. Run a workflow first to create the database."
            )

        self._store = SqliteWorkflowStore(
            f"sqlite:///{self._db_path}",
            create_tables=False,
        )
        self._queue = SqliteQueue(
            f"sqlite:///{self._db_path}",
            table_name="queue_messages",
        )
        self._fetcher = MonitorDataFetcher(self._store, self._queue)

    def list_workflows(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WorkflowInfo]:
        """List workflows from local store.

        Args:
            status: Filter by status (running/succeeded/failed)
            limit: Maximum number of workflows to return

        Returns:
            List of WorkflowInfo objects
        """
        status_filter = status or "all"
        data = self._fetcher.fetch(
            app_filter="highway-driver",
            limit=limit,
            status_filter=status_filter,
        )

        return [self._convert_workflow_view(wf) for wf in data.workflows]

    def get_workflow(self, execution_id: str) -> WorkflowInfo | None:
        """Get detailed workflow information.

        Args:
            execution_id: The Stabilize execution ID

        Returns:
            WorkflowInfo or None if not found
        """
        try:
            workflow = self._store.retrieve(execution_id)
        except (KeyError, ValueError, LookupError):
            # Workflow not found in store
            return None

        # Extract outputs from the highway stage
        outputs = {}
        if workflow.stages and workflow.stages[0].outputs:
            outputs = workflow.stages[0].outputs

        # Calculate progress
        completed = sum(1 for s in workflow.stages if s.status.is_complete)
        total = len(workflow.stages)

        # Get duration
        duration = format_duration(workflow.start_time, workflow.end_time)

        # Get error
        error = None
        if workflow.stages and workflow.stages[0].context:
            error = workflow.stages[0].context.get("error")
        error = error or outputs.get("error")

        return WorkflowInfo(
            execution_id=workflow.id,
            name=workflow.name,
            status=workflow.status.name.lower(),
            is_complete=workflow.status.is_complete,
            started_at=datetime.fromtimestamp(workflow.start_time / 1000)
            if workflow.start_time
            else None,
            completed_at=datetime.fromtimestamp(workflow.end_time / 1000)
            if workflow.end_time
            else None,
            duration=duration,
            highway_run_id=outputs.get("highway_run_id"),
            highway_status=outputs.get("highway_status"),
            highway_current_step=outputs.get("highway_current_step"),
            progress=(completed, total),
            error=error,
        )

    def get_progress(self, execution_id: str) -> tuple[int, int]:
        """Get workflow progress as (completed, total) stages.

        Args:
            execution_id: The Stabilize execution ID

        Returns:
            Tuple of (completed_stages, total_stages)
        """
        wf = self.get_workflow(execution_id)
        if wf:
            return wf.progress
        return (0, 0)

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate workflow statistics.

        Returns:
            Dict with keys: running, succeeded, failed, total
        """
        data = self._fetcher.fetch(app_filter="highway-driver", limit=1000)
        return {
            "running": data.workflow_stats.running,
            "succeeded": data.workflow_stats.succeeded,
            "failed": data.workflow_stats.failed,
            "total": data.workflow_stats.total,
        }

    def get_queue_stats(self) -> dict[str, Any]:
        """Get queue statistics.

        Returns:
            Dict with keys: pending, processing, stuck
        """
        data = self._fetcher.fetch(app_filter="highway-driver", limit=1)
        return {
            "pending": data.queue_stats.pending,
            "processing": data.queue_stats.processing,
            "stuck": data.queue_stats.stuck,
        }

    def _convert_workflow_view(self, wf: WorkflowView) -> WorkflowInfo:
        """Convert a WorkflowView to WorkflowInfo."""
        # We need to fetch the full workflow to get Highway-specific fields
        full_wf = self.get_workflow(wf.id)
        if full_wf:
            return full_wf

        # Fallback with limited info
        return WorkflowInfo(
            execution_id=wf.id,
            name=wf.name,
            status=wf.status.name.lower(),
            is_complete=wf.status.is_complete,
            started_at=datetime.fromtimestamp(wf.start_time / 1000) if wf.start_time else None,
            completed_at=datetime.fromtimestamp(wf.end_time / 1000) if wf.end_time else None,
            duration=format_duration(wf.start_time, wf.end_time),
            highway_run_id=None,
            highway_status=None,
            highway_current_step=None,
            progress=wf.stage_progress,
            error=None,
        )
