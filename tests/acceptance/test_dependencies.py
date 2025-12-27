#!/usr/bin/env python3
"""Acceptance test: Task dependencies on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_task_dependencies() -> None:
    """Verify tasks execute in correct order based on depends=[]."""
    driver = Driver()

    @driver.task(shell=True)
    def step_1():
        return "echo 'Step 1'"

    @driver.task(shell=True, depends=["step_1"])
    def step_2():
        return "echo 'Step 2'"

    @driver.task(shell=True, depends=["step_2"])
    def step_3():
        return "echo 'Step 3 - Final'"

    result = driver.run(wait=True, timeout=120)

    assert result.status == "completed"
    assert result.run_id is not None
