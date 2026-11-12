---
title: Apple Home & Siri
lede: Afterglow includes a HomeKit bridge, so the light shows up in the Home app like any other accessory.
---

## Adding the light

1. Click the bulb → **Add to Apple Home…**. A QR code opens on your Mac.
2. On your iPhone, open the **Home** app → **+** → **Add Accessory**, and scan the code.
3. Tap **Add Anyway** when it warns about an uncertified accessory. Afterglow isn't certified by Apple, which is normal for open-source HomeKit accessories.

The setup code is created once, the first time you open **Add to Apple Home…**, and stays the same afterwards. It's stored in `config.json`.

## What works

| From | You can |
|---|---|
| **Home app** | Turn on and off, set brightness, colour and white temperature, use it in scenes and automations |
| **Control Centre** | Tap to toggle, hold for brightness and colour |
| **Siri** | "Turn on the desk light", "Set the desk light to 30%", "Make the desk light blue" |
| **Apple Watch, HomePod** | Anything Siri and the Home app can do |

The light appears with the name you gave it when pairing.

Picking a colour in the Home app or with Siri stops a running theme, just as picking one from the menu does.

## When the Mac is asleep

The Mac is the bridge. While it sleeps, the Home app shows the light as **No Response**. That's expected. It comes back once the Mac wakes and reconnects to the light.

If you'd rather the light stay controllable all the time, keep the Mac awake (for example with **System Settings → Energy → Prevent automatic sleeping when the display is off** on a desktop Mac), or run the [headless bridge](command-line.md#headless-bridge) on a Mac that stays on.

## Automations

Because the light is a normal HomeKit accessory, the Home app's automations work. For example: turn the light on when you arrive home, or off at midnight. Automations run from your home hub (Apple TV, HomePod or iPad), and need the Mac to be awake to reach the light.

## Removing and re-adding

1. In the Home app, long-press the light → settings → **Remove Accessory**.
2. To add it again, choose **Add to Apple Home…** in the menu and scan the code.

If the Home app says the accessory is already added, but it isn't listed, choose **Set Up Light → Forget This Light…**, pair the light again, and then add it. Forgetting resets the HomeKit pairing state.

## Network

The bridge advertises itself on your local network with Bonjour (`_hap._tcp`) and listens on TCP port **51826**. If you use a firewall, allow incoming connections for Afterglow. The iPhone and Mac must be on the same network.
