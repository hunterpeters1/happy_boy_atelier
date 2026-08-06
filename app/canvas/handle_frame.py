"""Reusable interactive transform handles: corner scale + top rotate handle.

Designed for any target item that exposes:
    target.natural_size() -> (w, h)          unscaled local footprint
    target.scale_x() / target.scale_y() / target.set_scale_xy(sx, sy)
    target.rotation() / setRotation(deg)      (standard QGraphicsItem API)

Handles are children of the target item and use ItemIgnoresTransformations
so they render at a constant screen size while still tracking the target's
position, rotation, and scale exactly (Qt maps a child's local position
through the full parent transform chain even when the child itself ignores
that transform for rendering).

Corner-drag resize (free by default, Shift locks proportions) is anchored
at the corner opposite the one being dragged — see canvas/resize_math.py
for the geometry and why it has to be resolved in the item's own rotated
axes rather than screen axes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from .. import constants as C

HANDLE_PX = 9
MIN_SCALE = 0.05
MAX_SCALE = 40.0


class _CornerScaleHandle(QGraphicsRectItem):
    """Purely decorative. Actual resize interaction (hit-testing + drag) is
    handled directly by ReferenceImageItem itself (see
    layers/reference_layer.py: _hit_test_handle/_begin_handle_drag/
    _update_handle_drag). Confirmed at runtime that giving THIS item its
    own mousePressEvent didn't work: clicks landed on the parent
    (ReferenceImageItem, which is movable) instead of this child, dragging
    the whole image rather than resizing it — a known Qt limitation with
    hit-testing ItemIgnoresTransformations children over a transformed
    parent. setAcceptedMouseButtons(NoButton) below makes that explicit
    rather than relying on it being accidentally unreachable.
    """

    def __init__(self, target, sign_x: int, sign_y: int):
        super().__init__(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX, target)
        self._target = target
        self._sign_x = sign_x
        self._sign_y = sign_y
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(C.COLOR_BRASS)))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setCursor(QCursor(Qt.SizeFDiagCursor if sign_x * sign_y > 0 else Qt.SizeBDiagCursor))
        self.setAcceptedMouseButtons(Qt.NoButton)

    def reposition(self) -> None:
        w, h = self._target.natural_size()
        self.setPos(self._sign_x * w / 2, self._sign_y * h / 2)


class _RotateHandle(QGraphicsRectItem):
    """Purely decorative — see _CornerScaleHandle docstring above."""

    def __init__(self, target):
        super().__init__(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX, target)
        self._target = target
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(C.COLOR_BRASS_BRIGHT)))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAcceptedMouseButtons(Qt.NoButton)

    def reposition(self) -> None:
        w, h = self._target.natural_size()
        offset = max(20.0, h * 0.18)
        self.setPos(0, -h / 2 - offset)


class HandleFrame:
    """Owns the set of handle children for a target item and manages their
    visibility/position. Not a QGraphicsItem itself — just a small manager
    the target composes.
    """

    def __init__(self, target):
        self._target = target
        self._corners = [
            _CornerScaleHandle(target, -1, -1),
            _CornerScaleHandle(target, 1, -1),
            _CornerScaleHandle(target, -1, 1),
            _CornerScaleHandle(target, 1, 1),
        ]
        self._rotate = _RotateHandle(target)
        self.set_active(False)

    def reposition(self) -> None:
        for h in self._corners:
            h.reposition()
        self._rotate.reposition()

    def set_active(self, active: bool) -> None:
        for h in self._corners:
            h.setVisible(active)
        self._rotate.setVisible(active)
        if active:
            self.reposition()
