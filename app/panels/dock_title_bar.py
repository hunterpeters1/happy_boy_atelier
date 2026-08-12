"""A minimal custom title bar for QDockWidget, replacing the default
QSS-only QDockWidget::title so a pair of rivet marks — the same hardware
motif CanvasScene paints at each canvas corner — can sit at its left/right
edges. QSS alone can't add corner-specific marks without an image asset
(no pseudo-corner selectors), so this is a small real QWidget with its own
paintEvent instead, otherwise matching QDockWidget::title's existing look
(background/border-bottom/padding/font-weight/letter-spacing) verbatim so
swapping it in changes nothing but the rivets.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import constants as C

_RIVET_INSET_PX = 8.0


class DockTitleBar(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {C.COLOR_BG_DARKEST}; border-bottom: 1px solid {C.COLOR_LINE};")

        layout = QHBoxLayout(self)
        # Extra left/right margin (beyond QDockWidget::title's plain 8px)
        # clears the rivets painted in paintEvent() below.
        layout.setContentsMargins(18, 6, 18, 6)
        label = QLabel(title.upper())
        label.setStyleSheet(
            f"font-weight: 600; letter-spacing: 1px; color: {C.COLOR_INK}; background: transparent;"
        )
        layout.addWidget(label)
        layout.addStretch(1)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(C.COLOR_LINE)))
        cy = self.height() / 2.0
        painter.drawEllipse(QPointF(_RIVET_INSET_PX, cy), C.RIVET_RADIUS_PX, C.RIVET_RADIUS_PX)
        painter.drawEllipse(QPointF(self.width() - _RIVET_INSET_PX, cy), C.RIVET_RADIUS_PX, C.RIVET_RADIUS_PX)
