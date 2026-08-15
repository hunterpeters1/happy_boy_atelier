"""Composition layer: focal point markers, movement lines, and notes. The
artist places every mark by hand — nothing here is computed or suggested.
"""

from __future__ import annotations

import math
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItemGroup,
    QGraphicsTextItem,
)

from .. import constants as C
from .. import settings
from ..canvas.interactive_item import InteractiveItem
from ..canvas.point_handle import TwoPointHandle
from .reference_layer import ROTATION_SNAP_DEG
from .stacking_mixin import StackedLayerMixin

MARKER_R_PRIMARY = 11
MARKER_R_SECONDARY = 8


class FocalPointItem(InteractiveItem):
    def __init__(self, kind: str = "primary", node_id: str | None = None):
        super().__init__()
        self.node_id = node_id or str(uuid.uuid4())
        self.kind = kind  # "primary" | "secondary"
        self.setZValue(10)
        self.set_normal_cursor(Qt.PointingHandCursor)

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
        if self.is_app_selected():
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


def _smooth_polyline_path(points: list[QPointF]) -> QPainterPath:
    """The same points as a soft curve instead of hard-angled straight
    segments -- see settings.futuristic_accents_enabled(). Each interior
    point becomes a quadratic-Bezier control point steering the curve
    toward the midpoint of itself and the next point, a standard cheap
    "smooth a polyline" trick: the path still starts and ends exactly at
    the artist's own first/last points (never invents an endpoint), and
    with only 2 points there's nothing to smooth, so it's identical to a
    straight line either way.
    """
    path = QPainterPath(points[0])
    if len(points) <= 2:
        for p in points[1:]:
            path.lineTo(p)
        return path
    for i in range(1, len(points) - 1):
        control = points[i]
        next_mid = QPointF((points[i].x() + points[i + 1].x()) / 2, (points[i].y() + points[i + 1].y()) / 2)
        path.quadTo(control, next_mid)
    path.lineTo(points[-1])
    return path


class MovementLineItem(InteractiveItem):
    """A polyline sketched by the artist to plan the eye's path through the
    composition. Dragging the whole item translates every point together.
    """

    def __init__(self, points: list[QPointF], line_id: str | None = None):
        super().__init__()
        self.line_id = line_id or str(uuid.uuid4())
        self._points = points or [QPointF(0, 0), QPointF(60, 0)]
        self.setZValue(9)
        self.set_normal_cursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:
        xs = [p.x() for p in self._points]
        ys = [p.y() for p in self._points]
        return QRectF(min(xs) - 10, min(ys) - 10, max(xs) - min(xs) + 20, max(ys) - min(ys) + 20)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(C.COLOR_FOCAL_SECONDARY)
        pen = QPen(color, 2, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        if settings.futuristic_accents_enabled():
            painter.setRenderHint(QPainter.Antialiasing, True)
            path = _smooth_polyline_path(self._points)
        else:
            path = QPainterPath(self._points[0])
            for p in self._points[1:]:
                path.lineTo(p)
        painter.drawPath(path)
        # arrowhead at the end
        if len(self._points) >= 2:
            end = self._points[-1]
            prev = self._points[-2]
            angle = math.atan2(end.y() - prev.y(), end.x() - prev.x())
            size = 8
            p1 = QPointF(end.x() - size * math.cos(angle - 0.4), end.y() - size * math.sin(angle - 0.4))
            p2 = QPointF(end.x() - size * math.cos(angle + 0.4), end.y() - size * math.sin(angle + 0.4))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygonF([end, p1, p2]))
        if self.is_app_selected():
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


def _snap_to_angle(pivot: QPointF, point: QPointF, step_deg: float) -> QPointF:
    """`point` re-expressed at the same distance from `pivot` but at the
    nearest multiple of `step_deg` — MeasurementItem's Shift-drag angle
    snap, the same round(angle / step) * step pattern
    reference_layer.py's rotate-handle snap already uses for
    ROTATION_SNAP_DEG, applied to an endpoint-around-a-pivot instead of a
    whole-image rotation.
    """
    dx, dy = point.x() - pivot.x(), point.y() - pivot.y()
    distance = math.hypot(dx, dy)
    if distance == 0:
        return QPointF(point)
    snapped_deg = round(math.degrees(math.atan2(dy, dx)) / step_deg) * step_deg
    rad = math.radians(snapped_deg)
    return QPointF(pivot.x() + distance * math.cos(rad), pivot.y() + distance * math.sin(rad))


