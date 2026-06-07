import socket
import time
import threading
import queue


# ---------------------------------------------------------------------------
# Connection defaults  (QD003 uses a different SSID: "ESP32_QD003")
# ---------------------------------------------------------------------------

DEFAULT_IP   = "192.168.4.1"
DEFAULT_PORT = 100

# Motors need a minimum PWM to overcome static friction (same hardware)
MIN_EFFECTIVE_SPEED = 150


# ---------------------------------------------------------------------------
# Protocol — Action IDs  (firmware buffer[9])
# ---------------------------------------------------------------------------

CMD_RUN     = 0x01   # Manual control / activate a mode via device field
CMD_STANDBY = 0x03   # Stop everything, return to idle


# ---------------------------------------------------------------------------
# Protocol — Device IDs for CMD_RUN  (firmware buffer[10])
# ---------------------------------------------------------------------------

# Motor / servo / audio (identical to QD001)
DEV_MOTOR  = 0x0C
DEV_SERVO  = 0x02
DEV_BUZZER = 0x03
DEV_SPEED  = 0x0D

# CV mode activators — sent as the device field alongside CMD_RUN
# The QD003 parseData() runs a second switch on buffer[10], so these
# IDs set function_mode regardless of the action field.
DEV_QR_CODE       = 30
DEV_BARCODE       = 31
DEV_DIGITAL_RECOG = 32
DEV_COLOR_RECOG   = 33
DEV_IMAGE_RECOG   = 34
DEV_COLOR_TRACK   = 35   # val = color ID passed to color_recognize()
DEV_VISUAL_PATROL = 36
DEV_TRAFFIC       = 37
DEV_ML            = 38
DEV_FACE_RECOG    = 39

# RGB LED channels — val is 0–255
DEV_RGB_RED   = 41
DEV_RGB_GREEN = 42
DEV_RGB_BLUE  = 43

# Stop CV / return camera to menu
DEV_TAKE_STOP = 50

# Line-follow modes use the action field directly (same as QD001)
CMD_TRACK_1 = 0x04
CMD_TRACK_2 = 0x05


# ---------------------------------------------------------------------------
# Motor direction values  (val for DEV_MOTOR — identical to QD001)
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
DIR_SPIN_CCW     = 0x09
DIR_SPIN_CW      = 0x0A

# Color IDs used by ACB_CanMV.color_recognize()
COLOR_RED    = 1
COLOR_GREEN  = 2
COLOR_BLUE   = 3
COLOR_YELLOW = 4


# ---------------------------------------------------------------------------
# Internal packet builder  (same protocol as QD001)
# ---------------------------------------------------------------------------

