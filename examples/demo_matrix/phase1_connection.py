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

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    assert result.status == "completed", "Expected completed, got %s" % result.status
    print("PASSED: Activity near timeout completed successfully\n")
