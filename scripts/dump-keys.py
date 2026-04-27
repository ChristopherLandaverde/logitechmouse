#!/usr/bin/env python3
"""Print every key event from a given evdev device path.

Usage:
    sudo .venv/bin/python scripts/dump-keys.py /dev/input/event25

Press buttons on the device. Each press prints something like:
    BTN_EXTRA  pressed
    BTN_EXTRA  released

Ctrl-C to exit. Drop this script after we've identified the gesture
button code; it isn't part of the package.
"""
from __future__ import annotations

import sys

from evdev import InputDevice, categorize, ecodes


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} /dev/input/eventNN", file=sys.stderr)
        return 2

    path = sys.argv[1]
    dev = InputDevice(path)
    print(f"listening on {path} ({dev.name}) — press Ctrl-C to exit", file=sys.stderr)

    for event in dev.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        if event.value not in (0, 1):
            continue
        ke = categorize(event)
        keycode = ke.keycode
        if isinstance(keycode, (list, tuple)):
            name = ",".join(keycode) if keycode else f"code={event.code}"
        elif isinstance(keycode, str):
            name = keycode
        else:
            name = f"code={event.code}"
        state = "pressed" if event.value == 1 else "released"
        print(f"{name:32s} {state}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
