from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QSocketNotifier, QTimer
from PyQt6.QtWidgets import QApplication

from logitechmouse.cli import listen as listen_mod


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
    signal.signal(signal.SIGTERM, lambda s, f: None)

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


# ---------------------------------------------------------------------------
# Integration tests — _run_with_qt signal handler setup/restore
# ---------------------------------------------------------------------------


@pytest.fixture
def ring_cfg(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[device]\npath = "/dev/input/event99"\n\n'
        '[actions.a]\nkind = "command"\ncommand = "true"\n\n'
        '[rings.r]\nsegments = [\n'
        '  { action = "a", label = "A" },\n'
        '  { action = "a", label = "B" },\n'
        '  { action = "a", label = "C" },\n'
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


def test_run_with_qt_tears_down_virt_after_exec_returns(ring_cfg):
    """virt.close() and device.ungrab() must be called after app.exec() returns."""
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
