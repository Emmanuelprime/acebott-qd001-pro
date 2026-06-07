"""
Test: Movement
Exercises every motor direction for 0.8 s each with a short pause between.
The car WILL move — clear the area before running.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acebott_car import AcebottCar, DIR_TOP_LEFT, DIR_TOP_RIGHT, DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT

MOVE_DURATION = 0.8   # seconds per direction
PAUSE         = 0.4   # seconds between moves
TEST_SPEED    = 180   # moderate speed for testing


def _prompt(question: str) -> bool:
    answer = input(f"  >> {question} [y/n]: ").strip().lower()
    return answer == "y"


def run():
    print("\nMovement tests — car WILL move. Ensure it has clear space.\n")
    if not _prompt("Ready to start?"):
        print("Skipped.")
        return True

    passed = failed = 0

    moves = [
        ("forward",      lambda car: car.forward(TEST_SPEED)),
        ("backward",     lambda car: car.backward(TEST_SPEED)),
        ("strafe left",  lambda car: car.strafe_left(TEST_SPEED)),
        ("strafe right", lambda car: car.strafe_right(TEST_SPEED)),
        ("turn left (CCW spin)",  lambda car: car.turn_left(TEST_SPEED)),
        ("turn right (CW spin)", lambda car: car.turn_right(TEST_SPEED)),
        ("diagonal top-left",     lambda car: car.diagonal(DIR_TOP_LEFT, TEST_SPEED)),
        ("diagonal top-right",    lambda car: car.diagonal(DIR_TOP_RIGHT, TEST_SPEED)),
        ("diagonal bottom-left",  lambda car: car.diagonal(DIR_BOTTOM_LEFT, TEST_SPEED)),
        ("diagonal bottom-right", lambda car: car.diagonal(DIR_BOTTOM_RIGHT, TEST_SPEED)),
    ]

    with AcebottCar() as car:
        for name, action in moves:
            print(f"\n  Testing: {name} for {MOVE_DURATION}s ...")
            try:
                action(car)
                time.sleep(MOVE_DURATION)
                car.stop()
                time.sleep(PAUSE)
                ok = _prompt(f"Did the car move {name}?")
                if ok:
                    print(f"  [PASS] {name}")
                    passed += 1
                else:
                    print(f"  [FAIL] {name} — user reported no movement")
                    failed += 1
            except Exception as e:
                car.stop()
                print(f"  [FAIL] {name} raised: {e}")
                failed += 1

        print("\n  Testing: stop (car should remain stationary) ...")
        try:
            car.stop()
            time.sleep(1)
            ok = _prompt("Did the car stay still?")
            if ok:
                print("  [PASS] stop")
                passed += 1
            else:
                print("  [FAIL] stop — car moved unexpectedly")
                failed += 1
        except Exception as e:
            print(f"  [FAIL] stop raised: {e}")
            failed += 1

    print(f"\nMovement tests: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
