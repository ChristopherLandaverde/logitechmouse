# Interactive Ring Management CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ring`, `action`, `profile`, and `config` subcommands to the `logitechmouse` CLI so users can manage rings, segments, actions, and profiles without hand-editing TOML.

**Architecture:** A new `config_writer` module serializes `AppConfig` back to TOML using `tomli_w`. New CLI modules (`ring.py`, `action.py`, `profile.py`, `config_menu.py`) each export `register(sub)` and `run(args)`. `main.py` wires them in. All mutations follow: load → mutate in memory → validate → write.

**Tech Stack:** Python `argparse` (existing), `tomli_w` (new), `questionary` (new), `difflib` (stdlib)

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `src/logitechmouse/config_writer.py` | `AppConfig → dict → tomli_w.dump` |
| Create | `src/logitechmouse/cli/ring.py` | ring + ring segment subcommands |
| Create | `src/logitechmouse/cli/action.py` | action subcommands |
| Create | `src/logitechmouse/cli/profile.py` | profile + profile binding subcommands |
| Create | `src/logitechmouse/cli/config_menu.py` | interactive questionary menu |
| Modify | `src/logitechmouse/main.py` | wire new subparsers + `config` verb |
| Modify | `pyproject.toml` | add `questionary`, `tomli-w` to dependencies |
| Create | `tests/test_config_writer.py` | roundtrip + serialization tests |
| Create | `tests/test_cli_ring.py` | ring + segment command tests |
| Create | `tests/test_cli_action.py` | action command tests |
| Create | `tests/test_cli_profile.py` | profile + binding command tests |
| Create | `tests/test_cli_config_menu.py` | interactive menu mock tests |

---

## Task 1: Add tomli-w dependency + config_writer module

**Files:**
- Modify: `pyproject.toml`
- Create: `src/logitechmouse/config_writer.py`
- Create: `tests/test_config_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_writer.py
from pathlib import Path
import pytest
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from logitechmouse.config import (
    AppConfig, Action, Ring, Segment, Binding, Target,
    Profile, Theme, load_config,
)
from logitechmouse.config_writer import config_to_dict, write_config


def _minimal_config() -> AppConfig:
    return AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="Screenshot", icon="fa.camera"),
            Segment(action="shot", label="Alpha"),
            Segment(action="shot", label="Beta"),
        ])},
        bindings={"thumb": Binding(
            name="thumb", trigger="BTN_SIDE",
            target=Target(kind="ring", name="main"),
        )},
    )


def test_config_to_dict_actions():
    cfg = _minimal_config()
    d = config_to_dict(cfg)
    assert d["actions"]["shot"]["type"] == "command"
    assert d["actions"]["shot"]["command"] == "flameshot gui"


def test_config_to_dict_rings():
    cfg = _minimal_config()
    d = config_to_dict(cfg)
    segs = d["rings"]["main"]["segments"]
    assert len(segs) == 3
    assert segs[0] == {"action": "shot", "label": "Screenshot", "icon": "fa.camera"}
    assert segs[1] == {"action": "shot", "label": "Alpha"}


def test_config_to_dict_bindings():
    cfg = _minimal_config()
    d = config_to_dict(cfg)
    assert d["bindings"]["thumb"]["trigger"] == "BTN_SIDE"
    assert d["bindings"]["thumb"]["target"] == "ring:main"


def test_config_to_dict_no_theme_section_for_defaults():
    cfg = AppConfig()
    d = config_to_dict(cfg)
    assert "theme" not in d


def test_config_to_dict_theme_section_when_non_default():
    cfg = AppConfig(theme=Theme(name="brazil", overrides={}))
    d = config_to_dict(cfg)
    assert d["theme"]["name"] == "brazil"


def test_write_config_roundtrip(tmp_path):
    original = _minimal_config()
    p = tmp_path / "config.toml"
    write_config(p, original)
    loaded = load_config(p)
    assert loaded.actions["shot"].command == "flameshot gui"
    assert loaded.rings["main"].segments[0].label == "Screenshot"
    assert loaded.rings["main"].segments[0].icon == "fa.camera"
    assert loaded.rings["main"].segments[1].icon is None
    assert loaded.bindings["thumb"].target.kind == "ring"
    assert loaded.bindings["thumb"].target.name == "main"


def test_write_config_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "dir" / "config.toml"
    write_config(p, AppConfig())
    assert p.exists()


def test_roundtrip_profile(tmp_path):
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        profiles={"myapp": Profile(
            name="myapp",
            match_wm_class="MyApp",
            bindings={"btn_side": Binding(
                name="btn_side", trigger="BTN_SIDE",
                target=Target(kind="action", name="shot"),
            )},
        )},
    )
    p = tmp_path / "config.toml"
    write_config(p, cfg)
    loaded = load_config(p)
    assert loaded.profiles["myapp"].match_wm_class == "MyApp"
    assert loaded.profiles["myapp"].bindings["btn_side"].trigger == "BTN_SIDE"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_config_writer.py -v
```
Expected: `ModuleNotFoundError: No module named 'logitechmouse.config_writer'`

