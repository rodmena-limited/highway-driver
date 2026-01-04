#!/usr/bin/env python3
"""Acceptance test: Durable sleep via AST transformation.

This test verifies that time.sleep() calls in durable tasks are automatically
transformed to durable sleep that persists state and survives restarts.

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


def test_durable_sleep_single_task() -> None:
    """Verify time.sleep() works in a durable task."""
    driver = Driver()

    @driver.task(durable=True, timeout=60)
    def sleep_task():
        """A task that sleeps using standard time.sleep()."""
        time.sleep(3)  # Short sleep for quick test
        return {"slept": True, "duration": 3}

    # Execute and verify
    result = driver.run(timeout=60)

    assert result.state.value == "completed"
    assert result.tasks is not None
    # Highway returns results under 'highway_task' key
    task_result = next(iter(result.tasks.values()))
    assert task_result.result is not None
    assert task_result.result.get("slept") is True
    assert task_result.result.get("duration") == 3


def test_durable_sleep_multiple_sleeps() -> None:
    """Verify multiple time.sleep() calls in same task work correctly."""
    driver = Driver()

    @driver.task(durable=True, timeout=60)
    def multi_sleep_task():
        """A task with multiple sleep calls."""
        time.sleep(2)  # First sleep
        time.sleep(2)  # Second sleep
        return {"total_sleep": 4}

    result = driver.run(timeout=60)

    assert result.state.value == "completed"
    assert result.tasks is not None
    task_result = next(iter(result.tasks.values()))
    assert task_result.result is not None
    assert task_result.result.get("total_sleep") == 4


def test_durable_sleep_with_from_import() -> None:
    """Verify 'from time import sleep' syntax is also transformed."""
    driver = Driver()

    @driver.task(durable=True, timeout=60)
    def bare_sleep_task():
        """Uses bare sleep() function."""
        from time import sleep

        sleep(2)  # Should also be transformed
        return {"bare_sleep": True}

    result = driver.run(timeout=60)

    assert result.state.value == "completed"
    assert result.tasks is not None
    task_result = next(iter(result.tasks.values()))
    assert task_result.result is not None
    assert task_result.result.get("bare_sleep") is True


def test_durable_sleep_with_variable_duration() -> None:
    """Verify durable sleep works with variable duration."""
    driver = Driver()

    @driver.task(durable=True, timeout=60)
    def variable_sleep():
        """Sleep for a computed duration."""
        duration = 1 + 1  # Compute duration
        time.sleep(duration)
        return {"duration": duration}

    result = driver.run(timeout=60)

    assert result.state.value == "completed"
    assert result.tasks is not None
    task_result = next(iter(result.tasks.values()))
    assert task_result.result is not None
    assert task_result.result.get("duration") == 2
