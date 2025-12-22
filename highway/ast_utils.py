from __future__ import annotations
import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
_analyzer = FunctionAnalyzer()

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
    file_path: str = ''
    local_variables: list[str] = field(default_factory=list)
