import argparse
import signal
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


def test_command_only_path_oserror_during_read_still_tears_down(cmd_only_config):
    """A device disconnect mid-read must still close virt and ungrab."""
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=OSError("disconnect")), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt):
        rc = listen_mod.run(args)

    assert rc == 1
    fake_virt.close.assert_called_once_with()
    fake_dev.ungrab.assert_called_once_with()


def test_command_only_path_virt_close_failure_still_ungrabs(cmd_only_config):
    """A raise from virt.close() must NOT prevent device.ungrab()."""
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()
    fake_virt.close.side_effect = RuntimeError("evdev hiccup")

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt):
        rc = listen_mod.run(args)

    assert rc == 0
    fake_virt.close.assert_called_once_with()
    fake_dev.ungrab.assert_called_once_with()


def test_command_only_path_installs_sigterm_handler_and_restores_it(cmd_only_config):
    """run() must install a SIGTERM handler before entering the loop and
    restore the previous handler on exit."""
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")

    sentinel = signal.getsignal(signal.SIGTERM)

    captured = {}

    def stub_read_loop(device, swallow_codes=None, virt=None):
        captured["installed_handler"] = signal.getsignal(signal.SIGTERM)
        return iter([])

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=stub_read_loop), \
         patch("logitechmouse.cli.listen.try_grab", return_value=None):
        listen_mod.run(args)

    assert captured["installed_handler"] is not sentinel, \
        "SIGTERM handler must be installed during the read loop"
    assert signal.getsignal(signal.SIGTERM) is sentinel, \
        "SIGTERM handler must be restored after run() returns"


@pytest.fixture
def ring_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[device]
path = "/dev/input/event99"

[actions.beep]
kind = "command"
command = "true"

[rings.r1]
segments = [
  { label = "a", action = "beep" },
  { label = "b", action = "beep" },
  { label = "c", action = "beep" },
  { label = "d", action = "beep" },
]

[bindings.b1]
trigger = "BTN_BACK"
target = "ring:r1"
"""
    )
    return cfg


@pytest.mark.requires_display
def test_qt_path_calls_try_grab_and_tears_down(ring_config):
    """In the Qt path, try_grab runs after resolve and teardown runs after app.exec()."""
    args = argparse.Namespace(config=ring_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()
    captured = {}

    # Stub the worker's read loop to immediately emit `finished` so app.exec returns.
    def stub_read_loop(device, swallow_codes=None, virt=None):
        captured["swallow_codes"] = swallow_codes
        captured["virt"] = virt
        return iter([])

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=stub_read_loop), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt) as tg:
        rc = listen_mod.run(args)

    assert rc == 0
    tg.assert_called_once_with(fake_dev)
    assert captured["virt"] is fake_virt
    assert ecodes.BTN_BACK in captured["swallow_codes"]
    fake_virt.close.assert_called_once_with()
    fake_dev.ungrab.assert_called_once_with()
