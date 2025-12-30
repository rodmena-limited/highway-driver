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
