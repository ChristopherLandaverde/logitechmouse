from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s  %(message)s"


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def _install_signal_handlers() -> None:
    def _handle(signum, _frame):
        logging.info("received signal %s, exiting", signum)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logitechmouse")
    parser.add_argument("--config", type=Path, help="Path to config TOML")
    sub = parser.add_subparsers(dest="command", required=True)

    p_listen = sub.add_parser("listen", help="Run the event listener")
    p_listen.add_argument(
        "--device", default=None, help="Override [device].path with this event node"
    )

    p_devices = sub.add_parser("devices", help="List detected input devices")

    p_check = sub.add_parser("check-config", help="Validate config and exit")
    p_check.add_argument(
        "--device", default=None, help="Override [device].path with this event node"
    )

    p_run = sub.add_parser("run", help="Run a configured action once")
    p_run.add_argument("name", help="Action name as defined in config")
    p_run.add_argument("--dry-run", action="store_true", help="Do not spawn the command")

    p_install = sub.add_parser(
        "install-service",
        help="Write a systemd user unit file for logitechmouse",
    )
    p_install.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to config TOML (baked into ExecStart)",
    )
    p_install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing unit file",
    )

    return parser


def main() -> int:
    _configure_logging()
    _install_signal_handlers()

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "listen":
        from .cli.listen import run as run_cmd
    elif args.command == "devices":
        from .cli.devices import run as run_cmd
    elif args.command == "check-config":
        from .cli.check_config import run as run_cmd
    elif args.command == "run":
        from .cli.run import run as run_cmd
    elif args.command == "install-service":
        from .cli.install_service import run as run_cmd
    else:
        parser.error(f"unknown command: {args.command}")

    return run_cmd(args)


if __name__ == "__main__":
    raise SystemExit(main())
