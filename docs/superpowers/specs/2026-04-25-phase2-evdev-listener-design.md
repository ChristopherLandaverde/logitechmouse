# Phase 2 MVP: evdev Listener Design

Date: 2026-04-25
Status: Approved (brainstorm), pending implementation plan

## 1. Scope

Turn the existing scaffold into a working tool: a long-running listener that
watches a real Logitech MX mouse, matches button-press events against TOML
bindings, and fires the corresponding action (e.g. screenshot).

Default examples target the **gesture button (`BTN_TASK`)** to avoid OS-default
conflicts with browser back/forward navigation. No device grabbing, no overlay,
no profiles — those are later phases.

This is the "First implementation target" from `AGENTS.md`: load config,
register bindings, invoke a screenshot from a mapped button, log unsupported
environments clearly.

## 2. Architecture

Existing module layout is preserved; we extend rather than rewrite.

| Module | Change |
|---|---|
| `device.py` | Replace stub `DeviceBackend` with `EvdevBackend`. Adds device discovery (auto + override), readability check with remediation message, blocking `read_loop()` generator. New: `list_candidates()` for the `devices` subcommand. |
| `config.py` | Add optional `[device]` section: `name` (substring match) and `path` (explicit `/dev/input/eventN`). Validate trigger codes at load time. |
| `actions.py` | Switch `subprocess.run(check=True)` → `subprocess.Popen` (fire-and-forget). Spawn failures (e.g. binary not found) are caught and logged. Exit codes of spawned processes are not observed in MVP. |
| `main.py` | Convert flat `argparse` to subcommands: `listen`, `devices`, `run <action>`, `check-config`. Add SIGINT/SIGTERM handler. Wire in `logging`. |
| `overlay.py` | Untouched. |
| `pyproject.toml` | Add `evdev>=1.6` runtime dependency; add `pytest` to dev extras. |
| `examples/config.toml` | Default trigger becomes `BTN_TASK`. Comment notes that `BTN_SIDE`/`BTN_EXTRA` will double-fire with browser back/forward. |

### Data flow (listen mode)

```
load_config
  → resolve_device (config override, then auto-discover)
  → check readability
      ↳ if PermissionError: print remediation, exit 1
  → for event in device.read_loop():
        if event.type == EV_KEY and event.value == 1:   # key-down only
            binding = bindings_by_trigger.get(event.code_name)
            if binding:
                action = actions[binding.action]
                run_action(action)        # Popen, non-blocking
```

Single-threaded blocking loop on the main thread. Subprocesses are launched
fire-and-forget so a slow action does not stall event reading meaningfully.

## 3. Config schema

Existing `[actions.*]` and `[bindings.*]` sections unchanged. Add an optional
top-level `[device]` section.

```toml
[device]
# Both optional. If absent, auto-discover the first device matching
# "Logitech" or "MX". `path` wins over `name` if both are set.
name = "MX Master"          # case-insensitive substring match on device name
path = "/dev/input/event7"  # explicit path; skips name matching

[actions.screenshot]
type = "command"
command = "gnome-screenshot -a"

[bindings.gesture_button]
trigger = "BTN_TASK"        # gesture button; no OS default action
action = "screenshot"
```

### Device resolution order

`EvdevBackend.resolve(config)`:

1. If `device.path` is set → open it directly. If unreadable/nonexistent → exit
   with remediation.
2. Else if `device.name` is set → scan `/dev/input/event*`, pick first whose
   `name` contains the substring (case-insensitive).
3. Else → scan, pick first whose name matches
   `/logitech|mx (master|anywhere|ergo|vertical)/i`.
4. If nothing matches → exit 1, suggest running `logitechmouse devices`.

### Trigger validation

At config-load time every binding's `trigger` is resolved through
`evdev.ecodes.ecodes`. Unknown codes (e.g. `BTN_FOO`) cause an immediate exit
with a clear error rather than silently never firing.

## 4. CLI

Subcommand-based:

| Subcommand | Purpose |
|---|---|
| `logitechmouse listen` | Resolve device, attach, run the event loop. Default mode. |
| `logitechmouse devices` | Print a table of detected input devices (path, name, vendor, product, readable). Print a remediation hint if any are unreadable. |
| `logitechmouse run <action>` | One-shot: execute a configured action by name. Honors `--dry-run`. (Replaces the existing `--run-action` flag.) |
| `logitechmouse check-config` | Parse config and validate every binding references a defined action and a known trigger code. Exit 0 / 1. |

