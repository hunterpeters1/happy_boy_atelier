"""A small floating toolbar of the highest-frequency single-item actions
(Duplicate, Flip Horizontal, Lock/Unlock, Delete), appearing just outside
the current selection's bounding box — the structural lesson taken from
Milanote's/Figma's floating context toolbars (cut the eye-travel from the
canvas to a dock for the most common actions), rendered in this app's own
instrument-panel skin instead of their rounded pastel cards: the existing
`role="compact"` QToolButton QSS (hairline border, brass hover/checked),
not a new widget style.

Scoped to exactly one selected item — multi-select already has the
Properties panel's Batch Edit section for bulk actions; this widget's job
is cutting eye-travel for the single-selection case, not duplicating
batch editing. Every button calls the exact same CanvasScene/item methods
the right-click context menu and Edit menu already call
(CanvasView._build_context_menu(), MainWindow._duplicate_selected()) —
this is an additional low-travel trigger surface, not new action logic,
so undo/redo behaves identically regardless of which surface was used.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from .. import constants as C
from .. import icons

_BUTTON_PX = 20
_GAP_BELOW_ITEM_PX = 10


class SelectionContextToolbar(QWidget):
    def __init__(self, view) -> None:
        # Parented to the viewport, not a top-level window -- avoids every
        # OS floating-window quirk (focus stealing, always-on-top
        # interactions, alt-tab entries) a real QWidget(None) would bring.
        super().__init__(view.viewport())
        self._view = view
        self._current_item = None
        self._suspended = False

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: {C.COLOR_BG_RAISED}; border: 1px solid {C.COLOR_LINE}; border-radius: 2px;"
        )
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._duplicate_btn = self._make_button("image", "Duplicate (Ctrl+D)", self._duplicate)
        self._flip_btn = self._make_button("flip", "Flip Horizontal", self._flip_horizontal)
        self._lock_btn = self._make_button("lock", "Lock", self._toggle_lock)
        self._delete_btn = self._make_button("delete", "Delete", self._delete)
        for button in (self._duplicate_btn, self._flip_btn, self._lock_btn, self._delete_btn):
            layout.addWidget(button)

        scene = view.scene()
        if scene is not None and hasattr(scene, "selection_changed"):
            scene.selection_changed.connect(self.refresh)
        if hasattr(view, "zoom_changed"):
            view.zoom_changed.connect(lambda _zoom: self._reposition())
        view.horizontalScrollBar().valueChanged.connect(lambda _v: self._reposition())
        view.verticalScrollBar().valueChanged.connect(lambda _v: self._reposition())

    def _make_button(self, icon_name: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setProperty("role", "compact")
        button.setIconSize(QSize(_BUTTON_PX, _BUTTON_PX))
        button.setIcon(icons.icon(icon_name, _BUTTON_PX))
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        return button

    # -- suspend during an active drag (see CanvasView.mousePressEvent/
    # mouseReleaseEvent) -- a body drag can move the item right through
    # where this toolbar is sitting, and the toolbar must never steal a
    # mouse press meant for the canvas underneath it. --------------------
    def set_suspended(self, suspended: bool) -> None:
        self._suspended = suspended
        if suspended:
            self.setVisible(False)
        else:
            self.refresh()

    # -- selection-driven show/hide -----------------------------------------
    def refresh(self) -> None:
        scene = self._view.scene()
        items = scene.selected_items() if scene is not None and hasattr(scene, "selected_items") else []
        if self._suspended or len(items) != 1 or not hasattr(items[0], "sceneBoundingRect"):
            self._current_item = None
            self.setVisible(False)
            return
        item = items[0]
        self._current_item = item

        self._flip_btn.setVisible(hasattr(item, "flip_horizontal"))
        can_lock = hasattr(item, "set_locked") and hasattr(item, "is_locked")
        self._lock_btn.setVisible(can_lock)
        if can_lock:
            locked = item.is_locked()
            self._lock_btn.setIcon(icons.icon("unlock" if locked else "lock", _BUTTON_PX))
            self._lock_btn.setToolTip("Unlock" if locked else "Lock")

        self._reposition()
        self.adjustSize()
        self.setVisible(True)
        self.raise_()

    def _reposition(self) -> None:
        item = self._current_item
        if item is None:
            return
        view_rect = self._view.mapFromScene(item.sceneBoundingRect()).boundingRect()
        self.adjustSize()
        x = view_rect.center().x() - self.width() / 2
        # Below the item, not above -- HandleFrame's rotate handle sits
        # above a reference image's own top edge, so a toolbar placed
        # there would collide with it on every selected image.
        y = view_rect.bottom() + _GAP_BELOW_ITEM_PX
        self.move(round(x), round(y))

    # -- actions: identical calls to what the context menu/Edit menu use --
    def _duplicate(self) -> None:
        scene = self._view.scene()
        if scene is not None and hasattr(scene, "duplicate_selected_items"):
            scene.duplicate_selected_items()

    def _flip_horizontal(self) -> None:
        if self._current_item is not None and hasattr(self._current_item, "flip_horizontal"):
            self._current_item.flip_horizontal()

    def _toggle_lock(self) -> None:
        item = self._current_item
        if item is not None and hasattr(item, "set_locked"):
            item.set_locked(not item.is_locked())
            self.refresh()

    def _delete(self) -> None:
        scene = self._view.scene()
        if scene is not None and hasattr(scene, "delete_selected_items"):
            scene.delete_selected_items()
