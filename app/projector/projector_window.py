"""Projector mode: a fullscreen, physically-independent view of the
reference layer meant to be thrown onto the primary canvas with a
projector. It renders a snapshot of the drafting scene rather than sharing
live Qt items with the editor, so its own zoom/pan/rotation/flip/opacity
never disturb the working project — exactly the separation the
`projector_state` field in the .atelier format is meant to capture.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import constants as C


class _ProjectorCanvas(QWidget):
    state_changed = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._image: QImage | None = None
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._rotation = 0.0
        self._flip_h = False
        self._opacity = 1.0
        self._locked = False
        self._show_guides = False
        self._drag_start = None
        self._pan_start = None
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.refresh_snapshot()

    # -- snapshot rendering -------------------------------------------
    def refresh_snapshot(self) -> None:
        comp_v = self.scene.composition_layer.isVisible()
        persp_v = self.scene.perspective_layer.isVisible()
        light_v = self.scene.lighting_layer.isVisible()
        guides_v = self.scene.guides_layer.isVisible()
        self.scene.composition_layer.setVisible(False)
        self.scene.perspective_layer.setVisible(False)
        self.scene.lighting_layer.setVisible(False)
        self.scene.guides_layer.setVisible(self._show_guides)

        rect = self.scene.canvas_rect()
        w, h = max(1, int(rect.width())), max(1, int(rect.height()))
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.scene.render(painter, QRectF(0, 0, w, h), rect)
        painter.end()
        self._image = img

        self.scene.composition_layer.setVisible(comp_v)
        self.scene.perspective_layer.setVisible(persp_v)
        self.scene.lighting_layer.setVisible(light_v)
        self.scene.guides_layer.setVisible(guides_v)
        self.update()

    # -- state ----------------------------------------------------------
    def get_state(self) -> dict:
        return {
            "opacity": self._opacity, "zoom": self._zoom,
            "pan": [self._pan.x(), self._pan.y()],
            "rotation": self._rotation, "flip_h": self._flip_h, "locked": self._locked,
        }

    def apply_state(self, state: dict) -> None:
        self._opacity = float(state.get("opacity", 1.0))
        self._zoom = float(state.get("zoom", 1.0))
        pan = state.get("pan", [0, 0])
        self._pan = QPointF(pan[0], pan[1])
        self._rotation = float(state.get("rotation", 0.0))
        self._flip_h = bool(state.get("flip_h", False))
        self._locked = bool(state.get("locked", False))
        self.update()

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.setCursor(Qt.ArrowCursor if locked else Qt.OpenHandCursor)

    def set_opacity(self, value: float) -> None:
        self._opacity = value
        self.update()

    def set_show_guides(self, on: bool) -> None:
        self._show_guides = on
        self.refresh_snapshot()

    def nudge_zoom(self, factor: float) -> None:
        if self._locked:
            return
        self._zoom = max(0.05, min(20.0, self._zoom * factor))
        self.update()

    def nudge_rotation(self, degrees: float) -> None:
        if self._locked:
            return
        self._rotation += degrees
        self.update()

    def toggle_flip(self) -> None:
        if self._locked:
            return
        self._flip_h = not self._flip_h
        self.update()

    def reset_transform(self) -> None:
        if self._locked:
            return
        self._zoom, self._rotation, self._flip_h = 1.0, 0.0, False
        self._pan = QPointF(0, 0)
        self.update()

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("black"))
        if self._image is None:
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self._opacity)
        painter.save()
        center = self.rect().center()
        painter.translate(center.x() + self._pan.x(), center.y() + self._pan.y())
        painter.rotate(self._rotation)
        sx = -self._zoom if self._flip_h else self._zoom
        painter.scale(sx, self._zoom)
        w, h = self._image.width(), self._image.height()
        painter.drawImage(QRectF(-w / 2, -h / 2, w, h), self._image)
        painter.restore()

    # -- interaction --------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if not self._locked and event.button() == Qt.LeftButton:
            self._drag_start = event.position()
            self._pan_start = QPointF(self._pan)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            delta = event.position() - self._drag_start
            self._pan = self._pan_start + QPointF(delta.x(), delta.y())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        self.setCursor(Qt.ArrowCursor if self._locked else Qt.OpenHandCursor)

    def wheelEvent(self, event) -> None:
        if self._locked:
            return
        delta = event.angleDelta().y()
        self.nudge_zoom(1.1 if delta > 0 else 1 / 1.1)


class ProjectorWindow(QWidget):
    closed = Signal()

    def __init__(self, scene, initial_state: dict | None = None, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Happy Boy Atelier — Projector Mode")
        self.setStyleSheet(f"background:{C.COLOR_BG_DARKEST};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.canvas = _ProjectorCanvas(scene)
        if initial_state:
            self.canvas.apply_state(initial_state)
        layout.addWidget(self.canvas, 1)

        self.toolbar = self._build_toolbar()
        layout.addWidget(self.toolbar)

        self.showFullScreen()

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background: {C.COLOR_BG_DARKEST}; border-top: 1px solid {C.COLOR_LINE}; }}"
            f"QLabel {{ color: {C.COLOR_INK}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 10, 6)

        row.addWidget(QLabel("Opacity"))
        opacity = QSlider(Qt.Horizontal)
        opacity.setRange(10, 100)
        opacity.setValue(int(self.canvas._opacity * 100))
        opacity.setMaximumWidth(140)
        opacity.valueChanged.connect(lambda v: self.canvas.set_opacity(v / 100))
        row.addWidget(opacity)

        zoom_out = QPushButton("Zoom −")
        zoom_out.clicked.connect(lambda: self.canvas.nudge_zoom(1 / 1.15))
        zoom_in = QPushButton("Zoom +")
        zoom_in.clicked.connect(lambda: self.canvas.nudge_zoom(1.15))
        row.addWidget(zoom_out)
        row.addWidget(zoom_in)

        rot_l = QPushButton("Rotate ↺")
        rot_l.clicked.connect(lambda: self.canvas.nudge_rotation(-1.0))
        rot_r = QPushButton("Rotate ↻")
        rot_r.clicked.connect(lambda: self.canvas.nudge_rotation(1.0))
        row.addWidget(rot_l)
        row.addWidget(rot_r)

        flip_btn = QPushButton("Flip Horizontal")
        flip_btn.clicked.connect(self.canvas.toggle_flip)
        row.addWidget(flip_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.canvas.reset_transform)
        row.addWidget(reset_btn)

        guides_box = QCheckBox("Guides")
        guides_box.toggled.connect(self.canvas.set_show_guides)
        row.addWidget(guides_box)

        refresh_btn = QPushButton("Refresh from Canvas")
        refresh_btn.clicked.connect(self.canvas.refresh_snapshot)
        row.addWidget(refresh_btn)

        row.addStretch(1)

        self.lock_btn = QPushButton("Lock Projection")
        self.lock_btn.setCheckable(True)
        self.lock_btn.toggled.connect(self._on_lock_toggled)
        row.addWidget(self.lock_btn)

        exit_btn = QPushButton("Exit Projector Mode (Esc)")
        exit_btn.clicked.connect(self.close)
        row.addWidget(exit_btn)

        return bar

    def _on_lock_toggled(self, on: bool) -> None:
        self.canvas.set_locked(on)
        self.lock_btn.setText("Unlock Projection" if on else "Lock Projection")

    def get_state(self) -> dict:
        return self.canvas.get_state()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)
