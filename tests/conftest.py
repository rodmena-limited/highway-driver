"""Shared pytest fixtures for Highway Driver SDK tests.

This module provides common fixtures for both unit and acceptance tests.
"""

import os

import pytest
from dotenv import load_dotenv

# Load .env file for API credentials
load_dotenv()

from highway import Driver


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "acceptance: marks tests as acceptance tests (require API)")
    config.addinivalue_line("markers", "unit: marks tests as unit tests (no API required)")


@pytest.fixture
def api_key():
    """Return API key if available, None otherwise."""
    return os.environ.get("HIGHWAY_API_KEY")


@pytest.fixture
def api_endpoint():
    """Return API endpoint (defaults to local dev)."""
    return os.environ.get("HIGHWAY_API_ENDPOINT", "http://localhost:7822")


@pytest.fixture
def driver(api_key, api_endpoint):
    """Create a Driver instance with test configuration.

    Skips test if no API key is configured.
    """
    if not api_key:
        pytest.skip("HIGHWAY_API_KEY not set")
    d = Driver(api_key=api_key, endpoint=api_endpoint)
    yield d
    d.clear()


@pytest.fixture
def fresh_driver(api_key, api_endpoint):
    """Create a fresh Driver instance for each test.

    Use this when test modifies Driver state.
    """
    if not api_key:
        pytest.skip("HIGHWAY_API_KEY not set")
    return Driver(api_key=api_key, endpoint=api_endpoint)
