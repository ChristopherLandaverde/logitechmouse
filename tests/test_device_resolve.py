from dataclasses import dataclass
from unittest.mock import patch

import pytest

from logitechmouse.config import DeviceConfig
from logitechmouse.device import (
    CandidateDevice,
    DeviceNotFoundError,
    DeviceUnreadableError,
    EvdevBackend,
)


@dataclass
class FakeEvdev:
    path: str
    name: str
    vendor: int = 0x046D
    product: int = 0x4082
    readable: bool = True

    @property
    def info(self):
        class _I:
            vendor = self.vendor
            product = self.product
        return _I()


def make_factory(devices):
    """Return a callable that mimics evdev.InputDevice(path)."""
    by_path = {d.path: d for d in devices}

    def factory(path):
        d = by_path.get(path)
        if d is None or not d.readable:
            raise PermissionError(f"cannot open {path}")
        return d

    return factory


def patch_backend(devices):
    paths = [d.path for d in devices]
    factory = make_factory(devices)
    return (
        patch("logitechmouse.device.list_devices", return_value=paths),
        patch("logitechmouse.device.InputDevice", side_effect=factory),
    )


def test_list_candidates_marks_unreadable(monkeypatch):
    devices = [
        FakeEvdev("/dev/input/event5", "Logitech MX Master 3S"),
        FakeEvdev("/dev/input/event7", "Locked Device", readable=False),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        result = EvdevBackend().list_candidates()

    assert len(result) == 2
    by_path = {c.path: c for c in result}
    assert by_path["/dev/input/event5"].readable is True
    assert by_path["/dev/input/event5"].name == "Logitech MX Master 3S"
    assert by_path["/dev/input/event7"].readable is False
