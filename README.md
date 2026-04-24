# logitechmouse

Linux utility for recreating the closest practical version of Logitech MX mouse shortcuts and an Actions Ring-style workflow without relying on Logitech's proprietary desktop software.

## Goal

Start with the useful behavior first:

- map MX mouse buttons to Linux actions
- run commands such as screenshots from a mouse button
- support per-app shortcut profiles
- add an optional radial overlay later

## Project status

This repository is in the initial scaffold stage. The current code establishes the package layout, config model, and CLI entry point for future implementation.

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
pip install -e .
logitechmouse --help
```

## Configuration

The app looks for a TOML config file, defaulting to:

```text
~/.config/logitechmouse/config.toml
```

Example:

```toml
[actions.screenshot]
type = "command"
command = "gnome-screenshot -a"

[bindings.gesture_button]
trigger = "BTN_EXTRA"
action = "screenshot"
```

## Documents

- [Product Requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build Plan](docs/BUILD_PLAN.md)
- [Agent Guide](AGENTS.md)

