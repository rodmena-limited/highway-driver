"""Stabilize-based workflow runner for Highway Driver.

This module provides the HighwayRunner class that executes Highway
workflows through Stabilize orchestration layer.

Architecture:
    highway-driver -> Stabilize (HighwayTask) -> Highway API

The Golden Rule:
    highway-driver NEVER talks directly to Highway Engine.
    All execution goes through Stabilize.
"""

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

if TYPE_CHECKING:
    from highway.result import WorkflowResult

logger = logging.getLogger(__name__)

# Default polling configuration
DEFAULT_POLL_INTERVAL = 5.0  # seconds


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

        # Start background processing - Stabilize handles threading internally
        self._processor.start()

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

        # Store and start - background processor handles execution
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

    def logs(self, run_id: str) -> list[dict[str, Any]]:
        """Get workflow execution logs.

        Args:
            run_id: Stabilize execution ID or Highway run ID

        Returns:
            List of log entries from the workflow execution
        """
        logs: list[dict[str, Any]] = []

        try:
            # Get workflow from Stabilize store
            result = self._store.retrieve(run_id)

            # Extract logs from stage context/outputs
            for stage in result.stages:
                stage_context = stage.context or {}
                stage_outputs = stage.outputs or {}

                # Check for Highway execution logs
                highway_result = stage_outputs.get("highway_result", {})
                if isinstance(highway_result, dict):
                    output = highway_result.get("output", highway_result)
                    if isinstance(output, dict):
                        stdout = output.get("stdout", "")
                        stderr = output.get("stderr", "")

                        if stdout:
                            logs.append(
                                {
                                    "type": "stdout",
                                    "stage": stage.ref_id,
                                    "content": stdout,
                                }
                            )
                        if stderr:
                            logs.append(
                                {
                                    "type": "stderr",
                                    "stage": stage.ref_id,
                                    "content": stderr,
                                }
                            )

                # Check for task-level logs
                for task in stage.tasks:
                    task_outputs = getattr(task, "outputs", {}) or {}
                    if task_outputs:
                        logs.append(
                            {
                                "type": "task_output",
                                "task": task.name,
                                "stage": stage.ref_id,
                                "content": task_outputs,
                            }
                        )

        except Exception as e:
            logger.warning("Failed to retrieve logs for %s: %s", run_id, e)
            logs.append(
                {
                    "type": "error",
                    "content": "Failed to retrieve logs: %s" % str(e),
                }
            )

        return logs

    def _create_stabilize_workflow(
        self,
        workflow_json: dict[str, Any],
        inputs: dict[str, Any],
        workflow_id: str | None,
    ) -> Workflow:
        """Create Stabilize Workflow with HighwayTask stage.

        Args:
            workflow_json: Highway workflow definition
            inputs: Workflow inputs
            workflow_id: Optional workflow ID

        Returns:
            Stabilize Workflow ready for execution
        """
        workflow_name = workflow_json.get("name", "driver_workflow")

        return Workflow.create(
            application="highway-driver",
            name=workflow_name,
            stages=[
                StageExecution(
                    ref_id="highway_execution",
                    type="highway",
                    name="Execute Highway Workflow",
                    context={
                        "highway_workflow_definition": workflow_json,
                        "highway_inputs": inputs,
                        "highway_api_endpoint": self.endpoint,
                        "highway_api_key": self.api_key,
                        "highway_poll_interval_seconds": self.poll_interval,
                    },
                    tasks=[
                        TaskExecution.create(
                            name="Highway Task",
                            implementing_class="highway",
                            stage_start=True,
                            stage_end=True,
                        ),
                    ],
                ),
            ],
        )

    def _package_artifact(
        self,
        durable_functions: dict[str, Callable[..., Any]] | None,
        package_dirs: dict[str, tuple[str, str]] | None,
    ) -> PackagedArtifact:
        """Package functions or directories into artifact ZIP.

        Args:
            durable_functions: Dict of function name -> callable
            package_dirs: Dict of task name -> (package_path, entrypoint)

        Returns:
            PackagedArtifact with file path and metadata
        """
        # If package directories specified, use first one
        # TODO: Support multiple package directories
        if package_dirs:
            first_task = next(iter(package_dirs.keys()))
            package_path, entrypoint = package_dirs[first_task]
            return package_directory(
                source_dir=package_path,
                entrypoint=entrypoint,
            )

        # Otherwise package individual functions
        if durable_functions:
            return package_functions(durable_functions)

        raise ValueError("No functions or packages to package")

    def _create_multistage_workflow(
        self,
        workflow_json: dict[str, Any],
        artifact_path: str,
        inputs: dict[str, Any],
    ) -> Workflow:
        """Create 2-stage workflow: upload artifact -> execute Highway workflow.

        Args:
            workflow_json: Highway workflow definition
            artifact_path: Path to ZIP file from mktemp
            inputs: Workflow inputs

        Returns:
            Stabilize Workflow with upload and execution stages
        """
        workflow_name = workflow_json.get("name", "driver_workflow")

        return Workflow.create(
            application="highway-driver",
            name=workflow_name,
            stages=[
                # Stage 1: Upload artifact via HTTPTask
                StageExecution(
                    ref_id="upload_artifact",
                    type="http",
                    name="Upload Artifact",
                    context={
                        "url": "%s/api/v1/artifacts" % self.endpoint,
                        "method": "POST",
                        "upload_file": artifact_path,
                        "upload_field": "artifact",
                        "bearer_token": self.api_key,
                        "parse_json": True,
                        "timeout": 60,
                    },
                    tasks=[
                        TaskExecution.create(
                            name="Upload",
                            implementing_class="http",
                            stage_start=True,
                            stage_end=True,
                        ),
                    ],
                ),
                # Stage 2: Execute Highway workflow with artifact_id
                # MUST depend on Stage 1 to get artifact_id from upload response
                StageExecution(
                    ref_id="highway_execution",
                    type="highway",
                    name="Execute Highway Workflow",
                    requisite_stage_ref_ids={"upload_artifact"},  # Wait for upload
                    context={
                        "highway_workflow_definition": self._inject_artifact_id(workflow_json),
                        "highway_inputs": inputs,
                        "highway_api_endpoint": self.endpoint,
                        "highway_api_key": self.api_key,
                        "highway_poll_interval_seconds": self.poll_interval,
                        # Map artifact_id from Stage 1's HTTPTask response
                        # body_json comes from HTTPTask output, HighwayTask resolves the path
                        "highway_input_mappings": {
                            "_artifact_id": "body_json.artifact_id",
                        },
                    },
                    tasks=[
                        TaskExecution.create(
                            name="Highway Task",
                            implementing_class="highway",
                            stage_start=True,
                            stage_end=True,
                        ),
                    ],
                ),
            ],
        )

    def _inject_artifact_id(
        self,
        workflow_json: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare workflow definition for artifact_id injection.

        The workflow tasks use {{_artifact_id}} which Highway resolves
        from workflow inputs. The actual artifact_id value is passed
        via highway_input_mappings -> HighwayTask resolves body_json.artifact_id
        and adds it to inputs before submitting to Highway.

        Args:
            workflow_json: Original workflow definition

        Returns:
            Workflow definition (unchanged, artifact_id comes from inputs)
        """
        # No modification needed - artifact_id is passed via inputs
        # from HighwayTask's highway_input_mappings resolution
        return workflow_json

    def _convert_to_workflow_result(
        self,
        stabilize_result: Workflow,
        stabilize_id: str,
    ) -> WorkflowResult:
        """Convert Stabilize result to highway WorkflowResult.

        Args:
            stabilize_result: Stabilize Workflow after execution
            stabilize_id: Stabilize execution ID

        Returns:
            WorkflowResult for highway-driver API
        """
        from highway.result import TaskResult, WorkflowResult, WorkflowState

        # Find the highway stage (may be stages[0] for single-stage or stages[1] for multi-stage)
        stage = None
        for s in stabilize_result.stages:
            if s.type == "highway":
                stage = s
                break
        # Fallback to last stage if no highway type found
        if stage is None:
            stage = stabilize_result.stages[-1]

        outputs = stage.outputs or {}
        context = stage.context or {}

        # Extract Highway-specific data from outputs or context
        # Use stabilize_id as fallback when Highway run_id isn't available yet
        highway_run_id = (
            outputs.get("highway_run_id") or context.get("highway_run_id") or stabilize_id
        )
        highway_status = (
            outputs.get("highway_status")
            or context.get("highway_status")
            or "unknown"
        )
        highway_result = outputs.get("highway_result") or context.get("highway_result") or {}

        # If status is still unknown but there's an error, infer failed
        stage_error = outputs.get("error") or context.get("error")
        if highway_status == "unknown" and stage_error:
            highway_status = "failed"

        # Map Stabilize status to WorkflowState
        state = self._map_status_to_state(highway_status, stabilize_result.status)

        # Parse task results from highway_result
        tasks: dict[str, TaskResult] = {}
        if isinstance(highway_result, dict):
            # Highway returns result with output key
            output = highway_result.get("output", highway_result)
            if isinstance(output, dict):
                # Try to parse __HIGHWAY_RESULT__ from stdout
                stdout = output.get("stdout", "")
                if "__HIGHWAY_RESULT__:" in stdout:
                    try:
                        import json

                        json_str = stdout.split("__HIGHWAY_RESULT__:")[1].strip()
                        json_str = json_str.split("\n")[0]
                        parsed = json.loads(json_str)
                        output["parsed_result"] = parsed
                    except Exception:
                        pass

                # Create task result from output
                for task_name in ["highway_task"]:
                    tasks[task_name] = TaskResult(
                        name=task_name,
                        state=state,
                        result=output,
                    )

        # Get error if failed (reuse stage_error from earlier check)
        error = stage_error if state == WorkflowState.FAILED else None

        return WorkflowResult(
            run_id=highway_run_id,
            workflow_id=None,
            status=highway_status,
            state=state,
            tasks=tasks,
            error=error,
            stabilize_execution_id=stabilize_id,
        )

    def _map_status_to_state(
        self,
        highway_status: str,
        stabilize_status: Any,
    ) -> WorkflowState:
        """Map status to WorkflowState enum.

        Args:
            highway_status: Highway workflow status string
            stabilize_status: Stabilize workflow status

        Returns:
            WorkflowState enum value
        """
        from highway.result import WorkflowState

        # Check Highway status first
        status_map = {
            "pending": WorkflowState.PENDING,
            "submitted": WorkflowState.SUBMITTED,
            "running": WorkflowState.RUNNING,
            "sleeping": WorkflowState.SLEEPING,
            "waiting": WorkflowState.WAITING,
            "completed": WorkflowState.COMPLETED,
            "failed": WorkflowState.FAILED,
            "cancelled": WorkflowState.CANCELLED,
            "canceled": WorkflowState.CANCELLED,
            "timed_out": WorkflowState.TIMED_OUT,
        }

        if highway_status.lower() in status_map:
            return status_map[highway_status.lower()]

        # Fall back to Stabilize status
        if hasattr(stabilize_status, "name"):
            stabilize_name = stabilize_status.name.lower()
            if stabilize_name in ("succeeded", "completed"):
                return WorkflowState.COMPLETED
            elif stabilize_name in ("terminal", "failed"):
                return WorkflowState.FAILED
            elif stabilize_name in ("cancelled", "canceled"):
                return WorkflowState.CANCELLED
            elif stabilize_name == "running":
                return WorkflowState.RUNNING

        return WorkflowState.PENDING


# Backwards compatibility alias
StabilizeRunner = HighwayRunner
