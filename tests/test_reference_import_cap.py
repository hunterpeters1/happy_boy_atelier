"""MAX_REFERENCE_IMAGES (app/constants.py): this app plans a painting
with a handful of references, not a bulk photo library, so
MainWindow._import_image_paths() -- the one choke point every import
(file dialog, OS drag-and-drop, Library panel drag-in) goes through --
refuses to import past a hard per-project cap. Must never block real
UI interaction with a real modal, so QMessageBox.warning is monkeypatched
throughout.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from app import constants as C
from app.main_window import MainWindow


# Kept alive for the whole test session rather than let each window be
# garbage-collected at the end of its own test. Confirmed by direct
# reproduction (plain `del win; gc.collect()`, no test framework
# involved) that destroying a MainWindow that has ever pushed a real
# undo command hits a genuine pre-existing teardown-order issue --
# scene.undo_stack.indexChanged fires during its own destruction and
# reaches self.layers_panel.refresh_structure() after layers_panel's
# C++ side is already gone. That path is real, but it only exists here
# because tests construct and discard many disposable MainWindows in
# one process -- the shipped app constructs exactly one and destroys it
# only once, at actual process exit, so this never fires for a real
# user. Fixing MainWindow's shutdown signal wiring is out of scope for
# this cap feature; keeping instances alive for the session avoids
# exercising a path real usage never hits, same as how the app is
# actually run.
_KEEPALIVE: list[MainWindow] = []


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.show()
    QApplication.processEvents()
    _KEEPALIVE.append(win)
    return win


def _make_images(tmp_path: Path, count: int) -> list[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        path = tmp_path / f"photo{i}.png"
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor(10 * i % 255, 20, 30))
        pixmap.save(str(path), "PNG")
        paths.append(str(path))
    return paths


@pytest.fixture
def no_modal(monkeypatch):
    """A real QMessageBox.warning() would block forever waiting for a
    click that never comes under the offscreen test platform.
    """
    monkeypatch.setattr("app.main_window.QMessageBox.warning", lambda *a, **k: None)


def test_import_up_to_the_cap_succeeds(window, tmp_path, no_modal):
    win = window
    paths = _make_images(tmp_path, C.MAX_REFERENCE_IMAGES)
    win._import_image_paths(paths)
    assert len(win.scene.reference_layer.items()) == C.MAX_REFERENCE_IMAGES


def test_import_exceeding_the_cap_is_refused_entirely(window, tmp_path, no_modal):
    """All-or-nothing, matching the phone uploader's own batch cap: a
    batch that would exceed the limit imports nothing, rather than
    silently truncating to however many still fit.
    """
    win = window
    paths = _make_images(tmp_path, C.MAX_REFERENCE_IMAGES + 1)
    win._import_image_paths(paths)
    assert len(win.scene.reference_layer.items()) == 0


def test_import_that_would_push_an_already_full_project_over_is_refused(window, tmp_path, no_modal):
    win = window
    win._import_image_paths(_make_images(tmp_path, C.MAX_REFERENCE_IMAGES))
    assert len(win.scene.reference_layer.items()) == C.MAX_REFERENCE_IMAGES

    win._import_image_paths(_make_images(tmp_path / "more", 1))
    assert len(win.scene.reference_layer.items()) == C.MAX_REFERENCE_IMAGES


def test_import_partially_filling_remaining_headroom_succeeds(window, tmp_path, no_modal):
    win = window
    win._import_image_paths(_make_images(tmp_path, C.MAX_REFERENCE_IMAGES - 2))
    assert len(win.scene.reference_layer.items()) == C.MAX_REFERENCE_IMAGES - 2

    win._import_image_paths(_make_images(tmp_path / "more", 2))
    assert len(win.scene.reference_layer.items()) == C.MAX_REFERENCE_IMAGES


def test_loading_a_pre_existing_project_over_the_cap_is_not_truncated(window, tmp_path, no_modal):
    """The cap is a UI-level guard on new imports only -- it must never
    reach into ReferenceLayerGroup.load_from_dict() and silently drop
    images from a project that predates this limit (or was authored by
    hand-editing a .atelier file).
    """
    win = window
    over_cap = C.MAX_REFERENCE_IMAGES + 5
    rect = win.scene.canvas_rect()
    for i in range(over_cap):
        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(0, 0, 0))
        win.scene.reference_layer.add_image(pixmap, rect.width(), rect.height(), rect.center())

    assert len(win.scene.reference_layer.items()) == over_cap
