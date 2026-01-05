#!/usr/bin/env python3
"""Unit tests for durable sleep AST transformation.

Tests the automatic transformation of time.sleep() calls to durable sleep
that survives process restarts.
"""

import ast
import time
import zipfile

from highway.artifact import package_functions
from highway.transforms import (
    DurableSleepTransformer,
    get_durable_sleep_helper,
    transform_function_for_durability,
)


class TestDurableSleepTransformer:
    """Test the AST transformer for time.sleep() calls."""

    def test_transforms_time_sleep(self) -> None:
        """time.sleep(X) should become _durable_sleep(X, step_name=...)."""
        code = """
def my_task():
    time.sleep(60)
    return {'done': True}
"""
        tree = ast.parse(code)
        func = tree.body[0]
        transformer = DurableSleepTransformer("my_task")
        new_func = transformer.visit(func)
        ast.fix_missing_locations(new_func)

        result = ast.unparse(new_func)
        assert "_durable_sleep(60" in result
        assert "step_name='sleep_my_task_" in result
        assert transformer.sleep_count == 1

    def test_transforms_bare_sleep(self) -> None:
        """sleep(X) from 'from time import sleep' should be transformed."""
        code = """
def my_task():
    sleep(30)
    return {'done': True}
"""
        tree = ast.parse(code)
        func = tree.body[0]
        transformer = DurableSleepTransformer("my_task")
        new_func = transformer.visit(func)
        ast.fix_missing_locations(new_func)

        result = ast.unparse(new_func)
        assert "_durable_sleep(30" in result
        assert transformer.sleep_count == 1

    def test_transforms_multiple_sleeps(self) -> None:
        """Multiple sleep calls should each get unique step names."""
        code = """
def my_task():
    time.sleep(10)
    time.sleep(20)
    time.sleep(30)
    return {'done': True}
"""
        tree = ast.parse(code)
        func = tree.body[0]
        transformer = DurableSleepTransformer("my_task")
        new_func = transformer.visit(func)

        result = ast.unparse(new_func)
        assert result.count("_durable_sleep") == 3
        assert transformer.sleep_count == 3
        # Each should have unique step name
        assert "_1'" in result
        assert "_2'" in result
        assert "_3'" in result

    def test_preserves_non_sleep_code(self) -> None:
        """Code that doesn't use sleep should pass through unchanged."""
        code = """
def my_task():
    x = 1 + 2
    return {'result': x}
"""
        tree = ast.parse(code)
        func = tree.body[0]
        transformer = DurableSleepTransformer("my_task")
        new_func = transformer.visit(func)

        result = ast.unparse(new_func)
        assert "_durable_sleep" not in result
        assert transformer.sleep_count == 0

    def test_handles_sleep_with_variable(self) -> None:
        """Sleep with variable duration should be preserved."""
        code = """
def my_task(duration):
    time.sleep(duration)
    return {'done': True}
"""
        tree = ast.parse(code)
        func = tree.body[0]
        transformer = DurableSleepTransformer("my_task")
        new_func = transformer.visit(func)

        result = ast.unparse(new_func)
        assert "_durable_sleep(duration" in result


class TestTransformFunctionForDurability:
    """Test the high-level function transformer."""

    def test_transforms_function_source(self) -> None:
        """transform_function_for_durability should process complete function."""

        def sample_task():
            time.sleep(5)
            return {"done": True}

        result = transform_function_for_durability(sample_task)
        assert "_durable_sleep(5" in result
        assert "time.sleep" not in result

    def test_skip_transform_when_disabled(self) -> None:
        """Transformation can be disabled."""

        def sample_task():
            time.sleep(5)
            return {"done": True}

        result = transform_function_for_durability(sample_task, apply_sleep_transform=False)
        # Original time.sleep should be preserved (no transformation)
        assert "_durable_sleep" not in result


class TestDurableSleepHelper:
    """Test the generated helper function."""

    def test_helper_function_content(self) -> None:
        """Helper should contain durability logic using set_variable."""
        helper = get_durable_sleep_helper()

        # Should use variable storage for durability
        assert "get_variable" in helper
        assert "set_variable" in helper
        assert "_sleep_done_" in helper
        assert "_sleep_start_" in helper

    def test_helper_is_valid_python(self) -> None:
        """Helper source should be valid Python."""
        helper = get_durable_sleep_helper()
        # Should parse without error
        ast.parse(helper)


class TestArtifactPackagingWithDurableSleep:
    """Test that durable sleep is properly included in packaged artifacts."""

    def test_artifact_includes_transformed_code(self) -> None:
        """Package should contain transformed function with durable sleep."""

        def task_with_sleep():
            time.sleep(10)
            return {"slept": True}

        artifact = package_functions({"task_with_sleep": task_with_sleep})

        with zipfile.ZipFile(artifact.file_path, "r") as zf:
            tasks_content = zf.read("driver_tasks/tasks.py").decode("utf-8")

        # Should contain transformed sleep
        assert "_durable_sleep(10" in tasks_content
        assert "time.sleep" not in tasks_content.split("def task_with_sleep")[1]

    def test_artifact_includes_helper_function(self) -> None:
        """Package should include _durable_sleep helper function."""

        def task_with_sleep():
            time.sleep(10)
            return {"slept": True}

        artifact = package_functions({"task_with_sleep": task_with_sleep})

        with zipfile.ZipFile(artifact.file_path, "r") as zf:
            tasks_content = zf.read("driver_tasks/tasks.py").decode("utf-8")

        # Should contain helper function
        assert "def _durable_sleep(" in tasks_content
        assert "set_variable" in tasks_content
        assert "get_variable" in tasks_content

    def test_artifact_preserves_docstring(self) -> None:
        """Function docstrings should be preserved after transformation."""

        def task_with_docstring():
            """This task sleeps for a bit."""
            time.sleep(5)
            return {"done": True}

        artifact = package_functions({"task_with_docstring": task_with_docstring})

        with zipfile.ZipFile(artifact.file_path, "r") as zf:
            tasks_content = zf.read("driver_tasks/tasks.py").decode("utf-8")

        assert "This task sleeps for a bit" in tasks_content

    def test_multiple_functions_each_transformed(self) -> None:
        """Multiple functions should each be transformed independently."""

        def task_a():
            time.sleep(10)
            return {"task": "a"}

        def task_b():
            time.sleep(20)
            time.sleep(30)
            return {"task": "b"}

        artifact = package_functions({"task_a": task_a, "task_b": task_b})

        with zipfile.ZipFile(artifact.file_path, "r") as zf:
            tasks_content = zf.read("driver_tasks/tasks.py").decode("utf-8")

        # Each function should have its own transformed sleeps
        assert "_durable_sleep(10" in tasks_content
        assert "_durable_sleep(20" in tasks_content
        assert "_durable_sleep(30" in tasks_content
        # Step names should reference function names
        assert "sleep_task_a_" in tasks_content
        assert "sleep_task_b_" in tasks_content
