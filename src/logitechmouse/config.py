from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from evdev import ecodes


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "logitechmouse" / "config.toml"


@dataclass
class Action:
    name: str
    kind: str
    command: str | None = None


@dataclass
class Binding:
    name: str
    trigger: str
    action: str


@dataclass
class DeviceConfig:
    name: str | None = None
    path: str | None = None


@dataclass
class AppConfig:
    actions: dict[str, Action] = field(default_factory=dict)
    bindings: dict[str, Binding] = field(default_factory=dict)
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
        name: Binding(
            name=name,
            trigger=data["trigger"],
            action=data["action"],
        )
        for name, data in raw.get("bindings", {}).items()
    }
    raw_device = raw.get("device", {}) or {}
    device = DeviceConfig(
        name=raw_device.get("name"),
        path=raw_device.get("path"),
    )

    return AppConfig(actions=actions, bindings=bindings, device=device)


class ConfigError(Exception):
    """Raised when a loaded config fails validation."""


def validate_config(config: AppConfig) -> None:
    for action in config.actions.values():
        if action.kind == "command" and not action.command:
            raise ConfigError(f"action {action.name!r} is type=command but has no command")
    for binding in config.bindings.values():
        if binding.action not in config.actions:
            raise ConfigError(f"binding {binding.name!r} references unknown action {binding.action!r}")
        if binding.trigger not in ecodes.ecodes:
            raise ConfigError(f"binding {binding.name!r} has unknown trigger {binding.trigger!r}")
