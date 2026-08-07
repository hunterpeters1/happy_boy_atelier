"""Undo/redo correctness tests — the highest-value file in this suite,
since Phase 0.2 is almost entirely new mutation-path code that had never
been executed before (see the "Honesty note" in PHASE_0_PLAN.md).

Builds a real, offscreen CanvasScene (via the qapp fixture) and exercises
each command class exactly the way the UI does: mutate live state, push a
command, then assert state before/after undo and after redo — not just
that the command classes are internally consistent in isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QPixmap

from app.atelier_io import load_atelier, save_atelier
from app.canvas.canvas_scene import CanvasScene
from app.canvas.undo_commands import (
    AddItemCommand,
    CropItemCommand,
    DeleteItemCommand,
    ReorderItemCommand,
    SetNoteTextCommand,
    SetPerspectiveModeCommand,
    SetPropertyCommand,
    TransformCommand,
)
from app.constants import LayerKind, PerspectiveMode
from app.layers.composition_layer import FocalPointItem
from app.project import CanvasSpec, ProjectMeta, empty_manifest


def _scene(qapp) -> CanvasScene:
    # qapp isn't used directly — requesting it as a fixture ensures a
    # QApplication exists before any QGraphicsScene/QGraphicsItem is
    # constructed, which Qt requires even offscreen.
    return CanvasScene(CanvasSpec())


# -- AddItemCommand / DeleteItemCommand -----------------------------------------

def test_add_item_command_undo_redo(qapp):
    scene = _scene(qapp)
    item = FocalPointItem("primary")
    item.setPos(QPointF(10, 10))

    scene.undo_stack.push(AddItemCommand(scene.composition_layer, item, "Add focal point"))
    assert item in scene.composition_layer.focal_points

    scene.undo_stack.undo()
    assert item not in scene.composition_layer.focal_points

    scene.undo_stack.redo()
    assert item in scene.composition_layer.focal_points


def test_delete_item_command_undo_redo(qapp):
    scene = _scene(qapp)
    item = scene.composition_layer.add_focal_point("secondary", QPointF(5, 5))

    scene.undo_stack.push(DeleteItemCommand(scene.composition_layer, item, "Delete item"))
    assert item not in scene.composition_layer.focal_points

    scene.undo_stack.undo()
    assert item in scene.composition_layer.focal_points

    scene.undo_stack.redo()
    assert item not in scene.composition_layer.focal_points


def test_delete_item_command_undo_restores_original_stacking_position(qapp):
    """Deleting a non-last item and undoing must restore it to its exact
    original position, not silently move it to the front of the stack —
    add_existing() alone always appends, which is what DeleteItemCommand
    used to do on undo (a real bug: print order permanently changed).
    """
    scene = _scene(qapp)
    pixmap = QPixmap(10, 10)
    a = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    c = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    assert scene.reference_layer.items() == [a, b, c]

    scene.undo_stack.push(DeleteItemCommand(scene.reference_layer, b, "Delete item"))
    assert scene.reference_layer.items() == [a, c]

    scene.undo_stack.undo()
    assert scene.reference_layer.items() == [a, b, c]  # restored in the middle, not appended

    scene.undo_stack.redo()
    assert scene.reference_layer.items() == [a, c]
    scene.undo_stack.undo()
    assert scene.reference_layer.items() == [a, b, c]


def test_delete_item_command_undo_restores_position_in_typed_bucket(qapp):
    """Same guarantee for a typed-bucket group (composition/lighting) —
    deleting one of several focal points and undoing must land it back
    in the same spot within the focal_points bucket specifically.
    """
    scene = _scene(qapp)
    layer = scene.composition_layer
    a = layer.add_focal_point("primary", QPointF(0, 0))
    b = layer.add_focal_point("primary", QPointF(10, 10))
    c = layer.add_focal_point("primary", QPointF(20, 20))
    assert layer.focal_points == [a, b, c]

    scene.undo_stack.push(DeleteItemCommand(layer, b, "Delete item"))
    assert layer.focal_points == [a, c]

    scene.undo_stack.undo()
    assert layer.focal_points == [a, b, c]


def test_tool_click_add_and_delete_selected_round_trip(qapp):
    # Exercises the actual UI path (canvas_scene._handle_tool_click ->
    # delete_selected_items), not just the command classes directly.
    scene = _scene(qapp)
    scene.set_active_tool("focal_primary")
    assert scene._handle_tool_click(QPointF(30, 30)) is True
    assert len(scene.composition_layer.focal_points) == 1
    item = scene.composition_layer.focal_points[0]

    scene.set_selection([item])
    scene.delete_selected_items()
    assert scene.composition_layer.focal_points == []

    scene.undo_stack.undo()
    assert scene.composition_layer.focal_points == [item]


# -- TransformCommand / begin_transform / commit_transform ----------------------

def test_transform_command_undo_redo(qapp):
    scene = _scene(qapp)
    item = scene.composition_layer.add_focal_point("primary", QPointF(0, 0))

    old_state = (item.pos(), item.rotation(), item.scale())
    item.setPos(QPointF(50, 30))
    item.setRotation(45)
    new_state = (item.pos(), item.rotation(), item.scale())

    scene.undo_stack.push(TransformCommand(item, old_state, new_state, "Move"))
    assert item.pos() == QPointF(50, 30)
    assert item.rotation() == 45

    scene.undo_stack.undo()
    assert item.pos() == QPointF(0, 0)
    assert item.rotation() == 0

    scene.undo_stack.redo()
    assert item.pos() == QPointF(50, 30)
    assert item.rotation() == 45


def test_begin_commit_transform_pushes_exactly_one_command(qapp):
    """The actual press/release path used by whole-item drag (and, via the
    handle classes, scale/rotate) should push exactly one command per
    interaction — never one per intermediate move — and nothing at all if
    the interaction didn't change anything.
    """
    scene = _scene(qapp)
    item = scene.composition_layer.add_focal_point("primary", QPointF(0, 0))
    start_index = scene.undo_stack.index()

    item.begin_transform()
    item.setPos(QPointF(5, 5))   # simulates intermediate mouseMoveEvent frames
    item.setPos(QPointF(12, 9))
    item.setPos(QPointF(20, 20))
    item.commit_transform()

    assert scene.undo_stack.index() == start_index + 1  # one command, not three
    assert item.pos() == QPointF(20, 20)

    # A press/release with no net change must not push anything.
    item.begin_transform()
    item.commit_transform()
    assert scene.undo_stack.index() == start_index + 1

    scene.undo_stack.undo()
    assert item.pos() == QPointF(0, 0)

    scene.undo_stack.redo()
    assert item.pos() == QPointF(20, 20)


# -- CropItemCommand --------------------------------------------------------------

def test_crop_item_command_undo_redo(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))

    old_crop = QRect(*item.to_dict()["crop"])
    new_crop = QRect(10, 10, 50, 50)

    scene.undo_stack.push(CropItemCommand(item, old_crop, new_crop, "Crop image"))
    assert QRect(*item.to_dict()["crop"]) == new_crop

    scene.undo_stack.undo()
    assert QRect(*item.to_dict()["crop"]) == old_crop

    scene.undo_stack.redo()
    assert QRect(*item.to_dict()["crop"]) == new_crop


def test_crop_drag_pushes_one_command_not_per_frame(qapp):
    """Crop is direct manipulation via edge handles — dragging an edge
    modifies _crop live (no undo command per frame), and only on release
    is a single CropItemCommand pushed. Mirrors how resize/rotate work:
    begin_transform captures the baseline, commit pushes one command.
    """
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    start_index = scene.undo_stack.index()

    # Simulate the start of a crop-edge drag (right edge).
    item._begin_crop_drag("right")
    old_crop = QRect(item._crop)
    # Simulate several drag frames moving the right edge inward —
    # none of these should touch the undo stack.
    item._update_crop_drag(_FakeMouseEvent(QPointF(-25, 0)))
    item._update_crop_drag(_FakeMouseEvent(QPointF(-10, 0)))
    assert scene.undo_stack.index() == start_index
    # The crop has changed immediately (direct manipulation).
    assert QRect(item._crop) != old_crop

    item._commit_crop()
    assert scene.undo_stack.index() == start_index + 1

    # Undo restores the original crop.
    scene.undo_stack.undo()
    assert QRect(*item.to_dict()["crop"]) == old_crop
    # Redo re-applies the new crop.
    scene.undo_stack.redo()
    assert QRect(*item.to_dict()["crop"]) != old_crop


class _FakeMouseEvent:
    """Minimal stand-in for QGraphicsSceneMouseEvent so crop-drag update
    can be tested without a real mouse. Only scenePos() is used by
    _update_crop_drag.
    """
    def __init__(self, scene_pos: QPointF):
        self._scene_pos = scene_pos

    def scenePos(self) -> QPointF:
        return self._scene_pos


def test_reset_crop_via_command(qapp):
    """Reset Crop button / reset_crop() pushes a CropItemCommand that
    clears the crop back to full source. Undo/redo works."""
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    # Apply a crop directly.
    item.set_crop(QRect(20, 20, 40, 40))
    assert QRect(*item.to_dict()["crop"]) == QRect(20, 20, 40, 40)
    start_index = scene.undo_stack.index()

    # reset_crop pushes a command.
    item.reset_crop()
    assert scene.undo_stack.index() == start_index + 1
    assert QRect(*item.to_dict()["crop"]) == QRect(0, 0, 100, 100)

    # Undo re-applies the crop.
    scene.undo_stack.undo()
    assert QRect(*item.to_dict()["crop"]) == QRect(20, 20, 40, 40)

    # Redo clears it again.
    scene.undo_stack.redo()
    assert QRect(*item.to_dict()["crop"]) == QRect(0, 0, 100, 100)


def test_crop_does_not_interfere_with_resize(qapp):
    """After cropping, the image's natural_size() reflects the cropped
    dimensions so resize handles track the visible (cropped) footprint
    correctly."""
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    # Full image: natural_size is (275, 275) (fit_base_size with 500x500
    # canvas -> target=275, pixmap is square so both axes = 275).
    assert item.natural_size() == (275.0, 275.0)

    # Crop to half-width on the right: frac_w = 50/100 = 0.5.
    item.set_crop(QRect(0, 0, 50, 100))
    w, h = item.natural_size()
    assert w == 137.5  # 275 * (50 / 100)
    assert h == 275.0  # unchanged (frac_h = 100/100)

    # Resize after crop — set_scale_xy should still work (it changes the
    # item's transform, not natural_size). Just verify it doesn't raise.
    item.set_scale_xy(2.0, 2.0)
    assert item.scale_x() == 2.0
    assert item.scale_y() == 2.0


def test_crop_edge_handles_hidden_when_crop_is_full(qapp):
    """Edge handles are only visible when there's an active (non-full)
    crop — they shouldn't clutter the canvas when the image is uncropped."""
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))

    # No crop = edge handles hidden.
    item.set_ui_active(True)
    assert item._crop_is_full() is True
    # Edge handles exist but are not visible.
    edge_visible = all(h.isVisible() for h in item._handles._edges)
    assert not edge_visible

    # Apply a crop — edge handles become visible.
    item.set_crop(QRect(10, 10, 50, 50))
    assert item._crop_is_full() is False
    edge_visible = all(h.isVisible() for h in item._handles._edges)
    assert edge_visible

    # Reset crop — edge handles hidden again.
    item.reset_crop()
    edge_visible = all(h.isVisible() for h in item._handles._edges)
    assert not edge_visible


