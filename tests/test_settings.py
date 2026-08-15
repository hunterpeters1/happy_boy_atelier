"""app/settings.py: user preferences (Options > Settings…). Plain scalar
QSettings keys, no Qt item/scene coupling -- same spirit as
test_project_templates.py, but without the JSON-blob encoding those
presets need (a single scalar round-trips fine on its own).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings

from app import settings


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


def test_defaults_when_nothing_set(clean_settings):
    assert settings.autosave_interval_ms() == 3 * 60 * 1000
    assert settings.default_unit() == "in"
    assert settings.default_export_dpi() == 300
    assert settings.show_rulers_by_default() is True
    assert settings.futuristic_accents_enabled() is True


def test_autosave_interval_round_trips(clean_settings):
    settings.set_autosave_interval_ms(60_000)
    assert settings.autosave_interval_ms() == 60_000


def test_autosave_interval_off_is_a_real_persisted_choice(clean_settings):
    settings.set_autosave_interval_ms(settings.AUTOSAVE_OFF_MS)
    assert settings.autosave_interval_ms() == settings.AUTOSAVE_OFF_MS


def test_autosave_interval_rejects_a_value_outside_the_known_choices(clean_settings):
    # A stray/corrupted setting (or a future downgrade after a choice was
    # removed) falls back to the constants.py default rather than handing
    # QTimer.setInterval() something nonsensical.
    QSettings().setValue("settings/autosaveIntervalMs", 12345)
    assert settings.autosave_interval_ms() == 3 * 60 * 1000


def test_default_unit_round_trips(clean_settings):
    settings.set_default_unit("cm")
    assert settings.default_unit() == "cm"


def test_default_unit_rejects_unknown_unit(clean_settings):
    QSettings().setValue("settings/defaultUnit", "furlongs")
    assert settings.default_unit() == "in"


def test_default_export_dpi_round_trips(clean_settings):
    settings.set_default_export_dpi(150)
    assert settings.default_export_dpi() == 150


def test_default_export_dpi_rejects_out_of_range_value(clean_settings):
    QSettings().setValue("settings/defaultExportDpi", 99999)
    assert settings.default_export_dpi() == 300


def test_show_rulers_by_default_round_trips(clean_settings):
    settings.set_show_rulers_by_default(False)
    assert settings.show_rulers_by_default() is False
    settings.set_show_rulers_by_default(True)
    assert settings.show_rulers_by_default() is True


def test_show_rulers_by_default_handles_string_backed_bool(clean_settings):
    # Some QSettings backends (INI-based) hand bools back as the literal
    # strings "true"/"false" rather than a real bool -- confirmed a real
    # cross-backend inconsistency elsewhere in this app (see
    # app/settings.py's _as_bool() docstring).
    QSettings().setValue("settings/showRulersByDefault", "false")
    assert settings.show_rulers_by_default() is False
    QSettings().setValue("settings/showRulersByDefault", "true")
    assert settings.show_rulers_by_default() is True


def test_futuristic_accents_round_trips(clean_settings):
    settings.set_futuristic_accents_enabled(False)
    assert settings.futuristic_accents_enabled() is False
    settings.set_futuristic_accents_enabled(True)
    assert settings.futuristic_accents_enabled() is True


def test_futuristic_accents_handles_string_backed_bool(clean_settings):
    QSettings().setValue("settings/futuristicAccentsEnabled", "false")
    assert settings.futuristic_accents_enabled() is False
    QSettings().setValue("settings/futuristicAccentsEnabled", "true")
    assert settings.futuristic_accents_enabled() is True
