import pytest

from logitechmouse.config import Target, parse_target_string, ConfigError


def test_parse_action_target():
    t = parse_target_string("action:screenshot")
    assert t == Target(kind="action", name="screenshot")


def test_parse_ring_target():
    t = parse_target_string("ring:thumb_ring")
    assert t == Target(kind="ring", name="thumb_ring")


def test_parse_target_rejects_unknown_kind():
    with pytest.raises(ConfigError, match="unknown target kind 'macro'"):
        parse_target_string("macro:foo")


def test_parse_target_rejects_missing_separator():
    with pytest.raises(ConfigError, match="must be 'kind:name'"):
        parse_target_string("screenshot")


def test_parse_target_rejects_empty_name():
    with pytest.raises(ConfigError, match="empty name"):
        parse_target_string("action:")


def test_target_is_frozen():
    t = Target(kind="action", name="x")
    with pytest.raises(Exception):
        t.kind = "ring"  # frozen dataclasses raise FrozenInstanceError


import logging
import textwrap
from pathlib import Path

from logitechmouse.config import load_config


def write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_modern_target_action_form_parses(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        target = "action:shot"
    """)
    cfg = load_config(p)
    assert cfg.bindings["g"].target.kind == "action"
    assert cfg.bindings["g"].target.name == "shot"


def test_legacy_action_string_form_is_translated(tmp_path, caplog):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    with caplog.at_level(logging.INFO):
        cfg = load_config(p)
    assert cfg.bindings["g"].target.kind == "action"
    assert cfg.bindings["g"].target.name == "shot"
    # Migration nudge logged at INFO (not raised).
    assert any(
        "deprecated" in r.message.lower() and "g" in r.message
        for r in caplog.records
    )


def test_target_and_action_both_present_is_error(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "shot"
        target = "action:shot"
    """)
    import pytest
    from logitechmouse.config import ConfigError
    with pytest.raises(ConfigError, match="cannot specify both 'action' and 'target'"):
        load_config(p)


def test_neither_target_nor_action_is_error(tmp_path):
    p = write_cfg(tmp_path, """
        [bindings.g]
        trigger = "BTN_TASK"
    """)
    import pytest
    from logitechmouse.config import ConfigError
    with pytest.raises(ConfigError, match="must specify 'target'"):
        load_config(p)
