"""Export panel: format, resolution, and destination on one surface.

Previously this dialog only chose format/DPI — clicking OK then opened a
second, entirely separate native Save dialog with no filename suggested
from the project name, so exporting was always at least two dialogs and
two decisions. The destination now lives here too, pre-filled from the
project's own name and the project file's own folder, with a live
preview that updates as the format changes and a Browse… button only for
when the artist actually wants to override it.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

_FILTERS = {"png": "PNG Image (*.png)", "jpg": "JPEG Image (*.jpg)", "pdf": "PDF Planning Sheet (*.pdf)"}
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_filename(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "Untitled Painting"


class ExportDialog(QDialog):
    def __init__(self, project_name: str, default_dir: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(440)
        self._stem = _sanitize_filename(project_name)
        self._dir = default_dir
        # Only set once the artist actually uses Browse… — until then the
        # destination is fully computed from project name + format, and
        # keeps recomputing live as the format radio changes.
        self._explicit_path: Path | None = None

        layout = QVBoxLayout(self)

        self.group = QButtonGroup(self)
        row = QHBoxLayout()
        self.png_radio = QRadioButton("PNG")
        self.png_radio.setChecked(True)
        self.jpg_radio = QRadioButton("JPG")
        self.pdf_radio = QRadioButton("PDF Planning Sheet")
        for r in (self.png_radio, self.jpg_radio, self.pdf_radio):
            self.group.addButton(r)
            r.toggled.connect(self._update_destination_preview)
            row.addWidget(r)
        layout.addLayout(row)

        form = QFormLayout()
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        form.addRow("Output DPI", self.dpi_spin)
        layout.addLayout(form)
        self.pdf_radio.toggled.connect(lambda on: self.dpi_spin.setEnabled(not on))

        dest_row = QHBoxLayout()
        self.dest_edit = QLineEdit()
        self.dest_edit.textEdited.connect(self._on_dest_edited)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        dest_row.addWidget(self.dest_edit, 1)
        dest_row.addWidget(browse_btn)
        dest_form = QFormLayout()
        dest_form.addRow("Save as", dest_row)
        layout.addLayout(dest_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_destination_preview()

    def _on_dest_edited(self, text: str) -> None:
        self._explicit_path = Path(text) if text.strip() else None

    def _update_destination_preview(self) -> None:
        fmt = self.selected_format()
        if self._explicit_path is not None:
            path = self._explicit_path.with_suffix(f".{fmt}")
        else:
            path = self._dir / f"{self._stem}.{fmt}"
        self.dest_edit.blockSignals(True)
        self.dest_edit.setText(str(path))
        self.dest_edit.blockSignals(False)

    def _on_browse(self) -> None:
        fmt = self.selected_format()
        filename, _ = QFileDialog.getSaveFileName(self, "Export", self.dest_edit.text(), _FILTERS[fmt])
        if filename:
            self._explicit_path = Path(filename)
            self.dest_edit.setText(filename)

    def selected_format(self) -> str:
        if self.jpg_radio.isChecked():
            return "jpg"
        if self.pdf_radio.isChecked():
            return "pdf"
        return "png"

    def dpi(self) -> int:
        return self.dpi_spin.value()

    def destination_path(self) -> Path:
        fmt = self.selected_format()
        text = self.dest_edit.text().strip()
        path = Path(text) if text else self._dir / f"{self._stem}.{fmt}"
        if path.suffix.lower() != f".{fmt}":
            path = path.with_suffix(f".{fmt}")
        return path
