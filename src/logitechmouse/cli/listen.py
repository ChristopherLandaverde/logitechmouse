from __future__ import annotations

import argparse
import logging

from ..actions import run_action
from ..config import ConfigError, load_config, validate_config
from ..device import (
    DeviceNotFoundError,
    DeviceUnreadableError,
    EvdevBackend,
)


REMEDIATION = (
    "device is not readable. Add yourself to the `input` group:\n"
    "  sudo usermod -aG input $USER\n"
    "Then log out and back in."
)


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1

    if not cfg.bindings:
        logging.error(
            "config has no bindings; nothing would fire on key-down. "
            "Add at least one [bindings.NAME] section pointing to an action."
        )
        return 1

    if getattr(args, "device", None):
        cfg.device.path = args.device

    triggers = {b.trigger for b in cfg.bindings.values()} or None

    backend = EvdevBackend()
    try:
        device = backend.resolve(cfg.device, triggers=triggers)
    except DeviceUnreadableError as exc:
        logging.error("%s\n%s", exc, REMEDIATION)
        return 1
    except DeviceNotFoundError as exc:
        logging.error("%s", exc)
        return 1

    bindings_by_trigger = {b.trigger: b for b in cfg.bindings.values()}
    summary = ", ".join(
        f"{b.name}[{b.trigger}]->{b.target.kind}:{b.target.name}"
        for b in cfg.bindings.values()
    ) or "(none)"
    logging.info("listening on %s (%s)", device.path, device.name)
    logging.info("bindings: %s", summary)

    try:
        for event in backend.read_loop(device):
            binding = bindings_by_trigger.get(event.trigger)
            if binding is None:
                continue
            if not event.pressed:
                # Key-up does not fire action targets. Ring targets are
                # wired in a later task; this branch will route there.
                continue
            if binding.target.kind != "action":
                # Ring targets are wired in a later task; skip silently for now.
                continue
            action = cfg.actions[binding.target.name]
            result = run_action(action)
            if result.ok:
                logging.info("%s", result.detail)
            else:
                logging.warning("action %r %s", action.name, result.detail)
    except OSError as exc:
        logging.warning("device read failed: %s", exc)
        return 1

    return 0
