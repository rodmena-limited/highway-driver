#!/usr/bin/env python3
"""Example: Python task using stdlib libraries.

Tests that AST decorator stripping works correctly with:
- Multiple imports
- Dataclasses with decorators
- Nested functions
- Complex data structures
"""

from datetime import UTC

from highway import Driver

driver = Driver()


@driver.task(py=True)
def analyze_system():
    """Analyze system info using stdlib only."""
    import hashlib
    import os
    import platform
    import sys
    from collections import Counter
    from dataclasses import dataclass
    from datetime import datetime
    from functools import reduce

    @dataclass
    class SystemInfo:
        """System information container."""

        python_version: str
        platform: str
        architecture: str
        processor: str
        env_count: int
        timestamp: str

    @dataclass
    class AnalysisResult:
        """Full analysis result."""

        system: SystemInfo
        env_analysis: dict
        calculations: dict
        hash_demo: str

    # Gather system info
    system = SystemInfo(
        python_version=sys.version.split()[0],
        platform=platform.system(),
        architecture=platform.machine(),
        processor=platform.processor() or "unknown",
        env_count=len(os.environ),
        timestamp=datetime.now(UTC).isoformat(),
    )

    # Analyze environment variable patterns
    env_prefixes = Counter()
    for key in os.environ.keys():
        prefix = key.split("_")[0] if "_" in key else key[:4]
        env_prefixes[prefix] += 1

    # Some calculations to verify complex operations work
    numbers = list(range(1, 101))
    calculations = {
        "sum_1_to_100": sum(numbers),
        "factorial_10": reduce(lambda x, y: x * y, range(1, 11)),
        "fibonacci_10": (
            lambda n: [(f := [0, 1]) and [f.append(f[-1] + f[-2]) or f[-1] for _ in range(n)]][0][
                -1
            ]
        )(10),
        "primes_under_50": [
            n for n in range(2, 50) if all(n % i != 0 for i in range(2, int(n**0.5) + 1))
        ],
    }

    # Hash demonstration
    message = f"Highway sandbox test at {system.timestamp}"
    hash_demo = hashlib.sha256(message.encode()).hexdigest()[:16]

    result = AnalysisResult(
        system=system,
        env_analysis={"total_vars": system.env_count, "top_prefixes": env_prefixes.most_common(5)},
        calculations=calculations,
        hash_demo=hash_demo,
    )

    # Convert dataclasses to dict for JSON serialization
    return {
        "system": {
            "python_version": result.system.python_version,
            "platform": result.system.platform,
            "architecture": result.system.architecture,
            "processor": result.system.processor,
            "env_count": result.system.env_count,
            "timestamp": result.system.timestamp,
        },
        "env_analysis": result.env_analysis,
        "calculations": result.calculations,
        "hash_demo": result.hash_demo,
    }


if __name__ == "__main__":
    print("Running stdlib analysis in Highway sandbox...")

    result = driver.run(wait=True, timeout=60)

    print(f"\nWorkflow Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.tasks:
        for task_name, task_result in result.tasks.items():
            print(f"\n=== {task_name} ===")
            if task_result.result:
                stdout = task_result.result.get("stdout", "")
                stderr = task_result.result.get("stderr", "")

                if "__HIGHWAY_RESULT__:" in stdout:
                    import json

                    json_str = stdout.split("__HIGHWAY_RESULT__:")[1].strip()
                    data = json.loads(json_str)

                    print("\nSystem Info:")
                    print(f"  Python: {data['system']['python_version']}")
                    print(
                        f"  Platform: {data['system']['platform']} ({data['system']['architecture']})"
                    )
                    print(f"  Env vars: {data['system']['env_count']}")
                    print(f"  Timestamp: {data['system']['timestamp']}")

                    print("\nCalculations:")
                    print(f"  Sum 1-100: {data['calculations']['sum_1_to_100']}")
                    print(f"  10!: {data['calculations']['factorial_10']}")
                    print(f"  Fib(10): {data['calculations']['fibonacci_10']}")
                    print(f"  Primes <50: {data['calculations']['primes_under_50']}")

                    print(f"\nHash demo: {data['hash_demo']}")
                elif stdout:
                    print(f"Stdout: {stdout[:500]}")

                if stderr:
                    print(f"Stderr: {stderr[:500]}")

            if task_result.error:
                print(f"Error: {task_result.error}")
