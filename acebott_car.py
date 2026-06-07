import socket
import time
import threading


# ---------------------------------------------------------------------------
# Connection defaults
# ---------------------------------------------------------------------------

DEFAULT_IP   = "192.168.4.1"   # ESP32 AP default gateway
DEFAULT_PORT = 100             # TCP server port set in firmware

# Motors have a minimum PWM threshold below which static friction prevents
# movement. Tested values: 100 = no movement, 180 = moves. Tune this for
# your surface if needed (carpet requires higher values than hard floor).
MIN_EFFECTIVE_SPEED = 150


# ---------------------------------------------------------------------------
# Protocol — Action IDs (firmware buffer[9])
# ---------------------------------------------------------------------------

CMD_RUN     = 0x01   # Manual control — uses device + val
CMD_STANDBY = 0x03   # Stop everything, cancel autonomous mode
CMD_TRACK_1 = 0x04   # Line-follow mode 1 (left + right IR sensors)
CMD_TRACK_2 = 0x05   # Line-follow mode 2 (left + center + right IR sensors)
CMD_AVOID   = 0x06   # Obstacle avoidance (ultrasonic)
CMD_FOLLOW  = 0x07   # Ultrasonic follow mode


# ---------------------------------------------------------------------------
# Protocol — Device IDs for CMD_RUN (firmware buffer[10])
# ---------------------------------------------------------------------------

DEV_MOTOR  = 0x0C   # Motor direction — val is a DIR_* constant below
DEV_SERVO  = 0x02   # Tilt servo angle — val is 0–180 degrees
DEV_BUZZER = 0x03   # Play a tune — val is 1–4
DEV_LED    = 0x05   # LED modules — val is 1 (on) or 0 (off)
DEV_SHOOT  = 0x08   # Trigger shooter — 150 ms pulse, val ignored
DEV_SPEED  = 0x0D   # Set global speed — val is 0–255


# ---------------------------------------------------------------------------
# Motor direction values (val for DEV_MOTOR)
# ---------------------------------------------------------------------------

DIR_STOP         = 0x00
DIR_FORWARD      = 0x01
DIR_BACKWARD     = 0x02
DIR_STRAFE_LEFT  = 0x03
DIR_STRAFE_RIGHT = 0x04
DIR_TOP_LEFT     = 0x05
DIR_BOTTOM_LEFT  = 0x06
DIR_TOP_RIGHT    = 0x07
DIR_BOTTOM_RIGHT = 0x08
DIR_SPIN_CCW     = 0x09   # Counter-clockwise (Contrarotate in firmware)
DIR_SPIN_CW      = 0x0A   # Clockwise


# ---------------------------------------------------------------------------
# Internal packet builder
# ---------------------------------------------------------------------------

def _build_packet(action: int, device: int = 0x00, val: int = 0x00) -> bytes:
    """
    Build a 13-byte command packet matching the firmware's binary protocol.

    Wire layout:
      0xFF 0x55          — frame header (0xFF stored as prevc, 0x55 triggers start)
      0x0A               — length = 10 (counts every byte that follows)
      0x00 0x00 0x00     — buffer[3–5]: unused
      0x00 0x00 0x00     — buffer[6–8]: unused
      [action]           — buffer[9]:  command ID
      [device]           — buffer[10]: device ID
      0x00               — buffer[11]: unused
      [val]              — buffer[12]: value / direction / angle
    """
    return bytes([
        0xFF, 0x55, 0x0A,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        action & 0xFF,
        device & 0xFF,
        0x00,
        val & 0xFF,
    ])


# ---------------------------------------------------------------------------
# AcebottCar
# ---------------------------------------------------------------------------

