from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from evdev import ecodes


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "logitechmouse" / "config.toml"


class ConfigError(Exception):
    """Raised when a loaded config fails validation."""


@dataclass
class Action:
    name: str
    kind: str
    command: str | None = None


_VALID_TARGET_KINDS = ("action", "ring")


@dataclass(frozen=True)
class Target:
    kind: str   # "action" or "ring"
    name: str


def parse_target_string(raw: str) -> "Target":
    if ":" not in raw:
        raise ConfigError(
            f"target {raw!r} must be 'kind:name' (e.g. 'action:screenshot')"
        )
    kind, _, name = raw.partition(":")
    if kind not in _VALID_TARGET_KINDS:
        raise ConfigError(
            f"unknown target kind {kind!r} in {raw!r}; expected one of "
            + ", ".join(_VALID_TARGET_KINDS)
        )
    if not name:
        raise ConfigError(f"target {raw!r} has empty name after the ':'")
    return Target(kind=kind, name=name)


@dataclass
class Segment:
    action: str           # references actions[name]
    label: str
    icon: str | None = None


@dataclass
class Ring:
    name: str
    segments: list[Segment]


def _parse_binding(name: str, data: dict) -> "Binding":
    has_target = "target" in data
    has_action = "action" in data
    if has_target and has_action:
        raise ConfigError(
            f"binding {name!r}: cannot specify both 'action' and 'target'; "
            f"use 'target = \"action:NAME\"' (modern) or 'action = \"NAME\"' (legacy)"
        )
    if has_target:
        target = parse_target_string(data["target"])
    elif has_action:
        logging.info(
            "binding %r uses deprecated 'action = ...' form; the modern "
            "equivalent is 'target = \"action:%s\"'",
            name, data["action"],
        )
        target = Target(kind="action", name=data["action"])
    else:
        raise ConfigError(
            f"binding {name!r} must specify 'target' (e.g. 'target = \"action:screenshot\"')"
        )
    if "trigger" not in data:
        raise ConfigError(f"binding {name!r} missing 'trigger'")
    return Binding(name=name, trigger=data["trigger"], target=target)


@dataclass
class Binding:
    name: str
    trigger: str
    target: Target


def _parse_ring(name: str, data: dict) -> Ring:
    raw_segments = data.get("segments")
    if raw_segments is None:
        raise ConfigError(f"ring {name!r} missing 'segments' list")
    if not isinstance(raw_segments, list):
        raise ConfigError(f"ring {name!r}: 'segments' must be a list")
    segments: list[Segment] = []
    for i, seg in enumerate(raw_segments):
        if not isinstance(seg, dict):
            raise ConfigError(
                f"ring {name!r}.segments[{i}] must be an inline table"
            )
        if "action" not in seg:
            raise ConfigError(f"ring {name!r}.segments[{i}] missing 'action'")
        if "label" not in seg:
            raise ConfigError(f"ring {name!r}.segments[{i}] missing 'label'")
        icon = seg.get("icon")
        if icon is not None and (not isinstance(icon, str) or not icon):
            raise ConfigError(
                f"ring {name!r}.segments[{i}] icon must be a non-empty string"
            )
        segments.append(
            Segment(action=seg["action"], label=seg["label"], icon=icon)
        )
    return Ring(name=name, segments=segments)


@dataclass
class DeviceConfig:
    name: str | None = None
    path: str | None = None


@dataclass
class AppConfig:
    actions: dict[str, Action] = field(default_factory=dict)
    bindings: dict[str, Binding] = field(default_factory=dict)
    rings: dict[str, Ring] = field(default_factory=dict)
    device: DeviceConfig = field(default_factory=DeviceConfig)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppConfig()

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    actions = {
        name: Action(
            name=name,
            kind=data.get("type", "command"),
            command=data.get("command"),
        )
        for name, data in raw.get("actions", {}).items()
    }
    bindings = {
        name: _parse_binding(name, data)
        for name, data in raw.get("bindings", {}).items()
    }
    rings = {
        name: _parse_ring(name, data)
        for name, data in raw.get("rings", {}).items()
    }
    raw_device = raw.get("device", {}) or {}
    device = DeviceConfig(
        name=raw_device.get("name"),
        path=raw_device.get("path"),
    )

    return AppConfig(actions=actions, bindings=bindings, rings=rings, device=device)


def validate_config(config: AppConfig) -> None:
    for action in config.actions.values():
        if action.kind == "command" and not action.command:
            raise ConfigError(
                f"action {action.name!r} is type=command but has no command"
            )
    for binding in config.bindings.values():
        if binding.trigger not in ecodes.ecodes:
            raise ConfigError(
                f"binding {binding.name!r} has unknown trigger {binding.trigger!r}"
            )
        if binding.target.kind == "action":
            if binding.target.name not in config.actions:
                raise ConfigError(
                    f"binding {binding.name!r} references unknown action "
                    f"{binding.target.name!r}"
                )
        elif binding.target.kind == "ring":
            if binding.target.name not in config.rings:
                raise ConfigError(
                    f"binding {binding.name!r} references unknown ring "
                    f"{binding.target.name!r}"
                )
    for ring in config.rings.values():
        n = len(ring.segments)
        if n < 3 or n > 12:
            raise ConfigError(
                f"ring {ring.name!r} must have between 3 and 12 segments, got {n}"
            )
        for i, seg in enumerate(ring.segments):
            if not seg.label.strip():
                raise ConfigError(
                    f"rings.{ring.name}.segments[{i}].label is empty"
                )
            if seg.action not in config.actions:
                raise ConfigError(
                    f"rings.{ring.name}.segments[{i}].action {seg.action!r} not found"
                )
