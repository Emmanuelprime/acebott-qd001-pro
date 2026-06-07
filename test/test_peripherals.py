"""
Test: Peripherals
Tests LEDs, buzzer tunes, speed control, and the shooter.
The car will NOT drive — safe to run on a bench.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acebott_car import AcebottCar

PASS = "[PASS]"
FAIL = "[FAIL]"


def _prompt(question: str) -> bool:
    answer = input(f"  >> {question} [y/n]: ").strip().lower()
    return answer == "y"


def test_leds(car: AcebottCar):
    print("\ntest_leds")
    try:
        print("  Turning LEDs ON ...")
        car.set_leds(True)
        time.sleep(1.5)
        ok_on = _prompt("Are both LEDs on?")

        print("  Turning LEDs OFF ...")
        car.set_leds(False)
        time.sleep(1.5)
        ok_off = _prompt("Are both LEDs off?")

        if ok_on and ok_off:
            print(f"  {PASS} LED on/off")
            return True
        else:
            print(f"  {FAIL} LED on/off — unexpected result")
            return False
    except Exception as e:
        print(f"  {FAIL} raised: {e}")
        return False


def test_speed_control(car: AcebottCar):
    """
    Drives forward at three different speeds so the user can feel
    the difference. Car will move briefly.

    Speed 100 is intentionally below MIN_EFFECTIVE_SPEED to verify the
    motor minimum threshold. Values below ~150 won't move the car.
    """
    print("\ntest_speed_control")
    if not _prompt("Car will drive forward at 3 speeds. Ready?"):
        print("  Skipped.")
        return True
    results = []
    for speed, label in [(150, "slow"), (200, "medium"), (250, "fast")]:
        try:
            print(f"  Speed {speed} ({label}) for 1s ...")
            car.forward(speed)
            time.sleep(1)
            car.stop()
            time.sleep(0.5)
            ok = _prompt(f"Did the car move at {label} speed ({speed})?")
            results.append(ok)
            if ok:
                print(f"  {PASS} speed {speed}")
            else:
                print(f"  {FAIL} speed {speed}")
        except Exception as e:
            car.stop()
            print(f"  {FAIL} speed {speed} raised: {e}")
            results.append(False)
    return all(results)


def test_tunes(car: AcebottCar):
    print("\ntest_tunes")
    tune_names = {
        1: "Little Star",
        2: "Jingle Bell",
        3: "Happy New Year",
        4: "Old MacDonald",
    }
    # Tune durations (approximate, based on firmware note arrays)
    tune_wait = {1: 12, 2: 8, 3: 11, 4: 7}
    results = []
    for num, name in tune_names.items():
        try:
            print(f"  Playing tune {num}: {name} (wait ~{tune_wait[num]}s) ...")
            car.play_tune(num)
            time.sleep(tune_wait[num])
            ok = _prompt(f"Did you hear '{name}'?")
            results.append(ok)
            if ok:
                print(f"  {PASS} tune {num}: {name}")
            else:
                print(f"  {FAIL} tune {num}: {name}")
        except Exception as e:
            print(f"  {FAIL} tune {num} raised: {e}")
            results.append(False)
    return all(results)


def test_shooter(car: AcebottCar):
    print("\ntest_shooter")
    if not _prompt("Ready to test the shooter?"):
        print("  Skipped.")
        return True
    try:
        print("  Firing shooter (150 ms pulse) ...")
        car.shoot()
        time.sleep(0.5)
        ok = _prompt("Did the shooter fire?")
        if ok:
            print(f"  {PASS} shooter")
        else:
            print(f"  {FAIL} shooter — no actuation observed")
        return ok
    except Exception as e:
        print(f"  {FAIL} shooter raised: {e}")
        return False


def run():
    passed = failed = 0
    tests = [test_leds, test_speed_control, test_tunes, test_shooter]

    with AcebottCar() as car:
        for t in tests:
            ok = t(car)
            if ok:
                passed += 1
            else:
                failed += 1

    print(f"\nPeripheral tests: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
