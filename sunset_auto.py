"""
Turn the light on as it gets dark, following the local sunset time.

Sunset and twilight are calculated on the Mac (no internet needed) with the
`astral` library. From a little before sunset, the light comes on dim and warm
and brightens gradually until the end of civil twilight, when it's dark.

Rules
- Runs once per evening. If you turn the light off or change its brightness
  while it's brightening, it stops and leaves the light alone.
- If the light is already on when the time comes, it's left as is.
- If the Mac was asleep at sunset, the light comes on when the Mac wakes, as
  long as it's before the cut-off time (default 11 pm).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sun

log = logging.getLogger("sunset")

DEFAULT_LAT, DEFAULT_LON = -37.8136, 144.9631  # Melbourne; override in config.json
TICK_SECONDS = 30
START_BRIGHTNESS = 25  # % when the light first comes on
WARM_WHITE_MIREDS = 370  # about 2700 K
LEAD_CHOICES = [0, 15, 30, 45]  # minutes before sunset


def local_tz():
    """The Mac's time zone (with daylight-saving rules), e.g. Australia/Melbourne."""
    try:
        path = os.path.realpath("/etc/localtime")
        i = path.find("zoneinfo/")
        if i != -1:
            return ZoneInfo(path[i + len("zoneinfo/"):])
    except Exception:
        pass
    return dt.datetime.now().astimezone().tzinfo


def sun_times(cfg: dict, day: dt.date, tz=None) -> dict | None:
    tz = tz or local_tz()
    observer = Observer(
        latitude=float(cfg.get("latitude", DEFAULT_LAT)),
        longitude=float(cfg.get("longitude", DEFAULT_LON)),
    )
    try:
        s = sun(observer, date=day, tzinfo=tz)
    except ValueError:  # polar day/night: no sunset
        return None
    lead = dt.timedelta(minutes=int(cfg.get("sunset_lead_min", 15)))
    hh, mm = (int(x) for x in str(cfg.get("sunset_until", "23:00")).split(":"))
    start = s["sunset"] - lead
    return {
        "sunset": s["sunset"],
        "dusk": s["dusk"],  # end of civil twilight: properly dark
        "start": start,
        "full": max(s["dusk"], start + dt.timedelta(minutes=10)),
        "until": dt.datetime.combine(day, dt.time(hh, mm), tzinfo=tz),
    }


def is_evening(cfg: dict, now: dt.datetime | None = None) -> bool:
    """True between sunset and sunrise at the configured location."""
    now = now or dt.datetime.now(local_tz())
    observer = Observer(
        latitude=float(cfg.get("latitude", DEFAULT_LAT)),
        longitude=float(cfg.get("longitude", DEFAULT_LON)),
    )
    try:
        s = sun(observer, date=now.date(), tzinfo=now.tzinfo)
    except ValueError:
        return False
    return now >= s["sunset"] or now < s["sunrise"]


def fmt(t: dt.datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0").lower()


class SunsetAutomation:
    """Background task on the backend's event loop."""

    def __init__(self, backend):
        self.b = backend
        self.task: asyncio.Task | None = None
        self.phase = "idle"  # idle | ramping | done
        self._last_set: int | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self):  # loop thread
        if not self.running:
            self.task = asyncio.get_running_loop().create_task(self._run())

    def stop(self):  # loop thread
        if self.task:
            self.task.cancel()
        self.task = None
        self.phase = "idle"

    async def _run(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Sunset automation error")
            await asyncio.sleep(TICK_SECONDS)

    def target_brightness(self) -> int:
        return int(self.b.cfg.get("sunset_brightness", 100))

    def brightness_at(self, now: dt.datetime, t: dict) -> int:
        full = self.target_brightness()
        span = (t["full"] - t["start"]).total_seconds()
        frac = 1.0 if span <= 0 else min(1.0, max(0.0, (now - t["start"]).total_seconds() / span))
        return round(START_BRIGHTNESS + (full - START_BRIGHTNESS) * frac)

    async def tick(self, now: dt.datetime | None = None):
        acc = self.b.acc
        if acc is None:
            return
        now = now or dt.datetime.now(local_tz())
        today = now.date()
        t = sun_times(self.b.cfg, today, now.tzinfo)
        if t is None or now < t["start"] or now >= t["until"]:
            if self.phase == "ramping":
                self.phase = "done"
            return

        if self.b.cfg.get("sunset_last_run") != today.isoformat():
            # First moment in tonight's window.
            if acc.light_on:
                log.info("Sunset: light already on, leaving it alone")
                self.b.set_option("sunset_last_run", today.isoformat())
                self.phase = "done"
                return
            themes = getattr(self.b, "themes", None)
            if themes is not None and themes.active:
                log.info("Sunset at %s: turning the light on (theme %s)", fmt(t["sunset"]), themes.theme.name)
                await acc.control({"On": True})
                if acc.light_on and not acc.light.last_error:
                    self.b.set_option("sunset_last_run", today.isoformat())
                    self.phase = "done"
                return
            level = self.brightness_at(now, t)
            values = {"Brightness": level}
            if not self.b.cfg.get("spotify_sync"):
                values["ColorTemperature"] = WARM_WHITE_MIREDS
            log.info("Sunset at %s: turning the light on at %d%%", fmt(t["sunset"]), level)
            await acc.control(values)
            if acc.light_on and not acc.light.last_error:
                self.b.set_option("sunset_last_run", today.isoformat())
                self._last_set = level
                self.phase = "ramping" if now < t["full"] else "done"
            # else: light unreachable, try again next tick
            return

        if self.phase == "ramping":
            if not acc.light_on or abs(int(acc.c_bri.value) - (self._last_set or 0)) > 3:
                log.info("Sunset: light changed by hand, stopping the fade-up")
                self.phase = "done"
                return
            level = self.brightness_at(now, t)
            if now >= t["full"]:
                level, self.phase = self.target_brightness(), "done"
            if level != self._last_set:
                await acc.control({"Brightness": level})
                self._last_set = level

    def status_text(self, now: dt.datetime | None = None) -> str:
        now = now or dt.datetime.now(local_tz())
        t = sun_times(self.b.cfg, now.date(), now.tzinfo)
        if t is None:
            return "☀︎ No sunset today at this location"
        if self.phase == "ramping":
            return f"☀︎ Brightening until {fmt(t['full'])}"
        done_today = self.b.cfg.get("sunset_last_run") == now.date().isoformat()
        if now < t["start"] and not done_today:
            return f"☀︎ On at {fmt(t['start'])} · sunset {fmt(t['sunset'])}"
        if now < t["until"] and not done_today:
            return f"☀︎ Turning on now · sunset {fmt(t['sunset'])}"
        tomorrow = sun_times(self.b.cfg, now.date() + dt.timedelta(days=1), now.tzinfo)
        return f"☀︎ Tomorrow on at {fmt(tomorrow['start'])} · sunset {fmt(tomorrow['sunset'])}"
