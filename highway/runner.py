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
