from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from ..actions import run_action as _default_run_action
from ..config import AppConfig, ConfigError, load_config, validate_config
from ..device import (
    DeviceNotFoundError,
    DeviceUnreadableError,
    EvdevBackend,
)


REMEDIATION = (
    "device is not readable. Add yourself to the `input` group:\n"
    "  sudo usermod -aG input $USER\n"
    "Then log out and back in."
)


def dispatch_event(
    cfg: AppConfig,
    ring_controller,
    run_action: Callable,
    trigger: str,
    pressed: bool,
    cursor_pos: tuple[int, int],
) -> None:
    """Pure dispatch logic — testable without Qt or threads."""
    binding = next(
        (b for b in cfg.bindings.values() if b.trigger == trigger),
        None,
    )
    if binding is None:
        return
    if binding.target.kind == "action":
        if pressed:
            action = cfg.actions[binding.target.name]
            result = run_action(action)
            if result.ok:
                logging.info("%s", result.detail)
            else:
                logging.warning("action %r %s", action.name, result.detail)
    elif binding.target.kind == "ring":
        ring = cfg.rings[binding.target.name]
        if pressed:
            logging.info("ring open: %s at %s", ring.name, cursor_pos)
            ring_controller.open(ring, cursor_pos=cursor_pos)
        else:
            logging.info("ring close: %s", ring.name)
            ring_controller.close()


def _has_ring_bindings(cfg: AppConfig) -> bool:
    return any(b.target.kind == "ring" for b in cfg.bindings.values())


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1

    if not cfg.bindings:
        logging.error(
            "config has no bindings; nothing would fire on key-down. "
            "Add at least one [bindings.NAME] section pointing to a target."
        )
        return 1

    if getattr(args, "device", None):
        cfg.device.path = args.device

    triggers = {b.trigger for b in cfg.bindings.values()} or None

    backend = EvdevBackend()
    try:
        device = backend.resolve(cfg.device, triggers=triggers)
    except DeviceUnreadableError as exc:
        logging.error("%s\n%s", exc, REMEDIATION)
        return 1
    except DeviceNotFoundError as exc:
        logging.error("%s", exc)
        return 1

    summary = ", ".join(
        f"{b.name}[{b.trigger}]->{b.target.kind}:{b.target.name}"
        for b in cfg.bindings.values()
    ) or "(none)"
    logging.info("listening on %s (%s)", device.path, device.name)
    logging.info("bindings: %s", summary)

    if _has_ring_bindings(cfg):
        return _run_with_qt(cfg, backend, device)
    else:
        return _run_command_only(cfg, backend, device)


def _run_command_only(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    """Phase 2 path: no Qt, blocking read loop on the main thread."""
    try:
        for event in backend.read_loop(device):
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
    return 0


def _run_with_qt(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    """Ring-enabled path: QApplication on main thread, listener on worker thread."""
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

    from ..overlay.ring import RingController
    from ..overlay.widget import RingWidget
    from ..overlay.cursor import CursorPoller

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
                for ev in backend.read_loop(device):
                    self.event_received.emit(ev.trigger, ev.pressed)
            except OSError as exc:
                logging.warning("device read failed: %s", exc)
                self.finished.emit(1)
                return
            self.finished.emit(0)

    class _MainBridge(QObject):
        """Receives signals on the main thread and dispatches.

        Wrapping the slot in a QObject that lives on the main thread forces
        Qt to use a queued connection across threads, so ring_controller.open
        and any QWidget operations always run on the main (GUI) thread.
        """

        @pyqtSlot(str, bool)
        def on_event(self, trigger: str, pressed: bool) -> None:
            p = QCursor.pos()  # safe: this slot runs on the main thread
            dispatch_event(
                cfg,
                ring_controller=ring_controller,
                run_action=_default_run_action,
                trigger=trigger,
                pressed=pressed,
                cursor_pos=(p.x(), p.y()),
            )

    bridge = _MainBridge()  # parented to main thread by default
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

    app.exec()
    thread.wait(2000)
    return return_code["value"]


class _NoOpRingController:
    """Used in the command-only path so dispatch_event can be uniform."""

    def open(self, *args, **kwargs) -> None:
        logging.warning("ring target encountered in command-only listener path")

    def close(self) -> None:
        pass
