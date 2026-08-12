"""Project Panel row-button hover-reveal: item rows rest dim and rise to
full opacity on command, but a row whose lock/visibility has been toggled
away from its default must stay legible (not fade to near-invisible) even
at rest — see _RowButtons' docstring in app/panels/layers_panel.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.panels.layers_panel import LayersPanel, _RowButtons
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def _reference_row_buttons(panel: LayersPanel, item) -> _RowButtons:
    row = panel._row_for_obj[id(item)]
    return row.treeWidget().itemWidget(row, 1)


def test_fresh_default_state_item_row_rests_dim(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    panel = LayersPanel(scene)
    panel.refresh_structure()

    buttons = _reference_row_buttons(panel, item)
    assert buttons.hoverable is True
    assert buttons.is_default_state() is True
    assert buttons._fade.effect.opacity() == _RowButtons._REST_OPACITY_DEFAULT


def test_locked_item_row_rests_near_full_opacity(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    item.set_locked(True)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    buttons = _reference_row_buttons(panel, item)
    assert buttons.is_default_state() is False
    assert buttons._fade.effect.opacity() == _RowButtons._REST_OPACITY_NONDEFAULT


def test_hovering_a_row_reveals_full_opacity_then_rests_back_down(qapp):
    """The fade itself is an animated QPropertyAnimation (150ms, see
    app/scrollbars.py's OpacityFade) that only actually reaches its target
    opacity once the Qt event loop pumps a few frames — not something a
    synchronous headless test can observe directly. What's checked here is
    that set_row_hovered() aims the fade at the right target, which is the
    actual behavioral contract RowHoverFilter depends on.
    """
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    panel = LayersPanel(scene)
    panel.refresh_structure()

    buttons = _reference_row_buttons(panel, item)
    buttons.set_row_hovered(True)
    assert buttons._fade.animation.endValue() == 1.0

    buttons.set_row_hovered(False)
    assert buttons._fade.animation.endValue() == _RowButtons._REST_OPACITY_DEFAULT


def test_layer_header_row_buttons_are_not_hoverable(qapp):
    scene = _scene(qapp)
    panel = LayersPanel(scene)
    panel.refresh_structure()

    header_row = panel._layer_rows[list(panel._layer_rows.keys())[0]]
    header_buttons = header_row.treeWidget().itemWidget(header_row, 1)
    assert header_buttons.hoverable is False
    assert header_buttons._fade is None
