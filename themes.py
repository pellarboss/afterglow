"""
Colour themes that rotate the light through a palette.

Calm themes are warm-first (no blue) and change slowly with long fades, so
the change is felt more than noticed. Energetic themes are brighter, more
saturated and change faster. Nothing strobes: the fastest is every 8 s.

Each colour has its own brightness. The menu's brightness slider scales the
whole theme up or down. Focus uses cooler whites by day and warm whites after
sunset. Fireplace picks colours at random with small brightness changes, so
it flickers.
"""

from __future__ import annotations

import asyncio
import colorsys
import logging
import random
import time
from dataclasses import dataclass

import sunset_auto

log = logging.getLogger("themes")

# Approximate on-screen colour for each white, for the menu and widget.
KELVIN_HEX = {
    2000: "#FF890E", 2200: "#FF932C", 2700: "#FFA957", 3000: "#FFB46B", 3200: "#FFBB78",
    4000: "#FFD1A3", 4500: "#FFDBBA", 5000: "#FFE4CE", 6500: "#FFF9FD",
}


@dataclass(frozen=True)
class Colour:
    name: str
    hex: str
    brightness: int  # percent
    hue: float | None = None  # 0-360
    sat: float | None = None  # 0-100
    mireds: int | None = None  # white colour temperature
    evening: bool | None = None  # Focus only: True = after sunset, False = daytime


