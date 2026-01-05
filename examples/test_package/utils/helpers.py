"""Helper utilities for formatting and logging."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def format_result(operation: str, result: int | float) -> str:
    """Format an operation result as a string.

    Args:
        operation: Name of the operation (e.g., "addition")
        result: Numeric result

    Returns:
        Formatted string
    """
    return f"Result of {operation}: {result}"


def log_operation(operation: str, a: Any, b: Any, result: Any) -> dict[str, Any]:
    """Create a log entry for an operation.

    Args:
        operation: Name of the operation
        a: First operand
        b: Second operand
        result: Operation result

    Returns:
        Log entry dictionary
    """
    return {
        "operation": operation,
        "operands": [a, b],
        "result": result,
        "timestamp": datetime.now().isoformat(),
    }


def format_error(error: Exception) -> dict[str, str]:
    """Format an exception as a dictionary.

    Args:
        error: Exception to format

    Returns:
        Error dictionary with type and message
    """
    return {
        "error_type": type(error).__name__,
        "message": str(error),
    }
