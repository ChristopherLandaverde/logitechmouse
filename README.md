# logitechmouse

Linux utility for recreating the closest practical version of Logitech MX mouse shortcuts and an Actions Ring-style workflow without relying on Logitech's proprietary desktop software.

## Goal

Start with the useful behavior first:

- map MX mouse buttons to Linux actions
- run commands such as screenshots from a mouse button
- support per-app shortcut profiles
- add an optional radial overlay later

## Project status

Phase 2 MVP: the CLI listens on a real Logitech MX device via `evdev` and
fires shell-command actions on configured button presses. No device grabbing,
no overlay, no profiles yet — those are scheduled for later phases.

## Planned features

- device event capture for Logitech MX mice on Linux
- configurable button-to-action mappings
- screenshot, app launch, and key chord actions
- optional radial ring overlay triggered by mouse buttons
- profile switching by active application

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
logitechmouse --help
```

## Permissions

Reading `/dev/input/event*` requires membership in the `input` group:

```bash
sudo usermod -aG input $USER
# log out and back in for the change to apply
```

## Usage

```bash
logitechmouse devices                   # list detected input devices
logitechmouse check-config              # validate config and exit
logitechmouse run screenshot --dry-run  # run a configured action once
logitechmouse listen                    # start the event listener
```

## Configuration

The app looks for a TOML config file, defaulting to:

```text
~/.config/logitechmouse/config.toml
```

See `examples/config.toml` for a working sample. Default examples bind the
gesture button (`BTN_TASK`) because it has no OS-default action — `BTN_SIDE`
and `BTN_EXTRA` will double-fire with browser back/forward in this MVP.

## Documents

- [Product Requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build Plan](docs/BUILD_PLAN.md)
- [Agent Guide](AGENTS.md)

