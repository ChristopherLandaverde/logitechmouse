from __future__ import annotations

import argparse
from pathlib import Path

from logitechmouse.config import Action, AppConfig, Binding, Profile, Target, load_config
from logitechmouse.config_writer import write_config


def _args(config: Path, **kw) -> argparse.Namespace:
    return argparse.Namespace(config=config, **kw)


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    write_config(p, AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        profiles={"myapp": Profile(
            name="myapp", match_wm_class="MyApp",
            bindings={"btn_side": Binding(
                name="btn_side", trigger="BTN_SIDE",
                target=Target(kind="action", name="shot"),
            )},
        )},
    ))
    return p


def test_profile_list_shows(tmp_path, capsys):
    from logitechmouse.cli.profile import run_profile_list
    assert run_profile_list(_args(_seed(tmp_path))) == 0
    assert "myapp" in capsys.readouterr().out


def test_profile_list_empty(tmp_path, capsys):
    p = tmp_path / "c.toml"
    write_config(p, AppConfig())
    from logitechmouse.cli.profile import run_profile_list
    assert run_profile_list(_args(p)) == 0
    assert "No profiles" in capsys.readouterr().out


def test_profile_create(tmp_path):
    from logitechmouse.cli.profile import run_profile_create
    p = _seed(tmp_path)
    assert run_profile_create(_args(p, name="browser", match="Firefox")) == 0
    assert load_config(p).profiles["browser"].match_wm_class == "Firefox"


def test_profile_create_duplicate_fails(tmp_path, capsys):
    from logitechmouse.cli.profile import run_profile_create
    assert run_profile_create(_args(_seed(tmp_path), name="myapp", match="X")) == 1
    assert "already exists" in capsys.readouterr().err


def test_profile_delete_removes(tmp_path):
    from logitechmouse.cli.profile import run_profile_delete
    p = _seed(tmp_path)
    assert run_profile_delete(_args(p, name="myapp")) == 0
    assert "myapp" not in load_config(p).profiles


def test_profile_delete_unknown_fails(tmp_path, capsys):
    from logitechmouse.cli.profile import run_profile_delete
    assert run_profile_delete(_args(_seed(tmp_path), name="nope")) == 1


def test_binding_set_creates(tmp_path):
    from logitechmouse.cli.profile import run_binding_set
    p = _seed(tmp_path)
    assert run_binding_set(_args(p, profile="myapp", trigger="BTN_TASK",
                                  target="action:shot")) == 0
    b = load_config(p).profiles["myapp"].bindings.get("btn_task")
    assert b is not None and b.trigger == "BTN_TASK" and b.target.name == "shot"


def test_binding_set_invalid_trigger_fails(tmp_path, capsys):
    from logitechmouse.cli.profile import run_binding_set
    assert run_binding_set(_args(_seed(tmp_path), profile="myapp",
                                  trigger="NOT_REAL", target="action:shot")) == 1
    assert "trigger" in capsys.readouterr().err.lower()


def test_binding_remove(tmp_path):
    from logitechmouse.cli.profile import run_binding_remove
    p = _seed(tmp_path)
    assert run_binding_remove(_args(p, profile="myapp", trigger="BTN_SIDE")) == 0
    assert "btn_side" not in load_config(p).profiles["myapp"].bindings


def test_binding_remove_unknown_trigger_fails(tmp_path, capsys):
    from logitechmouse.cli.profile import run_binding_remove
    assert run_binding_remove(_args(_seed(tmp_path), profile="myapp",
                                     trigger="BTN_TASK")) == 1
