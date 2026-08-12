"""A small draggable square handle for one endpoint of a two-point
InteractiveItem — shared by DirectionArrowItem (lighting_layer.py) and
MeasurementItem (composition_layer.py) so both get the same press/move/
release-into-one-undo-command shape instead of each hand-rolling it.
Lives here (not in either layer module) since composition_layer.py and
lighting_layer.py already have a one-way import relationship (lighting
imports NoteItem from composition) and this needed to be reachable from
both without creating a cycle.

`owner` must expose:
- `points() -> (QPointF, QPointF)`
- `set_point(which: str, local: QPointF) -> None`
- `set_points(points: (QPointF, QPointF)) -> None`
- `color() -> str`
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from .. import constants as C

# Was 8 — bumped for a more forgiving grab, same reasoning as
# reference_layer.py's HANDLE_HIT_RADIUS_PX widening.
POINT_HANDLE_PX = 12


class TwoPointHandle(QGraphicsRectItem):
    def __init__(self, owner, which: str, *, undo_text: str):
        super().__init__(-POINT_HANDLE_PX / 2, -POINT_HANDLE_PX / 2, POINT_HANDLE_PX, POINT_HANDLE_PX, owner)
        self._owner = owner
        self._which = which
        self._undo_text = undo_text
        self._press_points = None
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(owner.color())))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def mousePressEvent(self, event) -> None:
        self._press_points = self._owner.points()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        local = self._owner.mapFromScene(event.scenePos())
        self._owner.set_point(self._which, local)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()
        if self._press_points is None:
            return
        old = self._press_points
        self._press_points = None
        new = self._owner.points()
        if old == new:
            return
        scene = self._owner.scene()
        if scene is None or not hasattr(scene, "undo_stack"):
            return
        from .undo_commands import SetPropertyCommand
        scene.undo_stack.push(SetPropertyCommand(self._owner.set_points, old, new, self._undo_text))
