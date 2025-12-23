"""Highway Driver SDK Exceptions.

All exceptions raised by the Highway Driver SDK are defined here.
Each exception includes a reference to the issuedb issue for tracking.
"""

from __future__ import annotations


class HighwayDriverError(Exception):
    """Base exception for all Highway Driver errors."""

    pass


class ConfigurationError(HighwayDriverError):
    """Raised when configuration is invalid or missing.

    Examples:
        - Missing API key
        - Invalid endpoint URL
        - Invalid timeout value
    """

    pass


class TaskDefinitionError(HighwayDriverError):
    """Raised when a task is defined incorrectly.

    Examples:
        - Multiple task types specified (shell=True, py=True)
        - No task type specified
        - Invalid dependency reference
        - Circular dependency detected
    """

    pass


class WorkflowBuildError(HighwayDriverError):
    """Raised when workflow DSL generation fails.

    Examples:
        - Cannot serialize task to Highway DSL
        - Invalid workflow structure
        - Missing required workflow fields
    """

    pass


class SubmissionError(HighwayDriverError):
    """Raised when workflow submission to Highway fails.

    Examples:
        - Network error
        - Authentication failure (401/403)
        - Server error (5xx)
    """

    pass


class ExecutionError(HighwayDriverError):
    """Raised when workflow execution fails.

    Examples:
        - Workflow failed status from Highway
        - Timeout waiting for completion
        - Cancelled by user
    """

    pass


class NotSupportedError(HighwayDriverError):
    """Raised for features not yet implemented.

    All incomplete features raise this with a reference to the
    tracking issue for when it will be implemented.
    """

    def __init__(self, feature: str, issue_ref: str = ""):
        msg = "Feature '%s' is not yet supported" % feature
        if issue_ref:
            msg += ". Track: %s" % issue_ref
        super().__init__(msg)
        self.feature = feature
        self.issue_ref = issue_ref
