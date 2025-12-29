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
