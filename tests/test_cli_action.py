from __future__ import annotations

import argparse
from pathlib import Path

from logitechmouse.config import Action, AppConfig, Ring, Segment, load_config
from logitechmouse.config_writer import write_config


def _args(config: Path, **kw) -> argparse.Namespace:
    return argparse.Namespace(config=config, **kw)


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
    ))
    return p


def test_action_list_shows(tmp_path, capsys):
    from logitechmouse.cli.action import run_action_list
    assert run_action_list(_args(_seed(tmp_path))) == 0
    assert "shot" in capsys.readouterr().out


def test_action_list_empty(tmp_path, capsys):
    p = tmp_path / "c.toml"
    write_config(p, AppConfig())
    from logitechmouse.cli.action import run_action_list
    assert run_action_list(_args(p)) == 0
    assert "No actions" in capsys.readouterr().out


def test_action_create_writes(tmp_path):
    from logitechmouse.cli.action import run_action_create
    p = _seed(tmp_path)
    assert run_action_create(_args(p, name="notify", command="notify-send hi")) == 0
    cfg = load_config(p)
    assert cfg.actions["notify"].command == "notify-send hi"
    assert cfg.actions["notify"].kind == "command"


def test_action_create_duplicate_fails(tmp_path, capsys):
    from logitechmouse.cli.action import run_action_create
    assert run_action_create(_args(_seed(tmp_path), name="shot", command="x")) == 1
    assert "already exists" in capsys.readouterr().err


def test_action_delete_removes(tmp_path):
    from logitechmouse.cli.action import run_action_delete
    p = _seed(tmp_path)
    assert run_action_delete(_args(p, name="shot", force=False)) == 0
    assert "shot" not in load_config(p).actions


def test_action_delete_blocks_when_segment_references(tmp_path, capsys):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="shot", label="B"),
            Segment(action="shot", label="C"),
        ])},
    ))
    from logitechmouse.cli.action import run_action_delete
    assert run_action_delete(_args(p, name="shot", force=False)) == 1
    assert "main" in capsys.readouterr().err


def test_action_delete_force_removes_segments(tmp_path):
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={
            "shot": Action(name="shot", kind="command", command="true"),
            "other": Action(name="other", kind="command", command="true"),
        },
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="A"),
            Segment(action="other", label="B"),
            Segment(action="other", label="C"),
        ])},
    ))
    from logitechmouse.cli.action import run_action_delete
    assert run_action_delete(_args(p, name="shot", force=True)) == 0
    r = load_config(p)
    assert "shot" not in r.actions
    for ring in r.rings.values():
        assert all(seg.action != "shot" for seg in ring.segments)
