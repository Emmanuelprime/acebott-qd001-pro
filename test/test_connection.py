"""
Test: Connection
Verifies connect / disconnect / is_connected / error on wrong host.
No movement — safe to run anytime.
"""

import sys
import os
import socket

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acebott_car import AcebottCar

PASS = "[PASS]"
FAIL = "[FAIL]"


def test_connect_disconnect():
    car = AcebottCar()
    assert not car.is_connected, "Should not be connected before connect()"
    print(f"  {PASS} is_connected is False before connect()")

    car.connect()
    assert car.is_connected, "Should be connected after connect()"
    print(f"  {PASS} is_connected is True after connect()")

    car.disconnect()
    assert not car.is_connected, "Should not be connected after disconnect()"
    print(f"  {PASS} is_connected is False after disconnect()")


def test_context_manager():
    with AcebottCar() as car:
        assert car.is_connected, "Should be connected inside with-block"
        print(f"  {PASS} context manager: connected inside with-block")
    assert not car.is_connected, "Should be disconnected after with-block exits"
    print(f"  {PASS} context manager: disconnected after with-block exits")


def test_double_disconnect():
    car = AcebottCar()
    car.connect()
    car.disconnect()
    try:
        car.disconnect()   # second disconnect must not raise
        print(f"  {PASS} double disconnect is safe")
    except Exception as e:
        print(f"  {FAIL} double disconnect raised: {e}")
        raise


def test_wrong_host():
    car = AcebottCar(ip="192.168.4.99", port=100)
    try:
        car.connect(timeout=2)
        car.disconnect()
        print(f"  {FAIL} expected connection to fail for wrong host")
        raise AssertionError("Should have raised")
    except (socket.timeout, socket.error, OSError):
        print(f"  {PASS} connection to wrong host raises socket error")


def test_command_without_connect():
    car = AcebottCar()
    try:
        car.stop()
        print(f"  {FAIL} expected RuntimeError when not connected")
        raise AssertionError("Should have raised")
    except RuntimeError:
        print(f"  {PASS} RuntimeError raised when sending without connect()")


def run():
    tests = [
        test_connect_disconnect,
        test_context_manager,
        test_double_disconnect,
        test_wrong_host,
        test_command_without_connect,
    ]
    passed = failed = 0
    for t in tests:
        print(f"\n{t.__name__}")
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {FAIL} {e}")
            failed += 1
    print(f"\nConnection tests: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
