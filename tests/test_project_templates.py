"""project_templates.py: a named {width, height, unit, guides} starting
point for New Painting, JSON-serialized under one QSettings key -- same
pattern as export_dialog.py's presets. See project_templates.py's module
docstring for why (auto-populating reference images/content from a
template would cross into "software infers the composition").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings

from app import project_templates
from app.project_templates import _SETTINGS_KEY


@pytest.fixture
def clean_templates(qapp):
    QSettings().remove(_SETTINGS_KEY)
    yield
    QSettings().remove(_SETTINGS_KEY)


def test_fresh_settings_has_no_templates(clean_templates):
    assert project_templates.load_templates() == {}


def test_save_template_persists_all_fields(clean_templates):
    project_templates.save_template(
        "Studio Portrait", width=11.0, height=14.0, unit="in",
        guides={"rule_of_thirds": True, "golden_ratio": False, "inch_grid": True},
    )
    assert project_templates.load_templates() == {
        "Studio Portrait": {
            "width": 11.0, "height": 14.0, "unit": "in",
            "guides": {"rule_of_thirds": True, "golden_ratio": False, "inch_grid": True},
        }
    }


def test_save_template_overwrites_same_name(clean_templates):
    project_templates.save_template("A", width=1.0, height=1.0, unit="in", guides={})
    project_templates.save_template("A", width=2.0, height=3.0, unit="cm", guides={"inch_grid": True})
    templates = project_templates.load_templates()
    assert len(templates) == 1
    assert templates["A"]["width"] == 2.0
    assert templates["A"]["unit"] == "cm"


def test_templates_persist_independently_of_load_templates_return_value(clean_templates):
    project_templates.save_template("A", width=1.0, height=1.0, unit="in", guides={})
    loaded = project_templates.load_templates()
    loaded["A"]["width"] = 999.0  # mutate the returned dict, not the store
    assert project_templates.load_templates()["A"]["width"] == 1.0


def test_delete_template_removes_it(clean_templates):
    project_templates.save_template("A", width=1.0, height=1.0, unit="in", guides={})
    project_templates.save_template("B", width=2.0, height=2.0, unit="in", guides={})
    project_templates.delete_template("A")
    assert list(project_templates.load_templates()) == ["B"]


def test_delete_missing_template_is_a_no_op(clean_templates):
    project_templates.save_template("A", width=1.0, height=1.0, unit="in", guides={})
    project_templates.delete_template("Nonexistent")
    assert list(project_templates.load_templates()) == ["A"]


def test_malformed_settings_value_loads_as_empty(clean_templates):
    QSettings().setValue(_SETTINGS_KEY, "not valid json{")
    assert project_templates.load_templates() == {}
