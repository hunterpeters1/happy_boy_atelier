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
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def _add_item(scene) -> object:
    pixmap = QPixmap(50, 50)
    return scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))


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
