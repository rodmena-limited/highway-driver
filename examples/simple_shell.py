#!/usr/bin/env python3
"""Simple shell task example.

Demonstrates the basic usage of Highway Driver with shell tasks.

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/simple_shell.py
"""

from highway import Driver


def main() -> None:
    driver = Driver()

    @driver.task(shell=True)
    def echo_hello():
        return "echo 'Hello from Highway Driver SDK!'"

    print("Submitting to Highway via Stabilize...")
    print("Endpoint: %s" % driver.endpoint)

    result = driver.run(wait=True, timeout=60)

    print()
    print("Result:")
    print("  Status: %s" % result.status)
    print("  Run ID: %s" % result.run_id)
    print("  Stabilize ID: %s" % result.stabilize_execution_id)

    # Get task output from highway_result
    for task_name, task_result in result.tasks.items():
        if task_result.result:
            stdout = task_result.result.get("stdout", "")
            if stdout:
                print("  Output: %s" % stdout.strip())


if __name__ == "__main__":
    main()
