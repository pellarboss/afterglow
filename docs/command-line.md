---
title: Command line
lede: Scan, pair and run the Apple Home bridge from Terminal, without the menu bar app.
---

`start.sh` sets up the Python environment on first run (and again whenever `requirements.txt` changes), then runs a command.

| Command | What it does |
|---|---|
| `./start.sh menubar` | Run the menu bar app from Terminal, with logs in the window |
| `./start.sh scan` | List Hue lights in Bluetooth range |
| `./start.sh pair <ADDRESS> [--name "Desk Light"]` | Pair with a light and save it to `config.json` |
| `./start.sh run` | Run the Apple Home bridge only, with no menu bar |
| `./start.sh setup` | Install or update dependencies, then exit |
| `./build_app.sh` | Build Afterglow.app in this folder |
| `./build_widget.sh` | Build and install the macOS widget (needs Xcode) |

Add `-v` to `scan`, `pair` or `run` for verbose logs, for example `./start.sh run -v`.

## Scan

```console
$ ./start.sh scan
Scanning for Hue Bluetooth lights for 10s ...

Found:
  01234567-89AB-CDEF-0123-456789ABCDEF   Hue lightstrip plus   (signal -58 dBm)

Next:  ./start.sh pair <ADDRESS>
```

Scans for 10 seconds by default; use `--seconds 20` for longer. On macOS, the address is a UUID that macOS assigns to the device, not a MAC address. It changes after the light is reset.

## Pair

Reset the light in the Hue app first (**Settings → Lights → your light → Reset**), then within a couple of minutes:

```console
$ ./start.sh pair 01234567-89AB-CDEF-0123-456789ABCDEF --name "Desk Light"
```

The light blinks once when it pairs. The address and name are saved to `config.json`.

## Headless bridge

```console
$ ./start.sh run
```

Runs only the Apple Home bridge, with no menu bar. It's useful on a Mac mini or other Mac that stays on. `run` is wrapped in `caffeinate -i`, so the Mac doesn't idle-sleep while it's running. Stop it with **Ctrl-C**.

It prints a QR code and the HomeKit setup code in Terminal. Add the light in the Home app with **+ → Add Accessory**, then scan the code, or choose **More options…** and type it. Keep the Terminal window open.

> Don't run `./start.sh run` and the menu bar app at the same time. The menu bar app already includes the bridge, and both would fight over the same light and HomeKit identity.

## Running the Python directly

```console
$ .venv/bin/python hue_homekit.py --help
usage: hue_homekit.py [-h] [-v] {scan,pair,run} ...
```

## Tests

The tests cover colour conversion, theme definitions and sunset maths. They don't need a light.

```console
$ .venv/bin/pip install pytest
$ .venv/bin/python -m pytest -q
```
