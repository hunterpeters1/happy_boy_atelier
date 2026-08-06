"""New Painting dialog: pick a canvas format (portrait / landscape / square
presets, or fully custom width/height/unit)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from .. import constants as C
from ..project import CanvasSpec

_CATEGORIES = {
    "Portrait": C.PORTRAIT_FORMATS,
    "Landscape": C.LANDSCAPE_FORMATS,
    "Square": C.SQUARE_FORMATS,
}


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Painting")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit("Untitled Painting")
        form.addRow("Title", self.name_edit)
        layout.addLayout(form)

        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("Format"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Portrait", "Landscape", "Square", "Custom"])
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        cat_row.addWidget(self.category_combo)
        layout.addLayout(cat_row)

        self.preset_list = QListWidget()
        self.preset_list.setMaximumHeight(140)
        layout.addWidget(self.preset_list)

        self.custom_group = QGroupBox("Custom Dimensions")
        cform = QFormLayout(self.custom_group)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 500)
        self.width_spin.setValue(16)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.5, 500)
        self.height_spin.setValue(20)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(C.UNITS)
        cform.addRow("Width", self.width_spin)
        cform.addRow("Height", self.height_spin)
        cform.addRow("Unit", self.unit_combo)
        layout.addWidget(self.custom_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_category_changed("Portrait")

    def _on_category_changed(self, category: str) -> None:
        self.preset_list.clear()
        is_custom = category == "Custom"
        self.custom_group.setVisible(is_custom)
        self.preset_list.setVisible(not is_custom)
        if not is_custom:
            for label, w, h in _CATEGORIES[category]:
                entry = QListWidgetItem(f'{label} in')
                entry.setData(Qt.UserRole, (w, h))
                self.preset_list.addItem(entry)
            self.preset_list.setCurrentRow(0)

    def canvas_spec(self) -> CanvasSpec:
        name = self.name_edit.text().strip() or "Untitled Painting"
        category = self.category_combo.currentText()
        if category == "Custom":
            return CanvasSpec(name=name, width=self.width_spin.value(),
                               height=self.height_spin.value(), unit=self.unit_combo.currentText())
        current = self.preset_list.currentItem()
        w, h = current.data(Qt.UserRole) if current else (16, 20)
        return CanvasSpec(name=name, width=float(w), height=float(h), unit="in")
