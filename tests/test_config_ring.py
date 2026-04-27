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
