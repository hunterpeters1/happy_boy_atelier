"""Composition layer: focal point markers, movement lines, and notes. The
artist places every mark by hand — nothing here is computed or suggested.
"""

from __future__ import annotations

import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsTextItem,
)

from .. import constants as C
from ..canvas.interactive_item import InteractiveItem

MARKER_R_PRIMARY = 11
MARKER_R_SECONDARY = 8


class FocalPointItem(InteractiveItem):
    def __init__(self, kind: str = "primary", node_id: str | None = None):
        super().__init__()
        self.node_id = node_id or str(uuid.uuid4())
        self.kind = kind  # "primary" | "secondary"
        self.setZValue(10)
        self.setCursor(Qt.PointingHandCursor)

    def _radius(self) -> float:
        return MARKER_R_PRIMARY if self.kind == "primary" else MARKER_R_SECONDARY

    def boundingRect(self) -> QRectF:
        r = self._radius() + 4
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        r = self._radius()
        color = QColor(C.COLOR_FOCAL_PRIMARY if self.kind == "primary" else C.COLOR_FOCAL_SECONDARY)
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(color) if self.kind == "primary" else Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r, r)
        painter.drawLine(-r - 5, 0, -r + 3, 0)
        painter.drawLine(r - 3, 0, r + 5, 0)
        painter.drawLine(0, -r - 5, 0, -r + 3)
        painter.drawLine(0, r - 3, 0, r + 5)
        if self.isSelected():
            painter.setPen(QPen(QColor(C.COLOR_BRASS_BRIGHT), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 6, r + 6)

    def to_dict(self) -> dict:
        return {"id": self.node_id, "kind": self.kind, "x": self.pos().x(), "y": self.pos().y()}

    @staticmethod
    def from_dict(d: dict) -> "FocalPointItem":
        item = FocalPointItem(kind=d.get("kind", "primary"), node_id=d.get("id"))
        item.setPos(float(d.get("x", 0)), float(d.get("y", 0)))
        return item


class MovementLineItem(InteractiveItem):
    """A polyline sketched by the artist to plan the eye's path through the
    composition. Dragging the whole item translates every point together.
    """

    def __init__(self, points: list[QPointF], line_id: str | None = None):
        super().__init__()
        self.line_id = line_id or str(uuid.uuid4())
        self._points = points or [QPointF(0, 0), QPointF(60, 0)]
        self.setZValue(9)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:
        xs = [p.x() for p in self._points]
        ys = [p.y() for p in self._points]
        return QRectF(min(xs) - 10, min(ys) - 10, max(xs) - min(xs) + 20, max(ys) - min(ys) + 20)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(C.COLOR_FOCAL_SECONDARY)
        pen = QPen(color, 2, Qt.DashLine)
        painter.setPen(pen)
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        painter.drawPath(path)
        # arrowhead at the end
        if len(self._points) >= 2:
            end = self._points[-1]
            prev = self._points[-2]
            import math
            angle = math.atan2(end.y() - prev.y(), end.x() - prev.x())
            size = 8
            p1 = QPointF(end.x() - size * math.cos(angle - 0.4), end.y() - size * math.sin(angle - 0.4))
            p2 = QPointF(end.x() - size * math.cos(angle + 0.4), end.y() - size * math.sin(angle + 0.4))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygonF([end, p1, p2]))
        if self.isSelected():
            painter.setPen(QPen(QColor(C.COLOR_BRASS), 1, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "id": self.line_id,
            "points": [[p.x() + pos.x(), p.y() + pos.y()] for p in self._points],
        }

    @staticmethod
    def from_dict(d: dict) -> "MovementLineItem":
        pts = [QPointF(x, y) for x, y in d.get("points", [[0, 0], [60, 0]])]
        return MovementLineItem(pts, line_id=d.get("id"))


class _NoteTextItem(QGraphicsTextItem):
    """The editable text child of a NoteItem. Commits the edit (pushing a
    SetNoteTextCommand via the parent NoteItem) when it loses focus, or
    when Escape/Enter ends the edit early — not per keystroke.
    """

    def __init__(self, text: str, note: "NoteItem"):
        super().__init__(text, note)
        self._note = note

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._note.commit_text_edit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)