Global flags: `--config PATH`, `--dry-run` (applies where meaningful).

### Behavior decisions

- Fire on **key-down only** (evdev `value == 1`); ignore key-up and autorepeat.
- **SIGINT / SIGTERM** close the device and exit 0.

## 5. `devices` output

```
PATH                  NAME                              VENDOR  PRODUCT  READABLE
/dev/input/event5     Logitech MX Master 3S             046d    4082     yes
/dev/input/event6     Logitech USB Receiver Consumer    046d    c548     yes
/dev/input/event7     AT Translated Set 2 keyboard      0000    0000     no

Some devices unreadable. Add yourself to the `input` group:
  sudo usermod -aG input $USER
Then log out and back in.
```

The remediation footer is only printed when at least one device returned
PermissionError.

## 6. Logging

Stdlib `logging` module. Format: `%(asctime)s %(levelname)s %(message)s`.
Default level INFO. Output to stdout. No file logging in MVP — users can
redirect themselves or run under systemd.

Examples:

```
2026-04-25 14:02:11 INFO  listening on /dev/input/event5 (Logitech MX Master 3S)
2026-04-25 14:02:11 INFO  bindings: gesture_button[BTN_TASK]→screenshot
2026-04-25 14:02:18 INFO  fired: screenshot (gnome-screenshot -a)
2026-04-25 14:03:02 WARN  action 'screenshot' failed to spawn: [Errno 2] No such file or directory: 'gnome-screenshot'
```

## 7. Error handling

Startup errors are fatal; runtime errors are logged and the loop continues.

| Condition | Behavior |
|---|---|
| Config file missing or malformed | exit 1, print parser error with file:line |
| Binding references undefined action | exit 1 at startup |
| Unknown trigger code | exit 1 at startup |
| Device not found | exit 1, suggest `logitechmouse devices` |
| Device unreadable (PermissionError) | exit 1, print `usermod -aG input` remediation |
| Device disconnected mid-run (`OSError`) | log WARN, exit 1 (let systemd / user restart) |
| Action subprocess fails to spawn (e.g. binary not found) | log WARN, keep listening |
| Action subprocess exits non-zero after spawn | not observed in MVP (fire-and-forget) |
| SIGINT / SIGTERM | log INFO, close device, exit 0 |

## 8. Testing

Minimal but real. No live-hardware tests in CI.

- `tests/test_config.py` — valid TOML, malformed TOML, missing action
  reference, unknown trigger code, optional `[device]` parsing.
- `tests/test_actions.py` — `run_action` with dry-run, with `/bin/true` and
  `/bin/false`, with missing command. Use real subprocess (no mocking).
- `tests/test_device_resolve.py` — `EvdevBackend.resolve()` parametrized:
  explicit path, name match, auto-match, no match. Mock only the
  `evdev.InputDevice` factory.
- **Manual smoke test** for `listen`: run `logitechmouse listen`, press the
  gesture button on a real MX mouse, verify the screenshot fires.

Add `pytest` to `[project.optional-dependencies].dev`.

## 9. Dependencies

Add to `pyproject.toml`:

- Runtime: `evdev>=1.6`
- Dev: `pytest>=7`

## 10. Non-goals (explicit, deferred)

- Device grabbing / `uinput` passthrough (Phase 2.5 if a user needs to override
  a conflicting button)
- Key-chord action type (Phase 3)
- App-aware profile switching (Phase 3)
- Config hot-reload
- Radial overlay (Phase 4)
- udev rule installer (Phase 2.5+)
- Multi-device support (single device only in MVP)
- Wayland-specific overlay concerns (no overlay yet)

## 11. Success criteria

- A user with an MX mouse, no prior setup beyond `pip install` and joining the
  `input` group, can write a 6-line config, run `logitechmouse listen`, press
  the gesture button, and get a screenshot.
- `logitechmouse devices` shows their mouse with `READABLE=yes`.
- `logitechmouse check-config` validates configs offline.
- All three unit test files pass.
