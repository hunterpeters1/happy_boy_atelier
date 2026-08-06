"""Lighting layer: light source marker, light/shadow direction arrows, and
notes. Purely a planning aid the artist places by hand.
"""

from __future__ import annotations

import math
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsItemGroup, QGraphicsRectItem

from .. import constants as C
from ..canvas.interactive_item import InteractiveItem
from .composition_layer import NoteItem

SOURCE_R = 10
POINT_HANDLE_PX = 8


class LightSourceItem(InteractiveItem):
    def __init__(self, source_id: str | None = None):
        super().__init__()
        self.source_id = source_id or str(uuid.uuid4())
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(12)

    def boundingRect(self) -> QRectF:
        r = SOURCE_R + 8
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(C.COLOR_LIGHT)
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color.lighter(110)))
        painter.drawEllipse(QPointF(0, 0), SOURCE_R * 0.55, SOURCE_R * 0.55)
        for i in range(8):
            angle = math.radians(i * 45)
            x1, y1 = math.cos(angle) * SOURCE_R * 0.75, math.sin(angle) * SOURCE_R * 0.75
            x2, y2 = math.cos(angle) * SOURCE_R * 1.3, math.sin(angle) * SOURCE_R * 1.3
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        if self.isSelected():
            painter.setPen(QPen(QColor(C.COLOR_BRASS_BRIGHT), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), SOURCE_R + 6, SOURCE_R + 6)

    def to_dict(self) -> dict:
        return {"id": self.source_id, "x": self.pos().x(), "y": self.pos().y()}

    @staticmethod
    def from_dict(d: dict) -> "LightSourceItem":
        item = LightSourceItem(source_id=d.get("id"))
        item.setPos(float(d.get("x", 0)), float(d.get("y", 0)))
        return item


class _PointHandle(QGraphicsRectItem):
    def __init__(self, arrow: "DirectionArrowItem", which: str):
        super().__init__(-POINT_HANDLE_PX / 2, -POINT_HANDLE_PX / 2, POINT_HANDLE_PX, POINT_HANDLE_PX, arrow)
        self._arrow = arrow
        self._which = which
        self._press_points = None
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(arrow.color())))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def mousePressEvent(self, event):
        self._press_points = self._arrow.points()
        event.accept()

    def mouseMoveEvent(self, event):
        local = self._arrow.mapFromScene(event.scenePos())
        self._arrow.set_point(self._which, local)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
        if self._press_points is None:
            return
        old = self._press_points
        self._press_points = None
        new = self._arrow.points()
        if old == new:
            return
        scene = self._arrow.scene()
        if scene is None or not hasattr(scene, "undo_stack"):
            return
        from ..canvas.undo_commands import SetPropertyCommand
        scene.undo_stack.push(SetPropertyCommand(self._arrow.set_points, old, new, "Move direction arrow"))


