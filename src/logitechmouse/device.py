from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from evdev import InputDevice, categorize, ecodes, list_devices

from .config import DeviceConfig


_AUTO_NAME_RE = re.compile(r"logitech|mx (master|anywhere|ergo|vertical)", re.IGNORECASE)


class DeviceNotFoundError(Exception):
    """Raised when no device matches the resolution criteria."""


class DeviceUnreadableError(Exception):
    """Raised when the matched device cannot be opened for reading."""


@dataclass
class CandidateDevice:
    path: str
    name: str
    vendor: int
    product: int
    readable: bool


@dataclass
class InputEvent:
    trigger: str  # evdev key code name, e.g. "BTN_TASK"


class EvdevBackend:
    def list_candidates(self) -> list[CandidateDevice]:
        candidates: list[CandidateDevice] = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                candidates.append(
                    CandidateDevice(
                        path=path,
                        name=dev.name,
                        vendor=dev.info.vendor,
                        product=dev.info.product,
                        readable=True,
                    )
                )
            except (PermissionError, OSError):
                candidates.append(
                    CandidateDevice(
                        path=path,
                        name="(unreadable)",
                        vendor=0,
                        product=0,
                        readable=False,
                    )
                )
        return candidates
