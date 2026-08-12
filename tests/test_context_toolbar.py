"""SelectionContextToolbar (app/canvas/context_toolbar.py): the floating
mini-toolbar of high-frequency single-item actions (Duplicate, Flip
Horizontal, Lock, Delete) that appears near the current selection.
Buttons route to the exact same CanvasScene/item methods the right-click
context menu and Edit menu already use, so undo/redo is exercised via
those, not reinvented here — these tests focus on the toolbar's own
show/hide/reposition/suspend behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.canvas.canvas_view import CanvasView
from app.project import CanvasSpec


def _view(qapp) -> tuple[CanvasView, CanvasScene]:
    # Returns both, not just the view -- QGraphicsScene isn't Qt-parented
    # to its view (a view doesn't own its scene), so if the caller only
    # keeps `view` and lets the local `scene` go out of scope, Python's
    # GC collects it and view.scene() comes back None.
    scene = CanvasScene(CanvasSpec())
    view = CanvasView(scene)
    view.resize(800, 600)
    view.show()
    view.fit_canvas(scene.canvas_rect())
    return view, scene


def test_hidden_with_no_selection(qapp):
    view, _scene = _view(qapp)
    assert view._context_toolbar.isVisible() is False


def test_shown_for_a_single_selected_reference_image(qapp):
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(200, 300))
    scene.set_selection([item])

    toolbar = view._context_toolbar
    assert toolbar.isVisible() is True
    assert toolbar._flip_btn.isVisible() is True
    assert toolbar._lock_btn.isVisible() is True


def test_hidden_for_multi_select(qapp):
    view, scene = _view(qapp)
    a = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(0, 0))
    b = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(400, 0))
    scene.set_selection([a, b])

    assert view._context_toolbar.isVisible() is False


def test_hidden_for_a_non_reference_marker_without_flip(qapp):
    """A focal point has no flip_horizontal (that's reference-image-only)
    but does support lock (every InteractiveItem does) -- the toolbar
    should still show (Duplicate/Delete/Lock are generic), with only Flip
    hiding itself rather than acting on an item that doesn't support it.
    """
    view, scene = _view(qapp)
    focal = scene.composition_layer.add_focal_point("primary", QPointF(100, 100))
    scene.set_selection([focal])

    toolbar = view._context_toolbar
    assert toolbar.isVisible() is True
    assert toolbar._flip_btn.isVisible() is False
    assert toolbar._lock_btn.isVisible() is True


def test_flip_button_pushes_one_undo_step(qapp):
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(200, 300))
    scene.set_selection([item])

    old_scale_x = item._scale_x
    view._context_toolbar._flip_btn.click()

    assert item._scale_x == -old_scale_x
    assert scene.undo_stack.count() == 1


def test_lock_button_locks_and_hides_toolbar(qapp):
    """Locking a selected item deselects it (InteractiveItem.set_locked()'s
    existing, pre-existing behavior -- a locked item isn't interactively
    selectable) -- the toolbar hiding itself right after is the correct
    consequence of that, not a bug to work around.
    """
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(200, 300))
    scene.set_selection([item])

    view._context_toolbar._lock_btn.click()

    assert item.is_locked() is True
    assert scene.selected_items() == []
    assert view._context_toolbar.isVisible() is False


def test_duplicate_button_adds_an_item(qapp):
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(200, 300))
    scene.set_selection([item])

    view._context_toolbar._duplicate_btn.click()

    assert len(scene.reference_layer.items()) == 2


def test_delete_button_removes_item_and_hides_toolbar(qapp):
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(200, 300))
    scene.set_selection([item])

    view._context_toolbar._delete_btn.click()

    assert item not in scene.reference_layer.items()
    assert view._context_toolbar.isVisible() is False


def test_suspend_hides_toolbar_and_resume_restores_it(qapp):
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(200, 300))
    scene.set_selection([item])
    toolbar = view._context_toolbar
    assert toolbar.isVisible() is True

    toolbar.set_suspended(True)
    assert toolbar.isVisible() is False

    toolbar.set_suspended(False)
    assert toolbar.isVisible() is True


def test_reposition_follows_zoom_changes(qapp):
    view, scene = _view(qapp)
    item = scene.reference_layer.add_image(QPixmap(50, 50), 500, 500, QPointF(400, 500))
    scene.set_selection([item])
    toolbar = view._context_toolbar

    pos_before = toolbar.pos()
    view.zoom_in()
    assert toolbar.pos() != pos_before