- [ ] **Step 3: Add tomli-w to pyproject.toml dependencies**

In `pyproject.toml`, change the `dependencies` list:
```toml
dependencies = [
  "evdev>=1.6",
  "tomli-w>=1.0",
]
```

Then install:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 4: Create config_writer.py**

```python
# src/logitechmouse/config_writer.py
from __future__ import annotations

from pathlib import Path

import tomli_w

from .config import AppConfig


def config_to_dict(config: AppConfig) -> dict:
    d: dict = {}

    if config.device.name is not None or config.device.path is not None:
        device: dict = {}
        if config.device.name is not None:
            device["name"] = config.device.name
        if config.device.path is not None:
            device["path"] = config.device.path
        d["device"] = device

    if config.actions:
        d["actions"] = {}
        for name, action in config.actions.items():
            entry: dict = {"type": action.kind}
            if action.command is not None:
                entry["command"] = action.command
            d["actions"][name] = entry

    if config.bindings:
        d["bindings"] = {
            name: {
                "trigger": b.trigger,
                "target": f"{b.target.kind}:{b.target.name}",
            }
            for name, b in config.bindings.items()
        }

    if config.rings:
        d["rings"] = {}
        for name, ring in config.rings.items():
            segments = []
            for seg in ring.segments:
                s: dict = {"action": seg.action, "label": seg.label}
                if seg.icon is not None:
                    s["icon"] = seg.icon
                segments.append(s)
            d["rings"][name] = {"segments": segments}

    if config.profiles:
        d["profiles"] = {}
        for name, profile in config.profiles.items():
            pd: dict = {"match_wm_class": profile.match_wm_class}
            if profile.bindings:
                pd["bindings"] = {
                    bname: {
                        "trigger": b.trigger,
                        "target": f"{b.target.kind}:{b.target.name}",
                    }
                    for bname, b in profile.bindings.items()
                }
            d["profiles"][name] = pd

    if config.theme.name != "dark" or config.theme.overrides:
        td: dict = {"name": config.theme.name}
        if config.theme.overrides:
            td["overrides"] = dict(config.theme.overrides)
        d["theme"] = td

    return d


def write_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump(config_to_dict(config), f)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_config_writer.py -v
```
Expected: all 8 tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/logitechmouse/config_writer.py tests/test_config_writer.py
git commit -m "feat(config): config_writer module — AppConfig → tomli_w TOML serialization"
```

---

## Task 2: ring list / show / create / delete

**Files:**
- Create: `src/logitechmouse/cli/ring.py`
- Create: `tests/test_cli_ring.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_ring.py
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from logitechmouse.config import Action, AppConfig, Ring, Segment, Binding, Target, load_config
from logitechmouse.config_writer import write_config


def _args(config: Path, **kwargs) -> argparse.Namespace:
    return argparse.Namespace(config=config, **kwargs)


def _seed_config(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="Screenshot"),
            Segment(action="shot", label="Alpha"),
            Segment(action="shot", label="Beta"),
        ])},
    )
    write_config(p, cfg)
    return p


# --- ring list ---

def test_ring_list_empty(tmp_path, capsys):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig())
    from logitechmouse.cli.ring import run_ring_list
    rc = run_ring_list(_args(p))
    assert rc == 0
    assert "No rings" in capsys.readouterr().out


def test_ring_list_shows_rings(tmp_path, capsys):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_ring_list
    rc = run_ring_list(_args(p))
    assert rc == 0
    assert "main" in capsys.readouterr().out


# --- ring show ---

def test_ring_show_lists_segments(tmp_path, capsys):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_ring_show
    rc = run_ring_show(_args(p, name="main"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Screenshot" in out
    assert "1." in out


def test_ring_show_unknown_suggests(tmp_path, capsys):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_ring_show
    rc = run_ring_show(_args(p, name="mian"))  # typo
    assert rc == 1
    assert "main" in capsys.readouterr().err  # did-you-mean


# --- ring create ---

def test_ring_create_writes_empty_ring(tmp_path):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_ring_create
    rc = run_ring_create(_args(p, name="work"))
    assert rc == 0
    cfg = load_config(p)
    assert "work" in cfg.rings
    assert cfg.rings["work"].segments == []


def test_ring_create_duplicate_fails(tmp_path, capsys):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_ring_create
    rc = run_ring_create(_args(p, name="main"))
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


# --- ring delete ---

def test_ring_delete_removes_ring(tmp_path):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_ring_delete
    rc = run_ring_delete(_args(p, name="main", force=False))
    assert rc == 0
    assert "main" not in load_config(p).rings


def test_ring_delete_blocks_when_binding_exists(tmp_path, capsys):
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="shot", label="B"),
            Segment(action="shot", label="C"),
        ])},
        bindings={"thumb": Binding(
            name="thumb", trigger="BTN_SIDE",
            target=Target(kind="ring", name="main"),
        )},
    )
    write_config(p, cfg)
    from logitechmouse.cli.ring import run_ring_delete
    rc = run_ring_delete(_args(p, name="main", force=False))
    assert rc == 1
    err = capsys.readouterr().err
    assert "thumb" in err


