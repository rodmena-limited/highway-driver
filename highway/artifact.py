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

@dataclass
class PackagedArtifact:
    """Result of packaging Python code into a ZIP artifact."""
    file_path: str
    content_hash: str
    package_name: str
    entrypoint: str
