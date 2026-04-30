from __future__ import annotations

import argparse
from pathlib import Path

import questionary

from ..config import DEFAULT_CONFIG_PATH, Action, Profile, Ring, load_config
from ..config_writer import write_config


def _p(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def _menu_action(path: Path) -> None:
    cfg = load_config(path)
    op = questionary.select("Action operation:", choices=["Create", "Delete", "List"]).ask()
    if op == "List":
        for name, a in cfg.actions.items():
            print(f"  {name}: {a.command}")
    elif op == "Create":
        name = questionary.text("Action name:").ask()
        if name in cfg.actions:
            print(f"Error: action '{name}' already exists.")
            return
        command = questionary.text("Shell command:").ask()
        cfg.actions[name] = Action(name=name, kind="command", command=command)
        write_config(path, cfg)
        print(f"Created action '{name}'.")
    elif op == "Delete":
        name = questionary.text("Action name to delete:").ask()
        if name in cfg.actions:
            del cfg.actions[name]
            write_config(path, cfg)
            print(f"Deleted action '{name}'.")
        else:
            print(f"Action '{name}' not found.")


def _menu_ring(path: Path) -> None:
    cfg = load_config(path)
    op = questionary.select("Ring operation:", choices=["Create", "Delete", "List"]).ask()
    if op == "List":
        for name, r in cfg.rings.items():
            print(f"  {name}: {len(r.segments)} segments")
    elif op == "Create":
        name = questionary.text("Ring name:").ask()
        if name in cfg.rings:
            print(f"Error: ring '{name}' already exists.")
            return
        cfg.rings[name] = Ring(name=name, segments=[])
        write_config(path, cfg)
        print(f"Created ring '{name}'.")
    elif op == "Delete":
        name = questionary.text("Ring name to delete:").ask()
        if name not in cfg.rings:
            print(f"Ring '{name}' not found.")
            return
        broken = [
            b.name for b in cfg.bindings.values()
            if b.target.kind == "ring" and b.target.name == name
        ] + [
            f"{p.name}/{b.name}"
            for p in cfg.profiles.values()
            for b in p.bindings.values()
            if b.target.kind == "ring" and b.target.name == name
        ]
        if broken:
            print(
                f"Error: ring '{name}' is referenced by bindings: {', '.join(broken)}. "
                f"Remove those bindings first or use the CLI with --force."
            )
            return
        del cfg.rings[name]
        write_config(path, cfg)
        print(f"Deleted ring '{name}'.")


def _menu_profile(path: Path) -> None:
    cfg = load_config(path)
    op = questionary.select("Profile operation:", choices=["Create", "Delete", "List"]).ask()
    if op == "List":
        for name, pr in cfg.profiles.items():
            print(f"  {name}: match={pr.match_wm_class}")
    elif op == "Create":
        name = questionary.text("Profile name:").ask()
        if name in cfg.profiles:
            print(f"Error: profile '{name}' already exists.")
            return
        match = questionary.text("WM class to match (e.g. Firefox):").ask()
        cfg.profiles[name] = Profile(name=name, match_wm_class=match)
        write_config(path, cfg)
        print(f"Created profile '{name}'.")
    elif op == "Delete":
        name = questionary.text("Profile name to delete:").ask()
        if name in cfg.profiles:
            del cfg.profiles[name]
            write_config(path, cfg)
            print(f"Deleted profile '{name}'.")
        else:
            print(f"Profile '{name}' not found.")


def run(args: argparse.Namespace) -> int:
    path = _p(args)
    while True:
        entity = questionary.select(
            "What would you like to manage?",
            choices=["Ring", "Action", "Profile", "Exit"],
        ).ask()
        if entity in ("Exit", None):
            break
        if entity == "Ring":
            _menu_ring(path)
        elif entity == "Action":
            _menu_action(path)
        elif entity == "Profile":
            _menu_profile(path)
        again = questionary.confirm("Make another change?").ask()
        if not again:
            break
    return 0
