"""Help > Upload From Phone… dialog: launches the standalone uploader/
tool (see uploader/app.py's own module docstring) as a child process and
shows the QR code / URL / PIN to scan or type on a phone, without the
artist needing to open a terminal or manage the uploader's separate venv
themselves.

Deliberately still runs the uploader as a fully separate process with its
own venv/dependencies — this dialog only launches it and talks to it via
process lifecycle plus a generated PIN passed through an env var
(HAPPY_BOY_UPLOADER_PIN, see uploader/app.py), and never imports anything
from uploader/ into this process. That keeps the "standalone tool, own
dependencies" boundary CLAUDE.md documents intact; this dialog is a
launcher/front door, not a merge of the two codebases.

Non-modal by design (MainWindow.show()s it, not exec()s it) — the whole
point of the live library sync (app/library.py's sync_from_uploader(),
polled by LibraryPanel) is watching photos land in the Reference Library
while this dialog is open, which a modal dialog blocking the rest of the
app would defeat.
"""

from __future__ import annotations

import io
import json
import secrets
import socket
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QProcess, QProcessEnvironment, Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .. import resources

# Must match uploader/app.py's own PORT constant -- there's no handshake
# to confirm it at runtime, since the uploader has no PySide6 dependency
# to report back through; this dialog just assumes the same fixed port
# uploader/app.py hardcodes.
PORT = 5000
# How long to wait before treating a still-running process as "started
# successfully" -- QProcess only tells us "the OS launched it" (started)
# vs. "it exited" (finished), not "it's actually listening on the port",
# so a short grace period is the practical way to catch a fast failure
# (e.g. port 5000 already in use) without an actual readiness handshake.
_STARTUP_GRACE_MS = 1200
# Safety cap on the stale-server recovery request (see
# _attempt_stale_server_recovery()) -- loopback should answer in
# milliseconds if anything's actually listening; this just guarantees
# the dialog can't hang indefinitely on "checking..." if something odd
# swallows the connection.
_RECOVERY_TIMEOUT_MS = 2500
# How long to wait after a successful recovery shutdown before trying to
# bind the port again -- _delayed_exit() on the uploader side waits
# ~0.3s before actually exiting, so the OS needs a moment past that to
# free the socket.
_RECOVERY_RETRY_DELAY_MS = 600


def _venv_python() -> Path | None:
    """Locate the uploader's own venv interpreter. Checks both the
    README-documented `.venv` and the plain `venv` name (some existing
    setups use that instead), and both Windows' `Scripts/python.exe`
    layout and the Unix `bin/python` layout (macOS/Linux) -- a venv only
    ever has one of these two, so trying both directly is simpler than
    branching on `sys.platform` first. None if neither exists, meaning
    the artist hasn't run `pip install -r requirements.txt` in uploader/
    yet.
    """
    uploader_dir = Path(resources.uploader_root())
    for venv_name in (".venv", "venv"):
        for sub_path in (("Scripts", "python.exe"), ("bin", "python")):
            candidate = uploader_dir / venv_name / Path(*sub_path)
            if candidate.exists():
                return candidate
    return None


