"""Highway Driver SDK - Simple decorator SDK for Highway Workflow Engine.

This package provides a DBOS-style decorator interface for defining
and executing workflows on Highway. It reduces workflow definition
from 400+ lines to ~10 lines.

Workflows are executed through Stabilize for durability, crash recovery,
and local monitoring.

Example:
    from highway import Driver

    driver = Driver()  # Uses HIGHWAY_API_KEY env var

    @driver.task(shell=True)
    def backup_db():
        return "pg_dump mydb > backup.sql"

    @driver.task(shell=True, depends=["backup_db"])
    def verify_backup():
        return "ls -la backup.sql"

    result = driver.run()
    print(result.status)  # "completed"

For non-blocking execution:
    result = driver.run(wait=False)
    print(result.run_id)  # Check status later
    status = driver.status(result.run_id)

For local monitoring (no API calls):
    from highway import WorkflowMonitor

    monitor = WorkflowMonitor()
    for wf in monitor.list_workflows():
        print(f"{wf.execution_id} {wf.status}")
"""

from highway.context import Context
from highway.driver import Driver
from highway.exceptions import (
    ConfigurationError,
    ExecutionError,
    HighwayDriverError,
    NotSupportedError,
    SubmissionError,
    TaskDefinitionError,
    WorkflowBuildError,
)
from highway.handle import WorkflowHandle
from highway.monitor import WorkflowInfo, WorkflowMonitor
from highway.result import (
    TaskResult,
    WorkflowResult,
    WorkflowState,
    WorkflowStatus,
)
from highway.task import TaskDefinition, TaskType

__version__ = "0.1.0"

__all__ = [
    # Main interface
    "Driver",
    "Context",
    "WorkflowHandle",
    # Monitoring
    "WorkflowMonitor",
    "WorkflowInfo",
    # Result types
    "WorkflowResult",
    "WorkflowStatus",
    "WorkflowState",
    "TaskResult",
    # Task types
    "TaskDefinition",
    "TaskType",
    # Exceptions
    "HighwayDriverError",
    "ConfigurationError",
    "TaskDefinitionError",
    "WorkflowBuildError",
    "SubmissionError",
    "ExecutionError",
    "NotSupportedError",
]