# -- Validation pass (per Hunter's Phase 0 undo-reliability checklist) ------------
#
# The tests above already cover most of this checklist via generic
# InteractiveItem/FocalPointItem cases, since ReferenceImageItem, VP, and
# horizon all share the same InteractiveItem.begin_transform()/
# commit_transform() machinery. The tests below specifically exercise
# ReferenceImageItem and perspective-point items directly (not just their
# shared base class), since a bug specific to one of those subclasses
# wouldn't show up in a FocalPointItem-only test.

def test_reference_image_move_undo_redo(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    start_index = scene.undo_stack.index()

    item.begin_transform()
    item.setPos(QPointF(5, 5))    # simulated intermediate drag frames
    item.setPos(QPointF(40, 15))
    item.setPos(QPointF(80, 30))
    item.commit_transform()

    assert scene.undo_stack.index() == start_index + 1  # one command, not three
    assert item.pos() == QPointF(80, 30)

    scene.undo_stack.undo()
    assert item.pos() == QPointF(0, 0)

    scene.undo_stack.redo()
    assert item.pos() == QPointF(80, 30)


def test_reference_image_rotate_undo_redo(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    start_index = scene.undo_stack.index()

    # Mirrors what _RotateHandle does: begin_transform() on press,
    # setRotation() per drag frame, commit_transform() on release.
    item.begin_transform()
    item.setRotation(10)
    item.setRotation(35)
    item.setRotation(72)
    item.commit_transform()

    assert scene.undo_stack.index() == start_index + 1
    assert item.rotation() == 72

    scene.undo_stack.undo()
    assert item.rotation() == 0

    scene.undo_stack.redo()
    assert item.rotation() == 72


def test_reference_image_delete_undo_redo(qapp):
    # Goes through CanvasScene.delete_item (the real call site double-
    # click/Delete-key routes through), not DeleteItemCommand directly.
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))

    scene.delete_item(item)
    assert item not in scene.reference_layer.items()

    scene.undo_stack.undo()
    assert item in scene.reference_layer.items()

    scene.undo_stack.redo()
    assert item not in scene.reference_layer.items()


