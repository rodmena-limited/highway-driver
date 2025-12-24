from __future__ import annotations
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from stabilize import StageExecution, TaskExecution, Workflow
from stabilize.handlers.complete_stage import CompleteStageHandler
from stabilize.handlers.complete_task import CompleteTaskHandler
from stabilize.handlers.complete_workflow import CompleteWorkflowHandler
from stabilize.handlers.run_task import RunTaskHandler
from stabilize.handlers.start_stage import StartStageHandler
from stabilize.handlers.start_task import StartTaskHandler
from stabilize.handlers.start_workflow import StartWorkflowHandler
from stabilize.orchestrator import Orchestrator
from stabilize.persistence.sqlite import SqliteWorkflowStore
from stabilize.queue.processor import QueueProcessor
from stabilize.queue.sqlite_queue import SqliteQueue
from stabilize.tasks.highway import HighwayTask
from stabilize.tasks.http import HTTPTask
from stabilize.tasks.registry import TaskRegistry
from highway.artifact import (
    PackagedArtifact,
    cleanup_artifact,
    package_directory,
    package_functions,
)
logger = logging.getLogger(__name__)
DEFAULT_POLL_INTERVAL = 5.0  # seconds
StabilizeRunner = HighwayRunner

class HighwayRunner:
    """Execute workflows via Stabilize + HighwayTask.

    This class provides the execution layer for highway-driver SDK.
    All Highway API communication goes through Stabilize's HighwayTask.

    Example:
        runner = HighwayRunner(
            api_key="hw_k1_...",
            endpoint="https://highway.solutions",
        )
        result = runner.run(workflow_json, inputs={}, timeout=300)
    """
    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Initialize Highway runner with Stabilize infrastructure.

        Args:
            api_key: Highway API key (falls back to HIGHWAY_API_KEY env var)
            endpoint: Highway API endpoint (falls back to HIGHWAY_API_ENDPOINT)
            poll_interval: Seconds between status polls (default: 5.0)
        """
        self.api_key = api_key or os.environ.get("HIGHWAY_API_KEY", "")
        self.endpoint = (
            endpoint or os.environ.get("HIGHWAY_API_ENDPOINT", "https://highway.solutions")
        ).rstrip("/")
        self.poll_interval = poll_interval

        # Setup Stabilize infrastructure with persistent SQLite
        db_url = "sqlite:///stabilize.db"
        self._store = SqliteWorkflowStore(db_url, create_tables=True)
        self._queue = SqliteQueue(db_url, table_name="queue_messages")
        self._queue._create_table()

        # Register tasks
        self._registry = TaskRegistry()
        self._registry.register("highway", HighwayTask)
        self._registry.register("http", HTTPTask)

        # Setup processor with all handlers
        self._processor = QueueProcessor(self._queue)
        self._register_handlers()

        self._orchestrator = Orchestrator(self._queue)

    def _register_handlers(self) -> None:
        """Register all Stabilize message handlers."""
        handlers = [
            StartWorkflowHandler(self._queue, self._store),
            StartStageHandler(self._queue, self._store),
            StartTaskHandler(self._queue, self._store),
            RunTaskHandler(self._queue, self._store, self._registry),
            CompleteTaskHandler(self._queue, self._store),
            CompleteStageHandler(self._queue, self._store),
            CompleteWorkflowHandler(self._queue, self._store),
        ]

        for handler in handlers:
            self._processor.register_handler(handler)

    def close(self) -> None:
        """Close resources."""
        pass

    def __enter__(self) -> HighwayRunner:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def run(
        self,
        workflow_json: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        timeout: float = 300,
        workflow_id: str | None = None,
        durable_functions: dict[str, Callable[..., Any]] | None = None,
        package_dirs: dict[str, tuple[str, str]] | None = None,
    ) -> WorkflowResult:
        """Execute workflow through Stabilize and wait for completion.

        Flow:
        1. If durable tasks exist, package and create multi-stage workflow
        2. Create Stabilize Workflow with HighwayTask stage
        3. Stabilize's HighwayTask submits to Highway API
        4. Stabilize polls and manages state
        5. Return results from Stabilize store

        Args:
            workflow_json: Highway workflow definition JSON
            inputs: Optional workflow inputs (merged into workflow variables)
            timeout: Maximum execution time in seconds
            workflow_id: Optional workflow ID for idempotency
            durable_functions: Dict of function name -> callable for auto-packaging
            package_dirs: Dict of task name -> (package_path, entrypoint)

        Returns:
            WorkflowResult with execution results
        """
        # Merge inputs into workflow variables
        if inputs:
            workflow_json = workflow_json.copy()
            variables = workflow_json.get("variables", {})
            variables.update(inputs)
            workflow_json["variables"] = variables

        artifact: PackagedArtifact | None = None

        try:
            # Check if we need multi-stage workflow for artifact upload
            if durable_functions or package_dirs:
                # Package functions/packages into artifact
                artifact = self._package_artifact(durable_functions, package_dirs)

                # Create multi-stage workflow: upload artifact -> execute Highway
                stabilize_workflow = self._create_multistage_workflow(
                    workflow_json, artifact.file_path, inputs or {}
                )
            else:
                # Create single-stage workflow with HighwayTask
                stabilize_workflow = self._create_stabilize_workflow(
                    workflow_json, inputs or {}, workflow_id
                )

            # Store and start
            self._store.store(stabilize_workflow)
            self._orchestrator.start(stabilize_workflow)

            logger.info(
                "Workflow submitted to Stabilize: stabilize_id=%s",
                stabilize_workflow.id,
            )

            # Process until complete or timeout
            self._processor.process_all(timeout=timeout)

            # Get result from Stabilize store
            result = self._store.retrieve(stabilize_workflow.id)
            return self._convert_to_workflow_result(result, stabilize_workflow.id)

        finally:
            # Clean up temporary artifact file
            if artifact:
                cleanup_artifact(artifact)

    def submit(
        self,
        workflow_json: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        durable_functions: dict[str, Callable[..., Any]] | None = None,
        package_dirs: dict[str, tuple[str, str]] | None = None,
    ) -> WorkflowResult:
        """Submit workflow without waiting for completion.

        Args:
            workflow_json: Highway workflow definition JSON
            inputs: Optional workflow inputs
            workflow_id: Optional workflow ID for tracking
            durable_functions: Dict of function name -> callable for auto-packaging
            package_dirs: Dict of task name -> (package_path, entrypoint)

        Returns:
            WorkflowResult with run_id for tracking (uses stabilize_execution_id
            until Highway run_id is available)
        """
        from highway.result import WorkflowResult, WorkflowState

        # Merge inputs into workflow variables
        if inputs:
            workflow_json = workflow_json.copy()
            variables = workflow_json.get("variables", {})
            variables.update(inputs)
            workflow_json["variables"] = variables

        # Check if we need multi-stage workflow for artifact upload
        if durable_functions or package_dirs:
            # Package functions/packages into artifact
            artifact = self._package_artifact(durable_functions, package_dirs)

            # Create multi-stage workflow: upload artifact -> execute Highway
            stabilize_workflow = self._create_multistage_workflow(
                workflow_json, artifact.file_path, inputs or {}
            )
            # Note: artifact cleanup happens after workflow completes (not immediate)
        else:
            # Create Stabilize workflow with HighwayTask
            stabilize_workflow = self._create_stabilize_workflow(
                workflow_json, inputs or {}, workflow_id
            )

        # Store and start (non-blocking)
        self._store.store(stabilize_workflow)
        self._orchestrator.start(stabilize_workflow)

        logger.info(
            "Workflow submitted to Stabilize: stabilize_id=%s",
            stabilize_workflow.id,
        )

        # Return stabilize_execution_id as run_id for tracking
        # The Highway run_id will be available after first poll via status()
        return WorkflowResult(
            run_id=stabilize_workflow.id,  # Use stabilize ID for tracking
            workflow_id=workflow_id,
            status="submitted",
            state=WorkflowState.SUBMITTED,
            started_at=datetime.now(UTC),
            stabilize_execution_id=stabilize_workflow.id,
        )

    def status(self, run_id: str) -> WorkflowResult:
        """Get workflow execution status.

        Args:
            run_id: Stabilize execution ID or Highway run ID

        Returns:
            WorkflowResult with current state
        """
        from highway.result import WorkflowResult, WorkflowState

        try:
            # Try to retrieve from Stabilize store
            result = self._store.retrieve(run_id)
            return self._convert_to_workflow_result(result, run_id)

        except Exception as e:
            logger.warning("Failed to retrieve status for %s: %s", run_id, e)
            return WorkflowResult(
                run_id=run_id,
                status="error",
                state=WorkflowState.FAILED,
                error="Failed to retrieve status: %s" % str(e),
            )

    def cancel(self, run_id: str) -> bool:
        """Cancel workflow execution.

        Args:
            run_id: Stabilize execution ID

        Returns:
            True if cancellation was requested
        """
        try:
            from stabilize.queue.messages import CancelWorkflow

            self._queue.push(CancelWorkflow(execution_id=run_id))
            logger.info("Cancellation requested for workflow %s", run_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel workflow %s: %s", run_id, e)
            return False
