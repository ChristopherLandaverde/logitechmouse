# Qt-path SIGTERM + systemd unit — Design Spec

**Date:** 2026-04-27
**Phase:** 6

---

## Problem

The command-only listen path handles SIGTERM cleanly via
`_sigterm_raises_keyboard_interrupt`. The Qt path (ring bindings) has no SIGTERM
handling: `app.exec()` blocks the main thread inside Qt's native event loop,
so Python signal handlers don't fire reliably. `systemctl stop` therefore
either hangs or hard-kills the process, leaving the grabbed device in a bad
state.

This phase fixes that and adds a `logitechmouse install-service` command so the
package works as a systemd user service out of the box.

---

## Architecture

### Qt-path SIGTERM fix

All changes are in `src/logitechmouse/cli/listen.py`, inside `_run_with_qt`,
before the `app.exec()` call.

**Setup (once, before `app.exec()`):**

1. Create a `socket.socketpair(AF_UNIX, SOCK_STREAM)` — a self-pipe pair. Set
   both ends non-blocking (required by `set_wakeup_fd`).
2. Call `signal.set_wakeup_fd(write_fd)` — Python writes a byte to `write_fd`
   whenever any signal arrives, regardless of which thread is running.
3. Install a no-op Python handler for SIGTERM:
   `signal.signal(SIGTERM, lambda s, f: None)`. This is required — `set_wakeup_fd`
   only fires for signals that have a Python-level handler installed (not `SIG_DFL`
   or `SIG_IGN`). The no-op prevents the OS from terminating the process before
   the event loop can respond.
4. Create `QSocketNotifier(read_fd, QSocketNotifier.Type.Read)` — Qt watches
   the read end on the main thread's event loop.
5. Connect `notifier.activated` to a slot that drains the read end and calls
   `app.quit()`.

**Shutdown sequence on SIGTERM:**

```
systemctl stop
  → SIGTERM delivered to process
  → no-op Python handler runs (process not killed)
  → Python writes byte to write_fd (set_wakeup_fd)
  → QSocketNotifier fires on main thread
  → slot drains read_fd, calls app.quit()
  → app.exec() returns
  → existing finally block: virt.close(), device.ungrab()
  → worker thread sees OSError from read_loop, emits finished
  → thread.wait(2000) joins worker
  → process exits 0
```

No new teardown code is needed — the existing `finally` block handles cleanup.
SIGINT (Ctrl+C) follows the same path since `set_wakeup_fd` catches all signals
that have a Python handler installed. Restore the previous SIGTERM handler after
`app.exec()` returns (in a `finally` block) so the context is clean.

The `_sigterm_raises_keyboard_interrupt` context manager on the command-only
path is **unchanged**.

**Failure mode:** If `set_wakeup_fd` fails (unusual environment, fd exhaustion),
log a warning and continue without the notifier. The process will respond to
SIGTERM via OS default (hard kill) — no worse than today.

---

### `install-service` command

New module: `src/logitechmouse/cli/install_service.py`
Registered as a subcommand in the existing CLI entry point.

```
logitechmouse install-service --config PATH [--force]
```

**Sequence:**

1. Resolve the `logitechmouse` binary via `shutil.which("logitechmouse")`,
   fallback to `sys.argv[0]`. Fail with exit 1 if neither resolves.
2. Resolve `--config PATH` to an absolute path. Fail with exit 1 if the file
   does not exist.
3. Render the unit file from a hardcoded template string (no external file).
4. Target path: `~/.config/systemd/user/logitechmouse.service`. Create
   intermediate directories if absent.
5. If the file already exists and `--force` is not set, exit 1 with a clear
   message.
6. Write the file.
7. Run `systemctl --user daemon-reload` via `subprocess.run`. On failure, warn
   only — do not exit 1 (systemd may not be running in all environments).
8. Print next-step instructions to stdout.

**Generated unit file template:**

```ini
[Unit]
Description=Logitech Mouse button remapper
After=graphical-session.target

[Service]
ExecStart={exec_start} listen --config {config_path}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

---

## Error handling

| Scenario | Behaviour |
|---|---|
| Config file not found | exit 1, no unit file written |
| Binary not resolvable | exit 1, advise checking PATH |
| Unit file exists, no `--force` | exit 1, tell user to use `--force` |
| Unit file dir not writable | surface `OSError` naturally |
| `daemon-reload` fails | warn, don't fail (file is written) |
| `set_wakeup_fd` fails | log warning, continue without notifier |
| Worker thread doesn't exit in 2s | existing `thread.wait(2000)` behaviour |

---

## Testing

### `install-service`

- Unit tests in `tests/test_install_service.py` using `tmp_path` fixture.
- Mock `shutil.which` and `subprocess.run`.
- Assert generated file content for happy path.
- Assert exit codes and messages for each error scenario.

### Qt SIGTERM

- Test in `tests/test_listen_qt_sigterm.py`.
- Spin up a minimal Qt app using the same `QSocketNotifier` setup, send
  `signal.SIGTERM` to `os.getpid()`, assert `app.exec()` returns and the
  teardown ran.
- Pattern mirrors the existing SIGTERM behavioural test in
  `tests/test_listen_grab.py`.

### End-to-end

- Optional test gated behind `requires_uinput` (same pattern as Phase 5):
  grab a real device, send SIGTERM to the Qt path, assert device is ungrabbed
  and virtual device is closed.

---

## Out of scope

- Wayland support (documented as a separate phase).
- App-specific profiles.
- `logitechmouse uninstall-service` command (can be added later; manual removal
  is one `rm` command).
- Packaging the unit file as a static asset (not viable due to dynamic
  `ExecStart` path).
