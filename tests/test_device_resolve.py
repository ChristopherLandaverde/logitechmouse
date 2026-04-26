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
    closed: bool = False

    @property
    def info(self):
        class _I:
            vendor = self.vendor
            product = self.product
        return _I()

    def capabilities(self):
        return {ecodes.EV_KEY: list(self.button_codes)}

    def close(self):
        self.closed = True


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


def test_resolve_closes_losing_candidates():
    """Each non-winning InputDevice opened during resolution must be released
    so we don't accumulate open file descriptors across long-running listens."""
    winner = FakeEvdev(
        "/dev/input/event5",
        "Logitech USB Receiver Mouse",
        button_codes=[ecodes.BTN_LEFT, ecodes.BTN_TASK],
    )
    loser = FakeEvdev(
        "/dev/input/event4",
        "Logitech Receiver Consumer Control",
        button_codes=[],
    )
    devices = [loser, winner]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig())
    assert dev.path == "/dev/input/event5"
    assert loser.closed is True
    assert winner.closed is False  # caller owns the winner; do NOT close it


def test_list_candidates_closes_inspected_devices():
    """list_candidates() inspects every node but returns metadata only;
    each opened device must be released."""
    devs = [
        FakeEvdev("/dev/input/event5", "Logitech MX Master 3S"),
        FakeEvdev("/dev/input/event7", "Other thing"),
    ]
    p1, p2 = patch_backend(devs)
    with p1, p2:
        EvdevBackend().list_candidates()
    assert all(d.closed for d in devs)


def test_resolve_raises_when_no_match_advertises_configured_triggers():
    """A subnode with BTN_LEFT only is button-capable but useless to a user
    who bound BTN_TASK. With explicit triggers, this must surface as an
    actionable error naming the missing trigger codes — not silently pick
    the device and never fire."""
    devices = [
        FakeEvdev(
            "/dev/input/event28",
            "Logitech USB Receiver",
            button_codes=[ecodes.BTN_LEFT],  # button-capable but no BTN_TASK
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceNotFoundError) as exc_info:
        EvdevBackend().resolve(DeviceConfig(), triggers={"BTN_TASK"})
    msg = str(exc_info.value)
    assert "BTN_TASK" in msg
    assert "--device" in msg


def test_resolve_auto_prefers_subnode_advertising_configured_triggers():
    """When multiple Logitech subnodes are button-capable, the one that
    actually advertises the user's configured trigger codes wins, even
    if it isn't first in iteration order."""
    devices = [
        FakeEvdev(
            "/dev/input/event28",
            "Logitech USB Receiver",
            button_codes=[ecodes.BTN_TOUCH, ecodes.BTN_TOOL_DOUBLETAP],
        ),
        FakeEvdev(
            "/dev/input/event25",
            "Logitech USB Receiver Mouse",
            button_codes=[ecodes.BTN_LEFT, ecodes.BTN_SIDE, ecodes.BTN_TASK],
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(
            DeviceConfig(), triggers={"BTN_TASK", "BTN_SIDE"}
        )
    assert dev.path == "/dev/input/event25"


def test_list_candidates_reports_button_capable_flag():
    devices = [
        FakeEvdev(
            "/dev/input/event4",
            "Logitech Receiver Consumer Control",
            button_codes=[],
        ),
        FakeEvdev(
            "/dev/input/event5",
            "Logitech MX Master 3S Mouse",
            button_codes=[ecodes.BTN_LEFT, ecodes.BTN_TASK],
        ),
        FakeEvdev(
            "/dev/input/event7",
            "Locked Device",
            readable=False,
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        result = EvdevBackend().list_candidates()

    by_path = {c.path: c for c in result}
    assert by_path["/dev/input/event4"].button_capable is False
    assert by_path["/dev/input/event5"].button_capable is True
    # Unreadable nodes can't be inspected; flag must be False (not None) for table rendering.
    assert by_path["/dev/input/event7"].button_capable is False


def test_resolve_explicit_path_bypasses_capability_filter_with_warning(caplog):
    devices = [
        FakeEvdev(
            "/dev/input/event4",
            "Some Generic Pedal",
            button_codes=[],  # no BTN_* codes
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2, caplog.at_level("WARNING"):
        dev = EvdevBackend().resolve(DeviceConfig(path="/dev/input/event4"))
    assert dev.path == "/dev/input/event4"
    assert any("button" in rec.message.lower() for rec in caplog.records)


def test_resolve_by_name_substring_skips_node_without_button_codes():
    devices = [
        FakeEvdev(
            "/dev/input/event4",
            "Logitech MX Master Consumer Control",
            button_codes=[],
        ),
        FakeEvdev(
            "/dev/input/event5",
            "Logitech MX Master 3S Mouse",
            button_codes=[ecodes.BTN_LEFT, ecodes.BTN_TASK],
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig(name="mx master"))
    assert dev.path == "/dev/input/event5"


def test_resolve_by_name_substring_all_without_button_codes_raises_actionable():
    devices = [
        FakeEvdev(
            "/dev/input/event4",
            "Logitech MX Master Consumer Control",
            button_codes=[],
        ),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceNotFoundError) as exc_info:
        EvdevBackend().resolve(DeviceConfig(name="mx master"))
    msg = str(exc_info.value).lower()
    assert "button" in msg
    assert "--device" in msg


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
