"""Properties panel correctness tests — currently just the Study Blur
defer-flag edge case; see PropertiesPanel._abort_pending_blur_drag()'s
docstring for the full failure scenario this guards against.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.canvas.undo_commands import SetPropertyCommand
from app.panels.properties_panel import PropertiesPanel
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def test_defer_blur_refresh_not_stuck_after_interrupted_drag(qapp):
    """Pressing a Blur slider (mouse down) sets defer_blur_refresh(True)
    on the item; only the release handler normally clears it. If the
    selection changes away mid-press (e.g. the item gets deleted while
    the slider is still held) without a release ever firing, the panel
    must still clear the flag — otherwise every later non-deferred
    set_blur_amount()/set_line_clarity() call (undo/redo) would silently
    stop refreshing the cached processed pixmap forever.
    """
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    scene.set_selection([item])
    panel = PropertiesPanel(scene)
    panel.refresh()

    panel._on_blur_field_pressed("blur")
    panel.blur_slider.setValue(60)
    assert item._defer_blur_refresh is True

    # Interrupt: delete the item while the slider is still held down.
    scene.delete_selected_items()
    panel.refresh()  # what scene.selection_changed -> properties_panel.refresh() does

    assert item._defer_blur_refresh is False

    # A later non-deferred setter call (undo/redo) must actually refresh
    # the cache, not silently skip it.
    old_blur = item.blur_amount()
    scene.undo_stack.push(SetPropertyCommand(item.set_blur_amount, old_blur, 25, "Change blur"))
    scene.undo_stack.undo()
    assert item._processed_cache_key[0] == item.blur_amount()


def test_defer_blur_refresh_not_touched_when_drag_completes_normally(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    scene.set_selection([item])
    panel = PropertiesPanel(scene)
    panel.refresh()

    panel._on_blur_field_pressed("blur")
    panel.blur_slider.setValue(40)
    panel._on_blur_field_released("blur")

    assert item._defer_blur_refresh is False
    assert item.blur_amount() == 40
    assert scene.undo_stack.count() == 1


# -- Same interrupted-drag family, exercised for the third ("grayscale")
# field added alongside "blur"/"clarity" — this is the one that actually
# changed the shared handlers from a two-way if/else to a three-way
# if/elif/else, the likeliest place for an off-by-one field mixup.

def test_grayscale_drag_interrupted_mid_press_clears_defer_flag(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    scene.set_selection([item])
    panel = PropertiesPanel(scene)
    panel.refresh()

    panel._on_blur_field_pressed("grayscale")
    panel.grayscale_slider.setValue(70)
    assert item._defer_blur_refresh is True

    scene.delete_selected_items()
    panel.refresh()

    assert item._defer_blur_refresh is False
    old = item.grayscale_amount()
    scene.undo_stack.push(SetPropertyCommand(item.set_grayscale_amount, old, 30, "Change value check"))
    scene.undo_stack.undo()
    assert item._processed_cache_key[2] == item.grayscale_amount()


def test_grayscale_drag_completes_normally_pushes_one_undo_step(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    scene.set_selection([item])
    panel = PropertiesPanel(scene)
    panel.refresh()

    panel._on_blur_field_pressed("grayscale")
    panel.grayscale_slider.setValue(80)
    panel._on_blur_field_released("grayscale")

    assert item._defer_blur_refresh is False
    assert item.grayscale_amount() == 80
    assert scene.undo_stack.count() == 1

    scene.undo_stack.undo()
    assert item.grayscale_amount() == 0.0
