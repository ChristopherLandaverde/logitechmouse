from __future__ import annotations

import argparse
import logging

from ..config import ConfigError, load_config, validate_config


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1
    except Exception as exc:
        logging.error("could not load config: %s", exc)
        return 1

    print(
        f"OK: {len(cfg.actions)} actions, {len(cfg.bindings)} bindings, "
        f"device={cfg.device.path or cfg.device.name or '(auto)'}"
    )
    return 0
