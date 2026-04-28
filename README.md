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

See `examples/config.toml` for a working sample. Bound trigger codes are
swallowed via a `/dev/uinput` virtual device so they do not reach focused
applications — `BTN_SIDE` / `BTN_EXTRA` no longer dual-fire with browser
back/forward when bound. If you do see dual-firing, see
[Troubleshooting → buttons fire twice](#buttons-fire-twice-your-action-runs-and-the-app-sees-the-click).

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

### Themes

The ring ships with two presets: `dark` (default) and `brazil` (yellow/blue,
bandeira do Brasil). Pick one via your `config.toml`:

```toml
[theme]
name = "brazil"
```

You can also override individual colors on top of a preset. Keys accept
`#rrggbb` or `#rrggbbaa` (alpha):

```toml
[theme]
name = "dark"

[theme.overrides]
bubble_active = "#ffdf00"   # active bubble fill
center_label  = "#002776"   # active segment label in dead zone
# Other keys: bubble, dead_zone, label, label_active, cancel
```

The `LOGITECHMOUSE_THEME=<preset>` env var still works and overrides the
TOML preset name — handy for testing without editing config.

## Troubleshooting

### Buttons fire twice (your action runs *and* the app sees the click)

`logitechmouse` swallows bound trigger codes via a `/dev/uinput` virtual
device. If `/dev/uinput` is not writable by your user, the listener falls
back to non-grab mode (you'll see a warning in the log) and bound buttons
also reach the focused app.

Fix on most distros — add yourself to a group with write access:

```bash
# Check who owns /dev/uinput:
ls -l /dev/uinput
# crw------- 1 root root ...   -> needs a udev rule (see below)
# crw-rw---- 1 root input ...  -> just join the group:
sudo usermod -aG input $USER
# log out + back in
```

Or drop a udev rule (works regardless of distro defaults):

```bash
sudo tee /etc/udev/rules.d/60-logitechmouse-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

After the fix, restart the listener and confirm the warning is gone.

## Documents

- [Product Requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build Plan](docs/BUILD_PLAN.md)
- [Agent Guide](AGENTS.md)

