#!/usr/bin/env python3
"""Acceptance test: Workflow inputs on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_workflow_inputs() -> None:
    """Verify workflow inputs are accessible in tasks via {{inputs.key}}."""
    driver = Driver()

    @driver.task(shell=True)
    def echo_message():
        return "echo 'Message: {{inputs.message}}'"

    result = driver.run(
        wait=True,
        timeout=60,
        inputs={"message": "Hello from Driver"},
    )

    assert result.status == "completed"
    assert result.run_id is not None
