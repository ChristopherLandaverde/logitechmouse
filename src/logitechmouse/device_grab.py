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
