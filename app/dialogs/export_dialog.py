"""Export dialog: PNG / JPG raster export, or a PDF planning sheet."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)

        self.group = QButtonGroup(self)
        row = QHBoxLayout()
        self.png_radio = QRadioButton("PNG")
        self.png_radio.setChecked(True)
        self.jpg_radio = QRadioButton("JPG")
        self.pdf_radio = QRadioButton("PDF Planning Sheet")
        for r in (self.png_radio, self.jpg_radio, self.pdf_radio):
            self.group.addButton(r)
            row.addWidget(r)
        layout.addLayout(row)

        form = QFormLayout()
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        form.addRow("Output DPI", self.dpi_spin)
        layout.addLayout(form)

        self.pdf_radio.toggled.connect(lambda on: self.dpi_spin.setEnabled(not on))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_format(self) -> str:
        if self.jpg_radio.isChecked():
            return "jpg"
        if self.pdf_radio.isChecked():
            return "pdf"
        return "png"

    def dpi(self) -> int:
        return self.dpi_spin.value()
