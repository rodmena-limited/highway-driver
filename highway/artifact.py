"""Artifact packaging for tools.python.run support.

This module packages Python functions and packages into ZIP artifacts
for upload to Highway's artifact storage.

Two packaging modes:
1. package_directory() - Full Python packages with subdirectories
2. package_functions() - Simple decorated functions (auto-packaged)

Context Handling:
- Engine always calls func(ctx, *args, **kwargs)
- We generate wrapper functions that detect if original wants ctx
- If original doesn't want ctx, we set thread-local context for get_context() access
- This allows existing packages to work WITHOUT modification
"""

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

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PackagedArtifact:
    """Result of packaging Python code into a ZIP artifact."""

    file_path: str  # Path to ZIP file (mktemp)
    content_hash: str  # SHA256 for caching/dedup
    package_name: str  # Root package name (e.g., "driver_tasks")
    entrypoint: str  # Module:function (e.g., "main:run_calculation")


def package_directory(
    source_dir: str,
    entrypoint: str,
    package_name: str | None = None,
) -> PackagedArtifact:
    """Package entire Python package directory into ZIP artifact.

    Args:
        source_dir: Path to package directory
        entrypoint: Module:function path (e.g., "main:run_calculation")
        package_name: Name for root package in ZIP (default: use directory name)

    Returns:
        PackagedArtifact with file path and metadata

    ZIP Structure (for issuedb/):
        issuedb/
        ├── __init__.py
        ├── cli.py
        └── ...

    Package is zipped as-is with no import rewriting.
    """
    source_dir = os.path.abspath(source_dir)

    if not os.path.isdir(source_dir):
        raise ValueError("Source directory does not exist: %s" % source_dir)

    # Use original package name by default (no renaming)
    original_package_name = os.path.basename(source_dir.rstrip("/"))
    if package_name is None:
        package_name = original_package_name

    # Create temp file for ZIP
    fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="driver_tasks_")
    os.close(fd)

    hasher = hashlib.sha256()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Walk source directory and add all .py files
        for root, dirs, files in os.walk(source_dir):
            # Filter out __pycache__ and hidden directories
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__"))]

            for filename in files:
                if not filename.endswith(".py"):
                    continue

                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, source_dir)

                # Create archive path under package_name
                archive_path = os.path.join(package_name, rel_path)

                # Read content
                with open(file_path, "rb") as f:
                    content = f.read()

                # Rewrite imports if package name differs
                if original_package_name != package_name:
                    content = _rewrite_imports(
                        content.decode("utf-8"),
                        original_package_name,
                        package_name,
                    ).encode("utf-8")

                hasher.update(content)
                zf.writestr(archive_path, content)

        # Ensure __init__.py exists at package root
        root_init = os.path.join(package_name, "__init__.py")
        if root_init not in zf.namelist():
            init_content = b'"""Auto-generated package init."""\n'
            zf.writestr(root_init, init_content)
            hasher.update(init_content)

        # Add highway_context.py for get_context() support
        context_path = os.path.join(package_name, "highway_context.py")
        if context_path not in zf.namelist():
            context_content = _get_highway_context_module().encode("utf-8")
            zf.writestr(context_path, context_content)
            hasher.update(context_content)
            logger.debug("Added highway_context.py to package artifact")

    content_hash = hasher.hexdigest()

    return PackagedArtifact(
        file_path=zip_path,
        content_hash=content_hash,
        package_name=package_name,
        entrypoint=entrypoint,
    )


def package_functions(
    functions: dict[str, Callable[..., Any]],
    package_name: str = "driver_tasks",
) -> PackagedArtifact:
    """Package individual functions into ZIP artifact.

    For decorated functions without package= parameter:
    1. Extract function source via inspect.getsource()
    2. Strip @driver decorators via AST
    3. Generate wrapper functions that handle ctx injection
    4. Include highway_context.py for get_context() access
    5. Write to ZIP in mktemp

    Args:
        functions: Dict mapping function name to callable
        package_name: Name for root package in ZIP

    Returns:
        PackagedArtifact with file path and metadata

    ZIP Structure:
        driver_tasks/
        ├── __init__.py
        ├── highway_context.py  # Context helper for get_context()
        └── tasks.py            # Original functions + wrappers
    """
    if not functions:
        raise ValueError("No functions provided for packaging")

    logger.info("Packaging %d functions into artifact", len(functions))

    # Generate tasks.py content with wrappers
    tasks_content = _generate_tasks_module(functions)

    # Get highway_context.py content
    context_content = _get_highway_context_module()

    # Create temp file for ZIP
    fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="driver_tasks_")
    os.close(fd)

    hasher = hashlib.sha256()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add __init__.py
        init_content = '"""Auto-generated package init."""\n'
        init_bytes = init_content.encode("utf-8")
        zf.writestr(os.path.join(package_name, "__init__.py"), init_bytes)
        hasher.update(init_bytes)

        # Add highway_context.py for get_context() access
        context_bytes = context_content.encode("utf-8")
        zf.writestr(os.path.join(package_name, "highway_context.py"), context_bytes)
        hasher.update(context_bytes)
        logger.debug("Added highway_context.py to artifact")

        # Add tasks.py with all functions and wrappers
        tasks_bytes = tasks_content.encode("utf-8")
        zf.writestr(os.path.join(package_name, "tasks.py"), tasks_bytes)
        hasher.update(tasks_bytes)

    content_hash = hasher.hexdigest()

    # Entrypoint uses wrapper function (_hw_<func_name>)
    first_func = next(iter(functions.keys()))

    logger.info("Created artifact: %s (hash=%s)", zip_path, content_hash[:16])

    return PackagedArtifact(
        file_path=zip_path,
        content_hash=content_hash,
        package_name=package_name,
        entrypoint="tasks:_hw_%s" % first_func,  # Wrapper function
    )


