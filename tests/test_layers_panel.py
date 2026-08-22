"""Project Panel row-button hover-reveal: item rows rest dim and rise to
full opacity on command, but a row whose lock/visibility has been toggled
away from its default must stay legible (not fade to near-invisible) even
at rest — see _RowButtons' docstring in app/panels/layers_panel.py.

Also covers the contact-sheet thumbnail icons reference-image rows use in
place of the generic "image" glyph (_reference_thumbnail_icon()).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF, QSize
from PySide6.QtGui import QColor, QPixmap

from app import constants as C
from app.canvas.canvas_scene import CanvasScene
from app.panels.layers_panel import LayersPanel, _RowButtons, _reference_thumbnail_icon
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


# -- contact-sheet thumbnails -------------------------------------------

def test_reference_thumbnail_icon_is_square_regardless_of_source_aspect(qapp):
    pixmap = QPixmap(300, 150)  # 2:1, non-square source
    pixmap.fill(QColor(10, 200, 10))

    from app.layers.reference_layer import ReferenceImageItem
    item = ReferenceImageItem("test-thumb", pixmap, 300, 150)

    icon = _reference_thumbnail_icon(item, C.TOOL_ROW_ICON_PX)
    pm = icon.pixmap(QSize(C.TOOL_ROW_ICON_PX, C.TOOL_ROW_ICON_PX))
    assert pm.width() == C.TOOL_ROW_ICON_PX
    assert pm.height() == C.TOOL_ROW_ICON_PX


def test_reference_thumbnail_icon_reflects_actual_pixel_content(qapp):
    pixmap = QPixmap(60, 60)
    pixmap.fill(QColor(220, 30, 30))

    from app.layers.reference_layer import ReferenceImageItem
    item = ReferenceImageItem("test-thumb-2", pixmap, 60, 60)

    icon = _reference_thumbnail_icon(item, C.TOOL_ROW_ICON_PX)
    pm = icon.pixmap(QSize(C.TOOL_ROW_ICON_PX, C.TOOL_ROW_ICON_PX))
    center = pm.toImage().pixelColor(C.TOOL_ROW_ICON_PX // 2, C.TOOL_ROW_ICON_PX // 2)
    assert center.red() > center.green()
    assert center.red() > center.blue()


def test_reference_image_row_gets_a_thumbnail_not_the_generic_glyph(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(80, 80)
    pixmap.fill(QColor(50, 50, 220))
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0))
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row = panel._row_for_obj[id(item)]
    pm = row.icon(0).pixmap(QSize(C.TOOL_ROW_ICON_PX, C.TOOL_ROW_ICON_PX))
    assert pm.width() == C.TOOL_ROW_ICON_PX
    center = pm.toImage().pixelColor(C.TOOL_ROW_ICON_PX // 2, C.TOOL_ROW_ICON_PX // 2)
    assert center.blue() > center.red()  # reflects the blue source photo


def test_non_reference_item_row_keeps_its_glyph_icon(qapp):
    """Composition/perspective/lighting markers aren't photos -- they
    should keep their existing glyph icon, not go through the thumbnail
    path at all.
    """
    scene = _scene(qapp)
    item = scene.composition_layer.add_focal_point("primary", QPointF(0, 0))
    panel = LayersPanel(scene)
    panel.refresh_structure()

    row = panel._row_for_obj[id(item)]
    assert not row.icon(0).isNull()


def test_minimum_width_fits_every_layer_header_label(qapp):
    """Regression test for a real bug: the panel's minimum width was
    once a hardcoded guess sized for item rows, which left the layer
    header rows' larger bold font clipped ("Composition"/"Perspective"
    rendered with a trailing "..."). _compute_minimum_width() must
    guarantee column 0 is wide enough for every header label, measured
    against the actual running font/style rather than a fixed constant.
    """
    scene = _scene(qapp)
    panel = LayersPanel(scene)
    panel.resize(panel.minimumWidth(), 600)
    panel.show()

    tree = panel.tree
    for kind, row in panel._layer_rows.items():
        needed = tree.indentation() + tree.sizeHintForIndex(tree.indexFromItem(row, 0)).width()
        assert tree.columnWidth(0) >= needed, f"{kind} header label would clip at the panel's minimum width"


def test_minimum_width_grows_with_the_header_font(qapp):
    """The floor must track the actual rendered font, not just a fixed
    number measured once on one machine -- this is what makes it correct
    across different DPI scaling, font substitution, and OS text-size
    accessibility settings, none of which can be hardcoded for in advance.
    """
    scene = _scene(qapp)
    panel = LayersPanel(scene)
    baseline = panel.minimumWidth()

    for row in panel._layer_rows.values():
        font = row.font(0)
        font.setPointSize(font.pointSize() + 10)
        row.setFont(0, font)

    assert panel._compute_minimum_width() > baseline
