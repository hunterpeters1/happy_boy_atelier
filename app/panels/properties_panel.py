"""Properties dock: a contextual inspector for whatever is currently
selected on the canvas. One panel, rows shown/hidden per item type, rather
than a maze of per-type stacked pages.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..canvas.undo_commands import SetNoteTextCommand, SetPropertyCommand
from ..layers.reference_layer import ReferenceImageItem
from ..layers.composition_layer import FocalPointItem, MovementLineItem, NoteItem
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.title = QLabel("Nothing selected")
        self.title.setProperty("role", "section")
        layout.addWidget(self.title)

        self.hint = QLabel("Select an item on the canvas to edit its properties.")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

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
            "canvas instead — hold Shift while dragging to lock proportions."
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

        crop_row = QHBoxLayout()
        self.crop_btn = QPushButton("Crop…")
        self.crop_btn.clicked.connect(self._on_crop_clicked)
        self.crop_apply_btn = QPushButton("Apply Crop")
        self.crop_apply_btn.clicked.connect(self._on_crop_apply)
        self.crop_cancel_btn = QPushButton("Cancel")
        self.crop_cancel_btn.clicked.connect(self._on_crop_cancel)
        crop_row.addWidget(self.crop_btn)
        crop_row.addWidget(self.crop_apply_btn)
        crop_row.addWidget(self.crop_cancel_btn)
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

        # -- position readout (VP / horizon / light source) ---------------
        self.position_box = QGroupBox("Position")
        players = QVBoxLayout(self.position_box)
        self.position_label = QLabel("")
        self.position_label.setProperty("role", "hint")
        players.addWidget(self.position_label)
        layout.addWidget(self.position_box)

        self.delete_btn = QPushButton("Delete Item")
        self.delete_btn.clicked.connect(lambda: self.request_delete.emit())
        layout.addWidget(self.delete_btn)

        layout.addStretch(1)
        self.refresh()

    # -----------------------------------------------------------------
    def refresh(self) -> None:
        selected = self.scene.selectedItems()
        item = selected[0] if len(selected) == 1 else None
        self._apply(item, multiple=len(selected) > 1)

    def show_item(self, item) -> None:
        """Point the inspector at `item` directly — used by the canvas's
        click handlers as a direct hand-off, independent of whatever Qt's
        selectedItems()/isSelected() bookkeeping reports at the moment.
        """
        self._apply(item, multiple=False)

    def _apply(self, item, multiple: bool) -> None:
        self._current = item

        for w in (self.transform_box, self.note_box, self.position_box, self.delete_btn):
            w.setVisible(False)
        self.crop_apply_btn.setVisible(False)
        self.crop_cancel_btn.setVisible(False)
        self.crop_btn.setVisible(False)

        if item is None:
            self.title.setText("Multiple items selected" if multiple else "Nothing selected")
            self.hint.setVisible(True)
            return

        self.hint.setVisible(False)
        self._updating = True
        try:
            if isinstance(item, ReferenceImageItem):
                self.title.setText("Reference Image")
                self.transform_box.setVisible(True)
                self.crop_btn.setVisible(True)
                self.delete_btn.setVisible(True)
                self.scale_spin.setValue(item.scale_factor())
                self.rotation_spin.setValue(item.rotation())
                self.opacity_slider.setValue(int(item.opacity() * 100))
                self.lock_box.setChecked(item.is_locked())
                self._scale_last = item.scale_factor()
                self._rotation_last = item.rotation()
                if item.is_cropping():
                    self.crop_apply_btn.setVisible(True)
                    self.crop_cancel_btn.setVisible(True)

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

            elif isinstance(item, DirectionArrowItem):
                self.title.setText(f"{item.kind.title()} Direction")
                self.delete_btn.setVisible(True)

            elif isinstance(item, LightSourceItem):
                self.title.setText("Light Source")
                self.delete_btn.setVisible(True)

            elif isinstance(item, VanishingPointItem):
                self.title.setText(f"Vanishing Point ({item.label})")
                self.position_box.setVisible(True)
                self.position_label.setText(f"x={item.pos().x():.0f}  y={item.pos().y():.0f}")

            elif isinstance(item, HorizonLineItem):
                self.title.setText("Horizon Line")
                self.position_box.setVisible(True)
                self.position_label.setText(f"y={item.pos().y():.0f}")
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
        self._current.set_scale_factor(value)
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

    def _on_lock_toggled(self, on: bool) -> None:
        # Lock state is deliberately excluded from undo/redo (Phase 0
        # decision: undo represents artwork-setup changes, not workflow
        # state) — this stays a direct call.
        if not self._updating and isinstance(self._current, ReferenceImageItem):
            self._current.set_locked(on)

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

    def _on_crop_clicked(self) -> None:
        if isinstance(self._current, ReferenceImageItem):
            self._current.enter_crop_mode()
            self.refresh()

    def _on_crop_apply(self) -> None:
        if isinstance(self._current, ReferenceImageItem):
            self._current.apply_crop()
            self.refresh()

    def _on_crop_cancel(self) -> None:
        if isinstance(self._current, ReferenceImageItem):
            self._current.cancel_crop()
            self.refresh()
