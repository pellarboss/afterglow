#!/usr/bin/env python3
"""
Afterglow: a menu bar app for a Bluetooth Philips Hue light.

- On/off, brightness, warm-to-cool white, colour presets and a colour picker
- Publishes the light to Apple Home (Siri, Control Centre, Home app)
- Turns the light off when the Mac goes to sleep
"""

from __future__ import annotations

import faulthandler
import logging
import subprocess
import sys
import time
from pathlib import Path

LOG_FILE = Path.home() / "Library" / "Logs" / "Afterglow.log"
if not (sys.stderr and sys.stderr.isatty()):
    # Launched as an app: send print output, tracebacks and hard crashes to the log file.
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2_000_000:
        LOG_FILE.replace(LOG_FILE.with_suffix(".old.log"))
    sys.stdout = sys.stderr = open(LOG_FILE, "a", buffering=1)
faulthandler.enable(sys.stderr)

import objc
import rumps
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSColor,
    NSColorPanel,
    NSColorSpace,
    NSWorkspace,
    NSWorkspaceDidWakeNotification,
    NSWorkspaceWillSleepNotification,
)
from Foundation import NSObject

import hue_homekit as core
from hue_backend import Backend
from sunset_auto import LEAD_CHOICES
from themes import GROUPS, themes_in
from desktop_widget import DesktopWidget
from widget_bridge import WidgetBridge

HERE = Path(__file__).resolve().parent
ICON_ON = str(HERE / "icons" / "bulb_on.png")
ICON_OFF = str(HERE / "icons" / "bulb_off.png")

PRESETS = [
    ("Warm White", {"ColorTemperature": 400}),
    ("Soft White", {"ColorTemperature": 333}),
    ("Neutral White", {"ColorTemperature": 250}),
    ("Daylight", {"ColorTemperature": 165}),
    None,
    ("Red", {"Hue": 0, "Saturation": 100}),
    ("Orange", {"Hue": 28, "Saturation": 100}),
    ("Yellow", {"Hue": 52, "Saturation": 100}),
    ("Green", {"Hue": 120, "Saturation": 100}),
    ("Cyan", {"Hue": 185, "Saturation": 100}),
    ("Blue", {"Hue": 235, "Saturation": 100}),
    ("Purple", {"Hue": 275, "Saturation": 100}),
    ("Pink", {"Hue": 320, "Saturation": 65}),
]

log = logging.getLogger("hue-menubar")


def warmth_to_mireds(v: float) -> int:
    """Slider 0 (warm) .. 100 (cool) -> mireds 500 .. 153."""
    return round(core.MAX_MIREDS - v * (core.MAX_MIREDS - core.MIN_MIREDS) / 100)


def mireds_to_warmth(m: int) -> float:
    return (core.MAX_MIREDS - m) * 100 / (core.MAX_MIREDS - core.MIN_MIREDS)


class CocoaBridge(NSObject):
    """Receives Cocoa callbacks (colour panel, sleep/wake) and forwards them."""

    def initWithApp_(self, app):
        self = objc.super(CocoaBridge, self).init()
        if self is None:
            return None
        self.app = app
        return self

    def colourChanged_(self, panel):
        self.app.colour_from_panel(panel)

    def willSleep_(self, _note):
        self.app.b.on_will_sleep()

    def didWake_(self, _note):
        self.app.b.on_did_wake()


