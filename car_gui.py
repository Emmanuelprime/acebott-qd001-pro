"""
Car Controller GUI
==================
Tkinter-based controller for ACEBOTT QD001 Pro.

Before running:
  1. Connect to WiFi: SSID="ESP32-CAR", password="12345678"
  2. Run: python car_gui.py

Mouse  — click and hold any direction button to move, release to stop
Keys   — W/S = Fwd/Bwd · A/D = Strafe · Q/E = Spin · Space = Stop
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acebott_car import (
    AcebottCar, MIN_EFFECTIVE_SPEED,
    DIR_FORWARD, DIR_BACKWARD,
    DIR_STRAFE_LEFT, DIR_STRAFE_RIGHT,
    DIR_TOP_LEFT, DIR_TOP_RIGHT,
    DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT,
    DIR_SPIN_CCW, DIR_SPIN_CW,
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG       = "#1e1e2e"
BTN      = "#313244"
BTN_ACT  = "#89b4fa"
TEXT     = "#cdd6f4"
RED      = "#f38ba8"
GREEN    = "#a6e3a1"
MUTED    = "#585b70"


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class CarGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.car  = AcebottCar()
        self._active_direction = None   # direction currently being commanded
        self._speed = tk.IntVar(value=200)

        root.title("ACEBOTT QD001 Pro — Controller")
        root.configure(bg=BG)
        root.resizable(False, False)

        self._build_ui()
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── Connection bar ─────────────────────────────────────────
        bar = tk.Frame(self.root, bg=BG)
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        self._conn_btn = tk.Button(
            bar, text="Connect", width=12,
            bg=GREEN, fg="#1e1e2e", font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2", command=self._toggle_connection,
        )
        self._conn_btn.pack(side="left")

        self._status_lbl = tk.Label(
            bar, text="Disconnected", bg=BG,
            fg=RED, font=("Segoe UI", 10),
        )
        self._status_lbl.pack(side="left", padx=14)

        # ── Speed slider ───────────────────────────────────────────
        spd = tk.Frame(self.root, bg=BG)
        spd.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        tk.Label(spd, text="Speed", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9)).pack(side="left")

        ttk.Scale(
            spd, from_=MIN_EFFECTIVE_SPEED, to=255,
            orient="horizontal", variable=self._speed, length=200,
        ).pack(side="left", padx=8)

        self._spd_val_lbl = tk.Label(
            spd, text="200", width=4, bg=BG, fg=TEXT, font=("Segoe UI", 9),
        )
        self._spd_val_lbl.pack(side="left")
        self._speed.trace_add("write", lambda *_: self._spd_val_lbl.config(
            text=str(self._speed.get())
        ))

        # ── D-pad ──────────────────────────────────────────────────
        #
        #   [ ↖ ]  [ ↑ Fwd  ]  [ ↗ ]
        #   [ ← ]  [ ■ STOP ]  [ → ]
        #   [ ↙ ]  [ ↓ Bwd  ]  [ ↘ ]
        #
        dpad = tk.Frame(self.root, bg=BG)
        dpad.grid(row=2, column=0, padx=10, pady=4)

        layout = [
            # (label,          grid_row, grid_col, direction)
            ("↖",              0, 0, DIR_TOP_LEFT),
            ("↑  Forward",     0, 1, DIR_FORWARD),
            ("↗",              0, 2, DIR_TOP_RIGHT),
            ("←  Strafe",      1, 0, DIR_STRAFE_LEFT),
            ("→  Strafe",      1, 2, DIR_STRAFE_RIGHT),
            ("↙",              2, 0, DIR_BOTTOM_LEFT),
            ("↓  Backward",    2, 1, DIR_BACKWARD),
            ("↘",              2, 2, DIR_BOTTOM_RIGHT),
        ]

        for label, r, c, direction in layout:
            btn = self._make_btn(dpad, label, BTN)
            btn.grid(row=r, column=c, padx=4, pady=4, ipadx=10, ipady=10)
            btn.bind("<ButtonPress-1>",   lambda e, d=direction: self._start(d))
            btn.bind("<ButtonRelease-1>", lambda e: self._stop())

        stop_btn = self._make_btn(dpad, "■  STOP", RED, fg="#1e1e2e",
                                  font=("Segoe UI", 10, "bold"))
        stop_btn.grid(row=1, column=1, padx=4, pady=4, ipadx=10, ipady=10)
        stop_btn.bind("<ButtonPress-1>", lambda e: self._stop())

        # ── Spin buttons ───────────────────────────────────────────
        spin = tk.Frame(self.root, bg=BG)
        spin.grid(row=3, column=0, pady=(4, 12))

        for label, direction, col in [
            ("↺  Spin Left",  DIR_SPIN_CCW, 0),
            ("Spin Right  ↻", DIR_SPIN_CW,  1),
        ]:
            btn = self._make_btn(spin, label, BTN)
            btn.grid(row=0, column=col, padx=24, ipadx=12, ipady=8)
            btn.bind("<ButtonPress-1>",   lambda e, d=direction: self._start(d))
            btn.bind("<ButtonRelease-1>", lambda e: self._stop())

        # ── Keyboard hint bar ──────────────────────────────────────
        tk.Label(
            self.root,
            text="  W/S = Fwd/Bwd   ·   A/D = Strafe   ·   Q/E = Spin   ·   Space = Stop  ",
            bg=MUTED, fg=TEXT, font=("Segoe UI", 8), pady=5,
        ).grid(row=4, column=0, sticky="ew")

    def _make_btn(self, parent, text, bg, fg=None, font=None):
        return tk.Button(
            parent, text=text, bg=bg, fg=fg or TEXT,
            font=font or ("Segoe UI", 10),
            relief="flat", cursor="hand2",
            activebackground=BTN_ACT, activeforeground="#1e1e2e",
            disabledforeground=MUTED,
        )

    # ------------------------------------------------------------------
    # Keyboard bindings
    # ------------------------------------------------------------------

    def _bind_keys(self):
        key_map = {
            "w": DIR_FORWARD,       "Up":    DIR_FORWARD,
            "s": DIR_BACKWARD,      "Down":  DIR_BACKWARD,
            "a": DIR_STRAFE_LEFT,
            "d": DIR_STRAFE_RIGHT,
            "q": DIR_SPIN_CCW,      "Left":  DIR_SPIN_CCW,
            "e": DIR_SPIN_CW,       "Right": DIR_SPIN_CW,
        }
        for key, direction in key_map.items():
            self.root.bind(f"<KeyPress-{key}>",
                           lambda e, d=direction: self._on_key_press(d))
            self.root.bind(f"<KeyRelease-{key}>",
                           lambda e, d=direction: self._on_key_release(d))
        self.root.bind("<space>", lambda e: self._stop())

    def _on_key_press(self, direction: int):
        if self._active_direction == direction:
            return          # suppress OS key-repeat events
        self._start(direction)

    def _on_key_release(self, direction: int):
        if self._active_direction == direction:
            self._stop()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _toggle_connection(self):
        if self.car.is_connected:
            self.car.disconnect()
            self._set_status(False)
        else:
            self._conn_btn.config(state="disabled", text="Connecting…")
            self.root.update_idletasks()
            threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        try:
            self.car.connect()
            self.root.after(0, lambda: self._set_status(True))
        except Exception as e:
            self.root.after(0, lambda: self._on_connect_fail(str(e)))

    def _set_status(self, connected: bool):
        if connected:
            self._conn_btn.config(state="normal", text="Disconnect", bg=RED)
            self._status_lbl.config(text="Connected  ✓", fg=GREEN)
        else:
            self._conn_btn.config(state="normal", text="Connect",    bg=GREEN)
            self._status_lbl.config(text="Disconnected",             fg=RED)

    def _on_connect_fail(self, msg: str):
        self._conn_btn.config(state="normal", text="Connect", bg=GREEN)
        self._status_lbl.config(text="Connection failed", fg=RED)
        messagebox.showerror(
            "Connection Error",
            f"Could not reach the car.\n\n{msg}\n\n"
            "Make sure your PC is connected to the 'ESP32-CAR' WiFi.",
        )

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def _start(self, direction: int):
        if not self.car.is_connected:
            return
        self._active_direction = direction
        try:
            self.car.move(direction, self._speed.get())
        except Exception:
            self._set_status(False)

    def _stop(self):
        self._active_direction = None
        if not self.car.is_connected:
            return
        try:
            self.car.stop()
        except Exception:
            self._set_status(False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_close(self):
        if self.car.is_connected:
            self.car.disconnect()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    CarGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
