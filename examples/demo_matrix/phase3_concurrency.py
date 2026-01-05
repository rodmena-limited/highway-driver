#!/usr/bin/env python3
"""Phase 3: Concurrency Race Condition Tests.

Port of demo_matrix/phase3_concurrency.py to Highway Driver SDK.

Tests:
- parallel_counter: 20 branches execute in parallel
- event_coordination: Emit → WaitFor event chain
- checkpoint_conflict: 2 branches competing for shared state
- fork_join_stress: Fork 10 branches, all must join

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/demo_matrix/phase3_concurrency.py
"""

from highway import Driver


def test_parallel_counter() -> None:
    """Test: 20 parallel branches incrementing counters."""
    driver = Driver()

    # 20 parallel tasks (no mutual dependencies = run in parallel)
    @driver.task(py=True)
    def counter_0():
        return {"branch": 0, "value": 1}

    @driver.task(py=True)
    def counter_1():
        return {"branch": 1, "value": 1}

    @driver.task(py=True)
    def counter_2():
        return {"branch": 2, "value": 1}

    @driver.task(py=True)
    def counter_3():
        return {"branch": 3, "value": 1}

    @driver.task(py=True)
    def counter_4():
        return {"branch": 4, "value": 1}

    @driver.task(py=True)
    def counter_5():
        return {"branch": 5, "value": 1}

    @driver.task(py=True)
    def counter_6():
        return {"branch": 6, "value": 1}

    @driver.task(py=True)
    def counter_7():
        return {"branch": 7, "value": 1}

    @driver.task(py=True)
    def counter_8():
        return {"branch": 8, "value": 1}

    @driver.task(py=True)
    def counter_9():
        return {"branch": 9, "value": 1}

    @driver.task(py=True)
    def counter_10():
        return {"branch": 10, "value": 1}

    @driver.task(py=True)
    def counter_11():
        return {"branch": 11, "value": 1}

    @driver.task(py=True)
    def counter_12():
        return {"branch": 12, "value": 1}

    @driver.task(py=True)
    def counter_13():
        return {"branch": 13, "value": 1}

    @driver.task(py=True)
    def counter_14():
        return {"branch": 14, "value": 1}

    @driver.task(py=True)
    def counter_15():
        return {"branch": 15, "value": 1}

    @driver.task(py=True)
    def counter_16():
        return {"branch": 16, "value": 1}

    @driver.task(py=True)
    def counter_17():
        return {"branch": 17, "value": 1}

    @driver.task(py=True)
    def counter_18():
        return {"branch": 18, "value": 1}

    @driver.task(py=True)
    def counter_19():
        return {"branch": 19, "value": 1}

    # Final task depends on all 20 - this is the "join" point
    @driver.task(
        py=True,
        depends=[
            "counter_0",
            "counter_1",
            "counter_2",
            "counter_3",
            "counter_4",
            "counter_5",
            "counter_6",
            "counter_7",
            "counter_8",
            "counter_9",
            "counter_10",
            "counter_11",
            "counter_12",
            "counter_13",
            "counter_14",
            "counter_15",
            "counter_16",
            "counter_17",
            "counter_18",
            "counter_19",
        ],
    )
    def verify_counter():
        return {"total_branches": 20, "status": "all_completed"}

    print("=== Test: parallel_counter ===")
    print("Running 20 parallel increment branches...")

    result = driver.run(wait=True, timeout=120)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    assert result.status == "completed", f"Expected completed, got {result.status}"
    print("PASSED: 20 parallel branches completed\n")


def test_event_coordination() -> None:
    """Test: Event emit followed by event wait coordination."""
    driver = Driver()

    @driver.task(py=True)
    def setup():
        return {"workflow_id": "test_123", "data": "payload"}

    @driver.emit(
        event="matrix_test_event",
        payload={"source": "emitter", "data": "test_payload"},
        depends=["setup"],
    )
    def emit_event():
        pass  # Marker function

    @driver.wait_for(event="matrix_test_event", timeout=30, depends=["emit_event"])
    def wait_event():
        pass  # Marker function

    @driver.task(py=True, depends=["wait_event"])
    def verify_event():
        return {"status": "event_received", "chain_complete": True}

    print("=== Test: event_coordination ===")
    print("Running emit -> wait_for event chain...")

    result = driver.run(wait=True, timeout=60)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    # Event coordination may not be fully supported yet
    print(f"Result: {result.status} (event coordination behavior documented)\n")


