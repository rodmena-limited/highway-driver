#!/usr/bin/env python3
"""Example: Testing dangerous operations in Highway sandbox.

This tests what dangerous OS-level operations are blocked/allowed
in Highway's execution environment. FOR SECURITY TESTING ONLY.

Usage:
    python examples/dangerous_ops.py
"""

from highway import Driver

driver = Driver()


@driver.task(py=True)
def attempt_dangerous_ops():
    """Attempt various dangerous operations to test sandbox restrictions."""
    import os
    import shutil

    results = {
        "tests_performed": [],
        "blocked": [],
        "allowed": [],
    }

    # Test 1: Try to remove 'tests' directory
    try:
        if os.path.exists("tests"):
            shutil.rmtree("tests")
            results["allowed"].append("rmtree tests - DELETED!")
        else:
            results["tests_performed"].append("tests dir not found")
    except Exception as e:
        results["blocked"].append(f"rmtree tests: {type(e).__name__}: {e}")

    # Test 2: Try to remove a file in engine directory
    try:
        if os.path.exists("engine/__init__.py"):
            os.remove("engine/__init__.py")
            results["allowed"].append("remove engine/__init__.py - DELETED!")
        else:
            results["tests_performed"].append("engine/__init__.py not found")
    except Exception as e:
        results["blocked"].append(f"remove engine/__init__.py: {type(e).__name__}: {e}")

    # Test 3: Try to write to /etc
    try:
        with open("/etc/test_highway", "w") as f:
            f.write("test")
        os.remove("/etc/test_highway")
        results["allowed"].append("write to /etc - ALLOWED!")
    except Exception as e:
        results["blocked"].append(f"write /etc: {type(e).__name__}: {e}")

    # Test 4: Try to read /etc/shadow (password hashes)
    try:
        with open("/etc/shadow") as f:
            content = f.read(100)
        results["allowed"].append(f"read /etc/shadow - GOT: {content[:50]}...")
    except Exception as e:
        results["blocked"].append(f"read /etc/shadow: {type(e).__name__}: {e}")

    # Test 5: Try to execute shell command
    try:
        import subprocess

        result = subprocess.run(["whoami"], capture_output=True, text=True)
        results["allowed"].append(f"subprocess whoami: {result.stdout.strip()}")
    except Exception as e:
        results["blocked"].append(f"subprocess: {type(e).__name__}: {e}")

    # Test 6: Try to access network
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("8.8.8.8", 53))
        s.close()
        results["allowed"].append("network access to 8.8.8.8:53 - CONNECTED!")
    except Exception as e:
        results["blocked"].append(f"network: {type(e).__name__}: {e}")

    # Test 7: Try to list /root
    try:
        contents = os.listdir("/root")
        results["allowed"].append(f"list /root: {contents[:5]}")
    except Exception as e:
        results["blocked"].append(f"list /root: {type(e).__name__}: {e}")

    # Summary
    results["summary"] = {
        "total_blocked": len(results["blocked"]),
        "total_allowed": len(results["allowed"]),
        "security_level": "WEAK"
        if len(results["allowed"]) > 2
        else "MODERATE"
        if results["allowed"]
        else "STRONG",
    }

    return results


if __name__ == "__main__":
    print("Testing dangerous operations in Highway sandbox...")
    print("WARNING: This may modify files if sandbox is not properly configured!\n")

    result = driver.run(wait=True, timeout=60)

    print(f"Workflow Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.error:
        print(f"Error: {result.error}")

    # Extract and display results
    if result.tasks:
        for task_name, task_result in result.tasks.items():
            if task_result.result and "stdout" in task_result.result:
                stdout = task_result.result["stdout"]
                if "__HIGHWAY_RESULT__:" in stdout:
                    import json

                    json_str = stdout.split("__HIGHWAY_RESULT__:")[1].strip()
                    report = json.loads(json_str)

                    print("\n--- SECURITY TEST RESULTS ---")
                    print(f"\nBLOCKED ({len(report['blocked'])}):")
                    for item in report["blocked"]:
                        print(f"  ✓ {item}")

                    print(f"\nALLOWED ({len(report['allowed'])}):")
                    for item in report["allowed"]:
                        print(f"  ✗ {item}")

                    print(f"\nSUMMARY: {report['summary']}")
