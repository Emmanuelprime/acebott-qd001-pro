"""
Run all test modules in sequence.
Usage:  python test/run_all.py

Tests are run in this order:
  1. Connection  (no movement — safe to run first)
  2. Peripherals (no driving — bench-safe)
  3. Movement    (car moves — needs clear space)
  4. Modes       (autonomous — needs appropriate environment)

Each module reports its own pass/fail summary.
This runner prints an overall result at the end.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_connection
import test_peripherals
import test_movement
import test_modes

SEPARATOR = "=" * 52


def main():
    suites = [
        ("Connection",  test_connection.run),
        ("Peripherals", test_peripherals.run),
        ("Movement",    test_movement.run),
        ("Modes",       test_modes.run),
    ]

    results = {}
    for name, run_fn in suites:
        print(f"\n{SEPARATOR}")
        print(f"  SUITE: {name}")
        print(SEPARATOR)
        try:
            results[name] = run_fn()
        except KeyboardInterrupt:
            print(f"\n  Interrupted — skipping remaining suites.")
            results[name] = False
            break
        except Exception as e:
            print(f"  Suite crashed: {e}")
            results[name] = False

    print(f"\n{SEPARATOR}")
    print("  OVERALL RESULTS")
    print(SEPARATOR)
    all_passed = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}]  {name}")
        if not ok:
            all_passed = False

    print(SEPARATOR)
    print(f"  {'All tests passed.' if all_passed else 'Some tests failed.'}")
    print(SEPARATOR)
    return all_passed


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
