"""Validator module for input validation."""

from __future__ import annotations

from typing import Any


def validate(value: Any) -> bool:
    """Validate that a value is a positive number.

    Args:
        value: Value to validate

    Returns:
        True if value is a positive number
    """
    if not isinstance(value, (int, float)):
        return False
    return value > 0


def validate_range(value: int | float, min_val: int | float, max_val: int | float) -> bool:
    """Validate that a value is within a range.

    Args:
        value: Value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        True if value is within range
    """
    return min_val <= value <= max_val


def validate_not_empty(value: str | list | dict) -> bool:
    """Validate that a collection is not empty.

    Args:
        value: Collection to validate

    Returns:
        True if collection has items
    """
    return len(value) > 0
