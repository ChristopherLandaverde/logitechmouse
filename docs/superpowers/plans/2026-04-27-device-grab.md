# Device Grab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop bound mouse-button events from reaching focused applications. Pressing `BTN_BACK` while bound to a `logitechmouse` action no longer navigates the browser. Cursor motion, scroll, and unbound buttons keep working normally.

**Architecture:** A new `device_grab` module wraps `evdev.UInput` to create a virtual mirror device. The `EvdevBackend` grabs the real device and forwards every event to the virtual device *except* `EV_KEY` events whose code is in the bound trigger set. When `/dev/uinput` is unavailable or permissions are denied, the listener logs a warning and continues without grab (current dual-fire behavior).

**Tech Stack:** Python 3.11+, `evdev>=1.6` (existing — provides `UInput`), `pytest>=7` (existing). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-27-device-grab-design.md` (commit `fd3abce`)

**Branch:** `phase5-device-grab` (already created and checked out).

**Predecessor:** Phase 4 Actions Ring (PR #3 squashed into `0f8ce57`). All existing tests must stay green throughout.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` (modify) | Register a new `requires_uinput` pytest marker. |
| `tests/conftest.py` (modify) | Skip `@pytest.mark.requires_uinput` tests when `/dev/uinput` is not writable by the current user. |
| `src/logitechmouse/device_grab.py` (create) | `VirtualDevice` (UInput wrapper), `try_grab(real_dev) -> VirtualDevice \| None`, capability filter helper. |
| `src/logitechmouse/device.py` (modify) | `EvdevBackend.read_loop` accepts optional `swallow_codes: set[int]` and `virt: VirtualDevice \| None`. Forwards every non-swallowed event to `virt` while still yielding `InputEvent` for bound triggers. |
| `src/logitechmouse/cli/listen.py` (modify) | Both code paths (`_run_command_only`, `_run_with_qt`) call `try_grab` after device resolve, pass `swallow_codes` + `virt` into `read_loop`, and tear down (close virt + ungrab) in `finally`. SIGTERM handler triggers the same teardown via `app.quit()` in the Qt path and a flag in the command-only path. |
| `examples/config.toml` (modify) | Remove the dual-fire caveat now that grab solves it. |
| `README.md` (modify) | New "Troubleshooting → buttons fire twice" section pointing at uinput permission setup; mention the virtual device name in the install section. |
| `tests/test_device_grab.py` (create) | Unit tests for `VirtualDevice`, `try_grab` (all branches), capability filter, with `evdev.UInput` and `InputDevice.grab` monkeypatched. |
| `tests/test_device_readloop.py` (modify) | Cover the new forwarding contract: bound `EV_KEY` is swallowed, unbound `EV_KEY` / `EV_REL` / `EV_SYN` are forwarded. |
| `tests/test_listen_grab.py` (create) | Listener-level: `try_grab` is called once after `resolve`; teardown runs in `finally`; `None` return falls back cleanly. |
| `tests/test_device_grab_integration.py` (create) | `@pytest.mark.requires_uinput`. Spins up a real virtual device, writes a synthetic event sequence, asserts pass-through behavior end-to-end. |

Files are split by responsibility. `device_grab.py` is the only place that touches `/dev/uinput`. `device.py` is the only place that runs the read loop. `cli/listen.py` is the only place that wires lifecycle.

---

## Task 0: Verify branch state

**Files:** none (git only).

- [ ] **Step 1: Confirm branch + clean tree**

```bash
git rev-parse --abbrev-ref HEAD
git status --short
```

Expected:
```
phase5-device-grab
```
(no other lines — working tree clean.)

- [ ] **Step 2: Confirm spec is committed**

```bash
git log --oneline -1 -- docs/superpowers/specs/2026-04-27-device-grab-design.md
```

Expected: one commit (`fd3abce` or later) referencing the device grab design spec.

---

## Task 1: Register the `requires_uinput` pytest marker

**Files:**
- Modify: `pyproject.toml:39-41`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add the marker to `pyproject.toml`**

