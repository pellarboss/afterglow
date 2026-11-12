"""
Sync the light's colour to the album cover playing in the Spotify Mac app.

Reads the current track's cover via Spotify's AppleScript support (no Spotify
login or developer keys needed), picks the most vivid colour from the cover and
fades the light to it. Mostly black-and-white covers fall back to warm white.
Works when the Spotify app on this Mac is playing, or controlling another device.
"""

from __future__ import annotations

import asyncio
import colorsys
import logging
import tempfile
from pathlib import Path

log = logging.getLogger("spotify-sync")

POLL_SECONDS = 2.0
FADE_MS = 1500
GREYSCALE_FALLBACK_MIREDS = 370  # warm white for black-and-white covers
COVER_FILE = Path(tempfile.gettempdir()) / "afterglow-cover.jpg"

# Never launches Spotify: it only asks if it's already running.
APPLESCRIPT = """
if application "Spotify" is running then
    tell application "Spotify"
        set out to (player state as text)
        try
            set out to out & tab & (artwork url of current track)
        on error
            set out to out & tab & ""
        end try
        try
            set out to out & tab & (artist of current track) & " – " & (name of current track)
        on error
            set out to out & tab & ""
        end try
        return out
    end tell
end if
return "not running"
"""

AUTOMATION_HELP = (
    "To match Spotify, Afterglow needs permission to read what Spotify is playing.\n\n"
    "Open System Settings > Privacy & Security > Automation, find Afterglow "
    "(or Terminal), and turn on Spotify."
)


async def now_playing() -> tuple[str, str, str]:
    """Returns (player_state, artwork_url, 'Artist – Track')."""
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", APPLESCRIPT,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=8)
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError("Spotify didn't respond")
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="replace").strip() or "osascript failed")
    parts = out.decode(errors="replace").rstrip("\n").split("\t")
    parts += [""] * (3 - len(parts))
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


async def download(url: str, dest: Path) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "curl", "-fsSL", "--max-time", "8", "-o", str(dest), url,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    return await proc.wait() == 0


def album_colour(path: str) -> tuple[float, float] | None:
    """Most vivid, reasonably common colour of a cover as (hue 0-360, saturation 0-100).

    Returns None for covers that are basically black, white or grey.
    """
    from PIL import Image

    img = Image.open(path).convert("RGB").resize((64, 64))
    pal = img.quantize(colors=10, method=Image.Quantize.MEDIANCUT)
    palette = pal.getpalette()
    total = 64 * 64
    best, best_score = None, 0.0
    for count, idx in pal.getcolors() or []:
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if v < 0.18 or s < 0.22:  # near-black or greyish: skip
            continue
        share = count / total
        if share < 0.02:  # tiny specks
            continue
        score = (share ** 0.5) * (s ** 1.5) * v
        if score > best_score:
            best, best_score = (h, s), score
    if best is None:
        return None
    h, s = best
    # Lights look washed out at cover-art saturation, so push it up a bit.
    return round(h * 360, 1), round(min(100.0, s * 100 * 1.15 + 10), 1)


class SpotifySync:
    """Background task (runs on the backend's event loop)."""

    def __init__(self, backend):
        self.b = backend
        self.task: asyncio.Task | None = None
        self.track: str | None = None
        self.state: str = "off"  # off | waiting | playing | paused | error
        self.error: str | None = None
        self._last_url: str | None = None
        self._warned = False

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self):  # call on the loop thread
        if not self.running:
            self._last_url = None
            self.state = "waiting"
            self.task = asyncio.get_running_loop().create_task(self._run())

    def stop(self):  # call on the loop thread
        if self.task:
            self.task.cancel()
        self.task = None
        self.track = None
        self.state = "off"

    async def _run(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                player, url, track = await now_playing()
                self.error = None
                if player == "playing":
                    self.state, self.track = "playing", track or None
                    if url and url != self._last_url and self.b.acc is not None:
                        if await download(url, COVER_FILE):
                            colour = await loop.run_in_executor(None, album_colour, str(COVER_FILE))
                            self._last_url = url
                            self.apply(colour, track)
                elif player == "paused":
                    self.state, self.track = "paused", track or None
                else:  # stopped / not running
                    self.state, self.track = "waiting", None
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if str(err) != self.error:  # log each distinct problem once
                    log.warning("Spotify sync: %s", err)
                self.state, self.error, self.track = "error", str(err), None
                text = str(err).lower()
                if ("-1743" in text or "not authorized" in text or "not allowed" in text) and not self._warned:
                    self._warned = True
                    self.b.notify("Allow Afterglow to read Spotify", AUTOMATION_HELP)
                await asyncio.sleep(POLL_SECONDS * 4)  # back off while there's a problem
            await asyncio.sleep(POLL_SECONDS)

    def apply(self, colour: tuple[float, float] | None, track: str = ""):
        if colour is None:
            log.info("Cover for %s is greyscale: warm white", track)
            self.b.request(ColorTemperature=GREYSCALE_FALLBACK_MIREDS, Transition=FADE_MS)
        else:
            log.info("Cover colour for %s: hue %.0f, saturation %.0f", track, *colour)
            self.b.request(Hue=colour[0], Saturation=colour[1], Transition=FADE_MS)
