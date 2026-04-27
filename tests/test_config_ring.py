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


def test_parses_ring_with_segments(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "gnome-screenshot -a"

        [actions.full]
        type = "command"
        command = "gnome-screenshot"

        [actions.lock]
        type = "command"
        command = "loginctl lock-session"

        [rings.thumb]
        segments = [
          { action = "shot", label = "Area" },
          { action = "full", label = "Full" },
          { action = "lock", label = "Lock" },
        ]
    """)
    cfg = load_config(p)
    assert "thumb" in cfg.rings
    ring = cfg.rings["thumb"]
    assert ring.name == "thumb"
    assert len(ring.segments) == 3
    assert ring.segments[0].action == "shot"
    assert ring.segments[0].label == "Area"
    assert ring.segments[0].icon is None


def test_parses_ring_segment_with_icon(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "S", icon = "camera-photo" },
          { action = "shot", label = "S2" },
          { action = "shot", label = "S3" },
        ]
    """)
    cfg = load_config(p)
    assert cfg.rings["r"].segments[0].icon == "camera-photo"
    assert cfg.rings["r"].segments[1].icon is None


def test_no_rings_section_yields_empty_dict(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"
    """)
    cfg = load_config(p)
    assert cfg.rings == {}


def test_validate_rejects_ring_target_to_missing_ring(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        target = "ring:nonexistent"
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match="binding 'g' references unknown ring 'nonexistent'"):
        validate_config(cfg)


def test_validate_passes_for_valid_ring_binding(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "B" },
          { action = "shot", label = "C" },
        ]

        [bindings.g]
        trigger = "BTN_TASK"
        target = "ring:r"
    """)
    cfg = load_config(p)
    from logitechmouse.config import validate_config
    validate_config(cfg)  # should not raise


def test_validate_rejects_ring_with_too_few_segments(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "B" },
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match="ring 'r' must have between 3 and 12 segments"):
        validate_config(cfg)


def test_validate_rejects_ring_with_too_many_segments(tmp_path):
    segs = ",\n          ".join(
        '{ action = "shot", label = "X" }' for _ in range(13)
    )
    p = write_cfg(tmp_path, f"""
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          {segs}
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match="ring 'r' must have between 3 and 12 segments"):
        validate_config(cfg)


def test_validate_rejects_segment_with_unknown_action(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "B" },
          { action = "missing", label = "C" },
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match=r"rings\.r\.segments\[2\]\.action 'missing' not found"):
        validate_config(cfg)


def test_validate_rejects_segment_with_blank_label(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "   " },
          { action = "shot", label = "C" },
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match=r"rings\.r\.segments\[1\]\.label is empty"):
        validate_config(cfg)
