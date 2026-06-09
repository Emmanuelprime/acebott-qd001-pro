#!/usr/bin/env python3
"""
Voice control for ACEBOTT smart car (QD001 Pro / QD003).
100% OFFLINE — no internet needed while connected to the car's WiFi AP.

First-time setup (do once while you still have internet):
    python voice_control.py --download-model

Usage:
    python voice_control.py                 # QD001 Pro default
    python voice_control.py --host 192.168.4.1 --port 100

Spoken commands:
    "go straight [for N seconds]"           → forward
    "go back / backward [for N seconds]"    → backward
    "turn left [for N seconds]"             → spin left
    "turn right [for N seconds]"            → spin right
    "turn around"                           → 180-degree spin
    "strafe left [for N seconds]"           → lateral left
    "strafe right [for N seconds]"          → lateral right
    "stop" / "halt"                         → stop all motors
    "speed N"                               → set speed (150–255)
    "exit" / "quit"                         → disconnect and exit

Requires:
    pip install vosk pyaudio
"""

import audioop
import json
import os
import re
import sys
import time
import zipfile
import argparse
import urllib.request

# Force UTF-8 output on Windows so box-drawing characters print correctly
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import pyaudio
except ImportError:
    print("Missing dependency. Run:  pip install pyaudio")
    sys.exit(1)

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
except ImportError:
    print("Missing dependency. Run:  pip install vosk")
    sys.exit(1)

from acebott_car import AcebottCar, MIN_EFFECTIVE_SPEED
from acebott_cv_car import AcebottCVCar


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

MODEL_DIR  = os.path.join(os.path.dirname(__file__), "vosk_model")
MODEL_URL  = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_NAME = "vosk-model-small-en-us-0.15"  # folder name inside the zip


def download_model():
    """Download and unzip the small English Vosk model (~40 MB)."""
    if os.path.isdir(MODEL_DIR):
        print(f"Model already exists at: {MODEL_DIR}")
        return

    print(f"Downloading Vosk English model from:\n  {MODEL_URL}")
    print("(~40 MB — do this once while you have internet access)\n")

    parent  = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(parent, "_vosk_model_download.zip")

    # Streaming download with progress bar
    try:
        with urllib.request.urlopen(MODEL_URL) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
                        print(f"\r  [{bar}] {pct:3d}%  {downloaded//1024:,} KB", end="", flush=True)
    except Exception as exc:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise RuntimeError(f"Download failed: {exc}") from exc

    print("\n  Extracting …")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(parent)

    extracted = os.path.join(parent, MODEL_NAME)
    os.rename(extracted, MODEL_DIR)
    os.remove(zip_path)
    print(f"Model saved to: {MODEL_DIR}\n")


def load_model() -> Model:
    if not os.path.isdir(MODEL_DIR):
        print(
            "Vosk model not found.\n"
            "Run this once (with internet) to download it:\n"
            "    python voice_control.py --download-model"
        )
        sys.exit(1)
    SetLogLevel(-1)   # suppress verbose Vosk/Kaldi output
    return Model(MODEL_DIR)


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

DEFAULT_HOST          = "192.168.4.1"
DEFAULT_PORT          = 100
DEFAULT_DURATION      = 1.5   # seconds to move when no duration is spoken
TURN_AROUND_DURATION  = 1.8   # seconds to spin for ~180°
SHORT_TURN_DURATION   = 0.6   # seconds for "turn left / right" (no duration)

SAMPLE_RATE           = 16000
CHUNK                 = 8000   # bytes read per iteration at native rate


def get_mic_rate(pa: "pyaudio.PyAudio") -> int:
    """Return the default input device's native sample rate as an int."""
    try:
        idx  = pa.get_default_input_device_info()["index"]
        rate = int(pa.get_device_info_by_index(idx)["defaultSampleRate"])
        return rate
    except Exception:
        return 44100   # safe fallback


# ---------------------------------------------------------------------------
# Command parser
# ---------------------------------------------------------------------------

# Set to True when --cv is passed; controls whether moves are re-sent in a loop
_CV_MODE: bool = False

# Interval (seconds) between repeated commands to the CV firmware
_CV_RESEND_INTERVAL = 0.05


def _move_for(move_fn, duration: float) -> None:
    """
    Call move_fn() and sustain movement for `duration` seconds.

    QD001 firmware:  motors stay on after a single packet → send once, sleep.
    CV firmware:     firmware stops motors on EVERY parsed packet → must
                     re-send the command repeatedly until the time is up.
    """
    if _CV_MODE:
        end = time.monotonic() + duration
        while time.monotonic() < end:
            move_fn()
            time.sleep(_CV_RESEND_INTERVAL)
    else:
        move_fn()
        time.sleep(duration)


def _extract_duration(text: str, default: float) -> float:
    """Pull 'for N seconds' / 'for N s' out of text."""
    m = re.search(r'\bfor\s+(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s\b)', text)
    return float(m.group(1)) if m else default


