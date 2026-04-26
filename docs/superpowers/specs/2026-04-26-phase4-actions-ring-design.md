# Phase 4 Design: Actions Ring

**Status:** Draft (brainstorm complete, awaiting user spec review before plan).
**Date:** 2026-04-26.
**Branch (target for impl):** `phase4-ring-prototype` (not yet created).
**Predecessor:** [Phase 2 evdev listener](./2026-04-25-phase2-evdev-listener-design.md), shipped via PR #2 (`4cdfc43`).

---

## 1. Goal

Ship the radial Actions Ring overlay — the product differentiator that justifies
this project existing. Pressing and holding a configured mouse button opens a
transparent radial overlay centered on the cursor. Releasing the button while the
cursor is over a wedge fires that wedge's action. Releasing in the center cancels.

The ring must feel as natural as Logitech Options' Actions Ring. That is the
quality bar. If the gesture feels laggy, jarring, or stale, we have failed.

## 2. Non-goals (Phase 4)

These are deliberately out of scope; revisit only if v1 surfaces a hard dependency.

- **Wayland support.** X11-only in v1. Wayland needs `wlr-layer-shell` + relative-pointer
  protocol and is broken on stock GNOME. Separate phase later.
- **Per-app ring profiles.** Phase 3 territory.
- **New action types** (`keychord`, `launch`, etc.). Phase 3. Ring segments fire whatever
  action types exist; when Phase 3 adds new kinds, segments pick them up automatically.
- **Theming config.** Defaults only in v1. We add `[theme]` knobs after we've used the
  ring for a week and know which knobs matter.
- **Nested rings.** A segment that opens another ring. Tempting, defer until we have
  evidence anyone wants it.
- **Icon rendering.** Schema accepts `icon = "<name>"` per segment so configs do not
  need to migrate later, but v1 renders labels only. Icon rendering is a polish pass.

## 3. User-facing behavior

### 3.1 Trigger model

Hold-to-show, release-to-fire.

1. User presses a button bound to `target = "ring:NAME"`.
2. On key-down (`evdev` value = 1), the overlay opens at the current cursor position.
3. While held, the overlay polls the cursor position at ~120 Hz. The wedge containing
   the cursor's angle from ring-center is highlighted.
4. On key-up (`evdev` value = 0):
   - If the cursor is outside the dead zone, fire the highlighted wedge's action.
   - If the cursor is inside the dead zone, cancel (no action fires).
   - Either way, the overlay closes.

### 3.2 Geometry and selection

- Each ring has N segments, where `3 <= N <= 12`. Default in `examples/config.toml` is 8.
- Wedge angle = `360 / N`. Wedge 0 starts at the 12 o'clock position and proceeds clockwise.
- Active wedge for cursor `(cx, cy)` and ring center `(rx, ry)`:
  - `dx = cx - rx`, `dy = cy - ry`
  - `r = hypot(dx, dy)`
  - If `r < dead_zone_radius`, no wedge is active (cancel state).
  - Else: `angle = atan2(dy, dx)` normalized to `[0, 360)` with 0 at 12 o'clock,
    increasing clockwise. `wedge_index = floor((angle + (360/N)/2) % 360 / (360/N))`.

### 3.3 Visual defaults (v1)

- Translucent dark background, `rgba(24, 24, 24, 0.85)`.
- Outer ring radius: 180 px. Dead-zone radius: 45 px (25% of outer).
- Each wedge: pie slice with 1 px separator from neighbors.
- Label centered along wedge bisector at ~70% of outer radius. Sans-serif, 14 px.
- Active wedge: brighter background (`rgba(56, 56, 56, 0.92)`), label boldens, slight
  scale (1.05x).
- Dead-zone center pip: shows literal text "Cancel" when cursor is inside.
- Open animation: 75 ms fade-in + scale 0.85 → 1.0. No close animation in v1.
- Cursor stays visible at all times.

### 3.4 Spawn behavior at screen edges

- Ring opens at cursor position by default.
- If the cursor is close enough to a screen edge that the full outer-radius circle
  would clip off-screen, the ring's geometric center shifts inward to fit fully on the
  monitor containing the cursor. The cursor is **not** warped.
- Hit-testing always uses the cursor's angle relative to the ring's actual (possibly
  shifted) center, not the cursor's own position.

### 3.5 Multi-ring

- Multiple `[rings.X]` tables allowed. Different buttons may bind to different rings.

## 4. Configuration schema

### 4.1 New schema

