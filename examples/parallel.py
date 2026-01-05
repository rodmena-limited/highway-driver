#!/usr/bin/env python3
"""Parallel task execution example.

Tasks without dependencies can run in parallel on Highway.
The final task waits for all parallel tasks to complete.

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/parallel.py
"""

from highway import Driver


def main() -> None:
    driver = Driver()

    # These three tasks have no dependencies - they run in parallel
    @driver.task(shell=True)
    def task_a():
        return "echo 'Task A' && sleep 1"

    @driver.task(shell=True)
    def task_b():
        return "echo 'Task B' && sleep 1"

    @driver.task(shell=True)
    def task_c():
        return "echo 'Task C' && sleep 1"

    # This task waits for all parallel tasks
    @driver.task(shell=True, depends=["task_a", "task_b", "task_c"])
    def final_task():
        return "echo 'All parallel tasks completed!'"

    print("Workflow structure:")
    print("  task_a ──┐")
    print("  task_b ──┼── final_task")
    print("  task_c ──┘")
    print()
    print("Submitting to Highway via Stabilize (parallel execution)...")

    result = driver.run(wait=True, timeout=120)

    print()
    print(f"Result: {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Stabilize ID: {result.stabilize_execution_id}")


if __name__ == "__main__":
    main()
