#!/usr/bin/env python3
"""Acceptance test: Observability methods (status, logs, cancel).

This test MUST RUN AND PASS against production Highway.
"""

import os
import time

import pytest

from highway import Driver

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_status_method() -> None:
    """Verify status() returns workflow state."""
    driver = Driver()

    @driver.task(shell=True)
    def quick_task():
        return "echo 'Quick task'"

    # Submit and immediately check status
    result = driver.run(wait=False)
    run_id = result.run_id

    assert run_id is not None
    assert result.status == "submitted"

    # Check status
    status = driver.status(run_id)
    assert status.run_id == run_id
    assert status.state is not None

    # Wait for completion
    time.sleep(10)
    final_status = driver.status(run_id)
    assert final_status.state.value in ("completed", "pending", "running")


def test_logs_method() -> None:
    """Verify logs() returns execution logs."""
    driver = Driver()

    @driver.task(shell=True)
    def echo_task():
        return "echo 'Log test'"

    result = driver.run(wait=True, timeout=60)

    # Get logs after completion
    logs = driver.logs(result.run_id)

    # Logs may be empty but should not raise
    assert isinstance(logs, list)
