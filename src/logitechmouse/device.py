from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from evdev import InputDevice, categorize, ecodes, list_devices

from .config import DeviceConfig


_AUTO_NAME_RE = re.compile(r"logitech|mx (master|anywhere|ergo|vertical)", re.IGNORECASE)

_BTN_MIN = 0x100  # ecodes.BTN_MISC
_BTN_MAX = 0x151  # ecodes.BTN_GEAR_UP


def _has_button_capability(dev: InputDevice) -> bool:
    try:
        caps = dev.capabilities()
    except Exception:
        return False
    keys = caps.get(ecodes.EV_KEY, []) or []
    return any(_BTN_MIN <= code <= _BTN_MAX for code in keys)


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

    def resolve(self, device_cfg: DeviceConfig) -> InputDevice:
        all_paths = list_devices()

        if device_cfg.path:
            if device_cfg.path not in all_paths:
                raise DeviceNotFoundError(
                    f"configured device path {device_cfg.path!r} not present"
                )
            try:
                return InputDevice(device_cfg.path)
            except (PermissionError, OSError) as exc:
                raise DeviceUnreadableError(str(exc)) from exc

        match_name = device_cfg.name
        saw_match_without_buttons = False
        for path in all_paths:
            try:
                dev = InputDevice(path)
            except (PermissionError, OSError):
                continue
            if match_name and match_name.lower() in dev.name.lower():
                return dev
            if not match_name and _AUTO_NAME_RE.search(dev.name):
                if _has_button_capability(dev):
                    return dev
                saw_match_without_buttons = True
                continue

        if saw_match_without_buttons:
            raise DeviceNotFoundError(
                "found Logitech device(s) but none expose button (BTN_*) "
                "capabilities; run `logitechmouse devices` and pass the "
                "correct node via --device"
            )
        criterion = f"name~{match_name!r}" if match_name else "auto-discovery"
        raise DeviceNotFoundError(
            f"no input device matched {criterion}; try `logitechmouse devices`"
        )

    def read_loop(self, device: InputDevice) -> Iterator[InputEvent]:
        """Yield InputEvent for every key-down on `device`. Blocking."""
        for event in device.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            if event.value != 1:
                continue
            key_event = categorize(event)
            keycode = key_event.keycode
            name = keycode[0] if isinstance(keycode, list) else keycode
            yield InputEvent(trigger=name)
