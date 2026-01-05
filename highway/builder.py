"""Workflow builder that translates Driver tasks to highway_dsl.

This module bridges the gap between highway-driver's decorator API
and the highway_dsl library's WorkflowBuilder fluent API.
"""

from __future__ import annotations

import inspect
import textwrap
from typing import TYPE_CHECKING, Any

from highway_dsl import Duration, WorkflowBuilder

from highway.exceptions import WorkflowBuildError
from highway.task import TaskDefinition, TaskType

if TYPE_CHECKING:
    from highway_dsl.models import Workflow


class DriverWorkflowBuilder:
    """Builds highway_dsl Workflow from Driver TaskDefinitions.

    This class translates the Driver's decorator-based task definitions
    into highway_dsl WorkflowBuilder API calls.

    Example:
        builder = DriverWorkflowBuilder("my_workflow", "1.0.0")
        for task_def in tasks.values():
            builder.add_task(task_def)
        workflow_json = builder.build()
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        """Initialize the workflow builder.

        Args:
            name: Workflow name
            version: Workflow version string
        """
        self._name = name
        self._version = version
        self._builder = WorkflowBuilder(name, version=version)
        self._added_tasks: set[str] = set()

    def add_task(self, task_def: TaskDefinition) -> None:
        """Add a task to the workflow based on its type.

        Args:
            task_def: Task definition to add

        Raises:
            WorkflowBuildError: If task type is not supported
        """
        handlers = {
            TaskType.SHELL: self._add_shell,
            TaskType.PYTHON: self._add_python,
            TaskType.HTTP: self._add_http,
            TaskType.TOOL: self._add_tool,
            TaskType.WORKFLOW: self._add_workflow,
            TaskType.FOREACH: self._add_foreach,
            TaskType.WHILE: self._add_while,
            TaskType.EMIT: self._add_emit,
            TaskType.WAIT_FOR: self._add_wait_for,
        }

        handler = handlers.get(task_def.task_type)
        if not handler:
            raise WorkflowBuildError(f"Unsupported task type: {task_def.task_type.value}")

        handler(task_def)
        self._added_tasks.add(task_def.name)

    def build(self) -> dict[str, Any]:
        """Build and return workflow as dict.

        Returns:
            Workflow definition as JSON-serializable dict
        """
        workflow = self._builder.build()
        return workflow.model_dump(mode="json")

    def build_workflow(self) -> Workflow:
        """Build and return workflow object.

        Returns:
            highway_dsl Workflow object
        """
        return self._builder.build()

    def _add_shell(self, task_def: TaskDefinition) -> None:
        """Add a shell task."""
        # Get command from function
        command = task_def.func()

        self._builder.task(
            task_def.name,
            "tools.shell.run",
            args=[command],
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )
        self._apply_policies(task_def)

    def _add_python(self, task_def: TaskDefinition) -> None:
        """Add a Python task."""
        if task_def.durable:
            self._add_durable_python(task_def)
        else:
            self._add_inline_python(task_def)

    def _add_inline_python(self, task_def: TaskDefinition) -> None:
        """Add inline Python task using tools.code.exec."""
        # Extract function source and generate code
        code = self._generate_python_code(task_def)

        self._builder.task(
            task_def.name,
            "tools.code.exec",
            kwargs={"code": code},
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )
        self._apply_policies(task_def)

    def _add_durable_python(self, task_def: TaskDefinition) -> None:
        """Add durable Python task with package artifact."""
        if task_def.package and task_def.entrypoint:
            # Package mode: use tools.python.run with fully-qualified function
            kwargs: dict[str, Any] = {
                "package": task_def.package,
                "entrypoint": task_def.entrypoint,
            }
            if task_def.func_args:
                kwargs["args"] = task_def.func_args
            if task_def.func_kwargs:
                kwargs["kwargs"] = task_def.func_kwargs

            self._builder.task(
                task_def.name,
                "tools.python.run",
                kwargs=kwargs,
                dependencies=task_def.depends or [],
                result_key=task_def.get_result_key(),
            )
        else:
            # Script mode: use tools.code.exec for inline code
            code = self._generate_python_code(task_def)
            self._builder.task(
                task_def.name,
                "tools.code.exec",
                kwargs={"code": code},
                dependencies=task_def.depends or [],
                result_key=task_def.get_result_key(),
            )
        self._apply_policies(task_def)

    def _add_http(self, task_def: TaskDefinition) -> None:
        """Add an HTTP task."""
        # Get HTTP config from function
        config = task_def.func()

        kwargs: dict[str, Any] = {"url": config.get("url")}
        if "method" in config:
            kwargs["method"] = config["method"]
        if "headers" in config:
            kwargs["headers"] = config["headers"]
        if "body" in config:
            kwargs["body"] = config["body"]
        if "timeout" in config:
            kwargs["timeout"] = config["timeout"]

        self._builder.task(
            task_def.name,
            "tools.http.request",
            kwargs=kwargs,
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )
        self._apply_policies(task_def)

    def _add_tool(self, task_def: TaskDefinition) -> None:
        """Add a generic Highway tool task."""
        if not task_def.tool_name:
            raise WorkflowBuildError(f"Task '{task_def.name}' is type TOOL but has no tool_name")

        # Get tool args/kwargs from function
        result = task_def.func()
        args: list[Any] = []
        kwargs: dict[str, Any] = {}

        if isinstance(result, dict):
            kwargs = result
        elif isinstance(result, (list, tuple)):
            args = list(result)
        elif result is not None:
            args = [result]

        self._builder.task(
            task_def.name,
            task_def.tool_name,
            args=args,
            kwargs=kwargs,
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )
        self._apply_policies(task_def)

    def _add_workflow(self, task_def: TaskDefinition) -> None:
        """Add a workflow execution task."""
        kwargs: dict[str, Any] = {}

        if task_def.workflow_definition_id:
            kwargs["workflow_definition_id"] = task_def.workflow_definition_id
        elif task_def.workflow_name:
            kwargs["workflow_name"] = task_def.workflow_name
        else:
            raise WorkflowBuildError(
                f"Task '{task_def.name}' is type WORKFLOW but has no "
                "workflow_name or workflow_definition_id"
            )

        # Get workflow inputs from function
        inputs = task_def.func()
        if inputs:
            kwargs["inputs"] = inputs

        self._builder.task(
            task_def.name,
            "workflow.execute",
            kwargs=kwargs,
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )
        self._apply_policies(task_def)

    def _add_foreach(self, task_def: TaskDefinition) -> None:
        """Add a ForEach loop task."""
        if not task_def.items:
            raise WorkflowBuildError(f"ForEach task '{task_def.name}' requires items parameter")

        # Get loop body command from function
        body_command = task_def.func()

        # Create loop body builder function
        def loop_body(b: WorkflowBuilder) -> WorkflowBuilder:
            b.task(
                f"{task_def.name}_body",
                "tools.shell.run",
                args=[body_command],
            )
            return b

        self._builder.foreach(
            task_def.name,
            items=task_def.items,
            loop_body=loop_body,
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )

    def _add_while(self, task_def: TaskDefinition) -> None:
        """Add a While loop task."""
        if not task_def.condition:
            raise WorkflowBuildError(f"While task '{task_def.name}' requires condition parameter")

        # Get loop body command from function
        body_command = task_def.func()

        # Create loop body builder function
        def loop_body(b: WorkflowBuilder) -> WorkflowBuilder:
            b.task(
                f"{task_def.name}_body",
                "tools.shell.run",
                args=[body_command],
            )
            return b

        self._builder.while_loop(
            task_def.name,
            condition=task_def.condition,
            loop_body=loop_body,
            dependencies=task_def.depends or [],
        )

    def _add_emit(self, task_def: TaskDefinition) -> None:
        """Add an emit event task."""
        if not task_def.event_name:
            raise WorkflowBuildError(f"Emit task '{task_def.name}' requires event_name parameter")

        kwargs: dict[str, Any] = {}
        if task_def.event_payload:
            kwargs["metadata"] = task_def.event_payload

        self._builder.emit_event(
            task_def.name,
            event_name=task_def.event_name,
            dependencies=task_def.depends or [],
            **kwargs,
        )

    def _add_wait_for(self, task_def: TaskDefinition) -> None:
        """Add a wait for event task."""
        if not task_def.event_name:
            raise WorkflowBuildError(
                f"WaitFor task '{task_def.name}' requires event_name parameter"
            )

        kwargs: dict[str, Any] = {}
        if task_def.event_timeout:
            kwargs["timeout_seconds"] = task_def.event_timeout

        self._builder.wait_for_event(
            task_def.name,
            event_name=task_def.event_name,
            dependencies=task_def.depends or [],
            **kwargs,
        )

    def _apply_policies(self, task_def: TaskDefinition) -> None:
        """Apply retry, timeout, and delay policies to current task."""
        # Apply retry policy
        if task_def.retries > 0:
            self._builder.retry(
                max_retries=task_def.retries,
                delay=Duration.seconds(task_def.retry_delay),
                backoff_factor=task_def.backoff_rate,
            )

        # Apply timeout policy
        if task_def.timeout:
            self._builder.timeout(
                timeout=Duration.seconds(task_def.timeout),
                kill_on_timeout=True,
            )

        # Apply delay (durable wait before execution)
        if task_def.delay:
            # Insert a wait task before this task
            wait_task_name = f"{task_def.name}_delay"
            self._builder.wait(wait_task_name, task_def.delay)

    def _generate_python_code(self, task_def: TaskDefinition) -> str:
        """Generate Python code from function for tools.code.exec.

        Extracts function body and converts return statements to RESULT assignments.
        Highway's code sandbox doesn't capture function return values, so we need
        to inline the code and use RESULT variable directly.

        Args:
            task_def: Task definition with function

        Returns:
            Python code string that can be executed by tools.code.exec
        """
        import re

        func = task_def.func

        # Get function source
        try:
            source = inspect.getsource(func)
            # Dedent to handle decorated functions
            source = textwrap.dedent(source)
        except (OSError, TypeError):
            raise WorkflowBuildError(
                f"Cannot extract source for function '{task_def.name}'. "
                "Ensure the function is defined in a regular Python file."
            )

        lines = source.split("\n")

        # Find the function definition line and extract body
        body_lines = []
        in_function = False
        in_docstring = False
        docstring_quote = None
        base_indent = None

        for line in lines:
            stripped = line.lstrip()

            # Skip decorators
            if stripped.startswith("@") and not in_function:
                continue

            # Skip function definition line
            if stripped.startswith("def ") and not in_function:
                in_function = True
                continue

            if in_function:
                # Handle docstrings at the start of function
                if in_docstring:
                    if docstring_quote in stripped:
                        in_docstring = False
                    continue

                if not body_lines and (stripped.startswith('"""') or stripped.startswith("'''")):
                    docstring_quote = stripped[:3]
                    if stripped.count(docstring_quote) >= 2:
                        # Single line docstring, skip it
                        continue
                    # Multi-line docstring starts
                    in_docstring = True
                    continue

                # Skip empty lines at the start
                if not body_lines and not stripped:
                    continue

                # Determine base indentation from first real line
                if base_indent is None and stripped:
                    base_indent = len(line) - len(stripped)

                # Dedent the line
                if base_indent and line.startswith(" " * base_indent):
                    line = line[base_indent:]

                body_lines.append(line)

        # Join body
        code = "\n".join(body_lines).rstrip()

        # Replace return statements with result assignment
        # Highway sandbox captures the variable named 'result' (lowercase)
        # Using intermediate variable because direct dict literal assignment doesn't work
        # Handle both "return value" and bare "return"
        code = re.sub(r"^(\s*)return\s+(.+)$", r"\1result = \2", code, flags=re.MULTILINE)
        code = re.sub(r"^(\s*)return\s*$", r"\1result = None", code, flags=re.MULTILINE)

        # Detect and add required imports for standard library modules
        imports = []
        if re.search(r"\btime\.", code):
            imports.append("import time")
        if re.search(r"\bjson\.", code):
            imports.append("import json")
        if re.search(r"\bos\.", code):
            imports.append("import os")
        if re.search(r"\bmath\.", code):
            imports.append("import math")
        if re.search(r"\brandom\.", code):
            imports.append("import random")
        if re.search(r"\bdatetime\.", code):
            imports.append("import datetime")
        if re.search(r"\bre\.", code):
            imports.append("import re")

        if imports:
            code = "\n".join(imports) + "\n\n" + code

        return code
