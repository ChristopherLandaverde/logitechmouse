import argparse
from unittest.mock import patch

import pytest

from logitechmouse.cli import listen as listen_mod
from logitechmouse.device import DeviceNotFoundError


def test_listen_returns_error_when_config_has_no_bindings(tmp_path, caplog):
    """A listener with no bindings will silently drop every event the user
    presses. Surface this at startup with a non-zero exit and a clear
    error log so the user knows the config is incomplete. The backend
    must NOT be touched in this case."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("# empty config\n")

    args = argparse.Namespace(config=cfg_path, device=None)

    # Trip-wire: if the empty-bindings guard isn't in place, run() falls
    # through to backend.resolve() and the test hangs on real hardware.
    # Patching resolve() to raise makes the failure mode visible instead.
    with patch.object(
        listen_mod.EvdevBackend,
        "resolve",
        side_effect=AssertionError("backend.resolve must not be called when bindings empty"),
    ), caplog.at_level("ERROR"):
        rc = listen_mod.run(args)

    assert rc == 1
    assert any(
        "binding" in rec.message.lower() for rec in caplog.records
    ), f"expected an error mentioning bindings, got: {[r.message for r in caplog.records]}"


def test_listen_retries_device_discovery_when_requested(tmp_path, caplog):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.a]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_SIDE"\n'
        'target = "action:a"\n'
    )
    args = argparse.Namespace(
        config=cfg_path,
        device=None,
        retry_device=True,
        retry_interval=0,
    )
    fake_device = type("FakeDev", (), {"path": "/fake", "name": "Fake"})()

    with patch.object(
        listen_mod,
        "_resolve_device",
        side_effect=[DeviceNotFoundError("not yet"), fake_device],
    ), patch.object(
        listen_mod.EvdevBackend,
        "read_loop",
        return_value=iter(()),
    ), patch(
        "logitechmouse.cli.listen.try_grab",
        return_value=None,
    ), patch(
        "logitechmouse.cli.listen.time.sleep",
    ) as sleep, caplog.at_level("WARNING"):
        rc = listen_mod.run(args)

    assert rc == 0
    sleep.assert_called_once_with(0.1)
    assert any("retrying device discovery" in rec.message for rec in caplog.records)


from unittest.mock import MagicMock

from logitechmouse.config import (
    Action, AppConfig, Binding, Ring, Segment, Target,
)
from logitechmouse.cli.listen import dispatch_event


def _cfg_with_action_and_ring():
    return AppConfig(
        actions={"a": Action(name="a", kind="command", command="true")},
        rings={
            "r": Ring(
                name="r",
                segments=[
                    Segment(action="a", label="A"),
                    Segment(action="a", label="B"),
                    Segment(action="a", label="C"),
                ],
            )
        },
        bindings={
            "act_btn": Binding(
                name="act_btn", trigger="BTN_SIDE",
                target=Target(kind="action", name="a"),
            ),
            "ring_btn": Binding(
                name="ring_btn", trigger="BTN_TASK",
                target=Target(kind="ring", name="r"),
            ),
        },
    )


def test_dispatch_action_target_on_keydown_runs_action():
    cfg = _cfg_with_action_and_ring()
    run_action = MagicMock()
    rc = MagicMock()
    dispatch_event(cfg, rc, run_action, trigger="BTN_SIDE", pressed=True, cursor_pos=(0, 0))
    run_action.assert_called_once_with(cfg.actions["a"])
    rc.open.assert_not_called()
    rc.close.assert_not_called()


def test_dispatch_action_target_on_keyup_does_nothing():
    cfg = _cfg_with_action_and_ring()
    run_action = MagicMock()
    rc = MagicMock()
    dispatch_event(cfg, rc, run_action, trigger="BTN_SIDE", pressed=False, cursor_pos=(0, 0))
    run_action.assert_not_called()


def test_dispatch_ring_target_on_keydown_opens():
    cfg = _cfg_with_action_and_ring()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), trigger="BTN_TASK", pressed=True, cursor_pos=(100, 200))
    rc.open.assert_called_once_with(cfg.rings["r"], cursor_pos=(100, 200))


def test_dispatch_ring_target_on_keyup_closes():
    cfg = _cfg_with_action_and_ring()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), trigger="BTN_TASK", pressed=False, cursor_pos=(0, 0))
    rc.close.assert_called_once()


def test_dispatch_unknown_trigger_is_noop():
    cfg = _cfg_with_action_and_ring()
    rc = MagicMock()
    run_action = MagicMock()
    dispatch_event(cfg, rc, run_action, trigger="BTN_NOT_BOUND", pressed=True, cursor_pos=(0, 0))
    rc.open.assert_not_called()
    rc.close.assert_not_called()
    run_action.assert_not_called()