# -- Perspective points (VP / horizon) share the same InteractiveItem drag --------

def test_vanishing_point_move_undo_redo(qapp):
    scene = _scene(qapp)
    vp = scene.perspective_layer.vps[0]
    start_pos = vp.pos()
    start_index = scene.undo_stack.index()

    vp.begin_transform()
    vp.setPos(start_pos + QPointF(30, -15))
    vp.commit_transform()

    assert scene.undo_stack.index() == start_index + 1
    assert vp.pos() == start_pos + QPointF(30, -15)

    scene.undo_stack.undo()
    assert vp.pos() == start_pos

    scene.undo_stack.redo()
    assert vp.pos() == start_pos + QPointF(30, -15)


def test_horizon_line_move_undo_redo(qapp):
    # HorizonLineItem constrains x to 0 via itemChange() — confirm that
    # constraint survives an undo/redo round trip (not just a plain set).
    scene = _scene(qapp)
    horizon = scene.perspective_layer.horizon
    start_y = horizon.pos().y()
    start_index = scene.undo_stack.index()

    horizon.begin_transform()
    horizon.setPos(QPointF(999, start_y + 40))  # x should be clamped to 0
    horizon.commit_transform()

    assert scene.undo_stack.index() == start_index + 1
    assert horizon.pos().x() == 0
    assert horizon.pos().y() == start_y + 40

    scene.undo_stack.undo()
    assert horizon.pos().x() == 0
    assert horizon.pos().y() == start_y

    scene.undo_stack.redo()
    assert horizon.pos().x() == 0
    assert horizon.pos().y() == start_y + 40


