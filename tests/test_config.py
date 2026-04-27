from pathlib import Path
import textwrap

import pytest

from logitechmouse.config import load_config, ConfigError, validate_config


def write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_missing_file_returns_empty_config(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.actions == {}
    assert cfg.bindings == {}
    assert cfg.device.name is None
    assert cfg.device.path is None


def test_parses_actions_and_bindings(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.gesture]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    cfg = load_config(p)
    assert cfg.actions["shot"].command == "true"
    assert cfg.bindings["gesture"].trigger == "BTN_TASK"
    assert cfg.bindings["gesture"].target.kind == "action"
    assert cfg.bindings["gesture"].target.name == "shot"


def test_parses_device_section(tmp_path):
    p = write_cfg(tmp_path, """
        [device]
        name = "MX Master"
        path = "/dev/input/event7"
    """)
    cfg = load_config(p)
    assert cfg.device.name == "MX Master"
    assert cfg.device.path == "/dev/input/event7"


def test_device_section_optional(tmp_path):
    p = write_cfg(tmp_path, "[actions.x]\ntype = \"command\"\ncommand = \"true\"\n")
    cfg = load_config(p)
    assert cfg.device.name is None
    assert cfg.device.path is None


def test_validate_passes_on_good_config(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    cfg = load_config(p)
    validate_config(cfg)  # should not raise


def test_validate_rejects_unknown_action_reference(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        target = "action:missing"
    """)
    cfg = load_config(p)
    with pytest.raises(ConfigError, match="binding 'g' references unknown action 'missing'"):
        validate_config(cfg)


def test_validate_rejects_unknown_trigger_code(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_NOPE"
        action = "shot"
    """)
    cfg = load_config(p)
    with pytest.raises(ConfigError, match="binding 'g' has unknown trigger 'BTN_NOPE'"):
        validate_config(cfg)


def test_validate_rejects_command_action_without_command(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
    """)
    cfg = load_config(p)
    with pytest.raises(ConfigError, match="action 'shot' is type=command but has no command"):
        validate_config(cfg)
