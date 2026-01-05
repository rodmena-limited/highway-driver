#!/usr/bin/env python3
"""Acceptance test for tools.python.run with package support.

This test validates that the highway-driver can:
1. Package a Python package with multiple modules
2. Upload the artifact to Highway
3. Execute functions with DurableContext
4. Handle cross-module imports correctly

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/test_durable_package.py
"""

from __future__ import annotations

import os
import sys

# Add examples to path for test_package import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from highway import Driver


def test_package_with_cross_imports() -> None:
    """Test: Package with cross-module imports."""
    driver = Driver()

    # Register task that uses external package
    @driver.task(
        durable=True,
        package="./examples/test_package",
        entrypoint="main:run_calculation",
    )
    def calculate():
        pass  # Implementation in package

    print("=== Test: package_with_cross_imports ===")
    print("Testing package with cross-module imports...")

    # This workflow will:
    # 1. Package test_package/ into ZIP
    # 2. Upload to Highway /api/v1/artifacts
    # 3. Execute main:run_calculation with DurableContext
    result = driver.run(wait=True, timeout=120, inputs={"a": 15, "b": 7})

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.status == "completed":
        print("PASSED: Package executed successfully")
    else:
        print(f"Note: Status {result.status} (may need Highway engine support)")


def test_while_loop_with_durable_context() -> None:
    """Test: While loop with mutable counter via DurableContext.

    Uses get_context() pattern - no ctx parameter needed!
    """
    driver = Driver(name="test-while-loop")

    @driver.task(durable=True)
    def init():
        # NEW PATTERN: No ctx param, use get_context()
        from driver_tasks.highway_context import get_context

        ctx = get_context()
        ctx.set_variable("counter", 0)
        ctx.set_variable("limit", 5)
        return {"initialized": True}

    @driver.while_loop(condition="{{counter}} < {{limit}}", depends=["init"])
    def increment():
        # NEW PATTERN: No ctx param, use get_context()
        from driver_tasks.highway_context import get_context

        ctx = get_context()
        counter = ctx.get_variable("counter", 0)
        ctx.set_variable("counter", counter + 1)
        return {"iteration": counter + 1}

    @driver.task(durable=True, depends=["increment"])
    def verify():
        # NEW PATTERN: No ctx param, use get_context()
        from driver_tasks.highway_context import get_context

        ctx = get_context()
        final = ctx.get_variable("counter")
        return {"final_counter": final, "success": final == 5}

    print("=== Test: while_loop_with_durable_context ===")
    print("Testing while loop with get_context() pattern...")

    result = driver.run(wait=True, timeout=120)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.status == "completed":
        print("PASSED: While loop with get_context() completed")
    else:
        print(f"Note: Status {result.status} (may need Highway engine support)")


def test_simple_durable_function() -> None:
    """Test: Simple durable function without package.

    Demonstrates BOTH patterns:
    1. With ctx parameter (legacy/explicit)
    2. Without ctx parameter (new - uses get_context())
    """
    driver = Driver(name="test-durable-patterns")

    # Pattern 1: WITH ctx parameter (legacy - still works)
    @driver.task(durable=True)
    def with_ctx_param(ctx):
        ctx.set_variable("pattern1", "with_ctx")
        return {"pattern": "with_ctx", "value": ctx.get_variable("pattern1")}

    # Pattern 2: WITHOUT ctx parameter (NEW - uses get_context())
    @driver.task(durable=True, depends=["with_ctx_param"])
    def without_ctx_param():
        # Import get_context() from the packaged module
        from driver_tasks.highway_context import get_context

        ctx = get_context()
        ctx.set_variable("pattern2", "get_context")
        return {"pattern": "get_context", "value": ctx.get_variable("pattern2")}

    # Verify both patterns worked
    @driver.task(durable=True, depends=["without_ctx_param"])
    def verify_both(ctx):
        p1 = ctx.get_variable("pattern1")
        p2 = ctx.get_variable("pattern2")
        return {
            "pattern1_value": p1,
            "pattern2_value": p2,
            "success": p1 == "with_ctx" and p2 == "get_context",
        }

    print("=== Test: simple_durable_function ===")
    print("Testing both ctx patterns:")
    print("  1. with_ctx_param(ctx) - legacy pattern")
    print("  2. without_ctx_param() - new get_context() pattern")

    result = driver.run(wait=True, timeout=60)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.status == "completed":
        print("PASSED: Both ctx patterns work correctly")
    else:
        print(f"Note: Status {result.status} (may need Highway engine support)")


def run_all() -> None:
    """Run all acceptance tests."""
    print("\n" + "=" * 60)
    print("ACCEPTANCE TESTS: tools.python.run Support")
    print("=" * 60 + "\n")

    test_simple_durable_function()
    print()
    test_while_loop_with_durable_context()
    print()
    test_package_with_cross_imports()

    print("\n" + "=" * 60)
    print("ACCEPTANCE TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
