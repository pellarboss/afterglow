# Security Policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems.

Use GitHub's private vulnerability reporting instead: go to the repository's **Security** tab → **Report a vulnerability**. You'll get a reply as soon as the maintainer can look at it.

## Scope

Things worth reporting include:

- HomeKit pairing state or setup codes being exposed, logged or sent anywhere
- Ways for another device on the local network to control the light without being paired in Apple Home
- Command injection through AppleScript, `osascript` or `curl` calls (for example via Spotify track metadata)

## What Afterglow stores

| File | Contains | Notes |
|---|---|---|
| `homekit.state` | HomeKit accessory keys and paired controllers | Treat like a password |
| `config.json` | Light address, name, HomeKit setup code, preferences | Don't share |
| `~/Library/Logs/Afterglow.log` | Runtime log | Check before attaching to an issue |
| `~/Library/Group Containers/<team ID>.afterglow/state.json` | What the widget shows: theme, palette, light name | Not sensitive |

All of these are local to your Mac. The first two live in the project folder and are excluded from git.

## Supported versions

Only the latest release on `main` gets fixes.
