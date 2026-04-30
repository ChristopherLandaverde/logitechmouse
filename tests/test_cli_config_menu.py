from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

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


class _Answer:
    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value


def test_menu_create_action(tmp_path):
    p = _seed(tmp_path)
    seq = iter(["Action", "Create", "notify", "notify-send hi"])
    confirm = iter([False])

    with patch("questionary.select", side_effect=lambda *a, **kw: _Answer(next(seq))), \
         patch("questionary.text", side_effect=lambda *a, **kw: _Answer(next(seq))), \
         patch("questionary.confirm", side_effect=lambda *a, **kw: _Answer(next(confirm))):
        from logitechmouse.cli.config_menu import run
        assert run(_args(p)) == 0

    assert load_config(p).actions["notify"].command == "notify-send hi"


def test_menu_create_ring(tmp_path):
    p = _seed(tmp_path)
    seq = iter(["Ring", "Create", "work"])
    confirm = iter([False])

    with patch("questionary.select", side_effect=lambda *a, **kw: _Answer(next(seq))), \
         patch("questionary.text", side_effect=lambda *a, **kw: _Answer(next(seq))), \
         patch("questionary.confirm", side_effect=lambda *a, **kw: _Answer(next(confirm))):
        from logitechmouse.cli.config_menu import run
        assert run(_args(p)) == 0

    assert "work" in load_config(p).rings


def test_menu_exit_immediately(tmp_path):
    p = _seed(tmp_path)
    seq = iter(["Exit"])

    with patch("questionary.select", side_effect=lambda *a, **kw: _Answer(next(seq))), \
         patch("questionary.text", side_effect=lambda *a, **kw: _Answer(None)), \
         patch("questionary.confirm", side_effect=lambda *a, **kw: _Answer(False)):
        from logitechmouse.cli.config_menu import run
        assert run(_args(p)) == 0
