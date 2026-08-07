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

    def remove_item(self, item) -> None:
        bucket = self._bucket_for(item)
        if bucket is not None and item in bucket:
            bucket.remove(item)
        self.removeFromGroup(item)
        if item.scene():
            item.scene().removeItem(item)
        self._reassign_z()
