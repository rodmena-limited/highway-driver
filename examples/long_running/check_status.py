#!/usr/bin/env python3
"""Check status of a running workflow.

This example demonstrates using retrieve_workflow() to get a WorkflowHandle
for an existing workflow:
1. Retrieve a workflow by run_id
2. Check status via handle.status property
3. Wait for completion via handle.result or handle.wait()

Usage:
    python examples/long_running/check_status.py <run_id>
    python examples/long_running/check_status.py <run_id> --wait  # Wait until complete
"""

import argparse
import time

from highway import Driver


def main():
    parser = argparse.ArgumentParser(description="Check workflow status")
    parser.add_argument("run_id", help="Highway workflow run ID")
    parser.add_argument(
        "--wait", action="store_true", help="Wait until workflow completes"
    )
    parser.add_argument(
        "--timeout", type=float, default=300.0, help="Max wait time in seconds"
    )
    args = parser.parse_args()

    driver = Driver()

    # Use retrieve_workflow() to get a handle for an existing workflow
    handle = driver.retrieve_workflow(args.run_id, timeout=args.timeout)

    print("Run ID: %s" % handle.run_id)

    if args.wait:
        print("Waiting for completion (timeout: %.0fs)..." % args.timeout)
        print()

        # Use handle.result to block until complete
        result = handle.result

        print("=" * 60)
        print("FINAL STATUS: %s" % result.state.value)
        print("=" * 60)

        if result.tasks:
            for task_name, task_result in result.tasks.items():
                print()
                print("Task: %s" % task_name)
                if task_result.result:
                    stdout = task_result.result.get("stdout", "")
                    if stdout:
                        print("  Output: %s" % stdout.strip()[:200])
                if task_result.error:
                    print("  Error: %s" % task_result.error)
    else:
        # Just check current status
        status = handle.status
        print("Status: %s" % status.status)
        print("State: %s" % status.state.value)

        if status.tasks:
            print()
            print("Tasks:")
            for task_name, task_result in status.tasks.items():
                print("  - %s: %s" % (task_name, task_result.state.value if task_result.state else "pending"))


if __name__ == "__main__":
    main()
