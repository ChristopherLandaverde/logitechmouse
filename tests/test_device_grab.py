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
