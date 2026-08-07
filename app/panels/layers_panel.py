"""Project Panel: one outliner listing every layer and every item placed
on the drafting table, replacing five separate fixed sections. Every
placed item — not just reference images — is a named, selectable row with
inline visibility/lock toggles, plus a live search filter across the
whole painting.

Reorder-within-a-layer (which item prints on top of which other one) is
per-row up/down buttons, not drag-and-drop: QTreeWidget's built-in
InternalMove drag would need a delegate that both blocks drags across
layer sections and translates a drop index back into a layer group's own
bookkeeping (ReferenceLayerGroup._items, or a typed bucket for
composition/lighting) — a real drag rewrite, not this pass. The buttons
call ReferenceLayerGroup.move_item_forward()/move_item_backward() and
the equivalents on CompositionLayerGroup/LightingLayerGroup (each undoable
via ReorderItemCommand). True hover-reveal icons are also still not in
(QTreeWidget doesn't support per-row hover visibility cheaply without a
custom item delegate; the eye/lock/reorder icons are small and always
visible instead).

Item rows list front-to-back, top to bottom — the row order matches print
order (top row = prints on top), which is why _populate_reference() etc.
below iterate each layer group's item list *reversed*: the group's own
list is stored back-to-front (index 0 = bottom) since z-values are
assigned as ascending list-index (see e.g. ReferenceLayerGroup._reassign_z).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import constants as C
from .. import icons
from ..constants import LayerKind, PerspectiveMode
from ..canvas.undo_commands import SetPerspectiveModeCommand, SetPropertyCommand
from ..layers.reference_layer import ReferenceImageItem
from ..layers.composition_layer import FocalPointItem, MovementLineItem, NoteItem
from ..layers.lighting_layer import LightSourceItem, DirectionArrowItem
from ..layers.perspective_layer import VanishingPointItem, HorizonLineItem

_ROLE_ITEM = Qt.UserRole
# Compact row-button icon size — bumped alongside the toolbar/tree icon
# bumps below for legibility; was 15/16, then 17, then 20px.
#
# NOT sized to literally match the Perspective section's "1-pt"/"2-pt"/
# "3-pt" QRadioButtons' sizeHint height, even though that was the original
# ask — measured on a real (non-offscreen) QApplication, a plain
# QRadioButton("1-pt") is only 20px tall (indicator + Segoe UI text line
# height), while a single compact QToolButton at this constant's *previous*
# value (20px icon) was already 31px tall — i.e. matching the radio's
# literal height would mean *shrinking* the buttons, the opposite of what
# was asked. The actual "these still look swallowed" complaint is ink
# density, not bounding-box size: icons.py's glyphs are 1.5-stroke-weight
# line art scaled uniformly with this constant (the SVG viewBox and its
# stroke-width scale together), so a thin stroke stays proportionally thin
# no matter how many times the box size alone gets bumped. Sized up further
# here for real visual weight and confirmed by eye against a real running
# window (see the grab()-based verification note in the git history for
# why offscreen rendering isn't trusted for this kind of judgment call).
_ROW_ICON_PX = 26


def _row_icon_and_label(item) -> tuple[str, str]:
    if isinstance(item, ReferenceImageItem):
        return "image", item.display_name
    if isinstance(item, FocalPointItem):
        return "focal", f"Focal point · {item.kind}"
    if isinstance(item, MovementLineItem):
        return "movement", "Movement line"
    if isinstance(item, NoteItem):
        text = item.text().strip() or "Note"
        return "note", (text if len(text) <= 32 else text[:31] + "…")
    if isinstance(item, LightSourceItem):
        return "light", "Light source"
    if isinstance(item, DirectionArrowItem):
        return ("light" if item.kind == "light" else "shadow"), f"{item.kind.title()} direction"
    if isinstance(item, VanishingPointItem):
        return "vanishing", f"Vanishing point ({item.label})"
    if isinstance(item, HorizonLineItem):
        return "vanishing", "Horizon line"
    return "shapes", type(item).__name__


class _RowButtons(QWidget):
    """The eye/lock toggle pair (plus, for reorderable item rows, an
    up/down stacking-order pair) used as column 1's item widget for both
    layer-header rows and individual item rows.
    """

    visibility_toggled = Signal(bool)
    lock_toggled = Signal(bool)
    move_forward_clicked = Signal()
    move_backward_clicked = Signal()

    def __init__(self, *, visible: bool, locked: bool, show_visibility: bool = True,
                 show_lock: bool = True, can_move_forward: bool | None = None,
                 can_move_backward: bool | None = None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        # Right margin reserves real clearance for the vertical scrollbar
        # (C.SCROLLBAR_WIDTH_PX), not just a cosmetic gap — measured at
        # this panel's own minimum width with enough rows to force a
        # scrollbar, the tree places this widget's right edge flush with
        # tree.width() itself, not tree.viewport().width() (the actually
        # visible area once the scrollbar's stripe is excluded), a ~10px
        # difference. Without this, the outermost pinned button (Visible,
        # since the Lock/Visible swap below) renders partly underneath the
        # scrollbar instead of clearing it. Column width below is
        # re-measured to account for the extra margin, not hand-tuned.
        layout.setContentsMargins(2, 0, 5 + C.SCROLLBAR_WIDTH_PX, 0)
        layout.setSpacing(2)
        # Reorder buttons only appear when the caller passes real
        # can_move_forward/backward booleans — None means "this item's
        # layer group doesn't support reordering" (perspective/guides).
        if can_move_forward is not None or can_move_backward is not None:
            self.up_btn = QToolButton()
            self.up_btn.setProperty("role", "compact")
            self.up_btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
            self.up_btn.setIcon(icons.icon("reorder_up", _ROW_ICON_PX))
            self.up_btn.setAutoRaise(True)
            self.up_btn.setToolTip("Bring forward (prints closer to the top)")
            self.up_btn.setEnabled(bool(can_move_forward))
            self.up_btn.clicked.connect(self.move_forward_clicked)
            layout.addWidget(self.up_btn)

            self.down_btn = QToolButton()
            self.down_btn.setProperty("role", "compact")
            self.down_btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
            self.down_btn.setIcon(icons.icon("reorder_down", _ROW_ICON_PX))
            self.down_btn.setAutoRaise(True)
            self.down_btn.setToolTip("Send backward (prints closer to the bottom)")
            self.down_btn.setEnabled(bool(can_move_backward))
            self.down_btn.clicked.connect(self.move_backward_clicked)
            layout.addWidget(self.down_btn)
        # Split alignment: reorder buttons (when present) pin to column 1's
        # left edge — immediately after column 0 ends, not necessarily
        # flush against variable-length label text, since column widths are
        # shared across every row — while eye/lock pin to the panel's right
        # edge below. The stretch between them is what creates the split;
        # on a row with no reorder buttons this stretch is the only thing
        # before eye/lock, so they land at the right edge same as ever.
        # This deliberately reopens a visible gap between short label text
        # and the right-pinned eye/lock on 2-button rows (layer headers,
        # perspective/guides items) — an explicit, requested trade-off in
        # favor of eye/lock always being at a predictable, consistent right
        # edge, not an oversight to "fix" again later.
        layout.addStretch(1)
        # Lock before Visible (swapped from the original eye-then-lock
        # order) — Visible is now the outermost/rightmost control.
        if show_lock:
            self.lock_btn = QToolButton()
            self.lock_btn.setProperty("role", "compact")
            self.lock_btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
            self.lock_btn.setCheckable(True)
            self.lock_btn.setChecked(locked)
            self.lock_btn.setIcon(icons.icon("lock" if locked else "unlock", _ROW_ICON_PX))
            self.lock_btn.setAutoRaise(True)
            self.lock_btn.setToolTip("Locked")
            self.lock_btn.toggled.connect(self._on_lock_toggled)
            self.lock_btn.toggled.connect(self.lock_toggled)
            layout.addWidget(self.lock_btn)
        if show_visibility:
            self.eye_btn = QToolButton()
            self.eye_btn.setProperty("role", "compact")
            self.eye_btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
            self.eye_btn.setCheckable(True)
            self.eye_btn.setChecked(visible)
            self.eye_btn.setIcon(icons.icon("eye", _ROW_ICON_PX))
            self.eye_btn.setAutoRaise(True)
            self.eye_btn.setToolTip("Visible")
            self.eye_btn.toggled.connect(self.visibility_toggled)
            layout.addWidget(self.eye_btn)

    def _on_lock_toggled(self, on: bool) -> None:
        self.lock_btn.setIcon(icons.icon("lock" if on else "unlock", _ROW_ICON_PX))


class LayersPanel(QWidget):
    tool_selected = Signal(str)
    request_import = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._tool_buttons: dict[str, QToolButton] = {}
        self._row_for_obj: dict[int, QTreeWidgetItem] = {}
        self._layer_rows: dict[LayerKind, QTreeWidgetItem] = {}
        self._expanded_default: dict[LayerKind, bool] = {kind: True for kind in C.LAYER_ORDER}
        self._syncing_selection = False

        # Lazy "before this edit session" baselines for undo-commit-on-
        # release, mirroring InteractiveItem's press/release pattern but
        # for spin boxes (which have no press/release signals).
        self._spacing_baseline: int | None = None
        self._spacing_last = 12
        self._line_width_baseline: float | None = None
        self._line_width_last = 2.0
        self._perspective_opacity_baseline: float | None = None

        # Mirrors PropertiesPanel.setMinimumWidth(300) — without a floor,
        # this dock could be squeezed narrower than column 1's fixed 169px
        # button strip (see setColumnWidth(1, ...) below) plus indentation/
        # icon overhead leaves room for, and item names (reference
        # filenames especially) got crushed down to a couple of characters.
        # Sized for the widest realistic row (an item row: indent + icon +
        # reorder up/down + eye + lock) with enough left over in column 0
        # for a legible chunk of a name.
        self.setMinimumWidth(328)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        search_row = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(icons.icon("search", 22).pixmap(22, 22))
        # The one icon in this panel that lives outside self.tree, so it's
        # not covered by refresh_structure()'s full rebuild on a theme
        # switch (see MainWindow._refresh_icon_colors()) — register it
        # individually.
        icons.register(search_icon, lambda obj, ic: obj.setPixmap(ic.pixmap(22, 22)), "search")
        search_row.addWidget(search_icon)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search this painting…")
        self.search_edit.textChanged.connect(self._apply_search_filter)
        search_row.addWidget(self.search_edit)
        outer.addLayout(search_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # NOT uniform: rows genuinely vary — most are a single icon+label,
        # but the tool-activation rows and the perspective settings form
        # are taller multi-widget content. setUniformRowHeights(True) makes
        # Qt skip per-item size-hint computation entirely for performance,
        # which was silently crushing every one of those rows to the
        # single-line row height regardless of what _set_row_widget() set.
        self.tree.setUniformRowHeights(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        # Measured, not guessed: _RowButtons' own sizeHint().width() for
        # the worst case (an item row with reorder up/down + eye + lock, 4
        # compact buttons at _ROW_ICON_PX plus its scrollbar-clearance
        # right margin) is 169px at the sizes/margins above. A too-narrow
        # value here silently compresses those rows below Qt's Fusion-
        # style minimum content rect (the same class of bug as the once-
        # blank row buttons fixed earlier) rather than clipping visibly,
        # so this must track _ROW_ICON_PX and _RowButtons' margins —
        # re-measure after changing either instead of hand-adjusting this
        # number.
        self.tree.setColumnWidth(1, 169)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        outer.addWidget(self.tree, 1)

        self.refresh_structure()

    # -- structural rebuild -------------------------------------------------
    def refresh_structure(self) -> None:
        """Full rebuild from current scene state. Covers what the old
        per-section refresh_reference_list()/sync_from_scene() each did
        separately — both now alias to this, see bottom of the class.
        """
        for kind, row in self._layer_rows.items():
            self._expanded_default[kind] = row.isExpanded()

        # tree.clear() destroys every existing row, which — since some of
        # them are currently selected — fires itemSelectionChanged just
        # like a real deselection would. Without this guard that ran
        # unguarded straight into _on_tree_selection_changed(), which
        # forwarded the now-empty tree selection to
        # scene.set_selection([]), silently wiping the actual scene
        # selection out from under any code that pushed an undo command
        # (triggering this exact rebuild) and then expected the selection
        # to still be there afterward — e.g. a batch edit followed
        # immediately by another one.
        self._syncing_selection = True
        try:
            self.tree.clear()
            self._row_for_obj = {}
            self._layer_rows = {}
            self._tool_buttons = {}

            self._build_layer(LayerKind.REFERENCE, "image", self.scene.reference_layer, self._populate_reference)
            self._add_layer_separator()
            self._build_layer(
                LayerKind.COMPOSITION, "shapes", self.scene.composition_layer, self._populate_composition
            )
            self._add_layer_separator()
            self._build_layer(
                LayerKind.PERSPECTIVE, "vanishing", self.scene.perspective_layer, self._populate_perspective
            )
            self._add_layer_separator()
            self._build_layer(LayerKind.LIGHTING, "light", self.scene.lighting_layer, self._populate_lighting)
            self._add_layer_separator()
            self._build_layer(
                LayerKind.GUIDES, "shapes", self.scene.guides_layer, self._populate_guides, show_lock=False
            )
        finally:
            self._syncing_selection = False

        self._sync_selection_highlight()
        self._apply_search_filter()

    @staticmethod
    def _set_row_widget(row: QTreeWidgetItem, column: int, widget: QWidget) -> None:
        """setItemWidget() alone does not grow the row to fit an embedded
        widget taller than plain text — every multi-button/multi-control
        row (tool-activation buttons, the perspective settings form, the
        import row) rendered crushed to a sliver without this.
        """
        row.setSizeHint(column, widget.sizeHint())
        row.treeWidget().setItemWidget(row, column, widget)

    def _build_layer(self, kind: LayerKind, icon_name: str, group, populate_fn, *, show_lock: bool = True) -> None:
        row = QTreeWidgetItem(self.tree)
        row.setIcon(0, icons.icon(icon_name, _ROW_ICON_PX))
        row.setText(0, C.LAYER_LABELS[kind])
        # An explicit absolute size, not "current size + 2" — QTreeWidgetItem
        # .font(0) returns a Qt-default-constructed QFont (whatever the
        # platform default point size happens to be, not the app-wide
        # QFont(C.FONT_FAMILY_UI, 11) set in theme.py) until a font has
        # actually been assigned, so a relative bump silently based itself
        # on the wrong starting size.
        row.setFont(0, QFont(C.FONT_FAMILY_UI, 13, QFont.Bold))
        row.setExpanded(self._expanded_default.get(kind, True))
        self._layer_rows[kind] = row

        buttons = _RowButtons(visible=group.isVisible(), locked=self.scene.layer_locked(kind), show_lock=show_lock)
        buttons.visibility_toggled.connect(group.setVisible)
        if show_lock:
            buttons.lock_toggled.connect(lambda on, k=kind: self.scene.set_layer_locked(k, on))
        self._set_row_widget(row, 1, buttons)

        populate_fn(row)

    def _add_layer_separator(self) -> None:
        """A thin hairline row between top-level layer sections — same
        visual language as the app's QMenu separators (theme.py:
        height 1px, COLOR_LINE, small margin), reused here rather than
        invented fresh, so the five sections read as distinct groups
        instead of one undifferentiated list.
        """
        row = QTreeWidgetItem(self.tree)
        row.setFlags(Qt.ItemIsEnabled)  # not selectable/clickable — pure spacing
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {C.COLOR_LINE}; border: none;")
        layout.addWidget(line)
        self._set_row_widget(row, 0, widget)
        self._span_full_width(row)

    def _span_full_width(self, row: QTreeWidgetItem) -> None:
        """Column 0 alone is narrower than the row (column 1 is reserved
        for eye/lock buttons on every *other* row) — span both columns so
        a row with nothing to put in column 1 gets that width back instead
        of it sitting there unused while column 0's own content (a
        separator line, or — worse — a row with real text/controls like
        the perspective mode radios/spinboxes) gets squeezed for no
        reason. PySide6 only exposes the QTreeView-level (row, parent,
        span) overload for QTreeWidget, not a QTreeWidgetItem-based
        convenience one, hence the indexFromItem() round-trip.
        """
        index = self.tree.indexFromItem(row)
        self.tree.setFirstColumnSpanned(index.row(), index.parent(), True)

    def _add_item_row(self, parent: QTreeWidgetItem, obj, group=None) -> QTreeWidgetItem:
        """`group` is the owning layer group if (and only if) it supports
        reordering (ReferenceLayerGroup/CompositionLayerGroup/
        LightingLayerGroup all expose can_move_forward()/backward() and
        move_item_forward()/backward()) — pass None to omit the up/down
        buttons entirely (perspective's horizon/vanishing points, which
        aren't freely reorderable).
        """
        icon_name, label = _row_icon_and_label(obj)
        row = QTreeWidgetItem(parent)
        row.setIcon(0, icons.icon(icon_name, _ROW_ICON_PX))
        row.setText(0, label)
        # A narrow dock elides long filenames/note text with "…" and gives
        # no other way to read the full name — the tooltip is that way.
        row.setToolTip(0, label)
        row.setData(0, _ROLE_ITEM, obj)
        self._row_for_obj[id(obj)] = row

        can_fwd = group.can_move_forward(obj) if group is not None else None
        can_back = group.can_move_backward(obj) if group is not None else None
        buttons = _RowButtons(
            visible=obj.isVisible(), locked=obj.is_locked(),
            can_move_forward=can_fwd, can_move_backward=can_back,
        )
        buttons.visibility_toggled.connect(obj.setVisible)
        buttons.lock_toggled.connect(obj.set_locked)
        if group is not None:
            buttons.move_forward_clicked.connect(lambda o=obj, g=group: self._reorder_item(g, o, True))
            buttons.move_backward_clicked.connect(lambda o=obj, g=group: self._reorder_item(g, o, False))
        self._set_row_widget(row, 1, buttons)
        return row

    def _reorder_item(self, group, item, forward: bool) -> None:
        can = group.can_move_forward(item) if forward else group.can_move_backward(item)
        if not can:
            return
        from ..canvas.undo_commands import ReorderItemCommand
        self.scene.undo_stack.push(ReorderItemCommand(group, item, forward))

    def _add_tool_row(self, parent: QTreeWidgetItem, tools: list[tuple[str, str, str]]) -> None:
        """tools: list of (tool_id, icon_name, tooltip)."""
        row = QTreeWidgetItem(parent)
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        for tool, icon_name, tooltip in tools:
            layout.addWidget(self._make_tool_button(tool, icon_name, tooltip))
        layout.addStretch(1)
        self._set_row_widget(row, 0, widget)
        self._span_full_width(row)

    def _add_toggle_row(self, parent: QTreeWidgetItem, label: str, checked: bool, on_toggled) -> None:
        row = QTreeWidgetItem(parent)
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 2)
        box = QCheckBox(label)
        box.setChecked(checked)
        box.toggled.connect(on_toggled)
        layout.addWidget(box)
        layout.addStretch(1)
        self._set_row_widget(row, 0, widget)
        self._span_full_width(row)

    # -- Reference ------------------------------------------------------
    def _populate_reference(self, parent: QTreeWidgetItem) -> None:
        row = QTreeWidgetItem(parent)
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 2)
        add_btn = QToolButton()
        add_btn.setProperty("role", "compact")
        add_btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
        add_btn.setIcon(icons.icon("import", _ROW_ICON_PX))
        add_btn.setAutoRaise(True)
        # Icon + tooltip only, no adjacent label — matches the Composition/
        # Lighting/Perspective "Add" rows below it rather than being the
        # one row in this panel with its own bespoke layout. Also sidesteps
        # QLabel's lack of auto-eliding: a visible "Import…" label here used
        # to be the one thing on this row that could get silently clipped.
        add_btn.setToolTip("Import reference image(s)…")
        add_btn.clicked.connect(self.request_import.emit)
        layout.addWidget(add_btn)
        layout.addStretch(1)
        self._set_row_widget(row, 0, widget)
        self._span_full_width(row)

        # Reversed: the layer group's own list is back-to-front (index 0 =
        # bottom of the stack), but the row order here should read
        # top-of-panel = top-of-stack, matching every other layered-editor
        # convention and the up/down buttons' "forward" = "up" mapping.
        for image in reversed(self.scene.reference_layer.items()):
            self._add_item_row(parent, image, self.scene.reference_layer)

    # -- Composition ------------------------------------------------------
    def _populate_composition(self, parent: QTreeWidgetItem) -> None:
        self._add_tool_row(parent, [
            ("focal_primary", "focal", "Add primary focal point"),
            ("focal_secondary", "focal", "Add secondary focal point"),
            ("movement_line", "movement", "Add movement line — click a start point, then an end point"),
            ("note_comp", "note", "Add note"),
        ])
        layer = self.scene.composition_layer
        for fp in reversed(layer.focal_points):
            self._add_item_row(parent, fp, layer)
        for line in reversed(layer.movement_lines):
            self._add_item_row(parent, line, layer)
        for note in reversed(layer.notes):
            self._add_item_row(parent, note, layer)

    # -- Perspective --------------------------------------------------------
    def _populate_perspective(self, parent: QTreeWidgetItem) -> None:
        row = QTreeWidgetItem(parent)
        self._set_row_widget(row, 0, self._build_perspective_settings_widget())
        self._span_full_width(row)

        layer = self.scene.perspective_layer
        self._add_item_row(parent, layer.horizon)
        for vp in layer.vps:
            self._add_item_row(parent, vp)

    def _build_perspective_settings_widget(self) -> QWidget:
        widget = QWidget()
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(6)

        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict[PerspectiveMode, QRadioButton] = {}
        for label, mode in [
            ("1-pt", PerspectiveMode.ONE_POINT),
            ("2-pt", PerspectiveMode.TWO_POINT),
            ("3-pt", PerspectiveMode.THREE_POINT),
        ]:
            radio = QRadioButton(label)
            if mode == self.scene.perspective_layer.mode:
                radio.setChecked(True)
            radio.toggled.connect(lambda checked, m=mode: checked and self._on_perspective_mode_chosen(m))
            self._mode_group.addButton(radio)
            self._mode_buttons[mode] = radio
            mode_row.addWidget(radio)
        v.addLayout(mode_row)

        spacing_row = QHBoxLayout()
        spacing_row.addWidget(QLabel("Grid lines"))
        self.spacing_spin = QSpinBox()
        self.spacing_spin.setRange(2, 48)
        self.spacing_spin.setValue(self.scene.perspective_layer.grid.line_count)
        self._spacing_last = self.spacing_spin.value()
        self.spacing_spin.valueChanged.connect(self._on_spacing_changed)
        self.spacing_spin.editingFinished.connect(self._commit_spacing)
        spacing_row.addWidget(self.spacing_spin)
        v.addLayout(spacing_row)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Line weight"))
        self.line_width_spin = QDoubleSpinBox()
        self.line_width_spin.setRange(1.0, 8.0)
        self.line_width_spin.setSingleStep(0.5)
        self.line_width_spin.setValue(self._line_width_last)
        self.line_width_spin.setToolTip(
            "Thicker lines are easier to see when projecting onto a wall — "
            "increase this if fine lines wash out until you zoom in."
        )
        self.line_width_spin.valueChanged.connect(self._on_line_width_changed)
        self.line_width_spin.editingFinished.connect(self._commit_line_width)
        width_row.addWidget(self.line_width_spin)
        v.addLayout(width_row)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        self.perspective_opacity = QSlider(Qt.Horizontal)
        self.perspective_opacity.setRange(10, 100)
        self.perspective_opacity.setValue(int(self.scene.perspective_layer.layer_opacity() * 100))
        self.perspective_opacity.valueChanged.connect(lambda v_: self.scene.perspective_layer.set_layer_opacity(v_ / 100))
        self.perspective_opacity.sliderPressed.connect(self._on_perspective_opacity_pressed)
        self.perspective_opacity.sliderReleased.connect(self._on_perspective_opacity_released)
        opacity_row.addWidget(self.perspective_opacity)
        v.addLayout(opacity_row)

        return widget

    def _on_perspective_mode_chosen(self, mode: PerspectiveMode) -> None:
        layer = self.scene.perspective_layer
        if mode == layer.mode:
            return
        old_mode, old_horizon_y, old_vp_positions = layer.snapshot_state()
        self.scene.undo_stack.push(
            SetPerspectiveModeCommand(layer, old_mode, old_horizon_y, old_vp_positions, mode)
        )

    def _on_spacing_changed(self, value: int) -> None:
        if self._spacing_baseline is None:
            self._spacing_baseline = self._spacing_last
        self.scene.perspective_layer.set_grid_spacing(value)
        self._spacing_last = value

    def _commit_spacing(self) -> None:
        if self._spacing_baseline is None:
            return
        old, new = self._spacing_baseline, self._spacing_last
        self._spacing_baseline = None
        if old != new:
            self.scene.undo_stack.push(
                SetPropertyCommand(self.scene.perspective_layer.set_grid_spacing, old, new, "Change grid spacing")
            )

    def _on_line_width_changed(self, value: float) -> None:
        if self._line_width_baseline is None:
            self._line_width_baseline = self._line_width_last
        self.scene.perspective_layer.set_line_width(value)
        self._line_width_last = value

    def _commit_line_width(self) -> None:
        if self._line_width_baseline is None:
            return
        old, new = self._line_width_baseline, self._line_width_last
        self._line_width_baseline = None
        if old != new:
            self.scene.undo_stack.push(
                SetPropertyCommand(self.scene.perspective_layer.set_line_width, old, new, "Change grid line weight")
            )

    def _on_perspective_opacity_pressed(self) -> None:
        self._perspective_opacity_baseline = self.perspective_opacity.value() / 100

    def _on_perspective_opacity_released(self) -> None:
        if self._perspective_opacity_baseline is None:
            return
        old = self._perspective_opacity_baseline
        new = self.perspective_opacity.value() / 100
        self._perspective_opacity_baseline = None
        if old != new:
            self.scene.undo_stack.push(
                SetPropertyCommand(self.scene.perspective_layer.set_layer_opacity, old, new, "Change grid opacity")
            )

    # -- Lighting -----------------------------------------------------
    def _populate_lighting(self, parent: QTreeWidgetItem) -> None:
        self._add_tool_row(parent, [
            ("light_source", "light", "Add light source"),
            ("light_arrow", "light", "Add light direction — click a start point, then an end point"),
            ("shadow_arrow", "shadow", "Add shadow direction — click a start point, then an end point"),
            ("note_light", "note", "Add note"),
        ])
        layer = self.scene.lighting_layer
        for source in reversed(layer.sources):
            self._add_item_row(parent, source, layer)
        for arrow in reversed(layer.arrows):
            self._add_item_row(parent, arrow, layer)
        for note in reversed(layer.notes):
            self._add_item_row(parent, note, layer)

    # -- Guides -----------------------------------------------------------
    def _populate_guides(self, parent: QTreeWidgetItem) -> None:
        layer = self.scene.guides_layer
        self._add_toggle_row(parent, "Rule of Thirds", layer.thirds.isVisible(), layer.set_rule_of_thirds)
        self._add_toggle_row(parent, "Golden Ratio", layer.golden.isVisible(), layer.set_golden_ratio)

    # -- selection sync (canvas <-> tree) ------------------------------------
    def _on_tree_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        items = [
            row.data(0, _ROLE_ITEM)
            for row in self.tree.selectedItems()
            if row.data(0, _ROLE_ITEM) is not None
        ]
        self.scene.set_selection(items)

    def _sync_selection_highlight(self) -> None:
        self._syncing_selection = True
        try:
            selected_ids = {id(obj) for obj in self.scene.selected_items()}
            self.tree.clearSelection()
            for oid, row in self._row_for_obj.items():
                row.setSelected(oid in selected_ids)
        finally:
            self._syncing_selection = False

    # -- search -----------------------------------------------------------
    def _apply_search_filter(self) -> None:
        text = self.search_edit.text().strip().lower()
        for kind, layer_row in self._layer_rows.items():
            any_match = not text
            has_persistent_row = False
            for i in range(layer_row.childCount()):
                child = layer_row.child(i)
                obj = child.data(0, _ROLE_ITEM)
                if obj is None:
                    child.setHidden(False)  # tool rows / settings / toggles always show
                    has_persistent_row = True
                    continue
                match = (not text) or (text in child.text(0).lower())
                child.setHidden(not match)
                any_match = any_match or match
            # A layer with a persistent action row (Import, the Composition/
            # Lighting "Add" row, the Perspective settings form, Guides'
            # toggles) must never be hidden by a search that happens to
            # match nothing inside it — hiding the parent QTreeWidgetItem
            # hides every child regardless of that child's own
            # setHidden(False) above, which used to make Import (and the
            # other layers' persistent rows) unreachable while filtering.
            layer_hides = (
                bool(text) and not any_match and not has_persistent_row
                and text not in C.LAYER_LABELS[kind].lower()
            )
            layer_row.setHidden(layer_hides)

    # -- tool activation (single-select across all tool buttons) ----------
    def _make_tool_button(self, tool: str, icon_name: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setProperty("role", "compact")
        btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
        btn.setIcon(icons.icon(icon_name, _ROW_ICON_PX))
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setToolTip(tooltip)
        btn.clicked.connect(lambda _checked, t=tool: self._activate_tool(t))
        self._tool_buttons[tool] = btn
        return btn

    def _activate_tool(self, tool: str) -> None:
        current = self.scene.active_tool()
        new_tool = None if current == tool else tool
        self.scene.set_active_tool(new_tool)
        self.tool_selected.emit(new_tool or "")
        self._sync_tool_buttons(new_tool)

    def _sync_tool_buttons(self, active_tool: str | None) -> None:
        for tool, btn in self._tool_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(tool == active_tool)
            btn.blockSignals(False)

    # -- back-compat call points (MainWindow calls these by name) ----------
    def refresh_reference_list(self) -> None:
        self.refresh_structure()

    def sync_from_scene(self) -> None:
        self.refresh_structure()