def _generate_tasks_module(functions: dict[str, Callable[..., Any]]) -> str:
    """Generate tasks.py module content with original functions and wrappers.

    For each user function, generates:
    1. The original function (decorators stripped, signature unchanged)
    2. A wrapper function (_hw_<name>) that handles ctx injection

    The wrapper:
    - Always accepts ctx as first param (engine requirement)
    - Inspects original function signature at runtime
    - If original wants ctx: passes it through
    - If original doesn't want ctx: sets thread-local context for get_context()

    Args:
        functions: Dict mapping function name to callable

    Returns:
        Python source code for tasks.py module
    """
    lines = [
        '"""Auto-generated tasks module from highway-driver.',
        '',
        'Contains original functions and wrapper functions (_hw_*).',
        'Engine calls wrappers; wrappers handle ctx injection.',
        '"""',
        '',
        'from __future__ import annotations',
        '',
        'import inspect as _inspect',
        'from typing import TYPE_CHECKING, Any',
        '',
        '# Import context helper from same package',
        'from . import highway_context as _hc',
        '',
        'if TYPE_CHECKING:',
        '    from highway_engine.durable_context import DurableContext',
        '',
        '',
    ]

    for func_name, func in functions.items():
        try:
            source = inspect.getsource(func)
            # Strip decorators only - DO NOT inject ctx
            cleaned_source = _strip_decorators(source, func_name)
            lines.append(cleaned_source)
            lines.append('')
            lines.append('')

            # Generate wrapper function
            wrapper_source = _generate_wrapper(func_name)
            lines.append(wrapper_source)
            lines.append('')
            lines.append('')

            logger.debug("Generated wrapper _hw_%s for function %s", func_name, func_name)

        except (OSError, TypeError) as e:
            raise ValueError(
                "Cannot extract source for function '%s': %s" % (func_name, e)
            )

    return '\n'.join(lines)


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


def _rewrite_imports(
    source: str,
    old_package: str,
    new_package: str,
) -> str:
    """Rewrite imports from old_package to new_package.

    Handles:
        from old_package.sub import foo  ->  from new_package.sub import foo
        import old_package.sub           ->  import new_package.sub
        from old_package import sub      ->  from new_package import sub

    Args:
        source: Python source code
        old_package: Original package name (e.g., "test_package")
        new_package: New package name (e.g., "driver_tasks")

    Returns:
        Source code with rewritten imports
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # If we can't parse, fall back to simple string replacement
        return source.replace(old_package + ".", new_package + ".")

    class ImportRewriter(ast.NodeTransformer):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
            if node.module and node.module.startswith(old_package):
                # from old_package.xxx import yyy
                if node.module == old_package:
                    node.module = new_package
                else:
                    # old_package.submodule -> new_package.submodule
                    suffix = node.module[len(old_package):]
                    node.module = new_package + suffix
            return node

        def visit_Import(self, node: ast.Import) -> ast.Import:
            for alias in node.names:
                if alias.name.startswith(old_package):
                    # import old_package.xxx
                    if alias.name == old_package:
                        alias.name = new_package
                    else:
                        suffix = alias.name[len(old_package):]
                        alias.name = new_package + suffix
            return node

    rewriter = ImportRewriter()
    new_tree = rewriter.visit(tree)
    ast.fix_missing_locations(new_tree)

    return ast.unparse(new_tree)


def cleanup_artifact(artifact: PackagedArtifact) -> None:
    """Remove temporary ZIP file.

    Args:
        artifact: PackagedArtifact to clean up
    """
    if artifact.file_path and os.path.exists(artifact.file_path):
        try:
            os.unlink(artifact.file_path)
        except OSError:
            pass  # Ignore cleanup errors
