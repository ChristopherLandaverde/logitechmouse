from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from evdev import ecodes

from ..config import (
    DEFAULT_CONFIG_PATH, Binding, ConfigError, Profile, load_config,
    parse_target_string, validate_config,
)
from ..config_writer import write_config


def _p(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def run_profile_list(args: argparse.Namespace) -> int:
    cfg = load_config(_p(args))
    if not cfg.profiles:
        print("No profiles defined.")
        return 0
    for name, pr in cfg.profiles.items():
        n = len(pr.bindings)
        print(f"{name}  match={pr.match_wm_class}  ({n} binding{'s' if n != 1 else ''})")
    return 0


def run_profile_create(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    if args.name in cfg.profiles:
        print(f"Error: profile '{args.name}' already exists.", file=sys.stderr)
        return 1
    cfg.profiles[args.name] = Profile(name=args.name, match_wm_class=args.match)
    try:
        validate_config(cfg)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    write_config(path, cfg)
    print(f"Created profile '{args.name}'.")
    return 0


def run_profile_delete(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    if args.name not in cfg.profiles:
        close = difflib.get_close_matches(args.name, cfg.profiles.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: profile '{args.name}' not found.{hint}", file=sys.stderr)
        return 1
    del cfg.profiles[args.name]
    try:
        validate_config(cfg)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    write_config(path, cfg)
    print(f"Deleted profile '{args.name}'.")
    return 0


def run_binding_set(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    profile = cfg.profiles.get(args.profile)
    if profile is None:
        close = difflib.get_close_matches(args.profile, cfg.profiles.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: profile '{args.profile}' not found.{hint}", file=sys.stderr)
        return 1
    if args.trigger not in ecodes.ecodes:
        print(f"Error: trigger '{args.trigger}' is not a valid evdev event code.",
              file=sys.stderr)
        return 1
    try:
        target = parse_target_string(args.target)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    binding_name = args.trigger.lower()
    profile.bindings[binding_name] = Binding(
        name=binding_name, trigger=args.trigger, target=target,
    )
    try:
        validate_config(cfg)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    write_config(path, cfg)
    print(f"Set binding '{args.trigger}' → '{args.target}' on profile '{args.profile}'.")
    return 0


def run_binding_remove(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    profile = cfg.profiles.get(args.profile)
    if profile is None:
        print(f"Error: profile '{args.profile}' not found.", file=sys.stderr)
        return 1
    match = next(
        (n for n, b in profile.bindings.items() if b.trigger == args.trigger), None
    )
    if match is None:
        print(
            f"Error: no binding with trigger '{args.trigger}' in profile '{args.profile}'.",
            file=sys.stderr,
        )
        return 1
    del profile.bindings[match]
    try:
        validate_config(cfg)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    write_config(path, cfg)
    print(f"Removed binding '{args.trigger}' from profile '{args.profile}'.")
    return 0


def run(args: argparse.Namespace) -> int:
    cmd = args.profile_command
    if cmd == "list":
        return run_profile_list(args)
    if cmd == "create":
        return run_profile_create(args)
    if cmd == "delete":
        return run_profile_delete(args)
    if cmd == "binding":
        bcmd = args.binding_command
        if bcmd == "set":
            return run_binding_set(args)
        if bcmd == "remove":
            return run_binding_remove(args)
    return 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("profile", help="Manage profiles")
    ps = p.add_subparsers(dest="profile_command", required=True)

    ps.add_parser("list", help="List all profiles")

    p_c = ps.add_parser("create", help="Create a new profile")
    p_c.add_argument("name")
    p_c.add_argument("--match", required=True, help="WM class to match (e.g. Firefox)")

    p_d = ps.add_parser("delete", help="Delete a profile")
    p_d.add_argument("name")

    p_b = ps.add_parser("binding", help="Manage profile bindings")
    bs = p_b.add_subparsers(dest="binding_command", required=True)

    p_bset = bs.add_parser("set", help="Set a binding on a profile")
    p_bset.add_argument("profile")
    p_bset.add_argument("--trigger", required=True, help="evdev event code, e.g. BTN_SIDE")
    p_bset.add_argument("--target", required=True,
                        help="target in 'kind:name' form, e.g. ring:main")

    p_brm = bs.add_parser("remove", help="Remove a binding from a profile")
    p_brm.add_argument("profile")
    p_brm.add_argument("trigger", help="evdev event code of the binding to remove")
