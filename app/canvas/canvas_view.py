"""The drafting viewport: precise zoom/pan and a physical-unit ruler drawn
along the canvas edges so the artist always sees real dimensions.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsView, QMenu

from .. import constants as C
from .. import icons

ZOOM_STEP = 1.15
MIN_ZOOM = 0.05
MAX_ZOOM = 24.0
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class CanvasView(QGraphicsView):
    zoom_changed = Signal(float)
    # Local image file paths dropped from the OS onto the canvas — there
    # was previously no way to import a reference except the file dialog.
    files_dropped = Signal(list)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        # SmartViewportUpdate (not FullViewportUpdate): repaint only the
        # region that actually changed each frame instead of the whole
        # viewport on every drag/resize tick. drawForeground()'s ruler
        # doesn't restrict itself to the passed `rect`, but Qt clips the
        # painter to the dirty region during a partial update regardless,
        # so this is a safe, purely-perf change — nothing here relied on
        # full-viewport repaints for correctness.
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QColor(C.COLOR_CANVAS_BG))
        self._zoom = 1.0
        self._space_panning = False
        self._middle_panning = False
        self._tool_armed = False
        self._show_ruler = True
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

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

    def fit_canvas(self, rect: QRectF, margin: float = 40) -> None:
        if rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-margin, -margin, margin, margin), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event):
        # Plain wheel zooms. Panning stays available via the scrollbars
        # and space+drag/middle-drag — no wheel modifier does anything
        # special.
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return
        self.set_zoom(self._zoom * (ZOOM_STEP if delta > 0 else 1 / ZOOM_STEP))

    # -- pan --------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._refresh_cursor()
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
            self._refresh_cursor()
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._middle_panning = True
            self._refresh_cursor()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MiddleButton:
            self._middle_panning = False
            self.setDragMode(QGraphicsView.RubberBandDrag if not self._space_panning else QGraphicsView.ScrollHandDrag)
            self._refresh_cursor()

    # -- tool-armed cursor --------------------------------------------------
    def set_tool_armed(self, armed: bool) -> None:
        """Called by CanvasScene.set_active_tool() (the single choke point
        for every tool activation/deactivation) so a crosshair shows
        while a placement tool (focal point, note, light source, etc.) is
        armed — previously the only cue was the status bar text and a
        right-click "Cancel Tool" entry, with no persistent visual cue
        that clicking anywhere would place something.
        """
        self._tool_armed = armed
        self._refresh_cursor()

    def _refresh_cursor(self) -> None:
        """Single place that decides the view's cursor, by priority:
        active panning (space or middle-button drag) > an armed
        placement tool > the plain default. Centralized rather than each
        of the four call sites above setting/unsetting the cursor
        directly, which would otherwise have a real bug: releasing
        space-pan while a tool was still armed would revert to the plain
        arrow instead of back to the crosshair.
        """
        if self._space_panning:
            self.setCursor(QCursor(Qt.OpenHandCursor))
        elif self._middle_panning:
            self.setCursor(QCursor(Qt.ClosedHandCursor))
        elif self._tool_armed:
            self.setCursor(QCursor(Qt.CrossCursor))
        else:
            self.unsetCursor()

    # -- OS drag-and-drop import ------------------------------------------
    @staticmethod
    def _image_paths(mime) -> list[str]:
        if not mime.hasUrls():
            return []
        return [
            url.toLocalFile() for url in mime.urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(_IMAGE_EXTENSIONS)
        ]

    def dragEnterEvent(self, event):
        if self._image_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._image_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = self._image_paths(event.mimeData())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # -- context menu -------------------------------------------------------
    def _build_context_menu(self, scene_pos: QPointF) -> QMenu | None:
        """Construct (but don't show) the right-click menu for a scene
        position — split out from contextMenuEvent so the menu's contents
        can be tested without ever calling the blocking QMenu.exec().
        """
        scene = self.scene()
        if scene is None or not hasattr(scene, "interactive_item_at"):
            return None
        item = scene.interactive_item_at(scene_pos, self.transform())
        menu = QMenu(self)
        if item is not None:
            if hasattr(scene, "set_selection"):
                scene.set_selection([item])
            locked = item.is_locked() if hasattr(item, "is_locked") else False
            if hasattr(scene, "delete_selected_items"):
                delete_action = menu.addAction(icons.icon("delete"), "Delete")
                delete_action.setEnabled(not locked)
                delete_action.triggered.connect(scene.delete_selected_items)
            if hasattr(item, "set_locked"):
                lock_action = menu.addAction(
                    icons.icon("unlock" if locked else "lock"), "Unlock" if locked else "Lock"
                )
                lock_action.triggered.connect(lambda: item.set_locked(not locked))
            # Crop is direct manipulation via edge handles on the canvas —
            # no context menu entry needed (the artist just grabs an edge
            # handle when the image has a crop applied).
            # -- PureRef-inspired quick transforms (reference images only) --
            if hasattr(item, "flip_horizontal"):
                menu.addSeparator()
                flip_h_action = menu.addAction("Flip Horizontal")
                flip_h_action.triggered.connect(item.flip_horizontal)
                flip_v_action = menu.addAction("Flip Vertical")
                flip_v_action.triggered.connect(item.flip_vertical)
                menu.addSeparator()
                magnify_action = menu.addAction("Magnify 2×")
                magnify_action.triggered.connect(item.magnify)
                demag_action = menu.addAction("Shrink to 50%")
                demag_action.triggered.connect(item.demagnify)
        else:
            fit_action = menu.addAction(icons.icon("fit"), "Fit Canvas")
            fit_action.triggered.connect(lambda: self.fit_canvas(scene.canvas_rect()))
            if hasattr(scene, "active_tool") and scene.active_tool():
                menu.addSeparator()
                cancel_action = menu.addAction("Cancel Tool (Esc)")
                cancel_action.triggered.connect(lambda: scene.set_active_tool(None))
        return menu

    def contextMenuEvent(self, event):
        menu = self._build_context_menu(self.mapToScene(event.pos()))
        if menu is None:
            super().contextMenuEvent(event)
            return
        if not menu.isEmpty():
            menu.exec(event.globalPos())

    # -- theme -------------------------------------------------------------
    def refresh_theme_colors(self) -> None:
        """The background brush is a QBrush set once at construction, not
        something QPalette/stylesheet changes touch on their own — call
        this after a live theme switch (see MainWindow._set_theme()) so
        the void beyond the scene's padded rect matches CanvasScene.
        drawBackground()'s freshly-repainted COLOR_CANVAS_BG immediately,
        instead of only after the next restart.
        """
        scene = self.scene()
        bg = getattr(scene, "_bg_color", C.COLOR_CANVAS_BG) if scene else C.COLOR_CANVAS_BG
        self.setBackgroundBrush(QColor(bg))
        self.viewport().update()

    def set_desk_color(self, color: str) -> None:
        """Update the view's background to match a new desk color."""
        self.setBackgroundBrush(QColor(color))
        self.viewport().update()

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
        bottom_right_view = self.mapFromScene(canvas_rect.bottomRight())

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

        self._draw_trim_marks(painter, top_left_view, top_right_view, bottom_left_view, bottom_right_view)
        self._draw_dimension_callout(painter, bottom_right_view)
        painter.restore()

    def _draw_trim_marks(self, painter: QPainter, top_left, top_right, bottom_left, bottom_right) -> None:
        """Short L-shaped ticks just outside each canvas corner, the same
        convention print-production sheets and technical drawings use to
        mark trim boundaries — distinct from the ruler's own tick marks
        (those read the surface; these mark it as a physical object being
        prepared for output, this app's actual premise). Same brass pen
        already set up by the caller; no new state.
        """
        gap, length = 3, 6
        for corner, (dx, dy) in (
            (top_left, (-1, -1)), (top_right, (1, -1)),
            (bottom_left, (-1, 1)), (bottom_right, (1, 1)),
        ):
            painter.drawLine(corner.x() + dx * gap, corner.y(), corner.x() + dx * (gap + length), corner.y())
            painter.drawLine(corner.x(), corner.y() + dy * gap, corner.x(), corner.y() + dy * (gap + length))

    def _draw_dimension_callout(self, painter: QPainter, bottom_right_view) -> None:
        """A live monospace readout of the canvas's real physical
        dimensions, in whichever unit the artist chose at New Painting —
        turns the canvas from "a rectangle" into a labeled technical
        artifact. Anchored off the bottom-right corner, clear of the
        ruler's own tick labels along the top/left edges.
        """
        spec = getattr(self.scene(), "canvas_spec", None)
        if spec is None:
            return
        label = f"{spec.width:.3f} × {spec.height:.3f} {spec.unit.upper()}"
        metrics = painter.fontMetrics()
        x = bottom_right_view.x() - metrics.horizontalAdvance(label)
        y = bottom_right_view.y() + metrics.ascent() + 10
        painter.drawText(x, y, label)
