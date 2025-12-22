from __future__ import annotations
import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
_analyzer = FunctionAnalyzer()
