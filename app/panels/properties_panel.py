"""Properties dock: a contextual inspector for whatever is currently
selected on the canvas. One panel, rows shown/hidden per item type, rather
than a maze of per-type stacked pages.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import constants as C
from .. import icons
from ..canvas.undo_commands import SetNoteTextCommand, SetPropertyCommand
from ..layers.reference_layer import ReferenceImageItem
from ..layers.composition_layer import FocalPointItem, MeasurementItem, MovementLineItem, NoteItem
from ..layers.lighting_layer import LightSourceItem, DirectionArrowItem
from ..layers.perspective_layer import VanishingPointItem, HorizonLineItem


class _NoteEdit(QPlainTextEdit):
    """QPlainTextEdit that reports when editing ends (focus lost), so the
    panel can commit a single SetNoteTextCommand instead of one per
    keystroke.
    """

    editing_finished = Signal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.editing_finished.emit()


class PropertiesPanel(QWidget):
    request_delete = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._current = None
        self._updating = False

        # Lazy "before this edit session" baselines for undo-commit-on-
        # release/blur, paired with the item the session started on so a
        # mid-edit selection change can't misattribute the commit.
        self._scale_baseline = None
        self._scale_last = None
        self._scale_edit_item = None
        self._rotation_baseline = None
        self._rotation_last = None
        self._rotation_edit_item = None
        self._opacity_baseline = None
        self._opacity_edit_item = None
        self._note_baseline = None
        self._note_last = None
        self._note_edit_item = None
        self._position_baseline: QPointF | None = None
        self._position_edit_item = None
        self._blur_baseline = None
        self._blur_edit_item = None
        self._clarity_baseline = None
        self._clarity_edit_item = None
        self._grayscale_baseline = None
        self._grayscale_edit_item = None
        # Recomputing the Study Blur preview costs real time (numpy work,
        # ~100ms+ even at its capped working resolution — see
        # reference_layer.py's BLUR_WORKING_DIM) unlike every other slider
        # here, which only touches cheap Qt state (opacity, position).
        # Debounced so a fast drag doesn't fire one recompute per pixel of
        # mouse movement; a paused/slow drag still gets periodic updates
        # rather than nothing until release. sliderReleased always forces
        # one final, immediate (non-debounced) recompute.
        self._blur_preview_timer = QTimer(self)
        self._blur_preview_timer.setSingleShot(True)
        self._blur_preview_timer.setInterval(150)
        self._blur_preview_timer.timeout.connect(self._apply_blur_preview)

        # Fixed regardless of which controls are currently visible — with
        # no minimum, the dock's preferred width tracked whatever group box
        # happened to be shown (e.g. the empty "Nothing selected" state is
        # far narrower than the Reset Crop button or the batch-align icon
        # row), so simply switching the canvas selection made the whole
        # right-hand dock visibly resize. Sized for the widest realistic
        # row plus margin, so it also reads less cramped even at rest.
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.title = QLabel("Nothing selected")
        self.title.setProperty("role", "section")
        layout.addWidget(self.title)

        self.hint = QLabel("Select an item on the canvas to edit its properties.")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        # -- info group (reference images): read-only file metadata ------
        self.info_box = QGroupBox("Info")
        info_layout = QVBoxLayout(self.info_box)
        self.info_filename_label = QLabel()
        self.info_filename_label.setWordWrap(True)
        self.info_format_label = QLabel()
        self.info_size_label = QLabel()
        self.info_dimensions_label = QLabel()
        for lbl in (
            self.info_filename_label, self.info_format_label,
            self.info_size_label, self.info_dimensions_label,
        ):
            info_layout.addWidget(lbl)
        layout.addWidget(self.info_box)

        # -- transform group (reference images) --------------------------
        self.transform_box = QGroupBox("Transform")
        tform = QVBoxLayout(self.transform_box)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Scale"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.05, 40.0)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setToolTip(
            "Uniform scale (sets both width and height equally). For an "
            "independent width/height resize, drag a corner handle on the "
            "canvas instead — hold Shift while dragging to lock proportions. "
            "Negative (flipped) images show absolute scale here; use the "
            "context menu's Flip Horizontal/Vertical for flipping."
        )
        self.scale_spin.valueChanged.connect(self._on_scale_changed)
        scale_row.addWidget(self.scale_spin)
        tform.addLayout(scale_row)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Rotation°"))
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360, 360)
        self.rotation_spin.setSingleStep(1)
        self.rotation_spin.valueChanged.connect(self._on_rotation_changed)
        self.rotation_spin.editingFinished.connect(self._commit_rotation)
        rot_row.addWidget(self.rotation_spin)
        tform.addLayout(rot_row)
        self.scale_spin.editingFinished.connect(self._commit_scale)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("Opacity"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_slider.sliderPressed.connect(self._on_opacity_pressed)
        self.opacity_slider.sliderReleased.connect(self._on_opacity_released)
        op_row.addWidget(self.opacity_slider)
        tform.addLayout(op_row)

        # -- Study Blur (canvas/study_blur.py): a painter's squint-test —
        # blur the reference to judge shapes/values, while dark lines stay
        # legible (boosted, not washed out) even at very low contrast.
        blur_row = QHBoxLayout()
        blur_row.addWidget(QLabel("Blur"))
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setRange(0, 100)
        self.blur_slider.setToolTip(
            "Blur the reference image on screen — a squint-test aid for "
            "judging overall shapes and values without fine detail. Never "
            "alters the saved image; off by default for exports too (see "
            "the Export dialog)."
        )
        self.blur_slider.valueChanged.connect(lambda v: self._on_blur_field_changed("blur", v))
        self.blur_slider.sliderPressed.connect(lambda: self._on_blur_field_pressed("blur"))
        self.blur_slider.sliderReleased.connect(lambda: self._on_blur_field_released("blur"))
        blur_row.addWidget(self.blur_slider)
        tform.addLayout(blur_row)

        clarity_row = QHBoxLayout()
        clarity_row.addWidget(QLabel("Line Clarity"))
        self.clarity_slider = QSlider(Qt.Horizontal)
        self.clarity_slider.setRange(0, 100)
        self.clarity_slider.setToolTip(
            "Keeps dark lines/edges sharp against the Blur above, even "
            "very faint ones — raise this if fine contour or shadow lines "
            "disappear into the blur."
        )
        self.clarity_slider.valueChanged.connect(lambda v: self._on_blur_field_changed("clarity", v))
        self.clarity_slider.sliderPressed.connect(lambda: self._on_blur_field_pressed("clarity"))
        self.clarity_slider.sliderReleased.connect(lambda: self._on_blur_field_released("clarity"))
        clarity_row.addWidget(self.clarity_slider)
        tform.addLayout(clarity_row)

        # "Value Check": non-destructive desaturate for judging value
        # relationships without color as a confound — same cache/export-
        # flag family as Blur/Line Clarity above (see study_blur.py).
        grayscale_row = QHBoxLayout()
        grayscale_row.addWidget(QLabel("Value Check"))
        self.grayscale_slider = QSlider(Qt.Horizontal)
        self.grayscale_slider.setRange(0, 100)
        self.grayscale_slider.setToolTip(
            "Desaturate the reference image on screen — judge value "
            "(light/dark) relationships without color as a distraction. "
            "Never alters the saved image; off by default for exports "
            "too (see the Export dialog)."
        )
        self.grayscale_slider.valueChanged.connect(lambda v: self._on_blur_field_changed("grayscale", v))
        self.grayscale_slider.sliderPressed.connect(lambda: self._on_blur_field_pressed("grayscale"))
        self.grayscale_slider.sliderReleased.connect(lambda: self._on_blur_field_released("grayscale"))
        grayscale_row.addWidget(self.grayscale_slider)
        tform.addLayout(grayscale_row)

        # Reset-crop button — crop is now direct manipulation via edge
        # handles on the canvas; this button just clears the crop back to
        # the full image (with undo support). Replaces the old three-button
        # Crop/Apply/Cancel flow.
        self.reset_crop_btn = QPushButton("Reset Crop")
        self.reset_crop_btn.clicked.connect(self._on_reset_crop)
        crop_row = QHBoxLayout()
        crop_row.addWidget(self.reset_crop_btn)
        tform.addLayout(crop_row)

        self.lock_box = QCheckBox("Locked")
        self.lock_box.toggled.connect(self._on_lock_toggled)
        tform.addWidget(self.lock_box)

        layout.addWidget(self.transform_box)

        # -- note text group --------------------------------------------
        self.note_box = QGroupBox("Note text")
        nlayout = QVBoxLayout(self.note_box)
        self.note_edit = _NoteEdit()
        self.note_edit.textChanged.connect(self._on_note_changed)
        self.note_edit.editing_finished.connect(self._commit_note)
        nlayout.addWidget(self.note_edit)
        layout.addWidget(self.note_box)

        # -- position (VP / horizon) -----------------------------------
        # Editable fields, not a read-only label — previously the only way
        # to reposition a vanishing point or the horizon was a canvas
        # drag; there was no way to type an exact coordinate at all.
        self.position_box = QGroupBox("Position")
        players = QVBoxLayout(self.position_box)

        self._position_x_widget = QWidget()
        x_row = QHBoxLayout(self._position_x_widget)
        x_row.setContentsMargins(0, 0, 0, 0)
        x_row.addWidget(QLabel("X"))
        self.position_x_spin = QDoubleSpinBox()
        self.position_x_spin.setRange(-50000, 50000)
        self.position_x_spin.setDecimals(2)
        self.position_x_spin.valueChanged.connect(self._on_position_changed)
        self.position_x_spin.editingFinished.connect(self._commit_position)
        x_row.addWidget(self.position_x_spin)
        players.addWidget(self._position_x_widget)

        y_row = QHBoxLayout()
        y_row.addWidget(QLabel("Y"))
        self.position_y_spin = QDoubleSpinBox()
        self.position_y_spin.setRange(-50000, 50000)
        self.position_y_spin.setDecimals(2)
        self.position_y_spin.valueChanged.connect(self._on_position_changed)
        self.position_y_spin.editingFinished.connect(self._commit_position)
        y_row.addWidget(self.position_y_spin)
        players.addLayout(y_row)

        layout.addWidget(self.position_box)

        # -- batch edit (multi-selection) --------------------------------
        # Previously selecting more than one item hid every control and
        # showed only "Multiple items selected" — no way to touch several
        # items at once without editing them one at a time.
        self.batch_box = QGroupBox("Batch Edit")
        blayout = QVBoxLayout(self.batch_box)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("Opacity"))
        op_minus = QPushButton("−5%")
        op_minus.clicked.connect(lambda: self._batch_nudge_opacity(-0.05))
        op_plus = QPushButton("+5%")
        op_plus.clicked.connect(lambda: self._batch_nudge_opacity(0.05))
        op_row.addWidget(op_minus)
        op_row.addWidget(op_plus)
        blayout.addLayout(op_row)

        self._batch_scale_widget = QWidget()
        scale_row = QHBoxLayout(self._batch_scale_widget)
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.addWidget(QLabel("Scale"))
        scale_down = QPushButton("×0.95")
        scale_down.clicked.connect(lambda: self._batch_nudge_scale(0.95))
        scale_up = QPushButton("×1.05")
        scale_up.clicked.connect(lambda: self._batch_nudge_scale(1.05))
        scale_row.addWidget(scale_down)
        scale_row.addWidget(scale_up)
        blayout.addWidget(self._batch_scale_widget)

        self._batch_align_widget = QWidget()
        align_row = QHBoxLayout(self._batch_align_widget)
        align_row.setContentsMargins(0, 0, 0, 0)
        align_row.addWidget(QLabel("Align"))
        for icon_name, mode, tip in [
            ("align_left", "left", "Align left edges"),
            ("align_right", "right", "Align right edges"),
            ("align_top", "top", "Align top edges"),
            ("align_bottom", "bottom", "Align bottom edges"),
        ]:
            btn = QToolButton()
            btn.setProperty("role", "compact")
            btn.setIcon(icons.icon(icon_name))
            icons.register(btn, lambda obj, ic: obj.setIcon(ic), icon_name)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked, m=mode: self._batch_align(m))
            align_row.addWidget(btn)
        align_row.addStretch(1)
        blayout.addWidget(self._batch_align_widget)

        batch_delete = QPushButton("Delete Selected")
        batch_delete.clicked.connect(lambda: self.request_delete.emit())
        blayout.addWidget(batch_delete)

        layout.addWidget(self.batch_box)

        self.delete_btn = QPushButton("Delete Item")
        self.delete_btn.clicked.connect(lambda: self.request_delete.emit())
        layout.addWidget(self.delete_btn)

        layout.addStretch(1)
        self.refresh()

    # -- unit conversion: scene coordinates are always 1/100 inch; shown
    # in whichever unit the current canvas spec uses (in/cm/mm/px) --------
    def _scene_to_display(self, value: float) -> float:
        inches = value / C.SCENE_PX_PER_INCH
        return C.from_inches(inches, self.scene.canvas_spec.unit)

    def _display_to_scene(self, value: float) -> float:
        inches = C.to_inches(value, self.scene.canvas_spec.unit)
        return inches * C.SCENE_PX_PER_INCH

    @staticmethod
    def _format_file_size(size: int | None) -> str:
        if size is None:
            return "Unknown"
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / 1024:.0f} KB"

    # -----------------------------------------------------------------
    def refresh(self) -> None:
        selected = self.scene.selected_items()
        item = selected[0] if len(selected) == 1 else None
        self._apply(item, multiple=len(selected) > 1)

    def _apply(self, item, multiple: bool) -> None:
        self._abort_pending_blur_drag(item)
        self._current = item

        for w in (self.info_box, self.transform_box, self.note_box, self.position_box, self.delete_btn, self.batch_box):
            w.setVisible(False)
        self.reset_crop_btn.setVisible(False)

        if item is None:
            if multiple:
                items = self.scene.selected_items()
                self.title.setText(f"{len(items)} items selected")
                self.hint.setVisible(False)
                self.batch_box.setVisible(True)
                self._batch_scale_widget.setVisible(any(hasattr(i, "set_scale_factor") for i in items))
                self._batch_align_widget.setVisible(len(items) >= 2)
            else:
                self.title.setText("Nothing selected")
                self.hint.setVisible(True)
            return

        self.hint.setVisible(False)
        self._updating = True
        try:
            if isinstance(item, ReferenceImageItem):
                self.title.setText("Reference Image")
                self.info_box.setVisible(True)
                self.info_filename_label.setText(f"File: {item.display_name}")
                self.info_format_label.setText(f"Format: {item.original_format or 'Unknown'}")
                self.info_size_label.setText(f"Original size: {self._format_file_size(item.original_file_size)}")
                self.info_dimensions_label.setText(
                    f"Dimensions: {item._source_pixmap.width()} × {item._source_pixmap.height()} px"
                )
                self.transform_box.setVisible(True)
                # "Reset Crop" button is shown whenever the image has a
                # crop applied — crop itself is done via edge handles on
                # the canvas (direct manipulation, no "enter crop mode"
                # needed). The button clears it back to full via undo.
                self.reset_crop_btn.setVisible(True)
                self.reset_crop_btn.setEnabled(not item.is_locked())
                self.reset_crop_btn.setToolTip(
                    "Unlock this image to reset crop." if item.is_locked() else ""
                )
                self.delete_btn.setVisible(True)
                # Use absolute scale for display when flipped (negative) —
                # the spin is 0.05–40, can't show negative. The sign is
                # preserved on the item itself; set_scale_factor applies
                # the absolute value, so a flipped image stays flipped.
                display_scale = abs(item.scale_factor())
                self.scale_spin.setValue(display_scale)
                self.rotation_spin.setValue(item.rotation())
                self.opacity_slider.setValue(int(item.opacity() * 100))
                self.blur_slider.setValue(int(item.blur_amount()))
                self.clarity_slider.setValue(int(item.line_clarity()))
                self.grayscale_slider.setValue(int(item.grayscale_amount()))
                self.lock_box.setChecked(item.is_locked())
                self._scale_last = item.scale_factor()
                self._rotation_last = item.rotation()

            elif isinstance(item, NoteItem):
                self.title.setText("Note")
                self.note_box.setVisible(True)
                self.delete_btn.setVisible(True)
                self.note_edit.blockSignals(True)
                self.note_edit.setPlainText(item.text())
                self.note_edit.blockSignals(False)
                self._note_last = item.text()

            elif isinstance(item, FocalPointItem):
                self.title.setText(f"Focal Point ({item.kind})")
                self.delete_btn.setVisible(True)

            elif isinstance(item, MovementLineItem):
                self.title.setText("Movement Line")
                self.delete_btn.setVisible(True)

            elif isinstance(item, MeasurementItem):
                self.title.setText(f"Measurement — {item.display_label()}")
                self.delete_btn.setVisible(True)

            elif isinstance(item, DirectionArrowItem):
                self.title.setText(f"{item.kind.title()} Direction")
                self.delete_btn.setVisible(True)

            elif isinstance(item, LightSourceItem):
                self.title.setText("Light Source")
                self.delete_btn.setVisible(True)

            elif isinstance(item, VanishingPointItem):
                self.title.setText(f"Vanishing Point ({item.label})")
                self.position_box.setVisible(True)
                self._position_x_widget.setVisible(True)
                self.position_x_spin.setValue(self._scene_to_display(item.pos().x()))
                self.position_y_spin.setValue(self._scene_to_display(item.pos().y()))

            elif isinstance(item, HorizonLineItem):
                self.title.setText("Horizon Line")
                self.position_box.setVisible(True)
                # X is fixed at 0 (HorizonLineItem.itemChange clamps every
                # drag to vertical-only) — showing an editable field that
                # always snaps back would be its own silent-no-op trap.
                self._position_x_widget.setVisible(False)
                self.position_y_spin.setValue(self._scene_to_display(item.pos().y()))
            else:
                self.title.setText(type(item).__name__)
        finally:
            self._updating = False

    # -- undo push helper -----------------------------------------------
    def _push_property(self, setter, old, new, label: str) -> None:
        scene = self.scene
        if scene is not None and hasattr(scene, "undo_stack"):
            scene.undo_stack.push(SetPropertyCommand(setter, old, new, label))

    # -- handlers -----------------------------------------------------
    def _on_scale_changed(self, value: float) -> None:
        if self._updating or not isinstance(self._current, ReferenceImageItem):
            return
        if self._scale_baseline is None:
            self._scale_baseline = self._scale_last
            self._scale_edit_item = self._current
        # Preserve the sign of any flipped axis — set_scale_factor sets both
        # axes to the same positive value, losing a flip. If the current
        # scale_x or scale_y is negative, restore that sign here.
        sx = value if self._current._scale_x > 0 else -value
        sy = value if self._current._scale_y > 0 else -value
        self._current.set_scale_xy(sx, sy)
        self._scale_last = value

    def _commit_scale(self) -> None:
        if self._scale_baseline is None:
            return
        old, item = self._scale_baseline, self._scale_edit_item
        new = self._scale_last
        self._scale_baseline = None
        self._scale_edit_item = None
        if item is not None and old != new:
            self._push_property(item.set_scale_factor, old, new, "Change scale")

    def _on_rotation_changed(self, value: float) -> None:
        if self._updating or not isinstance(self._current, ReferenceImageItem):
            return
        if self._rotation_baseline is None:
            self._rotation_baseline = self._rotation_last
            self._rotation_edit_item = self._current
        self._current.setRotation(value)
        self._rotation_last = value

    def _commit_rotation(self) -> None:
        if self._rotation_baseline is None:
            return
        old, item = self._rotation_baseline, self._rotation_edit_item
        new = self._rotation_last
        self._rotation_baseline = None
        self._rotation_edit_item = None
        if item is not None and old != new:
            self._push_property(item.setRotation, old, new, "Change rotation")

    def _on_position_changed(self, _value: float) -> None:
        if self._updating or self._current is None or not hasattr(self._current, "setPos"):
            return
        if self._position_baseline is None:
            self._position_baseline = self._current.pos()
            self._position_edit_item = self._current
        x = (
            self._display_to_scene(self.position_x_spin.value())
            if self._position_x_widget.isVisible()
            else self._current.pos().x()
        )
        y = self._display_to_scene(self.position_y_spin.value())
        self._current.setPos(x, y)

    def _commit_position(self) -> None:
        if self._position_baseline is None:
            return
        old, item = self._position_baseline, self._position_edit_item
        self._position_baseline = None
        self._position_edit_item = None
        if item is not None:
            new = item.pos()
            if old != new:
                self._push_property(item.setPos, old, new, "Move point")

    # -- batch edit (multi-selection) --------------------------------------
    def _batch_nudge_opacity(self, delta: float) -> None:
        items = self.scene.selected_items()
        if not items:
            return
        stack = self.scene.undo_stack
        multi = len(items) > 1
        if multi:
            stack.beginMacro("Nudge opacity")
        try:
            for item in items:
                old = item.opacity()
                new = max(0.05, min(1.0, old + delta))
                if new != old:
                    stack.push(SetPropertyCommand(item.setOpacity, old, new, "Change opacity"))
        finally:
            if multi:
                stack.endMacro()

    def _batch_nudge_scale(self, factor: float) -> None:
        items = [i for i in self.scene.selected_items() if hasattr(i, "set_scale_factor")]
        if not items:
            return
        stack = self.scene.undo_stack
        multi = len(items) > 1
        if multi:
            stack.beginMacro("Scale selection")
        try:
            for item in items:
                old = item.scale_factor()
                new = max(0.05, min(40.0, old * factor))
                if new != old:
                    stack.push(SetPropertyCommand(item.set_scale_factor, old, new, "Change scale"))
        finally:
            if multi:
                stack.endMacro()

    def _batch_align(self, mode: str) -> None:
        items = self.scene.selected_items()
        if len(items) < 2:
            return
        xs = [i.pos().x() for i in items]
        ys = [i.pos().y() for i in items]
        stack = self.scene.undo_stack
        stack.beginMacro(f"Align {mode}")
        try:
            for item in items:
                old = item.pos()
                if mode == "left":
                    new = QPointF(min(xs), old.y())
                elif mode == "right":
                    new = QPointF(max(xs), old.y())
                elif mode == "top":
                    new = QPointF(old.x(), min(ys))
                else:
                    new = QPointF(old.x(), max(ys))
                if new != old:
                    stack.push(SetPropertyCommand(item.setPos, old, new, f"Align {mode}"))
        finally:
            stack.endMacro()

    def _on_opacity_changed(self, value: int) -> None:
        if not self._updating and self._current is not None:
            self._current.setOpacity(value / 100)

    def _on_opacity_pressed(self) -> None:
        if self._current is not None:
            self._opacity_baseline = self._current.opacity()
            self._opacity_edit_item = self._current

    def _on_opacity_released(self) -> None:
        if self._opacity_baseline is None:
            return
        old, item = self._opacity_baseline, self._opacity_edit_item
        self._opacity_baseline = None
        self._opacity_edit_item = None
        if item is not None:
            new = item.opacity()
            if old != new:
                self._push_property(item.setOpacity, old, new, "Change opacity")

    # -- Study Blur / Value Check --------------------------------------------
    def _on_blur_field_pressed(self, field: str) -> None:
        if self._current is None or not isinstance(self._current, ReferenceImageItem):
            return
        item = self._current
        # Suppresses the setters' own immediate recompute for the
        # duration of this drag — see ReferenceImageItem.
        # set_defer_blur_refresh() for why that matters.
        item.set_defer_blur_refresh(True)
        if field == "blur":
            self._blur_baseline = item.blur_amount()
            self._blur_edit_item = item
        elif field == "clarity":
            self._clarity_baseline = item.line_clarity()
            self._clarity_edit_item = item
        else:
            self._grayscale_baseline = item.grayscale_amount()
            self._grayscale_edit_item = item

    def _on_blur_field_changed(self, field: str, value: int) -> None:
        if self._updating or self._current is None:
            return
        item = self._current
        if field == "blur":
            item.set_blur_amount(value)
        elif field == "clarity":
            item.set_line_clarity(value)
        else:
            item.set_grayscale_amount(value)
        # Only schedules the debounced preview recompute — set_blur_amount()/
        # set_line_clarity()/set_grayscale_amount() above already trigger a
        # plain repaint via update(), which redraws whatever's still
        # cached from before this tick (see ReferenceImageItem.
        # _get_processed_display_pixmap()).
        self._blur_preview_timer.start()

    def _apply_blur_preview(self) -> None:
        item = self._blur_edit_item or self._clarity_edit_item or self._grayscale_edit_item or self._current
        if isinstance(item, ReferenceImageItem):
            item._refresh_processed_pixmap()
            item.update()

    def _on_blur_field_released(self, field: str) -> None:
        if field == "blur":
            baseline, item = self._blur_baseline, self._blur_edit_item
            self._blur_baseline = None
            self._blur_edit_item = None
        elif field == "clarity":
            baseline, item = self._clarity_baseline, self._clarity_edit_item
            self._clarity_baseline = None
            self._clarity_edit_item = None
        else:
            baseline, item = self._grayscale_baseline, self._grayscale_edit_item
            self._grayscale_baseline = None
            self._grayscale_edit_item = None
        if baseline is None or item is None:
            return
        self._finish_blur_drag(field, baseline, item)

    def _finish_blur_drag(self, field: str, baseline, item) -> None:
        """Shared by a normal slider release and _abort_pending_blur_drag()
        below (an interrupted drag — e.g. Delete pressed while still
        holding the slider) — both need the same cleanup: stop deferring
        this item's recompute, force one final immediate recompute
        rather than leaving it to the debounce timer, and commit an undo
        step if the value actually changed.
        """
        item.set_defer_blur_refresh(False)
        self._blur_preview_timer.stop()
        item._refresh_processed_pixmap()
        item.update()
        if field == "blur":
            new, setter, label = item.blur_amount(), item.set_blur_amount, "Change blur"
        elif field == "clarity":
            new, setter, label = item.line_clarity(), item.set_line_clarity, "Change line clarity"
        else:
            new, setter, label = item.grayscale_amount(), item.set_grayscale_amount, "Change value check"
        if baseline != new:
            self._push_property(setter, baseline, new, label)

    def _abort_pending_blur_drag(self, new_item) -> None:
        """Called at the top of _apply() (every refresh: selection
        change, undo/redo, item add/delete) — if a Blur/Line Clarity/
        Value Check press is still pending (mouse down, sliderReleased
        never fired)
        for an item that's about to stop being the selection, finish it
        as an implicit release instead of leaving set_defer_blur_refresh
        (True) stuck forever on an item nothing will ever un-defer again
        (e.g. Delete pressed mid-drag: selection clears, sliderReleased
        never comes, and every later non-deferred setter call — undo/redo
        of an earlier change — would silently skip recomputing the
        processed-pixmap cache from then on).
        """
        if self._blur_edit_item is not None and self._blur_edit_item is not new_item:
            self._finish_blur_drag("blur", self._blur_baseline, self._blur_edit_item)
            self._blur_baseline = None
            self._blur_edit_item = None
        if self._clarity_edit_item is not None and self._clarity_edit_item is not new_item:
            self._finish_blur_drag("clarity", self._clarity_baseline, self._clarity_edit_item)
            self._clarity_baseline = None
            self._clarity_edit_item = None
        if self._grayscale_edit_item is not None and self._grayscale_edit_item is not new_item:
            self._finish_blur_drag("grayscale", self._grayscale_baseline, self._grayscale_edit_item)
            self._grayscale_baseline = None
            self._grayscale_edit_item = None

    def _on_lock_toggled(self, on: bool) -> None:
        # Lock state is deliberately excluded from undo/redo (Phase 0
        # decision: undo represents artwork-setup changes, not workflow
        # state) — this stays a direct call.
        if not self._updating and isinstance(self._current, ReferenceImageItem):
            self._current.set_locked(on)
            self.reset_crop_btn.setEnabled(not on)
            self.reset_crop_btn.setToolTip("Unlock this image to reset crop." if on else "")

    def _on_note_changed(self) -> None:
        if self._updating or not isinstance(self._current, NoteItem):
            return
        if self._note_baseline is None:
            self._note_baseline = self._note_last
            self._note_edit_item = self._current
        text = self.note_edit.toPlainText()
        self._current.set_text(text)
        self._note_last = text

    def _commit_note(self) -> None:
        if self._note_baseline is None:
            return
        old, item = self._note_baseline, self._note_edit_item
        new = self._note_last
        self._note_baseline = None
        self._note_edit_item = None
        if item is not None and old != new:
            scene = self.scene
            if scene is not None and hasattr(scene, "undo_stack"):
                scene.undo_stack.push(SetNoteTextCommand(item, old, new))

    def _on_reset_crop(self) -> None:
        if isinstance(self._current, ReferenceImageItem):
            self._current.reset_crop()
