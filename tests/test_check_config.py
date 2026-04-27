import argparse
import sys
from unittest.mock import patch

from logitechmouse.cli import check_config as cc_mod


def test_check_config_errors_when_ring_binding_but_pyqt6_unavailable(tmp_path, caplog):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.shot]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[rings.r]\n'
        'segments = [\n'
        '  { action = "shot", label = "A" },\n'
        '  { action = "shot", label = "B" },\n'
        '  { action = "shot", label = "C" },\n'
        ']\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_TASK"\n'
        'target = "ring:r"\n'
    )
    args = argparse.Namespace(config=cfg_path, device=None)

    # Pretend PyQt6 cannot be imported.
    with patch.dict(sys.modules, {"PyQt6": None, "PyQt6.QtWidgets": None}), \
         caplog.at_level("ERROR"):
        rc = cc_mod.run(args)

    assert rc == 1
    assert any("PyQt6" in r.message for r in caplog.records)


def test_check_config_passes_when_only_action_bindings(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.shot]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_TASK"\n'
        'target = "action:shot"\n'
    )
    args = argparse.Namespace(config=cfg_path, device=None)
    rc = cc_mod.run(args)
    assert rc == 0
