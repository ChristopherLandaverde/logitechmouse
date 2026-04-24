# Agent Guide

## Objective

Build a Linux-first utility that lets Logitech MX mouse users trigger custom actions from mouse buttons, beginning with simple one-press shortcuts such as screenshots and expanding toward an Actions Ring-like overlay.

## Product constraints

- Logitech's proprietary Actions Ring UI is not available on Linux.
- The replacement should prioritize practical workflows over pixel-perfect imitation.
- The first release should work without requiring users to write code.

## Near-term priorities

1. Detect MX button events reliably on Linux.
2. Map button events to actions from a user config file.
3. Support screenshot actions and key chord emission.
4. Add app-aware profiles.
5. Prototype an optional radial overlay.

## Technical direction

- Language: Python 3.11+
- Config: TOML
- Input integration: start with Linux event devices and leave room for `input-remapper`, `solaar`, or `logiops` integration
- UI: keep overlay implementation isolated so GTK or Qt can be swapped later

## Working rules

- Keep the command path and overlay path separate.
- Favor testable modules over direct logic in the CLI.
- Avoid hard-coding GNOME assumptions outside desktop integration boundaries.
- Treat Wayland and X11 differences as a first-class architecture concern.

## First implementation target

Deliver an MVP that can:

- load a config
- register one or more bindings
- invoke a screenshot command from a mapped button
- log unsupported environments clearly

