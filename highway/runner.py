"""Stabilize-based workflow runner with durability.

This module provides the StabilizeRunner class that executes Highway workflows
through Stabilize for durability, crash recovery, and monitoring.

Architecture:
    Driver → StabilizeRunner → HighwayTask → Highway API

Benefits:
    - Crash recovery via idempotency keys
    - Local SQLite persistence for monitoring
    - Automatic retry on transient failures
    - Non-blocking polling with backoff
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from stabilize import (
    CompleteStageHandler,
    CompleteTaskHandler,
    CompleteWorkflowHandler,
    HighwayTask,
    Orchestrator,
    QueueProcessor,
    RunTaskHandler,
    SqliteQueue,
    SqliteWorkflowStore,
    StageExecution,
    StartStageHandler,
    StartTaskHandler,
    StartWorkflowHandler,
    TaskExecution,
    TaskRegistry,
    Workflow,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class StabilizeRunner:
    """Runs Highway workflows through Stabilize for durability.

    This class wraps Stabilize's infrastructure to provide:
    - Persistent workflow storage in SQLite
    - Crash recovery via idempotency keys
    - Local monitoring without API calls
    - Non-blocking execution with polling

    Example:
        runner = StabilizeRunner()
        exec_id = runner.submit(workflow_json, inputs={"x": 1})
        result = runner.wait(exec_id, timeout=300)
    """

    # Default database location
    DEFAULT_DB_PATH = "~/.highway/workflows.db"

    def __init__(
        self,
        db_path: str | None = None,
        api_key: str | None = None,
        api_endpoint: str | None = None,
    ):
        """Initialize the Stabilize runner.

        Args:
            db_path: Path to SQLite database (default: ~/.highway/workflows.db)
            api_key: Highway API key (default: from HIGHWAY_API_KEY env)
            api_endpoint: Highway API endpoint (default: from HIGHWAY_API_ENDPOINT env)
        """
        self._db_path = os.path.expanduser(db_path or self.DEFAULT_DB_PATH)
        self._api_key = api_key
        self._api_endpoint = api_endpoint

        # Ensure directory exists
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize Stabilize components
        self._store = SqliteWorkflowStore(
            f"sqlite:///{self._db_path}",
            create_tables=True,
        )
        self._queue = SqliteQueue(
            f"sqlite:///{self._db_path}",
            table_name="queue_messages",
        )
        self._queue._create_table()

        # Setup processor and orchestrator
        self._processor, self._orchestrator = self._setup_pipeline()

    def _setup_pipeline(self) -> tuple[QueueProcessor, Orchestrator]:
        """Create processor and orchestrator with HighwayTask registered."""
        task_registry = TaskRegistry()
        task_registry.register("highway", HighwayTask)

        processor = QueueProcessor(self._queue)

        handlers = [
            StartWorkflowHandler(self._queue, self._store),
            StartStageHandler(self._queue, self._store),
            StartTaskHandler(self._queue, self._store),
            RunTaskHandler(self._queue, self._store, task_registry),
            CompleteTaskHandler(self._queue, self._store),
            CompleteStageHandler(self._queue, self._store),
            CompleteWorkflowHandler(self._queue, self._store),
        ]

        for handler in handlers:
            processor.register_handler(handler)

        orchestrator = Orchestrator(self._queue)
        return processor, orchestrator

    def submit(
        self,
        workflow_definition: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        workflow_name: str | None = None,
        api_key: str | None = None,
        api_endpoint: str | None = None,
    ) -> str:
        """Submit a workflow to Highway via Stabilize.

        Args:
            workflow_definition: Highway workflow JSON definition
            inputs: Workflow input parameters
            workflow_name: Optional name for the Stabilize workflow
            api_key: Override API key for this submission
            api_endpoint: Override API endpoint for this submission

        Returns:
            The Stabilize execution ID (use for status/wait)
        """
        # Build stage context for HighwayTask
        context: dict[str, Any] = {
            "highway_workflow_definition": workflow_definition,
            "highway_inputs": inputs or {},
        }

        # Add API credentials if provided (otherwise HighwayTask uses env vars)
        effective_key = api_key or self._api_key
        effective_endpoint = api_endpoint or self._api_endpoint

        if effective_key:
            context["highway_api_key"] = effective_key
        if effective_endpoint:
            context["highway_api_endpoint"] = effective_endpoint

        # Create Stabilize workflow with single HighwayTask stage
        name = workflow_name or workflow_definition.get("name", "highway_workflow")

        workflow = Workflow.create(
            application="highway-driver",
            name=name,
            stages=[
                StageExecution(
                    ref_id="highway_stage",
                    type="highway",
                    name=f"Highway: {name}",
                    context=context,
                    tasks=[
                        TaskExecution.create(
                            name="HighwayTask",
                            implementing_class="highway",
                            stage_start=True,
                            stage_end=True,
                        ),
                    ],
                ),
            ],
        )

        # Store and start workflow
        self._store.store(workflow)
        self._orchestrator.start(workflow)

        logger.info("Submitted workflow %s (execution_id=%s)", name, workflow.id)
        return cast(str, workflow.id)

    def wait(
        self,
        execution_id: str,
        timeout: float = 300,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        """Wait for workflow completion.

        Args:
            execution_id: The Stabilize execution ID
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks

        Returns:
            Final workflow result with status and outputs

        Raises:
            TimeoutError: If workflow doesn't complete within timeout
        """
        start_time = time.time()
        logger.debug("Waiting for workflow %s (timeout=%ds)", execution_id, timeout)

        while time.time() - start_time < timeout:
            # Process pending messages (this advances the workflow)
            self._processor.process_all(timeout=poll_interval)

            # Check status
            result = self.status(execution_id)
            if result.get("is_complete"):
                elapsed = time.time() - start_time
                logger.info(
                    "Workflow %s completed (status=%s, elapsed=%.1fs)",
                    execution_id,
                    result.get("status"),
                    elapsed,
                )
                return result

            time.sleep(poll_interval)

        logger.warning("Workflow %s timed out after %ds", execution_id, timeout)
        raise TimeoutError(f"Workflow {execution_id} did not complete within {timeout}s")

    def status(self, execution_id: str, process_pending: bool = True) -> dict[str, Any]:
        """Get current workflow status from local store.

        Args:
            execution_id: The Stabilize execution ID
            process_pending: If True, process pending messages first to
                           advance in-progress workflows (default: True)

        Returns:
            Status dict with keys:
                - execution_id: str
                - status: str (running/succeeded/failed/etc)
                - is_complete: bool
                - highway_run_id: str | None
                - highway_status: str | None
                - highway_result: Any | None
                - error: str | None
        """
        # Process pending messages to advance workflow state
        if process_pending:
            self._processor.process_all(timeout=0.5)

        workflow = self._store.retrieve(execution_id)

        # Extract outputs from the highway stage
        outputs = {}
        if workflow.stages and workflow.stages[0].outputs:
            outputs = workflow.stages[0].outputs

        # Get error from stage context if present
        error = None
        if workflow.stages and workflow.stages[0].context:
            error = workflow.stages[0].context.get("error")

        return {
            "execution_id": execution_id,
            "status": workflow.status.name.lower(),
            "is_complete": workflow.status.is_complete,
            "is_halt": workflow.status.is_halt,
            "highway_run_id": outputs.get("highway_run_id"),
            "highway_status": outputs.get("highway_status"),
            "highway_result": outputs.get("highway_result"),
            "highway_current_step": outputs.get("highway_current_step"),
            "highway_progress": outputs.get("highway_progress"),
            "error": error or outputs.get("error"),
            "started_at": workflow.start_time,
            "completed_at": workflow.end_time,
        }

    def list_workflows(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List workflows from local store.

        Args:
            status: Filter by status (running/succeeded/failed)
            limit: Maximum number of workflows to return

        Returns:
            List of workflow status dicts
        """
        # Get all workflows (Stabilize store returns by application)
        workflows = self._store.list_workflows(
            application="highway-driver",
            limit=limit,
        )

        results = []
        for wf in workflows:
            wf_status = self.status(wf.id)

            # Filter by status if specified
            if status and wf_status["status"] != status.lower():
                continue

            results.append(wf_status)

        return results

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running workflow.

        Args:
            execution_id: The Stabilize execution ID

        Returns:
            True if cancellation was initiated
        """
        workflow = self._store.retrieve(execution_id)

        if workflow.status.is_complete:
            return False

        self._orchestrator.cancel(
            workflow,
            user="highway-driver",
            reason="Cancelled by user",
        )

        # Process the cancel message
        self._processor.process_all(timeout=1.0)

        return True

    def process_pending(self, timeout: float = 1.0) -> None:
        """Process any pending workflow messages.

        Call this periodically to advance in-progress workflows.

        Args:
            timeout: Maximum time to spend processing
        """
        self._processor.process_all(timeout=timeout)
