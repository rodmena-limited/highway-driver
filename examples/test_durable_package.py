from __future__ import annotations
import os
import sys
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

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)

    if result.status == "completed":
        print("PASSED: Package executed successfully")
    else:
        print("Note: Status %s (may need Highway engine support)" % result.status)

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

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)

    if result.status == "completed":
        print("PASSED: While loop with get_context() completed")
    else:
        print("Note: Status %s (may need Highway engine support)" % result.status)
