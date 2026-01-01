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
