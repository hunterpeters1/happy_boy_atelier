"""Corner rivets (CanvasScene.drawBackground), trim marks + dimension
callout (CanvasView.drawForeground), and the dock title bar rivets
(DockTitleBar) are direct QPainter code, not covered by the rest of the
headless test suite's serialization/undo-stack focus. These tests just
confirm every paint path runs cleanly under all four theme palettes
(COLOR_LINE, the rivet color, is theme-dependent — see app/themes.py) —
actual pixel appearance still needs the manual pass called for in the
UI-upgrade plan's verification section.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.canvas.canvas_view import CanvasView
from app.canvas.canvas_scene import CanvasScene
from app.panels.dock_title_bar import DockTitleBar
from app.project import CanvasSpec
from app.themes import ThemeMode, apply_palette


@pytest.mark.parametrize("mode", list(ThemeMode))
def test_canvas_and_dock_paint_paths_survive_every_theme(qapp, mode):
    apply_palette(mode)
    try:
        scene = CanvasScene(CanvasSpec())
        view = CanvasView(scene)
        view.resize(400, 300)
        view.grab()  # forces drawBackground()/drawForeground() to run

        bar = DockTitleBar("Project")
        bar.resize(200, 28)
        bar.grab()  # forces paintEvent()
    finally:
        apply_palette(ThemeMode.LIGHT)  # restore the app default for later tests
