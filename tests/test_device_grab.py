from unittest.mock import MagicMock, patch

from evdev import InputDevice, ecodes

from logitechmouse.device_grab import VirtualDevice, _filter_capabilities, try_grab


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


def _fake_real_dev():
    dev = MagicMock(spec=InputDevice)
    dev.capabilities.return_value = _fake_caps()
    dev.path = "/dev/input/event99"
    dev.name = "fake mouse"
    return dev


def test_try_grab_happy_path_returns_virtual_device_and_grabs_real():
    fake_ui = MagicMock()
    real = _fake_real_dev()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        v = try_grab(real)
    assert isinstance(v, VirtualDevice)
    real.grab.assert_called_once_with()


def test_try_grab_returns_none_when_uinput_missing(caplog):
    real = _fake_real_dev()
    with patch(
        "logitechmouse.device_grab.UInput",
        side_effect=FileNotFoundError("/dev/uinput"),
    ):
        with caplog.at_level("WARNING"):
            v = try_grab(real)
    assert v is None
    real.grab.assert_not_called()
    assert any("uinput" in rec.message.lower() for rec in caplog.records)


def test_try_grab_returns_none_when_uinput_perm_denied(caplog):
    real = _fake_real_dev()
    with patch(
        "logitechmouse.device_grab.UInput",
        side_effect=PermissionError("/dev/uinput"),
    ):
        with caplog.at_level("WARNING"):
            v = try_grab(real)
    assert v is None
    real.grab.assert_not_called()
    assert any("permission" in rec.message.lower() for rec in caplog.records)


def test_try_grab_returns_none_when_real_device_already_grabbed(caplog):
    real = _fake_real_dev()
    real.grab.side_effect = OSError("already grabbed")
    fake_ui = MagicMock()
    with patch("logitechmouse.device_grab.UInput", return_value=fake_ui):
        with caplog.at_level("WARNING"):
            v = try_grab(real)
    assert v is None
    fake_ui.close.assert_called_once_with()  # virtual device cleaned up


def test_try_grab_returns_none_when_capabilities_read_fails(caplog):
    """If capabilities() raises (device disappeared / disconnect race),
    try_grab logs a WARNING and returns None without calling grab()."""
    real = _fake_real_dev()
    real.capabilities.side_effect = OSError("no such device")
    with caplog.at_level("WARNING"):
        v = try_grab(real)
    assert v is None
    real.grab.assert_not_called()
    msg = " ".join(rec.message for rec in caplog.records).lower()
    assert "fire twice" in msg or "troubleshooting" in msg


def test_try_grab_warning_mentions_dual_fire_remediation(caplog):
    """The warning must point users at the docs so the fallback is debuggable."""
    real = _fake_real_dev()
    with patch(
        "logitechmouse.device_grab.UInput",
        side_effect=FileNotFoundError("/dev/uinput"),
    ):
        with caplog.at_level("WARNING"):
            try_grab(real)
    msg = " ".join(rec.message for rec in caplog.records).lower()
    assert "dual" in msg or "fire twice" in msg or "troubleshooting" in msg
