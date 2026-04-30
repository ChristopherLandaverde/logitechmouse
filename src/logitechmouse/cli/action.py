from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from ..config import DEFAULT_CONFIG_PATH, Action, load_config
from ..config_writer import write_config


def _p(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def run_action_list(args: argparse.Namespace) -> int:
    cfg = load_config(_p(args))
    if not cfg.actions:
        print("No actions defined.")
        return 0
    for name, a in cfg.actions.items():
        cmd = f"  → {a.command}" if a.command else ""
        print(f"{name} [{a.kind}]{cmd}")
    return 0


def run_action_create(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    if args.name in cfg.actions:
        print(f"Error: action '{args.name}' already exists.", file=sys.stderr)
        return 1
    cfg.actions[args.name] = Action(name=args.name, kind="command", command=args.command)
    write_config(path, cfg)
    print(f"Created action '{args.name}'.")
    return 0


def run_action_delete(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    if args.name not in cfg.actions:
        close = difflib.get_close_matches(args.name, cfg.actions.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: action '{args.name}' not found.{hint}", file=sys.stderr)
        return 1
    broken_rings = [
        r.name for r in cfg.rings.values()
        if any(s.action == args.name for s in r.segments)
    ]
    broken_bindings = [
        b.name for b in cfg.bindings.values()
        if b.target.kind == "action" and b.target.name == args.name
    ]
    broken_profile = [
        f"{prof.name}/{b.name}"
        for prof in cfg.profiles.values()
        for b in prof.bindings.values()
        if b.target.kind == "action" and b.target.name == args.name
    ]
    broken = broken_rings + broken_bindings + broken_profile
    if broken and not args.force:
        print(
            f"Error: action '{args.name}' is referenced by: {', '.join(broken)}.\n"
            f"Use --force to delete the action and remove those references automatically.",
            file=sys.stderr,
        )
        return 1
    if args.force:
        for ring in cfg.rings.values():
            ring.segments = [s for s in ring.segments if s.action != args.name]
        cfg.bindings = {
            n: b for n, b in cfg.bindings.items()
            if not (b.target.kind == "action" and b.target.name == args.name)
        }
        for prof in cfg.profiles.values():
            prof.bindings = {
                n: b for n, b in prof.bindings.items()
                if not (b.target.kind == "action" and b.target.name == args.name)
            }
    del cfg.actions[args.name]
    write_config(path, cfg)
    print(f"Deleted action '{args.name}'.")
    return 0


def run(args: argparse.Namespace) -> int:
    cmd = args.action_command
    if cmd == "list":
        return run_action_list(args)
    if cmd == "create":
        return run_action_create(args)
    if cmd == "delete":
        return run_action_delete(args)
    return 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("action", help="Manage actions")
    ac = p.add_subparsers(dest="action_command", required=True)

    ac.add_parser("list", help="List all actions")

    p_c = ac.add_parser("create", help="Create a new command action")
    p_c.add_argument("name")
    p_c.add_argument("--command", required=True, help="Shell command to run")

    p_d = ac.add_parser("delete", help="Delete an action")
    p_d.add_argument("name")
    p_d.add_argument("--force", action="store_true",
                     help="Also remove segments and bindings referencing this action")
