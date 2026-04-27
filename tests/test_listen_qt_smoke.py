import argparse
from unittest.mock import patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from logitechmouse.cli import listen as listen_mod
from logitechmouse.device import InputEvent


@pytest.mark.requires_display
def test_qt_listener_dispatches_one_keydown_then_exits(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.a]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[rings.r]\n'
        'segments = [\n'
        '  { action = "a", label = "A" },\n'
        '  { action = "a", label = "B" },\n'
        '  { action = "a", label = "C" },\n'
        ']\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_TASK"\n'
        'target = "ring:r"\n'
    )
    args = argparse.Namespace(config=cfg_path, device=None)

    fake_device = type("FakeDev", (), {"path": "/fake", "name": "Fake"})()

    def fake_read_loop(_dev):
        yield InputEvent(trigger="BTN_TASK", pressed=True)
        yield InputEvent(trigger="BTN_TASK", pressed=False)

    with patch.object(
        listen_mod.EvdevBackend, "resolve", return_value=fake_device,
    ), patch.object(
        listen_mod.EvdevBackend, "read_loop", side_effect=fake_read_loop,
    ):
        rc = listen_mod.run(args)

    assert rc == 0
