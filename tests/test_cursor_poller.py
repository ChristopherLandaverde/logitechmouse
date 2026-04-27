import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import QPoint
from unittest.mock import MagicMock, patch

from logitechmouse.overlay.cursor import CursorPoller


@pytest.mark.requires_display
def test_poller_calls_callback_with_cursor_position(qtbot):
    callback = MagicMock()
    poller = CursorPoller(on_position=callback, interval_ms=8)
    with patch("logitechmouse.overlay.cursor.QCursor.pos", return_value=QPoint(123, 456)):
        poller.start()
        qtbot.wait(30)
        poller.stop()
    callback.assert_called()
    last_args = callback.call_args[0]
    assert last_args == (123, 456)


@pytest.mark.requires_display
def test_poller_skips_callback_when_cursor_unchanged(qtbot):
    callback = MagicMock()
    poller = CursorPoller(on_position=callback, interval_ms=8)
    with patch("logitechmouse.overlay.cursor.QCursor.pos", return_value=QPoint(100, 100)):
        poller.start()
        qtbot.wait(40)
        poller.stop()
    assert callback.call_count <= 1


@pytest.mark.requires_display
def test_stop_halts_callbacks(qtbot):
    callback = MagicMock()
    poller = CursorPoller(on_position=callback, interval_ms=8)
    with patch("logitechmouse.overlay.cursor.QCursor.pos", return_value=QPoint(0, 0)):
        poller.start()
        qtbot.wait(20)
        poller.stop()
    count_after_stop = callback.call_count
    qtbot.wait(40)
    assert callback.call_count == count_after_stop
