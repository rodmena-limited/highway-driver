"""AST transformations for durable execution.

This module provides AST-based transformations that automatically
convert standard Python constructs to durable equivalents.

Currently supports:
- time.sleep() -> durable sleep (survives restarts)

Usage:
    The transformations are applied automatically during artifact
    packaging for functions decorated with @task(durable=True).

Example:
    # What developers write (natural Python):
    @driver.task(durable=True)
    def my_task():
        time.sleep(60)  # Just Python!
        return {"done": True}

    # What gets executed (transformed by AST):
    def my_task():
        _durable_sleep(60, step_name="sleep_line_3")
        return {"done": True}
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable


class DurableSleepTransformer(ast.NodeTransformer):
    """AST transformer that rewrites time.sleep() to durable sleep.

    Transforms:
        time.sleep(X)  ->  _durable_sleep(X, step_name="sleep_{lineno}")
        sleep(X)       ->  _durable_sleep(X, step_name="sleep_{lineno}")

    The step_name is auto-generated from the line number for uniqueness.
    """

    def __init__(self, func_name: str = "unknown"):
        """Initialize transformer.

        Args:
            func_name: Name of function being transformed (for step naming)
        """
        super().__init__()
        self.func_name = func_name
        self.sleep_count = 0  # Counter for unique step names

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Visit a function call and transform sleep calls."""
        self.generic_visit(node)  # Visit children first

        if self._is_sleep_call(node):
            return self._make_durable_sleep(node)
        return node

    def _is_sleep_call(self, node: ast.Call) -> bool:
        """Check if this is a time.sleep() or sleep() call.

        Matches:
            - time.sleep(X)
            - sleep(X) if imported from time
        """
        # Match: time.sleep(...)
        if isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "sleep"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "time"
            ):
                return True

        # Match: sleep(...) - from time import sleep
        if isinstance(node.func, ast.Name) and node.func.id == "sleep":
            return True

        return False

    def _make_durable_sleep(self, node: ast.Call) -> ast.Call:
        """Transform a sleep call to durable sleep.

        Args:
            node: The original sleep call AST node

        Returns:
            New AST node for _durable_sleep() call
        """
        self.sleep_count += 1

        # Generate unique step name from function name and line number
        step_name = f"sleep_{self.func_name}_{node.lineno}_{self.sleep_count}"

        # Get the sleep duration argument
        if node.args:
            duration_arg = node.args[0]
        elif node.keywords:
            # Handle: time.sleep(seconds=60)
            for kw in node.keywords:
                if kw.arg in ("seconds", "secs", None):
                    duration_arg = kw.value
                    break
            else:
                # Fallback to first keyword
                duration_arg = node.keywords[0].value
        else:
            # No arguments - sleep(0)
            duration_arg = ast.Constant(value=0)

        # Create: _durable_sleep(duration, step_name="...")
        new_call = ast.Call(
            func=ast.Name(id="_durable_sleep", ctx=ast.Load()),
            args=[duration_arg],
            keywords=[
                ast.keyword(
                    arg="step_name",
                    value=ast.Constant(value=step_name),
                )
            ],
        )

        # Preserve location information
        ast.copy_location(new_call, node)
        ast.fix_missing_locations(new_call)

        return new_call


def transform_function_for_durability(
    func: Callable,
    apply_sleep_transform: bool = True,
) -> str:
    """Transform a function's source code for durable execution.

    This extracts the function source, applies AST transformations,
    and returns the transformed source code.

    Args:
        func: The function to transform
        apply_sleep_transform: Whether to transform time.sleep() calls

    Returns:
        Transformed Python source code

    Raises:
        ValueError: If source cannot be extracted or parsed
    """
    func_name = getattr(func, "__name__", "unknown")

    try:
        source = inspect.getsource(func)
    except (OSError, TypeError) as e:
        raise ValueError(f"Cannot extract source for '{func_name}': {e}") from e

    # Dedent to handle indented functions
    source = textwrap.dedent(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError(f"Cannot parse source for '{func_name}': {e}") from e

    if not tree.body:
        raise ValueError(f"Empty source for function '{func_name}'")

    node = tree.body[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError(f"Expected function definition for '{func_name}'")

    # Apply transformations
    if apply_sleep_transform:
        transformer = DurableSleepTransformer(func_name)
        node = transformer.visit(node)
        ast.fix_missing_locations(node)

    # Return transformed source
    return ast.unparse(node)


def get_durable_sleep_helper() -> str:
    """Return the _durable_sleep helper function source.

    This function is injected into the artifact to provide durable sleep
    functionality. It uses set_variable/get_variable to persist sleep
    state across restarts.

    Returns:
        Python source code for _durable_sleep function
    """
    return '''
def _durable_sleep(seconds: float, step_name: str = "sleep") -> None:
    """Durable sleep that survives process restarts.

    Uses Highway's variable storage to persist sleep state. If the process
    restarts during sleep, it will calculate remaining time and continue.

    Args:
        seconds: Duration to sleep in seconds
        step_name: Unique name for this sleep step (auto-generated)
    """
    import time as _time

    # Get context from thread-local
    from . import highway_context as _hc
    ctx = _hc.get_context()

    # Check if this sleep was already completed
    completed_key = f"_sleep_done_{step_name}"
    if ctx.get_variable(completed_key, False):
        return  # Already slept, skip

    # Check if sleep was started (for resumption after restart)
    start_key = f"_sleep_start_{step_name}"
    start_time = ctx.get_variable(start_key, None)

    if start_time is None:
        # First time - record start time
        start_time = _time.time()
        ctx.set_variable(start_key, start_time)

    # Calculate remaining sleep time
    elapsed = _time.time() - start_time
    remaining = max(0, seconds - elapsed)

    if remaining > 0:
        _time.sleep(remaining)

    # Mark as completed
    ctx.set_variable(completed_key, True)
'''


def generate_durable_imports() -> str:
    """Generate import statements needed for durable transforms.

    Returns:
        Python source code for import statements
    """
    return "import time"
