# Device Grab — Stop Bound Triggers From Reaching Other Apps

## Problem

Phase 4 ships the radial Actions Ring overlay, but the listener does not grab the underlying evdev device. Every bound trigger event (e.g. `BTN_BACK`, `BTN_FORWARD`) is dispatched by `logitechmouse` *and* delivered to whatever application has focus. In a browser this means pressing the thumb buttons fires the configured action *and* navigates back/forward. The PR caveat documented the issue and accepted it for v1; this spec resolves it.

## Goal

When a button is bound to a `logitechmouse` action or ring, the focused application must not see that button event. Unbound buttons, cursor motion, scroll wheel, and every other event from the same evdev node must continue to reach the system normally.

## Non-goals

- Daemonization / background autostart. Tracked separately as the systemd-unit work item.
- Wayland support. The grab approach below is platform-agnostic at the evdev layer; X11 vs Wayland concerns live above the listener.
- New binding semantics (e.g. "fire action *and* pass through"). YAGNI for v1.

## Strategy: uinput pass-through

`evdev`'s `device.grab()` claims exclusive access to a node. Because the Logitech receiver's mouse subnode (`event25` on the dev hardware) emits both `EV_REL` motion *and* `EV_KEY` button events on the same fd, a naive grab would freeze the cursor system-wide.

The standard fix — used by `xremap`, `evsieve`, `interception-tools`, and similar — is:

1. Open the real device.
2. Create a virtual device via `/dev/uinput` that mirrors the real device's capabilities.
3. Grab the real device.
4. In the read loop, forward every event to the virtual device **except** the `EV_KEY` events that match a bound trigger code, which are consumed by `dispatch_event`.

The virtual device is what the rest of the system (X server, Wayland compositor, focused apps) sees as the mouse. Motion, scroll, and unbound buttons pass through transparently. Bound triggers are swallowed.

## Activation policy

Auto-grab with graceful fallback:

- On listener start, attempt grab + uinput creation.
- Success → forward path is active; bound triggers are swallowed.
- Failure (`/dev/uinput` missing, perms denied, device already grabbed) → log a single warning that names the failure mode, points at docs for the `/dev/uinput` udev/group fix, and continues without grab. Bound actions still fire; dual-fire returns until the user fixes perms.

Rationale: most users on a fresh install already have read access to `/dev/input/*` because they joined the `input` group during the Phase 2 setup. `/dev/uinput` often needs an extra step (a udev rule or `uinput` group on some distros). Hard-failing on uinput would regress every user who is currently using ring bindings happily; warning + falling back keeps the existing behavior as the floor.

## Components

New module: `src/logitechmouse/device_grab.py`.

### `VirtualDevice`

Thin wrapper around `evdev.UInput`. Constructed from the real `InputDevice`'s capability map (filtered to drop `EV_SYN` — `UInput` reserves it). Sets the virtual device name to `"logitechmouse virtual"` so users can identify it in `evtest` / `xinput`. Implements `__enter__` / `__exit__` (`close()` on exit) and a `write_event(event)` method that calls the underlying `UInput.write(type, code, value)` and `syn()` after non-`EV_SYN` events.

### `try_grab(real_dev) -> VirtualDevice | None`

1. Build capability dict from `real_dev.capabilities(verbose=False)`.
2. Construct `VirtualDevice(caps, name=...)`. On `FileNotFoundError` (`/dev/uinput` missing) or `PermissionError`, log warn + return `None`.
3. Call `real_dev.grab()`. On `OSError` (already grabbed), close the virtual device and return `None`.
4. Return the `VirtualDevice`.

### `forward(virt, event, swallow_codes: set[int]) -> bool`

Returns `True` if the event was forwarded, `False` if swallowed. The caller uses the return value purely for logging; control flow does not branch on it.

Rule: swallow when `event.type == EV_KEY` and `event.code in swallow_codes`. Forward everything else (`EV_REL`, `EV_ABS`, `EV_MSC`, `EV_SYN`, unbound `EV_KEY`).

## Listener integration

`cli/listen.py` changes in both the command-only and Qt-driven paths:

```
device = backend.resolve(...)
swallow_codes = {ecodes.ecodes[t] for t in triggers if t in ecodes.ecodes}
virt = try_grab(device)  # or None
try:
    for raw in device.read_loop():
        if virt is not None and not (raw.type == EV_KEY and raw.code in swallow_codes):
            virt.write_event(raw)
        # existing dispatch path: convert to InputEvent and dispatch
        # only fires for bound trigger codes
finally:
    if virt is not None:
        virt.close()
        try: device.ungrab()
        except OSError: pass
```

