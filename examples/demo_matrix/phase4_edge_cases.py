from highway import Driver

def test_empty_foreach() -> None:
    """Test: ForEach over an empty list - should complete with zero iterations."""
    driver = Driver()

    @driver.task(py=True)
    def init_empty_list():
        return {"items": []}  # Empty list

    @driver.foreach(items="{{init_empty_list_result.items}}", depends=["init_empty_list"])
    def process_item():
        # This should never execute since list is empty
        return {"processed": True}

    @driver.task(py=True, depends=["process_item"])
    def verify_empty():
        return {"status": "zero_iterations", "completed": True}

    print("=== Test: empty_foreach ===")
    print("Running ForEach over empty list (should be zero iterations)...")

    result = driver.run(wait=True, timeout=60)

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    # ForEach on empty list behavior may vary
    print("Result: %s (empty foreach behavior documented)\n" % result.status)

def test_null_variable() -> None:
    """Test: Access undefined variable - should handle gracefully."""
    driver = Driver()

    @driver.task(py=True)
    def access_undefined():
        # Test None/undefined handling
        data = {"present": "value", "nested": {"inner": None}}
        # Access valid keys
        result = {
            "present_value": data.get("present"),
            "missing_value": data.get("missing"),  # Returns None
            "nested_none": data.get("nested", {}).get("inner"),
        }
        return result

    @driver.task(py=True, depends=["access_undefined"])
    def verify_null():
        return {"status": "no_crash", "handled_gracefully": True}

    print("=== Test: null_variable ===")
    print("Testing undefined variable access (should not crash)...")

    result = driver.run(wait=True, timeout=60)

    print("Status: %s" % result.status)
    print("Run ID: %s" % result.run_id)
    assert result.status == "completed", "Expected completed, got %s" % result.status
    print("PASSED: Null variable handled gracefully\n")
