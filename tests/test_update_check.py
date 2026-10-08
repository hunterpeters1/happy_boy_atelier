"""app/update_check.py: version parsing and the reply-handling logic
that decides whether to emit update_available. Never exercises
UpdateChecker.check() itself, which makes a real network request --
see the module's own docstring for why that must stay confined to
main.py's real entry point, never something a test triggers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtNetwork import QNetworkReply

from app import update_check


class _FakeReply:
    """Just enough of QNetworkReply's surface for _on_reply() to use."""

    def __init__(self, error=QNetworkReply.NoError, body: bytes = b""):
        self._error = error
        self._body = body
        self.deleted = False

    def error(self):
        return self._error

    def readAll(self):
        return self._body

    def deleteLater(self):
        self.deleted = True


def _reply_with(tag_name: str = "v1.2.0", html_url: str = "https://example.com/r/v1.2.0") -> _FakeReply:
    body = json.dumps({"tag_name": tag_name, "html_url": html_url}).encode()
    return _FakeReply(body=body)


def test_parse_version_basic():
    assert update_check._parse_version("1.2.0") == (1, 2, 0)
    assert update_check._parse_version("v1.2.0") == (1, 2, 0)
    assert update_check._parse_version("V2.0.0") == (2, 0, 0)


def test_parse_version_malformed_returns_none():
    assert update_check._parse_version("1.2.0-beta") is None
    assert update_check._parse_version("") is None
    assert update_check._parse_version("abc") is None
    assert update_check._parse_version("v") is None


def test_emits_when_remote_is_newer(qapp, monkeypatch):
    monkeypatch.setattr(update_check.C, "APP_VERSION", "1.0.0")
    checker = update_check.UpdateChecker()
    received = []
    checker.update_available.connect(lambda v, u: received.append((v, u)))

    reply = _reply_with(tag_name="v1.2.0", html_url="https://example.com/r/v1.2.0")
    checker._on_reply(reply)

    assert received == [("1.2.0", "https://example.com/r/v1.2.0")]
    assert reply.deleted is True


def test_does_not_emit_when_remote_is_not_newer(qapp, monkeypatch):
    monkeypatch.setattr(update_check.C, "APP_VERSION", "1.2.0")
    checker = update_check.UpdateChecker()
    received = []
    checker.update_available.connect(lambda v, u: received.append((v, u)))

    checker._on_reply(_reply_with(tag_name="v1.2.0"))
    checker._on_reply(_reply_with(tag_name="v1.0.0"))

    assert received == []


def test_does_not_emit_on_network_error(qapp, monkeypatch):
    monkeypatch.setattr(update_check.C, "APP_VERSION", "1.0.0")
    checker = update_check.UpdateChecker()
    received = []
    checker.update_available.connect(lambda v, u: received.append((v, u)))

    reply = _FakeReply(error=QNetworkReply.UnknownNetworkError, body=b"")
    checker._on_reply(reply)

    assert received == []
    assert reply.deleted is True


def test_does_not_emit_on_malformed_json(qapp, monkeypatch):
    monkeypatch.setattr(update_check.C, "APP_VERSION", "1.0.0")
    checker = update_check.UpdateChecker()
    received = []
    checker.update_available.connect(lambda v, u: received.append((v, u)))

    reply = _FakeReply(body=b"not json")
    checker._on_reply(reply)

    assert received == []
    assert reply.deleted is True


def test_does_not_emit_when_tag_or_url_missing(qapp, monkeypatch):
    monkeypatch.setattr(update_check.C, "APP_VERSION", "1.0.0")
    checker = update_check.UpdateChecker()
    received = []
    checker.update_available.connect(lambda v, u: received.append((v, u)))

    checker._on_reply(_FakeReply(body=json.dumps({"html_url": "https://x"}).encode()))
    checker._on_reply(_FakeReply(body=json.dumps({"tag_name": "v1.2.0"}).encode()))

    assert received == []


def test_does_not_emit_when_remote_tag_is_unparseable(qapp, monkeypatch):
    monkeypatch.setattr(update_check.C, "APP_VERSION", "1.0.0")
    checker = update_check.UpdateChecker()
    received = []
    checker.update_available.connect(lambda v, u: received.append((v, u)))

    checker._on_reply(_reply_with(tag_name="v1.2.0-beta"))

    assert received == []
