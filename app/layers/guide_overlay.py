"""Composition guide overlays: rule of thirds and golden ratio. Deliberately
just two toggles, non-interactive, top of the stack — per spec, avoid
excessive guides.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsObject

from .. import constants as C

GOLDEN_SECTION = 0.382  # 1 - 1/phi, phi ~= 1.618


class RuleOfThirdsOverlay(QGraphicsObject):
    def __init__(self, canvas_rect: QRectF):
        super().__init__()
        self._rect = canvas_rect
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(20)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = rect

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pen = QPen(QColor(C.COLOR_GUIDE), 1, Qt.DashLine)
        painter.setPen(pen)
        r = self._rect
        for i in (1, 2):
            x = r.left() + r.width() * i / 3
            painter.drawLine(x, r.top(), x, r.bottom())
            y = r.top() + r.height() * i / 3
            painter.drawLine(r.left(), y, r.right(), y)


class GoldenRatioOverlay(QGraphicsObject):
    def __init__(self, canvas_rect: QRectF):
        super().__init__()
        self._rect = canvas_rect
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(21)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = rect

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pen = QPen(QColor(C.COLOR_COPPER), 1, Qt.DashDotLine)
        painter.setPen(pen)
        r = self._rect
        for frac in (GOLDEN_SECTION, 1 - GOLDEN_SECTION):
            x = r.left() + r.width() * frac
            painter.drawLine(x, r.top(), x, r.bottom())
            y = r.top() + r.height() * frac
            painter.drawLine(r.left(), y, r.right(), y)


class GuidesLayerGroup(QGraphicsItemGroup):
    def __init__(self, canvas_rect: QRectF):
        super().__init__()
        self.setHandlesChildEvents(False)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.thirds = RuleOfThirdsOverlay(canvas_rect)
        self.golden = GoldenRatioOverlay(canvas_rect)
        self.thirds.setVisible(False)
        self.golden.setVisible(False)
        self.addToGroup(self.thirds)
        self.addToGroup(self.golden)

    def set_rule_of_thirds(self, on: bool) -> None:
        self.thirds.setVisible(on)

    def set_golden_ratio(self, on: bool) -> None:
        self.golden.setVisible(on)

    def to_dict(self) -> dict:
        return {"rule_of_thirds": self.thirds.isVisible(), "golden_ratio": self.golden.isVisible()}

    def load_from_dict(self, data: dict) -> None:
        self.set_rule_of_thirds(bool(data.get("rule_of_thirds", False)))
        self.set_golden_ratio(bool(data.get("golden_ratio", False)))
