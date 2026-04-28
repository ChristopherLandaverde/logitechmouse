from __future__ import annotations

import logging
from typing import Iterable

from evdev import InputDevice, UInput, ecodes

logger = logging.getLogger(__name__)


# UInput reserves EV_SYN; mice never produce these others, but caps may
# advertise them on virtual or composite devices. Stripping keeps the
# UInput constructor from raising.
_DROP_TYPES: frozenset[int] = frozenset({
    ecodes.EV_SYN,
    ecodes.EV_FF,
    ecodes.EV_FF_STATUS,
    ecodes.EV_LED,
    ecodes.EV_SND,
    ecodes.EV_PWR,
})


def _filter_capabilities(caps: dict[int, Iterable[int]]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for ev_type, codes in caps.items():
        if ev_type in _DROP_TYPES:
            continue
        codes_list = list(codes)
        if not codes_list:
            continue
        out[ev_type] = codes_list
    return out


class VirtualDevice:
    """Thin wrapper around evdev.UInput.

    Mirrors a real device's capabilities so the kernel exposes a virtual
    mouse that forwarded events can be written to. Owns lifetime of the
    underlying UInput; safe to close more than once.
    """

    DEFAULT_NAME = "logitechmouse virtual"

    def __init__(self, caps: dict[int, Iterable[int]], name: str = DEFAULT_NAME) -> None:
        filtered = _filter_capabilities(caps)
        self._ui = UInput(filtered, name=name)
        self._closed = False

    def write_event(self, event) -> None:
        """Forward a raw evdev InputEvent to the virtual device.

        EV_SYN is mapped to UInput.syn() so frame boundaries are preserved.
        Everything else goes through UInput.write(type, code, value).
        Silently no-ops after close() so the listener's worker thread can
        race with main-thread teardown without raising EBADF.
        """
        if self._closed:
            return
        if event.type == ecodes.EV_SYN:
            self._ui.syn()
        else:
            self._ui.write(event.type, event.code, event.value)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._ui.close()
        finally:
            self._closed = True

    def __enter__(self) -> "VirtualDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def try_grab(real_dev: InputDevice) -> "VirtualDevice | None":
    """Build a virtual mirror, grab the real device, return the mirror.

    Returns None (and logs one WARNING) when:
      - /dev/uinput is missing (FileNotFoundError)
      - the user lacks write permission on /dev/uinput (PermissionError)
      - the real device is already grabbed by another process (OSError)

    Callers must treat None as "grab disabled, dual-fire possible" and
    proceed without forwarding.
    """
    try:
        caps = real_dev.capabilities()
    except (OSError, AttributeError) as exc:
        logger.warning(
            "could not read capabilities of %s (%s); device grab disabled, "
            "bound buttons may fire twice in focused apps. See README "
            "Troubleshooting → buttons fire twice.",
            getattr(real_dev, "path", "?"),
            exc,
        )
        return None

    try:
        virt = VirtualDevice(caps)
    except FileNotFoundError:
        logger.warning(
            "/dev/uinput not present; device grab disabled, bound buttons "
            "may fire twice in focused apps. See README Troubleshooting → "
            "buttons fire twice."
        )
        return None
    except PermissionError:
        logger.warning(
            "/dev/uinput exists but permission denied for this user; device "
            "grab disabled, bound buttons may fire twice in focused apps. "
            "See README Troubleshooting → buttons fire twice."
        )
        return None

    try:
        real_dev.grab()
    except OSError as exc:
        logger.warning(
            "could not grab %s (%s); another process may already hold it. "
            "Device grab disabled, bound buttons may fire twice. See README "
            "Troubleshooting → buttons fire twice.",
            getattr(real_dev, "path", "?"),
            exc,
        )
        virt.close()
        return None

    return virt
