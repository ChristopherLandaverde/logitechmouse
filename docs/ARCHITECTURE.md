# Architecture

## Overview

The project is split into four main layers:

1. `config`
   Parses and validates TOML configuration.
2. `device`
   Receives button events from Linux input sources.
3. `actions`
   Executes commands, emits key chords, or opens overlays.
4. `overlay`
   Optional UI layer for an Actions Ring-like radial launcher.

## Design principles

- keep Linux input handling isolated from action execution
- let the config name actions independently from physical buttons
- make overlay support optional so command-only workflows remain simple

## Initial module layout

- `src/logitechmouse/config.py`
- `src/logitechmouse/device.py`
- `src/logitechmouse/actions.py`
- `src/logitechmouse/overlay.py`
- `src/logitechmouse/main.py`

## Planned execution flow

1. CLI starts and loads config.
2. Device backend subscribes to mouse button events.
3. Incoming event is matched against a binding.
4. Bound action is resolved by name.
5. Action dispatcher runs the command or opens the overlay.

## Expected backends

Short term:

- shell command execution
- dry-run mode
- stubbed device backend for development

Later:

- `evdev` backend for direct Linux input events
- integration adapters for `solaar` or `logiops`
- Wayland-safe overlay implementation

