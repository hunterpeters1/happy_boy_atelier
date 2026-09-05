"""A quiet, dismissible "a newer version exists" check -- not a package
manager, not an auto-updater. GitHub's own Releases API is the free,
already-available source of truth (this repo is where builds actually
get published), so no server of this app's own is needed.

Explicitly NOT wired to run on every MainWindow construction (see
MainWindow.check_for_updates_on_startup(), called once from main.py's
real app entry point) -- the test suite constructs many MainWindows
directly without going through main(), and none of those should ever
make a real network call.

Silent by design on every failure path: no internet, GitHub down, no
releases published yet (a 404, same as any other request failure here),
a malformed response, an unparseable version string -- all of these
just mean no signal is emitted, never an error shown to the artist.
This is a nice-to-know, not something that should ever look like the
app is broken.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import constants as C

_TIMEOUT_MS = 8000


def _parse_version(text: str) -> tuple[int, ...] | None:
    """"v1.2.0" / "1.2.0" -> (1, 2, 0). None on anything that doesn't
    cleanly parse as dot-separated integers (a pre-release suffix like
    "1.2.0-beta", a malformed tag, etc.) -- deliberately strict rather
    than guessing at a partial match, since silently misparsing a
    version is worse than just not showing the notice this one time.
    """
    text = text.strip().lstrip("vV")
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


class UpdateChecker(QObject):
    """update_available(version, release_url): emitted only when the
    latest GitHub release is genuinely newer than C.APP_VERSION. Never
    emitted on any failure, and never emitted at all if nothing newer
    exists.
    """

    update_available = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)

    def check(self) -> None:
        url = f"https://api.github.com/repos/{C.GITHUB_REPO}/releases/latest"
        request = QNetworkRequest(QUrl(url))
        reply = self._manager.get(request)
        reply.finished.connect(lambda: self._on_reply(reply))
        QTimer.singleShot(_TIMEOUT_MS, reply.abort)

    def _on_reply(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NoError:
                return
            data = json.loads(bytes(reply.readAll()))
            tag = data.get("tag_name", "")
            release_url = data.get("html_url", "")
            if not tag or not release_url:
                return

            latest = _parse_version(tag)
            current = _parse_version(C.APP_VERSION)
            if latest is None or current is None or latest <= current:
                return

            self.update_available.emit(tag.lstrip("vV"), release_url)
        except (ValueError, TypeError, AttributeError):
            # Malformed JSON, unexpected shape, etc. -- see module
            # docstring: every failure path here is silent by design.
            pass
        finally:
            reply.deleteLater()
