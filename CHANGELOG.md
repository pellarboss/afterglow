# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-12

First public release.

### Added
- Menu bar app: on/off, brightness, warm-to-cool white, colour presets and colour picker
- Built-in Apple Home (HomeKit) bridge with QR-code setup, so Siri and the Home app work
- Bluetooth pairing from the menu (scan, pair, forget)
- 12 themes in two groups, Calm and Energetic, with cross-fading brightness and colour
- macOS widget (WidgetKit) showing the theme, palette and on/off state, built with `build_widget.sh`
- Floating panel with the live colour, palette and countdown
- Match Spotify album art
- Turn on at sunset, with selectable lead time and a cut-off time
- Turn off when the Mac sleeps and optionally on when it wakes; Open at Login
- Command line: `scan`, `pair` and a headless `run` bridge
- Documentation site on GitHub Pages
