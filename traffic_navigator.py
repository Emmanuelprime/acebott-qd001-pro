"""
Traffic Sign Navigator
======================
Activates the QD003's traffic sign recognition mode and builds a live
visual map of the route as the car reads and executes each sign.

The car drives fully autonomously — this script monitors, visualises,
and can stop the car when a mission target is reached.

Signs supported by the firmware:
  Go_Straight, Turn_Right, Turn_Left, Turn_Around, Throughout (stop)

Before running:
  1. Connect to WiFi: "ESP32_QD003" / "12345678"
  2. Place printed traffic signs along a course
  3. Run: python traffic_navigator.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
import os
import math
import threading
import datetime
import json
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acebott_cv_car import AcebottCVCar

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG      = "#1e1e2e"
SURFACE = "#181825"
BTN     = "#313244"
BTN_ACT = "#89b4fa"
TEXT    = "#cdd6f4"
SUBTEXT = "#a6adc8"
MUTED   = "#585b70"
RED     = "#f38ba8"
GREEN   = "#a6e3a1"
YELLOW  = "#f9e2af"
BLUE    = "#89b4fa"
MAUVE   = "#cba6f7"
TEAL    = "#94e2d5"
GRID    = "#2a2a3e"

# ---------------------------------------------------------------------------
# Map constants
# ---------------------------------------------------------------------------

GRID_PX  = 64    # canvas pixels per route grid unit
MAP_W    = 512
MAP_H    = 512
ORIGIN_X = MAP_W // 2
ORIGIN_Y = MAP_H // 2

# How each sign changes heading (degrees) and steps forward (grid units)
SIGN_EFFECTS = {
    "Go_Straight": (  0, 1),
    "Turn_Right":  ( 90, 0),
    "Turn_Left":   (-90, 0),
    "Turn_Around": (180, 1),
    "Throughout":  (  0, 0),  # stop / no-entry
}

SIGN_COLOR = {
    "Go_Straight": BLUE,
    "Turn_Right":  GREEN,
    "Turn_Left":   GREEN,
    "Turn_Around": YELLOW,
    "Throughout":  RED,
}

SIGN_ICON = {
    "Go_Straight": "↑",
    "Turn_Right":  "→",
    "Turn_Left":   "←",
    "Turn_Around": "↩",
    "Throughout":  "✕",
}


# ---------------------------------------------------------------------------
# RouteMapper — tracks position/heading and redraws onto a tk.Canvas
# ---------------------------------------------------------------------------

class RouteMapper:
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.reset()

    def reset(self):
        self._x       = 0.0    # grid units from origin
        self._y       = 0.0
        self._heading = 0.0    # degrees  0=North/up  90=East  180=South
        self._path    = [(0.0, 0.0)]
        self._markers = []     # (gx, gy, sign_name)
        self.redraw()

    def apply_sign(self, sign: str):
        if sign not in SIGN_EFFECTS:
            return
        delta_h, steps = SIGN_EFFECTS[sign]
        self._heading = (self._heading + delta_h) % 360

        # Place sign marker at current position
        self._markers.append((self._x, self._y, sign))

        # Move forward if this sign causes movement
        if steps:
            rad = math.radians(self._heading)
            self._x += math.sin(rad) * steps
            self._y -= math.cos(rad) * steps   # y-axis inverted on canvas
            self._path.append((self._x, self._y))

        self.redraw()

    # ------------------------------------------------------------------

    def _to_canvas(self, gx, gy):
        return ORIGIN_X + gx * GRID_PX, ORIGIN_Y + gy * GRID_PX

    def redraw(self):
        c = self.canvas
        c.delete("all")

        # Grid lines
        visible = range(-MAP_W // GRID_PX - 1, MAP_W // GRID_PX + 2)
        for i in visible:
            x = ORIGIN_X + i * GRID_PX
            y = ORIGIN_Y + i * GRID_PX
            c.create_line(x, 0, x, MAP_H, fill=GRID, width=1)
            c.create_line(0, y, MAP_W, y, fill=GRID, width=1)

        # Origin dot
        c.create_oval(
            ORIGIN_X - 5, ORIGIN_Y - 5, ORIGIN_X + 5, ORIGIN_Y + 5,
            fill=MUTED, outline="",
        )
        c.create_text(ORIGIN_X + 8, ORIGIN_Y - 8, text="START",
                      fill=MUTED, font=("Segoe UI", 7), anchor="sw")

        # Route path
        if len(self._path) > 1:
            pts = []
            for gx, gy in self._path:
                pts.extend(self._to_canvas(gx, gy))
            c.create_line(*pts, fill=BLUE, width=3,
                          joinstyle="round", capstyle="round")

        # Sign markers
        for gx, gy, sign in self._markers:
            cx, cy = self._to_canvas(gx, gy)
            color = SIGN_COLOR.get(sign, TEXT)
            c.create_oval(cx - 12, cy - 12, cx + 12, cy + 12,
                          fill=color, outline=BG, width=2)
            c.create_text(cx, cy, text=SIGN_ICON.get(sign, "?"),
                          fill="#1e1e2e", font=("Segoe UI", 9, "bold"))

        # Current position + heading arrow
        cx, cy = self._to_canvas(self._x, self._y)
        rad    = math.radians(self._heading)
        tip_x  = cx + math.sin(rad) * 22
        tip_y  = cy - math.cos(rad) * 22
        c.create_oval(cx - 7, cy - 7, cx + 7, cy + 7,
                      fill=MAUVE, outline=BG, width=2)
        c.create_line(cx, cy, tip_x, tip_y,
                      fill=MAUVE, width=3, arrow="last",
                      arrowshape=(10, 13, 5))

        # Compass label
        dirs   = {0: "N", 45: "NE", 90: "E", 135: "SE",
                  180: "S", 225: "SW", 270: "W", 315: "NW"}
        snap_h = round(self._heading / 45) * 45 % 360
        c.create_text(MAP_W - 8, 8,
                      text=dirs.get(snap_h, f"{int(self._heading)}°"),
                      fill=MAUVE, font=("Segoe UI", 9, "bold"), anchor="ne")

    @property
    def position(self):
        return self._x, self._y

    @property
    def heading(self):
        return self._heading

    @property
    def sign_count(self):
        return len(self._markers)


# ---------------------------------------------------------------------------
# Navigator application
# ---------------------------------------------------------------------------

class NavigatorApp:
    def __init__(self, root: tk.Tk):
        self.root  = root
        self.car   = AcebottCVCar()
        self._log: deque = deque(maxlen=500)
        self._running_mission = False

        root.title("Traffic Sign Navigator — QD003")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        outer = tk.Frame(root, bg=BG)
        outer.pack(padx=10, pady=10)

        self._build_map(outer)
        self._build_panel(outer)

        # Hook tag callback
        self.car.set_tag_callback(self._on_tag)

        # Poll queue (tag callback runs on recv thread, UI updates on main)
        self._pending_tags: list = []
        self._pending_lock = threading.Lock()
        self.root.after(100, self._process_pending_tags)

    # ------------------------------------------------------------------
    # UI — map (left)
    # ------------------------------------------------------------------

    def _build_map(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="n", padx=(0, 12))

        tk.Label(left, text="Route Map", bg=BG, fg=TEAL,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self._canvas = tk.Canvas(
            left, width=MAP_W, height=MAP_H,
            bg=SURFACE, highlightthickness=1, highlightbackground=MUTED,
        )
        self._canvas.pack()
        self._mapper = RouteMapper(self._canvas)

        # Map controls
        btn_row = tk.Frame(left, bg=BG)
        btn_row.pack(fill="x", pady=(6, 0))
        self._mk_btn(btn_row, "Reset Map",   MUTED,  fg=TEXT,  cmd=self._reset_map).pack(side="left", padx=4)
        self._mk_btn(btn_row, "Export JSON", BTN,    fg=TEAL,  cmd=self._export).pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # UI — control panel (right)
    # ------------------------------------------------------------------

    def _build_panel(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=1, sticky="n")

        # ── Connection ────────────────────────────────────────────
        conn = tk.LabelFrame(right, text="  Connection  ", bg=BG, fg=BLUE,
                             font=("Segoe UI", 9, "bold"), bd=1,
                             relief="groove", labelanchor="n")
        conn.pack(fill="x", pady=(0, 8))

        row = tk.Frame(conn, bg=BG)
        row.pack(fill="x", padx=8, pady=6)
        self._conn_btn = self._mk_btn(row, "Connect", GREEN,
                                      fg="#1e1e2e",
                                      font=("Segoe UI", 10, "bold"),
                                      width=12, cmd=self._toggle_conn)
        self._conn_btn.pack(side="left")
        self._status_lbl = tk.Label(row, text="Disconnected",
                                    bg=BG, fg=RED, font=("Segoe UI", 9))
        self._status_lbl.pack(side="left", padx=10)

        # ── Mission ───────────────────────────────────────────────
        mis = tk.LabelFrame(right, text="  Mission  ", bg=BG, fg=MAUVE,
                            font=("Segoe UI", 9, "bold"), bd=1,
                            relief="groove", labelanchor="n")
        mis.pack(fill="x", pady=(0, 8))

        # Mission type
        self._mission_type = tk.StringVar(value="manual")
        for val, label in [
            ("manual",   "Manual — log only, never auto-stop"),
            ("count",    "Stop after N signs total"),
            ("sign",     "Stop when specific sign is seen"),
            ("sequence", "Stop when sign sequence is matched"),
        ]:
            tk.Radiobutton(
                mis, text=label, variable=self._mission_type, value=val,
                bg=BG, fg=TEXT, selectcolor=SURFACE,
                activebackground=BG, font=("Segoe UI", 9),
                command=self._update_mission_ui,
            ).pack(anchor="w", padx=10)

        # Mission parameters (shown/hidden based on type)
        self._mission_params = tk.Frame(mis, bg=BG)
        self._mission_params.pack(fill="x", padx=10, pady=(4, 0))

        # Count param
        self._count_frame = tk.Frame(self._mission_params, bg=BG)
        tk.Label(self._count_frame, text="Stop after",
                 bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left")
        self._stop_count = tk.IntVar(value=5)
        tk.Spinbox(self._count_frame, from_=1, to=100,
                   textvariable=self._stop_count,
                   bg=SURFACE, fg=TEXT, buttonbackground=BTN,
                   width=5, font=("Segoe UI", 9)).pack(side="left", padx=4)
        tk.Label(self._count_frame, text="signs",
                 bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left")

        # Sign param
        self._sign_frame = tk.Frame(self._mission_params, bg=BG)
        tk.Label(self._sign_frame, text="Stop on:",
                 bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left")
        self._stop_sign = tk.StringVar(value="Throughout")
        ttk.Combobox(
            self._sign_frame, textvariable=self._stop_sign,
            values=["Go_Straight", "Turn_Right", "Turn_Left",
                    "Turn_Around", "Throughout"],
            width=14, state="readonly",
        ).pack(side="left", padx=4)

        # Sequence param
        self._seq_frame = tk.Frame(self._mission_params, bg=BG)
        tk.Label(self._seq_frame, text="Sequence (comma-separated):",
                 bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(anchor="w")
        self._stop_seq = tk.StringVar(
            value="Go_Straight,Turn_Right,Throughout")
        tk.Entry(self._seq_frame, textvariable=self._stop_seq,
                 bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                 font=("Consolas", 8), relief="flat", width=28).pack(
            fill="x", pady=2)

        self._update_mission_ui()

        # Status
        status_row = tk.Frame(mis, bg=BG)
        status_row.pack(fill="x", padx=10, pady=(4, 2))
        tk.Label(status_row, text="Status:", bg=BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).pack(side="left")
        self._mission_status = tk.Label(
            status_row, text="Idle", bg=BG, fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self._mission_status.pack(side="left", padx=6)

        # Start / stop
        btn2 = tk.Frame(mis, bg=BG)
        btn2.pack(fill="x", padx=8, pady=(2, 8))
        self._start_btn = self._mk_btn(
            btn2, "▶  Start Mission", GREEN, fg="#1e1e2e",
            font=("Segoe UI", 10, "bold"), cmd=self._start_mission,
        )
        self._start_btn.pack(side="left", padx=4, ipadx=8, ipady=4)
        self._mk_btn(btn2, "■  Stop", RED, fg="#1e1e2e",
                     font=("Segoe UI", 10, "bold"),
                     cmd=self._stop_mission).pack(
            side="left", padx=4, ipadx=8, ipady=4)

        # ── Last sign ─────────────────────────────────────────────
        last = tk.LabelFrame(right, text="  Last Detected Sign  ", bg=BG,
                             fg=TEAL, font=("Segoe UI", 9, "bold"),
                             bd=1, relief="groove", labelanchor="n")
        last.pack(fill="x", pady=(0, 8))

        self._last_sign_lbl = tk.Label(
            last, text="—", bg=SURFACE, fg=MUTED,
            font=("Consolas", 22, "bold"), height=2, anchor="center",
        )
        self._last_sign_lbl.pack(fill="x", padx=8, pady=6)

        # ── Sign log ──────────────────────────────────────────────
        log_box = tk.LabelFrame(right, text="  Sign Log  ", bg=BG, fg=TEAL,
                                font=("Segoe UI", 9, "bold"), bd=1,
                                relief="groove", labelanchor="n")
        log_box.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            log_box, height=12, width=30,
            bg=SURFACE, fg=GREEN, font=("Consolas", 9),
            relief="flat", state="disabled", wrap="none",
        )
        sb = ttk.Scrollbar(log_box, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        self._log_text.pack(side="left", fill="both",
                            expand=True, padx=(6, 0), pady=(2, 4))
        sb.pack(side="right", fill="y", pady=(2, 4))

        # colour tags
        self._log_text.tag_configure("straight", foreground=BLUE)
        self._log_text.tag_configure("turn",     foreground=GREEN)
        self._log_text.tag_configure("around",   foreground=YELLOW)
        self._log_text.tag_configure("stop",     foreground=RED)
        self._log_text.tag_configure("ts",       foreground=MUTED)

        self._mk_btn(log_box, "Clear Log", MUTED, fg=SUBTEXT,
                     font=("Segoe UI", 8),
                     cmd=self._clear_log).pack(pady=(0, 4))

        # ── Raw feed (diagnostic) ────────────────────────────
        raw_box = tk.LabelFrame(right, text="  Raw Data from Car  ", bg=BG,
                                fg=YELLOW, font=("Segoe UI", 9, "bold"),
                                bd=1, relief="groove", labelanchor="n")
        raw_box.pack(fill="both", expand=True, pady=(4, 0))

        self._raw_text = tk.Text(
            raw_box, height=5, width=30,
            bg=SURFACE, fg=YELLOW, font=("Consolas", 8),
            relief="flat", state="disabled", wrap="none",
        )
        rsb = ttk.Scrollbar(raw_box, command=self._raw_text.yview)
        self._raw_text.configure(yscrollcommand=rsb.set)
        self._raw_text.pack(side="left", fill="both",
                            expand=True, padx=(6, 0), pady=(2, 4))
        rsb.pack(side="right", fill="y", pady=(2, 4))

        self._mk_btn(raw_box, "Clear", MUTED, fg=SUBTEXT,
                     font=("Segoe UI", 8),
                     cmd=lambda: self._clear_text(self._raw_text)
                     ).pack(pady=(0, 4))

        # ── Stats bar ─────────────────────────────────────────────
        stats = tk.Frame(right, bg=MUTED)
        stats.pack(fill="x", pady=(4, 0))
        self._stats_lbl = tk.Label(
            stats, text="Signs: 0   Turns: 0   Stops: 0",
            bg=MUTED, fg=TEXT, font=("Segoe UI", 8), pady=3,
        )
        self._stats_lbl.pack()

    # ------------------------------------------------------------------
    # Mission UI helpers
    # ------------------------------------------------------------------

    def _update_mission_ui(self):
        t = self._mission_type.get()
        for frame in (self._count_frame, self._sign_frame, self._seq_frame):
            frame.pack_forget()
        if t == "count":
            self._count_frame.pack(fill="x", pady=2)
        elif t == "sign":
            self._sign_frame.pack(fill="x", pady=2)
        elif t == "sequence":
            self._seq_frame.pack(fill="x", pady=2)

    def _check_mission(self, sign: str) -> bool:
        """Return True if the mission goal has been reached."""
        t = self._mission_type.get()
        if t == "manual":
            return False
        elif t == "count":
            return self._mapper.sign_count >= self._stop_count.get()
        elif t == "sign":
            return sign == self._stop_sign.get()
        elif t == "sequence":
            try:
                target = [s.strip() for s in self._stop_seq.get().split(",")
                          if s.strip()]
            except Exception:
                return False
            recent = [m[2] for m in list(self._mapper._markers)[-len(target):]]
            return recent == target
        return False

    # ------------------------------------------------------------------
    # Tag handling (called from recv thread — queued for main thread)
    # ------------------------------------------------------------------

    def _on_tag(self, tag: str):
        """Called from the recv thread — queue everything for the main thread."""
        with self._pending_lock:
            self._pending_tags.append(tag)

    def _process_pending_tags(self):
        with self._pending_lock:
            tags = list(self._pending_tags)
            self._pending_tags.clear()

        for tag in tags:
            # Always show in raw feed
            self._append_raw(tag)
            # Only handle known traffic signs for the map/mission
            if tag in SIGN_EFFECTS:
                self._handle_sign(tag)

        self.root.after(100, self._process_pending_tags)

    def _handle_sign(self, sign: str):
        if not self._running_mission:
            return

        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append((ts, sign))

        # Update map
        self._mapper.apply_sign(sign)

        # Update last-sign display
        color = SIGN_COLOR.get(sign, TEXT)
        icon  = SIGN_ICON.get(sign, "?")
        self._last_sign_lbl.config(
            text=f"{icon}  {sign}", fg=color, bg=SURFACE,
        )

        # Append to log
        tag_name = {
            "Go_Straight": "straight",
            "Turn_Right":  "turn",
            "Turn_Left":   "turn",
            "Turn_Around": "around",
            "Throughout":  "stop",
        }.get(sign, "straight")

        self._log_text.config(state="normal")
        self._log_text.insert("end", f"[", "ts")
        self._log_text.insert("end", ts,  "ts")
        self._log_text.insert("end", f"]  {icon} ", "ts")
        self._log_text.insert("end", sign + "\n", tag_name)
        self._log_text.see("end")
        self._log_text.config(state="disabled")

        # Update stats
        markers = [m[2] for m in self._mapper._markers]
        n_turns  = sum(1 for s in markers if s in ("Turn_Right", "Turn_Left"))
        n_around = sum(1 for s in markers if s == "Turn_Around")
        n_stops  = sum(1 for s in markers if s == "Throughout")
        self._stats_lbl.config(
            text=f"Signs: {len(markers)}   "
                 f"Turns: {n_turns + n_around}   "
                 f"Stops: {n_stops}"
        )

        # Mission check
        if self._check_mission(sign):
            self._mission_complete(sign)

    def _mission_complete(self, trigger_sign: str):
        self._mission_status.config(text="✓ Complete!", fg=GREEN)
        if self.car.is_connected:
            try:
                self.car.standby()
            except Exception:
                pass
        self._running_mission = False
        messagebox.showinfo(
            "Mission Complete",
            f"Goal reached!\nTriggered by: {trigger_sign}\n"
            f"Total signs: {self._mapper.sign_count}",
        )

    # ------------------------------------------------------------------
    # Mission start / stop
    # ------------------------------------------------------------------

    def _start_mission(self):
        if not self.car.is_connected:
            messagebox.showwarning("Not connected",
                                   "Connect to the car first.")
            return
        self._running_mission = True
        self._mission_status.config(text="Running…", fg=YELLOW)
        try:
            self.car.mode_traffic_identification()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._running_mission = False
            self._mission_status.config(text="Error", fg=RED)

    def _stop_mission(self):
        self._running_mission = False
        self._mission_status.config(text="Stopped", fg=MUTED)
        if self.car.is_connected:
            try:
                self.car.standby()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Map / log controls
    # ------------------------------------------------------------------

    def _reset_map(self):
        self._mapper.reset()
        self._last_sign_lbl.config(text="—", fg=MUTED, bg=SURFACE)
        self._stats_lbl.config(text="Signs: 0   Turns: 0   Stops: 0")

    def _clear_log(self):
        self._clear_text(self._log_text)

    def _clear_text(self, widget: tk.Text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.config(state="disabled")

    def _append_raw(self, text: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._raw_text.config(state="normal")
        self._raw_text.insert("end", f"[{ts}] {text}\n")
        self._raw_text.see("end")
        self._raw_text.config(state="disabled")

    def _export(self):
        data = {
            "exported_at": datetime.datetime.now().isoformat(),
            "signs": [
                {"x": round(gx, 3), "y": round(gy, 3), "sign": s}
                for gx, gy, s in self._mapper._markers
            ],
            "path": [
                {"x": round(gx, 3), "y": round(gy, 3)}
                for gx, gy in self._mapper._path
            ],
            "log": [{"time": ts, "sign": s} for ts, s in self._log],
        }
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"route_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        if path:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _toggle_conn(self):
        if self.car.is_connected:
            self._stop_mission()
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
            self.root.after(0, lambda: self._on_conn_fail(str(e)))

    def _set_status(self, connected: bool):
        if connected:
            self._conn_btn.config(state="normal",
                                  text="Disconnect", bg=RED)
            self._status_lbl.config(text="Connected  ✓", fg=GREEN)
        else:
            self._conn_btn.config(state="normal",
                                  text="Connect", bg=GREEN)
            self._status_lbl.config(text="Disconnected", fg=RED)
            self._running_mission = False
            self._mission_status.config(text="Idle", fg=MUTED)

    def _on_conn_fail(self, msg: str):
        self._conn_btn.config(state="normal", text="Connect", bg=GREEN)
        self._status_lbl.config(text="Connection failed", fg=RED)
        messagebox.showerror(
            "Connection Error",
            f"Could not reach the car.\n\n{msg}\n\n"
            "Make sure your PC is connected to 'ESP32_QD003' WiFi.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mk_btn(self, parent, text, bg, fg=TEXT, font=None,
                width=None, cmd=None):
        kw = {}
        if width:
            kw["width"] = width
        return tk.Button(
            parent, text=text, bg=bg, fg=fg,
            font=font or ("Segoe UI", 9),
            relief="flat", cursor="hand2",
            activebackground=BTN_ACT, activeforeground="#1e1e2e",
            command=cmd or (lambda: None), **kw,
        )

    def _on_close(self):
        self._stop_mission()
        if self.car.is_connected:
            self.car.disconnect()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    NavigatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
