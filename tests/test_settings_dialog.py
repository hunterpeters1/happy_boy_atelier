"""SettingsDialog (Options > Settings…): fields seed from current
settings, Save persists all five, Cancel discards everything changed in
the dialog.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings

from app import settings
from app.dialogs.settings_dialog import SettingsDialog


@pytest.fixture
def clean_settings(qapp):
    keys = [
        "settings/autosaveIntervalMs", "settings/defaultUnit",
        "settings/defaultExportDpi", "settings/showRulersByDefault",
        "settings/futuristicAccentsEnabled",
    ]
    for key in keys:
        QSettings().remove(key)
    yield
    for key in keys:
        QSettings().remove(key)


def test_fields_seed_from_current_settings(clean_settings):
    settings.set_autosave_interval_ms(settings.AUTOSAVE_OFF_MS)
    settings.set_default_unit("mm")
    settings.set_default_export_dpi(150)
    settings.set_show_rulers_by_default(False)
    settings.set_futuristic_accents_enabled(False)

    dlg = SettingsDialog()

    assert dlg.autosave_combo.currentData() == settings.AUTOSAVE_OFF_MS
    assert dlg.unit_combo.currentText() == "mm"
    assert dlg.dpi_spin.value() == 150
    assert dlg.rulers_check.isChecked() is False
    assert dlg.accents_check.isChecked() is False


def test_fields_seed_from_defaults_when_nothing_set(clean_settings):
    dlg = SettingsDialog()

    assert dlg.autosave_combo.currentData() == 3 * 60 * 1000
    assert dlg.unit_combo.currentText() == "in"
    assert dlg.dpi_spin.value() == 300
    assert dlg.rulers_check.isChecked() is True
    assert dlg.accents_check.isChecked() is True


def test_save_persists_all_five_fields(clean_settings):
    dlg = SettingsDialog()
    dlg.autosave_combo.setCurrentIndex(dlg.autosave_combo.findData(60_000))
    dlg.unit_combo.setCurrentText("px")
    dlg.dpi_spin.setValue(600)
    dlg.rulers_check.setChecked(False)
    dlg.accents_check.setChecked(False)

    dlg._on_save()

    assert settings.autosave_interval_ms() == 60_000
    assert settings.default_unit() == "px"
    assert settings.default_export_dpi() == 600
    assert settings.show_rulers_by_default() is False
    assert settings.futuristic_accents_enabled() is False


def test_save_accepts_the_dialog(clean_settings):
    dlg = SettingsDialog()
    dlg._on_save()
    assert dlg.result() == SettingsDialog.Accepted


def test_cancel_does_not_persist_changes(clean_settings):
    dlg = SettingsDialog()
    dlg.dpi_spin.setValue(600)
    dlg.unit_combo.setCurrentText("cm")
    dlg.accents_check.setChecked(False)

    dlg.reject()

    assert settings.default_export_dpi() == 300
    assert settings.default_unit() == "in"
    assert settings.futuristic_accents_enabled() is True