```toml
[device]
name = "Logitech USB Receiver Mouse"

[actions.screenshot_area]
type    = "command"
command = "gnome-screenshot -a"

[actions.screenshot_full]
type    = "command"
command = "gnome-screenshot"

[actions.lock]
type    = "command"
command = "loginctl lock-session"

[rings.thumb_ring]
# 3 <= len(segments) <= 12. Order is clockwise starting from 12 o'clock.
segments = [
  { action = "screenshot_area",  label = "Area" },
  { action = "screenshot_full",  label = "Full" },
  { action = "lock",             label = "Lock" },
  # icon = "<freedesktop-name>" is accepted on each segment but not rendered in v1.
]

[bindings.thumb_button]
trigger = "BTN_TASK"
target  = "ring:thumb_ring"

[bindings.side_button]
trigger = "BTN_SIDE"
target  = "action:screenshot_area"
```

### 4.2 Backward compatibility

Phase 2 configs use `action = "<name>"` on bindings. Loader keeps this working:

- If a `[bindings.X]` table has `action = "..."`, treat it as `target = "action:..."`.
- If it has `target = "..."`, parse the prefix.
- Either form is valid. New documentation uses `target`. No user has to edit configs.
- Loader emits a `DeprecationWarning` (logged at INFO level, not raised) when the legacy
  `action = "..."` form is used, with a one-line migration tip. We never plan to remove
  the legacy form, but the nudge documents the modern form for users reading logs.

### 4.3 Validation rules

Validation runs **after** the loader has translated any legacy `action = "..."` form
into the modern `target = "action:..."` form. By the time these rules are applied,
every binding has a `target`.

In addition to existing Phase 2 rules:

- Every binding's `target` must parse as `<kind>:<name>` with `kind ∈ {action, ring}`.
- For `target = "action:X"`, `X` must exist in `[actions.*]`.
- For `target = "ring:Y"`, `Y` must exist in `[rings.*]`.
- Every `[rings.Y]` table:
  - `segments` must have length `>= 3` and `<= 12`.
  - Every segment's `action` must exist in `[actions.*]`.
  - `label` is required and must be non-empty after `.strip()`.
  - `icon`, if present, must be a non-empty string. Not validated against a theme — Qt
    handles missing icons at render time.
- Validation errors raise `ConfigError` with a path-style message identifying the offender
  (e.g. `rings.thumb_ring.segments[2].action 'foo' not found`).

### 4.4 Internal types

The schema introduces these dataclasses in `config.py`:

```python
@dataclass(frozen=True)
class Target:
    kind: str   # "action" or "ring"
    name: str

@dataclass
class Segment:
    action: str           # references actions[name]
    label: str
    icon: str | None = None  # accepted but not rendered in v1

@dataclass
class Ring:
    name: str
    segments: list[Segment]
```

`Binding.action` (str) is replaced by `Binding.target` (Target). `AppConfig` gains
`rings: dict[str, Ring]`.

## 5. Architecture

### 5.1 Module layout

```
src/logitechmouse/
├── config.py        # extended: Ring, Segment dataclasses; target parsing
├── device.py        # extended: read_loop emits both key-down and key-up
├── actions.py       # unchanged in Phase 4
├── overlay/
│   ├── __init__.py
│   ├── ring.py      # RingController: state machine, lifetime, dispatch
│   ├── widget.py    # PyQt6 QWidget: paintEvent, geometry, animation
│   ├── geometry.py  # pure functions: angle math, hit-test, edge-shift
│   └── cursor.py    # XQueryPointer wrapper, polling timer
└── cli/
    └── listen.py    # extended: routes ring targets to RingController
```

`overlay/geometry.py` is pure (no Qt imports). All angle/hit-test/edge-shift logic lives
there so it is testable in isolation without spinning up a `QApplication`.

### 5.2 Data flow

```
evdev key-down ──► listener ──► dispatch by target kind
                                     │
                       ┌─────────────┴───────────┐
                       │                         │
              target = "action:X"       target = "ring:Y"
                       │                         │
              run_action(actions[X])   ring_controller.open(rings[Y], cursor_pos)
                                                 │
                                       (poll cursor at ~120 Hz, redraw active wedge)
                                                 │
                                       evdev key-up ──► ring_controller.close()
                                                          │
                                                          ├─ in dead zone → no action
                                                          └─ over wedge i  → run_action(rings[Y].segments[i].action)
```

### 5.3 `device.read_loop` change

Today (`device.py:187-204`) skips events with `value != 1`. Phase 4 must emit both
key-down and key-up. The signature changes:

```python
@dataclass
class InputEvent:
    trigger: str        # evdev key code name, e.g. "BTN_TASK"
    pressed: bool       # True for key-down, False for key-up

def read_loop(self, device: InputDevice) -> Iterator[InputEvent]:
    for event in device.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        if event.value not in (0, 1):  # ignore key-repeat (value=2)
            continue
        # ... existing keycode resolution ...
        yield InputEvent(trigger=name, pressed=(event.value == 1))
```

