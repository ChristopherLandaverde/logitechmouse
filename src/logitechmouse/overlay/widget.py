"""Transparent always-on-top ring overlay. PyQt6 + X11."""

from __future__ import annotations

import math
import os

from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import QWidget

from ..config import Ring
from .geometry import is_in_dead_zone, shifted_center_for_screen, wedge_index

try:
    import qtawesome as qta
    _QTA_AVAILABLE = True
except ImportError:
    _QTA_AVAILABLE = False


# WA_TranslucentBackground intentionally disabled: on Mutter/GNOME it renders
# as an invisible black square. Opaque backdrop with circular mask in v1.
RING_OUTER_RADIUS = 215
RING_DEAD_ZONE_RADIUS = 38
BUBBLE_ORBIT = 110
BUBBLE_R = 33
BUBBLE_R_ACTIVE = 40
_ICON_SIZE = 22
_ICON_SIZE_ACTIVE = 28

_THEMES: dict[str, dict[str, QColor]] = {
    "dark": {
        "bubble":        QColor(160, 160, 160, 255),
        "bubble_active": QColor(235, 235, 235, 255),
        "dead_zone":     QColor(18, 18, 18, 255),
        "label":         QColor(30, 30, 30, 255),
        "label_active":  QColor(10, 10, 10, 255),
        "cancel":        QColor(130, 130, 130, 255),
    },
    "brazil": {
        "bubble":        QColor(160, 160, 160, 255),
        "bubble_active": QColor(255, 223, 0, 255),
        "dead_zone":     QColor(255, 223, 0, 255),
        "label":         QColor(30, 30, 30, 255),
        "label_active":  QColor(0, 39, 118, 255),
        "cancel":        QColor(255, 255, 255, 255),
    },
}

_theme_name = os.environ.get("LOGITECHMOUSE_THEME", "dark").lower()
_theme = _THEMES.get(_theme_name, _THEMES["dark"])


class RingWidget(QWidget):
    """Renders the ring. Polled cursor position drives active_segment_index
    and is_in_dead_zone. The widget itself does not capture input.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._ring: Ring | None = None
        self._center_x = 0
        self._center_y = 0
        self.active_segment_index = 0
        self._open_animation: QPropertyAnimation | None = None
        self.is_in_dead_zone = True
        self._icon_cache: dict[tuple, QPixmap | None] = {}

    def show_at(self, ring: Ring, cursor_pos: tuple[int, int]) -> None:
        if ring is not self._ring:
            self._icon_cache.clear()
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
        self.setMask(self._build_mask(ring, size))
        self.update_cursor_position(*cursor_pos)
        self.show()
        self.raise_()

        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(75)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._open_animation = anim

    def update_cursor_position(self, cursor_x: int, cursor_y: int) -> None:
        if self._ring is None:
            return
        dx = cursor_x - self._center_x
        dy = cursor_y - self._center_y
        self.is_in_dead_zone = is_in_dead_zone(dx, dy, RING_DEAD_ZONE_RADIUS)
        if not self.is_in_dead_zone:
            self.active_segment_index = wedge_index(dx, dy, len(self._ring.segments))
        self.update()

    def _build_mask(self, ring: Ring, size: int) -> QRegion:
        ox = size / 2.0
        oy = size / 2.0
        n = len(ring.segments)
        region = QRegion()
        dz = RING_DEAD_ZONE_RADIUS + 4
        region |= QRegion(QRect(int(ox - dz), int(oy - dz), dz * 2, dz * 2), QRegion.RegionType.Ellipse)
        for i in range(n):
            theta_rad = math.radians(i * (360.0 / n) - 90.0)
            bx = ox + math.cos(theta_rad) * BUBBLE_ORBIT
            by = oy + math.sin(theta_rad) * BUBBLE_ORBIT
            r = BUBBLE_R_ACTIVE + 4
            region |= QRegion(QRect(int(bx - r), int(by - r), r * 2, r * 2), QRegion.RegionType.Ellipse)
        return region

    def _icon_pixmap(self, icon_name: str, size: int, is_active: bool) -> QPixmap | None:
        if not _QTA_AVAILABLE or not icon_name:
            return None
        key = (icon_name, size, is_active)
        if key not in self._icon_cache:
            color = _theme["label_active"] if is_active else _theme["label"]
            try:
                self._icon_cache[key] = qta.icon(icon_name, color=color).pixmap(size, size)
            except Exception:
                self._icon_cache[key] = None
        return self._icon_cache[key]

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._ring is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        ox = w / 2.0
        oy = h / 2.0
        n = len(self._ring.segments)

        monogram_font = QFont()
        monogram_font.setBold(True)
        monogram_font.setPointSize(10)

        for i in range(n):
            theta_rad = math.radians(i * (360.0 / n) - 90.0)
            bx = ox + math.cos(theta_rad) * BUBBLE_ORBIT
            by = oy + math.sin(theta_rad) * BUBBLE_ORBIT
            is_active = i == self.active_segment_index and not self.is_in_dead_zone
            r = float(BUBBLE_R_ACTIVE if is_active else BUBBLE_R)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_theme["bubble_active"] if is_active else _theme["bubble"])
            p.drawEllipse(QRectF(bx - r, by - r, r * 2.0, r * 2.0))

            segment = self._ring.segments[i]
            icon_size = _ICON_SIZE_ACTIVE if is_active else _ICON_SIZE
            pixmap = self._icon_pixmap(segment.icon or "", icon_size, is_active)
            if pixmap is not None:
                p.drawPixmap(int(bx - icon_size / 2), int(by - icon_size / 2), pixmap)
            else:
                monogram = segment.label[0].upper() if segment.label else "?"
                p.setFont(monogram_font)
                p.setPen(_theme["label_active"] if is_active else _theme["label"])
                fm = p.fontMetrics()
                p.drawText(int(bx - fm.horizontalAdvance(monogram) / 2), int(by + fm.height() / 4), monogram)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_theme["dead_zone"])
        p.drawEllipse(QRectF(ox - RING_DEAD_ZONE_RADIUS, oy - RING_DEAD_ZONE_RADIUS, RING_DEAD_ZONE_RADIUS * 2.0, RING_DEAD_ZONE_RADIUS * 2.0))

        if self.is_in_dead_zone:
            cancel_font = QFont()
            cancel_font.setPointSize(9)
            p.setFont(cancel_font)
            p.setPen(_theme["cancel"])
            fm = p.fontMetrics()
            p.drawText(int(ox - fm.horizontalAdvance("X") / 2), int(oy + fm.height() / 4), "X")
