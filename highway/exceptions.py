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

class TaskDefinitionError(HighwayDriverError):
    """Raised when a task is defined incorrectly.

    Examples:
        - Multiple task types specified (shell=True, py=True)
        - No task type specified
        - Invalid dependency reference
        - Circular dependency detected
    """
