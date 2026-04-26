from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from evdev import ecodes

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
    button_codes: list = field(default_factory=lambda: [ecodes.BTN_LEFT])

    @property
    def info(self):
        class _I:
            vendor = self.vendor
            product = self.product
        return _I()

    def capabilities(self):
        return {ecodes.EV_KEY: list(self.button_codes)}


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


def test_resolve_by_explicit_path():
    devices = [FakeEvdev("/dev/input/event5", "Logitech MX Master 3S")]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig(path="/dev/input/event5"))
    assert dev.path == "/dev/input/event5"


def test_resolve_explicit_path_unreadable_raises():
    devices = [FakeEvdev("/dev/input/event5", "x", readable=False)]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceUnreadableError):
        EvdevBackend().resolve(DeviceConfig(path="/dev/input/event5"))


def test_resolve_by_name_substring_case_insensitive():
    devices = [
        FakeEvdev("/dev/input/event4", "AT Keyboard"),
        FakeEvdev("/dev/input/event5", "Logitech MX Master 3S"),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig(name="mx master"))
    assert dev.path == "/dev/input/event5"


def test_resolve_auto_matches_logitech_or_mx():
    devices = [
        FakeEvdev("/dev/input/event4", "AT Keyboard"),
        FakeEvdev("/dev/input/event5", "Logitech USB Receiver Mouse"),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig())
    assert dev.path == "/dev/input/event5"


def test_resolve_not_found_raises():
    devices = [FakeEvdev("/dev/input/event4", "AT Keyboard")]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceNotFoundError):
        EvdevBackend().resolve(DeviceConfig())


def test_resolve_path_missing_raises_not_found():
    devices = [FakeEvdev("/dev/input/event5", "Logitech MX Master 3S")]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceNotFoundError):
        EvdevBackend().resolve(DeviceConfig(path="/dev/input/event99"))


def test_resolve_auto_all_matches_without_button_codes_raises_actionable():
    devices = [
        FakeEvdev(
            "/dev/input/event4",
            "Logitech USB Receiver Consumer Control",
            button_codes=[],
        ),
        FakeEvdev(
            "/dev/input/event5",
            "Logitech USB Receiver Keyboard",
            button_codes=[],
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        with pytest.raises(DeviceNotFoundError) as exc_info:
            EvdevBackend().resolve(DeviceConfig())

    msg = str(exc_info.value).lower()
    assert "button" in msg
    assert "devices" in msg  # tells user to inspect via `logitechmouse devices`
    assert "--device" in msg  # tells user to pass --device


def test_resolve_auto_skips_logitech_subnode_without_button_codes():
    devices = [
        FakeEvdev(
            "/dev/input/event4",
            "Logitech USB Receiver Consumer Control",
            button_codes=[],
        ),
        FakeEvdev(
            "/dev/input/event5",
            "Logitech USB Receiver Mouse",
            button_codes=[ecodes.BTN_LEFT, ecodes.BTN_TASK],
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig())
    assert dev.path == "/dev/input/event5"
