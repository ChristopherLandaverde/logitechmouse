# Build Plan

## Phase 1

- initialize package and CLI
- define config schema
- add dry-run command execution
- add sample config

## Phase 2

- implement Linux input event backend
- support binding mouse buttons to commands
- add logs and validation errors

## Phase 3

- add built-in screenshot helpers for GNOME and KDE
- add app-specific profiles
- add tests around config parsing and action dispatch

## Phase 4

- prototype radial overlay
- support selectable ring items
- improve desktop integration and packaging


## Phase 5

- exclusive device grab via uinput so bound buttons no longer reach apps
- virtual device forwards all unbound events (scroll, cursor, unbound buttons)
- swallow-codes computed from active bindings at startup
- 139 tests; Qt-path SIGTERM handling deferred to Phase 6

## Phase 6

- `install-service` CLI command writes a systemd user unit
- service auto-starts on login; `--config` wired as a global argument before `listen`
- exec path resolved to absolute venv binary (required by systemd)
- ring overlay: silver bubble style, Font Awesome icons via qtawesome
- overlay performance: skip identical repaints, cache font metrics, precompute bubble positions
- active segment label rendered in dead zone center for immediate selection feedback
- theme system: `dark` (default) and `brazil` via `LOGITECHMOUSE_THEME` env var
- app-specific profiles via X11 active-window detection (`xdotool` → WM_CLASS),
  `[profiles.NAME]` config sections override global bindings per-trigger

## Phase 7

- themes promoted to first-class TOML `[theme]` section with preset name plus
  per-key `[theme.overrides]` (hex `#rrggbb` / `#rrggbbaa`); env var stays as
  testing escape hatch
- minimalist B&W redesign: radial bubble gradients, hairline strokes, fade-out

## Planned (post-v1)

- interactive ring management: CLI/GUI for adding/removing apps from a ring
  without hand-editing `config.toml`
- Wayland support (layer-shell or per-compositor)
- BTN_EXTRA binding (deferred until use case is clearer)