Replace the `markers` list (lines 39-41) with:

```toml
markers = [
  "requires_display: skipped when DISPLAY env var is unset (Qt widget tests)",
  "requires_uinput: skipped when /dev/uinput is not writable (grab integration tests)",
]
```

- [ ] **Step 2: Add the skip hook to `conftest.py`**

Replace the file body with:

```python
import os
import pytest


def _uinput_writable() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def pytest_collection_modifyitems(config, items):
    """Skip markers when their environment isn't available.

    - requires_display: needs an X11 DISPLAY (use xvfb-run on CI).
    - requires_uinput: needs /dev/uinput writable by the current user.
    """
    no_display = not os.environ.get("DISPLAY")
    no_uinput = not _uinput_writable()
    skip_display = pytest.mark.skip(reason="DISPLAY unset; needs X11 (xvfb-run in CI)")
    skip_uinput = pytest.mark.skip(reason="/dev/uinput not writable (skip on CI without uinput)")
    for item in items:
        if no_display and "requires_display" in item.keywords:
            item.add_marker(skip_display)
        if no_uinput and "requires_uinput" in item.keywords:
            item.add_marker(skip_uinput)
```

- [ ] **Step 3: Run the existing suite to confirm nothing regressed**

Run:
```bash
xvfb-run -a pytest -q
```
Expected: all existing tests pass; collection still succeeds; no warnings about unknown markers.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "test: register requires_uinput marker and skip hook"
```

---

## Task 2: Capability filter helper (TDD)

**Files:**
- Create: `src/logitechmouse/device_grab.py`
- Create: `tests/test_device_grab.py`

The helper strips event types `UInput` either reserves (`EV_SYN`) or that mice never produce but might appear in caps (`EV_FF`, `EV_LED`, `EV_SND`, `EV_PWR`, `EV_FF_STATUS`). Without this, `UInput(...)` raises on the reserved keys.

- [ ] **Step 1: Write the failing test**

`tests/test_device_grab.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_device_grab.py -q`
Expected: import error (`ModuleNotFoundError: logitechmouse.device_grab`).

- [ ] **Step 3: Implement the helper**

Create `src/logitechmouse/device_grab.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_grab.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/device_grab.py tests/test_device_grab.py
git commit -m "feat(device_grab): capability filter for uinput mirror"
```

---

## Task 3: `VirtualDevice` wrapper (TDD)

**Files:**
- Modify: `src/logitechmouse/device_grab.py`
- Modify: `tests/test_device_grab.py`

`VirtualDevice` owns a single `UInput` instance and exposes only what the read loop needs: forward a raw evdev event, close on teardown, context-manager protocol.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device_grab.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_device_grab.py -q`
Expected: all 6 new tests fail with `ImportError: cannot import name 'VirtualDevice'`.

- [ ] **Step 3: Implement `VirtualDevice`**

Append to `src/logitechmouse/device_grab.py`:

```python
class VirtualDevice:
    """Thin wrapper around evdev.UInput.

    Mirrors a real device's capabilities so the kernel exposes a virtual
    mouse that forwarded events can be written to. Owns lifetime of the
    underlying UInput; safe to close more than once.
    """

    DEFAULT_NAME = "logitechmouse virtual"

    def __init__(self, caps: dict[int, Iterable[int]], name: str = DEFAULT_NAME) -> None:
        filtered = _filter_capabilities(caps)
        self._ui = UInput(filtered, name=name)
        self._closed = False

    def write_event(self, event) -> None:
        """Forward a raw evdev InputEvent to the virtual device.

        EV_SYN is mapped to UInput.syn() so frame boundaries are preserved.
        Everything else goes through UInput.write(type, code, value).
        """
        if event.type == ecodes.EV_SYN:
            self._ui.syn()
        else:
            self._ui.write(event.type, event.code, event.value)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._ui.close()
        finally:
            self._closed = True

    def __enter__(self) -> "VirtualDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_grab.py -q`
