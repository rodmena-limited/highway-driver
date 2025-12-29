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

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    assert result.status == "completed", "Expected completed, got %s" % result.status
    print("PASSED: Long task survived without connection death\n")
