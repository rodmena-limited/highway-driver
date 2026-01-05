#!/usr/bin/env python3
"""Phase 1: Connection & Timeout Stress Tests.

Port of demo_matrix/phase1_connection.py to Highway Driver SDK.

Tests:
- long_task_95s: Shell sleep 95s - must survive without connection death
- activity_near_timeout: Activity with 50s work, 60s timeout
- pool_stress: Spawn 5 parallel branches to stress connection pool

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/demo_matrix/phase1_connection.py
"""

from highway import Driver


def test_long_task_95s() -> None:
    """Test: 95-second task survives idle-in-transaction timeout."""
    driver = Driver()

    @driver.task(shell=True, timeout=120)
    def long_sleep():
        return "sleep 95 && echo 'survived_95s'"

    @driver.task(py=True, depends=["long_sleep"])
    def verify_completion():
        return {"status": "long_task_completed", "duration": 95}

    print("=== Test: long_task_95s ===")
    print("Running 95s sleep to test idle-in-transaction timeout...")

    result = driver.run(wait=True, timeout=150)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    assert result.status == "completed", f"Expected completed, got {result.status}"
    print("PASSED: Long task survived without connection death\n")


def test_activity_near_timeout() -> None:
    """Test: Activity near its timeout limit completes."""
    driver = Driver()

    @driver.task(shell=True, timeout=60)
    def near_timeout_work():
        return "sleep 50 && echo 'completed_near_timeout'"

    @driver.task(py=True, depends=["near_timeout_work"])
    def verify():
        return {"status": "near_timeout_completed"}

    print("=== Test: activity_near_timeout ===")
    print("Running 50s task with 60s timeout...")

    result = driver.run(wait=True, timeout=90)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    assert result.status == "completed", f"Expected completed, got {result.status}"
    print("PASSED: Activity near timeout completed successfully\n")


def test_pool_stress() -> None:
    """Test: 5 parallel branches without pool exhaustion."""
    driver = Driver()

    # 5 parallel branches (no mutual dependencies = run in parallel)
    @driver.task(py=True)
    def branch_0():
        import time

        time.sleep(0.5)
        return {"branch": 0, "done": True}

    @driver.task(py=True)
    def branch_1():
        import time

        time.sleep(0.5)
        return {"branch": 1, "done": True}

    @driver.task(py=True)
    def branch_2():
        import time

        time.sleep(0.5)
        return {"branch": 2, "done": True}

    @driver.task(py=True)
    def branch_3():
        import time

        time.sleep(0.5)
        return {"branch": 3, "done": True}

    @driver.task(py=True)
    def branch_4():
        import time

        time.sleep(0.5)
        return {"branch": 4, "done": True}

    # Wait for all 5 parallel branches
    @driver.task(py=True, depends=["branch_0", "branch_1", "branch_2", "branch_3", "branch_4"])
    def verify_pool():
        return {"all_branches_complete": True, "completed_branches": 5}

    print("=== Test: pool_stress ===")
    print("Running 5 parallel branches to stress connection pool...")

    result = driver.run(wait=True, timeout=60)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    assert result.status == "completed", f"Expected completed, got {result.status}"
    print("PASSED: 5 parallel branches completed without pool exhaustion\n")


def run_all() -> None:
    """Run all Phase 1 tests."""
    print("\n" + "=" * 60)
    print("PHASE 1: Connection & Timeout Stress Tests")
    print("=" * 60 + "\n")

    test_long_task_95s()
    test_activity_near_timeout()
    test_pool_stress()

    print("=" * 60)
    print("PHASE 1 COMPLETE: All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
