"""Transparent always-on-top ring overlay. PyQt6 + X11."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..config import Ring
from .geometry import is_in_dead_zone, shifted_center_for_screen, wedge_index


# Visual constants — tunable later.
RING_OUTER_RADIUS = 180
RING_DEAD_ZONE_RADIUS = 45
BG_COLOR = QColor(24, 24, 24, int(0.85 * 255))
ACTIVE_BG_COLOR = QColor(56, 56, 56, int(0.92 * 255))
SEPARATOR_COLOR = QColor(0, 0, 0, 200)
LABEL_COLOR = QColor(230, 230, 230)
CANCEL_COLOR = QColor(160, 160, 160)


class RingWidget(QWidget):
    """Renders the ring. Polled cursor position drives `active_segment_index`
    and `is_in_dead_zone`. The widget itself does not capture input.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._ring: Ring | None = None
        self._center_x = 0
        self._center_y = 0
        self.active_segment_index = 0
        self.is_in_dead_zone = True

    # --- public API consumed by RingController ---

    def show_at(self, ring: Ring, cursor_pos: tuple[int, int]) -> None:
        self._ring = ring
        screen = QGuiApplication.screenAt(QPoint(*cursor_pos)) or QGuiApplication.primaryScreen()
        geom = screen.geometry()
        cx, cy = shifted_center_for_screen(
            cursor_x=cursor_pos[0],
            cursor_y=cursor_pos[1],
            screen_left=geom.left(),
            screen_top=geom.top(),
            screen_right=geom.right(),
            screen_bottom=geom.bottom(),
            ring_radius=RING_OUTER_RADIUS,
        )
        self._center_x, self._center_y = cx, cy
        size = RING_OUTER_RADIUS * 2 + 8
        self.setGeometry(
            cx - RING_OUTER_RADIUS - 4,
            cy - RING_OUTER_RADIUS - 4,
            size,
            size,
        )
        self.update_cursor_position(*cursor_pos)
        self.show()
        self.raise_()

    def update_cursor_position(self, cursor_x: int, cursor_y: int) -> None:
        if self._ring is None:
            return
        dx = cursor_x - self._center_x
        dy = cursor_y - self._center_y
        self.is_in_dead_zone = is_in_dead_zone(dx, dy, RING_DEAD_ZONE_RADIUS)
        if not self.is_in_dead_zone:
            self.active_segment_index = wedge_index(dx, dy, len(self._ring.segments))
        self.update()

    # --- painting ---

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._ring is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        ox = w / 2.0
        oy = h / 2.0

        n = len(self._ring.segments)
        wedge_deg = 360.0 / n
        outer = RING_OUTER_RADIUS
        inner = RING_DEAD_ZONE_RADIUS

        for i in range(n):
            theta_center = i * wedge_deg
            qt_start_angle = (90.0 - (theta_center + wedge_deg / 2.0))
            color = ACTIVE_BG_COLOR if (
                i == self.active_segment_index and not self.is_in_dead_zone
            ) else BG_COLOR
            p.setPen(QPen(SEPARATOR_COLOR, 1))
            p.setBrush(color)
            rect = QRectF(ox - outer, oy - outer, outer * 2, outer * 2)
            p.drawPie(rect, int(qt_start_angle * 16), int(wedge_deg * 16))

            label_radius = outer * 0.70
            theta_rad = (theta_center - 90.0) * 3.141592653589793 / 180.0
            import math as _m
            lx = ox + _m.cos(theta_rad) * label_radius
            ly = oy + _m.sin(theta_rad) * label_radius
            p.setPen(LABEL_COLOR)
            text = self._ring.segments[i].label
            metrics = p.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()
            p.drawText(int(lx - tw / 2), int(ly + th / 4), text)

        p.setPen(QPen(SEPARATOR_COLOR, 1))
        p.setBrush(QColor(18, 18, 18, int(0.92 * 255)))
        p.drawEllipse(QRectF(ox - inner, oy - inner, inner * 2, inner * 2))

        if self.is_in_dead_zone:
            p.setPen(CANCEL_COLOR)
            text = "Cancel"
            metrics = p.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()
            p.drawText(int(ox - tw / 2), int(oy + th / 4), text)
