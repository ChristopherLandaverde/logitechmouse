# logitechmouse

Linux utility for recreating the closest practical version of Logitech MX mouse shortcuts and an Actions Ring-style workflow without relying on Logitech's proprietary desktop software.

## Goal

Start with the useful behavior first:

- map MX mouse buttons to Linux actions
- run commands such as screenshots from a mouse button
- support per-app shortcut profiles
- add an optional radial overlay later

## Project status

Phase 4: the radial Actions Ring is implemented. The CLI listens on a real
Logitech MX device via `evdev`, and configured buttons can either fire a
single action on press or open a radial overlay where the released segment
fires the action. X11 only in v1; Wayland support is a separate phase.

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
pip install -e ".[dev,ring]"
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

### Rings

A `[rings.NAME]` table defines a radial overlay with 3-12 segments. Each
segment names an existing `[actions.X]` and a label. To open the ring on a
button, set the binding's target to `ring:NAME`:

```toml
[rings.thumb_ring]
segments = [
  { action = "screenshot_area", label = "Area" },
  { action = "screenshot_full", label = "Full" },
  { action = "lock",            label = "Lock" },
]

[bindings.gesture_button]
trigger = "BTN_TASK"
target  = "ring:thumb_ring"
```

The ring opens on key-down at the cursor position, follows your cursor as you
hold the button, and fires the highlighted segment when you release. Releasing
in the center cancels.

### Targets vs legacy `action = "..."`

Bindings use `target = "kind:name"`:
- `target = "action:screenshot"` - fire `actions.screenshot` on press.
- `target = "ring:thumb_ring"` - open `rings.thumb_ring` on press, fire on release.

The Phase 2 form `action = "screenshot"` is still accepted; the loader maps it
to `target = "action:screenshot"` and logs a one-line migration note.

### Optional install for ring support

The radial ring needs PyQt6. Install with:

```bash
pip install 'logitechmouse[ring]'
```

Without `[ring]` you can still use action-only bindings; configs that define
ring bindings will fail validation with a clear message.

## Documents

- [Product Requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build Plan](docs/BUILD_PLAN.md)
- [Agent Guide](AGENTS.md)

