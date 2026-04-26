import argparse
from unittest.mock import patch

import pytest

from logitechmouse.cli import listen as listen_mod


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
