# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-28

First public release. Feature-complete for v1.

### Added

- **Event capture** — listens on a Logitech MX device via `evdev` and dispatches
  on configured triggers (`BTN_BACK`, `BTN_SIDE`, `BTN_EXTRA`, …).
- **TOML configuration** at `~/.config/logitechmouse/config.toml`:
  - `[actions.NAME]` — bind a name to a shell command.
  - `[bindings.NAME]` — map a button trigger to an action or a ring.
  - `[rings.NAME]` — define a 3-12 segment radial overlay.
  - `[profiles.NAME]` — per-app overrides, matched by `WM_CLASS`.
  - `[theme]` — preset name plus per-key hex color overrides.
  - `[device]` — pin a specific event device by name or path.
- **Actions Ring overlay** — radial menu opened on key-down, segment fired on
  release, center release cancels. Runs on PyQt6, X11 only in v1.
  - Bubble-style segments with Font Awesome icons via `qtawesome`.
  - Active segment label rendered in the dead-zone center.
  - `dark` (default) and `brazil` presets; per-key overrides accept
    `#rrggbb` / `#rrggbbaa`.
  - Performance: cached fonts, precomputed bubble positions, repaints skipped
    when no state changed.
- **Device grab via `/dev/uinput`** — bound trigger codes are swallowed so the
  focused application doesn't see them. Unbound events (cursor, scroll, other
  buttons) pass through a virtual device unchanged.
- **App-specific profiles** — `xdotool` is queried per key-press to read the
  active window's `WM_CLASS`; matching profile bindings override globals,
  with per-trigger fallthrough to the global set.
- **CLI subcommands**:
  - `logitechmouse devices` — list detected input devices.
  - `logitechmouse check-config` — validate config and exit.
  - `logitechmouse run NAME [--dry-run]` — run a configured action once.
  - `logitechmouse listen` — start the event listener.
  - `logitechmouse install-service` — write + enable a systemd user unit.
- **Systemd integration** — auto-start on login, absolute exec path, SIGTERM
  handled cleanly in both command-only and Qt event-loop paths.
- **Docs** — README, ARCHITECTURE, BUILD_PLAN, PRD, CONTRIBUTING.
- **Test suite** — 178 tests covering config parsing, device grab branches,
  read-loop forwarding, ring controller logic, theme plumbing, install-service,
  and gated end-to-end paths (`requires_display`, `requires_uinput`).
- **CI** — GitHub Actions runs the full suite under `xvfb-run` on Python
  3.11 and 3.12.

### Known limitations

- **X11 only.** The ring overlay relies on X11 primitives; Wayland support
  is on the roadmap.
- **MX hardware quirks.** Capability bits can lie. Use
  `scripts/dump-keys.py` to confirm what your mouse actually emits.
- **`BTN_EXTRA` unbound by default.** Reserved until a clear use case appears.
- **`flameshot` not bundled.** The Screenshot example action references it;
  install separately (`apt install flameshot`).

[Unreleased]: https://github.com/ChristopherLandaverde/logitechmouse/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChristopherLandaverde/logitechmouse/releases/tag/v0.1.0
