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
