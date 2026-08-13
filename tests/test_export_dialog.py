"""ExportDialog's batch export presets: save/recall a named
{format, dpi, include_study_effect} combo via QSettings — never the
destination, which stays per-export. See export_dialog.py's
_PRESETS_SETTINGS_KEY comment for why presets are JSON-serialized into a
single QSettings string value rather than relying on QSettings' own
dict/bool marshalling.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings

from app import settings as user_settings
from app.dialogs.export_dialog import ExportDialog, _PRESETS_SETTINGS_KEY, _load_presets


@pytest.fixture
def clean_export_presets(qapp):
    QSettings().remove(_PRESETS_SETTINGS_KEY)
    yield
    QSettings().remove(_PRESETS_SETTINGS_KEY)


@pytest.fixture
def clean_settings(qapp):
    QSettings().remove("settings/defaultExportDpi")
    yield
    QSettings().remove("settings/defaultExportDpi")


def _dialog(clean_export_presets) -> ExportDialog:
    return ExportDialog("My Painting", Path("/tmp"))


def test_fresh_dialog_has_only_the_none_preset(clean_export_presets):
    dlg = _dialog(clean_export_presets)
    assert [dlg.preset_combo.itemText(i) for i in range(dlg.preset_combo.count())] == ["(none)"]
    assert dlg.delete_preset_btn.isEnabled() is False


def test_dpi_defaults_to_300_when_no_preference_set(clean_export_presets, clean_settings):
    dlg = _dialog(clean_export_presets)
    assert dlg.dpi() == 300


def test_dpi_seeds_from_the_preferred_default(clean_export_presets, clean_settings):
    user_settings.set_default_export_dpi(150)
    dlg = _dialog(clean_export_presets)
    assert dlg.dpi() == 150


def test_save_preset_persists_current_field_values(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    dlg.jpg_radio.setChecked(True)
    dlg.dpi_spin.setValue(150)
    dlg.study_effect_check.setChecked(True)

    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("Critique Pack", True))
    dlg._on_save_preset()

    assert _load_presets() == {
        "Critique Pack": {"format": "jpg", "dpi": 150, "include_study_effect": True}
    }
    assert dlg.preset_combo.currentText() == "Critique Pack"


def test_save_preset_with_empty_name_or_cancel_does_nothing(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("", False))
    dlg._on_save_preset()
    assert _load_presets() == {}

    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("  ", True))
    dlg._on_save_preset()
    assert _load_presets() == {}


def test_selecting_a_preset_applies_its_fields(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    dlg.pdf_radio.setChecked(True)
    dlg.dpi_spin.setValue(600)
    dlg.study_effect_check.setChecked(True)
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("Hi-Res", True))
    dlg._on_save_preset()  # leaves "Hi-Res" as the current combo selection

    # reset fields back to defaults, and the combo to "(none)" -- otherwise
    # re-selecting an already-current index is a no-op (Qt doesn't re-fire
    # currentIndexChanged for an unchanged selection), which would trivially
    # "pass" without ever exercising _on_preset_selected() a second time.
    dlg.png_radio.setChecked(True)
    dlg.dpi_spin.setValue(300)
    dlg.study_effect_check.setChecked(False)
    dlg.preset_combo.setCurrentIndex(0)

    dlg.preset_combo.setCurrentIndex(dlg.preset_combo.findText("Hi-Res"))

    assert dlg.selected_format() == "pdf"
    assert dlg.dpi() == 600
    assert dlg.include_study_effect() is True
    assert dlg.delete_preset_btn.isEnabled() is True


def test_selecting_none_does_not_touch_current_fields(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    dlg.jpg_radio.setChecked(True)
    dlg.dpi_spin.setValue(150)
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("X", True))
    dlg._on_save_preset()

    dlg.preset_combo.setCurrentIndex(0)  # "(none)"

    assert dlg.selected_format() == "jpg"
    assert dlg.dpi() == 150
    assert dlg.delete_preset_btn.isEnabled() is False


def test_presets_persist_across_dialog_instances(clean_export_presets, monkeypatch):
    dlg1 = _dialog(clean_export_presets)
    dlg1.png_radio.setChecked(True)
    dlg1.dpi_spin.setValue(72)
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("Web Draft", True))
    dlg1._on_save_preset()

    dlg2 = ExportDialog("A Different Painting", Path("/tmp"))
    assert "Web Draft" in [dlg2.preset_combo.itemText(i) for i in range(dlg2.preset_combo.count())]


def test_delete_preset_removes_it(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("Temp", True))
    dlg._on_save_preset()
    assert "Temp" in _load_presets()

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr("app.dialogs.export_dialog.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    dlg._on_delete_preset()

    assert _load_presets() == {}
    assert [dlg.preset_combo.itemText(i) for i in range(dlg.preset_combo.count())] == ["(none)"]


def test_delete_preset_declined_keeps_it(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("Keep Me", True))
    dlg._on_save_preset()

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr("app.dialogs.export_dialog.QMessageBox.question", lambda *a, **k: QMessageBox.No)
    dlg._on_delete_preset()

    assert "Keep Me" in _load_presets()


def test_saving_a_preset_never_touches_destination(clean_export_presets, monkeypatch):
    dlg = _dialog(clean_export_presets)
    original_destination = dlg.destination_path()
    monkeypatch.setattr("app.dialogs.export_dialog.QInputDialog.getText", lambda *a, **k: ("Some Preset", True))
    dlg._on_save_preset()

    assert "destination" not in _load_presets()["Some Preset"]
    assert dlg.destination_path() == original_destination
