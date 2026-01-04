"""Workflow builder that translates Driver tasks to highway_dsl.

This module bridges the gap between highway-driver's decorator API
and the highway_dsl library's WorkflowBuilder fluent API.
"""

from __future__ import annotations

import inspect
import textwrap
from datetime import timedelta
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
            raise WorkflowBuildError(
                f"Unsupported task type: {task_def.task_type.value}"
            )

        handler(task_def)
        self._added_tasks.add(task_def.name)

    def build(self) -> dict[str, Any]:
        """Build and return workflow as dict.

        Returns:
            Workflow definition as JSON-serializable dict
        """
        workflow = self._builder.build()
        return workflow.model_dump(mode="json")

    def build_workflow(self) -> "Workflow":
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
        """Add inline Python task using tools.python.run."""
        # Extract function source and generate script
        script = self._generate_python_script(task_def)

        self._builder.task(
            task_def.name,
            "tools.python.run",
            kwargs={"script": script},
            dependencies=task_def.depends or [],
            result_key=task_def.get_result_key(),
        )
        self._apply_policies(task_def)

    def _add_durable_python(self, task_def: TaskDefinition) -> None:
        """Add durable Python task with package artifact."""
        kwargs: dict[str, Any] = {}

        if task_def.package and task_def.entrypoint:
            # Package mode: upload package and call entrypoint
            kwargs["package"] = task_def.package
            kwargs["entrypoint"] = task_def.entrypoint
            if task_def.func_args:
                kwargs["args"] = task_def.func_args
            if task_def.func_kwargs:
                kwargs["kwargs"] = task_def.func_kwargs
        else:
            # Script mode: serialize function as script
            script = self._generate_python_script(task_def)
            kwargs["script"] = script

        self._builder.activity(
            task_def.name,
            "tools.python.run",
            kwargs=kwargs,
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
            raise WorkflowBuildError(
                f"Task '{task_def.name}' is type TOOL but has no tool_name"
            )

        # Get tool args/kwargs from function
        result = task_def.func()
        args = []
        kwargs = {}

        if isinstance(result, dict):
            kwargs = result
        elif isinstance(result, (list, tuple)):
            args = list(result)
        else:
            args = [result]

        self._builder.task(
            task_def.name,
            task_def.tool_name,
            args=args if args else None,
            kwargs=kwargs if kwargs else None,
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
            raise WorkflowBuildError(
                f"ForEach task '{task_def.name}' requires items parameter"
            )

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
            raise WorkflowBuildError(
                f"While task '{task_def.name}' requires condition parameter"
            )

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
            raise WorkflowBuildError(
                f"Emit task '{task_def.name}' requires event_name parameter"
            )

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

    def _generate_python_script(self, task_def: TaskDefinition) -> str:
        """Generate Python script from function.

        Args:
            task_def: Task definition with function

        Returns:
            Python script string that can be executed by tools.python.run
        """
        func = task_def.func

        # Get function source
        try:
            source = inspect.getsource(func)
            # Dedent to handle decorated functions
            source = textwrap.dedent(source)
        except (OSError, TypeError):
            # Can't get source, function might be a lambda or built-in
            raise WorkflowBuildError(
                f"Cannot extract source for function '{task_def.name}'. "
                "Ensure the function is defined in a regular Python file."
            )

        # Remove decorator lines (lines starting with @)
        lines = source.split("\n")
        non_decorator_lines = []
        in_function = False
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("def "):
                in_function = True
            if in_function:
                non_decorator_lines.append(line)
            elif not stripped.startswith("@"):
                non_decorator_lines.append(line)

        source = "\n".join(non_decorator_lines)

        # Generate wrapper that calls function and sets RESULT
        script = f'''{source}

# Execute and capture result
RESULT = {func.__name__}()
'''
        return script
