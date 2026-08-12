"""Hover-reveal for Project Panel item-row icons.

`layers_panel.py`'s own module docstring long assumed this needed a custom
`QStyledItemDelegate` rewrite — it doesn't. `_RowButtons` is already a
persistent `QWidget` embedded per row via `setItemWidget()`, and (per its
`hoverable` flag) already owns its own `app/scrollbars.OpacityFade`, resting
dim and rising to full opacity on command. All this module does is watch
the tree's viewport for pointer movement and tell whichever row's
`_RowButtons` is currently under the cursor to reveal itself, and the
previously-hovered one to rest back down — no delegate, no custom paint
path.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QTreeWidget


class _RowHoverFilter(QObject):
    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._tree = tree
        self._current = None
        tree.viewport().installEventFilter(self)
        tree.viewport().setMouseTracking(True)

    def _buttons_at(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return None
        widget = self._tree.itemWidget(item, 1)
        if widget is None or not getattr(widget, "hoverable", False):
            return None
        return widget

    def eventFilter(self, watched, event) -> bool:
        etype = event.type()
        if etype == QEvent.MouseMove:
            self._set_hovered(self._buttons_at(event.position().toPoint()))
        elif etype == QEvent.Leave:
            self._set_hovered(None)
        return False

    def _set_hovered(self, buttons) -> None:
        if buttons is self._current:
            return
        previous, self._current = self._current, buttons
        # A rebuild (refresh_structure()) can destroy `previous`'s
        # underlying widget out from under this stale Python reference
        # without ever firing a Leave event first — guard against that
        # rather than assume the tree is quiescent whenever the pointer
        # is.
        if previous is not None:
            try:
                previous.set_row_hovered(False)
            except RuntimeError:
                pass
        if buttons is not None:
            buttons.set_row_hovered(True)


def install_row_hover(tree: QTreeWidget) -> None:
    """Idempotent enough for this app's needs — call once per QTreeWidget
    (LayersPanel does, right after constructing self.tree), matching how
    app/scrollbars.py's install() is called once from main.py. Parented to
    `tree`, so nothing else needs to keep a reference alive.
    """
    _RowHoverFilter(tree)
