"""Options > Settings…: a handful of standard, low-risk defaults the
artist can customize — never project state (see app/settings.py's own
module docstring). Same QDialog-via-global-stylesheet pattern every other
dialog in this app already establishes; no bespoke styling needed.

Fields are seeded from the current settings and only written back on
Save — Cancel discards anything changed in the dialog, matching
NewProjectDialog/ExportDialog's own accept/reject convention.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from .. import constants as C
from .. import settings


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.autosave_combo = QComboBox()
        for ms in settings.AUTOSAVE_CHOICES_MS:
            self.autosave_combo.addItem(settings.AUTOSAVE_CHOICE_LABELS[ms], ms)
        self._set_combo_by_data(self.autosave_combo, settings.autosave_interval_ms())
        autosave_label = QLabel("Autosave")
        autosave_label.setToolTip(
            "How often unsaved work is written to the crash-recovery "
            "slot. Separate from your own Save/Save As, which stays "
            "fully manual either way."
        )
        form.addRow(autosave_label, self.autosave_combo)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(C.UNITS)
        self.unit_combo.setCurrentText(settings.default_unit())
        form.addRow("Default unit for New Painting", self.unit_combo)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(settings.default_export_dpi())
        form.addRow("Default export DPI", self.dpi_spin)

        self.rulers_check = QCheckBox("Show rulers on new windows")
        self.rulers_check.setChecked(settings.show_rulers_by_default())
        form.addRow("", self.rulers_check)

        self.accents_check = QCheckBox("Futuristic UI accents")
        self.accents_check.setChecked(settings.futuristic_accents_enabled())
        self.accents_check.setToolTip(
            "A subtle glow pulse on the active tool, an eased fade-in for "
            "selection handles and restored panels, and softened movement-"
            "line curves. Purely cosmetic — turning this off makes each of "
            "those instant/hard-edged instead, nothing is removed."
        )
        form.addRow("", self.accents_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _on_save(self) -> None:
        settings.set_autosave_interval_ms(self.autosave_combo.currentData())
        settings.set_default_unit(self.unit_combo.currentText())
        settings.set_default_export_dpi(self.dpi_spin.value())
        settings.set_show_rulers_by_default(self.rulers_check.isChecked())
        settings.set_futuristic_accents_enabled(self.accents_check.isChecked())
        self.accept()