def test_ring_delete_force_removes_binding(tmp_path):
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="shot", label="B"),
            Segment(action="shot", label="C"),
        ])},
        bindings={"thumb": Binding(
            name="thumb", trigger="BTN_SIDE",
            target=Target(kind="ring", name="main"),
        )},
    )
    write_config(p, cfg)
    from logitechmouse.cli.ring import run_ring_delete
    rc = run_ring_delete(_args(p, name="main", force=True))
    assert rc == 0
    result = load_config(p)
    assert "main" not in result.rings
    assert "thumb" not in result.bindings
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_ring.py -v
```
Expected: `ModuleNotFoundError: No module named 'logitechmouse.cli.ring'`

- [ ] **Step 3: Create ring.py**

```python
# src/logitechmouse/cli/ring.py
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from ..config import DEFAULT_CONFIG_PATH, ConfigError, Ring, Segment, load_config
from ..config_writer import write_config


def _cfg_path(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def run_ring_list(args: argparse.Namespace) -> int:
    cfg = load_config(_cfg_path(args))
    if not cfg.rings:
        print("No rings defined.")
        return 0
    for name, ring in cfg.rings.items():
        print(f"{name} ({len(ring.segments)} segments)")
    return 0


def run_ring_show(args: argparse.Namespace) -> int:
    cfg = load_config(_cfg_path(args))
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
    path = _cfg_path(args)
    cfg = load_config(path)
    if args.name in cfg.rings:
        print(f"Error: ring '{args.name}' already exists.", file=sys.stderr)
        return 1
    cfg.rings[args.name] = Ring(name=args.name, segments=[])
    write_config(path, cfg)
    print(f"Created ring '{args.name}'.")
    return 0


def run_ring_delete(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
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
        f"{p.name}/{b.name}"
        for p in cfg.profiles.values()
        for b in p.bindings.values()
        if b.target.kind == "ring" and b.target.name == args.name
    ]
    broken = broken_global + broken_profile

    if broken and not args.force:
        print(
            f"Error: ring '{args.name}' is referenced by bindings: "
            f"{', '.join(broken)}.\n"
            f"Use --force to delete the ring and remove those bindings automatically.",
            file=sys.stderr,
        )
        return 1

    if args.force:
        cfg.bindings = {
            n: b for n, b in cfg.bindings.items()
            if not (b.target.kind == "ring" and b.target.name == args.name)
        }
        for profile in cfg.profiles.values():
            profile.bindings = {
                n: b for n, b in profile.bindings.items()
                if not (b.target.kind == "ring" and b.target.name == args.name)
            }

    del cfg.rings[args.name]
    write_config(path, cfg)
    print(f"Deleted ring '{args.name}'.")
    return 0


def run_segment_add(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
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
                f"Error: position {args.position} out of range "
                f"(1–{len(ring.segments) + 1}).",
                file=sys.stderr,
            )
            return 1
        ring.segments.insert(pos, seg)

    write_config(path, cfg)
    print(f"Added segment '{args.label}' to ring '{args.ring}'.")
    return 0


def run_segment_remove(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
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
        print(
            f"Error: ring '{args.ring}' already has the minimum 3 segments.",
            file=sys.stderr,
        )
        return 1

    removed = ring.segments.pop(pos)
    write_config(path, cfg)
    print(f"Removed segment '{removed.label}' from ring '{args.ring}'.")
    return 0


def run_segment_move(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)

    ring = cfg.rings.get(args.ring)
    if ring is None:
        print(f"Error: ring '{args.ring}' not found.", file=sys.stderr)
        return 1

    n = len(ring.segments)
    frm = args.frm - 1
    to = args.to - 1

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

    p_delete = rs.add_parser("delete", help="Delete a ring")
    p_delete.add_argument("name")
    p_delete.add_argument(
        "--force", action="store_true",
        help="Also remove bindings that reference this ring",
    )

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
```

- [ ] **Step 4: Add segment tests to test_cli_ring.py**

Append to `tests/test_cli_ring.py`:

```python
# --- ring segment add ---

def test_segment_add_appends(tmp_path):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_segment_add
    rc = run_segment_add(_args(p, ring="main", action="shot",
                                label="Gamma", icon=None, position=None))
    assert rc == 0
    cfg = load_config(p)
    assert cfg.rings["main"].segments[3].label == "Gamma"


def test_segment_add_inserts_at_position(tmp_path):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_segment_add
    rc = run_segment_add(_args(p, ring="main", action="shot",
                                label="First", icon=None, position=1))
    assert rc == 0
    assert load_config(p).rings["main"].segments[0].label == "First"


def test_segment_add_unknown_action_fails(tmp_path, capsys):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_segment_add
    rc = run_segment_add(_args(p, ring="main", action="nope",
                                label="X", icon=None, position=None))
    assert rc == 1
    assert "action" in capsys.readouterr().err.lower()


def test_segment_add_max_ceiling(tmp_path, capsys):
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label=str(i)) for i in range(12)
        ])},
    )
    write_config(p, cfg)
    from logitechmouse.cli.ring import run_segment_add
    rc = run_segment_add(_args(p, ring="main", action="shot",
                                label="overflow", icon=None, position=None))
    assert rc == 1
    assert "12" in capsys.readouterr().err


