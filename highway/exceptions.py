from __future__ import annotations

class HighwayDriverError(Exception):
    """Base exception for all Highway Driver errors."""

class ConfigurationError(HighwayDriverError):
    """Raised when configuration is invalid or missing.

    Examples:
        - Missing API key
        - Invalid endpoint URL
        - Invalid timeout value
    """
