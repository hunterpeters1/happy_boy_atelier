"""Shared stacking-order arithmetic for layer groups whose items live in
one or more ordered lists ("buckets") that double as z-print-order —
used by `ReferenceLayerGroup` (one flat bucket) and
`CompositionLayerGroup`/`LightingLayerGroup` (one bucket per marker type,
each with its own fixed z-band). Before this module existed, all three
classes duplicated this logic verbatim (modulo which bucket list they
operated on).

Subclasses supply two hooks:
- `_bucket_for(item)` — the list `item` belongs, or would belong, in
  (type-based for composition/lighting so it works even before `item` is
  actually in any bucket; trivially `self._items` for reference, which
  only ever hosts one type).
- `_reassign_z()` — the concrete z-value scheme for that subclass,
  applied after any add/remove/reorder.

Everything below is just list-index arithmetic layered on top of those.
A plain Python class (no Qt base) — safe to combine with
`QGraphicsItemGroup` via multiple inheritance.
"""

from __future__ import annotations


class StackedLayerMixin:
    def can_move_forward(self, item) -> bool:
        bucket = self._bucket_for(item)
        return bucket is not None and item in bucket and bucket.index(item) < len(bucket) - 1

    def can_move_backward(self, item) -> bool:
        bucket = self._bucket_for(item)
        return bucket is not None and item in bucket and bucket.index(item) > 0

    def move_item_forward(self, item) -> bool:
        if not self.can_move_forward(item):
            return False
        bucket = self._bucket_for(item)
        i = bucket.index(item)
        bucket[i], bucket[i + 1] = bucket[i + 1], bucket[i]
        self._reassign_z()
        return True

    def move_item_backward(self, item) -> bool:
        if not self.can_move_backward(item):
            return False
        bucket = self._bucket_for(item)
        i = bucket.index(item)
        bucket[i], bucket[i - 1] = bucket[i - 1], bucket[i]
        self._reassign_z()
        return True

    def index_of(self, item) -> int | None:
        """Position within item's own bucket, or None if not present.
        DeleteItemCommand (canvas/undo_commands.py) captures this right
        before removing an item so its undo can reinsert at the same
        spot instead of appending to the end, which would silently
        change print order.
        """
        bucket = self._bucket_for(item)
        if bucket is None or item not in bucket:
            return None
        return bucket.index(item)

    def move_item_to_top(self, item) -> bool:
        """Move `item` to the very end (top) of its bucket.
        Used by BringToFrontCommand. Returns False if the item isn't
        in the bucket or is already at the top.
        """
        bucket = self._bucket_for(item)
        if bucket is None or item not in bucket:
            return False
        i = bucket.index(item)
        if i == len(bucket) - 1:
            return False
        bucket.pop(i)
        bucket.append(item)
        self._reassign_z()
        return True

    def move_item_to_bottom(self, item) -> bool:
        """Move `item` to index 0 (bottom) of its bucket.
        Used by SendToBackCommand. Returns False if the item isn't
        in the bucket or is already at the bottom.
        """
        bucket = self._bucket_for(item)
        if bucket is None or item not in bucket:
            return False
        i = bucket.index(item)
        if i == 0:
            return False
        bucket.pop(i)
        bucket.insert(0, item)
        self._reassign_z()
        return True

    def move_item_to_index(self, item, index: int) -> bool:
        """Move `item` to an arbitrary position within its bucket, clamped
        to valid bounds. Used by SendToBackCommand/BringToFrontCommand's
        undo() to restore an item to its exact pre-move index — unlike
        add_existing(), which assumes the item was actually removed from
        the bucket first (true for DeleteItemCommand's undo, false here:
        move_item_to_top()/move_item_to_bottom() only reposition the item
        within the same bucket, so routing their undo through
        add_existing() either duplicated the item (no-dedup buckets) or
        silently no-opped (dedup-guarded buckets) instead of repositioning
        it. This method repositions directly instead.
        """
        bucket = self._bucket_for(item)
        if bucket is None or item not in bucket:
            return False
        bucket.remove(item)
        target = max(0, min(index, len(bucket)))
        bucket.insert(target, item)
        self._reassign_z()
        return True

    def can_send_to_back(self, item) -> bool:
        """True if `item` can be moved to the bottom of its bucket."""
        bucket = self._bucket_for(item)
        return bucket is not None and item in bucket and bucket.index(item) > 0

    def can_bring_to_front(self, item) -> bool:
        """True if `item` can be moved to the top of its bucket."""
        bucket = self._bucket_for(item)
        return bucket is not None and item in bucket and bucket.index(item) < len(bucket) - 1

    def remove_item(self, item) -> None:
        bucket = self._bucket_for(item)
        if bucket is not None and item in bucket:
            bucket.remove(item)
        self.removeFromGroup(item)
        if item.scene():
            item.scene().removeItem(item)
        self._reassign_z()
