"""Undo/redo command classes for CanvasScene's QUndoStack.

Scope (per Phase 0 decision): the undo stack covers content mutations only
— adding/removing objects, moving/scaling/rotating, cropping, text edits,
perspective changes, and artwork-related numeric properties (opacity, grid
line weight, grid spacing). Lock toggles, visibility toggles, and other UI/
workflow state are deliberately excluded — undo represents reversing
changes to the artwork setup, not general application state, so those
stay direct, un-undoable calls at their call sites.

Every command here follows the same "capture on press, commit a single
command on release, only if something changed" shape described in
V2_ROADMAP.md, rather than pushing one command per intermediate drag
event.
"""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand


class AddItemCommand(QUndoCommand):
    """Adds `item` to `group` on redo, removes it on undo. `group` must
    expose `add_existing(item)` and `remove_item(item)`.
    """

    def __init__(self, group, item, label: str = "Add item"):
        super().__init__(label)
        self._group = group
        self._item = item

    def redo(self) -> None:
        self._group.add_existing(self._item)

    def undo(self) -> None:
        self._group.remove_item(self._item)


class DeleteItemCommand(QUndoCommand):
    """Mirror image of AddItemCommand — removes on redo, restores on undo
    at its exact original stacking position (not just re-added, which
    `group.add_existing()` would otherwise append to the end of —
    silently moving a deleted-then-undone item to the front of its
    stacking band/print order). `group` must additionally expose
    `index_of(item)` (see layers/stacking_mixin.py, mixed into every
    layer group) alongside `add_existing`/`remove_item`.
    """

    def __init__(self, group, item, label: str = "Delete item"):
        super().__init__(label)
        self._group = group
        self._item = item
        self._index: int | None = None

    def redo(self) -> None:
        # Captured fresh on every redo (not just once in __init__) so a
        # delete/undo/redo cycle interleaved with other reordering still
        # restores to wherever the item actually was immediately before
        # this specific removal.
        self._index = self._group.index_of(self._item)
        self._group.remove_item(self._item)

    def undo(self) -> None:
        self._group.add_existing(self._item, self._index)


class TransformCommand(QUndoCommand):
    """Generic old/new (pos, rotation, scale) for whole-item moves and
    handle-driven scale/rotate. `old_state`/`new_state` are
    (QPointF, float, scale) tuples as produced by a class's
    _snapshot_transform() — `scale` is a single float for most items
    (InteractiveItem's default, using Qt's native uniform scale()), or an
    (scale_x, scale_y) tuple for items that support independent per-axis
    resize (ReferenceImageItem's override — see canvas/resize_math.py).
    """

    def __init__(self, item, old_state, new_state, label: str = "Transform"):
        super().__init__(label)
        self._item = item
        self._old = old_state
        self._new = new_state

    def _apply(self, state) -> None:
        pos, rotation, scale = state
        self._item.setPos(pos)
        self._item.setRotation(rotation)
        if isinstance(scale, tuple):
            self._item.set_scale_xy(*scale)
        elif hasattr(self._item, "set_scale_factor"):
            self._item.set_scale_factor(scale)
        else:
            self._item.setScale(scale)
        handles = getattr(self._item, "_handles", None)
        if handles is not None:
            handles.reposition()

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)


class CropItemCommand(QUndoCommand):
    """Old/new crop QRect for a ReferenceImageItem, pushed once per edge-drag
    release (commit-on-release) — not on every drag frame.
    """

    def __init__(self, item, old_crop, new_crop, label: str = "Crop image"):
        super().__init__(label)
        self._item = item
        self._old = old_crop
        self._new = new_crop

    def redo(self) -> None:
        self._item.set_crop(self._new)

    def undo(self) -> None:
        self._item.set_crop(self._old)


class SetNoteTextCommand(QUndoCommand):
    """Old/new text for a NoteItem, committed when editing ends (focus
    lost, or Escape/Enter) — not per keystroke.
    """

    def __init__(self, item, old_text: str, new_text: str, label: str = "Edit note text"):
        super().__init__(label)
        self._item = item
        self._old = old_text
        self._new = new_text

    def redo(self) -> None:
        self._item.set_text(self._new)

    def undo(self) -> None:
        self._item.set_text(self._old)


class SetPerspectiveModeCommand(QUndoCommand):
    """Captures the *current* mode's VP positions and horizon Y before
    switching, so undo restores them exactly rather than regenerating
    fresh defaults (today, switching 1pt -> 2pt -> 1pt loses the original
    1pt VP position; this command makes at least the undo path lossless).
    """

    def __init__(self, layer, old_mode, old_horizon_y, old_vp_positions, new_mode,
                 label: str = "Change perspective mode"):
        super().__init__(label)
        self._layer = layer
        self._old_mode = old_mode
        self._old_horizon_y = old_horizon_y
        self._old_vp_positions = list(old_vp_positions)
        self._new_mode = new_mode
        self._new_horizon_y = None
        self._new_vp_positions = None

    def redo(self) -> None:
        self._layer.set_mode(self._new_mode)
        if self._new_vp_positions is None:
            # First time through: capture the freshly-generated defaults so
            # a later redo (after an undo) restores this exact state
            # instead of re-generating a (possibly different) default.
            self._new_horizon_y = self._layer.horizon.pos().y()
            self._new_vp_positions = [vp.pos() for vp in self._layer.vps]
        else:
            self._layer.horizon.setPos(0, self._new_horizon_y)
            for vp, pos in zip(self._layer.vps, self._new_vp_positions):
                vp.setPos(pos)
        self._layer.grid.update()

    def undo(self) -> None:
        self._layer.set_mode(self._old_mode)
        self._layer.horizon.setPos(0, self._old_horizon_y)
        for vp, pos in zip(self._layer.vps, self._old_vp_positions):
            vp.setPos(pos)
        self._layer.grid.update()


