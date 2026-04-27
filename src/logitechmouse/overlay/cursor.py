"""8ms cursor polling on the Qt main thread."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QCursor


class CursorPoller(QObject):
    """Polls QCursor.pos() at a fixed interval and calls back with (x, y).
    Skips the callback when the cursor has not moved since the last tick.
    """

    def __init__(
        self,
        on_position: Callable[[int, int], None],
        interval_ms: int = 8,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_position = on_position
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self._last: tuple[int, int] | None = None

    def start(self) -> None:
        self._last = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        p = QCursor.pos()
        pos = (p.x(), p.y())
        if pos == self._last:
            return
        self._last = pos
        self._on_position(pos[0], pos[1])
