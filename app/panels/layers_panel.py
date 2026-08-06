"""Layers & Tools dock: per-layer visibility/lock, the reference image
list, and the placement tools for composition/perspective/lighting/guides.

This panel talks to the CanvasScene directly rather than bouncing every
toggle through MainWindow — keeps the wiring short for a single-scene app.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import constants as C
from ..constants import LayerKind, PerspectiveMode
from ..canvas.undo_commands import SetPerspectiveModeCommand, SetPropertyCommand


def _hline_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "hint")
    return lbl


class _LayerHeader(QWidget):
    visibility_toggled = Signal(bool)
    lock_toggled = Signal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setProperty("role", "section")
        self.visible_box = QCheckBox("Visible")
        self.visible_box.setChecked(True)
        self.lock_box = QCheckBox("Locked")
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(self.visible_box)
        layout.addWidget(self.lock_box)
        self.visible_box.toggled.connect(self.visibility_toggled)
        self.lock_box.toggled.connect(self.lock_toggled)


class LayersPanel(QWidget):
    tool_selected = Signal(str)
    request_import = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._tool_buttons: dict[str, QToolButton] = {}

        # Lazy "before this edit session" baselines for undo-commit-on-
        # release, mirroring InteractiveItem's press/release pattern but
        # for spin boxes (which have no press/release signals — see
        # _*_editing_finished below).
        self._spacing_baseline: int | None = None
        self._spacing_last = 12
        self._line_width_baseline: float | None = None
        self._line_width_last = 2.0  # matches line_width_spin's initial value, set below
        self._perspective_opacity_baseline: float | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        self._layout = QVBoxLayout(content)
        self._layout.setSpacing(10)

        self._build_reference_section()
        self._build_composition_section()
        self._build_perspective_section()
        self._build_lighting_section()
        self._build_guides_section()
        self._layout.addStretch(1)

    # -- Reference ----------------------------------------------------
    def _build_reference_section(self) -> None:
        box = QGroupBox("Reference")
        v = QVBoxLayout(box)
        header = _LayerHeader("Images")
        header.visibility_toggled.connect(self.scene.reference_layer.set_layer_visible)
        header.lock_toggled.connect(lambda on: self.scene.set_layer_locked(LayerKind.REFERENCE, on))
        v.addWidget(header)

        self.ref_list = QListWidget()
        self.ref_list.setMaximumHeight(140)
        self.ref_list.itemSelectionChanged.connect(self._on_ref_list_selection)
        v.addWidget(self.ref_list)

        row = QHBoxLayout()
        import_btn = QPushButton("Import Image…")
        import_btn.clicked.connect(self.request_import.emit)
        row.addWidget(import_btn)
        v.addLayout(row)
        v.addWidget(_hline_label("Select an image here or on canvas to edit it in Properties."))

        self._layout.addWidget(box)

    def refresh_reference_list(self) -> None:
        self.ref_list.blockSignals(True)
        self.ref_list.clear()
        for i, item in enumerate(self.scene.reference_layer.items()):
            entry = QListWidgetItem(f"Reference {i + 1}")
            entry.setData(Qt.UserRole, item)
            self.ref_list.addItem(entry)
        self.ref_list.blockSignals(False)

    def _on_ref_list_selection(self) -> None:
        selected = self.ref_list.selectedItems()
        self.scene.clearSelection()
        for entry in selected:
            item = entry.data(Qt.UserRole)
            if item is not None:
                item.setSelected(True)

    # -- Composition ----------------------------------------------------
    def _build_composition_section(self) -> None:
        box = QGroupBox("Composition")
        v = QVBoxLayout(box)
        header = _LayerHeader("Guides & Markers")
        header.visibility_toggled.connect(self.scene.composition_layer.setVisible)
        header.lock_toggled.connect(lambda on: self.scene.set_layer_locked(LayerKind.COMPOSITION, on))
        v.addWidget(header)

        grid = QHBoxLayout()
        for label, tool in [
            ("+ Primary Focal", "focal_primary"),
            ("+ Secondary Focal", "focal_secondary"),
        ]:
            grid.addWidget(self._make_tool_button(label, tool))
        v.addLayout(grid)

        grid2 = QHBoxLayout()
        for label, tool in [
            ("+ Movement Line", "movement_line"),
            ("+ Note", "note_comp"),
        ]:
            grid2.addWidget(self._make_tool_button(label, tool))
        v.addLayout(grid2)
        v.addWidget(_hline_label("Two-point tools: click a start, then an end point."))

        self._layout.addWidget(box)

    # -- Perspective ------------------------------------------------------
    def _build_perspective_section(self) -> None:
        box = QGroupBox("Perspective")
        v = QVBoxLayout(box)
        header = _LayerHeader("Grid")
        header.visibility_toggled.connect(self.scene.perspective_layer.set_layer_visible)
        header.lock_toggled.connect(lambda on: self.scene.set_layer_locked(LayerKind.PERSPECTIVE, on))
        v.addWidget(header)

        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict[PerspectiveMode, QRadioButton] = {}
        for label, mode in [("1-pt", PerspectiveMode.ONE_POINT), ("2-pt", PerspectiveMode.TWO_POINT), ("3-pt", PerspectiveMode.THREE_POINT)]:
            radio = QRadioButton(label)
            if mode == PerspectiveMode.ONE_POINT:
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
        self.spacing_spin.setValue(12)
        self.spacing_spin.valueChanged.connect(self._on_spacing_changed)
        self.spacing_spin.editingFinished.connect(self._commit_spacing)
        spacing_row.addWidget(self.spacing_spin)
        v.addLayout(spacing_row)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Line weight"))
        self.line_width_spin = QDoubleSpinBox()
        self.line_width_spin.setRange(1.0, 8.0)
        self.line_width_spin.setSingleStep(0.5)
        self.line_width_spin.setValue(2.0)
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
        self.perspective_opacity.setValue(85)
        self.perspective_opacity.valueChanged.connect(lambda v_: self.scene.perspective_layer.set_layer_opacity(v_ / 100))
        self.perspective_opacity.sliderPressed.connect(self._on_perspective_opacity_pressed)
        self.perspective_opacity.sliderReleased.connect(self._on_perspective_opacity_released)
        opacity_row.addWidget(self.perspective_opacity)
        v.addLayout(opacity_row)

        self._layout.addWidget(box)

    # -- undo/redo sync -----------------------------------------------------
    def sync_from_scene(self) -> None:
        """Refresh widgets that can drift out of sync after an undo/redo,
        since undo commands mutate the scene directly rather than going
        through these widgets' change handlers. Called whenever the undo
        stack's index changes (see MainWindow._rebuild_workspace).
        """
        mode = self.scene.perspective_layer.mode
        radio = self._mode_buttons.get(mode)
        if radio is not None and not radio.isChecked():
            radio.blockSignals(True)
            radio.setChecked(True)
            radio.blockSignals(False)

        spacing = self.scene.perspective_layer.grid.line_count
        if self.spacing_spin.value() != spacing:
            self.spacing_spin.blockSignals(True)
            self.spacing_spin.setValue(spacing)
            self.spacing_spin.blockSignals(False)
            self._spacing_last = spacing

    # -- perspective: undo-aware wrappers ----------------------------------
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
    def _build_lighting_section(self) -> None:
        box = QGroupBox("Lighting")
        v = QVBoxLayout(box)
        header = _LayerHeader("Light Plan")
        header.visibility_toggled.connect(self.scene.lighting_layer.setVisible)
        header.lock_toggled.connect(lambda on: self.scene.set_layer_locked(LayerKind.LIGHTING, on))
        v.addWidget(header)

        row1 = QHBoxLayout()
        for label, tool in [("+ Light Source", "light_source"), ("+ Light Dir.", "light_arrow")]:
            row1.addWidget(self._make_tool_button(label, tool))
        v.addLayout(row1)

        row2 = QHBoxLayout()
        for label, tool in [("+ Shadow Dir.", "shadow_arrow"), ("+ Note", "note_light")]:
            row2.addWidget(self._make_tool_button(label, tool))
        v.addLayout(row2)

        self._layout.addWidget(box)

    # -- Guides -----------------------------------------------------------
    def _build_guides_section(self) -> None:
        box = QGroupBox("Guides")
        v = QVBoxLayout(box)
        thirds = QCheckBox("Rule of Thirds")
        thirds.toggled.connect(self.scene.guides_layer.set_rule_of_thirds)
        golden = QCheckBox("Golden Ratio")
        golden.toggled.connect(self.scene.guides_layer.set_golden_ratio)
        v.addWidget(thirds)
        v.addWidget(golden)
        self._layout.addWidget(box)

    # -- tool activation (single-select across all tool buttons) ----------
    def _make_tool_button(self, label: str, tool: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(label)
        btn.setCheckable(True)
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
