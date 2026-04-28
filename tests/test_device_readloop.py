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


def _ev(type_, code, value):
    e = MagicMock()
    e.type = type_
    e.code = code
    e.value = value
    return e


def test_read_loop_forwards_unbound_ev_key_to_virt():
    real = MagicMock()
    real.read_loop.return_value = iter([
        _ev(ecodes.EV_KEY, ecodes.BTN_LEFT, 1),  # unbound -> forward
    ])
    virt = MagicMock()

    list(EvdevBackend().read_loop(
        real, swallow_codes={ecodes.BTN_BACK}, virt=virt
    ))

    virt.write_event.assert_called_once()
    # The forwarded event is the same object we put in.
    assert virt.write_event.call_args.args[0].code == ecodes.BTN_LEFT


def test_read_loop_swallows_bound_ev_key():
    real = MagicMock()
    real.read_loop.return_value = iter([
        _ev(ecodes.EV_KEY, ecodes.BTN_BACK, 1),
    ])
    virt = MagicMock()

    list(EvdevBackend().read_loop(
        real, swallow_codes={ecodes.BTN_BACK}, virt=virt
    ))

    virt.write_event.assert_not_called()


def test_read_loop_forwards_ev_rel_and_ev_syn():
    real = MagicMock()
    real.read_loop.return_value = iter([
        _ev(ecodes.EV_REL, ecodes.REL_X, 5),
        _ev(ecodes.EV_SYN, ecodes.SYN_REPORT, 0),
    ])
    virt = MagicMock()

    list(EvdevBackend().read_loop(
        real, swallow_codes={ecodes.BTN_BACK}, virt=virt
    ))

    assert virt.write_event.call_count == 2


def test_read_loop_yields_input_event_for_bound_key_down_and_up():
    real = MagicMock()
    real.read_loop.return_value = iter([
        _ev(ecodes.EV_KEY, ecodes.BTN_BACK, 1),  # down
        _ev(ecodes.EV_KEY, ecodes.BTN_BACK, 0),  # up
    ])

    out = list(EvdevBackend().read_loop(
        real, swallow_codes={ecodes.BTN_BACK}, virt=MagicMock()
    ))

    assert [(e.trigger, e.pressed) for e in out] == [
        ("BTN_BACK", True),
        ("BTN_BACK", False),
    ]


def test_read_loop_no_virt_means_no_forwarding_no_crash():
    """Existing callers (without grab) must keep working unchanged."""
    real = MagicMock()
    real.read_loop.return_value = iter([
        _ev(ecodes.EV_KEY, ecodes.BTN_BACK, 1),
        _ev(ecodes.EV_REL, ecodes.REL_X, 5),
    ])

    out = list(EvdevBackend().read_loop(real))  # no swallow_codes, no virt
    assert len(out) == 1
    assert out[0].trigger == "BTN_BACK"
