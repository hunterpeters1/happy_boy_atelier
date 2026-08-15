"""Reusable interactive transform handles: corner scale + top rotate handle.

Designed for any target item that exposes:
    target.natural_size() -> (w, h)          unscaled local footprint
    target.scale_x() / target.scale_y() / target.set_scale_xy(sx, sy)
    target.rotation() / setRotation(deg)      (standard QGraphicsItem API)

Handles are children of the target item and use ItemIgnoresTransformations
so they render at a constant screen size while still tracking the target's
position, rotation, and scale exactly (Qt maps a child's local position
through the full parent transform chain even when the child itself ignores
that transform for rendering).

Corner-drag resize (free by default, Shift locks proportions) is anchored
at the corner opposite the one being dragged — see canvas/resize_math.py
for the geometry and why it has to be resolved in the item's own rotated
axes rather than screen axes.

Edge handles (left/right/top/bottom midpoints) are for direct crop
manipulation on ReferenceImageItem — dragging an edge handle pushes that
edge inward to crop the image. Like the corner and rotate handles, they
are purely decorative (setAcceptedMouseButtons(NoButton)) — the actual
hit-testing and drag handling lives in ReferenceImageItem itself, for the
same Qt-child-over-transformed-parent click-delivery reason (see
_CornerScaleHandle docstring below).
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from .. import constants as C
from .. import settings

# How long the corner/rotate handles take to fade in when a new item is
# selected -- see settings.futuristic_accents_enabled(). Deliberately
# one-directional: fading *out* on deselect would mean the handles
# linger, semi-visible, right after a click that was meant to clear the
# selection, which reads as unresponsive rather than smooth. Appearing
# eases in; disappearing stays an instant setVisible(False), same as
# with accents off.
_FADE_IN_MS = 140

HANDLE_PX = 9
MIN_SCALE = 0.05
MAX_SCALE = 40.0
# Edge handles for crop are slightly larger than corner handles for a more
# forgiving grab — the same reasoning as HANDLE_HIT_RADIUS_PX widening in
# reference_layer.py, applied here for the new crop interaction.
EDGE_HANDLE_PX = 12
CROP_HANDLE_COLOR = C.COLOR_FOCAL_PRIMARY


class _CornerScaleHandle(QGraphicsRectItem):
    """Purely decorative. Actual resize interaction (hit-testing + drag) is
    handled directly by ReferenceImageItem itself (see
    layers/reference_layer.py: _hit_test_handle/_begin_handle_drag/
    _update_handle_drag). Confirmed at runtime that giving THIS item its
    own mousePressEvent didn't work: clicks landed on the parent
    (ReferenceImageItem, which is movable) instead of this child, dragging
    the whole image rather than resizing it — a known Qt limitation with
    hit-testing ItemIgnoresTransformations children over a transformed
    parent. setAcceptedMouseButtons(NoButton) below makes that explicit
    rather than relying on it being accidentally unreachable — for the
    same reason, this item never receives hover events either, so it sets
    no cursor of its own: the corner-resize cursor is
    ReferenceImageItem.hoverMoveEvent()'s job, computed the same way
    _hit_test_handle() decides whether a click landed here.
    """

    def __init__(self, target, sign_x: int, sign_y: int):
        super().__init__(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX, target)
        self._target = target
        self._sign_x = sign_x
        self._sign_y = sign_y
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(C.COLOR_BRASS)))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def reposition(self) -> None:
        w, h = self._target.natural_size()
        self.setPos(self._sign_x * w / 2, self._sign_y * h / 2)


class _RotateHandle(QGraphicsRectItem):
    """Purely decorative — see _CornerScaleHandle docstring above (same
    applies to its cursor: ReferenceImageItem.hoverMoveEvent() handles it)."""

    def __init__(self, target):
        super().__init__(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX, target)
        self._target = target
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(C.COLOR_BRASS_BRIGHT)))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def reposition(self) -> None:
        w, h = self._target.natural_size()
        offset = max(20.0, h * 0.18)
        self.setPos(0, -h / 2 - offset)


class _EdgeHandle(QGraphicsRectItem):
    """Purely decorative edge-midpoint handle for crop manipulation. Like
    _CornerScaleHandle, the actual mouse interaction is handled by the
    target item's own event handlers (same Qt limitation — see
    _CornerScaleHandle docstring). These exist only to render the visual
    grab affordance at the correct screen size regardless of zoom/rotation.

    `edge` is one of "left", "right", "top", "bottom".
    """

    def __init__(self, target, edge: str):
        super().__init__(-EDGE_HANDLE_PX / 2, -EDGE_HANDLE_PX / 2, EDGE_HANDLE_PX, EDGE_HANDLE_PX, target)
        self._target = target
        self._edge = edge
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(CROP_HANDLE_COLOR)))
        self.setPen(QPen(QColor(C.COLOR_BG_DARKEST), 1))
        self.setZValue(1000)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def reposition(self) -> None:
        w, h = self._target.natural_size()
        if self._edge == "left":
            self.setPos(-w / 2, 0)
        elif self._edge == "right":
            self.setPos(w / 2, 0)
        elif self._edge == "top":
            self.setPos(0, -h / 2)
        elif self._edge == "bottom":
            self.setPos(0, h / 2)


class HandleFrame:
    """Owns the set of handle children for a target item and manages their
    visibility/position. Not a QGraphicsItem itself — just a small manager
    the target composes.
    """

    def __init__(self, target):
        self._target = target
        self._corners = [
            _CornerScaleHandle(target, -1, -1),
            _CornerScaleHandle(target, 1, -1),
            _CornerScaleHandle(target, -1, 1),
            _CornerScaleHandle(target, 1, 1),
        ]
        self._rotate = _RotateHandle(target)
        # Edge handles for crop — created once, shown/hidden as needed.
        # Always created (not lazily) so they're ready the moment an image
        # with a crop is selected, with no allocation jitter on first use.
        self._edges = [_EdgeHandle(target, e) for e in ("left", "right", "top", "bottom")]
        self._fade_anim: QVariantAnimation | None = None
        self.set_active(False)
        self.set_crop_handles_visible(False)

    def reposition(self) -> None:
        for h in self._corners:
            h.reposition()
        self._rotate.reposition()
        for h in self._edges:
            h.reposition()

    def set_active(self, active: bool) -> None:
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None

        handles = [*self._corners, self._rotate]
        if active:
            for h in handles:
                h.setVisible(True)
            self.reposition()
            if settings.futuristic_accents_enabled():
                for h in handles:
                    h.setOpacity(0.0)
                anim = QVariantAnimation(self._target)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setDuration(_FADE_IN_MS)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.valueChanged.connect(lambda v, hs=handles: [h.setOpacity(v) for h in hs])
                anim.start()
                self._fade_anim = anim
            else:
                for h in handles:
                    h.setOpacity(1.0)
        else:
            for h in handles:
                h.setVisible(False)
                h.setOpacity(1.0)

    def set_crop_handles_visible(self, visible: bool) -> None:
        """Show/hide the edge (crop) handles independently from the
        corner/rotate handles. Called by ReferenceImageItem when the image
        has an active crop and is selected — crop handles only appear when
        there's actually a crop to adjust.
        """
        for h in self._edges:
            h.setVisible(visible)
