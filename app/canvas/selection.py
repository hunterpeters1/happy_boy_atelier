"""Shared click-to-select helper.

Every interactive marker (reference image, focal point, note, movement
line, light source, direction arrow, vanishing point, horizon) lives inside
a QGraphicsItemGroup layer with `setHandlesChildEvents(False)` so each child
manages its own mouse events. Relying purely on Qt's default per-item
mousePressEvent to flip selection state turned out to be unreliable once
items are nested this way — a plain click would move an item without ever
marking it selected, so the Properties panel and resize/rotate handles
(which both key off `isSelected()`) never appeared. Every selectable item
now explicitly calls this helper from its own `mousePressEvent` override
before deferring to the base implementation for the actual drag handling.
"""

from __future__ import annotations

from PySide6.QtCore import Qt


def select_on_left_click(item, event) -> None:
    if event.button() != Qt.LeftButton:
        return
    scene = item.scene()
    if scene is not None and not (event.modifiers() & Qt.ShiftModifier):
        scene.clearSelection()
    item.setSelected(True)
    # Belt-and-suspenders: also push the clicked item directly to whoever
    # is listening, instead of relying solely on Qt re-deriving it later
    # from scene.selectedItems()/isSelected(). A plain press-then-release
    # with no movement should be indistinguishable from the first instant
    # of a press-then-drag as far as selection is concerned, but if
    # anything upstream ever fails to notice the state flip, this signal
    # still gets the Properties panel pointed at the right item.
    if scene is not None and hasattr(scene, "item_activated"):
        scene.item_activated.emit(item)
