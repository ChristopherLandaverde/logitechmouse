# logitechmouse

[![CI](https://github.com/ChristopherLandaverde/logitechmouse/actions/workflows/test.yml/badge.svg)](https://github.com/ChristopherLandaverde/logitechmouse/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Linux x11](https://img.shields.io/badge/platform-Linux%20%2F%20X11-orange.svg)](#requirements)

Bring Logitech MX Master mouse productivity to Linux without the proprietary
desktop software. Map any mouse button to a shell command, an app launch, or
a radial **Actions Ring** — all driven by a single TOML config.

> **Status:** v0.1.0 — feature-complete for v1. 178 tests, runs as a systemd
> user service. X11 only; Wayland is on the roadmap.

## What it does

- Maps any Logitech MX button (`BTN_BACK`, `BTN_SIDE`, `BTN_EXTRA`, etc.) to
  a shell command, an app launch, or a radial overlay.
- **Actions Ring** — hold a bound button to open a 3-12 segment radial menu
  at the cursor. Move to a segment, release to fire. Release in the center
  to cancel.
- **App-specific profiles** — different bindings depending on the focused
  window's `WM_CLASS` (browser vs terminal vs editor).
- **No dual-fire** — bound buttons are swallowed via a `/dev/uinput` virtual
  device so the focused app doesn't also see the click.
- **Always-on** — `logitechmouse install-service` writes a systemd user unit
  that auto-starts on login.

## Requirements

- **Linux** with **X11** (Wayland is post-v1; the ring overlay needs X11
  primitives).
- **Python 3.11+**.
- **Logitech MX-class mouse** with at least one extra button (`BTN_BACK`,
  `BTN_SIDE`, etc.). Tested against MX Master 3/4. Other models work too —
  see [Hardware notes](#hardware-notes-mx-quirks).
- **System packages** (Debian / Ubuntu / Pop!\_OS):

  ```bash
  sudo apt install libxcb-cursor0 xdotool
  # libxcb-cursor0 — Qt6 xcb platform plugin (required for the ring overlay)
  # xdotool        — needed for app-specific profiles (active-window detection)
  ```

  On other distros, install the equivalents (Arch: `libxcb`, `xdotool`;
  Fedora: `xcb-util-cursor`, `xdotool`).

- **Permissions** for `/dev/input/event*` and `/dev/uinput` — see
  [Permissions](#permissions) below.

## Install

```bash
git clone https://github.com/ChristopherLandaverde/logitechmouse.git
cd logitechmouse
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ring]"        # add ,dev for tests
```

Then write a config (`~/.config/logitechmouse/config.toml`) — copy
`examples/config.toml` as a starting point — and run:

```bash
logitechmouse listen            # foreground (good for first run + debugging)
logitechmouse install-service   # one-shot: write + enable a systemd user unit
```

After `install-service`, the listener auto-starts on login and survives
reboots.

## Permissions

You need read access to `/dev/input/event*` and write access to `/dev/uinput`.
On most distros, joining the `input` group covers both:

```bash
sudo usermod -aG input $USER
# log out and back in
```

If `/dev/uinput` exists but isn't writable by `input`, drop a udev rule:

```bash
sudo tee /etc/udev/rules.d/60-logitechmouse-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Configuration

The app reads `~/.config/logitechmouse/config.toml`. A minimal config:

```toml
[actions.screenshot]
type    = "command"
command = "flameshot gui"

[bindings.thumb]
trigger = "BTN_BACK"
target  = "action:screenshot"
```

A `[rings.NAME]` table defines a radial overlay with 3-12 segments, each
referencing an `[actions.X]`:

```toml
[rings.thumb_ring]
segments = [
  { action = "screenshot", label = "Shot",  icon = "fa5s.camera" },
  { action = "lock",       label = "Lock",  icon = "fa5s.lock"   },
  { action = "files",      label = "Files", icon = "fa5s.folder" },
]

[bindings.thumb]
trigger = "BTN_BACK"
target  = "ring:thumb_ring"
```

Open the ring on key-down; release on a segment to fire; release in the
center to cancel.

### App-specific profiles

`[profiles.NAME]` overrides global bindings when the focused window's
`WM_CLASS` matches:

```toml
[profiles.firefox]
match_wm_class = "firefox"

[profiles.firefox.bindings.thumb]
trigger = "BTN_BACK"
target  = "action:firefox_back"
```

Unmatched triggers fall through to the global `[bindings.*]` set.

### Themes

Two presets ship: `dark` (default) and `brazil` (yellow/blue). Override
individual colors with `#rrggbb` or `#rrggbbaa`:

```toml
[theme]
name = "dark"

[theme.overrides]
bubble_active = "#ffdf00"
center_label  = "#002776"
# Other keys: bubble, dead_zone, label, label_active, cancel
```

The `LOGITECHMOUSE_THEME=<preset>` env var overrides the TOML name — handy
for trying a preset without editing config.

### Migration: legacy `action = ...` form

The old `action = "X"` form is still accepted; the loader maps it to
`target = "action:X"` and logs a one-line migration note.

## Hardware notes (MX quirks)

Capability bits on Logitech MX devices can lie. For example, on the MX
Master tested here, `BTN_TASK` is advertised as available but never fires —
the gesture button emits `BTN_BACK` instead. Behavior varies between
specific models.

To see what your mouse actually emits:

```bash
logitechmouse devices              # find your event node
sudo ./scripts/dump-keys.py /dev/input/eventNN
# now press every button on the mouse
```

Use the codes you actually see as `trigger` values in your bindings.

## CLI reference

```bash
logitechmouse devices                   # list detected input devices
logitechmouse check-config              # validate config and exit
logitechmouse run NAME --dry-run        # run a configured action once
logitechmouse listen                    # start the event listener (foreground)
logitechmouse install-service           # install + enable systemd user unit
```

## Troubleshooting

### Buttons fire twice

The listener swallows bound codes via `/dev/uinput`. If the device isn't
writable, it falls back to non-grab mode and bound buttons reach the focused
app. Fix permissions per [Permissions](#permissions).

### Service crashes on startup with a Qt error

Log shows `Could not load the Qt platform plugin "xcb"` or a core-dump:
install `libxcb-cursor0` (or your distro's equivalent) and restart.

```bash
sudo apt install libxcb-cursor0
systemctl --user reset-failed logitechmouse.service
systemctl --user start logitechmouse.service
```

### Ring overlay doesn't show

You're probably on Wayland. Check `echo $XDG_SESSION_TYPE` — if it says
`wayland`, switch to an X11 session at the login screen for now. Wayland
support is on the roadmap.

## Development

```bash
pip install -e ".[dev,ring]"
pytest                          # full suite (skips Qt tests if no $DISPLAY)
xvfb-run -a pytest              # full suite headless (matches CI)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor workflow.

## Documents

- [Product Requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build Plan](docs/BUILD_PLAN.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Agent Guide](AGENTS.md)

## License

[MIT](LICENSE) © Christopher Landaverde.
