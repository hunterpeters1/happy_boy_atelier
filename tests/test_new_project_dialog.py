"""NewProjectDialog's Templates section: hidden with no saved templates,
clicking a template fills width/height/unit and stages its guides dict;
clicking a plain size preset afterward clears any staged template guides
back to None. See project_templates.py and app/dialogs/new_project_dialog.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings

from app import project_templates
from app import settings as user_settings
from app.dialogs.new_project_dialog import NewProjectDialog
from app.project_templates import _SETTINGS_KEY


@pytest.fixture
def clean_templates(qapp):
    QSettings().remove(_SETTINGS_KEY)
    yield
    QSettings().remove(_SETTINGS_KEY)


@pytest.fixture
def clean_settings(qapp):
    QSettings().remove("settings/defaultUnit")
    yield
    QSettings().remove("settings/defaultUnit")


def test_template_section_hidden_with_no_saved_templates(clean_templates):
    dlg = NewProjectDialog()
    assert dlg.template_section_label.isHidden()
    assert dlg.template_list.isHidden()
    assert dlg.selected_template_guides() is None


def test_default_unit_falls_back_to_inches_when_no_preference_set(clean_templates, clean_settings):
    dlg = NewProjectDialog()
    assert dlg.unit_combo.currentText() == "in"
    assert dlg.width_spin.value() == 16.0
    assert dlg.height_spin.value() == 20.0


def test_size_seeds_from_the_preferred_unit_converting_the_same_physical_size(
    clean_templates, clean_settings
):
    user_settings.set_default_unit("cm")

    dlg = NewProjectDialog()

    assert dlg.unit_combo.currentText() == "cm"
    # 16x20in converted to cm, not the raw 16/20 numbers reinterpreted as
    # cm (which would be a tiny ~6x8in canvas instead of the intended
    # 16x20in default just shown in a different unit).
    assert dlg.width_spin.value() == pytest.approx(40.64, abs=0.01)
    assert dlg.height_spin.value() == pytest.approx(50.8, abs=0.01)


def test_template_section_visible_and_populated_with_saved_templates(clean_templates):
    project_templates.save_template(
        "Studio Portrait", width=11.0, height=14.0, unit="in",
        guides={"rule_of_thirds": True, "golden_ratio": False, "inch_grid": False},
    )
    dlg = NewProjectDialog()
    assert not dlg.template_section_label.isHidden()
    assert not dlg.template_list.isHidden()
    assert dlg.template_list.count() == 1
    assert dlg.template_list.item(0).text() == "Studio Portrait"


def test_clicking_a_template_applies_size_and_stages_guides(clean_templates):
    project_templates.save_template(
        "Studio Portrait", width=11.0, height=14.0, unit="cm",
        guides={"rule_of_thirds": True, "golden_ratio": False, "inch_grid": True},
    )
    dlg = NewProjectDialog()
    dlg._apply_template(dlg.template_list.item(0))

    assert dlg.width_spin.value() == 11.0
    assert dlg.height_spin.value() == 14.0
    assert dlg.unit_combo.currentText() == "cm"
    assert dlg.selected_template_guides() == {
        "rule_of_thirds": True, "golden_ratio": False, "inch_grid": True,
    }


def test_clicking_a_size_preset_after_a_template_clears_staged_guides(clean_templates):
    project_templates.save_template(
        "Studio Portrait", width=11.0, height=14.0, unit="in",
        guides={"rule_of_thirds": True},
    )
    dlg = NewProjectDialog()
    dlg._apply_template(dlg.template_list.item(0))
    assert dlg.selected_template_guides() is not None

    dlg._apply_preset(dlg.preset_list.item(0))
    assert dlg.selected_template_guides() is None


def test_canvas_spec_reflects_applied_template_size(clean_templates):
    project_templates.save_template(
        "Studio Portrait", width=9.0, height=12.0, unit="in", guides={},
    )
    dlg = NewProjectDialog()
    dlg._apply_template(dlg.template_list.item(0))
    spec = dlg.canvas_spec()
    assert spec.width == 9.0
    assert spec.height == 12.0
    assert spec.unit == "in"
