"""Perspective layer: horizon line, vanishing points, and 1/2/3-point grid
overlays. The artist places and moves every point; the grid is pure
geometry derived from those points, never an artistic suggestion.
"""

from __future__ import annotations

import math
import uuid

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsItemGroup, QGraphicsObject

from .. import constants as C
from ..constants import PerspectiveMode
from ..canvas.interactive_item import InteractiveItem

VP_MARK = 9


def clip_ray_to_rect(point: QPointF, angle_deg: float, rect: QRectF) -> tuple[QPointF, QPointF] | None:
    """Return the segment of the infinite line through `point` at angle
    `angle_deg` that lies inside `rect`, or None if it misses entirely.
    """
    dx = math.cos(math.radians(angle_deg))
    dy = math.sin(math.radians(angle_deg))
    far = max(rect.width(), rect.height()) * 4 + 1
    p1 = QPointF(point.x() - dx * far, point.y() - dy * far)
    p2 = QPointF(point.x() + dx * far, point.y() + dy * far)
    ray = QLineF(p1, p2)

    edges = [
        QLineF(rect.topLeft(), rect.topRight()),
        QLineF(rect.topRight(), rect.bottomRight()),
        QLineF(rect.bottomRight(), rect.bottomLeft()),
        QLineF(rect.bottomLeft(), rect.topLeft()),
    ]
    hits = []
    for edge in edges:
        itype, result_point = ray.intersects(edge)
        if itype == QLineF.BoundedIntersection:
            hits.append(result_point)
    if len(hits) < 2:
        return None
    best = (hits[0], hits[1])
    best_dist = QLineF(hits[0], hits[1]).length()
    for i in range(len(hits)):
        for j in range(i + 1, len(hits)):
            d = QLineF(hits[i], hits[j]).length()
            if d > best_dist:
                best_dist = d
                best = (hits[i], hits[j])
    return best


GRID_LINE_WIDTH_DEFAULT = 2.0
GRID_LINE_WIDTH_RANGE = (1.0, 8.0)


class HorizonLineItem(InteractiveItem):
    def __init__(self, canvas_w: float):
        super().__init__()
        self._canvas_w = canvas_w
        self._line_width = GRID_LINE_WIDTH_DEFAULT
        self.setCursor(Qt.SizeVerCursor)
        self.setZValue(5)

    def set_canvas_width(self, w: float) -> None:
        self.prepareGeometryChange()
        self._canvas_w = w

    def set_line_width(self, width: float) -> None:
        self._line_width = width
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -8, self._canvas_w + 40, 16)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return QPointF(0, value.y())
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(C.COLOR_PERSPECTIVE)
        pen = QPen(color, self._line_width, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(-20, 0), QPointF(self._canvas_w + 20, 0))
        painter.setFont(QFont(C.FONT_FAMILY_MONO, 7))
        painter.drawText(QPointF(-18, -4), "HORIZON")

    def to_dict(self) -> dict:
        return {"y": self.pos().y()}


class VanishingPointItem(InteractiveItem):
    def __init__(self, label: str, vp_id: str | None = None):
        super().__init__()
        self.vp_id = vp_id or str(uuid.uuid4())
        self.label = label
        self._line_width = GRID_LINE_WIDTH_DEFAULT
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(6)

    def set_line_width(self, width: float) -> None:
        self._line_width = width
        self.update()

    def boundingRect(self) -> QRectF:
        r = VP_MARK + 12
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(C.COLOR_PERSPECTIVE)
        pen = QPen(color, self._line_width)
        painter.setPen(pen)
        r = VP_MARK
        painter.drawLine(-r, -r, r, r)
        painter.drawLine(-r, r, r, -r)
        painter.drawEllipse(QPointF(0, 0), r + 3, r + 3)
        painter.setFont(QFont(C.FONT_FAMILY_MONO, 7))
        painter.drawText(QPointF(r + 4, 4), self.label)

    def to_dict(self) -> dict:
        return {"id": self.vp_id, "x": self.pos().x(), "y": self.pos().y(), "label": self.label}


class PerspectiveGridItem(QGraphicsObject):
    """Draws N evenly-angled construction lines through every vanishing
    point, clipped to the canvas rect. Recomputed live from current VP/
    horizon positions — nothing is cached or inferred.
    """

    def __init__(self, canvas_rect: QRectF, get_vps, line_count: int = 12,
                 line_width: float = GRID_LINE_WIDTH_DEFAULT):
        super().__init__()
        self._canvas_rect = canvas_rect
        self._get_vps = get_vps
        self.line_count = line_count
        self.line_width = line_width
        self.setZValue(4)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_line_count(self, n: int) -> None:
        self.line_count = max(2, n)
        self.update()

    def set_line_width(self, width: float) -> None:
        self.line_width = max(GRID_LINE_WIDTH_RANGE[0], min(GRID_LINE_WIDTH_RANGE[1], width))
        self.update()

    def boundingRect(self) -> QRectF:
        return self._canvas_rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(C.COLOR_PERSPECTIVE)
        color.setAlpha(160)
        pen = QPen(color, self.line_width)
        painter.setPen(pen)
        vps = self._get_vps()
        step = 180.0 / max(2, self.line_count)
        for vp in vps:
            for i in range(self.line_count):
                angle = i * step
                seg = clip_ray_to_rect(vp, angle, self._canvas_rect)
                if seg:
                    painter.drawLine(seg[0], seg[1])


