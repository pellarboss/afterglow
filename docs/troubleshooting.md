---
title: Troubleshooting
lede: Fixes for the problems people hit most, and how to get details when something else goes wrong.
---

## Find out what happened

Most problems are explained in the log. Click the bulb → **Set Up Light → Open Log**, or in Terminal:

```bash
tail -50 ~/Library/Logs/Afterglow.log
```

To see errors as they happen, run the app inside Terminal:

```bash
"Afterglow.app/Contents/MacOS/Afterglow"
```

or skip the app entirely with `./start.sh menubar`.

## The app flashes and quits

When an app is opened from Finder, Python errors aren't shown anywhere, so a crash looks like a flash. Afterglow writes the details to the log and shows a **Afterglow stopped unexpectedly** alert. Check the log, or run it inside Terminal as above.

Common causes:

- **The folder moved** after building. Run `./build_app.sh` again from the new location.
- **Dependencies are missing or out of date.** Run `./start.sh setup`, then open the app again.
- **Bluetooth access was refused.** See below.

## Bluetooth

**"Can't reach the light"** usually means the light is off at the wall, or out of range. Keep the Mac within about 10 m, with as few walls in between as possible.

**macOS didn't ask for Bluetooth access, or you clicked Don't Allow.** Go to **System Settings → Privacy & Security → Bluetooth** and turn on Afterglow. If it isn't listed, quit the app, rebuild with `./build_app.sh` and open it again.

**The light isn't found when scanning.**

- Make sure it's powered on.
- Close the Hue app on your iPhone, which may be holding the connection.
- Scan again; the strongest lights are listed first.

## Pairing

**"Pairing didn't work" or the light refused to pair.** The light wasn't in pairing mode. In the Hue app, go to **Settings → Lights → your light → Reset**, then pair again within a couple of minutes. Use **Reset**, not **Delete**. The address changes after a reset, so scan again first.

**The light isn't in the Hue app.** Add it with **Settings → Lights → +**, scanning the QR code on its power supply, then reset it.

## Apple Home

**The light shows "No Response".** The Mac is the bridge, so this is expected while it sleeps. If the Mac is awake:

- Check that Afterglow is running (the bulb is in the menu bar).
- Check that the iPhone and Mac are on the same network.
- In **System Settings → Privacy & Security → Local Network**, make sure Afterglow is allowed.

**"Accessory already added" but it's not in the Home app.** Choose **Set Up Light → Forget This Light…**, pair the light again, then choose **Add to Apple Home…**. Forgetting resets the HomeKit pairing.

**Two copies of the light, or it behaves erratically.** Make sure `./start.sh run` isn't running at the same time as the app. Only one bridge should run.

## Spotify

**The light doesn't change with the music.**

- Check that **Match Spotify Album Art** is ticked.
- Allow automation: **System Settings → Privacy & Security → Automation → Afterglow → Spotify**.
- Matching uses the Spotify **desktop app** on this Mac. Spotify in a web browser isn't supported.
- If the light is off, the colour waits until you turn it on.

## macOS widget

**`build_widget.sh` says there's no signing certificate.** In Xcode, go to **Settings → Accounts**, add your Apple ID, select your team → **Manage Certificates → + → Apple Development**. Then run the script again.

**The build failed.** The script prints the important lines; the full log is in `widget/build.log`.

**Afterglow doesn't appear in Edit Widgets.** Open `~/Applications/Afterglow Widget.app` once, then look again. The widget needs macOS 14 or later.

**The widget says Afterglow isn't running.** The menu bar app must be running to feed it. Open Afterglow.app; the widget catches up within a few minutes.

**The widget shows an old colour.** Expected for colour-only changes: macOS limits how often widgets refresh, so these show within about 5 minutes. Use the floating panel for the live colour.

## Sunset

**The light came on at the wrong time.** Sunset is calculated for Melbourne, Australia, unless you set your location. Add `latitude` and `longitude` to `config.json` (see [Configuration](configuration.md#sunset)).

**It didn't come on.** The sunset schedule runs once per evening and leaves the light alone if it's already on, or if you changed it while it was brightening. If the Mac woke after the cut-off time (11 pm by default), it doesn't turn on.

## Start over

1. Choose **Set Up Light → Forget This Light…**.
2. Remove the light from the Home app.
3. Reset the light in the Hue app, then pair and add it again.

## Still stuck?

[Open an issue](https://github.com/pellarboss/afterglow/issues/new/choose) with your macOS version, light model and the relevant lines from the log. Please don't include `config.json`, `homekit.state` or your setup code.
