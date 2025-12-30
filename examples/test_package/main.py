"""Main entrypoint for test package.

This module demonstrates cross-module imports and DurableContext usage.

IMPORTANT: Package mode vs Inline function mode:

- **Package mode** (package="./my_pkg", entrypoint="main:func"):
  Functions MUST accept `ctx` as first parameter. Engine passes it.

- **Inline function mode** (durable=True, no package=):
  Functions can use get_context() without ctx parameter.
  Wrapper handles ctx injection automatically.

This package uses package mode, so ctx parameter is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Cross-module imports to test package structure
from test_package.core.calculator import Calculator
from test_package.core.validator import validate
from test_package.utils.helpers import format_result, log_operation

if TYPE_CHECKING:
    # DurableContext is injected by Highway at runtime
    pass


def run_calculation(ctx: Any) -> dict[str, Any]:
    """Main entrypoint - receives DurableContext.

    This function demonstrates:
    1. Cross-module imports (Calculator, validate, format_result)
    2. DurableContext usage (get_variable, set_variable)
    3. Proper return value handling

    Args:
        ctx: DurableContext from Highway

    Returns:
        Dictionary with calculation results
    """
    calc = Calculator()

    # Get variables from workflow context
    a = ctx.get_variable("a", 10)
    b = ctx.get_variable("b", 5)

    # Perform calculations
    sum_result = calc.add(a, b)
    product = calc.multiply(a, b)
    difference = calc.subtract(a, b)

    # Validate results
    sum_valid = validate(sum_result)
    product_valid = validate(product)

    # Store results in workflow state (persists across iterations)
    if sum_valid:
        ctx.set_variable("sum", sum_result)
    if product_valid:
        ctx.set_variable("product", product)

    # Create log entries
    sum_log = log_operation("addition", a, b, sum_result)
    product_log = log_operation("multiplication", a, b, product)

    return {
        "sum": format_result("addition", sum_result),
        "product": format_result("multiplication", product),
        "difference": format_result("subtraction", difference),
        "sum_valid": sum_valid,
        "product_valid": product_valid,
        "logs": [sum_log, product_log],
    }


def increment_counter(ctx: Any) -> dict[str, Any]:
    """Increment counter - for while_loop testing.

    Args:
        ctx: DurableContext from Highway

    Returns:
        Dictionary with new counter value
    """
    counter = ctx.get_variable("counter", 0)
    limit = ctx.get_variable("limit", 5)

    new_counter = counter + 1
    ctx.set_variable("counter", new_counter)

    return {
        "iteration": new_counter,
        "remaining": limit - new_counter,
        "complete": new_counter >= limit,
    }