class PerspectiveLayerGroup(QGraphicsItemGroup):
    def __init__(self, canvas_rect: QRectF):
        super().__init__()
        self.setHandlesChildEvents(False)
        self._canvas_rect = canvas_rect
        self.mode = PerspectiveMode.ONE_POINT
        self.horizon = HorizonLineItem(canvas_rect.width())
        self.horizon.setPos(0, canvas_rect.height() / 2)
        self.vps: list[VanishingPointItem] = []
        self._line_width = GRID_LINE_WIDTH_DEFAULT
        self.grid = PerspectiveGridItem(canvas_rect, self._vp_positions, line_count=12,
                                         line_width=self._line_width)
        self._opacity = 0.85
        self._locked = False

        self.addToGroup(self.horizon)
        self.addToGroup(self.grid)
        self.horizon.yChanged.connect(self.grid.update)
        self.set_mode(PerspectiveMode.ONE_POINT)
        # Visible by default so it matches the "Visible" checkbox state in
        # the Layers panel; the artist can hide it with one click.

    def _vp_positions(self) -> list[QPointF]:
        return [vp.pos() for vp in self.vps]

    def snapshot_state(self):
        """(mode, horizon_y, vp_positions) for the *current* mode — used by
        SetPerspectiveModeCommand to capture undo state before switching.
        """
        return (self.mode, self.horizon.pos().y(), self._vp_positions())

    def set_mode(self, mode: PerspectiveMode) -> None:
        self.mode = mode
        for vp in self.vps:
            self.removeFromGroup(vp)
            if vp.scene():
                vp.scene().removeItem(vp)
        self.vps = []

        w, h = self._canvas_rect.width(), self._canvas_rect.height()
        hy = self.horizon.pos().y()
        if mode == PerspectiveMode.ONE_POINT:
            positions = [("VP1", QPointF(w / 2, hy))]
        elif mode == PerspectiveMode.TWO_POINT:
            positions = [("VP1", QPointF(-w * 0.15, hy)), ("VP2", QPointF(w * 1.15, hy))]
        else:
            positions = [
                ("VP1", QPointF(-w * 0.15, hy)),
                ("VP2", QPointF(w * 1.15, hy)),
                ("VP3", QPointF(w / 2, h * 1.4)),
            ]
        for label, pos in positions:
            vp = VanishingPointItem(label)
            vp.setPos(pos)
            vp.set_line_width(self._line_width + 0.5)
            vp.xChanged.connect(self.grid.update)
            vp.yChanged.connect(self.grid.update)
            self.addToGroup(vp)
            self.vps.append(vp)
        self.grid.update()

    def set_grid_spacing(self, line_count: int) -> None:
        self.grid.set_line_count(line_count)

    def set_line_width(self, width: float) -> None:
        self._line_width = max(GRID_LINE_WIDTH_RANGE[0], min(GRID_LINE_WIDTH_RANGE[1], width))
        self.grid.set_line_width(self._line_width)
        self.horizon.set_line_width(self._line_width + 0.5)
        for vp in self.vps:
            vp.set_line_width(self._line_width + 0.5)

    def set_layer_opacity(self, value: float) -> None:
        self._opacity = value
        self.setOpacity(value)

    def set_layer_locked(self, locked: bool) -> None:
        self._locked = locked
        for item in (self.horizon, *self.vps):
            item.set_locked(locked)

    def set_layer_visible(self, visible: bool) -> None:
        self.setVisible(visible)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "horizon_y": self.horizon.pos().y(),
            "vanishing_points": [[vp.pos().x(), vp.pos().y()] for vp in self.vps],
            "grid_spacing": self.grid.line_count,
            "line_width": self._line_width,
            "opacity": self._opacity,
            "visible": self.isVisible(),
            "locked": self._locked,
        }

    def load_from_dict(self, data: dict) -> None:
        mode = PerspectiveMode(data.get("mode", PerspectiveMode.ONE_POINT.value))
        self.horizon.setPos(0, float(data.get("horizon_y", self._canvas_rect.height() / 2)))
        self.set_mode(mode)
        vp_coords = data.get("vanishing_points", [])
        for vp, coord in zip(self.vps, vp_coords):
            vp.setPos(coord[0], coord[1])
        self.set_grid_spacing(int(data.get("grid_spacing", 12)))
        self.set_line_width(float(data.get("line_width", GRID_LINE_WIDTH_DEFAULT)))
        self.set_layer_opacity(float(data.get("opacity", 0.85)))
        self.set_layer_visible(bool(data.get("visible", True)))
        self.set_layer_locked(bool(data.get("locked", False)))