# -- Serialization correctness after undo/redo -------------------------------------

def test_serialization_reflects_state_after_undo(qapp):
    """Undo must not leave stale/corrupted data behind in to_manifest_layers()
    — the thing Save actually reads from.
    """
    scene = _scene(qapp)
    new_item = FocalPointItem("secondary")
    new_item.setPos(QPointF(50, 50))
    scene.undo_stack.push(AddItemCommand(scene.composition_layer, new_item, "Add focal point"))

    layers_before, _ = scene.to_manifest_layers()
    assert len(layers_before["composition"]["focal_points"]) == 1

    scene.undo_stack.undo()
    layers_after_undo, _ = scene.to_manifest_layers()
    assert layers_after_undo["composition"]["focal_points"] == []

    scene.undo_stack.redo()
    layers_after_redo, _ = scene.to_manifest_layers()
    assert len(layers_after_redo["composition"]["focal_points"]) == 1
    assert layers_after_redo["composition"]["focal_points"][0]["x"] == 50


def test_save_after_undo_persists_reverted_state(tmp_path, qapp):
    """The literal Save flow: build a manifest, write it, read it back —
    after an undo — and confirm the file on disk reflects the undone
    state, not whatever was on screen before the undo.
    """
    scene = _scene(qapp)
    item = FocalPointItem("primary")
    item.setPos(QPointF(10, 10))
    scene.undo_stack.push(AddItemCommand(scene.composition_layer, item, "Add focal point"))
    scene.undo_stack.undo()  # back to zero focal points

    meta = ProjectMeta()
    manifest = empty_manifest(scene.canvas_spec, meta)
    layers, images = scene.to_manifest_layers()
    manifest.update(layers)

    path = tmp_path / "after_undo.atelier"
    save_atelier(path, manifest, images)

    loaded_manifest, _ = load_atelier(path)
    assert loaded_manifest["composition"]["focal_points"] == []


