from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

_UNIT_TEMPLATE = """\n[Unit]
Description=Logitech Mouse button remapper
After=graphical-session.target

[Service]
ExecStart={exec_start} listen --config {config_path}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""


def run(args: argparse.Namespace) -> int:
    exec_start = shutil.which("logitechmouse") or (sys.argv[0] if sys.argv else None)
    if not exec_start:
        logging.error("cannot resolve logitechmouse binary; check your PATH")
        return 1

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        logging.error("config file not found: %s", config_path)
        return 1

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_path = unit_dir / "logitechmouse.service"

    if unit_path.exists() and not getattr(args, "force", False):
        logging.error(
            "service file already exists: %s â use --force to overwrite",
            unit_path,
        )
        return 1

    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        _UNIT_TEMPLATE.format(exec_start=exec_start, config_path=config_path)
    )
    logging.info("wrote %s", unit_path)

    result = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
    )
    if result.returncode != 0:
        logging.warning(
            "systemctl --user daemon-reload failed (rc=%d); "
            "run it manually once a systemd user session is available",
            result.returncode,
        )

    print("Service file written to " + str(unit_path))
    print("Enable and start with:")
    print("  systemctl --user enable --now logitechmouse")
    return 0
