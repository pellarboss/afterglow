# Contributing to Afterglow

Thanks for helping. Afterglow is a small project, so the process is light.

## Ways to help

- **Report a bug:** open an issue with the bug template. Include your macOS version, your light model and the relevant lines from `~/Library/Logs/Afterglow.log`.
- **Suggest a theme or feature:** open an issue with the feature template. For themes, a name, 5–6 colours and how often they should change is plenty.
- **Ask a question:** use [Discussions](../../discussions) rather than issues.
- **Send a pull request:** see below.

## Development setup

```bash
git clone https://github.com/pellarboss/afterglow.git
cd afterglow
./start.sh setup          # creates .venv and installs requirements.txt
./start.sh menubar        # run the menu bar app from Terminal (logs to the console)
```

Useful while developing:

```bash
./start.sh scan                       # list Hue lights in Bluetooth range
./start.sh pair <ADDRESS> --name Desk # pair and save to config.json
./start.sh run -v                     # headless HomeKit bridge with verbose logs
```

Running from Terminal shows Python tracebacks that the `.app` hides.

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Keep changes focused: one fix or feature per PR.
3. Test on a real light if your change touches Bluetooth, HomeKit or themes, and say so in the PR.
4. Make sure CI passes (it compiles every module and checks the shell scripts).
5. Update the docs in `docs/` if behaviour or menu items change.

### Style

- Python 3.10+, type hints where they help, standard library first.
- Keep the Bluetooth connection owned by the backend loop in `hue_backend.py`. UI code should never talk to the light directly.
- User-facing text: short, plain English, sentence case.

### Adding a theme

Themes live in `themes.py`. Add a `Theme(...)` to `_THEMES` with a unique key, a group (`"Calm"` or `"Energetic"`), an interval and fade, and its colours. Calm themes should avoid blue and change slowly. Nothing should change faster than every 8 seconds. Also add the theme to `docs/_data/themes.yml` so it appears on the website.

## Never commit personal state

`homekit.state`, `config.json` and `homekit-qr.png` hold your HomeKit pairing keys, setup code and light address. They're in `.gitignore`; please keep them out of commits, issues and screenshots.

## Licence

By contributing, you agree that your contributions are licensed under the [MIT Licence](LICENSE).
