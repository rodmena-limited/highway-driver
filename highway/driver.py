from __future__ import annotations
import ast
import inspect
import logging
import os
import textwrap
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypeVar
from highway.ast_utils import FunctionAnalyzer
from highway.exceptions import (
    ConfigurationError,
    NotSupportedError,
    TaskDefinitionError,
)
from highway.result import WorkflowResult
from highway.task import TaskDefinition, TaskType
logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])

class Driver:
    """Highway Driver - Simple decorator SDK for Highway Workflow Engine.

    The Driver class provides a DBOS-style decorator interface for defining
    and executing workflows on Highway. It handles:

    - Task registration via @driver.task() decorator
    - Workflow DSL generation
    - Execution via Stabilize orchestration layer
    - Status polling and result retrieval

    Architecture (Golden Rule - Driver NEVER talks directly to Highway):
        Driver -> Stabilize (HighwayTask) -> Highway API

    Example:
        from highway import Driver

        driver = Driver()  # Uses HIGHWAY_API_KEY env var

        @driver.task(shell=True)
        def backup_db():
            return "pg_dump mydb > backup.sql"

        @driver.task(py=True, depends=["backup_db"])
        def verify_backup():
            import os
            return os.path.exists("backup.sql")

        result = driver.run()
        print(result.status)  # "completed"

    Attributes:
        api_key: Highway API key for authentication
        endpoint: Highway API endpoint URL
        tasks: Registered task definitions
    """
    def __init__(
        self,
        name: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        """Initialize Highway Driver.

        Args:
            name: Workflow name. If not provided, auto-generates from first task
                  or uses 'driver_workflow_<uuid>'.
            api_key: Highway API key. If not provided, reads from
                     HIGHWAY_API_KEY environment variable.
            endpoint: Highway API endpoint URL.
                      Defaults to https://highway.solutions

        Note:
            API key is required. All execution goes through
            Stabilize -> Highway API.

        Example:
            driver = Driver(name="payment-processor")  # Explicit name
            driver = Driver()  # Auto: 'workflow_<first_task>' or 'driver_workflow_<uuid>'
        """
        self._name = name
        self.api_key = api_key or os.environ.get("HIGHWAY_API_KEY", "")
        self.endpoint = endpoint or os.environ.get("HIGHWAY_API_ENDPOINT", "https://highway.solutions")
        self._tasks: dict[str, TaskDefinition] = {}
        self._analyzer = FunctionAnalyzer()