class NoteItem(InteractiveItem):
    """A small pin marker with an attached editable text label. Used by both
    the composition and lighting layers.
    """

    def __init__(self, text: str = "Note", note_id: str | None = None, color: str = C.COLOR_BRASS):
        super().__init__()
        self.note_id = note_id or str(uuid.uuid4())
        self._color = color
        self.setZValue(11)
        self.setCursor(Qt.PointingHandCursor)

        self._text_item = _NoteTextItem(text, self)
        self._text_item.setDefaultTextColor(QColor(C.COLOR_INK))
        self._text_item.setFont(QFont(C.FONT_FAMILY_UI, 8))
        self._text_item.setPos(10, -10)
        self._text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        self._editing = False
        self._edit_baseline: str | None = None

    def text(self) -> str:
        return self._text_item.toPlainText()

    def set_text(self, text: str) -> None:
        self._text_item.setPlainText(text)

    def boundingRect(self) -> QRectF:
        return QRectF(-9, -9, 18, 18)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(self._color)
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(QBrush(color.darker(160)))
        painter.drawEllipse(QRectF(-7, -7, 14, 14))
        painter.setPen(QPen(QColor(C.COLOR_BG_DARKEST)))
        painter.setFont(QFont(C.FONT_FAMILY_UI, 8, QFont.Bold))
        painter.drawText(QRectF(-7, -7, 14, 14), Qt.AlignCenter, "i")
        if self.isSelected():
            painter.setPen(QPen(QColor(C.COLOR_BRASS_BRIGHT), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(-11, -11, 22, 22))

    def mouseDoubleClickEvent(self, event) -> None:
        if self._locked:
            event.ignore()
            return
        self.begin_text_edit()
        self._text_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self._text_item.setFocus()
        event.accept()

    def begin_text_edit(self) -> None:
        """Start (or continue) an edit session. Also used by the Properties
        panel's note text box, which drives edits without going through the
        canvas double-click flow. Safe to call repeatedly — only the first
        call in a session records the baseline to diff against on commit.
        """
        if self._edit_baseline is None:
            self._edit_baseline = self.text()

    def commit_text_edit(self) -> None:
        """Ends the current edit session (called on focus loss or Escape/
        Enter) and, if the text actually changed, pushes a single
        SetNoteTextCommand — not one per keystroke.
        """
        self._text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        if self._edit_baseline is None:
            return
        old = self._edit_baseline
        self._edit_baseline = None
        new = self.text()
        if old == new:
            return
        scene = self.scene()
        if scene is None or not hasattr(scene, "undo_stack"):
            return
        from ..canvas.undo_commands import SetNoteTextCommand
        scene.undo_stack.push(SetNoteTextCommand(self, old, new))

    def to_dict(self) -> dict:
        pos = self.pos()
        return {"id": self.note_id, "x": pos.x(), "y": pos.y(), "text": self.text()}

    @staticmethod
    def from_dict(d: dict, color: str = C.COLOR_BRASS) -> "NoteItem":
        item = NoteItem(text=d.get("text", ""), note_id=d.get("id"), color=color)
        item.setPos(float(d.get("x", 0)), float(d.get("y", 0)))
        return item


class CompositionLayerGroup(QGraphicsItemGroup):
    def __init__(self):
        super().__init__()
        self.setHandlesChildEvents(False)
        self.focal_points: list[FocalPointItem] = []
        self.movement_lines: list[MovementLineItem] = []
        self.notes: list[NoteItem] = []

    def add_existing(self, item) -> None:
        """Add an already-constructed item, routing it to the right
        bookkeeping bucket by type. This is the single choke point both the
        convenience add_X() methods below and AddItemCommand's redo() go
        through, so an undo'd delete restores an item exactly the same way
        a fresh add would place it.
        """
        if isinstance(item, FocalPointItem):
            bucket = self.focal_points
        elif isinstance(item, MovementLineItem):
            bucket = self.movement_lines
        elif isinstance(item, NoteItem):
            bucket = self.notes
        else:
            raise TypeError(f"CompositionLayerGroup cannot host {type(item).__name__}")
        self.addToGroup(item)
        if item not in bucket:
            bucket.append(item)

    def add_focal_point(self, kind: str, pos: QPointF) -> FocalPointItem:
        item = FocalPointItem(kind)
        item.setPos(pos)
        self.add_existing(item)
        return item

    def add_movement_line(self, points: list[QPointF]) -> MovementLineItem:
        item = MovementLineItem(points)
        self.add_existing(item)
        return item

    def add_note(self, pos: QPointF, text: str = "Note") -> NoteItem:
        item = NoteItem(text=text)
        item.setPos(pos)
        self.add_existing(item)
        return item

    def all_items(self):
        return [*self.focal_points, *self.movement_lines, *self.notes]

    def remove_item(self, item) -> None:
        for bucket in (self.focal_points, self.movement_lines, self.notes):
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
            "focal_points": [f.to_dict() for f in self.focal_points],
            "movement_lines": [m.to_dict() for m in self.movement_lines],
            "notes": [n.to_dict() for n in self.notes],
        }

    def load_from_dict(self, data: dict) -> None:
        self.clear()
        for f in data.get("focal_points", []):
            item = FocalPointItem.from_dict(f)
            self.addToGroup(item)
            self.focal_points.append(item)
        for m in data.get("movement_lines", []):
            item = MovementLineItem.from_dict(m)
            self.addToGroup(item)
            self.movement_lines.append(item)
        for n in data.get("notes", []):
            item = NoteItem.from_dict(n, color=C.COLOR_BRASS)
            self.addToGroup(item)
            self.notes.append(item)
