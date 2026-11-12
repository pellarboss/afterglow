#!/usr/bin/env python3
"""
Hue Bluetooth -> Apple Home bridge (no Hue Bridge needed).

Core module shared by the command line tool and the menu bar app
(hue_menubar.py). Talks to a Bluetooth-capable Philips Hue light and
publishes it to Apple Home as a HomeKit light.

Command line usage
  python hue_homekit.py scan              # find Hue lights nearby
  python hue_homekit.py pair <ADDRESS>    # pair once, saves to config.json
  python hue_homekit.py run               # HomeKit bridge without the menu bar app
"""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import json
import logging
import signal
import sys
from pathlib import Path

from bleak import BleakClient, BleakScanner
from pyhap.accessory import Accessory
from pyhap.accessory_driver import AccessoryDriver
from pyhap.const import CATEGORY_LIGHTBULB

# --- Hue Bluetooth GATT profile -------------------------------------------
HUE_ADV_UUID = "0000fe0f-0000-1000-8000-00805f9b34fb"  # advertised by Hue lights
UUID_POWER = "932c32bd-0002-47a2-835a-a8d455b859dd"  # 1 byte: 0/1
UUID_BRIGHTNESS = "932c32bd-0003-47a2-835a-a8d455b859dd"  # 1 byte: 1..254
UUID_TEMP = "932c32bd-0004-47a2-835a-a8d455b859dd"  # uint16 LE mireds 153..500
UUID_XY = "932c32bd-0005-47a2-835a-a8d455b859dd"  # 2x uint16 LE, x/y * 0xFFFF
UUID_EFFECTS = "932c32bd-0007-47a2-835a-a8d455b859dd"  # combined commands, used for fades
MIN_MIREDS, MAX_MIREDS = 153, 500

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
STATE_FILE = HERE / "homekit.state"
HOMEKIT_PORT = 51826

PAIRING_HELP = (
    "The light refused to pair because it isn't in pairing mode.\n\n"
    "In the Hue app (Bluetooth mode): Settings > Lights > + to add the light "
    "(scan the QR code on its power supply), then Settings > Lights > the light > "
    "Reset. Then scan again within a couple of minutes. The address changes "
    "after a reset."
)

log = logging.getLogger("hue-homekit")


# --- Colour conversion (Hue's wide-gamut D65 matrix) ----------------------
def hs_to_xy(hue: float, sat: float) -> tuple[float, float]:
    r, g, b = colorsys.hsv_to_rgb(hue / 360.0, sat / 100.0, 1.0)

    def lin(c):
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = lin(r), lin(g), lin(b)
    X = r * 0.664511 + g * 0.154324 + b * 0.162028
    Y = r * 0.283881 + g * 0.668433 + b * 0.047685
    Z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = X + Y + Z
    if total == 0:
        return 0.3127, 0.3290
    return X / total, Y / total


def xy_to_hs(x: float, y: float) -> tuple[float, float]:
    if y <= 0:
        return 0.0, 0.0
    Y = 1.0
    X = x / y * Y
    Z = (1 - x - y) / y * Y
    r = X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b = X * 0.051713 - Y * 0.121364 + Z * 1.011530
    r, g, b = max(r, 0), max(g, 0), max(b, 0)
    m = max(r, g, b) or 1.0
    r, g, b = r / m, g / m, b / m

    def gam(c):
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    h, s, _ = colorsys.rgb_to_hsv(gam(r), gam(g), gam(b))
    return round(h * 360, 1), round(s * 100, 1)


# --- Config ----------------------------------------------------------------
DEFAULT_CONFIG = {"off_on_sleep": True, "on_on_wake": False}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except ValueError:
            log.warning("config.json is not valid JSON; ignoring it")
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def homekit_pincode(cfg: dict) -> bytes:
    """A stable 8-digit Apple Home setup code, created once and kept in config.json."""
    code = cfg.get("homekit_code")
    if not code:
        import secrets

        digits = f"{secrets.randbelow(10**8):08d}"
        if digits in ("00000000", "11111111", "22222222", "33333333", "44444444",
                      "55555555", "66666666", "77777777", "88888888", "99999999",
                      "12345678", "87654321"):
            digits = "31415926"
        code = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        cfg["homekit_code"] = code
        save_config(cfg)
    return code.encode()


