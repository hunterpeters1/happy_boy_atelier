"""Radial (pie) menu for right-click context, replacing the conventional
linear context menu. Appears centered on the cursor with segments arranged
in a ring — the artist moves the mouse in the direction of the desired action
and clicks to confirm.

This is a drafting-tool interaction (deliberate, directional) rather than
a consumer-software context menu (linear list). Each segment shows an icon
and a label that fades in on hover.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import constants as C
from . import icons


# Angles (degrees) where each segment sits. Segment 0 is at the top (12 o'clock)
# and proceeds clockwise. Each segment gets an equal slice.
# Default: 8 segments (N, NE, E, SE, S, SW, W, NW) — enough for the full
# context-sensitive action set without crowding.
_DEFAULT_SLICES = 8


class RadialMenu(QWidget):
    """A pie menu that appears at a cursor position and lets the user
    select an action by moving the mouse in its direction."""

    action_triggered = Signal(object)  # the QAction or callable

    def __init__(self, items: list[tuple[str, str, object]], center: QPoint, parent=None):
        """items: list of (icon_name, label, action_or_callable) tuples.
           Positioned so `center` is the middle of the ring."""
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMousePos, False)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)

        self._items = items
        self._center = center
        self._hovered_index = -1
        self._outer_radius = 96  # px
        self._inner_radius = 28  # px — center dead zone
        self._label_offset = 32  # px from ring center for labels

        self.setMouseTracking(True)
        self.setFixedSize(self._outer_radius * 2 + 16, self._outer_radius * 2 + 16)
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

        # Close the menu after a short delay if the user doesn't interact
        self._auto_close = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        n = len(self._items)
        if n == 0:
            return

        slice_angle = 360.0 / n
        # Start at 12 o'clock, proceeding clockwise
        start_angle = -90.0

        for i, (icon_name, label, action) in enumerate(self._items):
            angle = start_angle + i * slice_angle
            angle_rad = math.radians(angle)
            next_angle = angle + slice_angle
            next_angle_rad = math.radians(next_angle)

            # Draw the pie slice
            path = QPainter.Path()
            path.moveTo(cx, cy)
            path.arcTo(cx - self._outer_radius, cy - self._outer_radius,
                       self._outer_radius * 2, self._outer_radius * 2,
                       angle, slice_angle)
            path.closeSubpath()

            # Fill
            if i == self._hovered_index:
                painter.setBrush(QColor(C.COLOR_BRASS))
                painter.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
            else:
                painter.setBrush(QColor(C.COLOR_BG_RAISED))
                painter.setPen(QPen(C.COLOR_LINE, 1))
            painter.drawPath(path)

            # Inner ring cutout (so it's an annulus, not a full pie)
            hole_path = QPainter.Path()
            hole_path.addEllipse(QPointF(cx, cy), self._inner_radius, self._inner_radius)
            path = path - hole_path

            # Redraw with the cutout
            if i == self._hovered_index:
                painter.setBrush(QColor(C.COLOR_BRASS))
            else:
                painter.setBrush(QColor(C.COLOR_BG_RAISED))
            painter.drawPath(path)

            # Draw icon at the slice's mid-angle
            mid_angle = angle + slice_angle / 2
            icon_dist = (self._inner_radius + self._outer_radius) / 2
            icon_x = cx + math.cos(math.radians(mid_angle)) * icon_dist
            icon_y = cy + math.sin(math.radians(mid_angle)) * icon_dist

            pm = icons.icon(icon_name, 20).pixmap(20, 20)
            painter.drawPixmap(icon_x - 10, icon_y - 10, pm)

            # Draw label on hover
            if i == self._hovered_index:
                label_x = cx + math.cos(math.radians(mid_angle)) * (self._outer_radius + self._label_offset)
                label_y = cy + math.sin(math.radians(mid_angle)) * (self._outer_radius + self._label_offset)
                painter.setPen(QPen(QColor(C.COLOR_INK)))
                painter.setFont(QFont(C.FONT_FAMILY_UI, 9))
                painter.drawText(label_x + 4, label_y + 4, label)

        # Center circle — dimmed, for cancel
        painter.setBrush(QColor(C.COLOR_BG_DARK))
        painter.setPen(QPen(C.COLOR_LINE, 1))
        painter.drawEllipse(QPointF(cx, cy), self._inner_radius, self._inner_radius)

        # Center icon (close/cancel)
        center_pm = icons.icon("delete", 16).pixmap(16, 16)
        painter.drawPixmap(cx - 8, cy - 8, center_pm)

    def mouseMoveEvent(self, event):
        cx, cy = self.width() / 2, self.height() / 2
        mouse = event.position().toPointF()
        dx = mouse.x() - cx
        dy = mouse.y() - cy
        dist = math.hypot(dx, dy)

        if dist < self._inner_radius:
            # In the center dead zone — cancel
            self._hovered_index = -1
            self.update()
            return

        angle = math.degrees(math.atan2(dy, dx))
        # Normalize to 0-360
        if angle < 0:
            angle += 360.0

        # Map angle to slice index
        # Our slices start at -90 (12 o'clock) and go clockwise
        adjusted = angle + 90.0
        while adjusted < 0:
            adjusted += 360.0
        while adjusted >= 360.0:
            adjusted -= 360.0

        n = len(self._items)
        slice_angle = 360.0 / n
        index = int(adjusted / slice_angle)

        if index != self._hovered_index:
            self._hovered_index = index
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            cx, cy = self.width() / 2, self.height() / 2
            mouse = event.position().toPointF()
            dx = mouse.x() - cx
            dy = mouse.y() - cy
            dist = math.hypot(dx, dy)

            if dist < self._inner_radius:
                # Center — cancel/close
                self.close()
            elif self._hovered_index >= 0:
                icon_name, label, action = self._items[self._hovered_index]
                self.action_triggered.emit(action)
                self.close()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def leaveEvent(self, event):
        # Don't cancel on leave — the user might be moving to click a segment
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        # Close when losing focus
        self.close()
        super().focusOutEvent(event)


def show_radial_menu(items: list[tuple[str, str, object]], center: QPoint, parent=None) -> RadialMenu:
    """Show a radial menu at `center` with the given items.
    Returns the RadialMenu instance."""
    menu = RadialMenu(items, center, parent)
    menu.show()
    return menu
