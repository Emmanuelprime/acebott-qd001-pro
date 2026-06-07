"""
Test: Autonomous Modes
Activates each autonomous mode for a fixed duration then returns to standby.
The car WILL move autonomously — clear the area and set up the appropriate
environment for each mode before confirming.

  Line follow modes  — needs a line-following track
  Obstacle avoidance — needs open space with at least one obstacle
  Follow mode        — needs an object to track 15–50 cm ahead
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acebott_car import AcebottCar

PASS = "[PASS]"
FAIL = "[FAIL]"
MODE_DURATION = 5   # seconds each mode runs before standby is sent


def _prompt(question: str) -> bool:
    answer = input(f"  >> {question} [y/n]: ").strip().lower()
    return answer == "y"


def _run_mode(car: AcebottCar, name: str, activate_fn, env_hint: str) -> bool:
    print(f"\n  Mode: {name}")
    print(f"  Environment needed: {env_hint}")
    if not _prompt(f"Ready to test {name} for {MODE_DURATION}s?"):
        print("  Skipped.")
        return True
    try:
        activate_fn()
        print(f"  Mode active — running for {MODE_DURATION}s ...")
        time.sleep(MODE_DURATION)
        car.standby()
        time.sleep(0.5)
        ok = _prompt(f"Did the car behave correctly in {name}?")
        if ok:
            print(f"  {PASS} {name}")
        else:
            print(f"  {FAIL} {name} — unexpected behaviour")
        return ok
    except Exception as e:
        car.standby()
        print(f"  {FAIL} {name} raised: {e}")
        return False


def test_standby(car: AcebottCar) -> bool:
    print("\ntest_standby")
    try:
        car.forward(150)
        time.sleep(0.5)
        car.standby()
        time.sleep(0.5)
        ok = _prompt("Did the car stop when standby() was sent?")
        if ok:
            print(f"  {PASS} standby cancels motion")
        else:
            print(f"  {FAIL} standby did not stop car")
        return ok
    except Exception as e:
        print(f"  {FAIL} standby raised: {e}")
        return False


def run():
    passed = failed = 0

    print("\nAutonomous mode tests — car WILL move.\n")

    with AcebottCar() as car:
        # Standby first (safest, no environment needed)
        ok = test_standby(car)
        passed += ok
        failed += not ok

        modes = [
            (
                "Line Follow Mode 1 (2-sensor)",
                car.mode_line_follow_1,
                "Black line on white surface, left + right IR sensors",
            ),
            (
                "Line Follow Mode 2 (3-sensor)",
                car.mode_line_follow_2,
                "Black line on white surface, all 3 IR sensors",
            ),
            (
                "Obstacle Avoidance",
                car.mode_obstacle_avoid,
                "Open area with at least one obstacle ahead",
            ),
            (
                "Follow Mode",
                car.mode_follow,
                "Object held 15–50 cm in front of the ultrasonic sensor",
            ),
        ]

        for name, fn, hint in modes:
            ok = _run_mode(car, name, fn, hint)
            passed += ok
            failed += not ok

    print(f"\nAutonomous mode tests: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