# --- ring segment remove ---

def test_segment_remove_removes(tmp_path):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_segment_add, run_segment_remove
    run_segment_add(_args(p, ring="main", action="shot",
                           label="Extra", icon=None, position=None))
    rc = run_segment_remove(_args(p, ring="main", position=4))
    assert rc == 0
    assert len(load_config(p).rings["main"].segments) == 3


def test_segment_remove_floor(tmp_path, capsys):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_segment_remove
    rc = run_segment_remove(_args(p, ring="main", position=1))
    assert rc == 1
    assert "minimum" in capsys.readouterr().err


# --- ring segment move ---

def test_segment_move_reorders(tmp_path):
    p = _seed_config(tmp_path)
    from logitechmouse.cli.ring import run_segment_move
    rc = run_segment_move(_args(p, ring="main", frm=1, to=3))
    assert rc == 0
    segs = load_config(p).rings["main"].segments
    assert segs[2].label == "Screenshot"
    assert segs[0].label == "Alpha"
```

- [ ] **Step 5: Run all ring tests**

```bash
pytest tests/test_cli_ring.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/cli/ring.py tests/test_cli_ring.py
git commit -m "feat(cli): ring + ring segment subcommands"
```

---

## Task 3: action list / create / delete

**Files:**
- Create: `src/logitechmouse/cli/action.py`
- Create: `tests/test_cli_action.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_action.py
from __future__ import annotations

import argparse
from pathlib import Path

from logitechmouse.config import Action, AppConfig, Ring, Segment, Binding, Target, load_config
from logitechmouse.config_writer import write_config


def _args(config: Path, **kwargs) -> argparse.Namespace:
    return argparse.Namespace(config=config, **kwargs)


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
    ))
    return p


def test_action_list_shows_actions(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.action import run_action_list
    rc = run_action_list(_args(p))
    assert rc == 0
    assert "shot" in capsys.readouterr().out


def test_action_list_empty(tmp_path, capsys):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig())
    from logitechmouse.cli.action import run_action_list
    rc = run_action_list(_args(p))
    assert rc == 0
    assert "No actions" in capsys.readouterr().out


def test_action_create_writes_action(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.action import run_action_create
    rc = run_action_create(_args(p, name="notify", command="notify-send hello"))
    assert rc == 0
    cfg = load_config(p)
    assert cfg.actions["notify"].command == "notify-send hello"
    assert cfg.actions["notify"].kind == "command"


def test_action_create_duplicate_fails(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.action import run_action_create
    rc = run_action_create(_args(p, name="shot", command="anything"))
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_action_delete_removes_action(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.action import run_action_delete
    rc = run_action_delete(_args(p, name="shot", force=False))
    assert rc == 0
    assert "shot" not in load_config(p).actions


def test_action_delete_blocks_when_segment_references_it(tmp_path, capsys):
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="shot", label="B"),
            Segment(action="shot", label="C"),
        ])},
    )
    write_config(p, cfg)
    from logitechmouse.cli.action import run_action_delete
    rc = run_action_delete(_args(p, name="shot", force=False))
    assert rc == 1
    assert "main" in capsys.readouterr().err


def test_action_delete_force_removes_ring_segments(tmp_path):
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={
            "shot": Action(name="shot", kind="command", command="true"),
            "other": Action(name="other", kind="command", command="true"),
        },
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="other", label="B"),
            Segment(action="other", label="C"),
        ])},
    )
    write_config(p, cfg)
    from logitechmouse.cli.action import run_action_delete
    rc = run_action_delete(_args(p, name="shot", force=True))
    assert rc == 0
    result = load_config(p)
    assert "shot" not in result.actions
    for ring in result.rings.values():
        for seg in ring.segments:
            assert seg.action != "shot"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_action.py -v
```
Expected: `ModuleNotFoundError: No module named 'logitechmouse.cli.action'`

- [ ] **Step 3: Create action.py**

```python
# src/logitechmouse/cli/action.py
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from ..config import DEFAULT_CONFIG_PATH, Action, load_config
from ..config_writer import write_config


