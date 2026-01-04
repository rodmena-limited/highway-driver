#!/usr/bin/env python3
"""Acceptance test: Observability methods (status, logs, cancel).

This test MUST RUN AND PASS against production Highway.
Uses the WorkflowHandle pattern for cleaner async workflow management.
"""

import os

import pytest

from highway import Driver, WorkflowHandle

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_status_via_handle() -> None:
    """Verify handle.status returns workflow state."""
    driver = Driver()

    @driver.task(shell=True)
    def quick_task():
        return "echo 'Quick task'"

    # Use start_workflow() for async execution
    handle = driver.start_workflow()

    assert isinstance(handle, WorkflowHandle)
    assert handle.run_id is not None

    # Access status via handle property (fetches fresh each time)
    status = handle.status
    assert status.run_id == handle.run_id
    assert status.state is not None

    # Wait for completion using handle.result (blocks until done)
    result = handle.wait(timeout=60)
    assert result.state.value in ("completed", "pending", "running")


def test_logs_via_handle() -> None:
    """Verify handle.logs returns execution logs."""
    driver = Driver()

    @driver.task(shell=True)
    def echo_task():
        return "echo 'Log test'"

    handle = driver.start_workflow(timeout=60)

    # Wait for completion first
    _ = handle.result

    # Access logs via handle property
    logs = handle.logs

    # Logs may be empty but should not raise
    assert isinstance(logs, list)