# -- Guide toggles: confirm they're deliberately excluded from undo ---------------

def test_guide_toggles_are_not_on_undo_stack(qapp):
    """Rule of Thirds / Golden Ratio are layer-visibility-style toggles,
    not content mutations — same category as lock/visibility, which the
    approved Phase 0 scope explicitly excludes from undo. Flagging this
    explicitly since it's easy to expect a Ctrl+Z-able "change" here.
    """
    scene = _scene(qapp)
    start_index = scene.undo_stack.index()

    scene.guides_layer.set_rule_of_thirds(True)
    scene.guides_layer.set_golden_ratio(True)

    assert scene.undo_stack.index() == start_index
    assert scene.guides_layer.thirds.isVisible() is True
    assert scene.guides_layer.golden.isVisible() is True


# -- Free corner-drag resize (independent scale_x/scale_y) ------------------------

def test_set_scale_xy_allows_independent_axes(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))

    item.set_scale_xy(2.0, 0.5)
    assert item.scale_x() == 2.0
    assert item.scale_y() == 0.5
    # Back-compat single-value accessor reads the X axis.
    assert item.scale_factor() == 2.0


def test_set_scale_factor_is_still_uniform(qapp):
    # The Properties panel's single Scale field must keep behaving as a
    # uniform (both-axes) scale, even though corner-drag can now diverge.
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))

    item.set_scale_xy(2.0, 0.5)  # start from a non-uniform state
    item.set_scale_factor(1.5)
    assert item.scale_x() == 1.5
    assert item.scale_y() == 1.5


def test_transform_command_handles_non_uniform_scale_tuple(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))

    old_state = item._snapshot_transform()
    item.set_scale_xy(3.0, 0.75)
    item.setPos(QPointF(40, -10))
    new_state = item._snapshot_transform()

    scene.undo_stack.push(TransformCommand(item, old_state, new_state, "Resize"))
    assert item.scale_x() == 3.0
    assert item.scale_y() == 0.75
    assert item.pos() == QPointF(40, -10)

    scene.undo_stack.undo()
    assert item.scale_x() == 1.0
    assert item.scale_y() == 1.0
    assert item.pos() == QPointF(0, 0)

    scene.undo_stack.redo()
    assert item.scale_x() == 3.0
    assert item.scale_y() == 0.75


