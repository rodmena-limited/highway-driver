#!/usr/bin/env python3
"""Multi-step workflow with dependencies.

Demonstrates task dependencies where each step runs after its dependency.

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/multi_step.py
"""

from highway import Driver


def main() -> None:
    driver = Driver()

    @driver.task(shell=True)
    def step_1():
        """First step - no dependencies."""
        return "echo 'Step 1: Initializing...'"

    @driver.task(shell=True, depends=["step_1"])
    def step_2():
        """Second step - runs after step_1."""
        return "echo 'Step 2: Processing...'"

    @driver.task(shell=True, depends=["step_2"])
    def step_3():
        """Third step - runs after step_2."""
        return "echo 'Step 3: Finalizing...'"

    print("Workflow structure:")
    print("  step_1 -> step_2 -> step_3")
    print()
    print("Submitting to Highway via Stabilize...")

    result = driver.run(wait=True, timeout=120)

    print()
    print(f"Result: {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Stabilize ID: {result.stabilize_execution_id}")


if __name__ == "__main__":
    main()
