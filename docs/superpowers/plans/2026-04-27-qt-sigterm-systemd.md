# Qt-path SIGTERM + systemd unit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix SIGTERM handling on the Qt listen path using `set_wakeup_fd` + `QSocketNotifier`, and add a `logitechmouse install-service` command that writes a systemd user unit file.

**Architecture:** Before `app.exec()`, a `socketpair` + `signal.set_wakeup_fd` wires all Python-handled signals to a `QSocketNotifier` on the main thread; the notifier slot calls `app.quit()`, causing `app.exec()` to return and the existing `finally` teardown block to run. The `install-service` command resolves the installed binary path, renders a unit file template, writes it to `~/.config/systemd/user/`, and runs `systemctl --user daemon-reload`.

**Tech Stack:** Python 3.11+, PyQt6 ~= 6.6, evdev, pytest, pytest-qt

---

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/logitechmouse/cli/listen.py` | Modify | Add socketpair + `set_wakeup_fd` + `QSocketNotifier` before `app.exec()` in `_run_with_qt`; add `import socket` |
| `src/logitechmouse/cli/install_service.py` | Create | `run(args)` — resolve binary, render template, write unit file, reload systemd |
| `src/logitechmouse/main.py` | Modify | Add `install-service` subparser (`--config` required, `--force` optional) and dispatch |
| `tests/test_listen_qt_sigterm.py` | Create | Unit + integration tests for the SIGTERM mechanism and `_run_with_qt` signal setup |
| `tests/test_install_service.py` | Create | Tests for all `install-service` paths (happy, errors, force) |

---

## Task 1: Qt mechanism unit tests

**Files:**
- Create: `tests/test_listen_qt_sigterm.py`

- [ ] **Step 1: Write the two mechanism tests**

```python
# tests/test_listen_qt_sigterm.py
from __future__ import annotations

import os
import signal
import socket
import sys

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QSocketNotifier, QTimer
from PyQt6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def test_socket_notifier_fires_when_written_to():
    """Writing to the write end of a socketpair causes QSocketNotifier to fire
    and call app.quit(); app.exec() returns."""
    app = _app()
    r, w = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    r.setblocking(False)
    w.setblocking(False)

    fired = []
    notifier = QSocketNotifier(r.fileno(), QSocketNotifier.Type.Read)

    def _slot():
        try:
            r.recv(256)
        except OSError:
            pass
        fired.append(True)
        app.quit()

    notifier.activated.connect(_slot)
    QTimer.singleShot(50, lambda: w.send(b"\x00"))
    app.exec()

    notifier.setEnabled(False)
    r.close()
    w.close()

    assert fired, "QSocketNotifier slot was not called"


def test_sigterm_via_set_wakeup_fd_triggers_notifier():
    """SIGTERM delivered to this process writes a byte via set_wakeup_fd,
    which fires the QSocketNotifier and causes app.exec() to return."""
    app = _app()
    r, w = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    r.setblocking(False)
    w.setblocking(False)

    prev_fd = signal.set_wakeup_fd(w.fileno())
    prev_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda s, f: None)  # no-op; must be non-SIG_DFL

    fired = []
    notifier = QSocketNotifier(r.fileno(), QSocketNotifier.Type.Read)

    def _slot():
        try:
            r.recv(256)
        except OSError:
            pass
        fired.append(True)
        app.quit()

    notifier.activated.connect(_slot)
    QTimer.singleShot(50, lambda: os.kill(os.getpid(), signal.SIGTERM))
    app.exec()

    notifier.setEnabled(False)
    signal.set_wakeup_fd(prev_fd)
    signal.signal(signal.SIGTERM, prev_sigterm)
    r.close()
    w.close()

    assert fired, "SIGTERM did not trigger QSocketNotifier via set_wakeup_fd"
```

- [ ] **Step 2: Run the tests — expect both to PASS** (mechanism is pure Qt/Python, no listen.py changes needed)

```bash
cd /home/chrisland/projects/logitechmouse
pytest tests/test_listen_qt_sigterm.py -v
```

Expected: 2 passed (or skipped if no display). If DISPLAY is unset, add `DISPLAY=:0` or run in a display session.

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen_qt_sigterm.py
git commit -m "test(qt_sigterm): mechanism unit tests — socketpair+notifier and set_wakeup_fd"
```

---

## Task 2: Qt SIGTERM integration tests

**Files:**
- Modify: `tests/test_listen_qt_sigterm.py` (append tests)

- [ ] **Step 1: Append integration tests for `_run_with_qt` signal setup**

