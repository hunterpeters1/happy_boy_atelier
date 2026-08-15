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
import secrets
import socket
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QPixmap
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


def _venv_python() -> Path | None:
    """Locate the uploader's own venv interpreter. Checks both the
    README-documented `.venv` and the plain `venv` name (some existing
    setups use that instead), Windows' Scripts/python.exe layout (this
    app is Windows-only, see CLAUDE.md). None if neither exists, meaning
    the artist hasn't run `pip install -r requirements.txt` in uploader/
    yet.
    """
    uploader_dir = Path(resources.uploader_root())
    for venv_name in (".venv", "venv"):
        candidate = uploader_dir / venv_name / "Scripts" / "python.exe"
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
<<<<<<< HEAD
            "the upload server.\n\n"
            "First time on this phone? Check \"Remember this device\" on the "
            "PIN screen — it'll skip straight to the upload page on every "
            "future visit, no new PIN needed."
=======
            "the upload server."
>>>>>>> origin/master
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
            self.status_label.setText(
                "The uploader hasn't been set up yet. Open a terminal in "
                "uploader/ and run:\n\n"
                "python -m venv .venv\n"
                ".venv\\Scripts\\activate\n"
                "pip install -r requirements.txt\n\n"
                "then try again."
            )
            return

        pin = f"{secrets.randbelow(1_000_000):06d}"
        url = f"http://{_lan_ip()}:{PORT}"

        process = QProcess(self)
        process.setWorkingDirectory(resources.uploader_root())
        env = QProcessEnvironment.systemEnvironment()
        env.insert("HAPPY_BOY_UPLOADER_PIN", pin)
        process.setProcessEnvironment(env)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_process_finished)
        process.start(str(venv_python), ["app.py"])
        self._process = process

        self.status_label.setText("Upload server running:")
        qr = _qr_pixmap(url)
        if qr is not None:
            self.qr_label.setPixmap(qr)
            self.qr_label.setVisible(True)
        self.info_label.setText(f"<b>{url}</b><br>PIN: <b>{pin}</b>")

        QTimer.singleShot(_STARTUP_GRACE_MS, self._check_still_running)

    def _check_still_running(self) -> None:
        if self._process is not None and self._process.state() == QProcess.NotRunning:
            self._show_failure()

    def _on_process_error(self, _error) -> None:
        self._show_failure()

    def _on_process_finished(self, _code, _status) -> None:
        # Only reachable if the process ended on its own (crash, port
        # conflict) — _stop_server() disconnects this signal before a
        # deliberate close/terminate, so that path never reaches here.
        self._show_failure()

    def _show_failure(self) -> None:
        self.qr_label.setVisible(False)
        self.info_label.setText("")
        self.status_label.setText(
            "The upload server didn't start — port 5000 may already be in "
            "use (perhaps by another copy of the uploader already "
            "running). Close this window and try again."
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
