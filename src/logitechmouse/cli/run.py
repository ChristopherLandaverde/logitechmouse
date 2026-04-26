from __future__ import annotations

import argparse
import logging

from ..actions import run_action
from ..config import ConfigError, load_config, validate_config


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1

    action = cfg.actions.get(args.name)
    if action is None:
        logging.error("unknown action: %s", args.name)
        return 1

    result = run_action(action, dry_run=args.dry_run)
    logging.info(result.detail)
    return 0 if result.ok else 1
