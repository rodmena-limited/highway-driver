#!/usr/bin/env python3
"""Check status of a running workflow.

This example demonstrates:
1. Checking workflow status using the run_id
2. Getting logs from a running workflow
3. Polling for completion

Usage:
    python examples/long_running/check_status.py <run_id>
    python examples/long_running/check_status.py <run_id> --wait  # Poll until complete
"""

import argparse
import sys
import time

from highway import Driver


def main():
    parser = argparse.ArgumentParser(description="Check workflow status")
    parser.add_argument("run_id", help="Highway workflow run ID")
    parser.add_argument(
        "--wait", action="store_true", help="Poll until workflow completes"
    )
    parser.add_argument(
        "--interval", type=float, default=10.0, help="Poll interval in seconds"
    )
    args = parser.parse_args()

    driver = Driver()

    if args.wait:
        print("Polling for completion (interval: %.1fs)..." % args.interval)
        print()

        while True:
            result = driver.status(args.run_id)
            print("[%s] Status: %s" % (time.strftime("%H:%M:%S"), result.status))

            if result.status in ("completed", "failed", "cancelled"):
                print()
                print("=" * 60)
                print("FINAL STATUS: %s" % result.status)
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
                break

            time.sleep(args.interval)
    else:
        result = driver.status(args.run_id)
        print("Run ID: %s" % args.run_id)
        print("Status: %s" % result.status)
        print("State: %s" % result.state)

        if result.tasks:
            print()
            print("Tasks:")
            for task_name, task_result in result.tasks.items():
                print("  - %s: %s" % (task_name, task_result.state or "pending"))


if __name__ == "__main__":
    main()