def is_pairing_error(err: BaseException | str | None) -> bool:
    text = str(err or "").lower()
    return "insufficient encryption" in text or "insufficient authentication" in text


# --- Bluetooth light -------------------------------------------------------
class HueBleLight:
    """Keeps one Bluetooth connection to the light, reconnecting as needed."""

    def __init__(self, address: str, on_change=None):
        self.address = address
        self.on_change = on_change  # called with dict of changed state
        self.client: BleakClient | None = None
        self.last_error: str | None = None
        self._lock: asyncio.Lock | None = None  # created lazily on the running loop

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def _connect(self) -> BleakClient:
        if self.connected:
            return self.client
        log.info("Connecting to %s ...", self.address)
        device = await BleakScanner.find_device_by_address(self.address, timeout=20)
        if device is None:
            raise ConnectionError(
                "Light not found. Is it powered on and within ~10 m of this Mac?"
            )
        client = BleakClient(
            device,
            disconnected_callback=lambda _c: log.warning("Light disconnected"),
            timeout=20,
        )
        await client.connect()
        self.client = client
        for uuid in (UUID_POWER, UUID_BRIGHTNESS, UUID_TEMP, UUID_XY):
            try:
                await client.start_notify(uuid, self._notify)
            except Exception as err:  # some models lack some characteristics
                log.debug("No notifications for %s: %s", uuid, err)
        log.info("Connected")
        return client

    async def disconnect(self):
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None

    async def _with_retry(self, op, what: str, attempts: int = 3):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            for attempt in range(1, attempts + 1):
                try:
                    client = await self._connect()
                    result = await op(client)
                    self.last_error = None
                    return result
                except Exception as err:
                    self.last_error = str(err)
                    log.warning("%s failed (attempt %d/%d): %s", what, attempt, attempts, err)
                    await self.disconnect()
                    if attempt < attempts:
                        await asyncio.sleep(1.5 * attempt)
            log.error("%s gave up after %d attempts", what, attempts)
            return None

    async def _write(self, uuid: str, data: bytes, what: str, attempts: int = 3):
        await self._with_retry(
            lambda c: c.write_gatt_char(uuid, data, response=True), what, attempts
        )

    # Control
    async def set_power(self, on: bool, attempts: int = 3):
        await self._write(
            UUID_POWER, bytes([1 if on else 0]), f"power {'on' if on else 'off'}", attempts
        )

    async def set_brightness(self, level_254: int):
        level = max(1, min(254, int(level_254)))
        await self._write(UUID_BRIGHTNESS, bytes([level]), f"brightness {level}")

    async def _write_fade(self, uuid: str, data: bytes, command: str, transition_ms, what: str):
        """Write a value, fading over transition_ms if given (falls back to instant)."""
        if not transition_ms:
            await self._write(uuid, data, what)
            return
        units = max(1, min(0xFFFF, int(transition_ms) // 100))
        fx = bytes.fromhex(command) + data + bytes.fromhex("0502") + units.to_bytes(2, "little")

        async def op(c: BleakClient):
            if c.services.get_characteristic(UUID_EFFECTS) is None:
                await c.write_gatt_char(uuid, data, response=True)
            else:
                await c.write_gatt_char(UUID_EFFECTS, fx, response=True)

        await self._with_retry(op, f"{what} (fade {units * 100} ms)")

    async def set_mireds(self, mireds: int, transition_ms: int | None = None):
        m = max(MIN_MIREDS, min(MAX_MIREDS, int(mireds)))
        await self._write_fade(UUID_TEMP, m.to_bytes(2, "little"), "0302", transition_ms, f"colour temp {m}")

    async def set_xy(self, x: float, y: float, transition_ms: int | None = None):
        data = int(x * 0xFFFF).to_bytes(2, "little") + int(y * 0xFFFF).to_bytes(2, "little")
        await self._write_fade(UUID_XY, data, "0404", transition_ms, f"colour xy ({x:.3f}, {y:.3f})")

    async def set_scene(self, brightness_254: int, xy: tuple[float, float] | None = None,
                        mireds: int | None = None, transition_ms: int | None = None):
        """Power on + brightness + colour (+ fade) in one command, so they change together."""
        bri = max(1, min(254, int(brightness_254)))
        xy_data = None
        if xy is not None:
            xy_data = int(xy[0] * 0xFFFF).to_bytes(2, "little") + int(xy[1] * 0xFFFF).to_bytes(2, "little")
        ct_data = None
        if xy is None and mireds is not None:
            ct_data = max(MIN_MIREDS, min(MAX_MIREDS, int(mireds))).to_bytes(2, "little")
        buf = bytes.fromhex("0101") + b"\x01" + bytes.fromhex("0201") + bytes([bri])
        if xy_data:
            buf += bytes.fromhex("0404") + xy_data
        elif ct_data:
            buf += bytes.fromhex("0302") + ct_data
        if transition_ms:
            units = max(1, min(0xFFFF, int(transition_ms) // 100))
            buf += bytes.fromhex("0502") + units.to_bytes(2, "little")

        async def op(c: BleakClient):
            if c.services.get_characteristic(UUID_EFFECTS) is not None:
                await c.write_gatt_char(UUID_EFFECTS, buf, response=True)
                return
            # Older firmware: separate writes, no fade.
            if xy_data:
                await c.write_gatt_char(UUID_XY, xy_data, response=True)
            elif ct_data:
                await c.write_gatt_char(UUID_TEMP, ct_data, response=True)
            await c.write_gatt_char(UUID_BRIGHTNESS, bytes([bri]), response=True)
            await c.write_gatt_char(UUID_POWER, b"\x01", response=True)

        await self._with_retry(op, f"scene (brightness {bri}, fade {transition_ms or 0} ms)")

    # State
    async def read_state(self, attempts: int = 3) -> dict | None:
        async def op(c: BleakClient):
            state = {}
            state["on"] = bool((await c.read_gatt_char(UUID_POWER))[0])
            state["brightness"] = (await c.read_gatt_char(UUID_BRIGHTNESS))[0]
            for uuid in (UUID_TEMP, UUID_XY):
                try:
                    state.update(self._decode(uuid, await c.read_gatt_char(uuid)))
                except Exception:
                    pass
            return state

        return await self._with_retry(op, "read state", attempts)

    @staticmethod
    def _decode(uuid: str, data: bytes) -> dict:
        uuid = uuid.lower()
        if uuid == UUID_POWER:
            return {"on": bool(data[0])}
        if uuid == UUID_BRIGHTNESS:
            return {"brightness": data[0]}
        if uuid == UUID_TEMP and len(data) >= 2:
            m = int.from_bytes(data[:2], "little")
            return {"mireds": m} if MIN_MIREDS <= m <= MAX_MIREDS else {}
        if uuid == UUID_XY and len(data) >= 4:
            x = int.from_bytes(data[0:2], "little") / 0xFFFF
            y = int.from_bytes(data[2:4], "little") / 0xFFFF
            return {"xy": (x, y)}
        return {}

    def _notify(self, sender, data: bytearray):
        uuid = getattr(sender, "uuid", str(sender))
        change = self._decode(uuid, bytes(data))
        if change and self.on_change:
            self.on_change(change)


# --- Scanning and pairing (shared by CLI and menu bar app) -----------------
async def scan_lights(seconds: int = 10) -> dict[str, tuple[str, int]]:
    """Returns {address: (name, rssi)} for Hue Bluetooth lights nearby."""
    found: dict[str, tuple[str, int]] = {}

    def cb(device, adv):
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        if HUE_ADV_UUID in uuids:
            found[device.address] = (device.name or adv.local_name or "Hue light", adv.rssi)

    async with BleakScanner(cb):
        await asyncio.sleep(seconds)
    return found


async def pair_light(address: str) -> tuple[bool, str]:
    """Connects (triggering macOS pairing) and blinks the light. Returns (ok, message)."""
    light = HueBleLight(address)
    state = await light.read_state(attempts=2)
    if state is None:
        await light.disconnect()
        if is_pairing_error(light.last_error):
            return False, PAIRING_HELP
        return False, f"Could not connect: {light.last_error}"
    await light.set_power(not state["on"])
    await asyncio.sleep(1.2)
    await light.set_power(state["on"])
    await light.disconnect()
    return True, "Paired. The light blinked to confirm."


# --- HomeKit accessory -----------------------------------------------------
class HueStripAccessory(Accessory):
    category = CATEGORY_LIGHTBULB

    def __init__(self, driver, name: str, address: str):
        super().__init__(driver, name)
        self.set_info_service(
            manufacturer="Philips Hue (Bluetooth)",
            model="Hue BLE light",
            serial_number=address.replace("-", "")[:16] or "hue-ble",
        )
        svc = self.add_preload_service(
            "Lightbulb",
            chars=["On", "Brightness", "Hue", "Saturation", "ColorTemperature"],
        )
        self.c_on = svc.configure_char("On", value=False)
        self.c_bri = svc.configure_char("Brightness", value=100)
        self.c_hue = svc.configure_char("Hue", value=0)
        self.c_sat = svc.configure_char("Saturation", value=0)
        self.c_ct = svc.configure_char(
            "ColorTemperature",
            value=366,
            properties={"minValue": MIN_MIREDS, "maxValue": MAX_MIREDS},
        )
        self.mode = "ct"  # "ct" (white) or "hs" (colour) - for the menu bar UI
        # One callback per HomeKit request, so colour + brightness arrive together.
        svc.setter_callback = self._on_homekit_set
        self.light = HueBleLight(address, on_change=self._on_light_change)
        self.light_on: bool | None = None  # last known real power state of the light
        self.on_external_colour = None  # called when Apple Home/Siri picks a colour
        self._poke: asyncio.Event | None = None

    # HomeKit -> light
    def _on_homekit_set(self, values: dict):
        log.info("HomeKit set: %s", values)
        if self.on_external_colour and any(k in values for k in ("Hue", "Saturation", "ColorTemperature")):
            self.on_external_colour()
        self.driver.add_job(self._apply, values)

    async def _apply(self, v: dict):
        if v.get("On") is False or v.get("Brightness") == 0:
            await self.light.set_power(False)
            self.light_on = False
            return
        if "Brightness" in v:
            await self.light.set_brightness(round(v["Brightness"] * 254 / 100))
        if "Hue" in v or "Saturation" in v:
            hue = v.get("Hue", self.c_hue.value)
            sat = v.get("Saturation", self.c_sat.value)
            self.mode = "hs"
            await self.light.set_xy(*hs_to_xy(hue, sat), transition_ms=v.get("Transition"))
        elif "ColorTemperature" in v:
            self.mode = "ct"
            await self.light.set_mireds(v["ColorTemperature"], transition_ms=v.get("Transition"))
        if v.get("On") is True or "Brightness" in v:
            # Skip the extra write while dragging sliders if we know it's already on.
            if not (self.light.connected and self.light_on is True):
                await self.light.set_power(True)
                self.light_on = True

    # Menu bar app -> light (must run on the driver's event loop)
    async def control(self, v: dict):
        await self._apply(v)
        if v.get("On") is False or v.get("Brightness") == 0:
            self.c_on.set_value(False)
            return
        if "Brightness" in v:
            self.c_bri.set_value(int(v["Brightness"]))
        if "Hue" in v:
            self.c_hue.set_value(v["Hue"])
        if "Saturation" in v:
            self.c_sat.set_value(v["Saturation"])
        if "ColorTemperature" in v:
            self.c_ct.set_value(int(v["ColorTemperature"]))
        if v.get("On") is True or "Brightness" in v:
            self.c_on.set_value(True)

    async def scene(self, brightness_pct: int, hue: float | None = None, sat: float | None = None,
                    mireds: int | None = None, transition_ms: int | None = None) -> bool:
        """Set brightness and colour together (used by themes). Returns True on success."""
        xy = hs_to_xy(hue, sat) if hue is not None else None
        await self.light.set_scene(round(brightness_pct * 254 / 100), xy=xy, mireds=mireds,
                                   transition_ms=transition_ms)
        if self.light.last_error:
            return False
        self.light_on = True
        self.c_on.set_value(True)
        self.c_bri.set_value(max(1, min(100, int(brightness_pct))))
        if xy is not None:
            self.mode = "hs"
            self.c_hue.set_value(round(hue, 1))
            self.c_sat.set_value(round(sat, 1))
        elif mireds is not None:
            self.mode = "ct"
            self.c_ct.set_value(max(MIN_MIREDS, min(MAX_MIREDS, int(mireds))))
        return True

    async def sleep_off(self):
        """Called just before the Mac sleeps."""
        await self.light.set_power(False, attempts=2)
        self.light_on = False
        self.c_on.set_value(False)

    def resync(self):
        """Ask the background loop to reconnect and refresh state now."""
        if self._poke:
            self._poke.set()

    # Light -> HomeKit (changes from the Hue app, a switch, etc.)
    def _on_light_change(self, s: dict):
        if "on" in s:
            self.light_on = s["on"]
            if s["on"] != self.c_on.value:
                self.c_on.set_value(s["on"])
        if "brightness" in s:
            pct = max(1, min(100, round(s["brightness"] * 100 / 254)))
            if pct != self.c_bri.value:
                self.c_bri.set_value(pct)
        if "mireds" in s:
            self.mode = "ct"
            if s["mireds"] != self.c_ct.value:
                self.c_ct.set_value(s["mireds"])
        if "xy" in s and "mireds" not in s:
            h, sat = xy_to_hs(*s["xy"])
            if (h, sat) != (self.c_hue.value, self.c_sat.value):
                self.c_hue.set_value(h)
                self.c_sat.set_value(sat)

    async def run(self):
        # Initial sync, then a keep-alive / resync every 60 s (or when poked).
        self._poke = asyncio.Event()
        while not self.driver.aio_stop_event.is_set():
            state = await self.light.read_state()
            if state:
                self._on_light_change(state)
            self._poke.clear()
            try:
                await asyncio.wait_for(self._poke.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def stop(self):
        if self._poke:
            self._poke.set()
        await self.light.disconnect()


# --- Command line ----------------------------------------------------------
async def cmd_scan(seconds: int):
    print(f"Scanning for Hue Bluetooth lights for {seconds}s ...")
    found = await scan_lights(seconds)
    if not found:
        print(
            "\nNo Hue lights found. Check:\n"
            "  - the strip has Bluetooth (BT logo on the box/controller; 2019+ models)\n"
            "  - it is powered on and within ~10 m of this Mac\n"
            "  - Terminal has Bluetooth permission (System Settings > Privacy & Security > Bluetooth)"
        )
        return
    print("\nFound:")
    for addr, (name, rssi) in sorted(found.items(), key=lambda i: -i[1][1]):
        print(f"  {addr}   {name}   (signal {rssi} dBm)")
    print("\nNext:  ./start.sh pair <ADDRESS>")


async def cmd_pair(address: str, name: str):
    print("Connecting. If macOS shows a Bluetooth pairing request, click Connect/Pair.")
    ok, message = await pair_light(address)
    print("\n" + message)
    if ok:
        cfg = load_config()
        cfg.update({"address": address, "name": name})
        save_config(cfg)
        print(f"Saved to {CONFIG_FILE.name}. Next:  ./start.sh menubar  (or ./start.sh run)")


def cmd_run():
    cfg = load_config()
    if not cfg.get("address"):
        sys.exit("No light configured yet. Run:  ./start.sh scan  then  ./start.sh pair <ADDRESS>")
    driver = AccessoryDriver(
        port=HOMEKIT_PORT, persist_file=str(STATE_FILE), pincode=homekit_pincode(cfg)
    )
    driver.add_accessory(HueStripAccessory(driver, cfg.get("name", "Light Strip"), cfg["address"]))
    signal.signal(signal.SIGTERM, driver.signal_handler)
    print(
        "\nHomeKit bridge running. To add it: iPhone Home app > + > Add Accessory >\n"
        "scan the QR code below (or 'More options...' and enter the code).\n"
        "Keep this window open and the Mac awake.\n"
    )
    driver.start()


def main():
    parser = argparse.ArgumentParser(description="Hue Bluetooth -> Apple Home bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", help="find Hue Bluetooth lights nearby")
    p_scan.add_argument("--seconds", type=int, default=10)
    p_pair = sub.add_parser("pair", help="pair with a light and save it")
    p_pair.add_argument("address")
    p_pair.add_argument("--name", default="Light Strip", help="name shown in Apple Home / used by Siri")
    sub.add_parser("run", help="run the HomeKit bridge (no menu bar)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.cmd == "scan":
        asyncio.run(cmd_scan(args.seconds))
    elif args.cmd == "pair":
        asyncio.run(cmd_pair(args.address, args.name))
    else:
        cmd_run()


if __name__ == "__main__":
    main()