def _build_packet(action: int, device: int = 0x00, val: int = 0x00) -> bytes:
    """
    Build a 13-byte command packet.

      0xFF 0x55          — frame header
      0x0A               — length byte (= 10)
      0x00 × 6           — buffer[3–8]: unused
      [action]           — buffer[9]
      [device]           — buffer[10]
      0x00               — buffer[11]: unused
      [val]              — buffer[12]
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
# AcebottCVCar
# ---------------------------------------------------------------------------

class AcebottCVCar:
    """
    Python interface for the ACEBOTT QD003 smart car (CV firmware).

    Usage
    -----
    Connect your PC to the car's WiFi ("ESP32_QD003" / "12345678"), then:

        from acebott_cv_car import AcebottCVCar

        def on_tag(tag: str):
            print("Got tag:", tag)

        with AcebottCVCar() as car:
            car.set_tag_callback(on_tag)
            car.mode_face_recognition()
            time.sleep(10)

    Key difference from QD001
    -------------------------
    - parseData() in this firmware always stops motors before processing
      any packet — there is no sustained-movement mode via CMD_RUN alone.
    - CV modes run autonomously in the firmware loop and stream recognition
      tags back over the TCP connection as newline-terminated strings.
    - No ultrasonic sensor, no shooter, no LED modules.
    """

    def __init__(self, ip: str = DEFAULT_IP, port: int = DEFAULT_PORT):
        self._ip   = ip
        self._port = port
        self._sock: socket.socket | None = None
        self._send_lock    = threading.Lock()
        self._running      = False
        self._current_speed: int | None = None

        # Tag reception
        self._tag_queue:    queue.Queue[str] = queue.Queue()
        self._tag_callback = None           # callable(tag: str) | None
        self._recv_thread:  threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, timeout: float = 5.0):
        """Open a TCP connection to the car."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect((self._ip, self._port))
        # Keep a short timeout so recv() doesn't block the thread permanently
        # and so we can check self._running periodically.
        self._sock.settimeout(0.5)
        self._running      = True
        self._current_speed = None

        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True
        )
        self._recv_thread.start()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def disconnect(self):
        """Stop CV, stop motors, close the connection."""
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
        with self._send_lock:
            self._sock.sendall(packet)

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _heartbeat_loop(self):
        """
        Keep the connection alive with a harmless 0x00 byte every 2 s.
        0x00 is not 0xFF/0x55/200 so the parser ignores it but the idle
        timer is reset — the same strategy used for QD001.
        """
        while self._running:
            time.sleep(2)
            if self._running and self._sock:
                try:
                    self._send(b'\x00')
                except Exception:
                    break

    def _recv_loop(self):
        """
        Read recognition tag strings sent back by the firmware.

        The firmware forwards everything on its serial port to the TCP client
        one character at a time — this includes:
          - Recognition tags from ACB_CanMV (e.g. "red\r\n", "Go_Straight\r\n")
          - Echo of every received command byte (Serial.write(c))
          - "[Client connected]" / "[Client disconnected]" debug strings

        We accumulate printable ASCII characters into a line buffer and emit
        a tag whenever a newline arrives.  Non-printable bytes (echoed binary
        command packets) are discarded so they don't pollute the output.
        """
        buf = ""
        while self._running:
            try:
                chunk = self._sock.recv(256)
                if not chunk:
                    break
                for byte in chunk:
                    ch = chr(byte)
                    if ch in ('\r', '\n'):
                        tag = buf.strip()
                        buf = ""
                        # Ignore empty lines and firmware debug messages
                        if tag and not tag.startswith("["):
                            self._tag_queue.put(tag)
                            if self._tag_callback:
                                try:
                                    self._tag_callback(tag)
                                except Exception:
                                    pass
                    elif ch.isprintable():
                        buf += ch
                        if len(buf) > 128:   # safety: discard runaway lines
                            buf = ""
            except socket.timeout:
                continue   # normal — check self._running and loop
            except Exception:
                break

    # ------------------------------------------------------------------
    # Tag reception
    # ------------------------------------------------------------------

    def set_tag_callback(self, callback):
        """
        Register a callable that is invoked on the receiver thread each
        time the car sends back a recognition tag string.
        callback signature: callback(tag: str)
        Pass None to deregister.
        """
        self._tag_callback = callback

    def get_tag(self) -> str | None:
        """
        Return the oldest pending tag from the queue, or None if empty.
        Non-blocking — suitable for polling in a GUI loop.
        """
        try:
            return self._tag_queue.get_nowait()
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # Movement  (same pre-pulse fixes as QD001 — same library/hardware)
    # ------------------------------------------------------------------

    def move(self, direction: int, speed: int = 200):
        """
        Send a direction command.
        Note: the QD003 firmware stops motors on every parsed packet, so
        this is always a one-shot command — the firmware loop does not
        sustain motion between packets. Call repeatedly or use an
        autonomous mode for continuous movement.
        """
        if speed != self._current_speed:
            self.set_speed(speed)
        self._send(_build_packet(CMD_RUN, DEV_MOTOR, direction))

    def stop(self):
        self._send(_build_packet(CMD_RUN, DEV_MOTOR, DIR_STOP))

    def forward(self, speed: int = 200):
        self.move(DIR_FORWARD, speed)

    def backward(self, speed: int = 200):
        self.move(DIR_BACKWARD, speed)

    def turn_left(self, speed: int = 200):
        """Spin CCW — requires backward pre-pulse (same library quirk as QD001)."""
        self.move(DIR_BACKWARD, speed)
        time.sleep(0.15)
        self.move(DIR_SPIN_CCW, speed)

    def turn_right(self, speed: int = 200):
        """Spin CW — requires backward pre-pulse."""
        self.move(DIR_BACKWARD, speed)
        time.sleep(0.15)
        self.move(DIR_SPIN_CW, speed)

    def strafe_left(self, speed: int = 200):
        self.move(DIR_STRAFE_LEFT, speed)

    def strafe_right(self, speed: int = 200):
        self.move(DIR_STRAFE_RIGHT, speed)

    def diagonal(self, direction: int, speed: int = 200):
        """
        Diagonal movement (DIR_TOP_LEFT/RIGHT, DIR_BOTTOM_LEFT/RIGHT).
        Bottom directions require a backward pre-pulse.
        """
        if direction in (DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT):
            self.move(DIR_BACKWARD, speed)
            time.sleep(0.15)
        self.move(direction, speed)

    def set_speed(self, speed: int):
        """Set the global motor speed (0–255). Always sends unconditionally."""
        speed = max(0, min(255, speed))
        self._send(_build_packet(CMD_RUN, DEV_SPEED, speed))
        self._current_speed = speed

    # ------------------------------------------------------------------
    # Servo & Audio
    # ------------------------------------------------------------------

    def set_servo(self, angle: int):
        """Set the camera height servo angle (0–180). 90 = centre."""
        angle = max(0, min(180, angle))
        self._send(_build_packet(CMD_RUN, DEV_SERVO, angle))

    def play_tune(self, tune: int):
        """
        Play a built-in tune.
          1 — Little Star   2 — Jingle Bell
          3 — Happy New Year  4 — Old MacDonald
        """
        self._send(_build_packet(CMD_RUN, DEV_BUZZER, max(1, min(4, tune))))

    # ------------------------------------------------------------------
    # RGB LED (on the CanMV camera module)
    # ------------------------------------------------------------------

    def set_rgb(self, r: int, g: int, b: int):
        """Set all three RGB LED channels at once (each 0–255)."""
        self._send(_build_packet(CMD_RUN, DEV_RGB_RED,   max(0, min(255, r))))
        self._send(_build_packet(CMD_RUN, DEV_RGB_GREEN, max(0, min(255, g))))
        self._send(_build_packet(CMD_RUN, DEV_RGB_BLUE,  max(0, min(255, b))))

    def set_rgb_red(self, val: int):
        self._send(_build_packet(CMD_RUN, DEV_RGB_RED,   max(0, min(255, val))))

    def set_rgb_green(self, val: int):
        self._send(_build_packet(CMD_RUN, DEV_RGB_GREEN, max(0, min(255, val))))

    def set_rgb_blue(self, val: int):
        self._send(_build_packet(CMD_RUN, DEV_RGB_BLUE,  max(0, min(255, val))))

    # ------------------------------------------------------------------
    # Standby / IR line-follow modes  (same as QD001)
    # ------------------------------------------------------------------

    def standby(self):
        """Cancel all modes, stop motors, centre servo."""
        self._send(_build_packet(CMD_STANDBY))

    def mode_line_follow_1(self):
        """IR 2-sensor line following (left + right)."""
        self._send(_build_packet(CMD_TRACK_1))

    def mode_line_follow_2(self):
        """IR 3-sensor line following (left + center + right)."""
        self._send(_build_packet(CMD_TRACK_2))

    # ------------------------------------------------------------------
    # CV modes  (activate camera-based autonomous behaviours)
    # ------------------------------------------------------------------

    def mode_qr_code(self):
        """Activate QR code recognition — tags streamed back via callback."""
        self._send(_build_packet(CMD_RUN, DEV_QR_CODE))

    def mode_barcode(self):
        """Activate barcode recognition."""
        self._send(_build_packet(CMD_RUN, DEV_BARCODE))

    def mode_digital_recognition(self):
        """Activate digit recognition."""
        self._send(_build_packet(CMD_RUN, DEV_DIGITAL_RECOG))

    def mode_color_recognition(self):
        """Activate colour recognition — tag is the colour name."""
        self._send(_build_packet(CMD_RUN, DEV_COLOR_RECOG))

    def mode_image_recognition(self):
        """Activate generic image classification."""
        self._send(_build_packet(CMD_RUN, DEV_IMAGE_RECOG))

    def mode_color_tracking(self, color_id: int = COLOR_RED):
        """
        Activate colour tracking — car physically follows the target colour.
        color_id: COLOR_RED(1), COLOR_GREEN(2), COLOR_BLUE(3), COLOR_YELLOW(4)
        """
        self._send(_build_packet(CMD_RUN, DEV_COLOR_TRACK, color_id))

    def mode_visual_patrol(self):
        """
        Activate camera-based line following.
        Servo tilts to 35° to look at the ground. No IR sensors used.
        """
        self._send(_build_packet(CMD_RUN, DEV_VISUAL_PATROL))

    def mode_traffic_identification(self):
        """
        Activate traffic sign recognition and autonomous driving.
        Signs: Go_Straight, Turn_Right, Turn_Left, Turn_Around, Throughout.
        """
        self._send(_build_packet(CMD_RUN, DEV_TRAFFIC))

    def mode_machine_learning(self):
        """Activate custom ML inference mode."""
        self._send(_build_packet(CMD_RUN, DEV_ML))

    def mode_face_recognition(self):
        """Activate face recognition — detected/not-detected tag streamed back."""
        self._send(_build_packet(CMD_RUN, DEV_FACE_RECOG))

    def stop_cv(self):
        """Stop the current CV mode and return the camera to its menu screen."""
        self._send(_build_packet(CMD_RUN, DEV_TAKE_STOP))

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
        return f"AcebottCVCar({self._ip}:{self._port}, {status})"
