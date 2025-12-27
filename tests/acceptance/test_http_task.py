#!/usr/bin/env python3
"""Acceptance test: HTTP task execution on Highway.

This test MUST RUN AND PASS against production Highway.
"""

import os

import pytest

from highway import Driver

pytestmark = pytest.mark.skipif(
    not os.environ.get("HIGHWAY_API_KEY"),
    reason="HIGHWAY_API_KEY not set",
)


def test_http_task() -> None:
    """Verify HTTP tasks work with tools.http.request."""
    driver = Driver()

    @driver.task(http=True)
    def fetch_httpbin():
        return {
            "url": "https://httpbin.org/get",
            "method": "GET",
            "timeout": 30,
        }

    result = driver.run(wait=True, timeout=60)

    assert result.status == "completed"
    assert result.run_id is not None