def test_corner_drag_resize_pushes_one_command_via_begin_commit_transform(qapp):
    """Exercises the same begin_transform()/set_scale_xy()/setPos()/
    commit_transform() sequence _CornerScaleHandle drives, without needing
    a real mouse event — the geometry itself (compute_corner_resize) is
    covered exhaustively in tests/test_resize_math.py.
    """
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    start_index = scene.undo_stack.index()

    item.begin_transform()
    item.set_scale_xy(1.2, 1.2)   # simulated intermediate drag frames
    item.set_scale_xy(2.0, 0.6)
    item.setPos(QPointF(15, -5))
    item.commit_transform()

    assert scene.undo_stack.index() == start_index + 1  # one command, not three
    assert item.scale_x() == 2.0
    assert item.scale_y() == 0.6

    scene.undo_stack.undo()
    assert item.scale_x() == 1.0
    assert item.scale_y() == 1.0
    assert item.pos() == QPointF(0, 0)


def test_reference_image_round_trips_independent_scale_through_atelier_dict(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(100, 100)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    item.set_scale_xy(2.5, 0.4)

    from app.layers.reference_layer import ReferenceImageItem

    record = item.to_dict()
    assert record["scale_x"] == 2.5
    assert record["scale_y"] == 0.4
    assert record["scale"] == 2.5  # legacy field, for older readers

    restored = ReferenceImageItem.from_dict(record, pixmap)
    assert restored.scale_x() == 2.5
    assert restored.scale_y() == 0.4


def test_reference_image_from_dict_falls_back_to_legacy_scale_field(qapp):
    # A project saved before free resize existed only has "scale" — both
    # axes should come from that single value so old files reopen looking
    # exactly as they did.
    from app.layers.reference_layer import ReferenceImageItem

    pixmap = QPixmap(100, 100)
    legacy_record = {
        "id": "legacy1", "x": 0, "y": 0, "rotation": 0, "scale": 1.75,
        "opacity": 1.0, "visible": True, "locked": False,
        "base_w": 100, "base_h": 100, "crop": [0, 0, 100, 100],
        "image": "images/legacy1.png",
    }
    restored = ReferenceImageItem.from_dict(legacy_record, pixmap)
    assert restored.scale_x() == 1.75
    assert restored.scale_y() == 1.75


# -- SetNoteTextCommand -----------------------------------------------------------

def test_set_note_text_command_undo_redo(qapp):
    scene = _scene(qapp)
    note = scene.composition_layer.add_note(QPointF(0, 0), text="Original")

    scene.undo_stack.push(SetNoteTextCommand(note, "Original", "Edited"))
    assert note.text() == "Edited"

    scene.undo_stack.undo()
    assert note.text() == "Original"

    scene.undo_stack.redo()
    assert note.text() == "Edited"


def test_note_commit_text_edit_pushes_once_per_edit_session(qapp):
    scene = _scene(qapp)
    note = scene.composition_layer.add_note(QPointF(0, 0), text="Original")
    start_index = scene.undo_stack.index()

    note.begin_text_edit()
    note.set_text("Draft one")   # simulates keystrokes during editing
    note.set_text("Draft two")
    note.set_text("Final text")
    note.commit_text_edit()

    assert scene.undo_stack.index() == start_index + 1  # one command, not three
    assert note.text() == "Final text"

    scene.undo_stack.undo()
    assert note.text() == "Original"

    # Editing then leaving the text unchanged must not push anything.
    note.begin_text_edit()
    note.commit_text_edit()
    assert scene.undo_stack.index() == start_index  # still at the undone position


# -- SetPropertyCommand ------------------------------------------------------------

def test_set_property_command_undo_redo_grid_line_weight(qapp):
    scene = _scene(qapp)
    layer = scene.perspective_layer

    old_width = layer._line_width
    new_width = 5.0
    scene.undo_stack.push(SetPropertyCommand(layer.set_line_width, old_width, new_width, "Line weight"))
    assert layer._line_width == new_width

    scene.undo_stack.undo()
    assert layer._line_width == old_width

    scene.undo_stack.redo()
    assert layer._line_width == new_width


# -- SetPerspectiveModeCommand -----------------------------------------------------

def test_set_perspective_mode_command_undo_redo(qapp):
    scene = _scene(qapp)
    layer = scene.perspective_layer
    assert layer.mode == PerspectiveMode.ONE_POINT

    old_mode, old_horizon_y, old_vps = layer.snapshot_state()
    scene.undo_stack.push(
        SetPerspectiveModeCommand(layer, old_mode, old_horizon_y, old_vps, PerspectiveMode.TWO_POINT)
    )
    assert layer.mode == PerspectiveMode.TWO_POINT
    assert len(layer.vps) == 2

    scene.undo_stack.undo()
    assert layer.mode == PerspectiveMode.ONE_POINT
    assert len(layer.vps) == 1

    scene.undo_stack.redo()
    assert layer.mode == PerspectiveMode.TWO_POINT
    assert len(layer.vps) == 2


def test_perspective_mode_switch_is_lossless_on_undo(qapp):
    # The specific quality improvement called out in PHASE_0_PLAN.md:
    # switching 1pt -> 2pt used to lose the original 1pt VP position on
    # switching back, because set_mode() always regenerates fresh
    # defaults. SetPerspectiveModeCommand's undo path must restore the
    # *exact* prior position, not a freshly regenerated default.
    scene = _scene(qapp)
    layer = scene.perspective_layer
    moved_pos = QPointF(123.0, 45.0)
    layer.vps[0].setPos(moved_pos)

    old_mode, old_horizon_y, old_vps = layer.snapshot_state()
    scene.undo_stack.push(
        SetPerspectiveModeCommand(layer, old_mode, old_horizon_y, old_vps, PerspectiveMode.TWO_POINT)
    )
    scene.undo_stack.undo()

    assert layer.vps[0].pos() == moved_pos


# -- Multi-select delete = one undo step -------------------------------------------

def test_multi_select_delete_is_one_undo_step(qapp):
    scene = _scene(qapp)
    a = scene.composition_layer.add_focal_point("primary", QPointF(0, 0))
    b = scene.composition_layer.add_focal_point("secondary", QPointF(20, 20))
    scene.set_selection([a, b])
    start_index = scene.undo_stack.index()

    scene.delete_selected_items()
    assert a not in scene.composition_layer.focal_points
    assert b not in scene.composition_layer.focal_points
    assert scene.undo_stack.index() == start_index + 1  # one macro, not two commands

    scene.undo_stack.undo()
    assert a in scene.composition_layer.focal_points
    assert b in scene.composition_layer.focal_points


# -- ReorderItemCommand / layer group stacking order --------------------------------

def test_reference_layer_reorder_forward_backward(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(10, 10)
    a = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    c = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    assert scene.reference_layer.items() == [a, b, c]
    assert [i.zValue() for i in (a, b, c)] == [0, 1, 2]

    assert scene.reference_layer.move_item_forward(a) is True
    assert scene.reference_layer.items() == [b, a, c]
    assert a.zValue() > b.zValue()

    assert scene.reference_layer.move_item_backward(c) is True
    assert scene.reference_layer.items() == [b, c, a]

    # Boundaries: can't move the frontmost item (a, now last) further
    # forward, or the backmost item (b, still first) further backward.
    assert scene.reference_layer.can_move_forward(a) is False
    assert scene.reference_layer.move_item_forward(a) is False
    assert scene.reference_layer.items() == [b, c, a]

    assert scene.reference_layer.can_move_backward(b) is False
    assert scene.reference_layer.move_item_backward(b) is False


def test_reorder_item_command_undo_redo(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(10, 10)
    a = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    assert scene.reference_layer.items() == [a, b]

    scene.undo_stack.push(ReorderItemCommand(scene.reference_layer, a, forward=True))
    assert scene.reference_layer.items() == [b, a]

    scene.undo_stack.undo()
    assert scene.reference_layer.items() == [a, b]

    scene.undo_stack.redo()
    assert scene.reference_layer.items() == [b, a]

    # backward is the exact mirror
    scene.undo_stack.push(ReorderItemCommand(scene.reference_layer, a, forward=False))
    assert scene.reference_layer.items() == [a, b]
    scene.undo_stack.undo()
    assert scene.reference_layer.items() == [b, a]


def test_composition_layer_reorder_is_scoped_to_marker_type(qapp):
    """Reordering only moves an item within its own marker-type bucket
    (focal points among focal points, notes among notes, etc.) — the
    fixed band ordering between types (movement lines < focal points <
    notes) is deliberate, not something the up/down buttons can disturb.
    """
    scene = _scene(qapp)
    layer = scene.composition_layer
    fp1 = layer.add_focal_point("primary", QPointF(0, 0))
    fp2 = layer.add_focal_point("secondary", QPointF(10, 10))
    note = layer.add_note(QPointF(20, 20))

    assert layer.can_move_forward(fp1) is True
    assert layer.move_item_forward(fp1) is True
    assert layer.focal_points == [fp2, fp1]
    # Still under the note band regardless of intra-bucket reordering.
    assert fp1.zValue() < note.zValue()
    assert fp2.zValue() < note.zValue()

    # A note has no siblings yet, so it can't move at all.
    assert layer.can_move_forward(note) is False
    assert layer.can_move_backward(note) is False
    assert layer.move_item_forward(note) is False


def test_lighting_layer_reorder_scoped_to_marker_type(qapp):
    scene = _scene(qapp)
    layer = scene.lighting_layer
    s1 = layer.add_source(QPointF(0, 0))
    s2 = layer.add_source(QPointF(10, 10))

    assert layer.move_item_backward(s2) is True
    assert layer.sources == [s2, s1]


# -- StackedLayerMixin.index_of() (layers/stacking_mixin.py) ------------------------

def test_index_of_reflects_position_and_absence(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(10, 10)
    a = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    assert scene.reference_layer.index_of(a) == 0
    assert scene.reference_layer.index_of(b) == 1

    other = FocalPointItem("primary")  # never added to reference_layer
    assert scene.reference_layer.index_of(other) is None


def test_index_of_scoped_to_typed_bucket(qapp):
    scene = _scene(qapp)
    layer = scene.composition_layer
    fp = layer.add_focal_point("primary", QPointF(0, 0))
    note = layer.add_note(QPointF(10, 10))
    # Each type has its own bucket — a note is always index 0 within
    # `notes`, regardless of how many focal points came before it.
    assert layer.index_of(fp) == 0
    assert layer.index_of(note) == 0


# -- Scope: lock/visibility toggles are excluded from undo -------------------------

def test_lock_toggle_is_not_on_undo_stack(qapp):
    """Explicit Phase 0 decision: undo represents reversing changes to the
    artwork setup, not application/workflow state, so lock and visibility
    toggles are direct calls that never touch the undo stack.
    """
    scene = _scene(qapp)
    scene.composition_layer.add_focal_point("primary", QPointF(0, 0))
    index_after_add = scene.undo_stack.index()

    scene.set_layer_locked(LayerKind.COMPOSITION, True)
    assert scene.undo_stack.index() == index_after_add

    scene.composition_layer.setVisible(False)
    assert scene.undo_stack.index() == index_after_add