Phase 2 callers of `read_loop` consumed `InputEvent.trigger` only. They now must filter
on `event.pressed`. Phase 2 listener becomes a one-line filter
(`if not event.pressed: continue`) before its existing trigger-match logic. Tests for
the Phase 2 listener get parameterized over `pressed=True/False` to confirm the filter.

### 5.4 `RingController` state machine

```
       ┌──────────┐
       │   IDLE   │
       └────┬─────┘
            │ open(ring, cursor_pos)
            ▼
       ┌──────────┐
       │  OPEN    │  ◄─── poll cursor, redraw active wedge
       └────┬─────┘
            │ close()
            ▼
   in dead zone? ──yes──► IDLE (no fire)
            │
            no
            ▼
   run_action(active wedge action) ──► IDLE
```

Re-entrancy: if `open()` is called while already `OPEN` (e.g. user presses the ring
button again before releasing the first), the second call is ignored. We log at DEBUG
level but do not crash.

Action dispatch on close uses the existing `run_action` from `actions.py`. Reused, not
duplicated.

### 5.5 Cursor polling

`overlay/cursor.py` wraps `python-xlib`'s `XQueryPointer` (or Qt's `QCursor.pos()`,
which on X11 internally calls the same thing — TBD in implementation, prefer
`QCursor.pos()` if it works for hit-testing latency). A `QTimer` at 8 ms interval
(~120 Hz) drives the redraw.

If the cursor has not moved since the last tick, skip the redraw. Wedge highlight
recompute is cheap but `QWidget.update()` is not free.

### 5.6 Listener integration

`cli/listen.py` currently dispatches `binding.action` directly to `run_action`. The
extension (this loop runs in the worker thread; see §5.7 for how events cross to
the main thread):

```python
for event in backend.read_loop(device):  # runs on listener worker thread
    binding = bindings_by_trigger.get(event.trigger)
    if binding is None:
        continue
    target = binding.target  # Target(kind, name)

    if target.kind == "action" and event.pressed:
        emit_to_main_thread(("action", target.name))
    elif target.kind == "ring":
        emit_to_main_thread(("ring_open" if event.pressed else "ring_close", target.name))
```

A slot on the Qt main thread receives these tuples and dispatches:

```python
def on_listener_event(kind, name):  # main thread
    if kind == "action":
        run_action(cfg.actions[name])
    elif kind == "ring_open":
        ring_controller.open(cfg.rings[name])
    elif kind == "ring_close":
        ring_controller.close()
```

`ring_controller` is created once at listener startup and lives for the listener's
lifetime. It owns the `QWidget` and the cursor-polling `QTimer`. The `QApplication`
is owned by `cli/listen.py`'s entry point.

### 5.7 Process model

The listener and the Qt app run in the same process. `QApplication.exec()` does NOT
block the listener — instead, the listener's `read_loop` runs in a background thread
and posts events to the Qt main thread via `QMetaObject.invokeMethod` (or a
`QueuedConnection` signal). The Qt main thread owns all widget operations.

Concretely: at startup, `cli/listen.py` creates `QApplication(sys.argv)`, hands the
listener loop to a `QThread`, and calls `app.exec()`. The listener thread emits a
signal on each evdev event; a slot on the main thread routes it to `ring_controller`
or `run_action`.

This keeps Qt happy (all GUI work on main thread) and `read_loop`'s blocking nature
out of the way of redraw.

### 5.8 Performance budget

- Ring open latency (key-down → first frame visible): **target < 50 ms** on the dev
  machine. If we miss this, the gesture feels laggy. Measure during manual test.
- Cursor poll interval: 8 ms (~120 Hz). Redraw skipped if cursor unchanged.
- Wedge highlight recompute: pure function, target < 0.1 ms.

## 6. Error handling

- **Display unavailable** (`DISPLAY` unset or X server unreachable): on listener
  startup, attempt `QApplication(sys.argv)` inside a try/except. On failure, log a clear
  error and exit non-zero with a message pointing at headless / Wayland environments.
- **No rings configured but bindings target rings**: caught at config validation; we
  never reach runtime in this state.
- **`run_action` failure inside ring dispatch**: same as Phase 2 — log at WARNING,
  ring closes normally, listener stays alive.
- **Cursor poll race** (cursor moved while we were drawing): no special handling. Next
  poll tick picks up the new position. Worst case a 1-frame stale highlight, sub-10 ms.
- **Re-entrant open**: see §5.4. Ignored, DEBUG log.
- **Multi-monitor cursor moves between monitors mid-hold**: ring stays anchored to its
  original monitor and original spawn center. Cursor angle is still computed against
  that center. If the user drags onto a different monitor, the ring may end up partly
  off-visible-area on the original monitor; this is acceptable for v1.

