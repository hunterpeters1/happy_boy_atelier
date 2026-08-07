"""Reference layer: each imported image is its own movable/scalable/rotatable
/croppable object. Images are embedded (the source QPixmap travels with the
project, never a file path) per the product spec.
"""

from __future__ import annotations

import math
import uuid

from PySide6.QtCore import QBuffer, QIODevice, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsRectItem,
)

from .. import constants as C
from ..canvas.handle_frame import HandleFrame, HANDLE_PX, MIN_SCALE, MAX_SCALE
from ..canvas.interactive_item import InteractiveItem
from ..canvas.resize_math import compute_corner_resize
from .stacking_mixin import StackedLayerMixin

# Was 10 — bumped for a more forgiving grab, same reasoning as
# HANDLE_HIT_RADIUS_PX below.
CROP_HANDLE_PX = 14
ROTATION_SNAP_DEG = 15.0
# Screen-pixel tolerance for position snapping — converted to scene units
# per-drag via the current view zoom, so the catch radius feels the same
# whether zoomed in or out.
SNAP_TOLERANCE_PX = 8.0
# Generous grab radius (viewport/device pixels) around each visual handle.
# Hit-testing for the resize/rotate handles is done manually here, in
# ReferenceImageItem's own mouse handlers, rather than by giving the
# small ItemIgnoresTransformations squares in handle_frame.py their own
# click handling: confirmed at runtime that clicks on those child items
# were being delivered to this (parent) item instead, dragging the whole
# image rather than resizing it — a known Qt limitation with hit-testing
# ItemIgnoresTransformations children over a transformed parent. The
# squares in handle_frame.py are now purely decorative (NoButton).
HANDLE_HIT_RADIUS_PX = HANDLE_PX / 2 + 10
# Fixed scene-unit pad added to boundingRect() around the corner handles
# while active (see boundingRect() below) so Qt still delivers the mouse
# press to this item when a click lands just outside the exact image
# edge, where the visual handle actually is. Deliberately not derived
# from HANDLE_HIT_RADIUS_PX (a *device-pixel* radius) or the current
# view zoom: boundingRect() must stay stable without a matching
# prepareGeometryChange() on every zoom change, so this is a generous
# flat scene-unit value rather than a pixel-exact one — the precise
# click tolerance is still enforced by _hit_test_handle() below.
HANDLE_CLICK_MARGIN_SCENE = 30.0
# Longest-edge cap (px) for the interactive display proxy — see
# ReferenceImageItem._get_display_pixmap(). 2000px comfortably exceeds
# typical on-screen display size even at high zoom on a 4K monitor, while
# staying far below a modern camera photo's native resolution.
MAX_DISPLAY_DIM = 2000
# Longest-edge cap (px) for Study Blur's own working resolution — see
# ReferenceImageItem._get_processed_display_pixmap(). Deliberately smaller
# than MAX_DISPLAY_DIM: measured numpy cost scales with pixel count, and
# processing at 2000px took the better part of a second per slider
# adjustment. ~900px keeps a single recompute in the ~100ms range, and
# the reduced resolution isn't a visible quality loss for a blur effect
# specifically, which has no fine detail left to lose.
BLUR_WORKING_DIM = 900


# tl/br share a diagonal, tr/bl share the other — same convention as
# ReferenceImageItem.hoverMoveEvent()'s corner-resize cursors.
_CROP_CORNER_CURSORS = {
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
}


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
        # Previously unset entirely — the smallest, least-forgiving
        # handle in the app had zero hover cue at all.
        self.setCursor(_CROP_CORNER_CURSORS[corner])

    def mouseMoveEvent(self, event):
        local = self._item.mapFromScene(event.scenePos())
        self._item.update_crop_corner(self._corner, local)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()


