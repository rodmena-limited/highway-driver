#!/usr/bin/env python3
"""Acceptance test: Python code execution on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_python_code_execution() -> None:
    """Verify py=True executes Python code via tools.code.exec."""
    driver = Driver()

    @driver.task(py=True)
    def compute_values():
        # This code runs on Highway via tools.code.exec
        result = {
            "sum": 1 + 2 + 3,
            "product": 2 * 3 * 4,
            "greeting": "Hello from Highway",
        }
        return result

    result = driver.run(wait=True, timeout=120)

    assert result.status == "completed"
    assert result.run_id is not None
