---
title: Getting started
lede: Build the app, pair your light and add it to Apple Home.
---

## What you need

- A Mac with Bluetooth, running macOS 12 or later
- **Python 3.10 or later.** macOS ships Python 3.9, so install a newer one: `brew install python@3.12`
- **The Xcode Command Line Tools**, to build the app: `xcode-select --install`
- A **Philips Hue light with Bluetooth** (look for the Bluetooth logo on the box or in the Hue app)
- The **Hue app** on your iPhone, to reset the light before pairing

Your Mac becomes the bridge, so keep it within about 10 m of the light. While the Mac sleeps, the light can't be controlled from Apple Home.

## 1. Download and build

```bash
git clone https://github.com/pellarboss/afterglow.git
cd afterglow
./build_app.sh
```

The first build creates a Python environment in `.venv` and installs the dependencies, which takes about a minute. It then builds **Afterglow.app** in the same folder.

> Put the folder somewhere permanent, such as `~/Applications` or `~/Documents`, before building. The app runs the code in this folder, so it stops working if the folder moves. If you do move it, run `./build_app.sh` again.

Prefer not to build an app? Run it from Terminal instead with `./start.sh menubar`. Errors then show in the Terminal window, which is handy for debugging.

## 2. Open it

```bash
open "Afterglow.app"
```

A bulb icon appears in the menu bar. When macOS asks, allow:

- **Bluetooth**, to talk to the light
- **Local network**, so Apple Home on your iPhone can reach the Mac

## 3. Reset the light

A Hue light only pairs with a new device when it's freshly reset.

1. In the Hue app on your iPhone, go to **Settings → Lights**.
2. Choose your light, then **Reset**. Use **Reset**, not **Delete**.

If the light isn't in the Hue app yet, add it first with **Settings → Lights → +** and scan the QR code on its power supply.

## 4. Pair from the menu bar

Within a couple of minutes of resetting:

1. Click the bulb → **Set Up Light → Scan for Lights**.
2. Choose **Pair "…"** next to your light. The bars show signal strength.
3. Give it a name. This is the name Siri and the Home app use, so pick something easy to say, such as "Desk Light".
4. If macOS asks to pair a Bluetooth device, click **Connect**.

The light blinks once when pairing works.

## 5. Add it to Apple Home

1. Click the bulb → **Add to Apple Home…**. A QR code opens on your Mac.
2. On your iPhone, open the **Home** app → **+** → **Add Accessory**, and scan the code.
3. When it warns about an uncertified accessory, tap **Add Anyway**.

The light now works with Siri, Control Centre and the Home app. See [Apple Home & Siri](apple-home.md) for more.

## 6. Start it automatically

Tick **Open at Login** in the menu. Afterglow then starts quietly in the background whenever you log in.

## 7. Add the widget (optional)

The macOS widget shows the current theme, its palette and whether the light is on, on your desktop or in Notification Centre. It needs macOS 14 or later and **Xcode**, with your Apple ID added under **Xcode → Settings → Accounts**. A free personal team is fine.

```bash
./build_widget.sh
```

The script installs XcodeGen with Homebrew if needed, finds your signing team, builds **Afterglow Widget.app** into `~/Applications` and connects the menu bar app to it. If you have more than one team, it lists them; run it again with the one to use:

```bash
AFTERGLOW_TEAM=ABCDE12345 ./build_widget.sh
```

Then right-click the desktop → **Edit Widgets**, search for **Afterglow** and add the small widget. If macOS asks whether Afterglow can access data from other apps, click **Allow**: that's Afterglow passing the theme to the widget.

## Updating

```bash
cd afterglow
git pull
./build_app.sh
```

Your pairing and settings are kept, because `homekit.state` and `config.json` aren't touched by updates. If the widget changed, run `./build_widget.sh` again too.

## Uninstalling

1. Untick **Open at Login**, then choose **Quit Afterglow**.
2. In the Home app, remove the light.
3. If you built the widget, remove it from your desktop and delete `~/Applications/Afterglow Widget.app`.
4. Delete the `afterglow` folder. Optionally delete `~/Library/Logs/Afterglow.log`.

## Next

- [Features](features.md): themes, widget, floating panel, Spotify and sunset
- [Troubleshooting](troubleshooting.md), if something doesn't work
