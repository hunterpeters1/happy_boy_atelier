"""Shared base for every top-level, click-to-select marker on the drafting
table: reference images, focal points, notes, movement lines, light
sources, direction arrows, vanishing points, and the horizon line.

Consolidates two things that were previously duplicated across eight
separate classes:

- **Click-to-select.** Relying on Qt's default per-item mousePressEvent
  to flip selection state turned out to be unreliable once items live
  inside a QGraphicsItemGroup layer with `setHandlesChildEvents(False)` —
  dragging worked, but a plain click never reliably registered as a
  selection, so the Properties panel and (for reference images) the
  resize/rotate handles never showed up. See `canvas/selection.py` for
  the explicit fix; this class is where it's wired in exactly once.
- **Per-item lock state.** Previously only `ReferenceImageItem` had a
  `set_locked`/`is_locked` pair — composition/lighting/perspective layer
  groups toggled `ItemIsMovable`/`ItemIsSelectable` flags directly on
  their children instead of going through a shared method, so those
  items had no way to report "am I locked" at all.

Subclasses that need extra behavior on a selection or lock change
override the hooks below rather than re-implementing `mousePressEvent` or
`set_locked` from scratch.

This is also the one place whole-item drag commits to undo/redo (Phase
0.2): `mousePressEvent` snapshots (pos, rotation, scale) before Qt's
default drag handling runs, and `mouseReleaseEvent` compares against the
post-drag state, pushing a single `TransformCommand` only if something
actually moved. Handle-driven scale/rotate (see `canvas/handle_frame.py`)
reuses the same `begin_transform`/`commit_transform` pair from outside
this class, since those drags originate on a child handle item, not here.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from .selection import select_on_left_click


class InteractiveItem(QGraphicsObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._locked = False
        self._transform_snapshot = None
        # NOT Qt's own isSelected()/setSelected() — confirmed at runtime
        # (a real QTest.mouseClick simulation, not just informal
        # suspicion) that selection state does not stick for children of a
        # QGraphicsItemGroup with setHandlesChildEvents(False), which is
        # every layer in this app. This flag, driven exclusively by
        # CanvasScene's own selection tracking (canvas_scene.py), is the
        # one thing paint() and every other consumer should check instead.
        self._app_selected = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

    # -- lock -------------------------------------------------------------
    def is_locked(self) -> bool:
        return self._locked

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.setFlag(QGraphicsItem.ItemIsMovable, not locked)
        self.setFlag(QGraphicsItem.ItemIsSelectable, not locked)
        if locked and self._app_selected:
            scene = self.scene()
            if scene is not None and hasattr(scene, "remove_from_selection"):
                scene.remove_from_selection(self)
        self._on_locked_changed(locked)
        self.update()

    # -- selection ----------------------------------------------------------
    def is_app_selected(self) -> bool:
        return self._app_selected

    def set_app_selected(self, selected: bool) -> None:
        if self._app_selected == selected:
            return
        self._app_selected = selected
        self.update()

    def _on_locked_changed(self, locked: bool) -> None:
        """Hook: react to a lock state change (e.g. hide transform
        handles, swap the cursor). No-op by default.
        """

    # -- click-to-select ----------------------------------------------------
    def _is_click_selectable(self) -> bool:
        """Hook: suppress selection during a special interaction state
        (e.g. a reference image mid-crop). True by default.
        """
        return True

    def mousePressEvent(self, event) -> None:
        if not self._locked and self._is_click_selectable():
            select_on_left_click(self, event)
        self.begin_transform()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.commit_transform()

    # -- undo/redo: whole-item transform capture -----------------------
    def _snapshot_transform(self):
        return (self.pos(), self.rotation(), self.scale())

    def begin_transform(self) -> None:
        """Call at the start of any drag/handle interaction that may move,
        rotate, or scale this item. Idempotent-safe to call even when
        nothing ends up changing — commit_transform() is a no-op then.
        """
        self._transform_snapshot = self._snapshot_transform()

    def commit_transform(self) -> None:
        """Call at the end of the interaction started by begin_transform().
        Pushes a single TransformCommand onto the scene's undo stack, only
        if the transform actually changed.
        """
        if self._transform_snapshot is None:
            return
        old = self._transform_snapshot
        self._transform_snapshot = None
        new = self._snapshot_transform()
        if old == new:
            return
        scene = self.scene()
        if scene is None or not hasattr(scene, "undo_stack"):
            return
        from .undo_commands import TransformCommand
        scene.undo_stack.push(TransformCommand(self, old, new))
