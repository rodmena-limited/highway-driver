#!/usr/bin/env python3
"""Acceptance test: WorkflowHandle pattern.

Tests the simplified WorkflowHandle API for async workflow management.
This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver, WorkflowHandle

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_start_workflow_returns_handle() -> None:
    """Verify start_workflow() returns a WorkflowHandle."""
    driver = Driver()

    @driver.task(shell=True)
    def quick_task():
        return "echo 'Hello from handle test'"

    handle = driver.start_workflow()

    assert isinstance(handle, WorkflowHandle)
    assert handle.run_id is not None
    assert len(handle.run_id) > 0


def test_handle_status_property() -> None:
    """Verify handle.status returns fresh status."""
    driver = Driver()

    @driver.task(shell=True)
    def status_task():
        return "echo 'Status test'"

    handle = driver.start_workflow()

    # Access status property (should fetch fresh each time)
    status1 = handle.status
    assert status1 is not None
    assert status1.run_id == handle.run_id

    # Status should have a state
    assert status1.state is not None


def test_handle_result_blocks_until_complete() -> None:
    """Verify handle.result blocks until workflow completes."""
    driver = Driver()

    @driver.task(shell=True)
    def blocking_task():
        return "echo 'Blocking test'"

    handle = driver.start_workflow(timeout=300)

    # Accessing .result should block until complete
    result = handle.result

    assert result is not None
    assert result.state.is_terminal()


def test_handle_result_is_cached() -> None:
    """Verify handle.result is cached after first access."""
    driver = Driver()

    @driver.task(shell=True)
    def cache_task():
        return "echo 'Cache test'"

    handle = driver.start_workflow(timeout=120)

    # First access blocks
    result1 = handle.result

    # Second access should return cached value instantly
    result2 = handle.result

    # Should be the same object (cached)
    assert result1 is result2


def test_retrieve_workflow() -> None:
    """Verify retrieve_workflow() creates handle for existing workflow."""
    driver = Driver()

    @driver.task(shell=True)
    def retrieve_task():
        return "echo 'Retrieve test'"

    # Start workflow and get run_id
    original_handle = driver.start_workflow()
    run_id = original_handle.run_id

    # Create a new driver instance (simulating different session)
    driver2 = Driver()

    # Retrieve the workflow
    retrieved_handle = driver2.retrieve_workflow(run_id)

    assert isinstance(retrieved_handle, WorkflowHandle)
    assert retrieved_handle.run_id == run_id

    # Should be able to get status
    status = retrieved_handle.status
    assert status is not None


def test_handle_logs_property() -> None:
    """Verify handle.logs returns execution logs."""
    driver = Driver()

    @driver.task(shell=True)
    def logs_task():
        return "echo 'Logs test'"

    handle = driver.start_workflow(timeout=120)

    # Wait for completion first
    _ = handle.result

    # Access logs
    logs = handle.logs
    assert isinstance(logs, list)


def test_handle_cancel() -> None:
    """Verify handle.cancel() works."""
    driver = Driver()

    @driver.task(shell=True)
    def long_task():
        return "sleep 60 && echo 'Done'"

    handle = driver.start_workflow()

    # Cancel immediately
    result = handle.cancel()

    # Cancel should return bool
    assert isinstance(result, bool)


def test_handle_repr() -> None:
    """Verify handle has useful string representation."""
    driver = Driver()

    @driver.task(shell=True)
    def repr_task():
        return "echo 'Repr test'"

    handle = driver.start_workflow()

    # Should have useful repr
    repr_str = repr(handle)
    assert "WorkflowHandle" in repr_str
    assert handle.run_id in repr_str


def test_handle_wait_method() -> None:
    """Verify handle.wait() method with custom timeout."""
    driver = Driver()

    @driver.task(shell=True)
    def wait_task():
        return "echo 'Wait test'"

    handle = driver.start_workflow()

    # Use wait() method with custom timeout
    result = handle.wait(timeout=300)

    assert result is not None
    assert result.state.is_terminal()