class ReferenceImageItem(InteractiveItem):
    """A single reference photo/object placed on the drafting table."""

    def __init__(self, image_id: str, source_pixmap: QPixmap, base_w: float, base_h: float,
                 crop: QRect | None = None, display_name: str | None = None,
                 original_format: str | None = None, original_file_size: int | None = None, parent=None):
        super().__init__(parent)
        self.image_id = image_id
        # The Project Panel lists this by display_name rather than a
        # positional "Reference 1/2/3" placeholder — falls back to the
        # image_id (still unique, just not human-friendly) for projects
        # saved before this field existed.
        self.display_name = display_name or image_id
        # Captured at import time for the Properties panel's info block.
        # None for images from projects saved before this field existed
        # (displayed as "Unknown" rather than guessed).
        self.original_format = original_format
        self.original_file_size = original_file_size
        self._source_pixmap = source_pixmap
        # Lazily-built QImage view of _source_pixmap, cached for the
        # eyedropper's pixel_color() -- sampling fires continuously on
        # hover, and _source_pixmap is set once here and never reassigned,
        # so this cache never needs invalidating.
        self._source_image = None
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
        self._handle_center_scene = QPointF()
        self._handle_press_mouse_angle = 0.0
        # True only while a plain body drag (not a handle drag, not a
        # programmatic setPos from undo/redo, batch align, etc.) is in
        # progress — itemChange() only snaps position during this window,
        # so restoring an exact stored position is never silently nudged.
        self._body_dragging = False

        # Cached downscaled proxy for interactive on-screen painting — see
        # _get_display_pixmap()/paint(). Keeps drag/resize smooth on large
        # camera photos without touching export/thumbnail quality, which
        # always draw straight from _source_pixmap instead (whenever
        # scene.rendering_for_export is set — see paint()).
        self._display_pixmap: QPixmap | None = None
        self._display_pixmap_crop: QRect | None = None
        self._display_pixmap_source_rect = QRectF()

        # Study Blur — see study_blur.py. 0 means "no effect" on both, the
        # default for every image unless the artist turns it on, and the
        # back-compat default for every .atelier file saved before this
        # feature existed (from_dict()). Processed-pixmap cache is keyed
        # on (blur, clarity, crop) so it only regenerates when one of
        # those actually changes, not on every repaint.
        self._blur_amount = 0.0
        self._line_clarity = 0.0
        self._processed_pixmap: QPixmap | None = None
        self._processed_cache_key: tuple | None = None
        # See set_defer_blur_refresh().
        self._defer_blur_refresh = False

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

    def _image_rect(self) -> QRectF:
        w, h = self.natural_size()
        return QRectF(-w / 2, -h / 2, w, h)

    def _get_display_pixmap(self) -> tuple[QPixmap, QRectF]:
        """Cached downscaled proxy of the (already-cropped) source pixmap
        for interactive on-screen painting only — see paint(). A
        multi-megapixel camera photo resampled at full resolution on
        every single repaint frame was the main cost behind sluggish
        drag/resize; this caps what actually gets resampled each frame to
        MAX_DISPLAY_DIM regardless of the source photo's real size.
        Regenerated only when the crop changes (compared against the
        cached crop below) — never touches _source_pixmap itself, so
        export/thumbnail rendering (which draws _source_pixmap directly
        whenever scene.rendering_for_export is set — see paint()) is
        completely unaffected.
        """
        if self._display_pixmap is not None and self._display_pixmap_crop == self._crop:
            return self._display_pixmap, self._display_pixmap_source_rect

        cropped_w, cropped_h = self._crop.width(), self._crop.height()
        longest = max(cropped_w, cropped_h, 1)
        if longest <= MAX_DISPLAY_DIM:
            # Already small enough — draw straight from the source with
            # the normal crop rect rather than allocating a copy that
            # would just be the same size.
            proxy = self._source_pixmap
            source_rect = QRectF(self._crop)
        else:
            scale = MAX_DISPLAY_DIM / longest
            cropped = self._source_pixmap.copy(self._crop)
            proxy = cropped.scaled(
                max(1, round(cropped_w * scale)), max(1, round(cropped_h * scale)),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            source_rect = QRectF(0, 0, proxy.width(), proxy.height())

        self._display_pixmap = proxy
        self._display_pixmap_crop = QRect(self._crop)
        self._display_pixmap_source_rect = source_rect
        return self._display_pixmap, self._display_pixmap_source_rect

    def _get_processed_display_pixmap(self) -> tuple[QPixmap, QRectF]:
        """Whatever Study Blur result is currently cached — paint() calls
        this unconditionally once blur/clarity is nonzero, but it does
        NOT itself decide when to recompute for a changed blur_amount()/
        line_clarity() (see _refresh_processed_pixmap() for why: that's
        real numpy work, and Qt schedules a repaint on every single
        slider tick during a drag — recomputing here on every one of
        those would defeat the Properties panel's debouncing entirely,
        since it'd happen via the normal paint cycle regardless). A crop
        change (or simply never having computed anything yet) is the one
        case handled eagerly here, since that's an infrequent, deliberate
        action, not a continuous-drag scenario.
        """
        proxy, source_rect = self._get_display_pixmap()
        crop_now = QRect(self._crop)
        never_computed = self._processed_pixmap is None or self._processed_cache_key is None
        crop_changed = not never_computed and self._processed_cache_key[2] != crop_now
        if never_computed or crop_changed:
            self._refresh_processed_pixmap()
        return self._processed_pixmap, source_rect

    def _refresh_processed_pixmap(self) -> None:
        """Actually run the Study Blur numpy pipeline against the current
        blur_amount()/line_clarity()/crop and cache the result. Called
        eagerly by _get_processed_display_pixmap() above on first use or
        a crop change, and explicitly by the Properties panel's debounced
        preview timer / slider-release handler for ordinary blur/clarity
        adjustments — see PropertiesPanel._apply_blur_preview().

        Processes at BLUR_WORKING_DIM, smaller than the crisp
        MAX_DISPLAY_DIM proxy, then scales the result back up to match
        it: measured numpy cost scales roughly with pixel count, and a
        2000px-class bitmap took the better part of a second per call —
        clearly not "smooth." Working at a smaller size and upscaling
        isn't a visible quality compromise here specifically *because*
        the output is a blur — it has no fine high-frequency detail left
        for the resolution cut to lose.
        """
        proxy, _ = self._get_display_pixmap()
        from ..canvas.study_blur import apply_study_effect
        work_pixmap = proxy
        longest = max(proxy.width(), proxy.height(), 1)
        if longest > BLUR_WORKING_DIM:
            scale = BLUR_WORKING_DIM / longest
            work_pixmap = proxy.scaled(
                max(1, round(proxy.width() * scale)), max(1, round(proxy.height() * scale)),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        processed_image = apply_study_effect(work_pixmap.toImage(), self._blur_amount, self._line_clarity)
        processed_pixmap = QPixmap.fromImage(processed_image)
        if processed_pixmap.size() != proxy.size():
            processed_pixmap = processed_pixmap.scaled(
                proxy.width(), proxy.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        self._processed_pixmap = processed_pixmap
        self._processed_cache_key = (self._blur_amount, self._line_clarity, QRect(self._crop))

    def boundingRect(self) -> QRectF:
        # Must cover the resize/rotate handles too, not just the image
        # pixels: the rotate handle sits well above the top edge (see
        # HandleFrame._RotateHandle.reposition()) and the corner handles'
        # grab radius (HANDLE_HIT_RADIUS_PX) extends past the corners. Qt
        # only ever delivers a mouse press to this item if the click point
        # falls inside boundingRect()/shape() — a tighter rect here meant
        # clicks on the handles (especially the rotate handle, entirely
        # outside the image rect) silently missed this item and fell
        # through to an empty-canvas click, which clears the selection.
        # That's what made the rotate handle appear dead and the corner
        # handles flaky, and made dragging near an edge look like the
        # selection randomly dropping/"jumping". paint() must keep using
        # _image_rect(), not this, or the pixmap would stretch to fill it.
        rect = self._image_rect()
        if self._ui_active and not self._locked and not self._crop_mode:
            _, h = self.natural_size()
            top_margin = max(20.0, h * 0.18) + HANDLE_CLICK_MARGIN_SCENE
            side_margin = HANDLE_CLICK_MARGIN_SCENE
            rect = rect.adjusted(-side_margin, -top_margin, side_margin, side_margin)
        return rect

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

    # -- Study Blur (see canvas/study_blur.py) -----------------------------
    def blur_amount(self) -> float:
        return self._blur_amount

    def set_blur_amount(self, value: float) -> None:
        self._blur_amount = max(0.0, min(100.0, value))
        if not self._defer_blur_refresh:
            self._refresh_processed_pixmap()
        self.update()

    def line_clarity(self) -> float:
        return self._line_clarity

    def set_line_clarity(self, value: float) -> None:
        self._line_clarity = max(0.0, min(100.0, value))
        if not self._defer_blur_refresh:
            self._refresh_processed_pixmap()
        self.update()

    def set_defer_blur_refresh(self, defer: bool) -> None:
        """Suppresses the immediate _refresh_processed_pixmap() call in
        set_blur_amount()/set_line_clarity() above while `defer` is True.
        The Properties panel turns this on for the duration of an active
        slider drag (see PropertiesPanel._on_blur_field_pressed()) so the
        expensive numpy recompute only happens via its own debounced
        timer/release handler, not once per mouse-move tick through the
        normal setter call. Every other caller of the setters — undo/redo
        (SetPropertyCommand calls them directly), project load
        (from_dict()), anything outside a live panel drag — leaves this
        False, so those always see an up-to-date processed pixmap on the
        very next paint rather than a stale one from before the change.
        """
        self._defer_blur_refresh = defer

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

    def _begin_handle_drag(self, hit: str, scene_pos: QPointF) -> None:
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
        elif hit == "rotate":
            # Track rotation as a delta from the press-time mouse angle,
            # both measured around a fixed scene-space center — not via
            # self.mapFromScene(event.scenePos()) (the old approach),
            # which maps through the item's *current* rotation. Since
            # that rotation is itself what each drag step updates, it
            # created a feedback loop — each step's angle measurement
            # used the frame the previous step just rotated into — so
            # the handle oscillated instead of tracking the cursor.
            self._handle_center_scene = self.mapToScene(QPointF(0, 0))
            dx = scene_pos.x() - self._handle_center_scene.x()
            dy = scene_pos.y() - self._handle_center_scene.y()
            self._handle_press_mouse_angle = math.degrees(math.atan2(dx, -dy))
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
            scene_pos = event.scenePos()
            dx = scene_pos.x() - self._handle_center_scene.x()
            dy = scene_pos.y() - self._handle_center_scene.y()
            current_angle = math.degrees(math.atan2(dx, -dy))
            new_rotation = self._handle_press_rotation + (current_angle - self._handle_press_mouse_angle)
            if event.modifiers() & Qt.ShiftModifier:
                new_rotation = round(new_rotation / ROTATION_SNAP_DEG) * ROTATION_SNAP_DEG
            self.setRotation(new_rotation)
        self._handles.reposition()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            hit = self._hit_test_handle(event.scenePos())
            if hit is not None:
                self._begin_handle_drag(hit, event.scenePos())
                event.accept()
                return
            self._body_dragging = True
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
        self._body_dragging = False
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event) -> None:
        # Nothing else gives a visual cue that a corner/rotate handle is
        # actually grabbable right where the cursor is — this is that
        # cue. Reuses the exact same _hit_test_handle() the mouse press
        # itself uses, so the cursor never claims a spot is grabbable
        # that a click there wouldn't actually hit, or vice versa.
        hit = self._hit_test_handle(event.scenePos())
        if hit is None:
            self.setCursor(Qt.ArrowCursor if self._locked else Qt.OpenHandCursor)
        elif hit == "rotate":
            self.setCursor(Qt.PointingHandCursor)
        else:
            _, sx_s, sy_s = hit.split(":")
            sx, sy = int(sx_s), int(sy_s)
            # Matches _CornerScaleHandle's own (never-delivered) cursor
            # in handle_frame.py — same diagonal-vs-anti-diagonal logic.
            self.setCursor(Qt.SizeFDiagCursor if sx * sy > 0 else Qt.SizeBDiagCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setCursor(Qt.ArrowCursor if self._locked else Qt.OpenHandCursor)
        super().hoverLeaveEvent(event)

    # -- lock / visibility ---------------------------------------------
    def set_ui_active(self, active: bool) -> None:
        """Called by CanvasScene off the item_activated signal (see
        canvas/selection.py) when this item becomes/stops being the one
        the user clicked. Drives the highlight border in paint() and the
        resize/rotate handles.
        """
        self.prepareGeometryChange()
        self._ui_active = active
        self._handles.set_active(active and not self._locked)
        self.update()

    def _on_locked_changed(self, locked: bool) -> None:
        self.prepareGeometryChange()
        self._handles.set_active(self._ui_active and not locked)
        self.setCursor(Qt.ArrowCursor if locked else Qt.OpenHandCursor)

    # -- crop -----------------------------------------------------------
    def enter_crop_mode(self) -> None:
        if self._locked:
            return
        self.prepareGeometryChange()
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

    # -- eyedropper -----------------------------------------------------
    def sample_source_pixel(self, scene_pos: QPointF) -> QPoint | None:
        """Map a scene-space point to a pixel coordinate in the full-
        resolution source image, for the eyedropper tool. Same local-
        coords -> fraction -> source-pixel transform apply_crop() uses on
        a rect below, generalized to a single point. Returns None if the
        point falls outside the actual image (e.g. a click near the
        padded handle-frame bounds that apply_crop()'s rect never has to
        handle).
        """
        local = self.mapFromScene(scene_pos)
        full_w, full_h = self.natural_size()
        if full_w <= 0 or full_h <= 0:
            return None
        frac_x = (local.x() + full_w / 2) / full_w
        frac_y = (local.y() + full_h / 2) / full_h
        if not (0.0 <= frac_x <= 1.0 and 0.0 <= frac_y <= 1.0):
            return None
        px = self._crop.x() + frac_x * self._crop.width()
        py = self._crop.y() + frac_y * self._crop.height()
        px_i, py_i = int(round(px)), int(round(py))
        if not (0 <= px_i < self._source_pixmap.width() and 0 <= py_i < self._source_pixmap.height()):
            return None
        return QPoint(px_i, py_i)

    def pixel_color(self, px: int, py: int) -> QColor:
        """RGB color at a source-pixel coordinate (see
        sample_source_pixel()). Caches the QImage conversion since this is
        called continuously while the eyedropper hovers -- reconverting
        the whole pixmap every mouse-move tick would be the same per-frame
        cost problem _get_display_pixmap() above exists to avoid.
        """
        if self._source_image is None:
            self._source_image = self._source_pixmap.toImage()
        return self._source_image.pixelColor(px, py)

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
        self.prepareGeometryChange()
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
        if change == QGraphicsItem.ItemPositionChange and self._body_dragging:
            return self._snap_position(value)
        return super().itemChange(change, value)

    def _snap_position(self, proposed: QPointF) -> QPointF:
        """Snap the item's center to the canvas center or to another
        visible reference image's center, within a zoom-independent
        catch radius. Hold Alt/Option to bypass entirely.
        """
        if QApplication.keyboardModifiers() & Qt.AltModifier:
            return proposed
        scene = self.scene()
        if scene is None:
            return proposed
        views = scene.views()
        zoom = views[0].transform().m11() if views else 1.0
        tolerance = SNAP_TOLERANCE_PX / max(zoom, 0.01)

        xs: list[float] = []
        ys: list[float] = []
        canvas_rect = getattr(scene, "canvas_rect", None)
        if canvas_rect is not None:
            rect = canvas_rect()
            xs.append(rect.center().x())
            ys.append(rect.center().y())
        reference_layer = getattr(scene, "reference_layer", None)
        if reference_layer is not None:
            for other in reference_layer.items():
                if other is self or not other.isVisible():
                    continue
                xs.append(other.pos().x())
                ys.append(other.pos().y())

        x, y = proposed.x(), proposed.y()
        for cx in xs:
            if abs(x - cx) <= tolerance:
                x = cx
                break
        for cy in ys:
            if abs(y - cy) <= tolerance:
                y = cy
                break
        return QPointF(x, y)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        # Not boundingRect(): that's padded to cover the resize/rotate
        # handles while active (see boundingRect() above), and drawing the
        # pixmap into the padded rect would stretch it.
        rect = self._image_rect()
        scene = self.scene()
        if scene is not None and getattr(scene, "rendering_for_export", False):
            # Set by atelier_io.py around every scene.render() call (PNG/
            # JPG export, PDF planning sheet, thumbnails) — always
            # full-resolution here so export quality never depends on
            # what's cheapest to redraw on screen during a drag. Not
            # `widget is None`: confirmed that's not a reliable signal for
            # "is this an export render" (see CanvasScene.__init__). Study
            # Blur only bakes into the actual export when the artist opts
            # in via the Export dialog's checkbox (export_study_effect) —
            # never for thumbnails, which reuse rendering_for_export but
            # not this second flag (see MainWindow.export_project()).
            if getattr(scene, "export_study_effect", False) and (self._blur_amount or self._line_clarity):
                from ..canvas.study_blur import apply_study_effect
                # Crop at full resolution first, then process — matching
                # what _get_processed_display_pixmap() does at proxy
                # resolution, so blur/edge radii (scaled relative to the
                # cropped image's own size) feel the same in the export
                # as they did in the on-screen preview.
                cropped_source = self._source_pixmap.copy(self._crop)
                processed = apply_study_effect(cropped_source.toImage(), self._blur_amount, self._line_clarity)
                painter.drawPixmap(rect, QPixmap.fromImage(processed),
                                    QRectF(0, 0, processed.width(), processed.height()))
            else:
                painter.drawPixmap(rect, self._source_pixmap, QRectF(self._crop))
        elif self._blur_amount or self._line_clarity:
            pixmap, source_rect = self._get_processed_display_pixmap()
            painter.drawPixmap(rect, pixmap, source_rect)
        else:
            pixmap, source_rect = self._get_display_pixmap()
            painter.drawPixmap(rect, pixmap, source_rect)

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
            "name": self.display_name,
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
            # Study Blur (see canvas/study_blur.py) — 0/0 for every image
            # until the artist turns it on.
            "blur": self._blur_amount,
            "line_clarity": self._line_clarity,
            # None for images imported before this field existed.
            "original_format": self.original_format,
            "original_file_size": self.original_file_size,
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
            # Older files (saved before "name" existed) fall back to the id.
            display_name=d.get("name") or d["id"],
            original_format=d.get("original_format"),
            original_file_size=d.get("original_file_size"),
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
        # Absent on every .atelier file saved before Study Blur existed —
        # defaults to "no effect," so old projects reopen looking exactly
        # as they did.
        item.set_blur_amount(float(d.get("blur", 0.0)))
        item.set_line_clarity(float(d.get("line_clarity", 0.0)))
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


class ReferenceLayerGroup(StackedLayerMixin, QGraphicsItemGroup):
    """Owns all reference image items; provides layer-level visibility/lock/
    opacity that the Layers panel drives.

    can_move_forward()/can_move_backward()/move_item_forward()/
    move_item_backward()/remove_item()/index_of() come from
    StackedLayerMixin (stacking_mixin.py) — this class only supplies
    _bucket_for() (trivial here: there's only ever the one bucket) and
    _reassign_z() (the print-order-IS-list-order scheme below).
    """

    def __init__(self):
        super().__init__()
        self.setHandlesChildEvents(False)
        self._items: list[ReferenceImageItem] = []

    def build_image_item(self, pixmap: QPixmap, canvas_w_scene: float, canvas_h_scene: float,
                          scene_center: QPointF, display_name: str | None = None,
                          original_format: str | None = None,
                          original_file_size: int | None = None) -> ReferenceImageItem:
        """Construct a new item positioned and sized as a fresh import,
        without adding it to the group yet. Used by callers that want to
        route the add through the undo stack (AddItemCommand calls
        add_existing() on redo); add_image() below is the direct,
        non-undoable convenience wrapper for internal/deserialization use.
        """
        base_w, base_h = fit_base_size(pixmap, canvas_w_scene, canvas_h_scene)
        item = ReferenceImageItem(
            str(uuid.uuid4()), pixmap, base_w, base_h, display_name=display_name,
            original_format=original_format, original_file_size=original_file_size,
        )
        item.setPos(scene_center)
        return item

    def add_image(self, pixmap: QPixmap, canvas_w_scene: float, canvas_h_scene: float,
                   scene_center: QPointF, display_name: str | None = None,
                   original_format: str | None = None,
                   original_file_size: int | None = None) -> ReferenceImageItem:
        item = self.build_image_item(
            pixmap, canvas_w_scene, canvas_h_scene, scene_center, display_name,
            original_format, original_file_size,
        )
        self.add_existing(item)
        return item

    def add_existing(self, item: ReferenceImageItem, index: int | None = None) -> None:
        """`index`: insert at this position instead of appending to the
        end — used by DeleteItemCommand.undo() (undo_commands.py) to
        restore an item to its exact original stacking position rather
        than silently moving it to the front.
        """
        self.addToGroup(item)
        if index is None or index >= len(self._items):
            self._items.append(item)
        else:
            self._items.insert(index, item)
        self._reassign_z()

    def _bucket_for(self, item) -> list:
        return self._items

    def items(self) -> list[ReferenceImageItem]:
        return list(self._items)

    def _reassign_z(self) -> None:
        # _items' own order IS the print order (index 0 = bottom) — the
        # Project Panel's per-row up/down buttons drive
        # move_item_forward()/backward() (StackedLayerMixin) through
        # ReorderItemCommand, and this is also exactly what
        # to_dict()/load_from_dict() persist, so no separate z field
        # is needed on disk.
        for i, item in enumerate(self._items):
            item.setZValue(i)

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
