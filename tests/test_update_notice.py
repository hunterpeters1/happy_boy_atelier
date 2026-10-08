"""MainWindow's side of the update-check feature: the status-bar notice
label, dismiss persistence, and check_for_updates_on_startup()'s own
gating on the Settings toggle. app/update_check.py's own parsing/
reply-handling logic is covered separately in test_update_check.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from app import settings
from app.main_window import MainWindow


@pytest.fixture
def clean_settings(qapp):
    keys = ["settings/checkForUpdatesEnabled", "settings/lastDismissedUpdateVersion"]
    for key in keys:
        QSettings().remove(key)
    yield
    for key in keys:
        QSettings().remove(key)


def _window(qapp) -> MainWindow:
    win = MainWindow()
    win.show()
    QApplication.processEvents()
    return win


def test_check_for_updates_on_startup_calls_checker_when_enabled(qapp, clean_settings):
    win = _window(qapp)
    settings.set_check_for_updates_enabled(True)
    calls = []
    win._update_checker.check = lambda: calls.append(True)

    win.check_for_updates_on_startup()

    assert calls == [True]


def test_check_for_updates_on_startup_skips_when_disabled(qapp, clean_settings):
    win = _window(qapp)
    settings.set_check_for_updates_enabled(False)
    calls = []
    win._update_checker.check = lambda: calls.append(True)

    win.check_for_updates_on_startup()

    assert calls == []


def test_update_available_shows_the_notice(qapp, clean_settings):
    win = _window(qapp)
    win._on_update_available("1.2.0", "https://example.com/r/v1.2.0")

    assert win.update_notice_label.isVisible() is True
    assert "1.2.0" in win.update_notice_label.text()


def test_update_available_suppressed_if_already_dismissed(qapp, clean_settings):
    win = _window(qapp)
    settings.set_last_dismissed_update_version("1.2.0")

    win._on_update_available("1.2.0", "https://example.com/r/v1.2.0")

    assert win.update_notice_label.isVisible() is False


def test_update_available_still_shown_for_a_newer_version_than_dismissed(qapp, clean_settings):
    win = _window(qapp)
    settings.set_last_dismissed_update_version("1.2.0")

    win._on_update_available("1.3.0", "https://example.com/r/v1.3.0")

    assert win.update_notice_label.isVisible() is True


def test_dismiss_link_hides_notice_and_persists_the_version(qapp, clean_settings):
    win = _window(qapp)
    win._on_update_available("1.2.0", "https://example.com/r/v1.2.0")

    win._on_update_notice_link("dismiss")

    assert win.update_notice_label.isVisible() is False
    assert settings.last_dismissed_update_version() == "1.2.0"


def test_clicking_the_real_link_opens_it_and_leaves_the_notice_alone(qapp, clean_settings, monkeypatch):
    win = _window(qapp)
    win._on_update_available("1.2.0", "https://example.com/r/v1.2.0")

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))

    win._on_update_notice_link("https://example.com/r/v1.2.0")

    assert opened == ["https://example.com/r/v1.2.0"]
    assert win.update_notice_label.isVisible() is True
    assert settings.last_dismissed_update_version() == ""
