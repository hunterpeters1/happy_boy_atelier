"""MeasurementItem (app/layers/composition_layer.py): the on-canvas ruler/
angle tool. Exercises the actual first-use path (the two-click tool flow
a real user hits, not just a pre-constructed item), undo/redo, the
to_dict()/from_dict() round trip, and the pure Shift-angle-snap helper.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF

from app.canvas.canvas_scene import CanvasScene
from app.canvas.undo_commands import DeleteItemCommand
from app.layers.composition_layer import MeasurementItem, _snap_to_angle
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def test_measure_tool_two_click_flow_places_a_fresh_measurement(qapp):
    """The actual path a first-time user hits: arm the tool, click twice —
    not constructing a MeasurementItem directly and skipping the tool
    machinery.
    """
    scene = _scene(qapp)
    scene.set_active_tool("measure")

    assert scene._handle_tool_click(QPointF(0, 0)) is True
    assert len(scene.composition_layer.measurements) == 0  # still waiting on the second click
    assert scene._handle_tool_click(QPointF(300, 400)) is True

    assert scene.active_tool() is None  # tool auto-clears after placing, like every other two-click tool
    assert len(scene.composition_layer.measurements) == 1
    item = scene.composition_layer.measurements[0]
    length, _angle = item.length_and_angle()
    assert length == 5.0  # 3-4-5 triangle at 100 scene px/inch


def test_add_and_delete_measurement_undo_redo(qapp):
    scene = _scene(qapp)
    scene.set_active_tool("measure")
    scene._handle_tool_click(QPointF(0, 0))
    scene._handle_tool_click(QPointF(100, 0))
    item = scene.composition_layer.measurements[0]

    scene.undo_stack.undo()
    assert item not in scene.composition_layer.measurements
    scene.undo_stack.redo()
    assert item in scene.composition_layer.measurements

    scene.delete_item(item)
    assert item not in scene.composition_layer.measurements
    scene.undo_stack.undo()
    assert item in scene.composition_layer.measurements


def test_measurement_to_dict_from_dict_round_trip(qapp):
    item = MeasurementItem(QPointF(10, 20), QPointF(210, 20))
    d = item.to_dict()

    restored = MeasurementItem.from_dict(d)
    assert restored.points() == item.points()
    assert restored.measurement_id == item.measurement_id


def test_measurement_from_dict_defaults_missing_fields(qapp):
    """No real .atelier file predates this field (it's new), but every
    schema addition in this codebase still goes through .get(key,
    default) fallbacks per CLAUDE.md -- confirm from_dict() doesn't raise
    on a sparse/malformed record.
    """
    restored = MeasurementItem.from_dict({})
    assert restored.points() == (QPointF(0, 0), QPointF(100, 0))


def test_composition_layer_group_round_trips_measurements(qapp):
    scene = _scene(qapp)
    scene.composition_layer.add_existing(MeasurementItem(QPointF(0, 0), QPointF(0, 200)))

    data = scene.composition_layer.to_dict()
    assert len(data["measurements"]) == 1

    scene2 = _scene(qapp)
    scene2.composition_layer.load_from_dict(data)
    assert len(scene2.composition_layer.measurements) == 1
    length, angle = scene2.composition_layer.measurements[0].length_and_angle()
    assert length == 2.0
    assert angle == -90.0


def test_length_and_angle_respects_canvas_unit(qapp):
    scene = _scene(qapp)
    scene.canvas_spec.unit = "cm"
    item = MeasurementItem(QPointF(0, 0), QPointF(100, 0))  # exactly 1 inch
    scene.composition_layer.add_existing(item)

    length, angle = item.length_and_angle()
    assert math.isclose(length, 2.54, rel_tol=1e-6)
    assert angle == 0.0


def test_snap_to_angle_rounds_to_nearest_step(qapp):
    pivot = QPointF(0, 0)
    # Almost exactly horizontal (dy=-3 out of dx=100) should snap to 0 deg.
    snapped = _snap_to_angle(pivot, QPointF(100, -3), 15.0)
    assert math.isclose(snapped.y(), 0.0, abs_tol=1e-6)
    assert math.isclose(snapped.x(), math.hypot(100, -3), rel_tol=1e-6)


def test_snap_to_angle_leaves_zero_length_untouched(qapp):
    pivot = QPointF(5, 5)
    assert _snap_to_angle(pivot, QPointF(5, 5), 15.0) == QPointF(5, 5)
