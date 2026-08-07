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