# ---------------------------------------------------------------------------
# Acoustic mishearing corrections for the small Vosk model
# ---------------------------------------------------------------------------

# Unambiguous word-level substitutions
_WORD_FIXES: dict[str, str] = {
    # "straight" commonly mis-decoded as "streets" / "tweets" / "strait" / etc.
    "streets":   "straight",
    "street":    "straight",
    "tweets":    "straight",
    "tweet":     "straight",
    "straits":   "straight",
    "strait":    "straight",
    "straights": "straight",
    "stray":     "straight",
    "trade":     "straight",
    "traits":    "straight",
    "trait":     "straight",
    # "forward"
    "ford":      "forward",
    "foreword":  "forward",
    "forewords": "forward",
    # "backward"
    "backwards": "backward",
    # "right"
    "rite":      "right",
    "wright":    "right",
    "write":     "right",
    # "left"
    "laughed":   "left",
    "lifts":     "left",
    # "halt"
    "whole":     "halt",
    "hauled":    "halt",
    # "strafe"
    "draft":     "strafe",
}

# Motion keywords used for context-aware prefix fixes
_MOTION = r'(?:straight|forward|back(?:ward)?|left|right|strafe|around|stop|halt)'

# Context-aware substitutions: replace word ONLY when followed by a motion word
_CONTEXT_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bgood\b(?=\s+' + _MOTION + r')'), 'go'),
    (re.compile(r'\bwho\b(?=\s+'  + _MOTION + r')'), 'go'),
    (re.compile(r'\bgot\b(?=\s+'  + _MOTION + r')'), 'go'),
    (re.compile(r'\bgo\s+streets\b'),                 'go straight'),
    (re.compile(r'\bstrap\b(?=\s+(?:left|right))'),   'strafe'),
]


def _fix_mishearings(text: str) -> str:
    """Correct small-model acoustic mishearings before command parsing."""
    # 1. word-level fixes
    words = text.split()
    text = " ".join(_WORD_FIXES.get(w, w) for w in words)
    # 2. context-aware fixes
    for pattern, replacement in _CONTEXT_FIXES:
        text = pattern.sub(replacement, text)
    return text


def execute(car, text: str) -> str:
    """
    Parse *text* and drive the car.  Returns a human-readable description
    of what was done, or a '?' string if the command was not recognised.
    """
    t = text.lower()

    # ── exit ─────────────────────────────────────────────────────────────
    if re.search(r'\b(exit|quit|disconnect|goodbye|bye)\b', t):
        return "__EXIT__"

    # ── stop / halt ───────────────────────────────────────────────────────
    if re.search(r'\b(stop|halt|freeze|stand still)\b', t):
        car.stop()
        return "Stopped"

    # ── turn around / U-turn ─────────────────────────────────────────────
    if re.search(r'\b(turn around|u.?turn|reverse direction|about face)\b', t):
        _move_for(car.turn_left, TURN_AROUND_DURATION)
        car.stop()
        return f"Turned around (~180°, {TURN_AROUND_DURATION}s spin)"

    # ── turn / spin left ─────────────────────────────────────────────────
    if re.search(r'\b(turn left|spin left|rotate left)\b', t):
        dur = _extract_duration(t, SHORT_TURN_DURATION)
        _move_for(car.turn_left, dur)
        car.stop()
        return f"Turned left  ({dur:.1f}s)"

    # ── turn / spin right ─────────────────────────────────────────────────
    if re.search(r'\b(turn right|spin right|rotate right)\b', t):
        dur = _extract_duration(t, SHORT_TURN_DURATION)
        _move_for(car.turn_right, dur)
        car.stop()
        return f"Turned right ({dur:.1f}s)"

    # ── forward ───────────────────────────────────────────────────────────
    if re.search(r'\b(go straight|go forward|move forward|drive forward|forward|straight ahead)\b', t):
        dur = _extract_duration(t, DEFAULT_DURATION)
        _move_for(car.forward, dur)
        car.stop()
        return f"Forward      ({dur:.1f}s)"

    # ── backward ──────────────────────────────────────────────────────────
    if re.search(r'\b(go back|backward|go backward|reverse|back up|move back)\b', t):
        dur = _extract_duration(t, DEFAULT_DURATION)
        _move_for(car.backward, dur)
        car.stop()
        return f"Backward     ({dur:.1f}s)"

    # ── strafe left ───────────────────────────────────────────────────────
    if re.search(r'\b(strafe left|slide left|move left|step left|side left)\b', t):
        dur = _extract_duration(t, DEFAULT_DURATION)
        _move_for(car.strafe_left, dur)
        car.stop()
        return f"Strafe left  ({dur:.1f}s)"

    # ── strafe right ──────────────────────────────────────────────────────
    if re.search(r'\b(strafe right|slide right|move right|step right|side right)\b', t):
        dur = _extract_duration(t, DEFAULT_DURATION)
        _move_for(car.strafe_right, dur)
        car.stop()
        return f"Strafe right ({dur:.1f}s)"

    # ── set speed ─────────────────────────────────────────────────────────
    m = re.search(r'\bspeed\s+(\d+)\b', t)
    if m:
        spd = max(MIN_EFFECTIVE_SPEED, min(255, int(m.group(1))))
        car.set_speed(spd)
        return f"Speed → {spd}"

    return f"? Not understood: '{text}'"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