```python
# append to tests/test_listen_qt_sigterm.py
import argparse
from unittest.mock import MagicMock, patch

from logitechmouse.cli import listen as listen_mod


@pytest.fixture
def ring_cfg(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[device]\npath = "/dev/input/event99"\n\n'
        '[actions.a]\nkind = "command"\ncommand = "true"\n\n'
        '[rings.r]\nsegments = [\n'
        '  { action = "a", label = "A" },\n'
        '  { action = "a", label = "B" },\n'
        ']\n\n'
        '[bindings.b1]\ntrigger = "BTN_BACK"\ntarget = "ring:r"\n'
    )
    return cfg


def test_run_with_qt_installs_noop_sigterm_and_restores_it(ring_cfg):
    """_run_with_qt must replace the SIGTERM handler with a no-op while
    app.exec() runs, then restore the original handler on exit."""
    args = argparse.Namespace(config=ring_cfg, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")

    original_sigterm = signal.getsignal(signal.SIGTERM)
    captured = {}

    def fake_exec():
        captured["sigterm"] = signal.getsignal(signal.SIGTERM)
        return 0

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=None), \
         patch("PyQt6.QtWidgets.QApplication.exec", side_effect=fake_exec), \
         patch("PyQt6.QtCore.QThread.start"), \
         patch("PyQt6.QtCore.QThread.wait"):
        listen_mod.run(args)

    assert captured.get("sigterm") is not original_sigterm, \
        "SIGTERM handler must be replaced (no-op) during app.exec()"
    assert signal.getsignal(signal.SIGTERM) is original_sigterm, \
        "SIGTERM handler must be restored after _run_with_qt returns"


def test_run_with_qt_tears_down_virt_after_sigterm(ring_cfg):
    """Teardown (virt.close, device.ungrab) must run after app.exec() returns
    regardless of whether exit was triggered by SIGTERM or normal finish."""
    args = argparse.Namespace(config=ring_cfg, device=None)
    fake_dev = MagicMock(path="/dev/input/event99", name="fake")
    fake_virt = MagicMock()

    with patch.object(listen_mod.EvdevBackend, "resolve", return_value=fake_dev), \
         patch.object(listen_mod.EvdevBackend, "read_loop", return_value=iter([])), \
         patch("logitechmouse.cli.listen.try_grab", return_value=fake_virt), \
         patch("PyQt6.QtWidgets.QApplication.exec", return_value=0), \
         patch("PyQt6.QtCore.QThread.start"), \
         patch("PyQt6.QtCore.QThread.wait"):
        listen_mod.run(args)

    fake_virt.close.assert_called_once()
    fake_dev.ungrab.assert_called_once()
```

- [ ] **Step 2: Run — expect the two new integration tests to FAIL**

```bash
pytest tests/test_listen_qt_sigterm.py -v
```

Expected: `test_run_with_qt_installs_noop_sigterm_and_restores_it` FAILS (handler not yet replaced), `test_run_with_qt_tears_down_virt_after_sigterm` may pass or fail.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_listen_qt_sigterm.py
git commit -m "test(qt_sigterm): integration tests for _run_with_qt signal setup (failing)"
```

---

## Task 3: Implement Qt-path SIGTERM fix

**Files:**
- Modify: `src/logitechmouse/cli/listen.py`

- [ ] **Step 1: Add `import socket` to the top of listen.py**

Current imports (lines 1-8):
```python
from __future__ import annotations

import argparse
import logging
import signal
import sys
from contextlib import contextmanager
from typing import Callable
```

Replace with:
```python
from __future__ import annotations

import argparse
import logging
import signal
import socket
import sys
from contextlib import contextmanager
from typing import Callable
```

- [ ] **Step 2: Replace the `try: app.exec()` block in `_run_with_qt`**

Find this block in `_run_with_qt` (currently after `thread.start()`, around line 273):
```python
    try:
        app.exec()
        thread.wait(2000)
    finally:
        if virt is not None:
            try:
                virt.close()
            except Exception:
                logging.exception("virt.close() failed")
            try:
                device.ungrab()
            except OSError:
                pass

    return return_code["value"]
