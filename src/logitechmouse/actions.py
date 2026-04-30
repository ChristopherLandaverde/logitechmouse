from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from .config import Action


@dataclass
class ActionResult:
    action: str
    ok: bool
    detail: str


def _in_own_cgroup(cmd: list[str]) -> list[str]:
    if _systemd_run_scope_available():
        return ["systemd-run", "--user", "--scope", "--"] + cmd
    return cmd


@lru_cache(maxsize=1)
def _systemd_run_scope_available() -> bool:
    if shutil.which("systemd-run") is None or not _user_bus_available():
        return False

    try:
        result = subprocess.run(
            ["systemd-run", "--user", "--scope", "--", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=0.1,
            check=False,
        )
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _user_bus_available() -> bool:
    bus_address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if bus_address.startswith("unix:path="):
        raw_path = bus_address.removeprefix("unix:path=").split(",", 1)[0]
        return Path(raw_path).exists()

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return (Path(runtime_dir) / "bus").exists()

    return False


def run_action(action: Action, dry_run: bool = False) -> ActionResult:
    if action.kind != "command":
        return ActionResult(action.name, False, f"unsupported action type: {action.kind}")

    if not action.command:
        return ActionResult(action.name, False, "missing command")

    if dry_run:
        return ActionResult(action.name, True, f"dry-run: {action.command}")

    try:
        parts = shlex.split(action.command)
    except ValueError as exc:
        return ActionResult(action.name, False, f"invalid command: {exc}")

    if shutil.which(parts[0]) is None:
        return ActionResult(action.name, False, f"failed to spawn: [Errno 2] No such file or directory: {parts[0]!r}")

    try:
        subprocess.Popen(_in_own_cgroup(parts), start_new_session=True)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return ActionResult(action.name, False, f"failed to spawn: {exc}")

    return ActionResult(action.name, True, f"fired: {action.command}")
