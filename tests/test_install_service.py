from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _args(config: Path, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(config=config, force=force)


def _run(args, home: Path):
    from logitechmouse.cli import install_service as mod
    with patch("pathlib.Path.home", return_value=home):
        return mod.run(args)


def test_happy_path_writes_unit_file(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("[device]\npath = '/dev/input/event0'\n")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/local/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=0)):
        rc = _run(_args(config), home=tmp_path)

    assert rc == 0
    unit = tmp_path / ".config" / "systemd" / "user" / "logitechmouse.service"
    assert unit.exists()
    content = unit.read_text()
    assert "/usr/local/bin/logitechmouse" in content
    assert str(config.resolve()) in content
    assert "listen --retry-device --retry-interval 5" in content
    assert "Restart=always" in content


def test_happy_path_runs_daemon_reload(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")

    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run", mock_run):
        _run(_args(config), home=tmp_path)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "daemon-reload" in cmd


def test_config_not_found_returns_1_no_unit_written(tmp_path):
    args = _args(tmp_path / "missing.toml")
    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"):
        rc = _run(args, home=tmp_path)

    assert rc == 1
    unit = tmp_path / ".config" / "systemd" / "user" / "logitechmouse.service"
    assert not unit.exists()


def test_binary_not_resolvable_returns_1(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")
    with patch("logitechmouse.cli.install_service.shutil.which", return_value=None), \
         patch("sys.argv", []):
        rc = _run(_args(config), home=tmp_path)
    assert rc == 1


def test_existing_unit_without_force_returns_1_and_does_not_overwrite(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit = unit_dir / "logitechmouse.service"
    unit.write_text("old content")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"):
        rc = _run(_args(config, force=False), home=tmp_path)

    assert rc == 1
    assert unit.read_text() == "old content"


def test_force_overwrites_existing_unit(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "logitechmouse.service").write_text("old content")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=0)):
        rc = _run(_args(config, force=True), home=tmp_path)

    assert rc == 0
    content = (unit_dir / "logitechmouse.service").read_text()
    assert content != "old content"
    assert "listen" in content and str(config.resolve()) in content


def test_daemon_reload_failure_warns_but_returns_0(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=1)):
        rc = _run(_args(config), home=tmp_path)

    assert rc == 0


def test_fallback_to_argv0_when_which_returns_none(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")

    with patch("logitechmouse.cli.install_service.shutil.which", return_value=None), \
         patch("sys.argv", ["/home/user/.local/bin/logitechmouse", "install-service"]), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=0)):
        rc = _run(_args(config), home=tmp_path)

    assert rc == 0
    unit = tmp_path / ".config" / "systemd" / "user" / "logitechmouse.service"
    assert "/home/user/.local/bin/logitechmouse" in unit.read_text()