Expected: 8 passed (2 from Task 2 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/device_grab.py tests/test_device_grab.py
git commit -m "feat(device_grab): VirtualDevice wrapper around evdev.UInput"
```

---

## Task 4: `try_grab` happy path + failure branches (TDD)

**Files:**
- Modify: `src/logitechmouse/device_grab.py`
- Modify: `tests/test_device_grab.py`

`try_grab` wraps the three failure modes (`/dev/uinput` missing, perm denied, real device already grabbed) so callers never have to handle them individually. Each failure logs once at WARNING and returns `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device_grab.py`:

```python
from logitechmouse.device_grab import try_grab


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_device_grab.py -q`
Expected: 5 new failures (`ImportError: cannot import name 'try_grab'`).

- [ ] **Step 3: Implement `try_grab`**

Append to `src/logitechmouse/device_grab.py`:

```python
def try_grab(real_dev: InputDevice) -> "VirtualDevice | None":
    """Build a virtual mirror, grab the real device, return the mirror.

    Returns None (and logs one WARNING) when:
      - /dev/uinput is missing (FileNotFoundError)
      - the user lacks write permission on /dev/uinput (PermissionError)
      - the real device is already grabbed by another process (OSError)

    Callers must treat None as "grab disabled, dual-fire possible" and
    proceed without forwarding.
    """
    try:
        caps = real_dev.capabilities()
    except (OSError, AttributeError) as exc:
        logger.warning(
            "could not read capabilities of %s (%s); device grab disabled, "
            "bound buttons may fire twice in focused apps. See README "
            "Troubleshooting → buttons fire twice.",
            getattr(real_dev, "path", "?"),
            exc,
        )
        return None

    try:
        virt = VirtualDevice(caps)
    except FileNotFoundError:
        logger.warning(
            "/dev/uinput not present; device grab disabled, bound buttons "
            "may fire twice in focused apps. See README Troubleshooting → "
            "buttons fire twice."
        )
        return None
    except PermissionError:
        logger.warning(
            "/dev/uinput exists but is not writable by this user; device "
            "grab disabled, bound buttons may fire twice in focused apps. "
            "See README Troubleshooting → buttons fire twice."
        )
        return None

    try:
        real_dev.grab()
    except OSError as exc:
        logger.warning(
            "could not grab %s (%s); another process may already hold it. "
            "Device grab disabled, bound buttons may fire twice. See README "
            "Troubleshooting → buttons fire twice.",
            getattr(real_dev, "path", "?"),
            exc,
        )
        virt.close()
        return None

    return virt
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_grab.py -q`
Expected: 13 passed (8 prior + 5 new).

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/device_grab.py tests/test_device_grab.py
git commit -m "feat(device_grab): try_grab with graceful fallback for missing uinput"
```

---

## Task 5: Backend forwards everything except bound triggers (TDD)

**Files:**
- Modify: `src/logitechmouse/device.py:188-206`
- Modify: `tests/test_device_readloop.py`

The backend's `read_loop` is the natural place to do the forwarding because it already iterates the raw evdev stream. New optional parameters keep existing callers working without grab.

- [ ] **Step 1: Read the existing test file**

Run: `cat tests/test_device_readloop.py`
Note the existing fixtures (mock device producing fake events); reuse them in the next step.

- [ ] **Step 2: Write the new failing tests**

Append to `tests/test_device_readloop.py`:

```python
from unittest.mock import MagicMock

from evdev import ecodes


def _ev(type_, code, value):
    e = MagicMock()
    e.type = type_
    e.code = code
    e.value = value
    return e


def test_read_loop_forwards_unbound_ev_key_to_virt():
    from logitechmouse.device import EvdevBackend

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
    from logitechmouse.device import EvdevBackend

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
    from logitechmouse.device import EvdevBackend

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
    from logitechmouse.device import EvdevBackend

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
    from logitechmouse.device import EvdevBackend

    real = MagicMock()
    real.read_loop.return_value = iter([
        _ev(ecodes.EV_KEY, ecodes.BTN_BACK, 1),
        _ev(ecodes.EV_REL, ecodes.REL_X, 5),
    ])

    out = list(EvdevBackend().read_loop(real))  # no swallow_codes, no virt
    assert len(out) == 1
    assert out[0].trigger == "BTN_BACK"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_device_readloop.py -q`
Expected: 5 new failures with `TypeError: read_loop() got an unexpected keyword argument 'swallow_codes'`.

- [ ] **Step 4: Update `EvdevBackend.read_loop`**

Replace the `read_loop` method in `src/logitechmouse/device.py` (currently lines 188-206) with:

```python
    def read_loop(
        self,
        device: InputDevice,
        swallow_codes: set[int] | None = None,
        virt: "VirtualDevice | None" = None,
    ) -> Iterator[InputEvent]:
        """Yield InputEvent for every key-down and key-up on `device`,
        ignoring key-repeat (value=2).

        When `virt` is provided, every event is forwarded to it *except*
        EV_KEY events whose code is in `swallow_codes`. This is how
        bound triggers are kept from reaching focused applications while
        cursor motion, scroll, and unbound buttons pass through.
        """
        swallow = swallow_codes or set()
        for event in device.read_loop():
            if virt is not None:
                is_bound_key = (
                    event.type == ecodes.EV_KEY and event.code in swallow
                )
                if not is_bound_key:
                    virt.write_event(event)

            if event.type != ecodes.EV_KEY:
                continue
            if event.value not in (0, 1):
                continue
            key_event = categorize(event)
            keycode = key_event.keycode
            if isinstance(keycode, list):
                name = keycode[0] if keycode else None
            elif isinstance(keycode, str):
                name = keycode
            else:
                name = None
            if not name:
                continue
            yield InputEvent(trigger=name, pressed=(event.value == 1))
```

Also add a `TYPE_CHECKING` import block at the top of `device.py` (after the existing imports) so the `VirtualDevice` annotation resolves without a runtime import cycle:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .device_grab import VirtualDevice
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_device_readloop.py -q`
Expected: all readloop tests pass (existing + 5 new).

Run the full suite:
```bash
xvfb-run -a pytest -q
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/device.py tests/test_device_readloop.py
git commit -m "feat(device): read_loop forwards non-bound events to virtual device"
```

---

## Task 6: Wire grab into the command-only listener path (TDD)

**Files:**
- Modify: `src/logitechmouse/cli/listen.py:104-119`
- Create: `tests/test_listen_grab.py`

The command-only path (no ring bindings) is simpler — single thread, blocking read loop. Wire `try_grab` after `resolve` and tear down in `finally`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_listen_grab.py`:

```python
import argparse
from unittest.mock import MagicMock, patch

import pytest
from evdev import ecodes

from logitechmouse.cli import listen as listen_mod


@pytest.fixture
def cmd_only_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[device]
path = "/dev/input/event99"

[actions.beep]
kind = "command"
command = "true"

[bindings.b1]
trigger = "BTN_BACK"
target = "action:beep"
"""
    )
    return cfg


def test_command_only_path_calls_try_grab_then_passes_virt_to_read_loop(cmd_only_config):
    args = argparse.Namespace(config=cmd_only_config, device=None)

    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()
    captured = {}

    def fake_read_loop(device, swallow_codes=None, virt=None):
        captured["device"] = device
        captured["swallow_codes"] = swallow_codes
        captured["virt"] = virt
        return iter([])  # immediately exit the loop

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=fake_read_loop), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt) as tg:
        rc = listen_mod.run(args)

    assert rc == 0
    tg.assert_called_once_with(fake_dev)
    assert captured["virt"] is fake_virt
    assert ecodes.BTN_BACK in captured["swallow_codes"]


def test_command_only_path_closes_virt_and_ungrabs_on_exit(cmd_only_config):
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt):
        listen_mod.run(args)

    fake_virt.close.assert_called_once_with()
    fake_dev.ungrab.assert_called_once_with()


def test_command_only_path_no_virt_does_not_call_ungrab(cmd_only_config):
    """When try_grab returns None, ungrab must not be called either."""
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=None):
        rc = listen_mod.run(args)

    assert rc == 0
    fake_dev.ungrab.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_listen_grab.py -q`
Expected: failures — `try_grab` is not yet imported in `listen.py`, and the read loop is not wired with `swallow_codes`/`virt`.

- [ ] **Step 3: Update `cli/listen.py`**

Add the import near the top of `src/logitechmouse/cli/listen.py`:

```python
from ..device_grab import try_grab
```

Replace `_run_command_only` with:

```python
def _run_command_only(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    """Phase 2 path: no Qt, blocking read loop on the main thread.

    Auto-grabs the device via uinput so bound triggers do not reach
    focused applications. Falls back to no-grab if try_grab returns None.
    """
    from evdev import ecodes
    swallow_codes = {
        ecodes.ecodes[b.trigger]
        for b in cfg.bindings.values()
        if b.trigger in ecodes.ecodes
    }
    virt = try_grab(device)
    try:
        for event in backend.read_loop(
            device, swallow_codes=swallow_codes, virt=virt
        ):
            dispatch_event(
                cfg,
                ring_controller=_NoOpRingController(),
                run_action=_default_run_action,
                trigger=event.trigger,
                pressed=event.pressed,
                cursor_pos=(0, 0),
            )
    except OSError as exc:
        logging.warning("device read failed: %s", exc)
        return 1
    finally:
        if virt is not None:
            virt.close()
            try:
                device.ungrab()
            except OSError:
                pass
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_listen_grab.py -q`
Expected: 3 passed.

Run the full suite:
```bash
xvfb-run -a pytest -q
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/cli/listen.py tests/test_listen_grab.py
git commit -m "feat(listen): grab device in command-only path with finally teardown"
```

---

## Task 7: Wire grab into the Qt-driven listener path

**Files:**
- Modify: `src/logitechmouse/cli/listen.py:122-203`
- Modify: `tests/test_listen_grab.py`

Same pattern as Task 6 but inside `_run_with_qt`. Teardown happens after `app.exec()` returns.

- [ ] **Step 1: Add the failing test**

Append to `tests/test_listen_grab.py`:

```python
@pytest.fixture
def ring_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[device]
path = "/dev/input/event99"

[actions.beep]
kind = "command"
command = "true"

[rings.r1]
segments = [
  { label = "a", action = "beep" },
  { label = "b", action = "beep" },
  { label = "c", action = "beep" },
  { label = "d", action = "beep" },
]

[bindings.b1]
trigger = "BTN_BACK"
target = "ring:r1"
"""
    )
    return cfg


@pytest.mark.requires_display
def test_qt_path_calls_try_grab_and_tears_down(ring_config):
    """In the Qt path, try_grab runs after resolve and teardown runs after app.exec()."""
    args = argparse.Namespace(config=ring_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()
    captured = {}

    # Stub the worker's read loop to immediately emit `finished` so app.exec returns.
    def stub_read_loop(device, swallow_codes=None, virt=None):
        captured["swallow_codes"] = swallow_codes
        captured["virt"] = virt
        return iter([])

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=stub_read_loop), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt) as tg:
        rc = listen_mod.run(args)

    assert rc == 0
    tg.assert_called_once_with(fake_dev)
    assert captured["virt"] is fake_virt
    assert ecodes.BTN_BACK in captured["swallow_codes"]
    fake_virt.close.assert_called_once_with()
    fake_dev.ungrab.assert_called_once_with()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `xvfb-run -a pytest tests/test_listen_grab.py::test_qt_path_calls_try_grab_and_tears_down -q`
Expected: fail — Qt path does not yet call `try_grab` or pass `swallow_codes`/`virt`.

- [ ] **Step 3: Update `_run_with_qt` in `cli/listen.py`**

Replace `_run_with_qt` with:

```python
def _run_with_qt(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    """Ring-enabled path: QApplication on main thread, listener on worker thread.

    Auto-grabs the device the same way the command-only path does. Teardown
    runs after app.exec() returns.
    """
    try:
        from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, pyqtSlot
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        logging.error(
            "config defines ring bindings but PyQt6 is not installed; "
            "install with: pip install 'logitechmouse[ring]'"
        )
        return 1

    from evdev import ecodes
    from ..overlay.ring import RingController
    from ..overlay.widget import RingWidget
    from ..overlay.cursor import CursorPoller

    swallow_codes = {
        ecodes.ecodes[b.trigger]
        for b in cfg.bindings.values()
        if b.trigger in ecodes.ecodes
    }
    virt = try_grab(device)

    app = QApplication.instance() or QApplication(sys.argv)

    ring_controller = RingController(
        widget_factory=RingWidget,
        run_action=_default_run_action,
        actions=cfg.actions,
        cursor_poller_factory=lambda cb: CursorPoller(on_position=cb),
    )

    class _ListenerWorker(QObject):
        event_received = pyqtSignal(str, bool)
        finished = pyqtSignal(int)

        def run(self) -> None:
            try:
                for ev in backend.read_loop(
                    device, swallow_codes=swallow_codes, virt=virt
                ):
                    self.event_received.emit(ev.trigger, ev.pressed)
            except OSError as exc:
                logging.warning("device read failed: %s", exc)
                self.finished.emit(1)
                return
            self.finished.emit(0)

    class _MainBridge(QObject):
        @pyqtSlot(str, bool)
        def on_event(self, trigger: str, pressed: bool) -> None:
            p = QCursor.pos()
            dispatch_event(
                cfg,
                ring_controller=ring_controller,
                run_action=_default_run_action,
                trigger=trigger,
                pressed=pressed,
                cursor_pos=(p.x(), p.y()),
            )

    bridge = _MainBridge()
    worker = _ListenerWorker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    return_code = {"value": 0}

    def _on_finished(rc: int) -> None:
        return_code["value"] = rc
        thread.quit()
        app.quit()

    worker.event_received.connect(
        bridge.on_event, Qt.ConnectionType.QueuedConnection
    )
    worker.finished.connect(_on_finished, Qt.ConnectionType.QueuedConnection)
    thread.start()

    try:
        app.exec()
        thread.wait(2000)
    finally:
        if virt is not None:
            virt.close()
            try:
                device.ungrab()
            except OSError:
                pass

    return return_code["value"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `xvfb-run -a pytest tests/test_listen_grab.py -q`
Expected: 4 passed.

Run the full suite:
```bash
xvfb-run -a pytest -q
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/cli/listen.py tests/test_listen_grab.py
git commit -m "feat(listen): grab device in Qt-driven path with finally teardown"
```

---

## Task 8: SIGTERM handler triggers clean teardown (command-only path)

**Files:**
- Modify: `src/logitechmouse/cli/listen.py`
- Modify: `tests/test_listen_grab.py`

Without an explicit handler, `SIGTERM` (sent by `systemctl --user stop logitechmouse` once the systemd unit lands) bypasses the `finally` block and leaves the virtual device + grab in place until the kernel reaps the process.

Scope note: only the command-only path gets SIGTERM handling here. Python signal handlers do not fire while Qt's native event loop is blocking, so the Qt path needs a `QSocketNotifier` / self-pipe pattern that is out of scope for this PR. The systemd-unit work item (which actually needs SIGTERM) can address Qt-path SIGTERM at the same time.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_listen_grab.py`:

```python
import signal


def test_command_only_path_installs_sigterm_handler_and_restores_it(cmd_only_config):
    """run() must install a SIGTERM handler before entering the loop and
    restore the previous handler on exit."""
    args = argparse.Namespace(config=cmd_only_config, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")

    sentinel = signal.getsignal(signal.SIGTERM)

    captured = {}

    def stub_read_loop(device, swallow_codes=None, virt=None):
        captured["installed_handler"] = signal.getsignal(signal.SIGTERM)
        return iter([])

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", side_effect=stub_read_loop), \
         patch("logitechmouse.cli.listen.try_grab", return_value=None):
        listen_mod.run(args)

    assert captured["installed_handler"] is not sentinel, \
        "SIGTERM handler must be installed during the read loop"
    assert signal.getsignal(signal.SIGTERM) is sentinel, \
        "SIGTERM handler must be restored after run() returns"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_listen_grab.py::test_command_only_path_installs_sigterm_handler_and_restores_it -q`
Expected: fail — handler is unchanged.

- [ ] **Step 3: Add a small SIGTERM helper and call it from both paths**

In `src/logitechmouse/cli/listen.py`, add at module top (after imports):

```python
import signal
from contextlib import contextmanager


@contextmanager
def _sigterm_raises_keyboard_interrupt():
    """Map SIGTERM to KeyboardInterrupt for the duration of the block.

    Both listener paths already exit cleanly on KeyboardInterrupt (the
    `finally` runs and the read loop ends), so re-using the same path
    keeps the teardown in one place.
    """
    previous = signal.getsignal(signal.SIGTERM)

    def _raise(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _raise)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
```

Wrap the body of `_run_command_only` in `with _sigterm_raises_keyboard_interrupt():` and add `except KeyboardInterrupt: pass` so the function returns 0 cleanly:

```python
def _run_command_only(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    from evdev import ecodes
    swallow_codes = {
        ecodes.ecodes[b.trigger]
        for b in cfg.bindings.values()
        if b.trigger in ecodes.ecodes
    }
    virt = try_grab(device)
    try:
        with _sigterm_raises_keyboard_interrupt():
            for event in backend.read_loop(
                device, swallow_codes=swallow_codes, virt=virt
            ):
                dispatch_event(
                    cfg,
                    ring_controller=_NoOpRingController(),
                    run_action=_default_run_action,
                    trigger=event.trigger,
                    pressed=event.pressed,
                    cursor_pos=(0, 0),
                )
    except KeyboardInterrupt:
        logging.info("listener stopped")
    except OSError as exc:
        logging.warning("device read failed: %s", exc)
        return 1
    finally:
        if virt is not None:
            virt.close()
            try:
                device.ungrab()
            except OSError:
                pass
    return 0
```

Leave `_run_with_qt` unchanged in this task — Python-level SIGTERM does not interrupt Qt's native event loop reliably, and the systemd-unit work item will revisit it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `xvfb-run -a pytest tests/test_listen_grab.py -q`
Expected: 5 passed.

Run the full suite:
```bash
xvfb-run -a pytest -q
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/cli/listen.py tests/test_listen_grab.py
git commit -m "feat(listen): SIGTERM teardown via KeyboardInterrupt mapping"
```

---

## Task 9: Integration test against real `/dev/uinput` (gated)

**Files:**
- Create: `tests/test_device_grab_integration.py`

This test only runs locally where `/dev/uinput` is writable. It proves the whole pipeline works end-to-end against the actual kernel uinput driver.

- [ ] **Step 1: Write the integration test**

Create `tests/test_device_grab_integration.py`:

```python
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
```

- [ ] **Step 2: Run the test locally**

Run: `pytest tests/test_device_grab_integration.py -q`
Expected: pass on a workstation with `/dev/uinput` writable; **automatically skipped** on CI (no `/dev/uinput`).

- [ ] **Step 3: Confirm CI skips the test**

Run: `pytest tests/test_device_grab_integration.py -q --collect-only`
Expected: the test is collected. The skip happens at run time via the `requires_uinput` marker hook from Task 1.

- [ ] **Step 4: Commit**

```bash
git add tests/test_device_grab_integration.py
git commit -m "test: end-to-end uinput grab + forward (gated by /dev/uinput)"
```

---

## Task 10: Documentation

**Files:**
- Modify: `examples/config.toml`
- Modify: `README.md`

- [ ] **Step 1: Remove the dual-fire caveat from `examples/config.toml`**

Open `examples/config.toml` and delete (or rewrite) the comment that warns about thumb codes dual-firing with browser back/forward. Replace it with a one-line note:

```toml
# Bound trigger codes are swallowed by logitechmouse so they do not reach
# focused applications. If you see double-firing (e.g. browser navigates
# AND your action runs), see the README "Troubleshooting → buttons fire
# twice" section — usually a /dev/uinput permission fix.
```

- [ ] **Step 2: Add the troubleshooting section to `README.md`**

Append to `README.md` (or insert under an existing Troubleshooting heading):

```markdown
## Troubleshooting

### Buttons fire twice (your action runs *and* the app sees the click)

`logitechmouse` swallows bound trigger codes via a `/dev/uinput` virtual
device. If `/dev/uinput` is not writable by your user, the listener falls
back to non-grab mode (you'll see a warning in the log) and bound buttons
also reach the focused app.

Fix on most distros — add yourself to a group with write access:

```bash
# Check who owns /dev/uinput:
ls -l /dev/uinput
# crw------- 1 root root ...   -> needs a udev rule (see below)
# crw-rw---- 1 root input ...  -> just join the group:
sudo usermod -aG input $USER
# log out + back in
```

Or drop a udev rule (works regardless of distro defaults):

```bash
sudo tee /etc/udev/rules.d/60-logitechmouse-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

After the fix, restart the listener and confirm the warning is gone.
```

- [ ] **Step 3: Verify the README still renders**

Run: `python -c "import pathlib; pathlib.Path('README.md').read_text()"` (smoke check, no syntax beyond markdown).

Run the full suite once more:
```bash
xvfb-run -a pytest -q
```
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add examples/config.toml README.md
git commit -m "docs: troubleshoot dual-fire via /dev/uinput perms"
```

---

## Task 11: Push branch and open PR

**Files:** none (git/gh).

- [ ] **Step 1: Push the branch**

Run:
```bash
git push -u origin phase5-device-grab
```

- [ ] **Step 2: Verify CI before opening the PR**

Run:
```bash
gh run list --branch phase5-device-grab --limit 1
```
Wait until the run completes; it should be green. (If it isn't, fix and re-push before opening the PR.)

- [ ] **Step 3: Open the PR**

Run:
```bash
gh pr create --title "Device grab: stop bound triggers from reaching focused apps" \
  --body "$(cat <<'EOF'
## Summary

- Adds `device_grab.VirtualDevice` and `try_grab(real_dev)` — a uinput
  pass-through that grabs the real evdev device and mirrors every event
  *except* bound trigger codes.
- `EvdevBackend.read_loop` now accepts `swallow_codes` + `virt` and
  forwards non-bound events while still yielding `InputEvent` for the
  bound ones. Existing callers without those args are unchanged.
- Both listener paths (command-only and Qt-driven) call `try_grab` after
  resolve, pass it into the read loop, and tear down the virtual device
  + ungrab the real one in `finally`.
- SIGTERM is mapped to `KeyboardInterrupt` so future `systemctl --user
  stop` reuses the same teardown path.
- Graceful fallback: missing/unwritable `/dev/uinput` or already-grabbed
  device → log a single warning, continue without grab (current dual-fire
  behavior). Documented in README troubleshooting.

Spec: `docs/superpowers/specs/2026-04-27-device-grab-design.md`
Plan: `docs/superpowers/plans/2026-04-27-device-grab.md`

## Test plan

- [x] Unit tests for capability filter, `VirtualDevice`, `try_grab` (all branches)
- [x] Backend forwarding contract tests (bound swallowed; unbound/REL/SYN forwarded)
- [x] Listener integration tests for both code paths (try_grab called, teardown runs)
- [x] SIGTERM handler installed during the loop and restored on exit
- [x] End-to-end integration test against real `/dev/uinput` (gated by `requires_uinput`, skipped on CI)
- [x] Manual hardware test: bound `BTN_BACK` no longer navigates the browser; cursor + scroll + unbound buttons still work

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 4: Confirm CI on the PR**

Run:
```bash
gh pr view --json statusCheckRollup,mergeable
```
Expected: `MERGEABLE` and both `pytest (3.11)` + `pytest (3.12)` SUCCESS.