class ReorderItemCommand(QUndoCommand):
    """Moves `item` one step forward (prints closer to the top of its own
    layer's stack) or backward. `group` must expose
    move_item_forward(item)/move_item_backward(item) — see
    ReferenceLayerGroup, CompositionLayerGroup, LightingLayerGroup. Forward
    and backward are exact inverses of each other (each is an adjacent-
    element swap within the group's internal order, which is its own
    inverse), so undo is just the opposite move rather than needing to
    snapshot and restore the whole order.
    """

    def __init__(self, group, item, forward: bool):
        super().__init__("Bring forward" if forward else "Send backward")
        self._group = group
        self._item = item
        self._forward = forward

    def redo(self) -> None:
        if self._forward:
            self._group.move_item_forward(self._item)
        else:
            self._group.move_item_backward(self._item)

    def undo(self) -> None:
        if self._forward:
            self._group.move_item_backward(self._item)
        else:
            self._group.move_item_forward(self._item)


class SendToBackCommand(QUndoCommand):
    """Moves `item` to the very bottom (index 0) of its layer's stack.
    `group` must expose move_item_to_bottom(item), move_item_to_index(item,
    index), and index_of(item). Captures the old index on each redo (not
    just __init__) so an interleaved reorder/restore cycle still restores
    correctly.

    undo() uses move_item_to_index() rather than add_existing() — the
    item was never removed from the bucket by move_item_to_bottom() (it
    only repositions within the same bucket), so add_existing() either
    duplicated it (buckets with no dedup guard) or silently no-opped
    (buckets that guard against re-adding a present item) instead of
    actually restoring its position.
    """

    def __init__(self, group, item):
        super().__init__("Send to back")
        self._group = group
        self._item = item
        self._old_index: int | None = None

    def redo(self) -> None:
        self._old_index = self._group.index_of(self._item)
        self._group.move_item_to_bottom(self._item)

    def undo(self) -> None:
        if self._old_index is not None:
            self._group.move_item_to_index(self._item, self._old_index)


class BringToFrontCommand(QUndoCommand):
    """Moves `item` to the very top of its layer's stack. Same
    capture-pattern as SendToBackCommand but targeting the end — see its
    docstring for why undo() uses move_item_to_index() instead of
    add_existing().
    """

    def __init__(self, group, item):
        super().__init__("Bring to front")
        self._group = group
        self._item = item
        self._old_index: int | None = None

    def redo(self) -> None:
        self._old_index = self._group.index_of(self._item)
        self._group.move_item_to_top(self._item)

    def undo(self) -> None:
        if self._old_index is not None:
            self._group.move_item_to_index(self._item, self._old_index)


class CopyItemCommand(QUndoCommand):
    """Duplicates `clone` (already constructed, not yet added to the scene)
    as a new sibling of `item` in `group`. On redo the clone is added to
    the group at the index right after `item`; on undo it's removed.
    Using a pre-built clone (rather than a factory) keeps the command
    simple and avoids re-running construction logic on each redo — the
    clone's full state (position, scale, rotation, note text, etc.) is
    captured once at duplicate time and faithfully restored by re-adding.
    """

    def __init__(self, group, item, clone, label: str = "Duplicate"):
        super().__init__(label)
        self._group = group
        self._item = item
        self._clone = clone
        self._index: int | None = None

    def redo(self) -> None:
        """On first redo, captures the insertion index (one slot after
        the original item) and adds the clone. On subsequent redos
        (after an undo), re-adds the clone at the same index.
        """
        if self._index is None or self._clone.scene() is None:
            self._index = max(0, (self._group.index_of(self._item) or 0) + 1)
        self._group.add_existing(self._clone, self._index)

    def undo(self) -> None:
        if self._clone is not None:
            self._group.remove_item(self._clone)


class SetPropertyCommand(QUndoCommand):
    """Generic single-value property change: opacity, grid line weight,
    grid spacing, arrow endpoints, scale, rotation, and similar. `setter`
    is a one-argument callable; `old_value`/`new_value` are whatever it
    accepts.
    """

    def __init__(self, setter, old_value, new_value, label: str = "Change property"):
        super().__init__(label)
        self._setter = setter
        self._old = old_value
        self._new = new_value

    def redo(self) -> None:
        self._setter(self._new)

    def undo(self) -> None:
        self._setter(self._old)
