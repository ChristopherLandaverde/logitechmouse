from evdev import ecodes

from logitechmouse.device_grab import _filter_capabilities


def test_filter_capabilities_drops_reserved_and_irrelevant_types():
    raw = {
        ecodes.EV_SYN: [0, 1, 2],          # reserved by UInput
        ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
        ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL],
        ecodes.EV_MSC: [ecodes.MSC_SCAN],
        ecodes.EV_FF: [0],                 # mice never have this
        ecodes.EV_LED: [0],
    }
    out = _filter_capabilities(raw)

    assert ecodes.EV_SYN not in out
    assert ecodes.EV_FF not in out
    assert ecodes.EV_LED not in out
    assert out[ecodes.EV_KEY] == [ecodes.BTN_LEFT, ecodes.BTN_RIGHT]
    assert out[ecodes.EV_REL] == [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]
    assert out[ecodes.EV_MSC] == [ecodes.MSC_SCAN]


def test_filter_capabilities_drops_empty_lists():
    raw = {ecodes.EV_KEY: [], ecodes.EV_REL: [ecodes.REL_X]}
    out = _filter_capabilities(raw)
    assert ecodes.EV_KEY not in out
    assert out[ecodes.EV_REL] == [ecodes.REL_X]


from unittest.mock import MagicMock, patch

from logitechmouse.device_grab import VirtualDevice


def _fake_caps():
    return {ecodes.EV_KEY: [ecodes.BTN_LEFT], ecodes.EV_REL: [ecodes.REL_X]}


def test_virtual_device_constructs_uinput_with_filtered_caps():
    with patch("logitechmouse.device_grab.UInput") as ui:
        VirtualDevice(_fake_caps(), name="logitechmouse virtual")
        ui.assert_called_once()
        kwargs = ui.call_args.kwargs
        # First positional or `events` keyword carries the caps dict.
        passed_caps = ui.call_args.args[0] if ui.call_args.args else kwargs["events"]
        assert ecodes.EV_KEY in passed_caps and ecodes.EV_REL in passed_caps
        assert kwargs.get("name") == "logitechmouse virtual"


def test_virtual_device_write_event_forwards_to_uinput():
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        v = VirtualDevice(_fake_caps())

    raw = MagicMock(type=ecodes.EV_REL, code=ecodes.REL_X, value=3)
    v.write_event(raw)
    fake_ui.write.assert_called_once_with(ecodes.EV_REL, ecodes.REL_X, 3)
    fake_ui.syn.assert_not_called()


def test_virtual_device_write_event_calls_syn_on_ev_syn():
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        v = VirtualDevice(_fake_caps())

    syn_event = MagicMock(type=ecodes.EV_SYN, code=ecodes.SYN_REPORT, value=0)
    v.write_event(syn_event)
    fake_ui.syn.assert_called_once_with()
    fake_ui.write.assert_not_called()


def test_virtual_device_close_closes_uinput():
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        v = VirtualDevice(_fake_caps())
    v.close()
    fake_ui.close.assert_called_once_with()


def test_virtual_device_context_manager_closes_on_exit():
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        with VirtualDevice(_fake_caps()) as v:
            assert v is not None
    fake_ui.close.assert_called_once_with()


def test_virtual_device_close_is_idempotent():
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        v = VirtualDevice(_fake_caps())
    v.close()
    v.close()
    assert fake_ui.close.call_count == 1


def test_virtual_device_write_event_after_close_is_silent():
    """Worker-thread races with main-thread close must not raise EBADF."""
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        v = VirtualDevice(_fake_caps())
    v.close()
    raw = MagicMock(type=ecodes.EV_REL, code=ecodes.REL_X, value=1)
    v.write_event(raw)  # must not raise
    fake_ui.write.assert_not_called()
    fake_ui.syn.assert_not_called()
