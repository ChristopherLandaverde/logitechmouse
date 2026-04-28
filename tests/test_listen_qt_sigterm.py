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