class MeasurementItem(InteractiveItem):
    """A ruler and protractor in one: a two-point segment reporting both
    its length (in the canvas's own display unit) and its angle from
    horizontal. Endpoints are independently draggable via TwoPointHandle
    (app/canvas/point_handle.py) — the same shared handle
    DirectionArrowItem (lighting_layer.py) uses, not a new interaction
    mechanism. Persists and undoes exactly like every other composition
    marker; the only thing computed here is the arithmetic display label
    itself (length/angle from the two points the artist placed) — the
    software never infers what to measure.
    """

    def __init__(self, p1: QPointF, p2: QPointF, measurement_id: str | None = None):
        super().__init__()
        self.measurement_id = measurement_id or str(uuid.uuid4())
        self._p1 = p1
        self._p2 = p2
        # Between movement lines (9) and focal points (10) -- see
        # CompositionLayerGroup._Z_BAND_MEASUREMENT below for the real
        # per-item stacking band; this constructor-time value only matters
        # before the item is ever added to a group.
        self.setZValue(9.5)
        self.set_normal_cursor(Qt.PointingHandCursor)
        self._h1 = TwoPointHandle(self, "p1", undo_text="Move measurement")
        self._h2 = TwoPointHandle(self, "p2", undo_text="Move measurement")
        self._reposition_handles()

    def color(self) -> str:
        return C.COLOR_PERSPECTIVE

    def _reposition_handles(self) -> None:
        self._h1.setPos(self._p1)
        self._h2.setPos(self._p2)

    def points(self) -> tuple[QPointF, QPointF]:
        return (QPointF(self._p1), QPointF(self._p2))

    def set_points(self, points: tuple[QPointF, QPointF]) -> None:
        self.prepareGeometryChange()
        self._p1, self._p2 = QPointF(points[0]), QPointF(points[1])
        self._reposition_handles()
        self.update()

    def set_point(self, which: str, local: QPointF) -> None:
        """Called by each endpoint's TwoPointHandle while dragging. Holding
        Shift snaps the dragged endpoint's angle around the *other*
        endpoint to the nearest ROTATION_SNAP_DEG increment — the same
        modifier/convention as rotating a reference image, applied to a
        ruler instead.
        """
        self.prepareGeometryChange()
        pivot = self._p2 if which == "p1" else self._p1
        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            local = _snap_to_angle(pivot, local, ROTATION_SNAP_DEG)
        if which == "p1":
            self._p1 = local
        else:
            self._p2 = local
        self._reposition_handles()
        self.update()

    def _display_unit(self) -> str:
        scene = self.scene()
        if scene is not None and hasattr(scene, "canvas_spec"):
            return scene.canvas_spec.unit
        return "in"

    def length_and_angle(self) -> tuple[float, float]:
        """(length in the canvas's own display unit, angle from horizontal
        in degrees, positive = counterclockwise) — pure arithmetic on the
        two points the artist placed.
        """
        dx = self._p2.x() - self._p1.x()
        dy = self._p2.y() - self._p1.y()
        length_in = math.hypot(dx, dy) / C.SCENE_PX_PER_INCH
        length = C.from_inches(length_in, self._display_unit())
        angle = math.degrees(math.atan2(-dy, dx))
        return length, angle

    def display_label(self) -> str:
        length, angle = self.length_and_angle()
        return f"{length:.1f} {self._display_unit()} · {angle:.0f}°"

    def boundingRect(self) -> QRectF:
        xs = [self._p1.x(), self._p2.x()]
        ys = [self._p1.y(), self._p2.y()]
        pad = 24  # room for the end ticks and the label past either point
        return QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(self.color())
        painter.setPen(QPen(color, 1.5))
        painter.drawLine(self._p1, self._p2)
        # Ruler-style perpendicular ticks at each end -- visually distinct
        # from a plain MovementLineItem segment at a glance.
        dx, dy = self._p2.x() - self._p1.x(), self._p2.y() - self._p1.y()
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length * 6, dx / length * 6
        painter.drawLine(QPointF(self._p1.x() - nx, self._p1.y() - ny), QPointF(self._p1.x() + nx, self._p1.y() + ny))
        painter.drawLine(QPointF(self._p2.x() - nx, self._p2.y() - ny), QPointF(self._p2.x() + nx, self._p2.y() + ny))
        painter.setFont(QFont(C.FONT_FAMILY_MONO, 8))
        mid = QPointF((self._p1.x() + self._p2.x()) / 2, (self._p1.y() + self._p2.y()) / 2)
        painter.drawText(mid + QPointF(6, -6), self.display_label())
        if self.is_app_selected():
            painter.setPen(QPen(QColor(C.COLOR_BRASS), 1, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "id": self.measurement_id,
            "x1": self._p1.x() + pos.x(), "y1": self._p1.y() + pos.y(),
            "x2": self._p2.x() + pos.x(), "y2": self._p2.y() + pos.y(),
        }

    @staticmethod
    def from_dict(d: dict) -> "MeasurementItem":
        return MeasurementItem(
            QPointF(float(d.get("x1", 0)), float(d.get("y1", 0))),
            QPointF(float(d.get("x2", 100)), float(d.get("y2", 0))),
            measurement_id=d.get("id"),
        )


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
        self.set_normal_cursor(Qt.PointingHandCursor)

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
        if self.is_app_selected():
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


class CompositionLayerGroup(StackedLayerMixin, QGraphicsItemGroup):
    """can_move_forward()/can_move_backward()/move_item_forward()/
    move_item_backward()/remove_item()/index_of() come from
    StackedLayerMixin (stacking_mixin.py) — this class supplies
    _bucket_for() and _reassign_z() below.
    """

    # Stacking bands, widest gap first: movement lines always print under
    # measurements, which always print under focal points, which always
    # print under notes (so a note's "i" stays legible even parked on top
    # of a marker) — that hierarchy is fixed, matching each item class's
    # own historical setZValue() call. What the Project Panel's up/down
    # buttons control is the order *within* one band (e.g. which of two
    # overlapping notes prints on top of the other) — see _reassign_z().
    _Z_BAND_MOVEMENT = 9.0
    _Z_BAND_MEASUREMENT = 9.5
    _Z_BAND_FOCAL = 10.0
    _Z_BAND_NOTE = 11.0
    _Z_STEP = 0.01

    def __init__(self):
        super().__init__()
        self.setHandlesChildEvents(False)
        self.focal_points: list[FocalPointItem] = []
        self.movement_lines: list[MovementLineItem] = []
        self.measurements: list[MeasurementItem] = []
        self.notes: list[NoteItem] = []

    def add_existing(self, item, index: int | None = None) -> None:
        """Add an already-constructed item, routing it to the right
        bookkeeping bucket by type (via _bucket_for(), which is
        type-based so it works before `item` is in any bucket). This is
        the single choke point both the convenience add_X() methods
        below and AddItemCommand's redo() go through, so an undo'd
        delete restores an item exactly the same way a fresh add would
        place it. `index`: insert at this position within the bucket
        instead of appending — used by DeleteItemCommand.undo()
        (undo_commands.py) to restore an item's exact original stacking
        position.
        """
        bucket = self._bucket_for(item)
        if bucket is None:
            raise TypeError(f"CompositionLayerGroup cannot host {type(item).__name__}")
        self.addToGroup(item)
        if item not in bucket:
            if index is None or index >= len(bucket):
                bucket.append(item)
            else:
                bucket.insert(index, item)
        self._reassign_z()

    def _bucket_for(self, item):
        if isinstance(item, FocalPointItem):
            return self.focal_points
        if isinstance(item, MovementLineItem):
            return self.movement_lines
        if isinstance(item, MeasurementItem):
            return self.measurements
        if isinstance(item, NoteItem):
            return self.notes
        return None

    def _reassign_z(self) -> None:
        for i, item in enumerate(self.movement_lines):
            item.setZValue(self._Z_BAND_MOVEMENT + i * self._Z_STEP)
        for i, item in enumerate(self.measurements):
            item.setZValue(self._Z_BAND_MEASUREMENT + i * self._Z_STEP)
        for i, item in enumerate(self.focal_points):
            item.setZValue(self._Z_BAND_FOCAL + i * self._Z_STEP)
        for i, item in enumerate(self.notes):
            item.setZValue(self._Z_BAND_NOTE + i * self._Z_STEP)

    def add_focal_point(self, kind: str, pos: QPointF) -> FocalPointItem:
        item = FocalPointItem(kind)
        item.setPos(pos)
        self.add_existing(item)
        return item

    def add_note(self, pos: QPointF, text: str = "Note") -> NoteItem:
        item = NoteItem(text=text)
        item.setPos(pos)
        self.add_existing(item)
        return item

    def all_items(self):
        return [*self.focal_points, *self.movement_lines, *self.measurements, *self.notes]

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
            "measurements": [m.to_dict() for m in self.measurements],
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
        for m in data.get("measurements", []):
            item = MeasurementItem.from_dict(m)
            self.addToGroup(item)
            self.measurements.append(item)
        for n in data.get("notes", []):
            item = NoteItem.from_dict(n, color=C.COLOR_BRASS)
            self.addToGroup(item)
            self.notes.append(item)
        self._reassign_z()
