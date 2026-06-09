"""
CV Car Controller GUI
======================
Tkinter controller for the ACEBOTT QD003 (CV firmware).

Before running:
  1. Connect to WiFi: SSID="ESP32_QD003", password="12345678"
  2. Run: python cv_car_gui.py

Layout
------
  Left  — Movement d-pad + speed slider
  Right — CV modes panel + RGB LED controls + live tag feed
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
import threading
import time
import queue
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acebott_cv_car import (
    AcebottCVCar, MIN_EFFECTIVE_SPEED,
    DIR_FORWARD, DIR_BACKWARD,
    DIR_STRAFE_LEFT, DIR_STRAFE_RIGHT,
    DIR_TOP_LEFT, DIR_TOP_RIGHT,
    DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT,
    DIR_SPIN_CCW, DIR_SPIN_CW,
    COLOR_RED, COLOR_GREEN, COLOR_BLUE, COLOR_YELLOW,
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG       = "#1e1e2e"
SURFACE  = "#181825"
BTN      = "#313244"
BTN_ACT  = "#89b4fa"
TEXT     = "#cdd6f4"
SUBTEXT  = "#a6adc8"
RED      = "#f38ba8"
GREEN    = "#a6e3a1"
YELLOW   = "#f9e2af"
BLUE     = "#89b4fa"
MAUVE    = "#cba6f7"
MUTED    = "#585b70"
TEAL     = "#94e2d5"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_btn(parent, text, bg, fg=TEXT, font=None, **kw):
    return tk.Button(
        parent, text=text, bg=bg, fg=fg,
        font=font or ("Segoe UI", 10),
        relief="flat", cursor="hand2",
        activebackground=BTN_ACT, activeforeground="#1e1e2e",
        **kw,
    )

def _label(parent, text, fg=TEXT, font=None, **kw):
    return tk.Label(parent, text=text, bg=BG, fg=fg,
                    font=font or ("Segoe UI", 9), **kw)


# ---------------------------------------------------------------------------
# Main GUI
# ---------------------------------------------------------------------------

class CVCarGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.car  = AcebottCVCar()

        self._speed        = tk.IntVar(value=200)
        self._active_dir   = None
        self._color_var    = tk.IntVar(value=COLOR_RED)
        self._rgb          = {"r": tk.IntVar(value=0),
                              "g": tk.IntVar(value=0),
                              "b": tk.IntVar(value=0)}
        self._active_mode_btn = None
        self._active_mode_name = "None"

        root.title("ACEBOTT QD003 — CV Controller")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        outer = tk.Frame(root, bg=BG)
        outer.pack(padx=10, pady=10)

        self._build_left(outer)
        self._build_right(outer)
        self._bind_keys()

        # Poll for incoming tags every 100 ms
        self.root.after(100, self._poll_tags)

    # ------------------------------------------------------------------
    # Left panel — connection + movement
    # ------------------------------------------------------------------

    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="n", padx=(0, 16))

        # Connection
        conn_frame = tk.Frame(left, bg=BG)
        conn_frame.pack(fill="x", pady=(0, 8))

        self._conn_btn = _flat_btn(
            conn_frame, "Connect", GREEN, fg="#1e1e2e",
            font=("Segoe UI", 10, "bold"), width=12,
            command=self._toggle_connection,
        )
        self._conn_btn.pack(side="left")

        self._status_lbl = _label(conn_frame, "Disconnected", fg=RED)
        self._status_lbl.pack(side="left", padx=10)

        # Speed
        spd = tk.Frame(left, bg=BG)
        spd.pack(fill="x", pady=(0, 8))

        _label(spd, "Speed").pack(side="left")
        ttk.Scale(spd, from_=MIN_EFFECTIVE_SPEED, to=255,
                  orient="horizontal", variable=self._speed,
                  length=180).pack(side="left", padx=6)
        self._spd_lbl = _label(spd, "200", width=4)
        self._spd_lbl.pack(side="left")
        self._speed.trace_add("write", lambda *_: self._spd_lbl.config(
            text=str(self._speed.get())))

        # D-pad
        dpad = tk.Frame(left, bg=BG)
        dpad.pack()

        layout = [
            ("↖",           0, 0, DIR_TOP_LEFT),
            ("↑  Fwd",      0, 1, DIR_FORWARD),
            ("↗",           0, 2, DIR_TOP_RIGHT),
            ("← Strafe",    1, 0, DIR_STRAFE_LEFT),
            ("→ Strafe",    1, 2, DIR_STRAFE_RIGHT),
            ("↙",           2, 0, DIR_BOTTOM_LEFT),
            ("↓  Bwd",      2, 1, DIR_BACKWARD),
            ("↘",           2, 2, DIR_BOTTOM_RIGHT),
        ]
        for label, r, c, direction in layout:
            b = _flat_btn(dpad, label, BTN)
            b.grid(row=r, column=c, padx=3, pady=3, ipadx=8, ipady=8)
            b.bind("<ButtonPress-1>",   lambda e, d=direction: self._start(d))
            b.bind("<ButtonRelease-1>", lambda e: self._stop())

        stop_b = _flat_btn(dpad, "■  STOP", RED, fg="#1e1e2e",
                           font=("Segoe UI", 10, "bold"))
        stop_b.grid(row=1, column=1, padx=3, pady=3, ipadx=8, ipady=8)
        stop_b.bind("<ButtonPress-1>", lambda e: self._stop())

        # Spin row
        spin = tk.Frame(left, bg=BG)
        spin.pack(pady=(6, 0))
        for label, direction, col in [
            ("↺  Spin L", DIR_SPIN_CCW, 0),
            ("Spin R  ↻", DIR_SPIN_CW,  1),
        ]:
            b = _flat_btn(spin, label, BTN)
            b.grid(row=0, column=col, padx=16, ipadx=10, ipady=6)
            b.bind("<ButtonPress-1>",   lambda e, d=direction: self._start(d))
            b.bind("<ButtonRelease-1>", lambda e: self._stop())

        # Key hint
        tk.Label(
            left,
            text="W/S=Fwd/Bwd  ·  A/D=Strafe  ·  Q/E=Spin  ·  Space=Stop",
            bg=MUTED, fg=TEXT, font=("Segoe UI", 8), pady=4,
        ).pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------------
    # Right panel — CV modes + RGB + tag log
    # ------------------------------------------------------------------

    def _build_right(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=1, sticky="n")

        # ── Live Recognition Display ───────────────────────────────
        vis_box = tk.LabelFrame(
            right, text="  Live Recognition  ", bg=BG, fg=TEAL,
            font=("Segoe UI", 9, "bold"), bd=1, relief="groove", labelanchor="n",
        )
        vis_box.pack(fill="x", pady=(0, 8))

        # Active mode badge
        mode_row = tk.Frame(vis_box, bg=BG)
        mode_row.pack(fill="x", padx=8, pady=(4, 2))
        _label(mode_row, "Mode:", fg=SUBTEXT).pack(side="left")
        self._mode_badge = _label(
            mode_row, "Standby", fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self._mode_badge.pack(side="left", padx=6)

        # Big result display — shows the most recent tag prominently
        self._result_lbl = tk.Label(
            vis_box, text="—", bg=SURFACE, fg=GREEN,
            font=("Consolas", 18, "bold"),
            width=24, height=2, relief="flat", anchor="center",
        )
        self._result_lbl.pack(padx=8, pady=(2, 4), fill="x")

        # Traffic mode workflow hint — hidden until traffic mode is active
        self._traffic_hint = tk.Label(
            vis_box,
            text="① Show sign to camera  →  ② Remove sign  →  ③ Car moves after 500 ms",
            bg=SURFACE, fg=YELLOW, font=("Segoe UI", 8), pady=4, wraplength=320,
        )
        self._traffic_hint.pack(fill="x", padx=8, pady=(0, 4))
        self._traffic_hint.pack_forget()   # hidden by default

        # Traffic execution status (shown briefly after a sign is acted on)
        self._traffic_status = tk.Label(
            vis_box, text="", bg=BG, fg=YELLOW,
            font=("Segoe UI", 9, "bold"),
        )
        self._traffic_status.pack(pady=(0, 4))

        # ── CV Modes ──────────────────────────────────────────────
        cv_box = tk.LabelFrame(right, text="  CV Modes  ", bg=BG, fg=MAUVE,
                               font=("Segoe UI", 9, "bold"),
                               bd=1, relief="groove", labelanchor="n")
        cv_box.pack(fill="x", pady=(0, 8))

        # Color selection for colour tracking
        col_frame = tk.Frame(cv_box, bg=BG)
        col_frame.pack(fill="x", padx=8, pady=(4, 2))
        _label(col_frame, "Track colour:", fg=SUBTEXT).pack(side="left")
        for name, cid, fg in [
            ("Red", COLOR_RED, RED), ("Green", COLOR_GREEN, GREEN),
            ("Blue", COLOR_BLUE, BLUE), ("Yellow", COLOR_YELLOW, YELLOW),
        ]:
            tk.Radiobutton(
                col_frame, text=name, variable=self._color_var, value=cid,
                bg=BG, fg=fg, selectcolor=SURFACE,
                activebackground=BG, activeforeground=fg,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=4)

        # Mode buttons grid
        modes = [
            ("QR Code",          self._activate_qr,          MAUVE),
            ("Barcode",          self._activate_barcode,      MAUVE),
            ("Digit Recog",      self._activate_digit,        MAUVE),
            ("Color Recog",      self._activate_color_recog,  TEAL),
            ("Image Recog",      self._activate_image,        TEAL),
            ("Color Tracking",   self._activate_color_track,  YELLOW),
            ("Visual Patrol",    self._activate_visual,       GREEN),
            ("Traffic Signs",    self._activate_traffic,      GREEN),
            ("Machine Learning", self._activate_ml,           MAUVE),
            ("Face Recog",       self._activate_face,         TEAL),
            ("IR Line Follow 1", self._activate_ir1,          SUBTEXT),
            ("IR Line Follow 2", self._activate_ir2,          SUBTEXT),
        ]

        grid = tk.Frame(cv_box, bg=BG)
        grid.pack(padx=8, pady=(2, 4))
        self._mode_buttons = {}
        for i, (label, cmd, accent) in enumerate(modes):
            b = _flat_btn(grid, label, BTN, fg=accent,
                          font=("Segoe UI", 9), width=16)
            b.grid(row=i // 2, column=i % 2, padx=3, pady=2,
                   ipadx=4, ipady=4)
            b.configure(command=lambda c=cmd, btn=b, n=label: self._run_cv_mode(c, btn, n))
            self._mode_buttons[label] = b

        standby_b = _flat_btn(cv_box, "⏹  Standby / Stop CV", RED,
                              fg="#1e1e2e", font=("Segoe UI", 9, "bold"),
                              command=self._do_standby)
        standby_b.pack(fill="x", padx=8, pady=(0, 6))

        # ── RGB LED ───────────────────────────────────────────────
        rgb_box = tk.LabelFrame(right, text="  Camera RGB LED  ", bg=BG,
                                fg=MAUVE, font=("Segoe UI", 9, "bold"),
                                bd=1, relief="groove", labelanchor="n")
        rgb_box.pack(fill="x", pady=(0, 8))

        for channel, color_fg, var in [
            ("R", RED,   self._rgb["r"]),
            ("G", GREEN, self._rgb["g"]),
            ("B", BLUE,  self._rgb["b"]),
        ]:
            row = tk.Frame(rgb_box, bg=BG)
            row.pack(fill="x", padx=8, pady=2)
            _label(row, channel, fg=color_fg,
                   font=("Segoe UI", 9, "bold"), width=2).pack(side="left")
            ttk.Scale(row, from_=0, to=255, orient="horizontal",
                      variable=var, length=160,
                      command=lambda v, c=channel: self._send_rgb()
                      ).pack(side="left", padx=4)
            val_lbl = _label(row, "0", width=4)
            val_lbl.pack(side="left")
            var.trace_add("write", lambda *_, lbl=val_lbl, v=var: lbl.config(
                text=str(v.get())))

        # ── Tag Feed ──────────────────────────────────────────────
        tag_box = tk.LabelFrame(right, text="  Recognition Output  ", bg=BG,
                                fg=TEAL, font=("Segoe UI", 9, "bold"),
                                bd=1, relief="groove", labelanchor="n")
        tag_box.pack(fill="both", expand=True)

        self._tag_text = tk.Text(
            tag_box, height=8, width=32,
            bg=SURFACE, fg=GREEN, font=("Consolas", 9),
            relief="flat", state="disabled", wrap="word",
        )
        self._tag_text.pack(fill="both", expand=True, padx=6, pady=(2, 4))

        _flat_btn(tag_box, "Clear", MUTED, fg=SUBTEXT,
                  font=("Segoe UI", 8),
                  command=self._clear_tags).pack(pady=(0, 4))

    # ------------------------------------------------------------------
    # Video stream
    # ------------------------------------------------------------------

    # (Note: The ACB_CanMV camera communicates over UART to the ESP32
    # coprocessor. It has its own LCD screen and does NOT stream video
    # over WiFi. Recognition results are received as text tags via TCP.)

    # ------------------------------------------------------------------
    # CV mode actions
    # ------------------------------------------------------------------

    def _run_cv_mode(self, cmd_fn, btn: tk.Button, name: str):
        if not self.car.is_connected:
            return
        if self._active_mode_btn and self._active_mode_btn != btn:
            self._active_mode_btn.config(relief="flat")
        self._active_mode_btn  = btn
        self._active_mode_name = name
        btn.config(relief="sunken")
        self._mode_badge.config(text=name, fg=TEAL)
        try:
            cmd_fn()
        except Exception:
            self._set_status(False)

    def _activate_qr(self):          self.car.mode_qr_code()
    def _activate_barcode(self):     self.car.mode_barcode()
    def _activate_digit(self):       self.car.mode_digital_recognition()
    def _activate_color_recog(self): self.car.mode_color_recognition()
    def _activate_image(self):       self.car.mode_image_recognition()
    def _activate_color_track(self): self.car.mode_color_tracking(self._color_var.get())
    def _activate_visual(self):      self.car.mode_visual_patrol()
    def _activate_traffic(self):
        self.car.mode_traffic_identification()
        self._traffic_hint.pack(fill="x", padx=8, pady=(0, 4))
    def _activate_ml(self):          self.car.mode_machine_learning()
    def _activate_face(self):        self.car.mode_face_recognition()
    def _activate_ir1(self):         self.car.mode_line_follow_1()
    def _activate_ir2(self):         self.car.mode_line_follow_2()

    def _do_standby(self):
        if self._active_mode_btn:
            self._active_mode_btn.config(relief="flat")
            self._active_mode_btn  = None
            self._active_mode_name = "None"
        self._mode_badge.config(text="Standby", fg=MUTED)
        self._result_lbl.config(text="—", fg=MUTED)
        self._traffic_hint.pack_forget()
        self._traffic_status.config(text="")
        if not self.car.is_connected:
            return
        try:
            self.car.standby()
        except Exception:
            self._set_status(False)

    # ------------------------------------------------------------------
    # RGB
    # ------------------------------------------------------------------

    def _send_rgb(self):
        if not self.car.is_connected:
            return
        try:
            self.car.set_rgb(
                self._rgb["r"].get(),
                self._rgb["g"].get(),
                self._rgb["b"].get(),
            )
        except Exception:
            self._set_status(False)

    # ------------------------------------------------------------------
    # Tag feed
    # ------------------------------------------------------------------

    TRAFFIC_SIGNS = {"Go_Straight", "Turn_Right", "Turn_Left",
                     "Turn_Around", "Throughout"}
    TRAFFIC_ICONS = {
        "Go_Straight": "↑", "Turn_Right":  "→", "Turn_Left": "←",
        "Turn_Around": "↩", "Throughout":  "✕",
    }
    TRAFFIC_EXEC_MS = {
        # How long the firmware's delay() keeps the car moving — used to
        # show the "Executing…" status for the right duration.
        "Go_Straight":  500,
        "Turn_Right":   500,
        "Turn_Left":    500,
        "Throughout":   500,
        "Turn_Around": 4350,   # 1450 + 1600 + 1300
    }

    def _poll_tags(self):
        while True:
            tag = self.car.get_tag()
            if tag is None:
                break
            self._append_tag(tag)
            # Update the big result label with the latest tag
            self._result_lbl.config(text=tag, fg=GREEN)
            # Traffic-specific feedback
            if self._active_mode_name == "Traffic Signs" and \
                    tag in self.TRAFFIC_SIGNS:
                icon = self.TRAFFIC_ICONS.get(tag, "")
                self._traffic_status.config(
                    text=f"✓ Seen: {icon} {tag}  —  remove sign, car acts in 500 ms…",
                    fg=YELLOW,
                )
                exec_ms = self.TRAFFIC_EXEC_MS.get(tag, 500)
                # After 500 ms debounce + execution time, show "Done"
                self.root.after(
                    500 + exec_ms,
                    lambda t=tag, i=icon: self._traffic_status.config(
                        text=f"✓ Done: {i} {t}", fg=GREEN
                    ),
                )
        self.root.after(100, self._poll_tags)

    def _append_tag(self, tag: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._tag_text.config(state="normal")
        self._tag_text.insert("end", f"[{ts}] {tag}\n")
        self._tag_text.see("end")
        self._tag_text.config(state="disabled")

    def _clear_tags(self):
        self._tag_text.config(state="normal")
        self._tag_text.delete("1.0", "end")
        self._tag_text.config(state="disabled")

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
            if self._active_mode_btn:
                self._active_mode_btn.config(relief="flat")
                self._active_mode_btn  = None
                self._active_mode_name = "None"
            self._mode_badge.config(text="Standby", fg=MUTED)
            self._result_lbl.config(text="—", fg=MUTED)
            self._traffic_hint.pack_forget()
            self._traffic_status.config(text="")

    def _on_connect_fail(self, msg: str):
        self._conn_btn.config(state="normal", text="Connect", bg=GREEN)
        self._status_lbl.config(text="Connection failed", fg=RED)
        messagebox.showerror(
            "Connection Error",
            f"Could not reach the car.\n\n{msg}\n\n"
            "Make sure your PC is connected to 'ESP32_QD003' WiFi.",
        )

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def _start(self, direction: int):
        if not self.car.is_connected:
            return
        self._active_dir = direction
        try:
            self.car.move(direction, self._speed.get())
        except Exception:
            self._set_status(False)

    def _stop(self):
        self._active_dir = None
        if not self.car.is_connected:
            return
        try:
            self.car.stop()
        except Exception:
            self._set_status(False)

    # ------------------------------------------------------------------
    # Keyboard
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
        if self._active_dir == direction:
            return
        self._start(direction)

    def _on_key_release(self, direction: int):
        if self._active_dir == direction:
            self._stop()

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
    CVCarGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
