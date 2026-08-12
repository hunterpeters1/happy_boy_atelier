"""Reference-image position snapping: rule-of-thirds/golden-ratio guide
intersections only engage while the corresponding guide is actually
visible (software doesn't infer -- the artist has to turn the guide on
first), matching the existing center-to-center snap's guard shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.layers.guide_overlay import GOLDEN_SECTION
from app.layers.reference_layer import ReferenceImageItem
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def _add_item(scene) -> object:
    pixmap = QPixmap(50, 50)
    return scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))


def _add_exact_item(scene, natural_w: float, natural_h: float, pos: QPointF) -> ReferenceImageItem:
    """add_image()'s canvas_w_scene/canvas_h_scene args aren't the desired
    image size -- fit_base_size() treats them as *the canvas's own*
    dimensions and fits the photo to ~55% of its longer side. For exact,
    round-number geometry in these edge-snap tests, construct the item
    directly with the natural size we actually want instead.
    """
    pixmap = QPixmap(round(natural_w), round(natural_h))
    item = ReferenceImageItem(f"test-{id(pixmap)}", pixmap, natural_w, natural_h)
    item.setPos(pos)
    scene.reference_layer.add_existing(item)
    return item


def test_rule_of_thirds_intersection_does_not_snap_while_guide_hidden(qapp):
    scene = _scene(qapp)
    rect = scene.canvas_rect()
    item = _add_item(scene)

    ix = rect.left() + rect.width() * 1 / 3
    iy = rect.top() + rect.height() * 1 / 3
    near = QPointF(ix + 3, iy + 3)

    assert item._snap_position(near) == near


def test_rule_of_thirds_intersection_snaps_once_guide_is_visible(qapp):
    scene = _scene(qapp)
    rect = scene.canvas_rect()
    item = _add_item(scene)
    scene.guides_layer.set_rule_of_thirds(True)

    ix = rect.left() + rect.width() * 2 / 3
    iy = rect.top() + rect.height() * 1 / 3
    near = QPointF(ix + 3, iy - 3)

    snapped = item._snap_position(near)
    assert snapped.x() == ix
    assert snapped.y() == iy


def test_golden_ratio_intersection_snaps_once_guide_is_visible(qapp):
    scene = _scene(qapp)
    rect = scene.canvas_rect()
    item = _add_item(scene)
    scene.guides_layer.set_golden_ratio(True)

    gx = rect.left() + rect.width() * GOLDEN_SECTION
    gy = rect.top() + rect.height() * (1 - GOLDEN_SECTION)
    near = QPointF(gx - 2, gy + 2)

    snapped = item._snap_position(near)
    assert snapped.x() == gx
    assert snapped.y() == gy


# -- edge-to-edge (not just center-to-center) snapping -----------------------

def test_snaps_own_edge_flush_with_canvas_edge(qapp):
    scene = _scene(qapp)
    rect = scene.canvas_rect()
    # natural size 200x200 at scale 1 -> half-extent (100, 100).
    item = _add_exact_item(scene, 200, 200, QPointF(0, 0))

    # Center at rect.left() + 100 would put the item's own left edge
    # exactly on the canvas's left edge -- approach from 3px off.
    target_x = rect.left() + 100
    near = QPointF(target_x + 3, rect.center().y())

    snapped = item._snap_position(near)
    assert snapped.x() == target_x


def test_snaps_own_edge_flush_with_another_images_edge(qapp):
    scene = _scene(qapp)
    # Anchor image: natural 200x200 at scale 1, centered at (500, 500) ->
    # right edge at x=600.
    _add_exact_item(scene, 200, 200, QPointF(500, 500))
    # Dragged image: natural 100x100 at scale 1 -> half-extent 50.
    # Center at 600 + 50 = 650 would put its own left edge flush against
    # the anchor's right edge (x=600).
    dragged = _add_exact_item(scene, 100, 100, QPointF(900, 500))

    near = QPointF(650 - 4, 500)
    snapped = dragged._snap_position(near)
    assert snapped.x() == 650
    assert snapped.y() == 500  # unrelated axis untouched (already a center-to-center match)


def test_edge_snap_respects_alt_bypass(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    scene = _scene(qapp)
    rect = scene.canvas_rect()
    item = _add_exact_item(scene, 200, 200, QPointF(0, 0))

    target_x = rect.left() + 100
    near = QPointF(target_x + 3, rect.center().y())

    original_modifiers = QApplication.keyboardModifiers
    QApplication.keyboardModifiers = staticmethod(lambda: Qt.AltModifier)
    try:
        assert item._snap_position(near) == near
    finally:
        QApplication.keyboardModifiers = original_modifiers
