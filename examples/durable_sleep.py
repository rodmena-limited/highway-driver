#!/usr/bin/env python3
"""Example: Durable Sleep

Demonstrates how time.sleep() automatically becomes durable in @task(durable=True).
No special imports or syntax needed - just write natural Python!

When a durable task uses time.sleep(), the driver automatically:
1. Transforms time.sleep() to _durable_sleep() via AST
2. The _durable_sleep() records start time in workflow state
3. If the process restarts, it resumes from where it left off

Run:
    python examples/durable_sleep.py
"""

import time

from highway import Driver

driver = Driver()


@driver.task(durable=True, timeout=120)
def step_1():
    """First step: sleep for 30 seconds."""
    print("Step 1: Starting sleep at", time.strftime("%H:%M:%S"))
    time.sleep(30)  # This automatically becomes durable!
    print("Step 1: Woke up at", time.strftime("%H:%M:%S"))
    return {"step": 1, "done": True}


@driver.task(durable=True, depends=["step_1"], timeout=120)
def step_2():
    """Second step: sleep for 20 seconds."""
    print("Step 2: Starting sleep at", time.strftime("%H:%M:%S"))
    time.sleep(20)  # Also durable!
    print("Step 2: Woke up at", time.strftime("%H:%M:%S"))
    return {"step": 2, "done": True}


@driver.task(durable=True, depends=["step_2"], timeout=120)
def step_3():
    """Final step with multiple sleeps."""
    print("Step 3: Multiple short sleeps")

    # Each sleep gets a unique step name automatically
    time.sleep(5)
    print("  - First sleep done")

    time.sleep(5)
    print("  - Second sleep done")

    time.sleep(5)
    print("  - Third sleep done")

    return {"step": 3, "done": True, "total_sleep": 15}


def main():
    print("=" * 60)
    print("Durable Sleep Example")
    print("=" * 60)
    print()
    print("This example demonstrates automatic durable sleep transformation.")
    print("The workflow has 3 steps with total ~65 seconds of sleep time.")
    print()
    print("Key points:")
    print("  - Developer writes: time.sleep(30)")
    print("  - Automatically becomes: _durable_sleep(30, step_name=...)")
    print("  - If process restarts during sleep, it resumes correctly")
    print()

    # Show the workflow structure
    print("Workflow structure:")
    print("  step_1 (30s sleep) -> step_2 (20s sleep) -> step_3 (3x5s sleeps)")
    print()

    # Submit and wait
    print("Submitting workflow...")
    handle = driver.start_workflow(timeout=180)

    print(f"Run ID: {handle.run_id}")
    print("Waiting for completion...")
    print()

    result = handle.result

    print("=" * 60)
    print(f"RESULT: {result.state.value}")
    print("=" * 60)

    if result.tasks:
        for name, task_result in result.tasks.items():
            print(f"\n{name}:")
            if task_result.result:
                print(f"  Result: {task_result.result}")


if __name__ == "__main__":
    main()