BANNER = """
╔═══════════════════════════════════════════════════════╗
║     ACEBOTT Voice Control  —  Offline / Listening     ║
╠═══════════════════════════════════════════════════════╣
║  go straight [for 3 seconds]  │  turn around          ║
║  turn left / right            │  go back              ║
║  strafe left / right          │  stop                 ║
║  speed 200                    │  exit                 ║
╚═══════════════════════════════════════════════════════╝
"""


def main():
    parser = argparse.ArgumentParser(description="ACEBOTT offline voice control")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--download-model", action="store_true",
        help="Download the Vosk speech model (needs internet, do once)",
    )
    parser.add_argument(
        "--cv", action="store_true",
        help="Use CV firmware (QD003 / car_firmware_cv) — re-sends movement "
             "commands in a loop since that firmware stops motors on each packet",
    )
    args = parser.parse_args()

    if args.download_model:
        download_model()
        sys.exit(0)

    global _CV_MODE
    _CV_MODE = args.cv

    # ── load offline speech model ─────────────────────────────────────────
    print("Loading speech model ...", end=" ", flush=True)
    model = load_model()
    rec   = KaldiRecognizer(model, SAMPLE_RATE)
    print("OK")

    # ── open microphone at its native rate, resample to 16 kHz ───────────
    pa       = pyaudio.PyAudio()
    mic_rate = get_mic_rate(pa)
    print(f"Microphone native rate: {mic_rate} Hz", end="")
    if mic_rate != SAMPLE_RATE:
        print(f"  (will resample -> {SAMPLE_RATE} Hz)")
    else:
        print()

    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=mic_rate,
            input=True,
            frames_per_buffer=CHUNK,
        )
    except OSError as exc:
        print(f"Microphone not found: {exc}")
        pa.terminate()
        sys.exit(1)

    _resample_state = None   # audioop resample state

    print(f"Connecting to {args.host}:{args.port} ...", end=" ", flush=True)
    car = AcebottCVCar(args.host, args.port) if args.cv else AcebottCar(args.host, args.port)
    try:
        car.connect()
    except Exception as exc:
        print(f"\nConnection failed: {exc}")
        print("Make sure you are connected to the car's WiFi network.")
        stream.stop_stream()
        stream.close()
        pa.terminate()
        sys.exit(1)

    print("Connected ✓")
    print(BANNER)
    print("Listening ... (speak clearly, Ctrl+C to quit)")
    print("Mic level and partial results will appear below:\n")

    silent_chunks  = 0
    resample_state = None

    try:
        while True:
            raw = stream.read(CHUNK, exception_on_overflow=False)

            # ── resample to 16 kHz if needed ──────────────────────────────
            if mic_rate != SAMPLE_RATE:
                raw, resample_state = audioop.ratecv(
                    raw, 2, 1, mic_rate, SAMPLE_RATE, resample_state
                )

            # ── live mic level bar ────────────────────────────────────────
            rms = audioop.rms(raw, 2)
            bar_len = min(30, rms // 100)
            bar = "#" * bar_len + "-" * (30 - bar_len)
            level_str = f"[{bar}] {rms:5d}"

            if rms < 50:
                silent_chunks += 1
                if silent_chunks == 60:   # ~5 s of total silence
                    print(
                        "\n[WARNING] No audio detected from microphone.\n"
                        "  Check that your mic is not muted and is set as the\n"
                        "  default recording device in Windows Sound settings.\n"
                    )
            else:
                silent_chunks = 0

            if rec.AcceptWaveform(raw):
                # ── full phrase recognised ─────────────────────────────────
                raw_text = json.loads(rec.Result()).get("text", "").strip()
                if not raw_text:
                    print(f"\r  {level_str}  (no speech)", end="", flush=True)
                    continue

                text = _fix_mishearings(raw_text)
                if text != raw_text:
                    print(f'\nHeard: "{raw_text}"  →  corrected: "{text}"')
                else:
                    print(f'\nHeard: "{text}"')
                result = execute(car, text)
                if result == "__EXIT__":
                    print("  -> Exiting ...")
                    break
                print(f"  -> {result}\n")
            else:
                # ── partial — show recognised words so far ─────────────────
                partial = json.loads(rec.PartialResult()).get("partial", "")
                display = f"  {partial:<40}" if partial else "  (listening...)"
                print(f"\r  {level_str}  {display}", end="", flush=True)

    except KeyboardInterrupt:
        print("\n(Ctrl+C — stopping)")
    finally:
        car.stop()
        car.disconnect()
        stream.stop_stream()
        stream.close()
        pa.terminate()
        print("Disconnected. Bye!")


if __name__ == "__main__":
    main()
