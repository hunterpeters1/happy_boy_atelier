"""The small set of "futuristic UI accents" gated by
settings.futuristic_accents_enabled() (Options > Settings…): a glow
pulse on the active placement-tool button (app/panels/layers_panel.py),
a fade-in for the resize/rotate handle frame on selection
(app/canvas/handle_frame.py), and softened movement-line curves
(app/layers/composition_layer.py). Each accent's off-state is asserted
alongside its on-state, since off must still be a fully working plain
fallback, never a missing feature.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QPointF, QRectF, QSettings
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsObject

from app import settings
from app.canvas.canvas_scene import CanvasScene
from app.canvas.handle_frame import HandleFrame
from app.layers.composition_layer import MovementLineItem, _smooth_polyline_path
from app.panels.layers_panel import LayersPanel
from app.project import CanvasSpec


@pytest.fixture
def clean_accents_setting(qapp):
    QSettings().remove("settings/futuristicAccentsEnabled")
    yield
    QSettings().remove("settings/futuristicAccentsEnabled")


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


# -- tool button glow -----------------------------------------------------

def test_activating_a_tool_applies_a_glow_effect_when_accents_on(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(True)
    scene = _scene(qapp)
    panel = LayersPanel(scene)

    panel._activate_tool("focal_primary")

    btn = panel._tool_buttons["focal_primary"]
    assert isinstance(btn.graphicsEffect(), QGraphicsDropShadowEffect)
    assert "focal_primary" in panel._tool_glow_anims


def test_activating_a_tool_has_no_glow_effect_when_accents_off(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(False)
    scene = _scene(qapp)
    panel = LayersPanel(scene)

    panel._activate_tool("focal_primary")

    btn = panel._tool_buttons["focal_primary"]
    assert btn.graphicsEffect() is None
    assert panel._tool_glow_anims == {}


def test_deactivating_a_tool_removes_its_glow_effect(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(True)
    scene = _scene(qapp)
    panel = LayersPanel(scene)

    panel._activate_tool("focal_primary")
    panel._activate_tool("focal_primary")  # clicking the same tool again deactivates it

    btn = panel._tool_buttons["focal_primary"]
    assert btn.graphicsEffect() is None
    assert panel._tool_glow_anims == {}


def test_switching_tools_moves_the_glow_to_the_newly_active_button(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(True)
    scene = _scene(qapp)
    panel = LayersPanel(scene)

    panel._activate_tool("focal_primary")
    panel._activate_tool("focal_secondary")

    assert panel._tool_buttons["focal_primary"].graphicsEffect() is None
    assert isinstance(panel._tool_buttons["focal_secondary"].graphicsEffect(), QGraphicsDropShadowEffect)
    assert list(panel._tool_glow_anims.keys()) == ["focal_secondary"]


# -- handle frame fade-in --------------------------------------------------

class _FakeTarget(QGraphicsObject):
    """A minimal stand-in for ReferenceImageItem: HandleFrame's corner/
    rotate handles need a real QGraphicsItem as their Qt parent, and
    set_active()'s fade animation is parented to the target itself,
    which needs a real QObject -- QGraphicsObject is both, unlike a
    plain QGraphicsItem/QGraphicsRectItem.
    """

    def natural_size(self):
        return (100.0, 100.0)

    def boundingRect(self) -> QRectF:
        return QRectF(-50, -50, 100, 100)

    def paint(self, painter, option, widget=None) -> None:
        pass


def test_handle_frame_starts_transparent_and_animates_in_when_accents_on(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(True)
    frame = HandleFrame(_FakeTarget())

    frame.set_active(True)

    assert frame._fade_anim is not None
    for h in [*frame._corners, frame._rotate]:
        assert h.isVisible() is True
        assert h.opacity() == 0.0  # animation just started, not yet advanced


def test_handle_frame_is_fully_opaque_immediately_when_accents_off(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(False)
    frame = HandleFrame(_FakeTarget())

    frame.set_active(True)

    assert frame._fade_anim is None
    for h in [*frame._corners, frame._rotate]:
        assert h.isVisible() is True
        assert h.opacity() == 1.0


def test_handle_frame_deactivate_is_instant_regardless_of_accents_setting(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(True)
    frame = HandleFrame(_FakeTarget())
    frame.set_active(True)

    frame.set_active(False)

    assert frame._fade_anim is None
    for h in [*frame._corners, frame._rotate]:
        assert h.isVisible() is False
        assert h.opacity() == 1.0  # reset, ready for next time


# -- softened movement-line curve ------------------------------------------

def test_smooth_polyline_path_starts_and_ends_at_the_real_points():
    points = [QPointF(0, 0), QPointF(50, 10), QPointF(100, 0)]
    path = _smooth_polyline_path(points)

    assert path.elementCount() > 0
    start = path.elementAt(0)
    assert (start.x, start.y) == (0.0, 0.0)
    end = path.elementAt(path.elementCount() - 1)
    assert (end.x, end.y) == (100.0, 0.0)


def test_smooth_polyline_path_is_a_straight_line_for_two_points():
    points = [QPointF(0, 0), QPointF(40, 40)]
    path = _smooth_polyline_path(points)

    # A 2-point path is just moveTo + lineTo -- nothing to smooth.
    assert path.elementCount() == 2


def test_movement_line_paints_without_error_in_both_accent_states(qapp, clean_accents_setting):
    from PySide6.QtGui import QImage, QPainter

    line = MovementLineItem([QPointF(0, 0), QPointF(30, 20), QPointF(60, 0)])
    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    try:
        settings.set_futuristic_accents_enabled(True)
        line.paint(painter, None)
        settings.set_futuristic_accents_enabled(False)
        line.paint(painter, None)
    finally:
        painter.end()
