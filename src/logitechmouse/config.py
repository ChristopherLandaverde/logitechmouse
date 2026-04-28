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


@dataclass
class Profile:
    name: str
    match_wm_class: str
    bindings: dict[str, Binding] = field(default_factory=dict)


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


# Recognized preset names. Widget owns the actual color tables; this list
# exists so config validation can reject typos without importing PyQt.
_VALID_THEME_PRESETS = ("dark", "brazil")

# Keys a user may override in `[theme.overrides]`. Must stay in lock-step with
# the keys present in every preset of `_THEMES` in overlay/widget.py.
_VALID_THEME_KEYS = frozenset(
    {"bubble", "bubble_active", "dead_zone", "label", "label_active", "cancel", "center_label"}
)


def _parse_hex_color(raw: str, where: str) -> str:
    """Validate a hex color string (`#rrggbb` or `#rrggbbaa`). Returns it
    normalized to lowercase. Raises ConfigError on bad input."""
    if not isinstance(raw, str):
        raise ConfigError(f"{where} must be a string like '#rrggbb', got {type(raw).__name__}")
    if not raw.startswith("#") or len(raw) not in (7, 9):
        raise ConfigError(
            f"{where} must be '#rrggbb' or '#rrggbbaa', got {raw!r}"
        )
    body = raw[1:]
    try:
        int(body, 16)
    except ValueError:
        raise ConfigError(f"{where} contains non-hex digits: {raw!r}") from None
    return raw.lower()


@dataclass
class Theme:
    name: str = "dark"
    # Maps theme key (e.g. "bubble_active") to a hex string. Widget converts.
    overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class AppConfig:
    actions: dict[str, Action] = field(default_factory=dict)
    bindings: dict[str, Binding] = field(default_factory=dict)
    rings: dict[str, Ring] = field(default_factory=dict)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    profiles: dict[str, Profile] = field(default_factory=dict)
    theme: Theme = field(default_factory=Theme)


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

    profiles: dict[str, Profile] = {}
    for pname, pdata in raw.get("profiles", {}).items():
        match_wm = pdata.get("match_wm_class", "")
        if not match_wm:
            raise ConfigError(f"profile {pname!r} missing 'match_wm_class'")
        profile_bindings = {
            bname: _parse_binding(bname, bdata)
            for bname, bdata in pdata.get("bindings", {}).items()
        }
        profiles[pname] = Profile(
            name=pname, match_wm_class=match_wm, bindings=profile_bindings
        )

    raw_theme = raw.get("theme", {}) or {}
    theme_name = raw_theme.get("name", "dark")
    if not isinstance(theme_name, str):
        raise ConfigError(f"theme.name must be a string, got {type(theme_name).__name__}")
    if theme_name not in _VALID_THEME_PRESETS:
        raise ConfigError(
            f"theme.name {theme_name!r} unknown; expected one of "
            + ", ".join(_VALID_THEME_PRESETS)
        )
    raw_overrides = raw_theme.get("overrides", {}) or {}
    if not isinstance(raw_overrides, dict):
        raise ConfigError("theme.overrides must be a table of key = '#rrggbb' entries")
    overrides: dict[str, str] = {}
    for key, value in raw_overrides.items():
        if key not in _VALID_THEME_KEYS:
            raise ConfigError(
                f"theme.overrides has unknown key {key!r}; expected one of "
                + ", ".join(sorted(_VALID_THEME_KEYS))
            )
        overrides[key] = _parse_hex_color(value, where=f"theme.overrides.{key}")
    theme = Theme(name=theme_name, overrides=overrides)

    return AppConfig(
        actions=actions,
        bindings=bindings,
        rings=rings,
        device=device,
        profiles=profiles,
        theme=theme,
    )


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
    for profile in config.profiles.values():
        for binding in profile.bindings.values():
            if binding.trigger not in ecodes.ecodes:
                raise ConfigError(
                    f"profile {profile.name!r} binding {binding.name!r} "
                    f"has unknown trigger {binding.trigger!r}"
                )
            if binding.target.kind == "action" and binding.target.name not in config.actions:
                raise ConfigError(
                    f"profile {profile.name!r} binding {binding.name!r} "
                    f"references unknown action {binding.target.name!r}"
                )
            elif binding.target.kind == "ring" and binding.target.name not in config.rings:
                raise ConfigError(
                    f"profile {profile.name!r} binding {binding.name!r} "
                    f"references unknown ring {binding.target.name!r}"
                )
