from __future__ import annotations

import argparse
from pathlib import Path

from .actions import run_action
from .config import load_config
from .device import DeviceBackend


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logitechmouse")
    parser.add_argument("--config", type=Path, help="Path to config TOML")
    parser.add_argument("--dry-run", action="store_true", help="Do not execute commands")
    parser.add_argument(
        "--run-action",
        metavar="NAME",
        help="Run one configured action directly for testing",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    backend = DeviceBackend()

    if args.run_action:
        action = config.actions.get(args.run_action)
        if action is None:
            parser.error(f"unknown action: {args.run_action}")

        result = run_action(action, dry_run=args.dry_run)
        print(result.detail)
        return 0 if result.ok else 1

    print("logitechmouse scaffold")
    print(f"backend: {backend.describe()}")
    print(f"actions: {len(config.actions)}")
    print(f"bindings: {len(config.bindings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