def C(name: str, spec: str, brightness: int, evening: bool | None = None) -> Colour:
    if spec.upper().endswith("K"):
        k = int(spec[:-1])
        return Colour(name, KELVIN_HEX[k], brightness, mireds=round(1_000_000 / k), evening=evening)
    r, g, b = (int(spec[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return Colour(name, spec, brightness, hue=round(h * 360, 1), sat=round(s * 100, 1), evening=evening)


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    group: str  # "Calm" or "Energetic"
    interval_s: float
    fade_ms: int
    colours: tuple[Colour, ...]
    flicker: bool = False
    time_aware: bool = False
    blue_rich: bool = False


_THEMES = [
    # --- Calm: warm-first, slow ---------------------------------------------
    Theme("jazz", "Jazz Bar at Night", "Calm", 45, 8000, (
        C("Whisky amber", "#E08A2E", 45), C("Candlelight", "2200K", 35),
        C("Burgundy velvet", "#8E1B3A", 30), C("Brass", "#D4A017", 40),
        C("Ember red", "#A8240F", 25), C("Cognac", "#9A4E1C", 35))),
    Theme("bangkok", "Bangkok Opium Den", "Calm", 60, 10000, (
        C("Red lacquer", "#A3121F", 35), C("Lantern orange", "#E8641B", 40),
        C("Saffron", "#F4B400", 35), C("Rosewood", "#7A2E2E", 25),
        C("Gold leaf", "#C9A227", 30), C("Teak glow", "#8B4A1E", 30))),
    Theme("relax", "Relax", "Calm", 90, 15000, (
        C("Sunset peach", "#FFB38A", 45), C("Terracotta rose", "#E3866F", 40),
        C("Apricot", "#F6A96B", 40), C("Warm white", "2700K", 45),
        C("Honey", "#F2A541", 40), C("Candlelight", "2200K", 35))),
    Theme("focus", "Focus", "Calm", 300, 30000, (
        C("Daylight", "5000K", 100, evening=False), C("Cool white", "4500K", 100, evening=False),
        C("Neutral white", "4000K", 95, evening=False),
        C("Evening white", "3200K", 80, evening=True), C("Soft white", "3000K", 80, evening=True),
        C("Warm white", "2700K", 75, evening=True)), time_aware=True),
    Theme("fireplace", "Fireplace", "Calm", 8, 3000, (
        C("Ember", "#B22A0E", 30), C("Flame", "#E8590C", 45), C("Glow", "#F59E0B", 40),
        C("Deep log", "#8B1A0A", 25), C("Candle", "2000K", 35)), flicker=True),
    Theme("marrakech", "Marrakech Dusk", "Calm", 60, 10000, (
        C("Terracotta", "#C2562F", 40), C("Saffron spice", "#E9A23B", 40),
        C("Rose clay", "#C97064", 35), C("Brass lantern", "#B8862B", 35),
        C("Paprika", "#9E2B1E", 30))),
    Theme("kyoto", "Kyoto Lanterns", "Calm", 60, 12000, (
        C("Torii vermilion", "#E34234", 40), C("Paper lantern", "#FFB347", 45),
        C("Cedar", "#8B5A2B", 30), C("Sake gold", "#E6C068", 40),
        C("Maple red", "#C1272D", 35))),
    # --- Energetic: bright, faster ------------------------------------------
    Theme("tokyo", "Tokyo Neon", "Energetic", 15, 1500, (
        C("Shibuya pink", "#FF2E88", 90), C("Electric cyan", "#00E5FF", 85),
        C("Ultraviolet", "#7B2CFF", 80), C("Acid lime", "#B6FF00", 75),
        C("Kabukicho red", "#FF1E3C", 85), C("Cobalt", "#1F4BFF", 80)), blue_rich=True),
    Theme("havana", "Havana Nights", "Energetic", 15, 1500, (
        C("Salsa red", "#E8112D", 85), C("Rum gold", "#E6A817", 85),
        C("Flamingo pink", "#FF5E8A", 80), C("Cigar ember", "#D2471C", 75),
        C("Sunset orange", "#FF7B29", 85), C("Papaya", "#FF9F45", 85))),
    Theme("rio", "Rio Carnival", "Energetic", 12, 1000, (
        C("Samba yellow", "#FFD000", 95), C("Carnival red", "#F2142A", 90),
        C("Tropical orange", "#FF8C00", 95), C("Feather magenta", "#E6198A", 85),
        C("Parrot green", "#4CCB2E", 80), C("Mango", "#FFB000", 90))),
    Theme("synthwave", "Synthwave Miami", "Energetic", 20, 2000, (
        C("Hot pink", "#FF3FA4", 90), C("Sunset orange", "#FF7A1A", 85),
        C("Laser violet", "#9B30FF", 80), C("Pool cyan", "#00D4E6", 80),
        C("Magenta", "#E0218A", 85), C("Palm gold", "#FFC233", 85)), blue_rich=True),
    Theme("berlin", "Berlin Warehouse", "Energetic", 8, 500, (
        C("Laser red", "#FF0A1E", 100), C("UV purple", "#6A0DFF", 85),
        C("Flash white", "6500K", 100), C("Acid green", "#39FF14", 85),
        C("Cobalt", "#0040FF", 85), C("Siren amber", "#FFA000", 95)), blue_rich=True),
]
THEMES: dict[str, Theme] = {t.key: t for t in _THEMES}
GROUPS = ["Calm", "Energetic"]


def themes_in(group: str) -> list[Theme]:
    return [t for t in _THEMES if t.group == group]


class ThemePlayer:
    """Rotates the light through a theme. Runs on the backend's event loop."""

    def __init__(self, backend, rng: random.Random | None = None):
        self.b = backend
        self.theme: Theme | None = None
        self.task: asyncio.Task | None = None
        self.index = -1
        self.current: Colour | None = None
        self.current_bri: int | None = None
        self.next_at = 0.0
        self.paused = False
        self._poke: asyncio.Event | None = None
        self._jump: int | None = None
        self._rescale = False
        self._was_on: bool | None = None
        self._rng = rng or random.Random()

    @property
    def active(self) -> bool:
        return self.theme is not None

    # --- control (loop thread) ---------------------------------------------
    def start(self, key: str, turn_on: bool = True):
        self.stop()
        self.theme = THEMES[key]
        self.index, self.current, self.current_bri = -1, None, None
        self._jump, self._rescale, self._was_on = None, False, None
        self._poke = asyncio.Event()
        self.task = asyncio.get_running_loop().create_task(self._run(turn_on))
        log.info("Theme started: %s", self.theme.name)

    def stop(self):
        if self.task:
            self.task.cancel()
        if self.theme:
            log.info("Theme stopped: %s", self.theme.name)
        self.task, self.theme, self.current, self.paused = None, None, None, False

    def jump(self, i: int):
        if self.theme and self._poke:
            self._jump = i
            self._poke.set()

    def rescale(self):
        if self.theme and self._poke:
            self._rescale = True
            self._poke.set()

    # --- palette / brightness ----------------------------------------------
    def palette(self) -> list[Colour]:
        t = self.theme
        if t is None:
            return []
        if not t.time_aware:
            return list(t.colours)
        evening = sunset_auto.is_evening(self.b.cfg)
        return [c for c in t.colours if c.evening is None or c.evening == evening]

    def scale(self) -> float:
        return float(self.b.cfg.get("theme_scale", 1.0))

    # --- engine --------------------------------------------------------------
    async def _run(self, turn_on: bool):
        acc = self.b.acc
        if acc is not None and (turn_on or acc.light_on):
            await self._advance(fade_ms=1000)
            self._was_on = True
        else:
            self.paused = True
            self.next_at = time.monotonic() + self.theme.interval_s
        while True:
            try:
                await asyncio.wait_for(self._poke.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
            self._poke.clear()
            acc = self.b.acc
            if acc is None:
                continue
            on = acc.light_on is True
            if self._jump is not None:
                i, self._jump = self._jump, None
                await self._advance(to=i, fade_ms=600)
                self.paused, self._was_on = False, True
                continue
            if self._rescale:
                self._rescale = False
                if on and self.current:
                    await self._apply(self.current, fade_ms=400)
                continue
            if not on:  # switched off (by hand, Siri or Mac sleep): pause
                self.paused, self._was_on = True, False
                continue
            if self.paused or self._was_on is False:  # light came back on
                self.paused, self._was_on = False, True
                await self._advance(same=True, fade_ms=0)
                continue
            if time.monotonic() >= self.next_at:
                await self._advance(fade_ms=self.theme.fade_ms)

    async def _advance(self, fade_ms: int, to: int | None = None, same: bool = False):
        pal = self.palette()
        if not pal:
            return
        if same and self.current in pal:
            self.index = pal.index(self.current)
        elif to is not None:
            self.index = to % len(pal)
        elif self.theme.flicker and len(pal) > 1:
            self.index = self._rng.choice([i for i in range(len(pal)) if i != self.index])
        else:
            self.index = (self.index + 1) % len(pal)
        await self._apply(pal[self.index], fade_ms)
        interval = self.theme.interval_s
        if self.theme.flicker:
            interval *= self._rng.uniform(0.75, 1.25)
        self.next_at = time.monotonic() + interval

    async def _apply(self, colour: Colour, fade_ms: int) -> bool:
        acc = self.b.acc
        if acc is None:
            return False
        bri = colour.brightness * self.scale()
        if self.theme and self.theme.flicker:
            bri += self._rng.uniform(-8, 8)
        bri = max(1, min(100, round(bri)))
        ok = await acc.scene(bri, hue=colour.hue, sat=colour.sat, mireds=colour.mireds,
                             transition_ms=fade_ms or None)
        if ok:
            self.current, self.current_bri = colour, bri
        return ok

    # --- for the menu and widget (main thread) -----------------------------
    def status(self) -> dict | None:
        t = self.theme
        if t is None:
            return None
        pal = self.palette()
        idx = pal.index(self.current) if self.current in pal else max(0, min(self.index, len(pal) - 1))
        cur = pal[idx] if pal else None
        return {
            "key": t.key,
            "name": t.name,
            "group": t.group,
            "colours": [(c.name, c.hex, c.brightness) for c in pal],
            "index": idx,
            "colour": (cur.name, cur.hex) if cur else ("", "#000000"),
            "brightness": self.current_bri if self.current_bri is not None else (cur.brightness if cur else 0),
            "seconds_left": max(0.0, self.next_at - time.monotonic()),
            "paused": self.paused,
            "flicker": t.flicker,
            "time_aware": t.time_aware,
            "daypart": ("evening" if sunset_auto.is_evening(self.b.cfg) else "daytime") if t.time_aware else None,
        }
