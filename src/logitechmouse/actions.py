from __future__ import annotations

from dataclasses import dataclass
import shlex
import subprocess

from .config import Action


@dataclass
class ActionResult:
    action: str
    ok: bool
    detail: str


def run_action(action: Action, dry_run: bool = False) -> ActionResult:
    if action.kind != "command":
        return ActionResult(action=action.name, ok=False, detail=f"unsupported action type: {action.kind}")

    if not action.command:
        return ActionResult(action=action.name, ok=False, detail="missing command")

    if dry_run:
        return ActionResult(action=action.name, ok=True, detail=f"dry-run: {action.command}")

    subprocess.run(shlex.split(action.command), check=True)
    return ActionResult(action=action.name, ok=True, detail=f"executed: {action.command}")
