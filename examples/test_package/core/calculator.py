from __future__ import annotations

class Calculator:
    """Simple calculator for demonstration."""
    def __init__(self, precision: int = 2) -> None:
        """Initialize calculator.

        Args:
            precision: Decimal precision for results
        """
        self.precision = precision
