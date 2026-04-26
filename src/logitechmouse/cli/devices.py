from __future__ import annotations

import argparse

from ..device import EvdevBackend


def run(args: argparse.Namespace) -> int:
    candidates = EvdevBackend().list_candidates()

    print(
        f"{'PATH':<22}{'NAME':<36}{'VENDOR':<8}{'PRODUCT':<9}"
        f"{'READABLE':<10}BUTTONS"
    )
    for c in candidates:
        print(
            f"{c.path:<22}{c.name[:35]:<36}"
            f"{c.vendor:04x}    {c.product:04x}     "
            f"{('yes' if c.readable else 'no'):<10}"
            f"{'yes' if c.button_capable else 'no'}"
        )

    if any(not c.readable for c in candidates):
        print()
        print("Some devices unreadable. Add yourself to the `input` group:")
        print("  sudo usermod -aG input $USER")
        print("Then log out and back in.")

    return 0
