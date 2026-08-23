"""SwatchesPanel's eyedropper activation button -- moved here from the
Project Panel's Reference tool row so the trigger (this button) and its
output (the live readout, pinned swatches) live in the same dock. See
CanvasScene.active_tool_changed, the signal that keeps this button and
every other tool-activation button (LayersPanel's) in sync with each
other regardless of which one actually changed the active tool.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from app import settings
from app.canvas.canvas_scene import CanvasScene
from app.panels.layers_panel import LayersPanel
from app.panels.swatches_panel import SwatchesPanel
from app.project import CanvasSpec, ProjectMeta


@pytest.fixture
def clean_accents_setting(qapp):
    QSettings().remove("settings/futuristicAccentsEnabled")
    yield
    QSettings().remove("settings/futuristicAccentsEnabled")


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def test_eyedropper_button_starts_unchecked(qapp):
    panel = SwatchesPanel(_scene(qapp), ProjectMeta())
    assert panel._eyedropper_btn.isChecked() is False


def test_clicking_the_eyedropper_button_arms_the_tool(qapp):
    scene = _scene(qapp)
    panel = SwatchesPanel(scene, ProjectMeta())

    panel._toggle_eyedropper()

    assert scene.active_tool() == "eyedropper"
    assert panel._eyedropper_btn.isChecked() is True


def test_clicking_the_eyedropper_button_again_disarms_it(qapp):
    scene = _scene(qapp)
    panel = SwatchesPanel(scene, ProjectMeta())

    panel._toggle_eyedropper()
    panel._toggle_eyedropper()

    assert scene.active_tool() is None
    assert panel._eyedropper_btn.isChecked() is False


def test_eyedropper_button_applies_glow_when_accents_on(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(True)
    scene = _scene(qapp)
    panel = SwatchesPanel(scene, ProjectMeta())

    panel._toggle_eyedropper()

    assert isinstance(panel._eyedropper_btn.graphicsEffect(), QGraphicsDropShadowEffect)


def test_eyedropper_button_has_no_glow_when_accents_off(qapp, clean_accents_setting):
    settings.set_futuristic_accents_enabled(False)
    scene = _scene(qapp)
    panel = SwatchesPanel(scene, ProjectMeta())

    panel._toggle_eyedropper()

    assert panel._eyedropper_btn.graphicsEffect() is None


def test_eyedropper_is_no_longer_a_project_panel_tool_button(qapp):
    scene = _scene(qapp)
    layers = LayersPanel(scene)
    assert "eyedropper" not in layers._tool_buttons


def test_arming_a_project_panel_tool_disarms_the_eyedropper_button(qapp):
    scene = _scene(qapp)
    layers = LayersPanel(scene)
    swatches = SwatchesPanel(scene, ProjectMeta())

    swatches._toggle_eyedropper()
    assert swatches._eyedropper_btn.isChecked() is True

    layers._activate_tool("focal_primary")

    assert swatches._eyedropper_btn.isChecked() is False
    assert layers._tool_buttons["focal_primary"].isChecked() is True


def test_arming_the_eyedropper_disarms_a_project_panel_tool(qapp):
    scene = _scene(qapp)
    layers = LayersPanel(scene)
    swatches = SwatchesPanel(scene, ProjectMeta())

    layers._activate_tool("focal_primary")
    assert layers._tool_buttons["focal_primary"].isChecked() is True

    swatches._toggle_eyedropper()

    assert layers._tool_buttons["focal_primary"].isChecked() is False
    assert swatches._eyedropper_btn.isChecked() is True


def test_escape_disarms_the_eyedropper_button_too(qapp):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    scene = _scene(qapp)
    swatches = SwatchesPanel(scene, ProjectMeta())
    swatches._toggle_eyedropper()
    assert swatches._eyedropper_btn.isChecked() is True

    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    scene.keyPressEvent(event)

    assert scene.active_tool() is None
    assert swatches._eyedropper_btn.isChecked() is False
