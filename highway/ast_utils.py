"""AST-based function analysis utilities.

This module provides enterprise-grade AST analysis of Python functions
decorated with @driver.task(). No string hacks - pure AST parsing.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FunctionAnalysis:
    """Complete analysis of a decorated function.

    All metadata is extracted using AST parsing only.
    No string manipulation or regex hacks.

    Attributes:
        name: Function name
        source: Full source code
        imports: List of imported modules (top-level only)
        parameters: List of parameter names
        return_annotation: Return type annotation (if present)
        docstring: Function docstring (if present)
        is_async: Whether function is async def
        line_number: Line number in source file
        file_path: Path to source file
        local_variables: Variables assigned in function body
    """

    name: str
    source: str
    imports: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    return_annotation: str | None = None
    docstring: str | None = None
    is_async: bool = False
    line_number: int = 0
    file_path: str = ""
    local_variables: list[str] = field(default_factory=list)


class FunctionAnalyzer:
    """Enterprise-grade AST analysis of Python functions.

    This class extracts all metadata from decorated functions using
    Python's ast module. It handles:
    - Nested functions
    - Decorators
    - Type annotations
    - Import detection within function body
    - Async functions

    Example:
        analyzer = FunctionAnalyzer()

        @driver.task(shell=True)
        def my_task():
            return "echo hello"

        analysis = analyzer.analyze(my_task)
        print(analysis.imports)  # []
        print(analysis.name)     # "my_task"
    """

    def analyze(self, func: Callable[..., Any]) -> FunctionAnalysis:
        """Extract all metadata from function using AST.

        Args:
            func: The function to analyze

        Returns:
            FunctionAnalysis with all extracted metadata

        Raises:
            ValueError: If function source cannot be parsed
        """
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError) as e:
            raise ValueError("Cannot get source for function '%s': %s" % (func.__name__, e))

        # Dedent to handle nested functions or class methods
        source = textwrap.dedent(source)

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            raise ValueError("Cannot parse source for function '%s': %s" % (func.__name__, e))

        func_def = self._find_function_def(tree, func.__name__)
        if func_def is None:
            raise ValueError(
                "Could not find function definition for '%s' in parsed AST" % func.__name__
            )

        try:
            file_path = inspect.getfile(func)
        except (OSError, TypeError):
            file_path = "<unknown>"

        return FunctionAnalysis(
            name=func.__name__,
            source=source,
            imports=self._extract_imports(func_def),
            parameters=self._extract_parameters(func_def),
            return_annotation=self._extract_return_annotation(func_def),
            docstring=ast.get_docstring(func_def),
            is_async=isinstance(func_def, ast.AsyncFunctionDef),
            line_number=func_def.lineno,
            file_path=file_path,
            local_variables=self._extract_local_variables(func_def),
        )

    def _find_function_def(
        self, tree: ast.AST, name: str
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        """Find the function definition in AST.

        Handles decorators by looking at the actual function name,
        not the decorator chain.

        Args:
            tree: Parsed AST tree
            name: Function name to find

        Returns:
            Function definition node or None if not found
        """
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == name:
                    return node
        return None

    def _extract_imports(self, func_def: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Extract import statements from function body.

        Only extracts imports INSIDE the function body, not module-level.
        Returns top-level package names only (e.g., 'os' from 'os.path').

        Args:
            func_def: Function definition node

        Returns:
            List of imported module names (deduplicated)
        """
        imports: set[str] = set()

        for node in ast.walk(func_def):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Get top-level package only
                    top_level = alias.name.split(".")[0]
                    imports.add(top_level)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Get top-level package only
                    top_level = node.module.split(".")[0]
                    imports.add(top_level)

        return sorted(imports)

    def _extract_parameters(self, func_def: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Extract parameter names from function signature.

        Excludes 'self' and 'cls' for methods.

        Args:
            func_def: Function definition node

        Returns:
            List of parameter names
        """
        params = []
        for arg in func_def.args.args:
            if arg.arg not in ("self", "cls"):
                params.append(arg.arg)

        # Also include *args and **kwargs names if present
        if func_def.args.vararg:
            params.append("*%s" % func_def.args.vararg.arg)
        if func_def.args.kwarg:
            params.append("**%s" % func_def.args.kwarg.arg)

        return params

    def _extract_return_annotation(
        self, func_def: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> str | None:
        """Extract return type annotation if present.

        Args:
            func_def: Function definition node

        Returns:
            Return annotation as string, or None if not annotated
        """
        if func_def.returns:
            return ast.unparse(func_def.returns)
        return None

    def _extract_local_variables(
        self, func_def: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[str]:
        """Extract variable names assigned in function body.

        Useful for understanding function structure.

        Args:
            func_def: Function definition node

        Returns:
            List of variable names (deduplicated)
        """
        variables: set[str] = set()

        for node in ast.walk(func_def):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        variables.add(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                variables.add(elt.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    variables.add(node.target.id)

        return sorted(variables)


# Module-level singleton for convenience
_analyzer = FunctionAnalyzer()


def analyze_function(func: Callable[..., Any]) -> FunctionAnalysis:
    """Analyze a function using the module-level analyzer.

    Convenience function for one-off analysis.

    Args:
        func: Function to analyze

    Returns:
        FunctionAnalysis with extracted metadata
    """
    return _analyzer.analyze(func)