```

Replace with:
```python
    from PyQt6.QtCore import QSocketNotifier

    r_sock, w_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    r_sock.setblocking(False)
    w_sock.setblocking(False)

    _wakeup_active = False
    prev_wakeup_fd = -1
    prev_sigterm = signal.getsignal(signal.SIGTERM)
    prev_sigint = signal.getsignal(signal.SIGINT)
    notifier = None

    try:
        prev_wakeup_fd = signal.set_wakeup_fd(w_sock.fileno())
        _wakeup_active = True
    except ValueError as exc:
        logging.warning("set_wakeup_fd unavailable: %s; SIGTERM will hard-kill the Qt path", exc)
        r_sock.close()
        w_sock.close()

    if _wakeup_active:
        signal.signal(signal.SIGTERM, lambda s, f: None)
        signal.signal(signal.SIGINT, lambda s, f: None)
        notifier = QSocketNotifier(r_sock.fileno(), QSocketNotifier.Type.Read)

        def _on_signal_wakeup():
            try:
                r_sock.recv(256)
            except OSError:
                pass
            app.quit()

        notifier.activated.connect(_on_signal_wakeup)

    try:
        app.exec()
        thread.wait(2000)
    finally:
        if _wakeup_active:
            notifier.setEnabled(False)
            signal.set_wakeup_fd(prev_wakeup_fd)
            signal.signal(signal.SIGTERM, prev_sigterm)
            signal.signal(signal.SIGINT, prev_sigint)
            r_sock.close()
            w_sock.close()
        if virt is not None:
            try:
                virt.close()
            except Exception:
                logging.exception("virt.close() failed")
            try:
                device.ungrab()
            except OSError:
                pass

    return return_code["value"]
```

- [ ] **Step 3: Run all Qt SIGTERM tests — expect all to pass**

```bash
pytest tests/test_listen_qt_sigterm.py -v
```

Expected: all 4 tests pass (2 mechanism + 2 integration).

- [ ] **Step 4: Run full test suite — expect no regressions**

```bash
pytest -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/cli/listen.py
git commit -m "feat(listen): Qt-path SIGTERM via set_wakeup_fd + QSocketNotifier"
```

---

## Task 4: install-service tests

**Files:**
- Create: `tests/test_install_service.py`

- [ ] **Step 1: Write all install-service tests**

```python
# tests/test_install_service.py
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _args(config: Path, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(config=config, force=force)


def _run(args, home: Path):
    from logitechmouse.cli import install_service as mod
    with patch("pathlib.Path.home", return_value=home):
        return mod.run(args)


def test_happy_path_writes_unit_file(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("[device]\npath = '/dev/input/event0'\n")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/local/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=0)):
        rc = _run(_args(config), home=tmp_path)

    assert rc == 0
    unit = tmp_path / ".config" / "systemd" / "user" / "logitechmouse.service"
    assert unit.exists()
    content = unit.read_text()
    assert "/usr/local/bin/logitechmouse" in content
    assert str(config.resolve()) in content
    assert "listen --config" in content
    assert "Restart=on-failure" in content


def test_happy_path_runs_daemon_reload(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")

    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run", mock_run):
        _run(_args(config), home=tmp_path)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "daemon-reload" in cmd


def test_config_not_found_returns_1_no_unit_written(tmp_path):
    args = _args(tmp_path / "missing.toml")
    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"):
        rc = _run(args, home=tmp_path)

    assert rc == 1
    unit = tmp_path / ".config" / "systemd" / "user" / "logitechmouse.service"
    assert not unit.exists()


def test_binary_not_resolvable_returns_1(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")
    with patch("logitechmouse.cli.install_service.shutil.which", return_value=None), \
         patch("sys.argv", []):
        rc = _run(_args(config), home=tmp_path)
    assert rc == 1


def test_existing_unit_without_force_returns_1_and_does_not_overwrite(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit = unit_dir / "logitechmouse.service"
    unit.write_text("old content")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"):
        rc = _run(_args(config, force=False), home=tmp_path)

    assert rc == 1
    assert unit.read_text() == "old content"


def test_force_overwrites_existing_unit(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "logitechmouse.service").write_text("old content")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=0)):
        rc = _run(_args(config, force=True), home=tmp_path)

    assert rc == 0
    content = (unit_dir / "logitechmouse.service").read_text()
    assert content != "old content"
    assert "listen --config" in content


def test_daemon_reload_failure_warns_but_returns_0(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")

    with patch("logitechmouse.cli.install_service.shutil.which",
               return_value="/usr/bin/logitechmouse"), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=1)):
        rc = _run(_args(config), home=tmp_path)

    assert rc == 0  # warn only, file is written


