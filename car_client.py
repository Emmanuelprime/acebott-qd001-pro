"""
Quick demo — connects to the car and runs a short movement sequence.

Before running:
  1. Connect your PC to WiFi: SSID="ESP32-CAR", password="12345678"
  2. Run:  python car_client.py

Import acebott_car.AcebottCar in your own application instead of this file.
"""

import time
from acebott_car import AcebottCar


if __name__ == "__main__":
    with AcebottCar() as car:
        print("Forward...")
        car.forward(speed=200)
        time.sleep(2)

        print("Turn right...")
        car.turn_right(speed=200)
        time.sleep(1)

        print("Stop.")
        car.stop()
        time.sleep(0.5)

        print("Playing tune 1...")
        car.play_tune(1)
        time.sleep(4)
