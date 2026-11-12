---
title: Features
lede: Everything in the menu, and what each option does.
---

## Menu bar controls

Click the bulb in the menu bar for:

- **Turn On / Turn Off**
- **Brightness** slider
- **White: warm ⟷ cool** slider, for white light from candle-warm to daylight
- **Colours**: eight colour presets and four whites
- **Colour Picker…**: the standard macOS colour picker, for any colour

Dragging a slider sends only the commands the light needs, so it stays responsive.

## Themes

**Themes** rotates the light through a palette. Brightness and colour cross-fade together, so changes are smooth.

| Calm (warm, no blue) | Changes every |
|---|---|
| Jazz Bar at Night | 45 s |
| Bangkok Opium Den | 60 s |
| Relax | 90 s |
| Focus: cool whites by day, warm after sunset | 5 min |
| Fireplace: flickers | about 8 s |
| Marrakech Dusk | 60 s |
| Kyoto Lanterns | 60 s |

| Energetic | Changes every |
|---|---|
| Tokyo Neon (blue-rich) | 15 s |
| Havana Nights | 15 s |
| Rio Carnival | 12 s |
| Synthwave Miami (blue-rich) | 20 s |
| Berlin Warehouse (blue-rich) | 8 s |

"Blue-rich" themes include strong blues, which you may want to avoid late in the evening. Nothing strobes: the fastest change is every 8 seconds.

- **Brightness:** the brightness slider scales the whole theme up or down.
- **Light off:** switching the light off, by hand, with Siri or when the Mac sleeps, pauses the theme. It carries on when the light comes back on.
- **Stopping a theme:** pick a colour (from the menu, the colour picker, Siri or the Home app), turn on Spotify matching, or choose **Stop Theme**.
- **At sunset:** if a theme is running at sunset, the light comes on in that theme.

Want a new theme? [Suggest one](https://github.com/pellarboss/afterglow/issues/new/choose) or see [Contributing](https://github.com/pellarboss/afterglow/blob/main/CONTRIBUTING.md#adding-a-theme).

## macOS widget

A small widget for your desktop or Notification Centre. It shows the current theme (or colour), its palette, and whether the light is on. Install it once with `./build_widget.sh`; see [Getting started](getting-started.md).

- **Add it:** right-click the desktop → **Edit Widgets**, search for **Afterglow**, then add the small size.
- **Apple controls when widgets refresh.** A widget can't follow a colour that changes every few seconds, so it shows the whole palette rather than the colour of the moment.
- **How quickly it updates:** theme and on/off changes show within about 20 seconds; colour-only changes, such as a new Spotify song, within about 5 minutes.
- **Afterglow not running?** The widget says so after 20 minutes.

## Floating panel

**Show Floating Panel** is a live alternative to the widget. It shows the theme name, the exact colour of the moment, the palette and a countdown to the next colour. With no theme running, it shows the light's current colour.

- **Jump to a colour:** click it in the palette.
- **Move it:** drag it anywhere. It remembers where you put it.
- **Placement:** it sits on the desktop behind your windows and appears on every Space. Tick **Floating Panel Always on Top** to keep it above your windows.

## Match Spotify album art

Tick **Match Spotify Album Art**. When a new song starts in the Spotify app on your Mac, the light fades to the most vivid colour on its cover. Mostly black-and-white covers switch it to warm white.

- **First time:** macOS asks to let Afterglow control Spotify. Click **OK**. If you missed the prompt, go to **System Settings → Privacy & Security → Automation → Afterglow** and turn on Spotify.
- **Spotify Connect:** this also works when the Spotify app on your Mac is playing on another device, such as a speaker.
- **Manual changes:** if you pick a colour yourself, it stays until the next song starts.
- **Light off:** if the light is off, it stays off. The colour is ready for when you turn it on.

Afterglow reads the current track through Spotify's built-in AppleScript support, so there's no Spotify login or developer key. It downloads the cover image from Spotify to pick the colour.

## Turn on at sunset

Tick **Turn On at Sunset**. A little before sunset, the light comes on dim and warm, then brightens to full by the end of civil twilight, when it's properly dark (about 30 minutes after sunset). The menu shows today's times, for example "On at 7:51 pm, sunset 8:06 pm".

- **Start time:** under **Sunset Timing**, choose at sunset, or 15, 30 or 45 minutes before.
- **Once per evening:** if you switch the light off or change its brightness while it's brightening, it stops and leaves the light alone. If the light is already on, it isn't touched.
- **Mac asleep at sunset:** the light comes on when the Mac wakes, as long as it's before the cut-off time (11 pm by default).
- **With Spotify matching:** the sunset schedule handles brightness only and leaves the colour to Spotify.
- **Your location:** sunset is calculated on your Mac, with no internet needed. The default location is Melbourne, Australia. Set yours in [Configuration](configuration.md#sunset).

## Sleep and wake

- **Turn Off When Mac Sleeps** (on by default) switches the light off as the Mac goes to sleep.
- **Turn On When Mac Wakes** (off by default) switches it back on when you return.

## Open at Login

**Open at Login** adds a small login item, so Afterglow starts in the background when you log in. It only works when you run **Afterglow.app**, not `./start.sh menubar`.

## Set Up Light

- **Scan for Lights**: list Hue lights in Bluetooth range, strongest signal first.
- **Pair "…"**: pair with a light and name it.
- **Open Log**: open `~/Library/Logs/Afterglow.log`.
- **Forget This Light…**: unpair and start over. Also remove the light from the Home app.
