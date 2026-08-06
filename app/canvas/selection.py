"""Shared click-to-select helper.

Every interactive marker (reference image, focal point, note, movement
line, light source, direction arrow, vanishing point, horizon) lives inside
a QGraphicsItemGroup layer with `setHandlesChildEvents(False)` so each child
manages its own mouse events. Qt's own selection model — isSelected(),
setSelected(), scene.selectedItems() — does not stick for children of a
group like this; confirmed at runtime with a real QTest.mouseClick
simulation (not just a plain click failing to *register* as one — a
directly-called item.setSelected(True) reverts immediately too, with no
mouse event involved at all). So this app tracks selection itself, entirely
through CanvasScene.set_selection()/add_to_selection() (see
canvas/canvas_scene.py), and every selectable item calls this helper from
its own `mousePressEvent` override before deferring to the base
implementation for the actual drag handling.
"""

from __future__ import annotations

from PySide6.QtCore import Qt


def select_on_left_click(item, event) -> None:
    if event.button() != Qt.LeftButton:
        return
    scene = item.scene()
    if scene is None or not hasattr(scene, "set_selection"):
        return
    if event.modifiers() & Qt.ShiftModifier:
        scene.add_to_selection(item)
    else:
        scene.set_selection([item])
