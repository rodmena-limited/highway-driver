#!/usr/bin/env python3
"""Submit long-running workflow and exit immediately.

This example demonstrates:
1. Submitting a workflow that takes ~3 minutes (3 phases x 60 seconds)
2. Driver exits immediately after submission
3. Workflow continues running on Highway
4. Status can be checked later using check_status.py

Run:
    python examples/long_running/submit.py

Then check status:
    python examples/long_running/check_status.py <run_id>
"""

from highway import Driver


def main():
    driver = Driver()

    @driver.task(shell=True, timeout=120)
    def phase_1():
        """First phase: 60 second task."""
        return "echo 'Phase 1 started at $(date)' && sleep 60 && echo 'Phase 1 completed at $(date)'"

    @driver.task(shell=True, depends=["phase_1"], timeout=120)
    def phase_2():
        """Second phase: 60 second task after phase_1."""
        return "echo 'Phase 2 started at $(date)' && sleep 60 && echo 'Phase 2 completed at $(date)'"

    @driver.task(shell=True, depends=["phase_2"], timeout=120)
    def phase_3():
        """Third phase: 60 second task after phase_2."""
        return "echo 'Phase 3 started at $(date)' && sleep 60 && echo 'ALL PHASES COMPLETE at $(date)'"

    print("Submitting long-running workflow (~3 minutes)...")
    print("Workflow structure: phase_1 (60s) -> phase_2 (60s) -> phase_3 (60s)")
    print()

    # Submit with wait=False to return immediately
    result = driver.run(wait=False, timeout=300)

    print("Workflow submitted successfully!")
    print()
    print("Run ID: %s" % result.run_id)
    print("Stabilize ID: %s" % result.stabilize_execution_id)
    print("Status: %s" % result.status)
    print()
    print("Driver is exiting. Workflow continues running on Highway.")
    print()
    print("To check status, run:")
    print("  python examples/long_running/check_status.py %s" % result.run_id)


if __name__ == "__main__":
    main()
