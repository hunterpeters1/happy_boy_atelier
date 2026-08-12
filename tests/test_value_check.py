"""ReferenceImageItem.grayscale_amount()/set_grayscale_amount()
(app/layers/reference_layer.py) and CanvasScene.toggle_grayscale_all()
(app/canvas/canvas_scene.py) — the item-level field plus the scene-wide
"squint at the whole board" macro built on top of it. The pure
image-processing math itself is covered separately in
tests/test_study_blur.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.layers.reference_layer import ReferenceImageItem
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def test_fresh_reference_image_has_no_grayscale_by_default(qapp):
    scene = _scene(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    assert item.grayscale_amount() == 0.0


def test_set_grayscale_amount_clamps_to_0_100(qapp):
    scene = _scene(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    item.set_grayscale_amount(150)
    assert item.grayscale_amount() == 100.0
    item.set_grayscale_amount(-10)
    assert item.grayscale_amount() == 0.0


def test_grayscale_amount_round_trips_through_to_dict(qapp):
    scene = _scene(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    item.set_grayscale_amount(75)

    d = item.to_dict()
    assert d["grayscale"] == 75.0
    restored = ReferenceImageItem.from_dict(d, QPixmap(50, 50))
    assert restored.grayscale_amount() == 75.0


def test_grayscale_amount_missing_from_legacy_dict_falls_back_to_zero(qapp):
    """No real .atelier file predates this field, but every schema
    addition here uses a .get(key, default) fallback per CLAUDE.md —
    confirm a record with the key simply absent still loads cleanly.
    """
    scene = _scene(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    d = item.to_dict()
    d.pop("grayscale")

    restored = ReferenceImageItem.from_dict(d, QPixmap(50, 50))
    assert restored.grayscale_amount() == 0.0


def test_toggle_grayscale_all_turns_on_then_off_as_one_undo_step_each(qapp):
    scene = _scene(qapp)
    a = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(400, 0))

    scene.toggle_grayscale_all()
    assert a.grayscale_amount() == 100.0
    assert b.grayscale_amount() == 100.0

    scene.toggle_grayscale_all()
    assert a.grayscale_amount() == 0.0
    assert b.grayscale_amount() == 0.0

    # Each toggle_grayscale_all() call is one undo step, however many
    # images it touched.
    scene.undo_stack.undo()
    assert a.grayscale_amount() == 100.0
    assert b.grayscale_amount() == 100.0
    scene.undo_stack.undo()
    assert a.grayscale_amount() == 0.0
    assert b.grayscale_amount() == 0.0


def test_toggle_grayscale_all_skips_locked_and_hidden_images(qapp):
    scene = _scene(qapp)
    visible = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    locked = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(400, 0))
    locked.set_locked(True)
    hidden = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(800, 0))
    hidden.setVisible(False)

    scene.toggle_grayscale_all()

    assert visible.grayscale_amount() == 100.0
    assert locked.grayscale_amount() == 0.0
    assert hidden.grayscale_amount() == 0.0


def test_toggle_grayscale_all_with_no_eligible_images_is_a_noop(qapp):
    scene = _scene(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    item.set_locked(True)

    scene.toggle_grayscale_all()  # must not raise
    assert scene.undo_stack.count() == 0


def test_duplicate_carries_over_grayscale_amount(qapp):
    scene = _scene(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    item.set_grayscale_amount(60)
    scene.set_selection([item])

    scene.duplicate_selected_items()

    clones = [i for i in scene.reference_layer.items() if i is not item]
    assert len(clones) == 1
    assert clones[0].grayscale_amount() == 60.0
