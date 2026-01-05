#!/usr/bin/env python3
"""Run all Demo Matrix tests.

This script runs all phases of the demo matrix test suite.

Run with:
    export HIGHWAY_API_KEY="hw_k1_..."
    python examples/demo_matrix/run_all.py
"""

import sys
import traceback

# Support both direct execution and module import
try:
    from examples.demo_matrix import (
        phase1_connection,
        phase2_retry,
        phase3_concurrency,
        phase4_edge_cases,
        phase5_advanced,
    )
except ModuleNotFoundError:
    from . import (
        phase1_connection,
        phase2_retry,
        phase3_concurrency,
        phase4_edge_cases,
        phase5_advanced,
    )


def main() -> int:
    """Run all demo matrix phases."""
    print("\n" + "=" * 70)
    print("HIGHWAY DRIVER SDK - DEMO MATRIX TEST SUITE")
    print("=" * 70)
    print("\nThis test suite validates the Highway Driver SDK against")
    print("production highway.solutions with systematic corner case tests.\n")

    failures = []

    # Phase 1: Connection & Timeout
    try:
        phase1_connection.run_all()
    except Exception as e:
        failures.append(("Phase 1", str(e)))
        traceback.print_exc()

    # Phase 2: Retry & Failure
    try:
        phase2_retry.run_all()
    except Exception as e:
        failures.append(("Phase 2", str(e)))
        traceback.print_exc()

    # Phase 3: Concurrency
    try:
        phase3_concurrency.run_all()
    except Exception as e:
        failures.append(("Phase 3", str(e)))
        traceback.print_exc()

    # Phase 4: Edge Cases
    try:
        phase4_edge_cases.run_all()
    except Exception as e:
        failures.append(("Phase 4", str(e)))
        traceback.print_exc()

    # Phase 5: Advanced Patterns
    try:
        phase5_advanced.run_all()
    except Exception as e:
        failures.append(("Phase 5", str(e)))
        traceback.print_exc()

    # Summary
    print("\n" + "=" * 70)
    if failures:
        print("DEMO MATRIX SUMMARY: %d FAILURES" % len(failures))
        for phase, error in failures:
            print(f"  - {phase}: {error}")
        print("=" * 70)
        return 1
    else:
        print("DEMO MATRIX SUMMARY: ALL PHASES PASSED!")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
