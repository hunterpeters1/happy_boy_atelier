"""The drafting viewport: precise zoom/pan and a physical-unit ruler drawn
along the canvas edges so the artist always sees real dimensions.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsView

from .. import constants as C

ZOOM_STEP = 1.15
MIN_ZOOM = 0.05
MAX_ZOOM = 24.0


class CanvasView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setBackgroundBrush(QColor(C.COLOR_BG_DARKEST))
        self._zoom = 1.0
        self._space_panning = False
        self._middle_panning = False
        self._show_ruler = True
        self.setMouseTracking(True)

    # -- zoom -----------------------------------------------------------
    def current_zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float, anchor_view_pos=None) -> None:
        factor = max(MIN_ZOOM, min(MAX_ZOOM, factor))
        ratio = factor / self._zoom
        if ratio == 1.0:
            return
        self.scale(ratio, ratio)
        self._zoom = factor
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / ZOOM_STEP)

    def zoom_reset(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        self.zoom_changed.emit(self._zoom)

    def fit_canvas(self, rect: QRectF, margin: float = 40) -> None:
        if rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-margin, -margin, margin, margin), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event):
        # Ctrl/Cmd+scroll zooms — the convention every other creative tool
        # already trains into a painter's hand. Plain scroll pans vertically
        # and Shift+scroll pans horizontally, matching a native scroll area
        # instead of the reverse (plain wheel = zoom) this view used to use.
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return
        if event.modifiers() & Qt.ControlModifier:
            self.set_zoom(self._zoom * (ZOOM_STEP if delta > 0 else 1 / ZOOM_STEP))
            return
        bar = self.horizontalScrollBar() if event.modifiers() & Qt.ShiftModifier else self.verticalScrollBar()
        bar.setValue(bar.value() - delta)

    # -- pan --------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(QCursor(Qt.OpenHandCursor))
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            scene = self.scene()
            if scene is not None and hasattr(scene, "delete_selected_items"):
                scene.delete_selected_items()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = False
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.unsetCursor()
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._middle_panning = True
            self.setCursor(QCursor(Qt.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.RubberBandDrag if not self._space_panning else QGraphicsView.ScrollHandDrag)
            self.unsetCursor()

    # -- ruler overlay ----------------------------------------------------
    def set_ruler_visible(self, visible: bool) -> None:
        self._show_ruler = visible
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if not self._show_ruler:
            return
        canvas_rect = getattr(self.scene(), "canvas_rect", None)
        if canvas_rect is None:
            return
        canvas_rect = canvas_rect()
        painter.save()
        painter.resetTransform()
        pen = QPen(QColor(C.COLOR_BRASS))
        pen.setWidth(1)
        painter.setPen(pen)
        font = QFont(C.FONT_FAMILY_MONO, 7)
        painter.setFont(font)

        px_per_in = C.SCENE_PX_PER_INCH
        top_left_view = self.mapFromScene(canvas_rect.topLeft())
        top_right_view = self.mapFromScene(canvas_rect.topRight())
        bottom_left_view = self.mapFromScene(canvas_rect.bottomLeft())

        # top ruler ticks (every inch)
        width_in = canvas_rect.width() / px_per_in
        for i in range(int(width_in) + 1):
            scene_x = canvas_rect.left() + i * px_per_in
            view_pt = self.mapFromScene(QPointF(scene_x, canvas_rect.top()))
            painter.drawLine(view_pt.x(), top_left_view.y() - 8, view_pt.x(), top_left_view.y())
            if i % 1 == 0:
                painter.drawText(view_pt.x() + 2, top_left_view.y() - 10, str(i))

        height_in = canvas_rect.height() / px_per_in
        for i in range(int(height_in) + 1):
            scene_y = canvas_rect.top() + i * px_per_in
            view_pt = self.mapFromScene(QPointF(canvas_rect.left(), scene_y))
            painter.drawLine(top_left_view.x() - 8, view_pt.y(), top_left_view.x(), view_pt.y())
            if i % 1 == 0:
                painter.drawText(top_left_view.x() - 26, view_pt.y() - 2, str(i))
        painter.restore()
