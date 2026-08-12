"""AboutDialog: the app's identity moment, replacing the old plain
QMessageBox.about() call. Covers content/wiring only -- visual styling
comes from theme.py's global QDialog rule and isn't meaningfully testable
headless.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import constants as C
from app.dialogs.about_dialog import AboutDialog
from app.main_window import MainWindow


def test_about_dialog_shows_app_name_and_version(qapp):
    dlg = AboutDialog()
    assert C.APP_NAME in dlg.name_label.text()
    assert C.APP_VERSION in dlg.name_label.text()


def test_about_dialog_has_ok_button_that_accepts(qapp):
    dlg = AboutDialog()
    dlg.accept()
    assert dlg.result() == AboutDialog.Accepted


def test_main_window_show_about_opens_about_dialog(qapp, monkeypatch):
    win = MainWindow()
    win.show()

    opened = {}

    class _RecordingDialog(AboutDialog):
        def exec(self):
            opened["shown"] = True
            return AboutDialog.Accepted

    monkeypatch.setattr("app.main_window.AboutDialog", _RecordingDialog)
    win._show_about()

    assert opened.get("shown") is True
