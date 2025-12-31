from __future__ import annotations
import ast
import hashlib
import inspect
import logging
import os
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable
logger = logging.getLogger(__name__)

def _generate_wrapper(func_name: str) -> str:
    """Generate a wrapper function that handles ctx injection.

    The wrapper:
    - Accepts ctx as first param (engine always passes it)
    - Inspects original function to see if it wants ctx
    - If yes: passes ctx through
    - If no: sets thread-local context and calls without ctx

    Args:
        func_name: Name of the original function

    Returns:
        Python source code for wrapper function
    """
    # Use string formatting to avoid AST complexity
    wrapper = '''def _hw_{func_name}(ctx, *_args, **_kwargs):
    """Highway wrapper for {func_name} - handles ctx injection."""
    _sig = _inspect.signature({func_name})
    _params = list(_sig.parameters.keys())

    # Check if original function wants ctx as first param
    if _params and _params[0] in ('ctx', 'context'):
        return {func_name}(ctx, *_args, **_kwargs)
    else:
        # Set thread-local context for get_context() access
        _hc._set_context(ctx)
        try:
            return {func_name}(*_args, **_kwargs)
        finally:
            _hc._clear_context()'''.format(func_name=func_name)

    return wrapper

def _get_highway_context_module() -> str:
    """Return content for highway_context.py module.

    This module provides thread-local context access for user code
    that doesn't accept ctx as a parameter.

    Returns:
        Python source code for highway_context.py
    """
    return '''"""Highway context helper for accessing DurableContext.

This module provides get_context() for accessing the current
DurableContext from within a Highway task, without requiring
ctx as a function parameter.

Usage:
    from highway_context import get_context

    def my_existing_function(order_id):
        # Existing code - no ctx parameter needed
        ctx = get_context()
        ctx.set_variable("processed", True)
        return {"order_id": order_id}
"""

import threading

_thread_local = threading.local()


def get_context():
    """Get current DurableContext from within a Highway task.

    Returns:
        DurableContext: The current execution context

    Raises:
        RuntimeError: If called outside a Highway task execution
    """
    ctx = getattr(_thread_local, 'ctx', None)
    if ctx is None:
        raise RuntimeError(
            "get_context() called outside Highway task execution. "
            "This function can only be used within a durable task."
        )
    return ctx


def _set_context(ctx):
    """Set the thread-local context (called by wrapper)."""
    _thread_local.ctx = ctx


def _clear_context():
    """Clear the thread-local context (called by wrapper)."""
    _thread_local.ctx = None
'''

def _strip_decorators(source: str, func_name: str) -> str:
    """Strip @driver decorators from function source.

    Uses AST to safely remove decorator lines while preserving
    the original function signature unchanged.

    NOTE: We do NOT inject ctx here. The wrapper function handles ctx.
    This allows existing packages to work without modification.

    Args:
        source: Original function source code
        func_name: Name of the function (for error messages)

    Returns:
        Cleaned source code without decorators (signature unchanged)
    """
    # Dedent source to handle indented functions
    source = textwrap.dedent(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError("Cannot parse source for '%s': %s" % (func_name, e))

    if not tree.body:
        raise ValueError("Empty source for function '%s'" % func_name)

    node = tree.body[0]

    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError("Expected function definition for '%s'" % func_name)

    # Remove all decorators - signature stays unchanged
    node.decorator_list = []

    # Generate clean source
    return ast.unparse(node)

@dataclass
class PackagedArtifact:
    """Result of packaging Python code into a ZIP artifact."""
    file_path: str
    content_hash: str
    package_name: str
    entrypoint: str
