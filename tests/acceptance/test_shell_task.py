#!/usr/bin/env python3
"""Acceptance test: Shell task execution on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver

# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_shell_task_execution() -> None:
    """Submit shell task to Highway and verify execution."""
    driver = Driver()

    @driver.task(shell=True)
    def echo_test():
        return "echo 'Highway Driver SDK Acceptance Test'"

    result = driver.run(wait=True, timeout=60)

    assert result.status == "completed", f"Expected completed, got {result.status}"
    assert result.run_id is not None, "run_id should be set"
    assert result.state.value == "completed"
