"""Transparent always-on-top ring overlay. PyQt6 + X11."""

from __future__ import annotations

import math
import os

from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QBrush, QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap, QRadialGradient, QRegion
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
BUBBLE_ORBIT = 115
BUBBLE_R = 24
BUBBLE_R_ACTIVE = 30
_ICON_SIZE = 18
_ICON_SIZE_ACTIVE = 22

_THEMES: dict[str, dict[str, QColor]] = {
    "dark": {
        "bubble":        QColor(32, 32, 32, 255),
        "bubble_active": QColor(252, 252, 252, 255),
        "dead_zone":     QColor(6, 6, 6, 255),
        "label":         QColor(158, 158, 158, 255),
        "label_active":  QColor(4, 4, 4, 255),
        "cancel":        QColor(58, 58, 58, 255),
        "center_label":  QColor(248, 248, 248, 255),
    },
    "brazil": {
        "bubble":        QColor(32, 32, 32, 255),
        "bubble_active": QColor(255, 223, 0, 255),
        "dead_zone":     QColor(255, 223, 0, 255),
        "label":         QColor(158, 158, 158, 255),
        "label_active":  QColor(0, 39, 118, 255),
        "cancel":        QColor(255, 255, 255, 255),
        "center_label":  QColor(0, 39, 118, 255),
    },
}

def _color_from_hex(raw: str) -> QColor:
    """Convert '#rrggbb' or '#rrggbbaa' to QColor. Caller has already validated."""
    body = raw.lstrip("#")
    if len(body) == 6:
        r, g, b = int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)
        return QColor(r, g, b, 255)
    return QColor(int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16), int(body[6:8], 16))


def apply_theme(name: str = "dark", overrides: dict[str, str] | None = None) -> None:
    """Replace the active theme palette. Env var LOGITECHMOUSE_THEME, when set,
    overrides `name` so users can force a preset for testing without editing
    config. Unknown preset names fall back to dark (validation happens upstream
    in config.py — this is the safety net)."""
    env_name = os.environ.get("LOGITECHMOUSE_THEME")
    chosen = (env_name or name or "dark").lower()
    base = _THEMES.get(chosen, _THEMES["dark"]).copy()
    if overrides:
        for key, hex_value in overrides.items():
            if key in base:
                base[key] = _color_from_hex(hex_value)
    global _theme
    _theme = base


_theme: dict[str, QColor] = {}
apply_theme()


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
        self._close_animation: QPropertyAnimation | None = None
        self.is_in_dead_zone = True
        self._icon_cache: dict[tuple, QPixmap | None] = {}
        self._bubble_offsets: list[tuple[float, float]] = []
        self._monogram_font = QFont()
        self._monogram_font.setBold(True)
        self._monogram_font.setPointSize(10)
        self._cancel_font = QFont()
        self._cancel_font.setPointSize(9)
        self._label_font = QFont()
        self._label_font.setPointSize(9)

    def show_at(self, ring: Ring, cursor_pos: tuple[int, int]) -> None:
        if self._close_animation is not None:
            self._close_animation.stop()
            self._close_animation = None

        if ring is not self._ring:
            self._icon_cache.clear()
            n = len(ring.segments)
            self._bubble_offsets = [
                (
                    math.cos(math.radians(i * (360.0 / n) - 90.0)) * BUBBLE_ORBIT,
                    math.sin(math.radians(i * (360.0 / n) - 90.0)) * BUBBLE_ORBIT,
                )
                for i in range(n)
            ]
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
        new_dead = is_in_dead_zone(dx, dy, RING_DEAD_ZONE_RADIUS)
        new_seg = self.active_segment_index
        if not new_dead:
            new_seg = wedge_index(dx, dy, len(self._ring.segments))
        if new_seg == self.active_segment_index and new_dead == self.is_in_dead_zone:
            return
        self.active_segment_index = new_seg
        self.is_in_dead_zone = new_dead
        self.update()

    def hide(self) -> None:  # noqa: A003
        if self._close_animation is not None:
            self._close_animation.stop()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(50)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self._finish_hide)
        anim.start()
        self._close_animation = anim

    def _finish_hide(self) -> None:
        self._close_animation = None
        QWidget.hide(self)

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

        ox = self.width() / 2.0
        oy = self.height() / 2.0

        _backdrop_r = float(BUBBLE_R_ACTIVE + 4)  # matches mask boundary
        for i, (dx_off, dy_off) in enumerate(self._bubble_offsets):
            bx = ox + dx_off
            by = oy + dy_off
            is_active = i == self.active_segment_index and not self.is_in_dead_zone
            r = float(BUBBLE_R_ACTIVE if is_active else BUBBLE_R)

            grad_back = QRadialGradient(QPointF(bx, by), _backdrop_r)
            grad_back.setColorAt(0.0, QColor(20, 20, 20))
            grad_back.setColorAt(1.0, QColor(3, 3, 3))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad_back))
            p.drawEllipse(QRectF(bx - _backdrop_r, by - _backdrop_r, _backdrop_r * 2.0, _backdrop_r * 2.0))

            if is_active:
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 35), 0.8))
            p.setBrush(_theme["bubble_active"] if is_active else _theme["bubble"])
            p.drawEllipse(QRectF(bx - r, by - r, r * 2.0, r * 2.0))

            segment = self._ring.segments[i]
            icon_size = _ICON_SIZE_ACTIVE if is_active else _ICON_SIZE
            pixmap = self._icon_pixmap(segment.icon or "", icon_size, is_active)
            if pixmap is not None:
                p.drawPixmap(int(bx - icon_size / 2), int(by - icon_size / 2), pixmap)
            else:
                monogram = segment.label[0].upper() if segment.label else "?"
                p.setFont(self._monogram_font)
                p.setPen(_theme["label_active"] if is_active else _theme["label"])
                fm = p.fontMetrics()
                p.drawText(int(bx - fm.horizontalAdvance(monogram) / 2), int(by + fm.height() / 4), monogram)

        grad_dz = QRadialGradient(QPointF(ox, oy), RING_DEAD_ZONE_RADIUS)
        grad_dz.setColorAt(0.0, QColor(18, 18, 18))
        grad_dz.setColorAt(0.8, QColor(6, 6, 6))
        grad_dz.setColorAt(1.0, QColor(2, 2, 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad_dz))
        p.drawEllipse(QRectF(ox - RING_DEAD_ZONE_RADIUS, oy - RING_DEAD_ZONE_RADIUS,
                      RING_DEAD_ZONE_RADIUS * 2.0, RING_DEAD_ZONE_RADIUS * 2.0))

        if self.is_in_dead_zone:
            p.setFont(self._cancel_font)
            p.setPen(_theme["cancel"])
            fm = p.fontMetrics()
            p.drawText(int(ox - fm.horizontalAdvance("×") / 2), int(oy + fm.height() / 4), "×")
        elif self._ring is not None:
            label = self._ring.segments[self.active_segment_index].label or ""
            p.setFont(self._label_font)
            p.setPen(_theme["center_label"])
            fm = p.fontMetrics()
            p.drawText(int(ox - fm.horizontalAdvance(label) / 2), int(oy + fm.height() / 4), label)
