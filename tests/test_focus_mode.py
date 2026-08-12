"""Focus Mode ("Clear the Bench"): hides the toolbar and every dock, and
restores each dock to exactly its pre-focus visibility on exit — not a
blanket re-show, since Properties/Swatches are tabified and only one may
have actually been visible going in. See MainWindow.toggle_focus_mode().
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
