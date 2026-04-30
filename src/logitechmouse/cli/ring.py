from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from ..config import DEFAULT_CONFIG_PATH, Ring, Segment, load_config
from ..config_writer import write_config


def _p(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def run_ring_list(args: argparse.Namespace) -> int:
    cfg = load_config(_p(args))
    if not cfg.rings:
        print("No rings defined.")
        return 0
    for name, ring in cfg.rings.items():
        print(f"{name} ({len(ring.segments)} segments)")
    return 0


def run_ring_show(args: argparse.Namespace) -> int:
    cfg = load_config(_p(args))
    ring = cfg.rings.get(args.name)
    if ring is None:
        close = difflib.get_close_matches(args.name, cfg.rings.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: ring '{args.name}' not found.{hint}", file=sys.stderr)
        return 1
    print(f"Ring: {ring.name} ({len(ring.segments)} segments)")
    for i, seg in enumerate(ring.segments, 1):
        icon = f" [{seg.icon}]" if seg.icon else ""
        print(f"  {i}. {seg.label}{icon} → {seg.action}")
    return 0


def run_ring_create(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    if args.name in cfg.rings:
        print(f"Error: ring '{args.name}' already exists.", file=sys.stderr)
        return 1
    cfg.rings[args.name] = Ring(name=args.name, segments=[])
    write_config(path, cfg)
    print(f"Created ring '{args.name}'.")
    return 0


def run_ring_delete(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    if args.name not in cfg.rings:
        close = difflib.get_close_matches(args.name, cfg.rings.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: ring '{args.name}' not found.{hint}", file=sys.stderr)
        return 1
    broken_global = [
        b.name for b in cfg.bindings.values()
        if b.target.kind == "ring" and b.target.name == args.name
    ]
    broken_profile = [
        f"{prof.name}/{b.name}"
        for prof in cfg.profiles.values()
        for b in prof.bindings.values()
        if b.target.kind == "ring" and b.target.name == args.name
    ]
    broken = broken_global + broken_profile
    if broken and not args.force:
        print(
            f"Error: ring '{args.name}' is referenced by bindings: {', '.join(broken)}.\n"
            f"Use --force to delete the ring and remove those bindings automatically.",
            file=sys.stderr,
        )
        return 1
    if args.force:
        cfg.bindings = {
            n: b for n, b in cfg.bindings.items()
            if not (b.target.kind == "ring" and b.target.name == args.name)
        }
        for prof in cfg.profiles.values():
            prof.bindings = {
                n: b for n, b in prof.bindings.items()
                if not (b.target.kind == "ring" and b.target.name == args.name)
            }
    del cfg.rings[args.name]
    write_config(path, cfg)
    print(f"Deleted ring '{args.name}'.")
    return 0


def run_segment_add(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    ring = cfg.rings.get(args.ring)
    if ring is None:
        close = difflib.get_close_matches(args.ring, cfg.rings.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: ring '{args.ring}' not found.{hint}", file=sys.stderr)
        return 1
    if args.action not in cfg.actions:
        close = difflib.get_close_matches(args.action, cfg.actions.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: action '{args.action}' not found.{hint}", file=sys.stderr)
        return 1
    if len(ring.segments) >= 12:
        print(f"Error: ring '{args.ring}' already has the maximum 12 segments.", file=sys.stderr)
        return 1
    seg = Segment(action=args.action, label=args.label, icon=args.icon)
    if args.position is None:
        ring.segments.append(seg)
    else:
        pos = args.position - 1
        if not (0 <= pos <= len(ring.segments)):
            print(
                f"Error: position {args.position} out of range (1–{len(ring.segments) + 1}).",
                file=sys.stderr,
            )
            return 1
        ring.segments.insert(pos, seg)
    write_config(path, cfg)
    print(f"Added segment '{args.label}' to ring '{args.ring}'.")
    return 0


def run_segment_remove(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    ring = cfg.rings.get(args.ring)
    if ring is None:
        print(f"Error: ring '{args.ring}' not found.", file=sys.stderr)
        return 1
    pos = args.position - 1
    if not (0 <= pos < len(ring.segments)):
        print(
            f"Error: position {args.position} out of range (1–{len(ring.segments)}).",
            file=sys.stderr,
        )
        return 1
    if len(ring.segments) <= 3:
        print(f"Error: ring '{args.ring}' already has the minimum 3 segments.", file=sys.stderr)
        return 1
    removed = ring.segments.pop(pos)
    write_config(path, cfg)
    print(f"Removed segment '{removed.label}' from ring '{args.ring}'.")
    return 0


def run_segment_move(args: argparse.Namespace) -> int:
    path = _p(args)
    cfg = load_config(path)
    ring = cfg.rings.get(args.ring)
    if ring is None:
        print(f"Error: ring '{args.ring}' not found.", file=sys.stderr)
        return 1
    n = len(ring.segments)
    frm, to = args.frm - 1, args.to - 1
    if not (0 <= frm < n):
        print(f"Error: from-position {args.frm} out of range (1–{n}).", file=sys.stderr)
        return 1
    if not (0 <= to < n):
        print(f"Error: to-position {args.to} out of range (1–{n}).", file=sys.stderr)
        return 1
    seg = ring.segments.pop(frm)
    ring.segments.insert(to, seg)
    write_config(path, cfg)
    print(f"Moved segment to position {args.to} in ring '{args.ring}'.")
    return 0


def run(args: argparse.Namespace) -> int:
    cmd = args.ring_command
    if cmd == "list":
        return run_ring_list(args)
    if cmd == "show":
        return run_ring_show(args)
    if cmd == "create":
        return run_ring_create(args)
    if cmd == "delete":
        return run_ring_delete(args)
    if cmd == "segment":
        scmd = args.segment_command
        if scmd == "add":
            return run_segment_add(args)
        if scmd == "remove":
            return run_segment_remove(args)
        if scmd == "move":
            return run_segment_move(args)
    return 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ring", help="Manage rings")
    rs = p.add_subparsers(dest="ring_command", required=True)

    rs.add_parser("list", help="List all rings")

    p_show = rs.add_parser("show", help="Show segments in a ring")
    p_show.add_argument("name")

    p_create = rs.add_parser("create", help="Create a new empty ring")
    p_create.add_argument("name")

    p_del = rs.add_parser("delete", help="Delete a ring")
    p_del.add_argument("name")
    p_del.add_argument("--force", action="store_true",
                       help="Also remove bindings that reference this ring")

    p_seg = rs.add_parser("segment", help="Manage ring segments")
    ss = p_seg.add_subparsers(dest="segment_command", required=True)

    p_add = ss.add_parser("add", help="Add a segment to a ring")
    p_add.add_argument("ring")
    p_add.add_argument("--action", required=True)
    p_add.add_argument("--label", required=True)
    p_add.add_argument("--icon", default=None)
    p_add.add_argument("--position", type=int, default=None,
                       help="1-indexed insert position (default: append)")

    p_rm = ss.add_parser("remove", help="Remove a segment (1-indexed position)")
    p_rm.add_argument("ring")
    p_rm.add_argument("position", type=int)

    p_mv = ss.add_parser("move", help="Move a segment (1-indexed positions)")
    p_mv.add_argument("ring")
    p_mv.add_argument("frm", type=int, metavar="from")
    p_mv.add_argument("to", type=int)
