#!/usr/bin/env python3
"""Acceptance test: Generic tool interface on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_generic_tool_shell() -> None:
    """Verify tool= parameter works with tools.shell.run.

    This uses the generic tool interface to call the same underlying
    tool that shell=True uses, demonstrating the mechanism works.
    """
    driver = Driver()

    @driver.task(tool="tools.shell.run")
    def echo_via_tool():
        # When using tool=, function returns the kwargs
        # For tools.shell.run, first positional arg is the command
        return {"command": "echo 'Hello from generic tool interface'"}

    result = driver.run(wait=True, timeout=60)

    assert result.status == "completed"
    assert result.run_id is not None


def test_generic_tool_http_request() -> None:
    """Verify tool= parameter works with tools.http.request."""
    driver = Driver()

    @driver.task(tool="tools.http.request")
    def fetch_via_tool():
        return {
            "url": "https://httpbin.org/get",
            "method": "GET",
            "timeout": 30,
        }

    result = driver.run(wait=True, timeout=60)

    assert result.status == "completed"
    assert result.run_id is not None