class DirectionArrowItem(InteractiveItem):
    def __init__(self, kind: str, p1: QPointF, p2: QPointF, arrow_id: str | None = None):
        super().__init__()
        self.arrow_id = arrow_id or str(uuid.uuid4())
        self.kind = kind  # "light" | "shadow"
        self._p1 = p1
        self._p2 = p2
        self.setZValue(8)
        self._h1 = _PointHandle(self, "p1")
        self._h2 = _PointHandle(self, "p2")
        self._reposition_handles()

    def color(self) -> str:
        return C.COLOR_LIGHT if self.kind == "light" else C.COLOR_SHADOW

    def _reposition_handles(self) -> None:
        self._h1.setPos(self._p1)
        self._h2.setPos(self._p2)

    def set_point(self, which: str, local: QPointF) -> None:
        self.prepareGeometryChange()
        if which == "p1":
            self._p1 = local
        else:
            self._p2 = local
        self._reposition_handles()
        self.update()

    def points(self) -> tuple[QPointF, QPointF]:
        return (QPointF(self._p1), QPointF(self._p2))

    def set_points(self, points: tuple[QPointF, QPointF]) -> None:
        self.prepareGeometryChange()
        self._p1, self._p2 = QPointF(points[0]), QPointF(points[1])
        self._reposition_handles()
        self.update()

    def boundingRect(self) -> QRectF:
        xs = [self._p1.x(), self._p2.x()]
        ys = [self._p1.y(), self._p2.y()]
        return QRectF(min(xs) - 10, min(ys) - 10, max(xs) - min(xs) + 20, max(ys) - min(ys) + 20)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(self.color())
        painter.setPen(QPen(color, 2))
        painter.drawLine(self._p1, self._p2)
        angle = math.atan2(self._p2.y() - self._p1.y(), self._p2.x() - self._p1.x())
        size = 10
        tip = self._p2
        left = QPointF(tip.x() - size * math.cos(angle - 0.4), tip.y() - size * math.sin(angle - 0.4))
        right = QPointF(tip.x() - size * math.cos(angle + 0.4), tip.y() - size * math.sin(angle + 0.4))
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([tip, left, right]))
        if self.isSelected():
            painter.setPen(QPen(QColor(C.COLOR_BRASS), 1, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "id": self.arrow_id, "kind": self.kind,
            "x1": self._p1.x() + pos.x(), "y1": self._p1.y() + pos.y(),
            "x2": self._p2.x() + pos.x(), "y2": self._p2.y() + pos.y(),
        }

    @staticmethod
    def from_dict(d: dict) -> "DirectionArrowItem":
        return DirectionArrowItem(
            d.get("kind", "light"),
            QPointF(float(d.get("x1", 0)), float(d.get("y1", 0))),
            QPointF(float(d.get("x2", 40)), float(d.get("y2", 0))),
            arrow_id=d.get("id"),
        )


class LightingLayerGroup(QGraphicsItemGroup):
    def __init__(self):
        super().__init__()
        self.setHandlesChildEvents(False)
        self.sources: list[LightSourceItem] = []
        self.arrows: list[DirectionArrowItem] = []
        self.notes: list[NoteItem] = []

    def add_existing(self, item) -> None:
        """Add an already-constructed item, routing it to the right
        bookkeeping bucket by type — the single choke point both the
        convenience add_X() methods below and AddItemCommand's redo() use.
        """
        if isinstance(item, LightSourceItem):
            bucket = self.sources
        elif isinstance(item, DirectionArrowItem):
            bucket = self.arrows
        elif isinstance(item, NoteItem):
            bucket = self.notes
        else:
            raise TypeError(f"LightingLayerGroup cannot host {type(item).__name__}")
        self.addToGroup(item)
        if item not in bucket:
            bucket.append(item)

    def add_source(self, pos: QPointF) -> LightSourceItem:
        item = LightSourceItem()
        item.setPos(pos)
        self.add_existing(item)
        return item

    def add_arrow(self, kind: str, p1: QPointF, p2: QPointF) -> DirectionArrowItem:
        item = DirectionArrowItem(kind, p1, p2)
        self.add_existing(item)
        return item

    def add_note(self, pos: QPointF, text: str = "Lighting note") -> NoteItem:
        item = NoteItem(text=text, color=C.COLOR_LIGHT)
        item.setPos(pos)
        self.add_existing(item)
        return item

    def all_items(self):
        return [*self.sources, *self.arrows, *self.notes]

    def remove_item(self, item) -> None:
        for bucket in (self.sources, self.arrows, self.notes):
            if item in bucket:
                bucket.remove(item)
        self.removeFromGroup(item)
        if item.scene():
            item.scene().removeItem(item)

    def clear(self) -> None:
        for item in self.all_items():
            self.remove_item(item)

    def set_layer_locked(self, locked: bool) -> None:
        for item in self.all_items():
            item.set_locked(locked)

    def to_dict(self) -> dict:
        return {
            "sources": [s.to_dict() for s in self.sources],
            "arrows": [a.to_dict() for a in self.arrows],
            "notes": [n.to_dict() for n in self.notes],
        }

    def load_from_dict(self, data: dict) -> None:
        self.clear()
        for s in data.get("sources", []):
            item = LightSourceItem.from_dict(s)
            self.addToGroup(item)
            self.sources.append(item)
        for a in data.get("arrows", []):
            item = DirectionArrowItem.from_dict(a)
            self.addToGroup(item)
            self.arrows.append(item)
        for n in data.get("notes", []):
            item = NoteItem.from_dict(n, color=C.COLOR_LIGHT)
            self.addToGroup(item)
            self.notes.append(item)