Two practical wrinkles:

1. The current `EvdevBackend.read_loop` filters to `EV_KEY` and yields `InputEvent`. Forwarding needs the *raw* event stream too. Refactor: `read_loop` yields a small dataclass that carries both the raw evdev event and the parsed `InputEvent | None`, or expose two iterators. The lower-friction option is to push the forwarding *into* the backend so the listener's contract stays (trigger, pressed) tuples; the backend takes a `swallow_codes` set and an optional `VirtualDevice` and handles forwarding internally. This spec adopts that shape.
2. Signal handling: a `signal.signal(SIGTERM, ...)` handler in `listen.run` that triggers a clean teardown. The `finally` block already covers normal exit and `KeyboardInterrupt`; SIGTERM (e.g. when a future systemd unit stops the service) needs explicit handling so the virtual device is destroyed and the real device is ungrabbed.

## Hold-to-open ring interaction

The ring's open/close cycle is press → hold → release. Both edges are bound-trigger events and must be swallowed. The current dispatch already handles both; nothing changes about the ring's behavior. Key-repeat (`value=2`) on a held bound trigger is dropped at the backend layer (already true) and is *not* forwarded to the virtual device.

## Edge cases

- **uinput perms missing.** Warn once, continue without grab. Document `/dev/uinput` udev rule in README under "Troubleshooting → buttons fire twice".
- **Device hot-unplug while grabbed.** `device.read_loop` raises `OSError`; the `finally` block runs; the virtual device is destroyed cleanly. The listener exits with a non-zero status (matches today's behavior).
- **Crash mid-loop.** `finally` covers it. Worst case, if the process is `kill -9`'d, the virtual device persists until the kernel reaps it (seconds). Acceptable.
- **Two `logitechmouse` instances on the same device.** Second instance's grab fails with `OSError`, `try_grab` returns `None`, second instance runs without grab and dual-fires. This is fine: running two listeners is user error; the warning makes it diagnosable.

## Tests

### Unit (no `/dev/uinput` required)

`tests/test_device_grab.py`:

- `try_grab` happy path: monkeypatched `UInput` constructor + `real_dev.grab()` succeed → returns `VirtualDevice`, `grab` was called.
- `try_grab` no uinput: `UInput` raises `FileNotFoundError` → returns `None`, `grab` *not* called.
- `try_grab` perm denied: `UInput` raises `PermissionError` → returns `None`.
- `try_grab` already grabbed: `real_dev.grab()` raises `OSError` → returns `None`, virtual device was closed.
- `forward` swallows bound `EV_KEY`, forwards unbound `EV_KEY`, forwards `EV_REL`, forwards `EV_SYN`.
- `VirtualDevice.__exit__` calls underlying `close`.

### Integration (gated by `/dev/uinput` availability)

`tests/test_device_grab_integration.py`, marked `@pytest.mark.requires_uinput`:

- Create a uinput device, write a known sequence of synthetic events, assert that a separate reader sees the correct subset (unbound forwarded, bound swallowed).
- Skipped on CI runners that don't expose `/dev/uinput`. The marker is collected via `conftest.py` similar to the existing `requires_display` marker.

### Listener-level

`tests/test_listen_grab.py`:

- Listener calls `try_grab` once after `resolve`.
- When `try_grab` returns `None`, listener still dispatches bound triggers correctly (regression check on the fallback path).
- When `try_grab` returns a fake `VirtualDevice`, raw events flowing through the read loop are forwarded except bound codes.

## Documentation

- README "Setup" gains a uinput section. Two paths: (a) add user to `input` group (works on most distros where `/dev/uinput` is `crw-rw---- root:input`), or (b) drop a udev rule under `/etc/udev/rules.d/`.
- README "Troubleshooting" gets the dual-fire entry pointing at the same setup section.
- The PR caveat in `examples/config.toml` about dual-fire is removed.

## Out of scope (followups)

- Wayland-native global hotkeys (replacing evdev grab on Wayland would mean talking to each compositor's portal).
- A `passthrough = true` per-binding override that fires the action *and* forwards the event (hold for real demand).
- A status command that reports whether the running listener has grab active.

## Acceptance

- Pressing `BTN_BACK` (or any bound thumb code) in a focused browser fires the configured action and does *not* navigate.
- Cursor motion and scroll wheel work normally throughout.
- Removing `/dev/uinput` (or denying perms) downgrades to the current dual-fire behavior with a clear warning, no crash.
- All new tests pass; existing tests continue to pass.