## 7. Testing strategy

Mirroring the Phase 2 TDD discipline.

### 7.1 Pure-function tests (no Qt, no evdev)

`tests/test_geometry.py`:
- Wedge index for `(angle, N)` over `N ∈ {3, 4, 6, 8, 12}` and `angle ∈ {0, 45, 90, ...}`.
- Edge-shift function: given `(cursor, screen_rect, ring_radius)`, returns ring center
  fully on-screen, never warping cursor.
- Dead-zone hit-test: `(distance < dead_zone_radius)` returns "no wedge."

`tests/test_config_ring.py`:
- Parse `target = "ring:X"` and `target = "action:Y"` correctly.
- Parse legacy `action = "X"` form into `target = "action:X"`. Confirm DeprecationWarning
  is logged.
- Validation errors: missing target ring, segment with unknown action, segments < 3,
  segments > 12, missing label.

### 7.2 Listener integration tests (mocked Qt + mocked backend)

`tests/test_listen_cli.py` (extended):
- Mock `EvdevBackend.read_loop` with a fixed sequence of `InputEvent(pressed=True/False)`.
- Mock `RingController.open` / `.close` / `run_action`.
- Confirm: action target on key-down fires `run_action`; action target on key-up does
  not re-fire. Ring target on key-down calls `controller.open`; on key-up calls
  `controller.close`.

### 7.3 Qt widget tests

`tests/test_overlay_widget.py`:
- Use `pytest-qt` (new dev dep) or `QApplication` fixture.
- Smoke test: `RingWidget(ring=test_ring).show()` does not raise; `paintEvent` runs
  without exception.
- Hit-test integration: programmatically set cursor position, trigger a poll tick,
  assert the active wedge index matches expectation.

Skipped on CI if no display: tests are marked `@pytest.mark.requires_display` and
the GitHub Actions matrix wraps them in `xvfb-run`. Locally on dev machines they
just run.

### 7.4 Manual hardware test

Once the listener integration passes, run on the user's actual MX hardware. The
mouse subnode path shifts across sessions (USB renumbering); resolve it via the
existing auto-discovery or `--device $(logitechmouse devices | grep -i 'logitech.*mouse' | awk ...)`.
The durable identity is the device name "Logitech USB Receiver Mouse," not a fixed
`/dev/input/event*` path.

Bind `BTN_TASK` to a 4-segment ring with one wedge per gnome-screenshot variant.
Verify:
- Hold + release outside dead zone fires the right action.
- Hold + release in center cancels.
- Hold + release exactly on a separator doesn't crash (deterministic behavior either
  side of the boundary is fine, but it must not crash or fire two actions).
- Multi-monitor: open the ring near a monitor edge; ring shifts inward, gesture works.

## 8. Dependencies

New runtime deps:
- `PyQt6 ~= 6.6` (~50 MB install).
- `python-xlib ~= 0.33` (only if we go that route for cursor; `QCursor.pos()` may suffice).

New dev deps:
- `pytest-qt ~= 4.4`.

`pyproject.toml` gets `[project.optional-dependencies]` entry `ring = ["PyQt6"]`. Users
who only want command-bindings (Phase 2 functionality) do not pay the PyQt6 install
cost — `pip install logitechmouse` stays light; `pip install logitechmouse[ring]`
adds the overlay.

The CLI gracefully degrades: if a config defines a ring binding but PyQt6 is not
importable, validation fails at startup with a clear message ("install
`logitechmouse[ring]` to use ring bindings").

## 9. Migration and rollout

- Implementation lands on a `phase4-ring-prototype` branch, not `main`.
- TDD per-cycle commits, same format as Phase 2.
- PR includes updated `examples/config.toml` with one ring example, updated README
  Usage section, updated `docs/PRD.md` to mark ring goal as shipped.
- After merge, manual hardware test on `main` before declaring done.

## 10. Open issues / decisions deferred to spec review

- Whether to use `QCursor.pos()` or raw `python-xlib.XQueryPointer` for cursor polling.
  Decide during implementation; both are tested behind `overlay/cursor.py`.
- Exact dead-zone radius (currently 25%). May tune after first manual test.
- Whether to add Esc-key cancel as a global shortcut while ring is open. Probably yes,
  but it requires a separate keyboard listener; defer to v1.1 unless it falls out of
  the implementation for free.

---

## Appendix: visual reference

```
     12 o'clock
       seg 0
   seg 7 ┌──┐ seg 1
        │ ●│         ● = ring center; release here = cancel
seg 6 ──┤  ├── seg 2     dashed = dead zone (25% radius)
        │  │
   seg 5 └──┘ seg 3
       seg 4
       6 o'clock
```

Wedges go clockwise from 12 o'clock. N=8 shown.
