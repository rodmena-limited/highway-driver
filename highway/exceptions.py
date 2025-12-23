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

class WorkflowBuildError(HighwayDriverError):
    """Raised when workflow DSL generation fails.

    Examples:
        - Cannot serialize task to Highway DSL
        - Invalid workflow structure
        - Missing required workflow fields
    """

class SubmissionError(HighwayDriverError):
    """Raised when workflow submission to Highway fails.

    Examples:
        - Network error
        - Authentication failure (401/403)
        - Server error (5xx)
    """
