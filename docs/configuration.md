---
title: Configuration
lede: Most settings are in the menu. Everything is saved to config.json, which you can also edit by hand.
---

`config.json` lives in the Afterglow folder, next to `hue_menubar.py`. It's created when you first pair a light.

To edit it, choose **Quit Afterglow**, change the file, then open the app again. The app rewrites the file when you change settings in the menu, so edits made while it's running can be lost.

> `config.json` holds your HomeKit setup code and your light's address. It's excluded from git; don't share it.

## Light

| Key | Default | Set from the menu | What it does |
|---|---|---|---|
| `address` | none | Pair | Bluetooth identifier of the paired light |
| `name` | `"Light Strip"` | Pair | Name in Apple Home and for Siri |
| `homekit_code` | created once | Add to Apple Home… | 8-digit HomeKit setup code, `XXX-XX-XXX` |
| `off_on_sleep` | `true` | Turn Off When Mac Sleeps | Switch the light off when the Mac sleeps |
| `on_on_wake` | `false` | Turn On When Mac Wakes | Switch it back on when the Mac wakes |

## Themes

| Key | Default | Set from the menu | What it does |
|---|---|---|---|
| `theme` | none | Themes | Key of the running theme, such as `"jazz"` or `"tokyo"`. Restored on launch |
| `theme_scale` | `1.0` | Brightness, while a theme runs | Scales every colour's brightness in the theme |

Theme keys: `jazz`, `bangkok`, `relax`, `focus`, `fireplace`, `marrakech`, `kyoto`, `tokyo`, `havana`, `rio`, `synthwave`, `berlin`.

## Floating panel

| Key | Default | Set from the menu | What it does |
|---|---|---|---|
| `widget_visible` | `false` | Show Floating Panel | Show the floating panel |
| `widget_on_top` | `false` | Floating Panel Always on Top | Keep the panel above windows |
| `widget_pos` | none | Drag the panel | Saved position on screen |

## macOS widget

Set by `build_widget.sh`; you shouldn't need to change them.

| Key | What it does |
|---|---|
| `widget_group` | App Group the widget reads from, `<team ID>.afterglow` |
| `widget_app` | Path to the installed `Afterglow Widget.app` |

## Spotify

| Key | Default | Set from the menu | What it does |
|---|---|---|---|
| `spotify_sync` | `false` | Match Spotify Album Art | Follow the album cover colour |

## Sunset

| Key | Default | Set from the menu | What it does |
|---|---|---|---|
| `sunset_auto` | `false` | Turn On at Sunset | Turn on at sunset |
| `sunset_lead_min` | `15` | Sunset Timing | Minutes before sunset to start: `0`, `15`, `30` or `45` |
| `sunset_until` | `"23:00"` | none | Latest time to turn on, for when the Mac wakes late |
| `sunset_brightness` | `100` | none | Brightness (%) to reach by the time it's dark |
| `latitude` | `-37.8136` | none | Your latitude, for sunset times |
| `longitude` | `144.9631` | none | Your longitude, for sunset times |

The default location is Melbourne, Australia. For Sydney, for example:

```json
{
  "latitude": -33.87,
  "longitude": 151.21,
  "sunset_until": "22:30"
}
```

Sunset times use your Mac's time zone, including daylight saving.

## Other files

| File | What it is |
|---|---|
| `homekit.state` | HomeKit pairing keys and paired iPhones. Treat it like a password |
| `homekit-qr.png` | The setup QR code, created by **Add to Apple Home…** |
| `~/Library/Logs/Afterglow.log` | The app's log. Rotated at 2 MB |
| `~/Library/Group Containers/<team ID>.afterglow/state.json` | What the macOS widget shows: theme, palette, on/off |
| `~/Library/LaunchAgents/local.afterglow.menubar.plist` | Created by **Open at Login**, removed when you untick it |
