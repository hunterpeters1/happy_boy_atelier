"""PhoneUploadDialog's stale-server recovery path: when port 5000 is
already in use, before giving up it asks whatever's listening to
identify itself and step aside via uploader/app.py's /internal/shutdown
route (see that module's own docstring on the route).

Deliberately does not exercise a real QProcess/uploader launch -- same
scoping test_phone_upload_dialog.py's own docstring describes -- these
tests call the recovery methods directly on a dialog whose __init__ was
short-circuited to the "uploader not set up" path.

Deliberately also never issues a real network request (no real loopback
HTTP server, no real QNetworkAccessManager round trip): a real request
that actually receives a response was confirmed at runtime to leave this
environment's Qt/offscreen-QPA networking stack in a state that
segfaults on *any* later QApplication.processEvents() call for the rest
of the process -- not just in this file, in the whole suite, depending
on collection order. That's a sandbox/environment instability, not a
bug in the dialog's own code (the same request completes correctly and
quickly in a standalone script outside pytest), but it's not a risk
worth taking in a shared test suite. Every branch _on_recovery_reply()
can take is still covered, just via a fake reply object instead of a
real socket.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication

from app.dialogs import phone_upload_dialog as dlg_module
from app.dialogs.phone_upload_dialog import PhoneUploadDialog


def _pump_until(predicate, timeout_s: float = 3.0) -> bool:
    """Repeated small processEvents() + sleep() slices to let a
    QTimer.singleShot() callback actually fire. Returns whether the
    predicate became true before the timeout.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class _FakeReply:
    """Just enough of QNetworkReply's surface for
    _on_recovery_reply() -- error(), readAll(), deleteLater() -- to
    exercise its branching without a real socket round trip.
    """

    def __init__(self, error, body: bytes):
        self._error = error
        self._body = body

    def error(self):
        return self._error

    def readAll(self):
        return self._body

    def deleteLater(self):
        pass


def _dialog(qapp, monkeypatch) -> PhoneUploadDialog:
    # Short-circuits __init__ straight to the "uploader not set up"
    # message so it never touches a real QProcess -- same pattern
    # test_main_window.py's phone-upload wiring tests already use.
    monkeypatch.setattr(dlg_module, "_venv_python", lambda: None)
    return PhoneUploadDialog()


def test_on_recovery_reply_retries_the_launch_when_recovered(qapp, monkeypatch):
    dlg = _dialog(qapp, monkeypatch)
    calls = []
    dlg._launch_process = lambda: calls.append(True)

    dlg._on_recovery_reply(_FakeReply(QNetworkReply.NoError, b'{"ok": true}'))

    assert "restarting" in dlg.status_label.text().lower()
    settled = _pump_until(lambda: calls)
    assert settled, "recovery never retried _launch_process()"
    assert calls == [True]


def test_on_recovery_reply_fails_on_network_error(qapp, monkeypatch):
    dlg = _dialog(qapp, monkeypatch)

    dlg._on_recovery_reply(_FakeReply(QNetworkReply.ConnectionRefusedError, b""))

    assert "couldn't automatically recover" in dlg.status_label.text()


def test_on_recovery_reply_fails_when_response_is_not_our_ok_json(qapp, monkeypatch):
    dlg = _dialog(qapp, monkeypatch)

    dlg._on_recovery_reply(_FakeReply(QNetworkReply.NoError, b"<html>404 not found</html>"))

    assert "couldn't automatically recover" in dlg.status_label.text()


def test_on_recovery_reply_fails_when_ok_is_not_true(qapp, monkeypatch):
    dlg = _dialog(qapp, monkeypatch)

    dlg._on_recovery_reply(_FakeReply(QNetworkReply.NoError, b'{"ok": false}'))

    assert "couldn't automatically recover" in dlg.status_label.text()


def test_handle_startup_failure_only_recovers_once(qapp, monkeypatch):
    dlg = _dialog(qapp, monkeypatch)
    recovery_calls = []
    dlg._attempt_stale_server_recovery = lambda: recovery_calls.append(True)

    dlg._launch_settled = False
    dlg._handle_startup_failure()
    assert recovery_calls == [True]
    assert dlg._recovery_attempted is True

    # A second failed launch (a fresh _launch_process() call would have
    # reset this) should go straight to the real failure message instead
    # of trying to recover again.
    dlg._launch_settled = False
    dlg._handle_startup_failure()

    assert recovery_calls == [True]
    assert "couldn't automatically recover" in dlg.status_label.text()


def test_handle_startup_failure_ignores_duplicate_signals_for_the_same_launch(qapp, monkeypatch):
    dlg = _dialog(qapp, monkeypatch)
    recovery_calls = []
    dlg._attempt_stale_server_recovery = lambda: recovery_calls.append(True)

    # errorOccurred, finished, and the grace-period timer can all fire
    # for one failed launch attempt -- only the first should act.
    dlg._handle_startup_failure()
    dlg._handle_startup_failure()
    dlg._handle_startup_failure()

    assert recovery_calls == [True]
