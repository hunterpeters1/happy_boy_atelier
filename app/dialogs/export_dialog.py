"""Export panel: destination, format, and (secondary) resolution on one
surface.

Previously this dialog only chose format/DPI — clicking OK then opened a
second, entirely separate native Save dialog with no filename suggested
from the project name, so exporting was always at least two dialogs and
two decisions. The destination now lives here too, pre-filled from the
project's own name and the project file's own folder. DPI is a real,
useful setting (it controls the actual pixel size of the exported
raster) but reads as an odd, overly technical first-thing-you-see —
"Choose Destination…" is now the prominent, first action (a real native
file dialog, same as Save As), with format next and DPI last as a small
secondary field that most artists can just leave alone.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
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
        # Only set once the artist actually uses Choose Destination… —
        # until then the destination is fully computed from project name +
        # format, and keeps recomputing live as the format radio changes.
        self._explicit_path: Path | None = None

        layout = QVBoxLayout(self)

        # -- destination: the prominent, first action — a real native file
        # dialog, exactly like Save As, rather than a small "Browse…"
        # button tucked next to an easy-to-miss text field.
        dest_row = QHBoxLayout()
        choose_btn = QPushButton("Choose Destination…")
        choose_btn.setDefault(True)
        choose_btn.clicked.connect(self._on_browse)
        dest_row.addWidget(choose_btn)
        self.dest_label = QLabel()
        self.dest_label.setWordWrap(True)
        self.dest_label.setProperty("role", "hint")
        dest_row.addWidget(self.dest_label, 1)
        layout.addLayout(dest_row)

        layout.addSpacing(8)

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

        layout.addSpacing(8)

        # -- DPI: still real (it sets the exported raster's actual pixel
        # size) but secondary — most artists never need to touch it, so it
        # no longer competes with destination/format for attention.
        form = QFormLayout()
        dpi_label = QLabel("Output DPI")
        dpi_label.setProperty("role", "hint")
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setToolTip(
            "Resolution of the exported image, in pixels per inch. 300 is a "
            "standard print resolution; higher only matters for large-format "
            "or professional printing. Not used for PDF (vector output)."
        )
        form.addRow(dpi_label, self.dpi_spin)
        layout.addLayout(form)
        self.pdf_radio.toggled.connect(lambda on: self.dpi_spin.setEnabled(not on))

        layout.addSpacing(8)
        self.study_effect_check = QCheckBox("Include Study Blur effect")
        self.study_effect_check.setToolTip(
            "Off by default: exports always render the crisp original "
            "regardless of any Blur/Line Clarity dialed in on screen. "
            "Check this to bake whatever's currently set on each "
            "reference image into this export instead."
        )
        layout.addWidget(self.study_effect_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_destination_preview()

    def _update_destination_preview(self) -> None:
        fmt = self.selected_format()
        if self._explicit_path is not None:
            path = self._explicit_path.with_suffix(f".{fmt}")
        else:
            path = self._dir / f"{self._stem}.{fmt}"
        self.dest_label.setText(str(path))

    def _on_browse(self) -> None:
        fmt = self.selected_format()
        current = self._explicit_path or (self._dir / f"{self._stem}.{fmt}")
        filename, _ = QFileDialog.getSaveFileName(self, "Export", str(current), _FILTERS[fmt])
        if filename:
            self._explicit_path = Path(filename)
            self._update_destination_preview()

    def selected_format(self) -> str:
        if self.jpg_radio.isChecked():
            return "jpg"
        if self.pdf_radio.isChecked():
            return "pdf"
        return "png"

    def dpi(self) -> int:
        return self.dpi_spin.value()

    def include_study_effect(self) -> bool:
        return self.study_effect_check.isChecked()

    def destination_path(self) -> Path:
        fmt = self.selected_format()
        text = self.dest_label.text().strip()
        path = Path(text) if text else self._dir / f"{self._stem}.{fmt}"
        if path.suffix.lower() != f".{fmt}":
            path = path.with_suffix(f".{fmt}")
        return path
