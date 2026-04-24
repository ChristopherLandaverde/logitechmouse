from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


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
class AppConfig:
    actions: dict[str, Action]
    bindings: dict[str, Binding]


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppConfig(actions={}, bindings={})

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    raw_actions = raw.get("actions", {})
    raw_bindings = raw.get("bindings", {})

    actions = {
        name: Action(
            name=name,
            kind=data.get("type", "command"),
            command=data.get("command"),
        )
        for name, data in raw_actions.items()
    }
    bindings = {
        name: Binding(
            name=name,
            trigger=data["trigger"],
            action=data["action"],
        )
        for name, data in raw_bindings.items()
    }

    return AppConfig(actions=actions, bindings=bindings)
