"""MainWindow dock-rebuild behavior. Focus Mode's own tests already cover
toolbar/dock show-hide (test_focus_mode.py); this file covers
_rebuild_workspace()'s dock lifecycle itself -- specifically
library_dock, the one dock that's stable across project switches while
layers_dock (its tab partner) is a fresh QDockWidget every time.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from app import library, project_templates
from app.main_window import MainWindow
from app.project import CanvasSpec
from app.project_templates import _SETTINGS_KEY as _TEMPLATES_SETTINGS_KEY


@pytest.fixture
def library_dir_tmp(qapp):
    QStandardPaths.setTestModeEnabled(True)
    path = library.library_dir()
    shutil.rmtree(path, ignore_errors=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def clean_templates(qapp):
    from PySide6.QtCore import QSettings
    QSettings().remove(_TEMPLATES_SETTINGS_KEY)
    yield
    QSettings().remove(_TEMPLATES_SETTINGS_KEY)


def _window(qapp) -> MainWindow:
    win = MainWindow()
    win.show()
    QApplication.processEvents()
    return win


def test_library_dock_exists_and_is_tabified_with_project_dock(library_dir_tmp, qapp):
    win = _window(qapp)
    assert win.library_dock in win.tabifiedDockWidgets(win.layers_dock)


def test_library_dock_stays_tabified_across_repeated_project_switches(library_dir_tmp, qapp):
    """layers_dock is a fresh QDockWidget on every _rebuild_workspace()
    call; library_dock is not -- confirm the tabify pairing is correctly
    re-established against each new layers_dock, not just the first one.
    """
    win = _window(qapp)

    for _ in range(3):
        win._new_project(CanvasSpec())
        QApplication.processEvents()
        assert win.library_dock in win.tabifiedDockWidgets(win.layers_dock)


def test_old_project_dock_is_detached_after_a_project_switch(library_dir_tmp, qapp):
    win = _window(qapp)
    old_layers_dock = win.layers_dock

    win._new_project(CanvasSpec())
    QApplication.processEvents()

    assert win.layers_dock is not old_layers_dock
    assert old_layers_dock.parent() is None


def test_save_as_template_persists_current_spec_and_guides(library_dir_tmp, clean_templates, qapp, monkeypatch):
    win = _window(qapp)
    win._new_project(CanvasSpec(width=7.0, height=5.0, unit="in"))
    win.scene.guides_layer.set_rule_of_thirds(True)

    monkeypatch.setattr("app.main_window.QInputDialog.getText", lambda *a, **k: ("My Template", True))
    win.save_as_template()

    templates = project_templates.load_templates()
    assert templates["My Template"]["width"] == 7.0
    assert templates["My Template"]["height"] == 5.0
    assert templates["My Template"]["unit"] == "in"
    assert templates["My Template"]["guides"]["rule_of_thirds"] is True


def test_save_as_template_with_empty_name_or_cancel_does_nothing(library_dir_tmp, clean_templates, qapp, monkeypatch):
    win = _window(qapp)
    win._new_project(CanvasSpec())

    monkeypatch.setattr("app.main_window.QInputDialog.getText", lambda *a, **k: ("", False))
    win.save_as_template()
    assert project_templates.load_templates() == {}

    monkeypatch.setattr("app.main_window.QInputDialog.getText", lambda *a, **k: ("  ", True))
    win.save_as_template()
    assert project_templates.load_templates() == {}


def test_new_project_applies_supplied_guides(library_dir_tmp, clean_templates, qapp):
    win = _window(qapp)
    win._new_project(CanvasSpec(), guides={"rule_of_thirds": True, "golden_ratio": True, "inch_grid": False})

    assert win.scene.guides_layer.thirds.isVisible() is True
    assert win.scene.guides_layer.golden.isVisible() is True
    assert win.scene.guides_layer.grid.isVisible() is False


def test_show_phone_upload_creates_and_shows_a_dialog(library_dir_tmp, qapp, monkeypatch):
    from app.dialogs import phone_upload_dialog as dlg_module

    # The wiring tests below only care about MainWindow's own instance
    # tracking (raise existing vs. build a new one, close-cleanup) -- not
    # whether a real uploader process can actually launch on this
    # (non-Windows, no real venv guaranteed) test machine. Short-circuiting
    # _venv_python() to None takes the dialog straight to its "not set up"
    # message without ever touching QProcess.
    monkeypatch.setattr(dlg_module, "_venv_python", lambda: None)

    win = _window(qapp)
    win._show_phone_upload()

    assert win._phone_upload_dialog is not None
    assert win._phone_upload_dialog.isVisible()


def test_show_phone_upload_raises_existing_dialog_instead_of_duplicating(
    library_dir_tmp, qapp, monkeypatch
):
    from app.dialogs import phone_upload_dialog as dlg_module

    monkeypatch.setattr(dlg_module, "_venv_python", lambda: None)

    win = _window(qapp)
    win._show_phone_upload()
    first = win._phone_upload_dialog

    win._show_phone_upload()

    assert win._phone_upload_dialog is first


def test_show_phone_upload_creates_a_fresh_dialog_after_the_last_one_closed(
    library_dir_tmp, qapp, monkeypatch
):
    from app.dialogs import phone_upload_dialog as dlg_module

    monkeypatch.setattr(dlg_module, "_venv_python", lambda: None)

    win = _window(qapp)
    win._show_phone_upload()
    first = win._phone_upload_dialog
    first.close()

    win._show_phone_upload()

    # A stale reference to an already-closed dialog (whose uploader
    # process, if any, has already stopped) must not be silently reused
    # -- reopening after a close needs a genuinely new attempt.
    assert win._phone_upload_dialog is not first
    assert win._phone_upload_dialog.isVisible()


def test_closing_main_window_also_closes_the_phone_upload_dialog(
    library_dir_tmp, qapp, monkeypatch
):
    from app.dialogs import phone_upload_dialog as dlg_module

    monkeypatch.setattr(dlg_module, "_venv_python", lambda: None)

    win = _window(qapp)
    win._show_phone_upload()
    assert win._phone_upload_dialog.isVisible()

    win.close()

    assert not win._phone_upload_dialog.isVisible()


def test_new_project_without_guides_leaves_defaults(library_dir_tmp, clean_templates, qapp):
    win = _window(qapp)
    win._new_project(CanvasSpec())

    assert win.scene.guides_layer.thirds.isVisible() is False
    assert win.scene.guides_layer.golden.isVisible() is False
    assert win.scene.guides_layer.grid.isVisible() is False
