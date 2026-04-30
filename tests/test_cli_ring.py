from __future__ import annotations

import argparse
from pathlib import Path

from logitechmouse.config import Action, AppConfig, Binding, Ring, Segment, Target, load_config
from logitechmouse.config_writer import write_config


def _args(config: Path, **kw) -> argparse.Namespace:
    return argparse.Namespace(config=config, **kw)


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="Screenshot"),
            Segment(action="shot", label="Alpha"),
            Segment(action="shot", label="Beta"),
        ])},
    ))
    return p


def test_ring_list_empty(tmp_path, capsys):
    p = tmp_path / "c.toml"
    write_config(p, AppConfig())
    from logitechmouse.cli.ring import run_ring_list
    assert run_ring_list(_args(p)) == 0
    assert "No rings" in capsys.readouterr().out


def test_ring_list_shows_names(tmp_path, capsys):
    from logitechmouse.cli.ring import run_ring_list
    assert run_ring_list(_args(_seed(tmp_path))) == 0
    assert "main" in capsys.readouterr().out


def test_ring_show_lists_segments(tmp_path, capsys):
    from logitechmouse.cli.ring import run_ring_show
    assert run_ring_show(_args(_seed(tmp_path), name="main")) == 0
    out = capsys.readouterr().out
    assert "Screenshot" in out and "1." in out


def test_ring_show_typo_suggests(tmp_path, capsys):
    from logitechmouse.cli.ring import run_ring_show
    assert run_ring_show(_args(_seed(tmp_path), name="mian")) == 1
    assert "main" in capsys.readouterr().err


def test_ring_create_writes_empty_ring(tmp_path):
    from logitechmouse.cli.ring import run_ring_create
    p = _seed(tmp_path)
    assert run_ring_create(_args(p, name="work")) == 0
    cfg = load_config(p)
    assert "work" in cfg.rings and cfg.rings["work"].segments == []


def test_ring_create_duplicate_fails(tmp_path, capsys):
    from logitechmouse.cli.ring import run_ring_create
    assert run_ring_create(_args(_seed(tmp_path), name="main")) == 1
    assert "already exists" in capsys.readouterr().err


def test_ring_delete_removes(tmp_path):
    from logitechmouse.cli.ring import run_ring_delete
    p = _seed(tmp_path)
    assert run_ring_delete(_args(p, name="main", force=False)) == 0
    assert "main" not in load_config(p).rings


def test_ring_delete_blocks_when_referenced(tmp_path, capsys):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="shot", label="B"),
            Segment(action="shot", label="C"),
        ])},
        bindings={"thumb": Binding(name="thumb", trigger="BTN_SIDE",
                                   target=Target(kind="ring", name="main"))},
    ))
    from logitechmouse.cli.ring import run_ring_delete
    assert run_ring_delete(_args(p, name="main", force=False)) == 1
    assert "thumb" in capsys.readouterr().err


def test_ring_delete_force_removes_bindings(tmp_path):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="shot", label="B"),
            Segment(action="shot", label="C"),
        ])},
        bindings={"thumb": Binding(name="thumb", trigger="BTN_SIDE",
                                   target=Target(kind="ring", name="main"))},
    ))
    from logitechmouse.cli.ring import run_ring_delete
    assert run_ring_delete(_args(p, name="main", force=True)) == 0
    r = load_config(p)
    assert "main" not in r.rings and "thumb" not in r.bindings


def test_segment_add_appends(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.ring import run_segment_add
    assert run_segment_add(_args(p, ring="main", action="shot",
                                  label="Gamma", icon=None, position=None)) == 0
    assert load_config(p).rings["main"].segments[3].label == "Gamma"


def test_segment_add_at_position(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.ring import run_segment_add
    assert run_segment_add(_args(p, ring="main", action="shot",
                                  label="First", icon=None, position=1)) == 0
    assert load_config(p).rings["main"].segments[0].label == "First"


def test_segment_add_unknown_action_fails(tmp_path, capsys):
    from logitechmouse.cli.ring import run_segment_add
    assert run_segment_add(_args(_seed(tmp_path), ring="main", action="nope",
                                  label="X", icon=None, position=None)) == 1


def test_segment_add_ceiling(tmp_path, capsys):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label=str(i)) for i in range(12)
        ])},
    ))
    from logitechmouse.cli.ring import run_segment_add
    assert run_segment_add(_args(p, ring="main", action="shot",
                                  label="over", icon=None, position=None)) == 1
    assert "12" in capsys.readouterr().err


def test_segment_remove_succeeds(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.ring import run_segment_add, run_segment_remove
    run_segment_add(_args(p, ring="main", action="shot", label="D", icon=None, position=None))
    assert run_segment_remove(_args(p, ring="main", position=4)) == 0
    assert len(load_config(p).rings["main"].segments) == 3


def test_segment_remove_floor(tmp_path, capsys):
    from logitechmouse.cli.ring import run_segment_remove
    assert run_segment_remove(_args(_seed(tmp_path), ring="main", position=1)) == 1
    assert "minimum" in capsys.readouterr().err


def test_segment_move_reorders(tmp_path):
    p = _seed(tmp_path)
    from logitechmouse.cli.ring import run_segment_move
    assert run_segment_move(_args(p, ring="main", frm=1, to=3)) == 0
    segs = load_config(p).rings["main"].segments
    assert segs[2].label == "Screenshot"
    assert segs[0].label == "Alpha"
