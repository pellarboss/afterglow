---
title: How it works
lede: The Mac stands in for the Hue Bridge. One background loop owns the Bluetooth connection and serves Apple Home from it.
---

## Architecture

```text
 iPhone / Siri / HomePod                       Philips Hue light
        │  HomeKit (HAP over local network)           ▲
        ▼                                             │ Bluetooth LE (GATT)
 ┌──────────────────────────── Mac ─────────────────────────────┐
 │                                                              │
 │  hue_backend.py  ── one asyncio loop on a background thread  │
 │   ├─ HueBleLight         Bluetooth driver (bleak)            │
 │   ├─ HueStripAccessory   HomeKit light (HAP-python)          │
 │   ├─ Theme engine        themes.py                           │
 │   ├─ Spotify sync        spotify_sync.py                     │
 │   └─ Sunset schedule     sunset_auto.py                      │
 │                 ▲                                            │
 │                 │ thread-safe calls                          │
 │  hue_menubar.py (rumps)        desktop_widget.py (PyObjC)    │
 │        │                       floating panel                │
 │        └─ widget_bridge.py ──▶ App Group state.json          │
 │                                     │                        │
 │                          Afterglow Widget (WidgetKit)        │
 └──────────────────────────────────────────────────────────────┘
```

Everything that touches the light goes through the backend loop, so the menu, the widget, Apple Home, themes, Spotify and the sunset schedule share a single Bluetooth connection and never send conflicting commands. When a value changes, for example from Siri, the backend updates HomeKit and the menu together.

## The Hue Bluetooth profile

Hue lights with Bluetooth advertise the service `0000fe0f-0000-1000-8000-00805f9b34fb`. Control uses these characteristics:

| Characteristic | UUID | Format |
|---|---|---|
| Power | `932c32bd-0002-47a2-835a-a8d455b859dd` | 1 byte: `0` off, `1` on |
| Brightness | `932c32bd-0003-47a2-835a-a8d455b859dd` | 1 byte: `1`–`254` |
| Colour temperature | `932c32bd-0004-47a2-835a-a8d455b859dd` | uint16 little-endian, mireds `153`–`500` |
| Colour (CIE xy) | `932c32bd-0005-47a2-835a-a8d455b859dd` | 2 × uint16 little-endian, `x` and `y` × 65535 |
| Combined commands | `932c32bd-0007-47a2-835a-a8d455b859dd` | Several values plus a transition time, in 100 ms steps |

Fades use the combined-commands characteristic, so colour and brightness change together on the light itself. Lights whose firmware doesn't offer it fall back to instant changes.

The light only accepts a new Bluetooth bond when it's in pairing mode, which is why it must be reset in the Hue app first.

## Colour

HomeKit describes colour as hue and saturation. The light wants CIE 1931 xy coordinates. Afterglow converts between the two with the wide-gamut RGB-to-XYZ matrix Philips publishes for Hue lights, including sRGB gamma correction. White light is sent as a colour temperature in mireds (1,000,000 ÷ kelvin) rather than as an xy colour.

## Apple Home

The HomeKit side is a HAP-python accessory with a Lightbulb service: On, Brightness, Hue, Saturation and Colour Temperature. Pairing keys are saved in `homekit.state`. The setup code is random, created once and kept in `config.json`. The bridge advertises `_hap._tcp` with Bonjour and listens on port 51826.

## Themes

A theme is a list of colours, each with its own brightness, plus an interval and a fade time. The engine steps through them, asking the light to fade over the fade time. Fireplace picks colours at random with small brightness changes, so it flickers. Focus filters its colours by whether it's before or after sunset. Turning the light off pauses the engine; turning it on resumes.

## Spotify

Every two seconds, an AppleScript asks the Spotify app (only if it's already running) for the player state and the current track's artwork URL. When the track changes, the cover is downloaded, shrunk and scanned for the most vivid colour that covers a reasonable share of the image. Mostly greyscale covers map to warm white.

## Sunset

`astral` calculates sunset and the end of civil twilight on the Mac, from your latitude and longitude and the Mac's time zone. No internet is needed. Brightness ramps linearly from 25% at the start time to the target by the end of twilight.

## The macOS widget

A widget can't use Bluetooth or run Python, so the menu bar app hands it a small JSON file. `widget_bridge.py` writes `state.json` (theme, palette, on/off, light name) into an App Group container, `~/Library/Group Containers/<team ID>.afterglow/`, and asks macOS to reload the widget.

macOS gives a widget roughly 40–70 refreshes a day, so the bridge rate-limits itself: theme and on/off changes at most every 20 seconds, colour-only changes at most every 5 minutes. The colour of the moment in a theme isn't tracked at all, because it changes faster than any widget can refresh. The bridge also rewrites the file every 5 minutes as a heartbeat, so the widget can tell when Afterglow has stopped.

The widget itself is a small SwiftUI app plus WidgetKit extension in `widget/`. `project.yml` is an [XcodeGen](https://github.com/yonaskolb/XcodeGen) spec; `build_widget.sh` fills in your signing team and bundle IDs, generates the Xcode project, builds it and installs it to `~/Applications`. Both targets are sandboxed and share only the App Group.

## The app wrapper

`build_app.sh` compiles a tiny C launcher that starts the project's Python with `hue_menubar.py`, and wraps it in a `.app` bundle with an `Info.plist` (menu bar only, with Bluetooth, local network and Apple Events usage descriptions). It's signed ad hoc. Being a real app means macOS asks for Bluetooth and network permission for Afterglow itself, rather than for Terminal or Python, and it can open at login.

When launched as an app, output and crashes go to `~/Library/Logs/Afterglow.log`. If startup fails, an alert says so.

## Built with

[bleak](https://github.com/hbldh/bleak) (Bluetooth LE), [HAP-python](https://github.com/ikalchev/HAP-python) (HomeKit), [rumps](https://github.com/jaredks/rumps) (menu bar), [PyObjC](https://github.com/ronaldoussoren/pyobjc) (floating panel and system events), SwiftUI and WidgetKit (macOS widget), [astral](https://github.com/sffjunkie/astral) (sunset) and [Pillow](https://python-pillow.org) (album art).
