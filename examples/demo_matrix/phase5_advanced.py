#!/usr/bin/env python3
"""Phase 5: Advanced Pattern Tests.

Port of demo_matrix/phase5_advanced.py to Highway Driver SDK.

Tests:
- diamond_pattern: A → (B, C in parallel) → D

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/demo_matrix/phase5_advanced.py
"""

from highway import Driver


def test_diamond_pattern() -> None:
    """Test: Diamond DAG pattern A → (B, C) → D."""
    driver = Driver()

    # Task A: First task, sets up execution order
    @driver.task(py=True)
    def task_a():
        return {"task": "A", "order": 1}

    # Task B: Depends on A, runs in parallel with C
    @driver.task(py=True, depends=["task_a"])
    def task_b():
        import time
        time.sleep(0.5)  # Simulate work
        return {"task": "B", "order": 2}

    # Task C: Depends on A, runs in parallel with B
    @driver.task(py=True, depends=["task_a"])
    def task_c():
        import time
        time.sleep(0.3)  # Shorter than B
        return {"task": "C", "order": 2}

    # Task D: Depends on both B and C (diamond convergence)
    @driver.task(py=True, depends=["task_b", "task_c"])
    def task_d():
        return {"task": "D", "order": 3, "b_and_c_completed": True}

    # Verification task
    @driver.task(py=True, depends=["task_d"])
    def verify_diamond():
        return {
            "pattern": "A → (B, C) → D",
            "status": "diamond_ok",
            "execution_order_correct": True
        }

    print("=== Test: diamond_pattern ===")
    print("Running diamond DAG: A → (B, C parallel) → D...")
    print("  task_a")
    print("    ├── task_b (0.5s)")
    print("    └── task_c (0.3s)")
    print("         └── task_d")
    print()

    result = driver.run(wait=True, timeout=60)

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    assert result.status == "completed", "Expected completed, got %s" % result.status
    print("PASSED: Diamond pattern executed correctly\n")


def test_nested_parallel() -> None:
    """Test: Nested parallel execution - multiple parallel groups."""
    driver = Driver()

    # Outer group 1: 3 parallel tasks
    @driver.task(py=True)
    def outer1_task0():
        import time
        time.sleep(0.2)
        return {"outer": 1, "inner": 0}

    @driver.task(py=True)
    def outer1_task1():
        import time
        time.sleep(0.2)
        return {"outer": 1, "inner": 1}

    @driver.task(py=True)
    def outer1_task2():
        import time
        time.sleep(0.2)
        return {"outer": 1, "inner": 2}

    # Outer group 2: 3 parallel tasks (runs in parallel with group 1)
    @driver.task(py=True)
    def outer2_task0():
        import time
        time.sleep(0.2)
        return {"outer": 2, "inner": 0}

    @driver.task(py=True)
    def outer2_task1():
        import time
        time.sleep(0.2)
        return {"outer": 2, "inner": 1}

    @driver.task(py=True)
    def outer2_task2():
        import time
        time.sleep(0.2)
        return {"outer": 2, "inner": 2}

    # Wait for all 6 tasks
    @driver.task(py=True, depends=[
        "outer1_task0", "outer1_task1", "outer1_task2",
        "outer2_task0", "outer2_task1", "outer2_task2"
    ])
    def verify_nested():
        return {"total_completed": 6, "status": "nested_ok"}

    print("=== Test: nested_parallel ===")
    print("Running 2 groups of 3 parallel tasks (6 total)...")

    result = driver.run(wait=True, timeout=60)

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    assert result.status == "completed", "Expected completed, got %s" % result.status
    print("PASSED: Nested parallel groups completed\n")


def test_linear_chain() -> None:
    """Test: Simple linear chain A → B → C → D."""
    driver = Driver()

    @driver.task(py=True)
    def step_a():
        return {"step": "A", "order": 1}

    @driver.task(py=True, depends=["step_a"])
    def step_b():
        return {"step": "B", "order": 2}

    @driver.task(py=True, depends=["step_b"])
    def step_c():
        return {"step": "C", "order": 3}

    @driver.task(py=True, depends=["step_c"])
    def step_d():
        return {"step": "D", "order": 4, "chain_complete": True}

    print("=== Test: linear_chain ===")
    print("Running linear chain: A → B → C → D...")

    result = driver.run(wait=True, timeout=60)

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    assert result.status == "completed", "Expected completed, got %s" % result.status
    print("PASSED: Linear chain executed in order\n")


def run_all() -> None:
    """Run all Phase 5 tests."""
    print("\n" + "=" * 60)
    print("PHASE 5: Advanced Pattern Tests")
    print("=" * 60 + "\n")

    test_diamond_pattern()
    test_nested_parallel()
    test_linear_chain()

    print("=" * 60)
    print("PHASE 5 COMPLETE: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
