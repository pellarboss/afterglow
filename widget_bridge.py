"""
Feeds the Afterglow macOS widget.

The widget (built by build_widget.sh) can't talk Bluetooth or run Python, so
this writes a small state file into the widget's App Group container and asks
macOS to refresh the widget when something it shows changes.

Apple gives a widget roughly 40-70 refreshes a day, so refreshes are
rate-limited: theme / on-off changes at most every 20 s, and colour-only
changes (Spotify, manual picks) at most every 5 minutes. The colour that's
showing mid-theme is deliberately not tracked, since it changes every
8-300 s, far faster than a widget can refresh.
"""

from __future__ import annotations

import colorsys
import json
import logging
import math
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("widget-bridge")

GROUP_ROOT = Path.home() / "Library" / "Group Containers"
MAJOR_GAP = 20  # s between refreshes for theme / power changes
MINOR_GAP = 300  # s between refreshes for colour-only changes
HEARTBEAT = 300  # s: rewrite the file so the widget can tell Afterglow is running


def hs_hex(hue: float, sat: float) -> str:
    r, g, b = colorsys.hsv_to_rgb((hue % 360) / 360, max(0, min(100, sat)) / 100, 1.0)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def kelvin_hex(mireds: int) -> str:
    t = 1_000_000 / max(1, mireds) / 100
    r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = lambda v: max(0, min(255, round(v)))
    return "#%02X%02X%02X" % (c(r), c(g), c(b))


def every_text(theme_status: dict, interval_s: float) -> str:
    if theme_status.get("flicker"):
        return "flickers"
    if interval_s >= 60:
        m = interval_s / 60
        return f"every {m:g} min"
    return f"every {interval_s:g} s"


class WidgetBridge:
    def __init__(self, backend):
        self.b = backend
        self._major_key = None
        self._minor_key = None
        self._last_write = 0.0
        self._last_reload = 0.0
        self._pending: str | None = None  # "major" | "minor"

    # --- where ---------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.b.cfg.get("widget_group"))

    def state_path(self) -> Path | None:
        group = self.b.cfg.get("widget_group")
        return GROUP_ROOT / group / "state.json" if group else None

    # --- what ----------------------------------------------------------------
    def build_state(self) -> dict:
        snap = self.b.snapshot()
        st = self.b.theme_status()
        sp = self.b.spotify_status()
        reachable = bool(snap["ready"] and (snap["connected"] or not snap["error"]))
        state = {
            "updated": time.time(),
            "lightName": snap["name"],
            "configured": bool(snap["configured"]),
            "on": bool(snap["on"]),
            "reachable": reachable,
            "brightness": int(snap["brightness"]),
            "mode": "manual",
            "theme": None,
            "group": None,
            "every": None,
            "colours": [],
            "colourName": "",
        }
        if st:
            from themes import THEMES

            theme = THEMES.get(st["key"])
            state.update(
                mode="theme",
                theme=st["name"],
                group=st["group"] + (f" · {st['daypart']}" if st.get("daypart") else ""),
                every=every_text(st, theme.interval_s if theme else 60),
                colours=[{"name": n, "hex": h} for n, h, _ in st["colours"]],
                colourName="",
            )
            return state
        if snap["mode"] == "hs":
            hex_str, name = hs_hex(snap["hue"], snap["sat"]), "Colour"
        else:
            hex_str, name = kelvin_hex(snap["ct"]), f"White {round(1_000_000 / snap['ct'] / 100) * 100:,} K"
        if sp.get("enabled"):
            state["mode"] = "spotify"
            name = sp.get("track") or "Matching Spotify"
        state["colours"] = [{"name": name, "hex": hex_str}]
        state["colourName"] = name
        return state

    # --- tick (main thread, every second) -------------------------------------
    def tick(self, now: float | None = None):
        path = self.state_path()
        if path is None:
            return
        now = now or time.time()
        state = self.build_state()
        major = json.dumps({k: state[k] for k in ("configured", "on", "reachable", "mode", "theme", "group", "every", "colours")
                            if not (k == "colours" and state["mode"] != "theme")}, sort_keys=True)
        minor = json.dumps({k: state[k] for k in ("brightness", "colours", "colourName", "lightName")}, sort_keys=True)

        changed = None
        if major != self._major_key:
            changed = "major"
        elif minor != self._minor_key:
            changed = "minor"

        if changed or now - self._last_write >= HEARTBEAT:
            self._write(path, state)
            self._last_write = now
        if changed:
            first = self._major_key is None
            self._major_key, self._minor_key = major, minor
            if first or changed == "major":
                self._pending = "major"
            elif self._pending is None:
                self._pending = "minor"

        if self._pending:
            gap = MAJOR_GAP if self._pending == "major" else MINOR_GAP
            if now - self._last_reload >= gap:
                self.reload()
                self._last_reload = now
                self._pending = None

    def _write(self, path: Path, state: dict):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=1))
            os.replace(tmp, path)
        except Exception as err:
            log.warning("Could not write widget state to %s: %s", path, err)

    def reload(self):
        """Ask the widget's helper app to refresh the widget (it reloads and quits)."""
        app = self.b.cfg.get("widget_app")
        if not app or not Path(app).exists():
            return
        try:
            subprocess.Popen(["open", "-g", "-j", app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as err:
            log.warning("Could not refresh widget: %s", err)
