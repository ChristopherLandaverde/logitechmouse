"""End-to-end uinput integration. Skipped on CI without /dev/uinput."""

import time

import pytest

evdev = pytest.importorskip("evdev")
from evdev import InputDevice, UInput, ecodes, list_devices  # noqa: E402

from logitechmouse.device import EvdevBackend  # noqa: E402
from logitechmouse.device_grab import try_grab  # noqa: E402


pytestmark = pytest.mark.requires_uinput


def _open_source_device():
    """Make a uinput source device that emits the events we want to test."""
    caps = {
        ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_BACK],
        ecodes.EV_REL: [ecodes.REL_X],
    }
    src = UInput(caps, name="logitechmouse-test-src")
    # Wait for udev to expose the new node.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        for path in list_devices():
            try:
                d = InputDevice(path)
            except OSError:
                continue
            if d.name == "logitechmouse-test-src":
                return src, d
            d.close()
        time.sleep(0.05)
    src.close()
    pytest.skip("could not find the test source device after 2s")


def test_grab_and_forward_end_to_end():
    src, real = _open_source_device()
    try:
        virt = try_grab(real)
        if virt is None:
            pytest.skip("try_grab returned None on a system that should support uinput")

        # Emit one bound + one unbound + a sync.
        src.write(ecodes.EV_KEY, ecodes.BTN_BACK, 1)
        src.write(ecodes.EV_REL, ecodes.REL_X, 7)
        src.syn()
        src.write(ecodes.EV_KEY, ecodes.BTN_BACK, 0)
        src.syn()

        # Drain a few events from the backend, then stop.
        events = []
        gen = EvdevBackend().read_loop(
            real, swallow_codes={ecodes.BTN_BACK}, virt=virt
        )
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(events) < 2:
            try:
                events.append(next(gen))
            except StopIteration:
                break

        # Backend must yield BTN_BACK down + up (bound trigger) and nothing else.
        assert [(e.trigger, e.pressed) for e in events] == [
            ("BTN_BACK", True),
            ("BTN_BACK", False),
        ]
    finally:
        try:
            virt.close()
        except Exception:
            pass
        try:
            real.ungrab()
        except Exception:
            pass
        src.close()
