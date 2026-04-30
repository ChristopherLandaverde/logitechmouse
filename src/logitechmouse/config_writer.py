from __future__ import annotations

from pathlib import Path

import tomli_w

from .config import AppConfig


def config_to_dict(config: AppConfig) -> dict:
    d: dict = {}

    if config.device.name is not None or config.device.path is not None:
        device: dict = {}
        if config.device.name is not None:
            device["name"] = config.device.name
        if config.device.path is not None:
            device["path"] = config.device.path
        d["device"] = device

    if config.actions:
        d["actions"] = {}
        for name, action in config.actions.items():
            entry: dict = {"type": action.kind}
            if action.command is not None:
                entry["command"] = action.command
            d["actions"][name] = entry

    if config.bindings:
        d["bindings"] = {
            name: {
                "trigger": b.trigger,
                "target": f"{b.target.kind}:{b.target.name}",
            }
            for name, b in config.bindings.items()
        }

    if config.rings:
        d["rings"] = {}
        for name, ring in config.rings.items():
            segments = []
            for seg in ring.segments:
                s: dict = {"action": seg.action, "label": seg.label}
                if seg.icon is not None:
                    s["icon"] = seg.icon
                segments.append(s)
            d["rings"][name] = {"segments": segments}

    if config.profiles:
        d["profiles"] = {}
        for name, profile in config.profiles.items():
            pd: dict = {"match_wm_class": profile.match_wm_class}
            if profile.bindings:
                pd["bindings"] = {
                    bname: {
                        "trigger": b.trigger,
                        "target": f"{b.target.kind}:{b.target.name}",
                    }
                    for bname, b in profile.bindings.items()
                }
            d["profiles"][name] = pd

    if config.theme.name != "dark" or config.theme.overrides:
        td: dict = {"name": config.theme.name}
        if config.theme.overrides:
            td["overrides"] = dict(config.theme.overrides)
        d["theme"] = td

    return d


def write_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump(config_to_dict(config), f)
