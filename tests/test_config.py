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


def test_theme_defaults_to_dark_when_section_absent(tmp_path):
    p = write_cfg(tmp_path, "[actions.x]\ntype = \"command\"\ncommand = \"true\"\n")
    cfg = load_config(p)
    assert cfg.theme.name == "dark"
    assert cfg.theme.overrides == {}


def test_theme_parses_preset_name(tmp_path):
    p = write_cfg(tmp_path, """
        [theme]
        name = "brazil"
    """)
    cfg = load_config(p)
    assert cfg.theme.name == "brazil"
    assert cfg.theme.overrides == {}


def test_theme_parses_overrides(tmp_path):
    p = write_cfg(tmp_path, """
        [theme]
        name = "dark"

        [theme.overrides]
        bubble_active = "#FFDF00"
        center_label = "#002776"
    """)
    cfg = load_config(p)
    assert cfg.theme.name == "dark"
    assert cfg.theme.overrides["bubble_active"] == "#ffdf00"
    assert cfg.theme.overrides["center_label"] == "#002776"


def test_theme_rejects_unknown_preset(tmp_path):
    p = write_cfg(tmp_path, """
        [theme]
        name = "neon"
    """)
    with pytest.raises(ConfigError, match="theme.name 'neon' unknown"):
        load_config(p)


def test_theme_rejects_unknown_override_key(tmp_path):
    p = write_cfg(tmp_path, """
        [theme.overrides]
        bogus = "#000000"
    """)
    with pytest.raises(ConfigError, match="theme.overrides has unknown key 'bogus'"):
        load_config(p)


def test_theme_rejects_bad_hex(tmp_path):
    p = write_cfg(tmp_path, """
        [theme.overrides]
        bubble = "ffdf00"
    """)
    with pytest.raises(ConfigError, match=r"theme\.overrides\.bubble must be '#rrggbb'"):
        load_config(p)


def test_theme_rejects_non_hex_digits(tmp_path):
    p = write_cfg(tmp_path, """
        [theme.overrides]
        bubble = "#zzzzzz"
    """)
    with pytest.raises(ConfigError, match="non-hex digits"):
        load_config(p)


def test_theme_accepts_8_digit_hex(tmp_path):
    p = write_cfg(tmp_path, """
        [theme.overrides]
        bubble = "#FFDF0080"
    """)
    cfg = load_config(p)
    assert cfg.theme.overrides["bubble"] == "#ffdf0080"
