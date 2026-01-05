#!/usr/bin/env python3
"""HTTP task example.

Demonstrates making HTTP requests via Highway.

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/http_tasks.py
"""

from highway import Driver


def main() -> None:
    driver = Driver()

    @driver.task(http=True)
    def fetch_api():
        """Make a GET request to httpbin."""
        return {
            "url": "https://httpbin.org/get",
            "method": "GET",
            "timeout": 30,
        }

    @driver.task(http=True)
    def post_data():
        """Make a POST request with JSON body."""
        return {
            "url": "https://httpbin.org/post",
            "method": "POST",
            "json": {"message": "Hello from Highway!"},
            "timeout": 30,
        }

    print("Submitting to Highway via Stabilize...")

    result = driver.run(wait=True, timeout=120)

    print()
    print(f"Result: {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Stabilize ID: {result.stabilize_execution_id}")


if __name__ == "__main__":
    main()
