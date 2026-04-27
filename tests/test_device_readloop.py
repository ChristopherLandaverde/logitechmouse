from unittest.mock import MagicMock

from evdev import ecodes

from logitechmouse.device import EvdevBackend, InputEvent


def _fake_kev(code: int, value: int):
    """Fabricate an evdev event-like object that categorize() handles."""
    e = MagicMock()
    e.type = ecodes.EV_KEY
    e.code = code
    e.value = value
    return e


def _fake_device_yielding(events):
    dev = MagicMock()
    dev.read_loop = MagicMock(return_value=iter(events))
    return dev


def test_read_loop_emits_key_down_with_pressed_true():
    dev = _fake_device_yielding([_fake_kev(ecodes.BTN_TASK, 1)])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [InputEvent(trigger="BTN_TASK", pressed=True)]


def test_read_loop_emits_key_up_with_pressed_false():
    dev = _fake_device_yielding([_fake_kev(ecodes.BTN_TASK, 0)])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [InputEvent(trigger="BTN_TASK", pressed=False)]


def test_read_loop_ignores_key_repeat():
    dev = _fake_device_yielding([
        _fake_kev(ecodes.BTN_TASK, 1),
        _fake_kev(ecodes.BTN_TASK, 2),  # repeat
        _fake_kev(ecodes.BTN_TASK, 0),
    ])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [
        InputEvent(trigger="BTN_TASK", pressed=True),
        InputEvent(trigger="BTN_TASK", pressed=False),
    ]


def test_read_loop_ignores_non_key_events():
    e_syn = MagicMock()
    e_syn.type = ecodes.EV_SYN
    dev = _fake_device_yielding([e_syn, _fake_kev(ecodes.BTN_SIDE, 1)])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [InputEvent(trigger="BTN_SIDE", pressed=True)]