class AcebottCar:
    """
    Python interface for the ACEBOTT QD001 Pro smart car.

    Usage
    -----
    Connect your PC to the car's WiFi ("ESP32-CAR" / "12345678"), then:

        from acebott_car import AcebottCar

        with AcebottCar() as car:
            car.forward(speed=200)
            time.sleep(1)
            car.stop()

    All public methods raise RuntimeError if called before connect().
    """

    def __init__(self, ip: str = DEFAULT_IP, port: int = DEFAULT_PORT):
        self._ip   = ip
        self._port = port
        self._sock: socket.socket | None = None
        self._lock  = threading.Lock()
        self._running = False
        self._heartbeat_thread: threading.Thread | None = None
        self._current_speed: int | None = None  # cached to avoid redundant DEV_SPEED packets

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, timeout: float = 5.0):
        """
        Open a TCP connection to the car.
        Must be called before any command method.
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect((self._ip, self._port))
        self._current_speed = None  # firmware speed state is unknown on fresh connect
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def disconnect(self):
        """Stop the car and close the TCP connection."""
        self._running = False
        try:
            self.standby()
        except Exception:
            pass
        if self._sock:
            self._sock.close()
            self._sock = None

    @property
    def is_connected(self) -> bool:
        return self._sock is not None and self._running

    def _send(self, packet: bytes):
        if not self.is_connected:
            raise RuntimeError("Not connected — call connect() first.")
        with self._lock:
            self._sock.sendall(packet)

    def _heartbeat_loop(self):
        """
        Keep the TCP connection alive without disrupting autonomous modes.

        The firmware drops the connection only when ALL three are true:
          - no data received for > 3 s
          - st flag is True  (set only when byte 0xC8 / 200 is received)
          - client.available() == 0

        Any byte that is NOT 0xC8 resets st=False and the idle timer.
        Sending a full CMD_STANDBY packet would cancel the current
        function_mode, so we send a single 0x00 byte instead — harmless
        to the parser (not 0xFF, not 0x55, not 200) but enough to keep
        the connection alive.
        """
        while self._running:
            time.sleep(2)
            if self._running and self._sock:
                try:
                    self._send(b'\x00')
                except Exception:
                    break

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def move(self, direction: int, speed: int = 200):
        """
        Send a direction command at the given speed (0–255).
        direction must be one of the DIR_* constants.

        DEV_SPEED is only sent when the speed value changes, keeping each
        move() call to a single packet in the common case and eliminating
        the race where a back-to-back speed+direction pair could cause the
        firmware to process the direction before the new speed is applied.
        """
        if speed != self._current_speed:
            self.set_speed(speed)
        self._send(_build_packet(CMD_RUN, DEV_MOTOR, direction))

    def stop(self):
        """Stop all motors immediately."""
        self._send(_build_packet(CMD_RUN, DEV_MOTOR, DIR_STOP))

    def forward(self, speed: int = 200):
        self.move(DIR_FORWARD, speed)

    def backward(self, speed: int = 200):
        self.move(DIR_BACKWARD, speed)

    def turn_left(self, speed: int = 200):
        """
        Spin counter-clockwise.
        The ACB_SmartCar_V2 library requires a brief backward pulse before
        the spin engages — mirrors how the firmware's own obstacle-avoidance
        mode uses Contrarotate (always preceded by a Backward move).
        """
        self.move(DIR_BACKWARD, speed)
        time.sleep(0.15)
        self.move(DIR_SPIN_CCW, speed)

    def turn_right(self, speed: int = 200):
        """
        Spin clockwise.
        See turn_left for the reason behind the backward pre-pulse.
        """
        self.move(DIR_BACKWARD, speed)
        time.sleep(0.15)
        self.move(DIR_SPIN_CW, speed)

    def strafe_left(self, speed: int = 200):
        """Translate left (mecanum / omni wheels)."""
        self.move(DIR_STRAFE_LEFT, speed)

    def strafe_right(self, speed: int = 200):
        """Translate right (mecanum / omni wheels)."""
        self.move(DIR_STRAFE_RIGHT, speed)

    def diagonal(self, direction: int, speed: int = 200):
        """
        Diagonal movement.
        direction: DIR_TOP_LEFT, DIR_TOP_RIGHT,
                   DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT

        Bottom directions (backward-diagonal) require the same backward
        pre-pulse as spin commands — the ACB_SmartCar_V2 library needs
        the motors energised in reverse before engaging these movements.
        """
        if direction in (DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT):
            self.move(DIR_BACKWARD, speed)
            time.sleep(0.15)
        self.move(direction, speed)

    # ------------------------------------------------------------------
    # Speed
    # ------------------------------------------------------------------

    def set_speed(self, speed: int):
        """
        Set the global motor speed used by the firmware (0–255).
        The firmware default on boot is 250.
        Always sends the packet unconditionally — use this to force a
        speed sync (e.g. after reconnecting). move() uses caching instead.
        """
        speed = max(0, min(255, speed))
        self._send(_build_packet(CMD_RUN, DEV_SPEED, speed))
        self._current_speed = speed

    # ------------------------------------------------------------------
    # Servo
    # ------------------------------------------------------------------

    def set_servo(self, angle: int):
        """
        Set the tilt servo angle (0–180 degrees).
        90 = centre / forward-facing.
        """
        angle = max(0, min(180, angle))
        self._send(_build_packet(CMD_RUN, DEV_SERVO, angle))

    # ------------------------------------------------------------------
    # Peripherals
    # ------------------------------------------------------------------

    def set_leds(self, on: bool):
        """Turn both LED modules on (True) or off (False)."""
        self._send(_build_packet(CMD_RUN, DEV_LED, 0x01 if on else 0x00))

    def shoot(self):
        """Trigger the shooter (150 ms solenoid pulse)."""
        self._send(_build_packet(CMD_RUN, DEV_SHOOT, 0x01))

    def play_tune(self, tune: int):
        """
        Play a built-in tune.
          1 — Little Star
          2 — Jingle Bell
          3 — Happy New Year
          4 — Old MacDonald
        """
        tune = max(1, min(4, tune))
        self._send(_build_packet(CMD_RUN, DEV_BUZZER, tune))

    # ------------------------------------------------------------------
    # Autonomous modes
    # ------------------------------------------------------------------

    def standby(self):
        """Cancel any autonomous mode, stop motors, centre servo."""
        self._send(_build_packet(CMD_STANDBY))

    def mode_line_follow_1(self):
        """
        Activate 2-sensor line following.
        Uses left + right IR sensors only.
        """
        self._send(_build_packet(CMD_TRACK_1))

    def mode_line_follow_2(self):
        """
        Activate 3-sensor line following.
        Uses left + center + right IR sensors.
        """
        self._send(_build_packet(CMD_TRACK_2))

    def mode_obstacle_avoid(self):
        """
        Activate autonomous obstacle avoidance.
        Servo scans left/right with ultrasonic sensor to pick a clear path.
        """
        self._send(_build_packet(CMD_AVOID))

    def mode_follow(self):
        """
        Activate ultrasonic follow mode.
        Car follows an object kept 15–50 cm in front of the sensor.
        """
        self._send(_build_packet(CMD_FOLLOW))

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def __repr__(self):
        status = "connected" if self.is_connected else "disconnected"
        return f"AcebottCar({self._ip}:{self._port}, {status})"
