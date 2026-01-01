import os
import pytest
from highway import Driver

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "acceptance: marks tests as acceptance tests (require API)"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests (no API required)"
    )

def api_key():
    """Return API key if available, None otherwise."""
    return os.environ.get("HIGHWAY_API_KEY")

def api_endpoint():
    """Return API endpoint (defaults to local dev)."""
    return os.environ.get("HIGHWAY_API_ENDPOINT", "http://localhost:7822")

def driver(api_key, api_endpoint):
    """Create a Driver instance with test configuration.

    Skips test if no API key is configured.
    """
    if not api_key:
        pytest.skip("HIGHWAY_API_KEY not set")
    d = Driver(api_key=api_key, endpoint=api_endpoint)
    yield d
    d.clear()