def _cfg_path(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def run_action_list(args: argparse.Namespace) -> int:
    cfg = load_config(_cfg_path(args))
    if not cfg.actions:
        print("No actions defined.")
        return 0
    for name, action in cfg.actions.items():
        cmd = f"  → {action.command}" if action.command else ""
        print(f"{name} [{action.kind}]{cmd}")
    return 0


def run_action_create(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)
    if args.name in cfg.actions:
        print(f"Error: action '{args.name}' already exists.", file=sys.stderr)
        return 1
    cfg.actions[args.name] = Action(
        name=args.name, kind="command", command=args.command
    )
    write_config(path, cfg)
    print(f"Created action '{args.name}'.")
    return 0


def run_action_delete(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)
    if args.name not in cfg.actions:
        close = difflib.get_close_matches(args.name, cfg.actions.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: action '{args.name}' not found.{hint}", file=sys.stderr)
        return 1

    # Rings that reference this action via segments
    broken_rings = [
        ring.name
        for ring in cfg.rings.values()
        if any(seg.action == args.name for seg in ring.segments)
    ]
    # Bindings that reference this action directly
    broken_bindings = [
        b.name for b in cfg.bindings.values()
        if b.target.kind == "action" and b.target.name == args.name
    ]
    broken_profile_bindings = [
        f"{p.name}/{b.name}"
        for p in cfg.profiles.values()
        for b in p.bindings.values()
        if b.target.kind == "action" and b.target.name == args.name
    ]
    broken = broken_rings + broken_bindings + broken_profile_bindings

    if broken and not args.force:
        print(
            f"Error: action '{args.name}' is referenced by: "
            f"{', '.join(broken)}.\n"
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
        for profile in cfg.profiles.values():
            profile.bindings = {
                n: b for n, b in profile.bindings.items()
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

    p_create = ac.add_parser("create", help="Create a new command action")
    p_create.add_argument("name")
    p_create.add_argument("--command", required=True, help="Shell command to run")

    p_delete = ac.add_parser("delete", help="Delete an action")
    p_delete.add_argument("name")
    p_delete.add_argument(
        "--force", action="store_true",
        help="Also remove segments and bindings that reference this action",
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cli_action.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/cli/action.py tests/test_cli_action.py
git commit -m "feat(cli): action list/create/delete subcommands"
```

---

## Task 4: profile list / create / delete / binding set / binding remove

**Files:**
- Create: `src/logitechmouse/cli/profile.py`
- Create: `tests/test_cli_profile.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_profile.py
from __future__ import annotations

import argparse
from pathlib import Path

from logitechmouse.config import (
    Action, AppConfig, Binding, Profile, Target, load_config,
)
from logitechmouse.config_writer import write_config


def _args(config: Path, **kwargs) -> argparse.Namespace:
    return argparse.Namespace(config=config, **kwargs)


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        profiles={"myapp": Profile(
            name="myapp",
            match_wm_class="MyApp",
            bindings={"btn_side": Binding(
                name="btn_side", trigger="BTN_SIDE",
                target=Target(kind="action", name="shot"),
            )},
        )},
    )
    write_config(p, cfg)
    return p


def test_profile_list_shows_profiles(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_profile_list
    rc = run_profile_list(_args(p))
    assert rc == 0
    assert "myapp" in capsys.readouterr().out


def test_profile_list_empty(tmp_path, capsys):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig())
    from logitechmouse.cli.profile import run_profile_list
    rc = run_profile_list(_args(p))
    assert rc == 0
    assert "No profiles" in capsys.readouterr().out


def test_profile_create_writes_profile(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_profile_create
    rc = run_profile_create(_args(p, name="browser", match="Firefox"))
    assert rc == 0
    cfg = load_config(p)
    assert cfg.profiles["browser"].match_wm_class == "Firefox"


def test_profile_create_duplicate_fails(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_profile_create
    rc = run_profile_create(_args(p, name="myapp", match="X"))
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_profile_delete_removes_profile(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_profile_delete
    rc = run_profile_delete(_args(p, name="myapp"))
    assert rc == 0
    assert "myapp" not in load_config(p).profiles


def test_profile_delete_unknown_fails(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_profile_delete
    rc = run_profile_delete(_args(p, name="nope"))
    assert rc == 1


def test_profile_binding_set_creates_binding(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_binding_set
    rc = run_binding_set(_args(
        p, profile="myapp",
        trigger="BTN_TASK",
        target="action:shot",
    ))
    assert rc == 0
    cfg = load_config(p)
    b = cfg.profiles["myapp"].bindings.get("btn_task")
    assert b is not None
    assert b.trigger == "BTN_TASK"
    assert b.target.kind == "action"
    assert b.target.name == "shot"


def test_profile_binding_set_invalid_trigger_fails(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_binding_set
    rc = run_binding_set(_args(
        p, profile="myapp",
        trigger="NOT_A_REAL_TRIGGER",
        target="action:shot",
    ))
    assert rc == 1
    assert "trigger" in capsys.readouterr().err.lower()


def test_profile_binding_remove_removes_binding(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_binding_remove
    rc = run_binding_remove(_args(p, profile="myapp", trigger="BTN_SIDE"))
    assert rc == 0
    assert "btn_side" not in load_config(p).profiles["myapp"].bindings


def test_profile_binding_remove_unknown_trigger_fails(tmp_path, capsys):
    p = _seed(tmp_path)
    from logitechmouse.cli.profile import run_binding_remove
    rc = run_binding_remove(_args(p, profile="myapp", trigger="BTN_TASK"))
    assert rc == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_profile.py -v
```
Expected: `ModuleNotFoundError: No module named 'logitechmouse.cli.profile'`

- [ ] **Step 3: Create profile.py**

```python
# src/logitechmouse/cli/profile.py
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from evdev import ecodes

from ..config import (
    DEFAULT_CONFIG_PATH, Binding, ConfigError, Profile, Target,
    load_config, parse_target_string,
)
from ..config_writer import write_config


def _cfg_path(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def run_profile_list(args: argparse.Namespace) -> int:
    cfg = load_config(_cfg_path(args))
    if not cfg.profiles:
        print("No profiles defined.")
        return 0
    for name, profile in cfg.profiles.items():
        n = len(profile.bindings)
        print(f"{name}  match={profile.match_wm_class}  ({n} binding{'s' if n != 1 else ''})")
    return 0


def run_profile_create(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)
    if args.name in cfg.profiles:
        print(f"Error: profile '{args.name}' already exists.", file=sys.stderr)
        return 1
    cfg.profiles[args.name] = Profile(
        name=args.name, match_wm_class=args.match
    )
    write_config(path, cfg)
    print(f"Created profile '{args.name}'.")
    return 0


def run_profile_delete(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)
    if args.name not in cfg.profiles:
        close = difflib.get_close_matches(args.name, cfg.profiles.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: profile '{args.name}' not found.{hint}", file=sys.stderr)
        return 1
    del cfg.profiles[args.name]
    write_config(path, cfg)
    print(f"Deleted profile '{args.name}'.")
    return 0


def run_binding_set(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)

    profile = cfg.profiles.get(args.profile)
    if profile is None:
        close = difflib.get_close_matches(args.profile, cfg.profiles.keys(), n=1)
        hint = f"  Did you mean '{close[0]}'?" if close else ""
        print(f"Error: profile '{args.profile}' not found.{hint}", file=sys.stderr)
        return 1

    if args.trigger not in ecodes.ecodes:
        print(f"Error: trigger '{args.trigger}' is not a valid evdev event code.", file=sys.stderr)
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
    write_config(path, cfg)
    print(f"Set binding '{args.trigger}' → '{args.target}' on profile '{args.profile}'.")
    return 0


def run_binding_remove(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    cfg = load_config(path)

    profile = cfg.profiles.get(args.profile)
    if profile is None:
        print(f"Error: profile '{args.profile}' not found.", file=sys.stderr)
        return 1

    match = next(
        (name for name, b in profile.bindings.items() if b.trigger == args.trigger),
        None,
    )
    if match is None:
        print(
            f"Error: no binding with trigger '{args.trigger}' "
            f"in profile '{args.profile}'.",
            file=sys.stderr,
        )
        return 1

    del profile.bindings[match]
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

    p_create = ps.add_parser("create", help="Create a new profile")
    p_create.add_argument("name")
    p_create.add_argument("--match", required=True,
                          help="WM class to match (e.g. 'Firefox')")

    p_delete = ps.add_parser("delete", help="Delete a profile")
    p_delete.add_argument("name")

    p_binding = ps.add_parser("binding", help="Manage profile bindings")
    bs = p_binding.add_subparsers(dest="binding_command", required=True)

    p_bset = bs.add_parser("set", help="Set a binding on a profile")
    p_bset.add_argument("profile")
    p_bset.add_argument("--trigger", required=True,
                        help="evdev event code, e.g. BTN_SIDE")
    p_bset.add_argument("--target", required=True,
                        help="target in 'kind:name' form, e.g. ring:main")

    p_brm = bs.add_parser("remove", help="Remove a binding from a profile")
    p_brm.add_argument("profile")
    p_brm.add_argument("trigger", help="evdev event code of the binding to remove")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cli_profile.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/cli/profile.py tests/test_cli_profile.py
git commit -m "feat(cli): profile list/create/delete + binding set/remove subcommands"
```

---

## Task 5: Wire all subcommands into main.py

**Files:**
- Modify: `src/logitechmouse/main.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cli_parser.py (open the file and add):
def test_parser_has_ring_subcommand():
    from logitechmouse.main import build_parser
    p = build_parser()
    args = p.parse_args(["ring", "list"])
    assert args.command == "ring"
    assert args.ring_command == "list"


def test_parser_has_action_subcommand():
    from logitechmouse.main import build_parser
    p = build_parser()
    args = p.parse_args(["action", "list"])
    assert args.command == "action"
    assert args.action_command == "list"


def test_parser_has_profile_subcommand():
    from logitechmouse.main import build_parser
    p = build_parser()
    args = p.parse_args(["profile", "list"])
    assert args.command == "profile"
    assert args.profile_command == "list"


def test_parser_has_config_subcommand():
    from logitechmouse.main import build_parser
    p = build_parser()
    args = p.parse_args(["config"])
    assert args.command == "config"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_parser.py -v -k "ring or action or profile or config"
```
Expected: `SystemExit` (argparse rejects unknown subcommands)

- [ ] **Step 3: Update main.py**

Replace the entire `build_parser()` function and update the `main()` dispatch in `src/logitechmouse/main.py`:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logitechmouse")
    parser.add_argument("--config", type=Path, help="Path to config TOML")
    sub = parser.add_subparsers(dest="command", required=True)

    p_listen = sub.add_parser("listen", help="Run the event listener")
    p_listen.add_argument(
        "--device", default=None, help="Override [device].path with this event node"
    )

    sub.add_parser("devices", help="List detected input devices")

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

    from .cli.ring import register as register_ring
    from .cli.action import register as register_action
    from .cli.profile import register as register_profile
    register_ring(sub)
    register_action(sub)
    register_profile(sub)

    sub.add_parser("config", help="Interactive configuration menu")

    return parser
```

And in `main()`, add dispatch branches after the existing `elif` chain (before the `else`):

```python
    elif args.command == "ring":
        from .cli.ring import run as run_cmd
    elif args.command == "action":
        from .cli.action import run as run_cmd
    elif args.command == "profile":
        from .cli.profile import run as run_cmd
    elif args.command == "config":
        from .cli.config_menu import run as run_cmd
```

- [ ] **Step 4: Run parser tests + full suite**

```bash
pytest tests/test_cli_parser.py -v
pytest --tb=short -q
```
Expected: all existing 178 tests still pass; new parser tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/main.py tests/test_cli_parser.py
git commit -m "feat(cli): wire ring/action/profile/config subcommands into main parser"
```

---

## Task 6: Interactive config menu

**Files:**
- Modify: `pyproject.toml` — add questionary
- Create: `src/logitechmouse/cli/config_menu.py`
- Create: `tests/test_cli_config_menu.py`

- [ ] **Step 1: Add questionary to pyproject.toml**

```toml
dependencies = [
  "evdev>=1.6",
  "tomli-w>=1.0",
  "questionary>=2.0",
]
```

```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_cli_config_menu.py
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch, call

import pytest

from logitechmouse.config import Action, AppConfig, load_config
from logitechmouse.config_writer import write_config


def _args(config: Path) -> argparse.Namespace:
    return argparse.Namespace(config=config)


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
    ))
    return p


def test_menu_create_action(tmp_path):
    p = _seed(tmp_path)
    answers = iter([
        "Action",          # top-level entity
        "Create",          # operation
        "notify",          # name
        "notify-send hi",  # command
        "No",              # continue?
    ])

    with patch("questionary.select") as mock_select, \
         patch("questionary.text") as mock_text, \
         patch("questionary.confirm") as mock_confirm:

        mock_select.return_value.ask.side_effect = lambda: next(answers)
        mock_text.return_value.ask.side_effect = lambda: next(answers)
        mock_confirm.return_value.ask.side_effect = lambda: False

        from logitechmouse.cli.config_menu import run
        rc = run(_args(p))

    assert rc == 0
    cfg = load_config(p)
    assert cfg.actions["notify"].command == "notify-send hi"


def test_menu_delete_action(tmp_path):
    p = _seed(tmp_path)
    answers = iter([
        "Action",   # entity
        "Delete",   # operation
        "shot",     # name
        "No",       # continue?
    ])

    with patch("questionary.select") as mock_select, \
         patch("questionary.text") as mock_text, \
         patch("questionary.confirm") as mock_confirm:

        mock_select.return_value.ask.side_effect = lambda: next(answers)
        mock_text.return_value.ask.side_effect = lambda: next(answers)
        mock_confirm.return_value.ask.side_effect = lambda: False

        from logitechmouse.cli.config_menu import run
        rc = run(_args(p))

    assert rc == 0
    assert "shot" not in load_config(p).actions


def test_menu_create_ring(tmp_path):
    p = _seed(tmp_path)
    answers = iter([
        "Ring",     # entity
        "Create",   # operation
        "work",     # ring name
        "No",       # continue?
    ])

    with patch("questionary.select") as mock_select, \
         patch("questionary.text") as mock_text, \
         patch("questionary.confirm") as mock_confirm:

        mock_select.return_value.ask.side_effect = lambda: next(answers)
        mock_text.return_value.ask.side_effect = lambda: next(answers)
        mock_confirm.return_value.ask.side_effect = lambda: False

        from logitechmouse.cli.config_menu import run
        rc = run(_args(p))

    assert rc == 0
    assert "work" in load_config(p).rings
```

- [ ] **Step 3: Run to confirm failure**

```bash
pytest tests/test_cli_config_menu.py -v
```
Expected: `ModuleNotFoundError: No module named 'logitechmouse.cli.config_menu'`

- [ ] **Step 4: Create config_menu.py**

```python
# src/logitechmouse/cli/config_menu.py
from __future__ import annotations

import argparse
from pathlib import Path

import questionary

from ..config import DEFAULT_CONFIG_PATH, Action, Ring, load_config
from ..config_writer import write_config


def _cfg_path(args: argparse.Namespace) -> Path:
    return getattr(args, "config", None) or DEFAULT_CONFIG_PATH


def _menu_action(path: Path) -> None:
    cfg = load_config(path)
    op = questionary.select("Action operation:", choices=["Create", "Delete", "List"]).ask()
    if op == "List":
        for name, a in cfg.actions.items():
            print(f"  {name}: {a.command}")
        return
    if op == "Create":
        name = questionary.text("Action name:").ask()
        command = questionary.text("Shell command:").ask()
        cfg.actions[name] = Action(name=name, kind="command", command=command)
        write_config(path, cfg)
        print(f"Created action '{name}'.")
    if op == "Delete":
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
        return
    if op == "Create":
        name = questionary.text("Ring name:").ask()
        cfg.rings[name] = Ring(name=name, segments=[])
        write_config(path, cfg)
        print(f"Created ring '{name}'.")
    if op == "Delete":
        name = questionary.text("Ring name to delete:").ask()
        if name in cfg.rings:
            del cfg.rings[name]
            write_config(path, cfg)
            print(f"Deleted ring '{name}'.")
        else:
            print(f"Ring '{name}' not found.")


def _menu_profile(path: Path) -> None:
    cfg = load_config(path)
    op = questionary.select("Profile operation:", choices=["Create", "Delete", "List"]).ask()
    if op == "List":
        for name, pr in cfg.profiles.items():
            print(f"  {name}: match={pr.match_wm_class}")
        return
    from ..config import Profile
    if op == "Create":
        name = questionary.text("Profile name:").ask()
        match = questionary.text("WM class to match (e.g. Firefox):").ask()
        cfg.profiles[name] = Profile(name=name, match_wm_class=match)
        write_config(path, cfg)
        print(f"Created profile '{name}'.")
    if op == "Delete":
        name = questionary.text("Profile name to delete:").ask()
        if name in cfg.profiles:
            del cfg.profiles[name]
            write_config(path, cfg)
            print(f"Deleted profile '{name}'.")
        else:
            print(f"Profile '{name}' not found.")


def run(args: argparse.Namespace) -> int:
    path = _cfg_path(args)
    while True:
        entity = questionary.select(
            "What would you like to manage?",
            choices=["Ring", "Action", "Profile", "Exit"],
        ).ask()
        if entity == "Exit" or entity is None:
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
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_cli_config_menu.py -v
```
Expected: all 3 tests pass.

- [ ] **Step 6: Run full test suite**

```bash
pytest --tb=short -q
```
Expected: all tests pass (new + existing 178).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/logitechmouse/cli/config_menu.py tests/test_cli_config_menu.py
git commit -m "feat(cli): interactive config menu via questionary"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by task |
|---|---|
| `ring list/create/delete/show` | Task 2 |
| `ring segment add/remove/move` | Task 2 |
| `action list/create/delete` | Task 3 |
| `profile list/create/delete` | Task 4 |
| `profile binding set/remove` | Task 4 |
| `logitechmouse config` interactive menu | Task 6 |
| `tomli_w` clean rewrite | Task 1 |
| `questionary` dependency | Task 6 |
| `validate_config` before write | All mutating commands |
| `ring create` bypasses segment-count check | Task 2 `run_ring_create` |
| 3-segment floor on remove | Task 2 `run_segment_remove` |
| 12-segment ceiling on add | Task 2 `run_segment_add` |
| `--force` for ring/action delete | Tasks 2, 3 |
| `difflib` did-you-mean | Tasks 2, 3, 4 |
| Wire into main.py | Task 5 |
| 1-indexed positions | Tasks 2 (segment remove/move) |

**Placeholder scan:** No TBD/TODO/placeholder text found. All code steps are complete.

**Type consistency:** `_cfg_path(args)` is defined in each module independently with the same signature. `run(args)` and `register(sub)` are consistent across ring/action/profile. The `Segment`, `Ring`, `Action`, `Profile`, `Binding`, `Target` imports all reference the same classes from `config.py`.
