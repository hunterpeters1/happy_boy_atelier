"""Project Panel: one outliner listing every layer and every item placed
on the drafting table, replacing five separate fixed sections. Every
placed item — not just reference images — is a named, selectable row with
inline visibility/lock toggles, plus a live search filter across the
whole painting.

Two things the redesign dossier's vision calls for are deliberately not
in this pass: drag-to-reorder within a layer (none of the layer group
classes expose a reorder operation yet — faking the drag visuals with no
backend effect would be worse than not having it) and true hover-reveal
icons (QTreeWidget doesn't support per-row hover visibility cheaply
without a custom item delegate; the eye/lock icons are small and always
visible instead).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
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
    """The eye/lock toggle pair used as column 1's item widget for both
    layer-header rows and individual item rows.
    """

    visibility_toggled = Signal(bool)
    lock_toggled = Signal(bool)

    def __init__(self, *, visible: bool, locked: bool, show_visibility: bool = True,
                 show_lock: bool = True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)
        layout.addStretch(1)
        if show_visibility:
            self.eye_btn = QToolButton()
            self.eye_btn.setProperty("role", "compact")
            self.eye_btn.setIconSize(QSize(15, 15))
            self.eye_btn.setCheckable(True)
            self.eye_btn.setChecked(visible)
            self.eye_btn.setIcon(icons.icon("eye"))
            self.eye_btn.setAutoRaise(True)
            self.eye_btn.setToolTip("Visible")
            self.eye_btn.toggled.connect(self.visibility_toggled)
            layout.addWidget(self.eye_btn)
        if show_lock:
            self.lock_btn = QToolButton()
            self.lock_btn.setProperty("role", "compact")
            self.lock_btn.setIconSize(QSize(15, 15))
            self.lock_btn.setCheckable(True)
            self.lock_btn.setChecked(locked)
            self.lock_btn.setIcon(icons.icon("lock" if locked else "unlock"))
            self.lock_btn.setAutoRaise(True)
            self.lock_btn.setToolTip("Locked")
            self.lock_btn.toggled.connect(self._on_lock_toggled)
            self.lock_btn.toggled.connect(self.lock_toggled)
            layout.addWidget(self.lock_btn)

    def _on_lock_toggled(self, on: bool) -> None:
        self.lock_btn.setIcon(icons.icon("lock" if on else "unlock"))


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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        search_row = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(icons.icon("search", 14).pixmap(14, 14))
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
        self.tree.setColumnWidth(1, 56)
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
            self._build_layer(
                LayerKind.COMPOSITION, "shapes", self.scene.composition_layer, self._populate_composition
            )
            self._build_layer(
                LayerKind.PERSPECTIVE, "vanishing", self.scene.perspective_layer, self._populate_perspective
            )
            self._build_layer(LayerKind.LIGHTING, "light", self.scene.lighting_layer, self._populate_lighting)
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
        row.setIcon(0, icons.icon(icon_name))
        row.setText(0, C.LAYER_LABELS[kind])
        font = row.font(0)
        font.setBold(True)
        row.setFont(0, font)
        row.setExpanded(self._expanded_default.get(kind, True))
        self._layer_rows[kind] = row

        buttons = _RowButtons(visible=group.isVisible(), locked=self.scene.layer_locked(kind), show_lock=show_lock)
        buttons.visibility_toggled.connect(group.setVisible)
        if show_lock:
            buttons.lock_toggled.connect(lambda on, k=kind: self.scene.set_layer_locked(k, on))
        self._set_row_widget(row, 1, buttons)

        populate_fn(row)

    def _add_item_row(self, parent: QTreeWidgetItem, obj) -> QTreeWidgetItem:
        icon_name, label = _row_icon_and_label(obj)
        row = QTreeWidgetItem(parent)
        row.setIcon(0, icons.icon(icon_name))
        row.setText(0, label)
        # A narrow dock elides long filenames/note text with "…" and gives
        # no other way to read the full name — the tooltip is that way.
        row.setToolTip(0, label)
        row.setData(0, _ROLE_ITEM, obj)
        self._row_for_obj[id(obj)] = row

        buttons = _RowButtons(visible=obj.isVisible(), locked=obj.is_locked())
        buttons.visibility_toggled.connect(obj.setVisible)
        buttons.lock_toggled.connect(obj.set_locked)
        self._set_row_widget(row, 1, buttons)
        return row

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

    # -- Reference ------------------------------------------------------
    def _populate_reference(self, parent: QTreeWidgetItem) -> None:
        row = QTreeWidgetItem(parent)
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 2)
        add_btn = QToolButton()
        add_btn.setProperty("role", "compact")
        add_btn.setIconSize(QSize(16, 16))
        add_btn.setIcon(icons.icon("import"))
        add_btn.setAutoRaise(True)
        add_btn.setToolTip("Import reference image(s)…")
        add_btn.clicked.connect(self.request_import.emit)
        layout.addWidget(add_btn)
        # Shorter label than the button's own tooltip — the full sentence
        # rarely fits this dock's width and QLabel doesn't auto-elide with
        # "…" the way QTreeWidgetItem text does, so a long label just gets
        # silently clipped with no indication there's more to it.
        import_label = QLabel("Import…")
        import_label.setToolTip("Import reference image(s)…")
        layout.addWidget(import_label)
        layout.addStretch(1)
        self._set_row_widget(row, 0, widget)

        for image in self.scene.reference_layer.items():
            self._add_item_row(parent, image)

    # -- Composition ------------------------------------------------------
    def _populate_composition(self, parent: QTreeWidgetItem) -> None:
        self._add_tool_row(parent, [
            ("focal_primary", "focal", "Add primary focal point"),
            ("focal_secondary", "focal", "Add secondary focal point"),
            ("movement_line", "movement", "Add movement line — click a start point, then an end point"),
            ("note_comp", "note", "Add note"),
        ])
        layer = self.scene.composition_layer
        for fp in layer.focal_points:
            self._add_item_row(parent, fp)
        for line in layer.movement_lines:
            self._add_item_row(parent, line)
        for note in layer.notes:
            self._add_item_row(parent, note)

    # -- Perspective --------------------------------------------------------
    def _populate_perspective(self, parent: QTreeWidgetItem) -> None:
        row = QTreeWidgetItem(parent)
        self._set_row_widget(row, 0, self._build_perspective_settings_widget())

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
        for source in layer.sources:
            self._add_item_row(parent, source)
        for arrow in layer.arrows:
            self._add_item_row(parent, arrow)
        for note in layer.notes:
            self._add_item_row(parent, note)

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
            any_match = not text and True
            for i in range(layer_row.childCount()):
                child = layer_row.child(i)
                obj = child.data(0, _ROLE_ITEM)
                if obj is None:
                    child.setHidden(False)  # tool rows / settings / toggles always show
                    any_match = any_match or not text
                    continue
                match = (not text) or (text in child.text(0).lower())
                child.setHidden(not match)
                any_match = any_match or match
            layer_hides = bool(text) and not any_match and text not in C.LAYER_LABELS[kind].lower()
            layer_row.setHidden(layer_hides)

    # -- tool activation (single-select across all tool buttons) ----------
    def _make_tool_button(self, tool: str, icon_name: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setProperty("role", "compact")
        btn.setIconSize(QSize(16, 16))
        btn.setIcon(icons.icon(icon_name))
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
