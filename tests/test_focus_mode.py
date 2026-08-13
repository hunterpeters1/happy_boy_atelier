"""Focus Mode ("Clear the Bench"): hides the toolbar and every dock, and
restores each dock to exactly its pre-focus visibility on exit — not a
blanket re-show, since Properties/Swatches are tabified and only one may
have actually been visible going in. See MainWindow.toggle_focus_mode().
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt

from app.main_window import MainWindow


def _window(qapp) -> MainWindow:
    win = MainWindow()
    # isVisible() only reflects real on-screen state once the top-level
    # window itself has been shown -- without this every child dock/
    # toolbar reports False regardless of Focus Mode.
    win.show()
    return win


def test_focus_mode_hides_toolbar_and_docks(qapp):
    win = _window(qapp)
    assert win.focus_mode_action.isChecked() is False

    win.focus_mode_action.trigger()

    assert win.focus_mode_action.isChecked() is True
    assert win.toolbar.isVisible() is False
    assert win.layers_dock.isVisible() is False
    assert win.properties_dock.isVisible() is False
    assert win.swatches_dock.isVisible() is False


def test_focus_mode_restores_prior_dock_visibility_exactly(qapp):
    """A dock the artist had already hidden before entering Focus Mode
    must stay hidden on exit, not get reshown along with the others.
    """
    win = _window(qapp)
    win.properties_dock.setVisible(False)

    win.focus_mode_action.trigger()  # enter
    win.focus_mode_action.trigger()  # exit

    assert win.focus_mode_action.isChecked() is False
    assert win.toolbar.isVisible() is True
    assert win.layers_dock.isVisible() is True
    assert win.properties_dock.isVisible() is False
    assert win.swatches_dock.isVisible() is True


def test_focus_mode_makes_desk_transparent_and_restores_it(qapp):
    win = _window(qapp)
    win.meta.bg_color = "#336699"
    win.scene.set_bg_color(win.meta.bg_color)

    win.focus_mode_action.trigger()  # enter
    assert win.scene._desk_transparent is True
    assert win.testAttribute(Qt.WA_TranslucentBackground) is True
    # Neither the live scene color nor the project's own saved preference
    # is touched -- set_desk_transparent() is a separate rendering flag,
    # not a color override.
    assert win.scene._bg_color == "#336699"
    assert win.meta.bg_color == "#336699"

    win.focus_mode_action.trigger()  # exit
    assert win.scene._desk_transparent is False
    assert win.testAttribute(Qt.WA_TranslucentBackground) is False
    assert win.scene._bg_color == "#336699"
    assert win.meta.bg_color == "#336699"


def test_focus_mode_clears_the_view_and_viewport_for_transparency(qapp):
    """The actual see-through mechanism has three moving parts beyond the
    scene flag itself: the view's own fallback background brush, and the
    viewport widget's translucency attribute + auto-fill, both of which
    would otherwise repaint an opaque backdrop under the scene before
    drawBackground() gets a chance to leave those pixels untouched.
    """
    win = _window(qapp)

    win.focus_mode_action.trigger()  # enter
    assert win.view.backgroundBrush().style() == Qt.NoBrush
    assert win.view.viewport().testAttribute(Qt.WA_TranslucentBackground) is True
    assert win.view.viewport().autoFillBackground() is False

    win.focus_mode_action.trigger()  # exit
    assert win.view.backgroundBrush().style() != Qt.NoBrush
    assert win.view.viewport().testAttribute(Qt.WA_TranslucentBackground) is False
    assert win.view.viewport().autoFillBackground() is True


def test_focus_mode_shows_opacity_slider_and_resets_it_on_exit(qapp):
    win = _window(qapp)
    assert win.focus_opacity_slider.isHidden()

    win.focus_mode_action.trigger()  # enter
    assert not win.focus_opacity_slider.isHidden()
    assert not win.focus_opacity_label.isHidden()

    win.focus_opacity_slider.setValue(50)
    # The offscreen QPA platform quantizes window opacity to 8-bit
    # precision internally (confirmed: reads back ~0.498 for 0.5, not
    # exactly 0.5) -- a real platform applies it exactly, so this only
    # needs to confirm setWindowOpacity was actually driven by the slider.
    assert abs(win.windowOpacity() - 0.5) < 0.01

    win.focus_mode_action.trigger()  # exit
    assert win.focus_opacity_slider.isHidden()
    assert win.focus_opacity_label.isHidden()
    assert win.focus_opacity_slider.value() == 100
    assert win.windowOpacity() == 1.0
