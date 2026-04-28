from __future__ import annotations

from dataclasses import dataclass
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
    if shutil.which("systemd-run"):
        return ["systemd-run", "--user", "--scope", "--"] + cmd
    return cmd


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