class HueMenuApp(rumps.App):
    def __init__(self, backend: Backend):
        super().__init__("Afterglow", icon=ICON_OFF, template=True, quit_button=None)
        self.b = backend
        self._last_input = 0.0
        self._setting_panel = False
        self._setup_version = -1
        self._setup_configured = None

        self.status = rumps.MenuItem("Starting…")
        self.toggle = rumps.MenuItem("Turn On", callback=self.on_toggle)
        self.bri_label = rumps.MenuItem("Brightness")
        self.bri = rumps.SliderMenuItem(
            value=100, min_value=1, max_value=100, callback=self.on_brightness, dimensions=(220, 24)
        )
        self.warm_label = rumps.MenuItem("White: warm ⟷ cool")
        self.warm = rumps.SliderMenuItem(
            value=40, min_value=0, max_value=100, callback=self.on_warmth, dimensions=(220, 24)
        )
        self.colours = rumps.MenuItem("Colours")
        self.preset_items: dict[str, tuple[rumps.MenuItem, dict]] = {}
        entries = []
        for preset in PRESETS:
            if preset is None:
                entries.append(None)
                continue
            name, values = preset
            item = rumps.MenuItem(name, callback=self.on_preset)
            self.preset_items[name] = (item, values)
            entries.append(item)
        self.colours.update(entries)
        self.picker = rumps.MenuItem("Colour Picker…", callback=self.on_picker)
        self.themes_menu = rumps.MenuItem("Themes")
        self.theme_items: dict[str, rumps.MenuItem] = {}
        entries = []
        for group in GROUPS:
            if entries:
                entries.append(None)
            entries.append(rumps.MenuItem(group))  # header (no callback = greyed)
            for theme in themes_in(group):
                item = rumps.MenuItem(f"    {theme.name}", callback=self.on_theme)
                item.theme_key = theme.key
                self.theme_items[theme.key] = item
                entries.append(item)
        entries += [None, rumps.MenuItem("Stop Theme", callback=self.on_stop_theme)]
        self.themes_menu.update(entries)
        self.widget_item = rumps.MenuItem("Show Floating Panel", callback=self.on_widget)
        self.widget_top_item = rumps.MenuItem("Floating Panel Always on Top", callback=self.on_widget_top)
        self.spotify_item = rumps.MenuItem("Match Spotify Album Art", callback=self.on_spotify)
        self.spotify_now = rumps.MenuItem("♫ Waiting for Spotify…")
        self.sunset_item = rumps.MenuItem("Turn On at Sunset", callback=self.on_sunset)
        self.sunset_info = rumps.MenuItem("☀︎")
        self.sunset_timing = rumps.MenuItem("Sunset Timing")
        self.lead_items = []
        for minutes in LEAD_CHOICES:
            label = "At Sunset" if minutes == 0 else f"{minutes} Min Before Sunset"
            item = rumps.MenuItem(label, callback=self.on_sunset_lead)
            item.minutes = minutes
            self.lead_items.append(item)
        self.sunset_timing.update(self.lead_items)

        self.opt_sleep = rumps.MenuItem("Turn Off When Mac Sleeps", callback=self.on_opt_sleep)
        self.opt_wake = rumps.MenuItem("Turn On When Mac Wakes", callback=self.on_opt_wake)
        self.opt_login = rumps.MenuItem(
            "Open at Login", callback=self.on_opt_login if self.b.app_path() else None
        )
        self.home = rumps.MenuItem("Add to Apple Home…", callback=self.on_homekit)
        self.setup = rumps.MenuItem("Set Up Light")
        self.quit_item = rumps.MenuItem("Quit Afterglow", callback=self.on_quit, key="q")

        self.menu = [
            self.status,
            None,
            self.toggle,
            None,
            self.bri_label,
            self.bri,
            self.warm_label,
            self.warm,
            None,
            self.themes_menu,
            self.colours,
            self.picker,
            None,
            self.spotify_item,
            self.spotify_now,
            None,
            self.sunset_item,
            self.sunset_info,
            self.sunset_timing,
            None,
            self.opt_sleep,
            self.opt_wake,
            self.opt_login,
            None,
            self.widget_item,
            self.widget_top_item,
            None,
            self.home,
            self.setup,
            None,
            self.quit_item,
        ]

        # Cocoa hooks: colour panel target + sleep/wake notifications.
        self.bridge = CocoaBridge.alloc().initWithApp_(self)
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            self.bridge, "willSleep:", NSWorkspaceWillSleepNotification, None
        )
        nc.addObserver_selector_name_object_(
            self.bridge, "didWake:", NSWorkspaceDidWakeNotification, None
        )

        self.bridge = WidgetBridge(self.b)  # feeds the macOS widget
        self.widget = DesktopWidget(self.b)
        if self.b.cfg.get("widget_visible", False):
            self.widget.show()

        self.rebuild_setup_menu()
        self.timer = rumps.Timer(self.refresh, 1)
        self.timer.start()

    # --- helpers -----------------------------------------------------------
    def touched(self):
        self._last_input = time.monotonic()

    def power_on_if_off(self) -> dict:
        return {} if self.b.snapshot()["on"] else {"On": True}

    def require_light(self) -> bool:
        if self.b.acc is None:
            rumps.alert("No light set up yet", "Use Set Up Light > Scan for Lights first.")
            return False
        return True

    # --- controls ----------------------------------------------------------
    def on_toggle(self, _):
        if not self.require_light():
            return
        self.touched()
        self.b.request(On=not self.b.snapshot()["on"])

    def on_brightness(self, slider):
        self.touched()
        if self.b.themes.active:
            self.b.theme_brightness(slider.value)
        else:
            self.b.request(Brightness=int(round(slider.value)))

    def on_warmth(self, slider):
        self.touched()
        self.b.stop_theme()
        self.b.request(ColorTemperature=warmth_to_mireds(slider.value), **self.power_on_if_off())

    def on_preset(self, item):
        if not self.require_light():
            return
        self.touched()
        self.b.stop_theme()
        _, values = self.preset_items[item.title]
        if "ColorTemperature" in values:
            self.warm.value = mireds_to_warmth(values["ColorTemperature"])
        self.b.request(**values, **self.power_on_if_off())

    def on_picker(self, _):
        if not self.require_light():
            return
        snap = self.b.snapshot()
        panel = NSColorPanel.sharedColorPanel()
        panel.setTarget_(self.bridge)
        panel.setAction_("colourChanged:")
        panel.setContinuous_(True)
        panel.setShowsAlpha_(False)
        self._setting_panel = True
        try:
            panel.setColor_(
                NSColor.colorWithCalibratedHue_saturation_brightness_alpha_(
                    snap["hue"] / 360.0, max(snap["sat"], 1) / 100.0, 1.0, 1.0
                )
            )
        finally:
            self._setting_panel = False
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel.makeKeyAndOrderFront_(None)

    def colour_from_panel(self, panel):
        if self._setting_panel:
            return
        colour = panel.color().colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
        if colour is None:
            return
        self.touched()
        self.b.stop_theme()
        self.b.request(
            Hue=round(colour.hueComponent() * 360, 1),
            Saturation=round(colour.saturationComponent() * 100, 1),
            **self.power_on_if_off(),
        )

    def on_theme(self, item):
        if not self.require_light():
            return
        self.touched()
        self.b.set_theme(item.theme_key)

    def on_stop_theme(self, _):
        self.b.stop_theme()

    def on_widget(self, item):
        show = not bool(item.state)
        self.b.set_option("widget_visible", show)
        self.widget.show() if show else self.widget.hide()

    def on_widget_top(self, item):
        self.b.set_option("widget_on_top", not bool(item.state))
        self.widget.apply_level()

    def on_spotify(self, item):
        enable = not bool(item.state)
        if enable and not self.require_light():
            return
        self.b.set_spotify(enable)

    def on_sunset(self, item):
        enable = not bool(item.state)
        if enable and not self.require_light():
            return
        self.b.set_sunset(enable)

    def on_sunset_lead(self, item):
        self.b.set_sunset_lead(item.minutes)

    # --- options -----------------------------------------------------------
    def on_opt_sleep(self, item):
        self.b.set_option("off_on_sleep", not bool(item.state))

    def on_opt_wake(self, item):
        self.b.set_option("on_on_wake", not bool(item.state))

    def on_opt_login(self, item):
        try:
            self.b.set_login(not bool(item.state))
        except Exception as err:
            rumps.alert("Open at Login", str(err))

    # --- Apple Home ----------------------------------------------------------
    def on_homekit(self, _):
        if not self.require_light():
            return
        snap = self.b.snapshot()
        if snap["homekit_paired"]:
            rumps.alert(
                "Already in Apple Home",
                f"'{snap['name']}' is already added to Apple Home. Try: "
                f"\"Hey Siri, turn on {snap['name']}\".\n\nTo add it to a different "
                "home, remove it from the Home app first.",
            )
            return
        result = self.b.homekit_code()
        if result is None:
            rumps.alert("Apple Home", "The Apple Home bridge isn't running yet. Try again shortly.")
            return
        code, qr_path = result
        if qr_path is not None:
            subprocess.run(["open", str(qr_path)], check=False)
        rumps.alert(
            "Add to Apple Home",
            "On your iPhone: Home app > + > Add Accessory, then scan the QR code "
            "that just opened on your Mac.\n\n"
            f"Or tap 'More options…', pick '{snap['name']}' and enter code {code}.\n\n"
            "When it warns about an uncertified accessory, tap Add Anyway.",
        )

    # --- set up ------------------------------------------------------------
    def rebuild_setup_menu(self):
        self._setup_version = self.b.scan_version
        self._setup_configured = self.b.configured
        if getattr(self.setup, "_menu", None) is not None:  # rumps crashes on clear() before first add
            self.setup.clear()
        self.setup.add(rumps.MenuItem("Scan for Lights", callback=self.on_scan))
        if self.b.scan_results:
            self.setup.add(None)
            for address, (name, rssi) in sorted(
                self.b.scan_results.items(), key=lambda i: -i[1][1]
            ):
                bars = "▂▄▆█"[: max(1, min(4, (rssi + 100) // 12))]
                current = " (current)" if address == self.b.cfg.get("address") else ""
                item = rumps.MenuItem(
                    f"Pair “{name}”  {bars}  {address[:8]}…{current}", callback=self.on_pair
                )
                item.address = address
                self.setup.add(item)
        self.setup.add(None)
        self.setup.add(rumps.MenuItem("Open Log", callback=self.on_open_log))
        if self.b.configured:
            self.setup.add(rumps.MenuItem("Forget This Light…", callback=self.on_forget))

    def on_scan(self, _):
        self.b.scan()

    def on_pair(self, item):
        window = rumps.Window(
            message=(
                "Name for Apple Home and Siri.\n\n"
                "The light must be in pairing mode (freshly reset in the Hue app). "
                "If macOS asks to pair, click Connect."
            ),
            title="Pair Light",
            default_text=self.b.cfg.get("name", "Study Light"),
            ok="Pair",
            cancel="Cancel",
            dimensions=(260, 22),
        )
        response = window.run()
        if not response.clicked:
            return
        self.b.pair(item.address, response.text.strip() or "Light Strip")

    def on_forget(self, _):
        if rumps.alert(
            "Forget this light?",
            "Afterglow will stop controlling it and remove it from the Apple Home bridge.",
            ok="Forget",
            cancel="Cancel",
        ):
            self.b.forget()

    def on_open_log(self, _):
        if LOG_FILE.exists():
            subprocess.run(["open", "-a", "Console", str(LOG_FILE)], check=False)
        else:
            rumps.alert("No log file", "Logs go to Terminal when run with ./start.sh menubar.")

    def on_quit(self, _):
        self.timer.stop()
        self.b.shutdown()
        rumps.quit_application()

    # --- periodic UI refresh (main thread) ---------------------------------
    def refresh(self, _timer=None):
        notice = self.b.pop_notice()
        if notice:
            rumps.alert(*notice)

        if (
            self._setup_version != self.b.scan_version
            or self._setup_configured != self.b.configured
        ):
            self.rebuild_setup_menu()

        s = self.b.snapshot()
        icon = ICON_ON if (s["on"] and s["ready"]) else ICON_OFF
        if self.icon != icon:
            self.icon = icon

        if self.b.busy:
            status = self.b.busy
        elif not s["configured"]:
            status = "No light set up: Set Up Light > Scan"
        elif not s["ready"]:
            status = f"{s['name']}: starting…"
        elif s["connected"]:
            status = f"{s['name']}: {'On' if s['on'] else 'Off'} · {s['brightness']}%"
        elif s["error"]:
            status = f"{s['name']}: can't reach the light"
        else:
            status = f"{s['name']}: connecting…"
        if self.status.title != status:
            self.status.title = status

        toggle = "Turn Off" if s["on"] else "Turn On"
        if self.toggle.title != toggle:
            self.toggle.title = toggle

        if time.monotonic() - self._last_input > 2 and s["ready"]:
            if abs(self.bri.value - s["brightness"]) >= 1:
                self.bri.value = s["brightness"]
            if s["mode"] == "ct":
                w = mireds_to_warmth(s["ct"])
                if abs(self.warm.value - w) >= 1:
                    self.warm.value = w

        for name, (item, values) in self.preset_items.items():
            if "ColorTemperature" in values:
                match = s["mode"] == "ct" and abs(s["ct"] - values["ColorTemperature"]) <= 3
            else:
                match = (
                    s["mode"] == "hs"
                    and abs(s["hue"] - values["Hue"]) <= 2
                    and abs(s["sat"] - values["Saturation"]) <= 2
                )
            state = int(match and s["ready"] and not self.b.themes.active)
            if item.state != state:
                item.state = state

        st = self.b.theme_status()
        active_key = st["key"] if st else None
        for key, item in self.theme_items.items():
            state = int(key == active_key)
            if item.state != state:
                item.state = state
        themes_title = f"Theme: {st['name']}" if st else "Themes"
        if self.themes_menu.title != themes_title:
            self.themes_menu.title = themes_title
        self.widget_item.state = int(self.widget.visible)
        self.widget_top_item.state = int(bool(self.b.cfg.get("widget_on_top")))
        self.widget.update()
        try:
            self.bridge.tick()
        except Exception:
            log.exception("Widget bridge error")

        sp = self.b.spotify_status()
        self.spotify_item.state = int(sp["enabled"])
        if sp["state"] == "playing" and sp["track"]:
            now = f"♫ {sp['track']}"
        elif sp["state"] == "paused":
            now = f"♫ Paused: {sp['track']}" if sp["track"] else "♫ Paused"
        elif sp["state"] == "error":
            now = "♫ Can't read Spotify (see Open Log)"
        else:
            now = "♫ Waiting for Spotify to play…"
        if len(now) > 48:
            now = now[:47] + "…"
        if self.spotify_now.title != now:
            self.spotify_now.title = now
        self.spotify_now._menuitem.setHidden_(not sp["enabled"])

        ss = self.b.sunset_status()
        self.sunset_item.state = int(ss["enabled"])
        if ss["enabled"] and self.sunset_info.title != ss["text"]:
            self.sunset_info.title = ss["text"]
        self.sunset_info._menuitem.setHidden_(not ss["enabled"])
        for item in self.lead_items:
            item.state = int(item.minutes == ss["lead"])

        self.opt_sleep.state = int(self.b.cfg.get("off_on_sleep", True))
        self.opt_wake.state = int(self.b.cfg.get("on_on_wake", False))
        self.opt_login.state = int(self.b.login_enabled())

        if s["homekit_paired"]:
            home = "Apple Home: Added ✓"
        elif s["ready"] and not s["homekit_ok"]:
            home = "Apple Home: Not Running"
        else:
            home = "Add to Apple Home…"
        if self.home.title != home:
            self.home.title = home


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def crash_dialog():
    script = (
        'display alert "Afterglow stopped unexpectedly" message '
        '"Details are in ~/Library/Logs/Afterglow.log" as critical'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def main():
    setup_logging()
    log.info("Afterglow starting (Python %s)", sys.version.split()[0])
    try:
        # Menu bar only: no Dock icon.
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        backend = Backend()
        backend.start()
        HueMenuApp(backend).run()
    except Exception:
        log.exception("Afterglow crashed")
        crash_dialog()
        raise


if __name__ == "__main__":
    main()
