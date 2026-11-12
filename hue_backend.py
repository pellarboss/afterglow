"""
Background engine for the Afterglow menu bar app.

Runs one asyncio loop on a background thread that owns the Bluetooth
connection and the Apple Home (HomeKit) bridge, so the menu bar UI and
Apple Home share a single connection to the light.
"""

from __future__ import annotations

import asyncio
import logging
import os
import plistlib
import threading
from pathlib import Path

from pyhap.accessory_driver import AccessoryDriver

import hue_homekit as core
from spotify_sync import SpotifySync
from sunset_auto import SunsetAutomation
from themes import THEMES, ThemePlayer

log = logging.getLogger("hue-backend")

AGENT_LABEL = "local.afterglow.menubar"
OLD_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / "local.huelight.menubar.plist"
AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"
QR_FILE = core.HERE / "homekit-qr.png"

MIN_MIREDS, MAX_MIREDS = core.MIN_MIREDS, core.MAX_MIREDS


class Backend:
    def __init__(self, advertise: bool = True):
        self.cfg = core.load_config()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name="hue-loop", daemon=True)
        self.advertise = advertise
        self.driver: AccessoryDriver | None = None
        self.acc: core.HueStripAccessory | None = None
        self.homekit_ok = False
        self.scan_results: dict[str, tuple[str, int]] = {}
        self.scan_version = 0
        self.busy: str | None = None
        self._notices: list[tuple[str, str]] = []
        self._pending: dict = {}
        self._flush_scheduled = False
        self._lock = threading.Lock()
        self.spotify = SpotifySync(self)
        self.sunset = SunsetAutomation(self)
        self.themes = ThemePlayer(self)

    # --- loop plumbing -----------------------------------------------------
    def migrate_login_item(self):
        """Hue Light -> Afterglow: move an old 'Open at Login' entry to the new app."""
        if OLD_AGENT_PATH.exists():
            OLD_AGENT_PATH.unlink(missing_ok=True)
            if self.app_path():
                try:
                    self.set_login(True)
                    log.info("Moved Open at Login to Afterglow")
                except Exception:
                    log.exception("Could not move Open at Login")

    def start(self):
        self.migrate_login_item()
        self.thread.start()
        if self.configured:
            self.submit(self._start_homekit())
        if self.cfg.get("spotify_sync"):
            self.loop.call_soon_threadsafe(self.spotify.start)
        if self.cfg.get("sunset_auto"):
            self.loop.call_soon_threadsafe(self.sunset.start)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def notify(self, title: str, message: str):
        with self._lock:
            self._notices.append((title, message))

    def pop_notice(self) -> tuple[str, str] | None:
        with self._lock:
            return self._notices.pop(0) if self._notices else None

    @property
    def configured(self) -> bool:
        return bool(self.cfg.get("address"))

    # --- Apple Home bridge -------------------------------------------------
    async def _start_homekit(self):
        kwargs = {} if self.advertise else {"advertise": False}  # tests only
        driver = AccessoryDriver(
            port=core.HOMEKIT_PORT,
            persist_file=str(core.STATE_FILE),
            pincode=core.homekit_pincode(self.cfg),
            loop=self.loop,
            **kwargs,
        )
        driver.tid = threading.current_thread()  # we are on the loop thread
        acc = core.HueStripAccessory(
            driver, self.cfg.get("name", "Light Strip"), self.cfg["address"]
        )
        driver.add_accessory(acc)
        # Picking a colour with Siri / the Home app stops a running theme.
        acc.on_external_colour = lambda: self.loop.call_soon_threadsafe(self._external_colour)
        self.driver, self.acc = driver, acc
        key = self.cfg.get("theme")
        if key in THEMES and not self.themes.active:
            self.themes.start(key, turn_on=False)  # resume after a restart, without forcing it on
        try:
            await driver.async_start()
            self.homekit_ok = True
        except Exception as err:
            log.exception("Apple Home bridge failed to start")
            self.homekit_ok = False
            self.notify(
                "Apple Home bridge didn't start",
                f"{err}\n\nThe menu bar controls still work. If './start.sh run' is "
                "still running in Terminal, stop it (Ctrl-C) and reopen Afterglow.",
            )
            # Still keep the light connection alive for the menu bar controls.
            driver.aio_stop_event = asyncio.Event()
            self.loop.create_task(acc.run())

    async def _stop_homekit(self):
        driver, acc, started = self.driver, self.acc, self.homekit_ok
        self.driver = self.acc = None
        self.homekit_ok = False
        if driver is None:
            return
        try:
            if started:
                await driver.async_stop()
            else:
                if driver.aio_stop_event is not None:
                    driver.aio_stop_event.set()
                if acc:
                    await acc.stop()
        except Exception:
            log.exception("Error stopping Apple Home bridge")

    def shutdown(self, timeout: float = 5.0):
        try:
            self.submit(self._stop_homekit()).result(timeout=timeout)
        except Exception:
            pass

    # --- State for the UI (read from the main thread) ----------------------
    def snapshot(self) -> dict:
        acc, driver = self.acc, self.driver
        snap = {
            "configured": self.configured,
            "name": self.cfg.get("name", "Light"),
            "ready": acc is not None,
            "on": False,
            "brightness": 100,
            "hue": 0.0,
            "sat": 0.0,
            "ct": 366,
            "mode": "ct",
            "connected": False,
            "error": None,
            "homekit_ok": self.homekit_ok,
            "homekit_paired": False,
        }
        if acc is not None:
            snap.update(
                on=bool(acc.c_on.value),
                brightness=int(acc.c_bri.value),
                hue=float(acc.c_hue.value),
                sat=float(acc.c_sat.value),
                ct=int(acc.c_ct.value),
                mode=acc.mode,
                connected=acc.light.connected,
                error=acc.light.last_error,
            )
        if driver is not None:
            snap["homekit_paired"] = bool(driver.state.paired)
        return snap

    # --- Light control (called from the UI thread) -------------------------
    def request(self, **values):
        """Queue a change. Rapid slider/picker updates are coalesced."""
        if self.acc is None:
            log.info("Ignoring %s: no light set up", values)
            return
        with self._lock:
            p = self._pending
            if "Hue" in values or "Saturation" in values:
                p.pop("ColorTemperature", None)
            if "ColorTemperature" in values:
                p.pop("Hue", None)
                p.pop("Saturation", None)
            if "Brightness" in values and "On" not in values:
                p.pop("On", None)
            if values.get("On") is False:
                p.clear()
            p.update(values)
            if self._flush_scheduled:
                return
            self._flush_scheduled = True
        self.loop.call_soon_threadsafe(lambda: self.loop.create_task(self._flush()))

    async def _flush(self):
        await asyncio.sleep(0.08)
        with self._lock:
            values, self._pending = self._pending, {}
            self._flush_scheduled = False
        if self.acc is not None and values:
            await self.acc.control(values)

    # --- Sleep / wake (called on the main thread by macOS) -----------------
    def on_will_sleep(self):
        if self.acc is None or not self.cfg.get("off_on_sleep", True):
            return
        log.info("Mac is going to sleep: turning the light off")
        fut = self.submit(self.acc.sleep_off())
        try:
            fut.result(timeout=8)  # macOS waits for us (up to ~30 s)
        except Exception as err:
            fut.cancel()
            log.warning("Could not turn the light off before sleep: %s", err)

    def on_did_wake(self):
        acc = self.acc
        if acc is None:
            return

        async def job():
            await asyncio.sleep(3)  # give Bluetooth a moment to come back
            if self.cfg.get("on_on_wake", False):
                await acc.control({"On": True})
            acc.resync()
            if self.cfg.get("sunset_auto"):
                await asyncio.sleep(2)
                await self.sunset.tick()  # woke up after sunset? turn on now

        self.submit(job())

    # --- Themes ------------------------------------------------------------
    def set_theme(self, key: str | None):
        if key is not None and key not in THEMES:
            return
        self.set_option("theme", key)
        if key and self.cfg.get("spotify_sync"):
            self.set_spotify(False)

        def go():
            if key:
                self.themes.start(key, turn_on=True)
            else:
                self.themes.stop()

        self.loop.call_soon_threadsafe(go)

    def stop_theme(self):
        if self.cfg.get("theme"):
            self.set_theme(None)

    def _external_colour(self):
        if self.themes.active:
            log.info("Colour picked in Apple Home: stopping theme")
            self.set_option("theme", None)
            self.themes.stop()

    def theme_status(self) -> dict | None:
        return self.themes.status()

    def theme_jump(self, index: int):
        self.loop.call_soon_threadsafe(self.themes.jump, int(index))

    def theme_brightness(self, pct: float):
        """Brightness slider while a theme runs: scale the whole theme."""
        cur = self.themes.current
        base = cur.brightness if cur else 50
        scale = max(0.2, min(3.0, float(pct) / max(1, base)))
        self.set_option("theme_scale", round(scale, 3))
        self.loop.call_soon_threadsafe(self.themes.rescale)

    # --- Spotify -----------------------------------------------------------
    def set_spotify(self, enabled: bool):
        if enabled:
            self.stop_theme()
        self.set_option("spotify_sync", enabled)
        self.loop.call_soon_threadsafe(self.spotify.start if enabled else self.spotify.stop)

    def spotify_status(self) -> dict:
        sp = self.spotify
        return {"enabled": bool(self.cfg.get("spotify_sync")), "state": sp.state,
                "track": sp.track, "error": sp.error}

    # --- Sunset ------------------------------------------------------------
    def set_sunset(self, enabled: bool):
        self.set_option("sunset_auto", enabled)
        self.loop.call_soon_threadsafe(self.sunset.start if enabled else self.sunset.stop)

    def set_sunset_lead(self, minutes: int):
        self.set_option("sunset_lead_min", int(minutes))

    def sunset_status(self) -> dict:
        enabled = bool(self.cfg.get("sunset_auto"))
        try:
            text = self.sunset.status_text() if enabled else ""
        except Exception as err:
            text = f"☀︎ {err}"
        return {"enabled": enabled, "text": text, "lead": int(self.cfg.get("sunset_lead_min", 15))}

    # --- Settings ----------------------------------------------------------
    def set_option(self, key: str, value):
        self.cfg[key] = value
        core.save_config(self.cfg)

    @staticmethod
    def app_path() -> str | None:
        return os.environ.get("AFTERGLOW_APP_PATH") or os.environ.get("HUE_APP_PATH")

    @staticmethod
    def login_enabled() -> bool:
        return AGENT_PATH.exists()

    def set_login(self, enabled: bool):
        if not enabled:
            AGENT_PATH.unlink(missing_ok=True)
            return
        app = self.app_path()
        if not app:
            raise RuntimeError("Open at Login only works when running Afterglow.app")
        AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AGENT_PATH.open("wb") as f:
            plistlib.dump(
                {
                    "Label": AGENT_LABEL,
                    "ProgramArguments": ["/usr/bin/open", "-g", "-a", app],
                    "RunAtLoad": True,
                },
                f,
            )

    # --- Apple Home pairing code -------------------------------------------
    def homekit_code(self) -> tuple[str, Path | None] | None:
        if self.acc is None or self.driver is None:
            return None
        code = self.driver.state.pincode.decode()
        try:
            import pyqrcode

            pyqrcode.create(self.acc.xhm_uri()).png(str(QR_FILE), scale=12, quiet_zone=4)
            return code, QR_FILE
        except Exception:
            log.exception("Could not create QR code image")
            return code, None

    # --- Set up: scan, pair, forget ----------------------------------------
    def scan(self, seconds: int = 8):
        if self.busy:
            return
        self.busy = "Scanning for lights…"

        async def job():
            try:
                self.scan_results = await core.scan_lights(seconds)
                self.scan_version += 1
                if not self.scan_results:
                    self.notify(
                        "No Hue lights found",
                        "Make sure the light is powered on and within about 10 m, "
                        "and that Afterglow is allowed to use Bluetooth "
                        "(System Settings > Privacy & Security > Bluetooth).",
                    )
            except Exception as err:
                log.exception("Scan failed")
                self.notify("Scan failed", str(err))
            finally:
                self.busy = None

        self.submit(job())

    def pair(self, address: str, name: str):
        if self.busy:
            return
        self.busy = "Pairing…"

        async def job():
            try:
                await self._stop_homekit()  # release the current connection
                ok, message = await core.pair_light(address)
                if ok:
                    self.cfg.update(address=address, name=name)
                    core.save_config(self.cfg)
                    self.notify(
                        "Light paired",
                        f"{message}\n\nNext: choose 'Add to Apple Home…' in the menu.",
                    )
                else:
                    self.notify("Pairing didn't work", message)
                if self.configured:
                    await self._start_homekit()
            except Exception as err:
                log.exception("Pairing failed")
                self.notify("Pairing failed", str(err))
            finally:
                self.busy = None

        self.submit(job())

    def forget(self):
        async def job():
            await self._stop_homekit()
            for key in ("address", "name"):
                self.cfg.pop(key, None)
            core.save_config(self.cfg)
            core.STATE_FILE.unlink(missing_ok=True)
            self.notify(
                "Light forgotten",
                "Also remove it from the Home app on your iPhone "
                "(long-press the light > Settings > Remove Accessory).",
            )

        self.submit(job())
