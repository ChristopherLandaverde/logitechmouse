import argparse
from unittest.mock import MagicMock, patch

import pytest
from evdev import ecodes

from logitechmouse.cli import listen as listen_mod


@pytest.fixture
def cmd_only_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[device]
path = "/dev/input/event99"

[actions.beep]
kind = "command"
command = "true"

[bindings.b1]
trigger = "BTN_BACK"
target = "action:beep"
"""
    )
    return cfg


def test_command_only_path_calls_try_grab_then_passes_virt_to_read_loop(cmd_only_config):
    args = argparse.Namespace(config=cmd_only_config, device=None)

    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()
    captured = {}

    def fake_read_loop(device, swallow_codes=None, virt=None):
        captured["device"] = device
        captured["swallow_codes"] = swallow_codes
        captured["virt"] = virt
        return iter([])  # immediately exit the loop

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=fake_read_loop), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt) as tg:
        rc = listen_mod.run(args)

    assert rc == 0
    tg.assert_called_once_with(fake_dev)
    assert captured["virt"] is fake_virt
    assert ecodes.BTN_BACK in captured["swallow_codes"]


def test_command_only_path_closes_virt_and_ungrabs_on_exit(cmd_only_config):
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt):
        listen_mod.run(args)

    fake_virt.close.assert_called_once_with()
    fake_dev.ungrab.assert_called_once_with()


def test_command_only_path_no_virt_does_not_call_ungrab(cmd_only_config):
    """When try_grab returns None, ungrab must not be called either."""
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=None):
        rc = listen_mod.run(args)

    assert rc == 0
    fake_dev.ungrab.assert_not_called()