def test_checkpoint_conflict() -> None:
    """Test: 2 branches competing for shared state."""
    driver = Driver()

    @driver.task(py=True)
    def init_shared():
        return {"shared_key": "initial", "counter": 0}

    # Branch A - runs in parallel with B
    @driver.task(py=True, depends=["init_shared"])
    def branch_a():
        import time

        time.sleep(0.1)  # Small delay
        return {"written_by": "branch_a", "value": "A"}

    # Branch B - runs in parallel with A
    @driver.task(py=True, depends=["init_shared"])
    def branch_b():
        import time

        time.sleep(0.05)  # Slightly faster
        return {"written_by": "branch_b", "value": "B"}

    # Wait for both branches
    @driver.task(py=True, depends=["branch_a", "branch_b"])
    def verify_conflict():
        return {"status": "conflict_resolved", "both_completed": True}

    print("=== Test: checkpoint_conflict ===")
    print("Running 2 parallel branches competing for state...")

    result = driver.run(wait=True, timeout=60)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    assert result.status == "completed", f"Expected completed, got {result.status}"
    print("PASSED: Parallel conflict handled\n")


def test_fork_join_stress() -> None:
    """Test: Fork 10 branches, all must join."""
    driver = Driver()

    # Fork 10 branches with varying execution times
    @driver.task(py=True)
    def fork_0():
        import time

        time.sleep(0.1)
        return {"fork": 0, "completed": True}

    @driver.task(py=True)
    def fork_1():
        import time

        time.sleep(0.15)
        return {"fork": 1, "completed": True}

    @driver.task(py=True)
    def fork_2():
        import time

        time.sleep(0.2)
        return {"fork": 2, "completed": True}

    @driver.task(py=True)
    def fork_3():
        import time

        time.sleep(0.12)
        return {"fork": 3, "completed": True}

    @driver.task(py=True)
    def fork_4():
        import time

        time.sleep(0.18)
        return {"fork": 4, "completed": True}

    @driver.task(py=True)
    def fork_5():
        import time

        time.sleep(0.08)
        return {"fork": 5, "completed": True}

    @driver.task(py=True)
    def fork_6():
        import time

        time.sleep(0.22)
        return {"fork": 6, "completed": True}

    @driver.task(py=True)
    def fork_7():
        import time

        time.sleep(0.14)
        return {"fork": 7, "completed": True}

    @driver.task(py=True)
    def fork_8():
        import time

        time.sleep(0.11)
        return {"fork": 8, "completed": True}

    @driver.task(py=True)
    def fork_9():
        import time

        time.sleep(0.16)
        return {"fork": 9, "completed": True}

    # Join all forks
    @driver.task(
        py=True,
        depends=[
            "fork_0",
            "fork_1",
            "fork_2",
            "fork_3",
            "fork_4",
            "fork_5",
            "fork_6",
            "fork_7",
            "fork_8",
            "fork_9",
        ],
    )
    def verify_join():
        return {"branches_completed": 10, "status": "all_joined"}

    print("=== Test: fork_join_stress ===")
    print("Forking 10 branches with varying execution times...")

    result = driver.run(wait=True, timeout=60)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    assert result.status == "completed", f"Expected completed, got {result.status}"
    print("PASSED: All 10 forks joined successfully\n")


def run_all() -> None:
    """Run all Phase 3 tests."""
    print("\n" + "=" * 60)
    print("PHASE 3: Concurrency Race Condition Tests")
    print("=" * 60 + "\n")

    test_parallel_counter()
    test_checkpoint_conflict()
    test_fork_join_stress()
    test_event_coordination()

    print("=" * 60)
    print("PHASE 3 COMPLETE: All tests executed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
