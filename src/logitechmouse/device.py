from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterator

from evdev import InputDevice, categorize, ecodes, list_devices

from .config import DeviceConfig

logger = logging.getLogger(__name__)


_AUTO_NAME_RE = re.compile(r"logitech|mx (master|anywhere|ergo|vertical)", re.IGNORECASE)

_BTN_MIN = 0x100  # ecodes.BTN_MISC
_BTN_MAX = 0x151  # ecodes.BTN_GEAR_UP


def _has_button_capability(dev: InputDevice) -> bool:
    try:
        caps = dev.capabilities()
    except (OSError, AttributeError):
        return False
    keys = caps.get(ecodes.EV_KEY, []) or []
    return any(_BTN_MIN <= code <= _BTN_MAX for code in keys)


def _close_quietly(dev: InputDevice | None) -> None:
    if dev is None:
        return
    close = getattr(dev, "close", None)
    if close is None:
        return
    try:
        close()
    except (OSError, AttributeError):
        pass


def _score_for_triggers(dev: InputDevice, triggers: set[str] | None) -> int:
    """How well does this device match the user's intent?

    With explicit triggers: return the count of trigger codes the device
    advertises. With no triggers (or unknown trigger names): fall back to
    1 if the device exposes any BTN_*, else 0.
    """
    try:
        caps = dev.capabilities()
    except (OSError, AttributeError):
        return 0
    keys = set(caps.get(ecodes.EV_KEY, []) or [])
    if triggers:
        trigger_codes = {ecodes.ecodes[t] for t in triggers if t in ecodes.ecodes}
        if trigger_codes:
            return len(keys & trigger_codes)
    return 1 if any(_BTN_MIN <= k <= _BTN_MAX for k in keys) else 0


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
    button_capable: bool = False


@dataclass
class InputEvent:
    trigger: str  # evdev key code name, e.g. "BTN_TASK"


class EvdevBackend:
    def list_candidates(self) -> list[CandidateDevice]:
        candidates: list[CandidateDevice] = []
        for path in list_devices():
            dev = None
            try:
                dev = InputDevice(path)
                candidates.append(
                    CandidateDevice(
                        path=path,
                        name=dev.name,
                        vendor=dev.info.vendor,
                        product=dev.info.product,
                        readable=True,
                        button_capable=_has_button_capability(dev),
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
            finally:
                _close_quietly(dev)
        return candidates

    def resolve(
        self,
        device_cfg: DeviceConfig,
        triggers: set[str] | None = None,
    ) -> InputDevice:
        all_paths = list_devices()

        if device_cfg.path:
            if device_cfg.path not in all_paths:
                raise DeviceNotFoundError(
                    f"configured device path {device_cfg.path!r} not present"
                )
            try:
                dev = InputDevice(device_cfg.path)
            except (PermissionError, OSError) as exc:
                raise DeviceUnreadableError(str(exc)) from exc
            if not _has_button_capability(dev):
                logger.warning(
                    "device %s exposes no button (BTN_*) capabilities; "
                    "configured triggers may never fire",
                    device_cfg.path,
                )
            return dev

        match_name = device_cfg.name
        scored: list[tuple[InputDevice, int]] = []
        for path in all_paths:
            try:
                dev = InputDevice(path)
            except (PermissionError, OSError):
                continue
            if match_name:
                is_match = match_name.lower() in dev.name.lower()
            else:
                is_match = bool(_AUTO_NAME_RE.search(dev.name))
            if not is_match:
                _close_quietly(dev)
                continue
            scored.append((dev, _score_for_triggers(dev, triggers)))

        def _release_all_and_raise(exc: Exception) -> None:
            for d, _ in scored:
                _close_quietly(d)
            raise exc

        if not scored:
            criterion = f"name~{match_name!r}" if match_name else "auto-discovery"
            raise DeviceNotFoundError(
                f"no input device matched {criterion}; try `logitechmouse devices`"
            )

        best_dev, best_score = max(scored, key=lambda pair: pair[1])
        if best_score == 0:
            if triggers:
                wanted = ", ".join(sorted(triggers))
                _release_all_and_raise(DeviceNotFoundError(
                    f"found Logitech device(s) but none advertise the "
                    f"configured trigger codes ({wanted}); run "
                    f"`logitechmouse devices` and pass the correct node "
                    f"via --device"
                ))
            _release_all_and_raise(DeviceNotFoundError(
                "found Logitech device(s) but none expose button (BTN_*) "
                "capabilities; run `logitechmouse devices` and pass the "
                "correct node via --device"
            ))

        for dev, _ in scored:
            if dev is not best_dev:
                _close_quietly(dev)
        return best_dev

    def read_loop(self, device: InputDevice) -> Iterator[InputEvent]:
        """Yield InputEvent for every key-down on `device`. Blocking."""
        for event in device.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            if event.value != 1:
                continue
            key_event = categorize(event)
            keycode = key_event.keycode
            if isinstance(keycode, list):
                name = keycode[0] if keycode else None
            elif isinstance(keycode, str):
                name = keycode
            else:
                name = None
            if not name:
                continue
            yield InputEvent(trigger=name)
