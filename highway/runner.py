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