def test_fallback_to_argv0_when_which_returns_none(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("")

    with patch("logitechmouse.cli.install_service.shutil.which", return_value=None), \
         patch("sys.argv", ["/home/user/.local/bin/logitechmouse", "install-service"]), \
         patch("logitechmouse.cli.install_service.subprocess.run",
               return_value=MagicMock(returncode=0)):
        rc = _run(_args(config), home=tmp_path)

    assert rc == 0
    unit = tmp_path / ".config" / "systemd" / "user" / "logitechmouse.service"
    assert "/home/user/.local/bin/logitechmouse" in unit.read_text()
```

- [ ] **Step 2: Run — expect ImportError (module doesn't exist yet)**

```bash
pytest tests/test_install_service.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `logitechmouse.cli.install_service` does not exist.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_install_service.py
git commit -m "test(install_service): all cases — happy path, errors, force, daemon-reload"
```

---

## Task 5: Implement install-service

**Files:**
- Create: `src/logitechmouse/cli/install_service.py`

- [ ] **Step 1: Create the module**

```python
# src/logitechmouse/cli/install_service.py
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

_UNIT_TEMPLATE = """\
[Unit]
Description=Logitech Mouse button remapper
After=graphical-session.target

[Service]
ExecStart={exec_start} listen --config {config_path}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""


def run(args: argparse.Namespace) -> int:
    exec_start = shutil.which("logitechmouse") or (sys.argv[0] if sys.argv else None)
    if not exec_start:
        logging.error("cannot resolve logitechmouse binary; check your PATH")
        return 1

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        logging.error("config file not found: %s", config_path)
        return 1

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_path = unit_dir / "logitechmouse.service"

    if unit_path.exists() and not getattr(args, "force", False):
        logging.error(
            "service file already exists: %s — use --force to overwrite",
            unit_path,
        )
        return 1

    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        _UNIT_TEMPLATE.format(exec_start=exec_start, config_path=config_path)
    )
    logging.info("wrote %s", unit_path)

    result = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
    )
    if result.returncode != 0:
        logging.warning(
            "systemctl --user daemon-reload failed (rc=%d); "
            "run it manually once a systemd user session is available",
            result.returncode,
        )

    print(
        f"\nService file written to {unit_path}\n"
        f"Enable and start with:\n"
        f"  systemctl --user enable --now logitechmouse\n"
    )
    return 0
```

- [ ] **Step 2: Run install-service tests — expect all to pass**

```bash
pytest tests/test_install_service.py -v
```

Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/logitechmouse/cli/install_service.py
git commit -m "feat(cli): install-service command — writes systemd user unit file"
```

---

## Task 6: Wire install-service into main.py

**Files:**
- Modify: `src/logitechmouse/main.py`

- [ ] **Step 1: Add the subparser and dispatch to `main.py`**

In `build_parser()`, after the `p_run` subparser block (around line 46), add:

```python
    p_install = sub.add_parser(
        "install-service",
        help="Write a systemd user unit file for logitechmouse",
    )
    p_install.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to config TOML (baked into the unit file's ExecStart)",
    )
    p_install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing unit file",
    )
```

In `main()`, add a branch in the `if/elif` chain (after the `run` branch, before the `else`):

```python
    elif args.command == "install-service":
        from .cli.install_service import run as run_cmd
```

- [ ] **Step 2: Smoke-test the CLI wiring**

```bash
cd /home/chrisland/projects/logitechmouse
python -m logitechmouse install-service --help
```

Expected output includes `--config` (required) and `--force`.

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass (no regressions).

- [ ] **Step 4: Commit**

```bash
git add src/logitechmouse/main.py
git commit -m "feat(main): wire install-service subcommand"
```

---

## Task 7: Final verification and push

- [ ] **Step 1: Run full test suite one more time**

```bash
pytest -v 2>&1 | tail -20
```

Expected: all green, no skips other than `requires_display` / `requires_uinput`.

- [ ] **Step 2: Check that `install-service` end-to-end produces a valid unit**

```bash
# create a dummy config file
tmp=$(mktemp /tmp/logitechmouse-XXXX.toml)
echo '[device]' > "$tmp"
echo 'path = "/dev/input/event0"' >> "$tmp"

python -m logitechmouse install-service --config "$tmp"
cat ~/.config/systemd/user/logitechmouse.service
rm "$tmp"
```

Expected: file exists, contains `ExecStart=...logitechmouse listen --config /tmp/logitechmouse-...toml`.

- [ ] **Step 3: Push branch and open PR**

```bash
git push origin main
```

Or if working on a feature branch:
```bash
git checkout -b phase6-qt-sigterm
git push -u origin phase6-qt-sigterm
gh pr create --title "feat: Phase 6 — Qt-path SIGTERM + systemd unit" \
  --body "Fixes SIGTERM on the Qt listen path via set_wakeup_fd + QSocketNotifier. Adds install-service command."
```
