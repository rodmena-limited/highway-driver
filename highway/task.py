from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

class TaskType(Enum):
    """Type of task execution."""
    SHELL = 'shell'
    PYTHON = 'python'
    HTTP = 'http'
    TOOL = 'tool'
    WORKFLOW = 'workflow'
    FOREACH = 'foreach'
    WHILE = 'while'
    EMIT = 'emit'
    WAIT_FOR = 'wait_for'
