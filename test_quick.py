#!/usr/bin/env python3
"""Quick test script that loads .env and runs a simple workflow."""

from pathlib import Path

# Load .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            import os

            os.environ[key] = value

from highway import Driver

driver = Driver()

print("API Key:", driver.api_key[:20] + "..." if driver.api_key else "NOT SET")
print("Endpoint:", driver.endpoint)
print()


@driver.task(shell=True)
def hello():
    return "echo 'Hello from Highway Driver!'"


print("Running workflow...")
result = driver.run(wait=True, timeout=60)

print()
print("Status:", result.status)
print("Run ID:", result.run_id)
