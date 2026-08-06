"""Reference layer: each imported image is its own movable/scalable/rotatable
/croppable object. Images are embedded (the source QPixmap travels with the
project, never a file path) per the product spec.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsRectItem,
    QStyle,
)

from .. import constants as C
from ..canvas.handle_frame import HandleFrame, HANDLE_PX, MIN_SCALE, MAX_SCALE
from ..canvas.interactive_item import InteractiveItem
from ..canvas.resize_math import compute_corner_resize

CROP_HANDLE_PX = 10
# Generous grab radius (viewport/device pixels) around each visual handle.
# Hit-testing for the resize/rotate handles is done manually here, in
# ReferenceImageItem's own mouse handlers, rather than by giving the
# small ItemIgnoresTransformations squares in handle_frame.py their own
# click handling: confirmed at runtime that clicks on those child items
# were being delivered to this (parent) item instead, dragging the whole
# image rather than resizing it — a known Qt limitation with hit-testing
# ItemIgnoresTransformations children over a transformed parent. The
# squares in handle_frame.py are now purely decorative (NoButton).
HANDLE_HIT_RADIUS_PX = HANDLE_PX / 2 + 6


class _CropHandle(QGraphicsRectItem):
    """Free (non-aspect-locked) corner handle used only while a reference
    item is in crop-editing mode.
    """

    def __init__(self, item: "ReferenceImageItem", corner: str):
        super().__init__(-CROP_HANDLE_PX / 2, -CROP_HANDLE_PX / 2, CROP_HANDLE_PX, CROP_HANDLE_PX, item)
        self._item = item
        self._corner = corner  # "tl","tr","bl","br"
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(C.COLOR_FOCAL_PRIMARY)))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1001)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def mouseMoveEvent(self, event):
        local = self._item.mapFromScene(event.scenePos())
        self._item.update_crop_corner(self._corner, local)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()


class ReferenceImageItem(InteractiveItem):
    """A single reference photo/object placed on the drafting table."""

    def __init__(self, image_id: str, source_pixmap: QPixmap, base_w: float, base_h: float,
                 crop: QRect | None = None, parent=None):
        super().__init__(parent)
        self.image_id = image_id
        self._source_pixmap = source_pixmap
        self._base_w = base_w
        self._base_h = base_h
        self._crop = crop or QRect(0, 0, source_pixmap.width(), source_pixmap.height())
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._crop_mode = False
        self._crop_preview = QRectF()
        self._crop_handles: list[_CropHandle] = []
        # Drives the on-canvas highlight border + resize/rotate handles.
        # Deliberately NOT Qt's own isSelected(): confirmed via runtime
        # logging that setSelected(True) does not reliably stick on items
        # living inside this app's QGraphicsItemGroup + setHandlesChildEvents
        # (False) layer setup, so CanvasScene drives this directly off the
        # item_activated signal instead (see canvas/selection.py).
        self._ui_active = False

        # Manual resize/rotate handle drag state (see HANDLE_HIT_RADIUS_PX
        # above for why this lives here instead of on the handle items).
        self._active_handle: str | None = None  # None | "corner:sx:sy" | "rotate"
        self._handle_half_size = (1.0, 1.0)
        self._handle_press_scale = (1.0, 1.0)
        self._handle_press_rotation = 0.0
        self._handle_anchor_scene = QPointF()

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)

        self._handles = HandleFrame(self)

    # -- geometry -----------------------------------------------------
    def natural_size(self) -> tuple[float, float]:
        sw = max(1, self._source_pixmap.width())
        sh = max(1, self._source_pixmap.height())
        frac_w = self._crop.width() / sw
        frac_h = self._crop.height() / sh
        return (self._base_w * frac_w, self._base_h * frac_h)

    def boundingRect(self) -> QRectF:
        w, h = self.natural_size()
        return QRectF(-w / 2, -h / 2, w, h)

    def scale_x(self) -> float:
        return self._scale_x

    def scale_y(self) -> float:
        return self._scale_y

    def scale_factor(self) -> float:
        """Back-compat single-value accessor: the X scale. Used by the
        Properties panel's uniform "Scale" field and by anything treating
        this item as if it only had one scale axis. After a free (non-
        uniform) corner-drag resize, this may differ from scale_y() —
        use scale_x()/scale_y() directly when that distinction matters.
        """
        return self._scale_x

    def set_scale_factor(self, s: float) -> None:
        """Uniform scale — sets both axes equally. This is what the
        Properties panel's single Scale field drives; independent
        per-axis resize only happens via corner-drag (see
        canvas/resize_math.py and canvas/handle_frame.py).
        """
        self.set_scale_xy(s, s)

    def set_scale_xy(self, sx: float, sy: float) -> None:
        self._scale_x = sx
        self._scale_y = sy
        self.setTransform(QTransform().scale(sx, sy))

    def _snapshot_transform(self):
        # Override InteractiveItem's default, which reads Qt's native
        # single-value scale() — this item's scale lives in a custom
        # QTransform instead (see set_scale_xy()) so it can be non-uniform.
        return (self.pos(), self.rotation(), (self._scale_x, self._scale_y))

    # -- resize/rotate handles (manual hit-test, see HANDLE_HIT_RADIUS_PX) --
    def _view(self):
        scene = self.scene()
        if scene is None:
            return None
        views = scene.views()
        return views[0] if views else None

    _CORNER_SIGNS = (("tl", -1, -1), ("tr", 1, -1), ("bl", -1, 1), ("br", 1, 1))

    def _hit_test_handle(self, scene_pos: QPointF) -> str | None:
        if not self._ui_active or self._locked or self._crop_mode:
            return None
        view = self._view()
        if view is None:
            return None
        click_vp = view.mapFromScene(scene_pos)
        w, h = self.natural_size()
        for _name, sx, sy in self._CORNER_SIGNS:
            handle_vp = view.mapFromScene(self.mapToScene(QPointF(sx * w / 2, sy * h / 2)))
            dx, dy = click_vp.x() - handle_vp.x(), click_vp.y() - handle_vp.y()
            if math.hypot(dx, dy) <= HANDLE_HIT_RADIUS_PX:
                return f"corner:{sx}:{sy}"
        offset = max(20.0, h * 0.18)
        rotate_vp = view.mapFromScene(self.mapToScene(QPointF(0, -h / 2 - offset)))
        dx, dy = click_vp.x() - rotate_vp.x(), click_vp.y() - rotate_vp.y()
        if math.hypot(dx, dy) <= HANDLE_HIT_RADIUS_PX:
            return "rotate"
        return None

    def _begin_handle_drag(self, hit: str) -> None:
        self._active_handle = hit
        w, h = self.natural_size()
        self._handle_half_size = (w / 2.0, h / 2.0)
        self._handle_press_scale = (self._scale_x, self._scale_y)
        self._handle_press_rotation = self.rotation()
        if hit.startswith("corner:"):
            _, sx_s, sy_s = hit.split(":")
            sx, sy = int(sx_s), int(sy_s)
            anchor_local = QPointF(-sx * self._handle_half_size[0], -sy * self._handle_half_size[1])
            self._handle_anchor_scene = self.mapToScene(anchor_local)
        self.begin_transform()

    def _update_handle_drag(self, event) -> None:
        if self._active_handle.startswith("corner:"):
            _, sx_s, sy_s = self._active_handle.split(":")
            sx, sy = int(sx_s), int(sy_s)
            locked = bool(event.modifiers() & Qt.ShiftModifier)
            scene_pos = event.scenePos()
            new_center, new_sx, new_sy = compute_corner_resize(
                anchor=(self._handle_anchor_scene.x(), self._handle_anchor_scene.y()),
                cursor=(scene_pos.x(), scene_pos.y()),
                drag_sign=(sx, sy),
                half_size=self._handle_half_size,
                rotation_deg=self._handle_press_rotation,
                press_scale=self._handle_press_scale,
                locked=locked,
                min_scale=MIN_SCALE,
                max_scale=MAX_SCALE,
            )
            self.set_scale_xy(new_sx, new_sy)
            self.setPos(QPointF(*new_center))
        elif self._active_handle == "rotate":
            local = self.mapFromScene(event.scenePos())
            angle = math.degrees(math.atan2(local.x(), -local.y()))
            self.setRotation(self._handle_press_rotation + angle)
        self._handles.reposition()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            hit = self._hit_test_handle(event.scenePos())
            if hit is not None:
                self._begin_handle_drag(hit)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._active_handle is not None:
            self._update_handle_drag(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._active_handle is not None:
            self._active_handle = None
            self.commit_transform()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- lock / visibility ---------------------------------------------
    def set_ui_active(self, active: bool) -> None:
        """Called by CanvasScene off the item_activated signal (see
        canvas/selection.py) when this item becomes/stops being the one
        the user clicked. Drives the highlight border in paint() and the
        resize/rotate handles.
        """
        self._ui_active = active
        self._handles.set_active(active and not self._locked)
        self.update()

    def is_ui_active(self) -> bool:
        return self._ui_active

    def _on_locked_changed(self, locked: bool) -> None:
        self._handles.set_active(self._ui_active and not locked)
        self.setCursor(Qt.ArrowCursor if locked else Qt.OpenHandCursor)

    # -- crop -----------------------------------------------------------
    def enter_crop_mode(self) -> None:
        if self._locked:
            return
        self._crop_mode = True
        w, h = self.natural_size()
        self._crop_preview = QRectF(-w / 2, -h / 2, w, h)
        self._handles.set_active(False)
        if not self._crop_handles:
            self._crop_handles = [_CropHandle(self, c) for c in ("tl", "tr", "bl", "br")]
        for handle in self._crop_handles:
            handle.setVisible(True)
        self._reposition_crop_handles()
        self.update()

    def _reposition_crop_handles(self) -> None:
        r = self._crop_preview
        positions = {
            "tl": r.topLeft(), "tr": r.topRight(),
            "bl": r.bottomLeft(), "br": r.bottomRight(),
        }
        for handle in self._crop_handles:
            handle.setPos(positions[handle._corner])

    def update_crop_corner(self, corner: str, local: QPointF) -> None:
        r = self._crop_preview
        if corner == "tl":
            r = QRectF(local, r.bottomRight())
        elif corner == "tr":
            r = QRectF(QPointF(r.left(), local.y()), QPointF(local.x(), r.bottom()))
        elif corner == "bl":
            r = QRectF(QPointF(local.x(), r.top()), QPointF(r.right(), local.y()))
        elif corner == "br":
            r = QRectF(r.topLeft(), local)
        self._crop_preview = r.normalized()
        self._reposition_crop_handles()
        self.update()

    def set_crop(self, rect: QRect) -> None:
        """Apply a crop QRect directly (source-pixel coordinates). Used both
        by apply_crop() below and by CropItemCommand's undo/redo.
        """
        self.prepareGeometryChange()
        self._crop = QRect(rect)
        self._handles.reposition()
        self.update()

    def apply_crop(self) -> None:
        if not self._crop_mode:
            return
        full_w, full_h = self.natural_size()
        r = self._crop_preview
        # map preview rect (local, centered coords) -> fraction of current display -> source pixels
        left_frac = (r.left() + full_w / 2) / full_w
        top_frac = (r.top() + full_h / 2) / full_h
        w_frac = r.width() / full_w
        h_frac = r.height() / full_h

        px = self._crop.x() + left_frac * self._crop.width()
        py = self._crop.y() + top_frac * self._crop.height()
        pw = max(4, w_frac * self._crop.width())
        ph = max(4, h_frac * self._crop.height())
        old_crop = QRect(self._crop)
        new_crop = QRect(round(px), round(py), round(pw), round(ph))
        self.cancel_crop()
        if new_crop != old_crop:
            scene = self.scene()
            if scene is not None and hasattr(scene, "undo_stack"):
                from ..canvas.undo_commands import CropItemCommand
                scene.undo_stack.push(CropItemCommand(self, old_crop, new_crop))
            else:
                self.set_crop(new_crop)
        self.update()

    def cancel_crop(self) -> None:
        self._crop_mode = False
        for handle in self._crop_handles:
            handle.setVisible(False)
        self._handles.set_active(self._ui_active and not self._locked)
        self.update()

    def is_cropping(self) -> bool:
        return self._crop_mode

    # -- Qt overrides -----------------------------------------------------
    def _is_click_selectable(self) -> bool:
        return not self._crop_mode

    def itemChange(self, change, value):
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = self.boundingRect()
        painter.drawPixmap(rect, self._source_pixmap, QRectF(self._crop))

        if self._crop_mode:
            path = QPainterPath()
            path.addRect(rect)
            path.addRect(self._crop_preview)
            painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)
            painter.setPen(QPen(QColor(C.COLOR_FOCAL_PRIMARY), 0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._crop_preview)
            return

        if self._ui_active and not self._locked:
            pen = QPen(QColor(C.COLOR_BRASS), 0, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

        if self._locked:
            pen = QPen(QColor(C.COLOR_COPPER), 0, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "id": self.image_id,
            "x": pos.x(), "y": pos.y(),
            "rotation": self.rotation(),
            # "scale" is a legacy single-value field kept for older
            # readers/back-compat; scale_x/scale_y are authoritative and
            # can differ after a free (non-uniform) corner-drag resize.
            "scale": self._scale_x,
            "scale_x": self._scale_x,
            "scale_y": self._scale_y,
            "opacity": self.opacity(),
            "visible": self.isVisible(),
            "locked": self._locked,
            "base_w": self._base_w, "base_h": self._base_h,
            "crop": [self._crop.x(), self._crop.y(), self._crop.width(), self._crop.height()],
            "image": f"images/{self.image_id}.png",
        }

    @staticmethod
    def from_dict(d: dict, source_pixmap: QPixmap) -> "ReferenceImageItem":
        crop_vals = d.get("crop") or [0, 0, source_pixmap.width(), source_pixmap.height()]
        item = ReferenceImageItem(
            image_id=d["id"],
            source_pixmap=source_pixmap,
            base_w=float(d.get("base_w", source_pixmap.width())),
            base_h=float(d.get("base_h", source_pixmap.height())),
            crop=QRect(*crop_vals),
        )
        item.setPos(float(d.get("x", 0)), float(d.get("y", 0)))
        item.setRotation(float(d.get("rotation", 0)))
        # scale_x/scale_y are authoritative; fall back to the legacy
        # single "scale" field for projects saved before free resize
        # existed, so older files reopen looking exactly as they did.
        legacy_scale = float(d.get("scale", 1.0))
        scale_x = float(d.get("scale_x", legacy_scale))
        scale_y = float(d.get("scale_y", legacy_scale))
        item.set_scale_xy(scale_x, scale_y)
        item.setOpacity(float(d.get("opacity", 1.0)))
        item.setVisible(bool(d.get("visible", True)))
        item.set_locked(bool(d.get("locked", False)))
        return item

    def encode_png(self) -> bytes:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        self._source_pixmap.save(buf, "PNG")
        return bytes(buf.data())


def fit_base_size(pixmap: QPixmap, canvas_w_in_scene: float, canvas_h_in_scene: float) -> tuple[float, float]:
    """Default on-import footprint: fit within ~55% of the canvas' longer
    side, preserving the photo's own aspect ratio.
    """
    target = max(canvas_w_in_scene, canvas_h_in_scene) * 0.55
    w, h = pixmap.width(), pixmap.height()
    if w <= 0 or h <= 0:
        return target, target
    if w >= h:
        return target, target * (h / w)
    return target * (w / h), target


class ReferenceLayerGroup(QGraphicsItemGroup):
    """Owns all reference image items; provides layer-level visibility/lock/
    opacity that the Layers panel drives.
    """

    def __init__(self):
        super().__init__()
        self.setHandlesChildEvents(False)
        self._items: list[ReferenceImageItem] = []

    def build_image_item(self, pixmap: QPixmap, canvas_w_scene: float, canvas_h_scene: float,
                          scene_center: QPointF) -> ReferenceImageItem:
        """Construct a new item positioned and sized as a fresh import,
        without adding it to the group yet. Used by callers that want to
        route the add through the undo stack (AddItemCommand calls
        add_existing() on redo); add_image() below is the direct,
        non-undoable convenience wrapper for internal/deserialization use.
        """
        base_w, base_h = fit_base_size(pixmap, canvas_w_scene, canvas_h_scene)
        item = ReferenceImageItem(str(uuid.uuid4()), pixmap, base_w, base_h)
        item.setPos(scene_center)
        return item

    def add_image(self, pixmap: QPixmap, canvas_w_scene: float, canvas_h_scene: float,
                   scene_center: QPointF) -> ReferenceImageItem:
        item = self.build_image_item(pixmap, canvas_w_scene, canvas_h_scene, scene_center)
        self.add_existing(item)
        return item

    def add_existing(self, item: ReferenceImageItem) -> None:
        item.setZValue(len(self._items))
        self.addToGroup(item)
        self._items.append(item)

    def remove_item(self, item: ReferenceImageItem) -> None:
        if item in self._items:
            self._items.remove(item)
            self.removeFromGroup(item)
            item.scene().removeItem(item) if item.scene() else None

    def items(self) -> list[ReferenceImageItem]:
        return list(self._items)

    def clear(self) -> None:
        for item in list(self._items):
            self.remove_item(item)

    def set_layer_locked(self, locked: bool) -> None:
        for item in self._items:
            item.set_locked(locked)

    def set_layer_visible(self, visible: bool) -> None:
        self.setVisible(visible)

    def to_dict(self) -> tuple[list[dict], dict[str, bytes]]:
        records, images = [], {}
        for item in self._items:
            records.append(item.to_dict())
            images[item.image_id] = item.encode_png()
        return records, images

    def load_from_dict(self, records: list[dict], images: dict[str, bytes]) -> None:
        self.clear()
        for record in records:
            png_bytes = images.get(record["id"])
            if png_bytes is None:
                continue
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes, "PNG")
            item = ReferenceImageItem.from_dict(record, pixmap)
            self.add_existing(item)