def _lan_ip() -> str:
    """Same trick as uploader/app.py's own get_lan_ip() — a UDP "connect"
    that never actually sends anything, just asks the OS which local
    interface it would use to reach an external address, to find this
    machine's real LAN IP rather than 127.0.0.1. Duplicated here rather
    than imported, since this dialog deliberately never imports from the
    standalone uploader/ tool (see this module's own docstring).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _qr_pixmap(data: str) -> QPixmap | None:
    """None (not a crash) if qrcode/pypng aren't installed — the URL/PIN
    text alone is still enough to connect, just without a scannable code.
    """
    try:
        import qrcode
        from qrcode.image.pure import PyPNGImage
    except ImportError:
        return None
    img = qrcode.make(data, image_factory=PyPNGImage)
    buf = io.BytesIO()
    img.save(buf)
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), "PNG")
    return pixmap if not pixmap.isNull() else None


class PhoneUploadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upload From Phone")
        self.setMinimumWidth(360)
        self._process: QProcess | None = None
        self._network_manager = QNetworkAccessManager(self)
        # At most one automatic recovery attempt per dialog -- see
        # _handle_startup_failure().
        self._recovery_attempted = False
        # Guards errorOccurred/finished/the grace-period timer all firing
        # for the same failed launch -- see _handle_startup_failure().
        self._launch_settled = False

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Starting the upload server…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignHCenter)
        self.qr_label.setVisible(False)
        layout.addWidget(self.qr_label)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignHCenter)
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        hint = QLabel(
            "Scan the QR code (or type the URL) on a phone on the same WiFi "
            "network, then enter the PIN. Uploaded photos appear in the "
            "Reference Library automatically. Closing this window stops "
            "the upload server.\n\n"
            "First time on this phone? Check \"Remember this device\" on the "
            "PIN screen — it'll skip straight to the upload page on every "
            "future visit, no new PIN needed."
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self._start_server()

    # -- process lifecycle ----------------------------------------------
    def _start_server(self) -> None:
        venv_python = _venv_python()
        if venv_python is None:
            activate_line = (
                ".venv\\Scripts\\activate" if sys.platform == "win32" else "source .venv/bin/activate"
            )
            self.status_label.setText(
                "The uploader hasn't been set up yet. Open a terminal in "
                "uploader/ and run:\n\n"
                "python -m venv .venv\n"
                f"{activate_line}\n"
                "pip install -r requirements.txt\n\n"
                "then try again."
            )
            return
        self._venv_python_path = venv_python
        self._launch_process()

    def _launch_process(self) -> None:
        pin = f"{secrets.randbelow(1_000_000):06d}"
        url = f"http://{_lan_ip()}:{PORT}"

        process = QProcess(self)
        process.setWorkingDirectory(resources.uploader_root())
        env = QProcessEnvironment.systemEnvironment()
        env.insert("HAPPY_BOY_UPLOADER_PIN", pin)
        process.setProcessEnvironment(env)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_process_finished)
        process.start(str(self._venv_python_path), ["app.py"])
        self._process = process
        self._launch_settled = False

        self.status_label.setText("Upload server running:")
        qr = _qr_pixmap(url)
        self.qr_label.setPixmap(qr if qr is not None else QPixmap())
        self.qr_label.setVisible(qr is not None)
        self.info_label.setText(f"<b>{url}</b><br>PIN: <b>{pin}</b>")

        QTimer.singleShot(_STARTUP_GRACE_MS, self._check_still_running)

    def _check_still_running(self) -> None:
        if self._process is not None and self._process.state() == QProcess.NotRunning:
            self._handle_startup_failure()

    def _on_process_error(self, _error) -> None:
        self._handle_startup_failure()

    def _on_process_finished(self, _code, _status) -> None:
        # Only reachable if the process ended on its own (crash, port
        # conflict) — _stop_server() disconnects this signal before a
        # deliberate close/terminate, so that path never reaches here.
        self._handle_startup_failure()

    def _handle_startup_failure(self) -> None:
        # errorOccurred, finished, and the grace-period timeout can all
        # fire for the same failed launch (or a stale timer can fire
        # late, after a recovery retry already succeeded or failed on
        # its own) -- only the first one for a given _launch_process()
        # call should actually act.
        if self._launch_settled:
            return
        self._launch_settled = True

        if not self._recovery_attempted:
            self._recovery_attempted = True
            self._attempt_stale_server_recovery()
        else:
            self._show_failure()

    # -- stale-server recovery -------------------------------------------
    def _attempt_stale_server_recovery(self) -> None:
        """Port 5000 being busy is, in practice, almost always a leftover
        copy of this exact tool from a previous session that didn't shut
        down cleanly (a crash, a force-quit) rather than some unrelated
        app — so before giving up, ask whatever's on that port to
        identify itself and step aside, via uploader/app.py's
        /internal/shutdown route. This never inspects or kills anything
        at the OS/process level: if nothing answers, or it doesn't
        answer the way our own uploader would (an old build without this
        route, or a genuinely unrelated service), _on_recovery_reply()
        below falls straight through to the normal failure message.
        """
        self.status_label.setText("Port 5000 is busy — checking for a leftover copy of this server…")
        net_request = QNetworkRequest(QUrl(f"http://127.0.0.1:{PORT}/internal/shutdown"))
        reply = self._network_manager.post(net_request, QByteArray())
        reply.finished.connect(lambda: self._on_recovery_reply(reply))
        QTimer.singleShot(_RECOVERY_TIMEOUT_MS, reply.abort)

    def _on_recovery_reply(self, reply: QNetworkReply) -> None:
        recovered = False
        if reply.error() == QNetworkReply.NoError:
            try:
                recovered = json.loads(bytes(reply.readAll())).get("ok") is True
            except ValueError:
                recovered = False
        reply.deleteLater()

        if recovered:
            self.status_label.setText("Leftover server found — restarting…")
            QTimer.singleShot(_RECOVERY_RETRY_DELAY_MS, self._launch_process)
        else:
            self._show_failure()

    def _show_failure(self) -> None:
        self.qr_label.setVisible(False)
        self.info_label.setText("")
        self.status_label.setText(
            "The upload server didn't start, and this app couldn't "
            "automatically recover port 5000 — it may be in use by "
            "something other than a previous copy of this tool. Close "
            "whatever's using it and try again."
        )

    def _stop_server(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.state() != QProcess.NotRunning:
            process.finished.disconnect(self._on_process_finished)
            process.terminate()
            if not process.waitForFinished(2000):
                process.kill()

    def closeEvent(self, event) -> None:
        self._stop_server()
        super().closeEvent(event)
