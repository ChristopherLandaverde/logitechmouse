import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from logitechmouse.config import Ring, Segment
from logitechmouse.overlay.widget import RingWidget


@pytest.fixture
def fake_ring():
    return Ring(
        name="r",
        segments=[
            Segment(action="a", label="One"),
            Segment(action="a", label="Two"),
            Segment(action="a", label="Three"),
            Segment(action="a", label="Four"),
        ],
    )


@pytest.mark.requires_display
def test_widget_can_be_constructed_and_shown(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    assert w.isVisible()
    flags = w.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    # WA_TranslucentBackground is intentionally OFF in v1: it interacts badly
    # with some compositors (Mutter on the dev hardware rendered the widget
    # as an invisible black rect). Theming + opt-in transparency is a polish
    # item — see widget.py BG_COLOR comment.
    assert not w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert w.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    w.hide()
    qtbot.wait(80)  # allow 50 ms InCubic fade-out
    assert not w.isVisible()


@pytest.mark.requires_display
def test_widget_initial_state_no_segment_active(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    w.update_cursor_position(500, 500)
    assert w.is_in_dead_zone is True


@pytest.mark.requires_display
def test_widget_open_animation_runs_and_finishes_at_full_opacity(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    assert w._open_animation is not None  # type: ignore[attr-defined]
    qtbot.wait(120)  # > 75 ms + slop
    assert w.windowOpacity() == pytest.approx(1.0, abs=1e-3)
