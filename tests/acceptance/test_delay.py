#!/usr/bin/env python3
"""Acceptance test: Delay (durable sleep) execution on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os
import time
from datetime import timedelta

import pytest

from highway import Driver

# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_delay_execution() -> None:
    """Verify delay uses Highway's WaitOperator for durable sleep."""
    driver = Driver()

    @driver.task(shell=True)
    def quick_task():
        return "echo 'quick'"

    @driver.task(shell=True, delay=timedelta(seconds=5), depends=["quick_task"])
    def delayed_task():
        return "echo 'after delay'"

    start = time.time()
    result = driver.run(wait=True, timeout=60)
    elapsed = time.time() - start

    assert result.status == "completed", "Expected completed, got %s" % result.status
    assert result.run_id is not None
    # Should take at least 5 seconds due to WaitOperator
    assert elapsed >= 5.0, "Expected at least 5s delay, got %.1fs" % elapsed


def test_delay_no_dependencies() -> None:
    """Verify delay works on start task with no dependencies."""
    driver = Driver()

    @driver.task(shell=True, delay=timedelta(seconds=3))
    def delayed_start():
        return "echo 'delayed start'"

    start = time.time()
    result = driver.run(wait=True, timeout=60)
    elapsed = time.time() - start

    assert result.status == "completed"
    assert elapsed >= 3.0, "Expected at least 3s delay, got %.1fs" % elapsed
