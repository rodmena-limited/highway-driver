#!/usr/bin/env python3
"""Example: Exploring the Highway sandbox environment.

This tests what OS-level operations are available in Highway's
sandboxed Python execution environment (tools.code.exec).

Usage:
    python examples/os_exploration.py
"""

from highway import Driver

driver = Driver()


@driver.task(py=True)
def explore_environment():
    """Explore what's available in Highway's sandbox."""
    import os
    import platform
    import sys

    report = {
        "os_name": os.name,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": sys.version,
        "current_dir": os.getcwd(),
        "dir_contents": [],
        "env_vars": {},
        "user_info": {},
    }

    # List current directory
    try:
        report["dir_contents"] = os.listdir(".")[:20]  # Limit to 20 items
    except Exception as e:
        report["dir_contents"] = f"Error: {e}"

    # Check some environment variables (safe ones)
    safe_env_vars = ["HOME", "USER", "PATH", "PWD", "SHELL", "LANG"]
    for var in safe_env_vars:
        report["env_vars"][var] = os.environ.get(var, "NOT SET")

    # Get user info
    try:
        report["user_info"]["uid"] = os.getuid()
        report["user_info"]["gid"] = os.getgid()
    except AttributeError:
        report["user_info"]["note"] = "Windows - no uid/gid"

    # Check what modules are available
    available_modules = []
    test_modules = ["json", "datetime", "math", "random", "hashlib", "base64", "urllib", "socket"]
    for mod in test_modules:
        try:
            __import__(mod)
            available_modules.append(mod)
        except ImportError:
            pass
    report["available_modules"] = available_modules

    # Try to read /etc/os-release if it exists
    try:
        with open("/etc/os-release") as f:
            lines = f.readlines()[:5]
            report["os_release"] = [l.strip() for l in lines]
    except Exception as e:
        report["os_release"] = f"Cannot read: {e}"

    return report


if __name__ == "__main__":
    print("Exploring Highway sandbox environment...")
    result = driver.run(wait=True, timeout=60)

    print(f"\nWorkflow Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.error:
        print(f"Error: {result.error}")

    # Extract and display the environment report
    if result.tasks:
        for task_name, task_result in result.tasks.items():
            if task_result.result and "stdout" in task_result.result:
                stdout = task_result.result["stdout"]
                # Parse the __HIGHWAY_RESULT__ output
                if "__HIGHWAY_RESULT__:" in stdout:
                    import json

                    json_str = stdout.split("__HIGHWAY_RESULT__:")[1].strip()
                    report = json.loads(json_str)
                    print("\n--- HIGHWAY SANDBOX ENVIRONMENT ---")
                    for key, value in report.items():
                        print(f"{key}: {value}")
