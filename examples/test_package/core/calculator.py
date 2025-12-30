"""Calculator module with basic math operations."""

from __future__ import annotations


class Calculator:
    """Simple calculator for demonstration."""

    def __init__(self, precision: int = 2) -> None:
        """Initialize calculator.

        Args:
            precision: Decimal precision for results
        """
        self.precision = precision

    def add(self, a: int | float, b: int | float) -> int | float:
        """Add two numbers.

        Args:
            a: First number
            b: Second number

        Returns:
            Sum of a and b
        """
        return round(a + b, self.precision)

    def multiply(self, a: int | float, b: int | float) -> int | float:
        """Multiply two numbers.

        Args:
            a: First number
            b: Second number

        Returns:
            Product of a and b
        """
        return round(a * b, self.precision)

    def subtract(self, a: int | float, b: int | float) -> int | float:
        """Subtract b from a.

        Args:
            a: First number
            b: Second number

        Returns:
            Difference of a and b
        """
        return round(a - b, self.precision)

    def divide(self, a: int | float, b: int | float) -> float:
        """Divide a by b.

        Args:
            a: Dividend
            b: Divisor

        Returns:
            Quotient

        Raises:
            ValueError: If b is zero
        """
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return round(a / b, self.precision)
