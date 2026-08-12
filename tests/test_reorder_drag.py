"""Drag-to-reorder within a layer section (LayersPanel._handle_reorder_drop(),
driven by _ReorderableTree.dropEvent()). The heavy lifting (StackedLayerMixin,
MoveItemToIndexCommand) was already exercised elsewhere; these tests focus on
the row-order <-> bucket-order translation and the rejection cases — the
actual place a sign error or an accidental cross-section reorder would hide.

Item rows list top-to-bottom in *print* order (top row = prints on top),
which is each layer group's own bucket order *reversed* — see
app/panels/layers_panel.py's module docstring.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QAbstractItemView

from app.canvas.canvas_scene import CanvasScene
from app.panels.layers_panel import LayersPanel, _ROLE_ITEM
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def _add_three_images(scene):
    pix = QPixmap(40, 40)
    a = scene.reference_layer.add_image(pix, 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(pix, 500, 500, QPointF(100, 0))
    c = scene.reference_layer.add_image(pix, 500, 500, QPointF(200, 0))
    return a, b, c


def _bucket_order(scene):
    return list(scene.reference_layer.items())


def test_drop_above_moves_dragged_item_to_print_on_top_of_target(qapp):
    scene = _scene(qapp)
    a, b, c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    row_c = panel._row_for_obj[id(c)]  # c starts as the topmost row (last in bucket)

    handled = panel._handle_reorder_drop(a, row_a, row_c, QAbstractItemView.AboveItem)
    assert handled is True

    # a now prints above c (c was topmost, a is dropped above it -> a is
    # the new topmost), b unaffected in relative order to c.
    assert _bucket_order(scene) == [b, c, a]
    assert scene.undo_stack.count() == 1


def test_drop_below_moves_dragged_item_just_under_target(qapp):
    scene = _scene(qapp)
    a, b, c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    row_c = panel._row_for_obj[id(c)]

    handled = panel._handle_reorder_drop(a, row_a, row_c, QAbstractItemView.BelowItem)
    assert handled is True

    # a lands directly below c in tree order (top-to-bottom: c, a, b) ->
    # bucket order (bottom-to-top, reversed): b, a, c.
    assert _bucket_order(scene) == [b, a, c]


def test_reorder_is_a_single_undo_step(qapp):
    scene = _scene(qapp)
    a, b, c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    row_c = panel._row_for_obj[id(c)]
    panel._handle_reorder_drop(a, row_a, row_c, QAbstractItemView.AboveItem)

    assert _bucket_order(scene) == [b, c, a]
    scene.undo_stack.undo()
    assert _bucket_order(scene) == [a, b, c]


def test_dropping_on_itself_is_a_noop(qapp):
    scene = _scene(qapp)
    a, b, c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    handled = panel._handle_reorder_drop(a, row_a, row_a, QAbstractItemView.AboveItem)
    assert handled is False
    assert scene.undo_stack.count() == 0


def test_dropping_back_in_original_spot_is_a_noop(qapp):
    scene = _scene(qapp)
    a, b, c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    row_b = panel._row_for_obj[id(b)]
    # a is already directly below b in tree order -- dropping it "below b"
    # again should change nothing.
    handled = panel._handle_reorder_drop(a, row_a, row_b, QAbstractItemView.BelowItem)
    assert handled is False
    assert scene.undo_stack.count() == 0


def test_cross_layer_section_drop_is_rejected(qapp):
    scene = _scene(qapp)
    a, b, c = _add_three_images(scene)
    focal = scene.composition_layer.add_focal_point("primary", QPointF(0, 0))
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    row_focal = panel._row_for_obj[id(focal)]

    handled = panel._handle_reorder_drop(a, row_a, row_focal, QAbstractItemView.AboveItem)
    assert handled is False
    assert scene.undo_stack.count() == 0
    assert _bucket_order(scene) == [a, b, c]


def test_drop_on_a_layer_header_row_is_rejected(qapp):
    scene = _scene(qapp)
    a, _b, _c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    header_row = panel._layer_rows[list(panel._layer_rows.keys())[0]]

    handled = panel._handle_reorder_drop(a, row_a, header_row, QAbstractItemView.AboveItem)
    assert handled is False
    assert scene.undo_stack.count() == 0


def test_on_item_indicator_is_rejected(qapp):
    """Only a linear above/below reorder is meaningful here -- a drop
    registered directly "on" another row (would-be nesting) has no
    sensible interpretation for a flat layer stack.
    """
    scene = _scene(qapp)
    a, b, _c = _add_three_images(scene)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row_a = panel._row_for_obj[id(a)]
    row_b = panel._row_for_obj[id(b)]
    handled = panel._handle_reorder_drop(a, row_a, row_b, QAbstractItemView.OnItem)
    assert handled is False
