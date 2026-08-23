"""Tests for the standalone phone-uploader Flask app (uploader/app.py),
focused on the "remember this device" trust layer -- login/PIN behavior,
cookie issuance, hashed at-rest storage, and the /forget-device revocation
path. Deliberately does NOT touch upload()/HEIC conversion -- that's the
pre-existing photo-handling path, unrelated to this feature.

uploader/ is a standalone tool with its own venv/dependencies (see
CLAUDE.md and app/dialogs/phone_upload_dialog.py's module docstring) --
Flask is never a main-app dependency. `pytest.importorskip` below lets
this file skip cleanly (not error) when Flask isn't installed, so running
the main app's `pytest` suite from the repo root without the uploader's
own venv active still passes; running it with Flask installed (e.g. from
uploader's own venv, or `pip install -r uploader/requirements.txt`)
exercises these tests too.

app.py is loaded by file path under a private module name rather than a
plain `import app`, since the main app/ package at the repo root is
already named "app" -- a bare `import app` here would silently resolve to
the wrong module (or the cached one) when both test suites run together.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("flask")
pytest.importorskip("pillow_heif")

_APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
_MODULE_NAME = "happy_boy_uploader_app"

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _APP_PATH)
uploader_app = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = uploader_app
_spec.loader.exec_module(uploader_app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(uploader_app, "TRUSTED_DEVICES_PATH", tmp_path / "trusted_devices.json")
    monkeypatch.setattr(uploader_app, "_trusted_hashes", set())
    monkeypatch.setattr(uploader_app, "PIN", "123456")
    uploader_app.app.config.update(TESTING=True)
    with uploader_app.app.test_client() as test_client:
        yield test_client


def test_hash_token_is_deterministic_and_distinct():
    assert uploader_app._hash_token("abc") == uploader_app._hash_token("abc")
    assert uploader_app._hash_token("abc") != uploader_app._hash_token("xyz")


def test_load_trusted_hashes_missing_file_returns_empty_set(tmp_path):
    monkeypatch_path = tmp_path / "does_not_exist.json"
    original = uploader_app.TRUSTED_DEVICES_PATH
    uploader_app.TRUSTED_DEVICES_PATH = monkeypatch_path
    try:
        assert uploader_app._load_trusted_hashes() == set()
    finally:
        uploader_app.TRUSTED_DEVICES_PATH = original


def test_load_trusted_hashes_corrupt_file_returns_empty_set(tmp_path):
    path = tmp_path / "trusted_devices.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    original = uploader_app.TRUSTED_DEVICES_PATH
    uploader_app.TRUSTED_DEVICES_PATH = path
    try:
        assert uploader_app._load_trusted_hashes() == set()
    finally:
        uploader_app.TRUSTED_DEVICES_PATH = original


def test_save_and_load_trusted_hashes_round_trip(tmp_path):
    path = tmp_path / "trusted_devices.json"
    original_path = uploader_app.TRUSTED_DEVICES_PATH
    original_hashes = uploader_app._trusted_hashes
    uploader_app.TRUSTED_DEVICES_PATH = path
    uploader_app._trusted_hashes = {"aaa", "bbb"}
    try:
        uploader_app._save_trusted_hashes()
        assert uploader_app._load_trusted_hashes() == {"aaa", "bbb"}
    finally:
        uploader_app.TRUSTED_DEVICES_PATH = original_path
        uploader_app._trusted_hashes = original_hashes


def test_login_page_loads_when_not_remembered(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_index_redirects_to_login_when_unauthenticated(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_wrong_pin_shows_error_and_does_not_authenticate(client):
    response = client.post("/login", data={"pin": "000000"})
    assert response.status_code == 200
    assert b"Incorrect PIN" in response.data
    assert client.get("/").status_code == 302


def test_correct_pin_without_remember_does_not_persist_device(client):
    response = client.post("/login", data={"pin": "123456"})
    assert response.status_code == 302
    assert client.get("/").status_code == 200
    assert uploader_app._trusted_hashes == set()
    assert not uploader_app.REMEMBER_COOKIE_NAME in response.headers.get("Set-Cookie", "")


def test_correct_pin_with_remember_sets_cookie_and_persists_hash(client):
    response = client.post("/login", data={"pin": "123456", "remember": "on"})
    assert response.status_code == 302
    assert uploader_app.REMEMBER_COOKIE_NAME in response.headers.get("Set-Cookie", "")
    assert len(uploader_app._trusted_hashes) == 1
    assert uploader_app.TRUSTED_DEVICES_PATH.exists()


def test_remembered_device_reaches_protected_route_without_session(client):
    client.post("/login", data={"pin": "123456", "remember": "on"})
    client.delete_cookie("session")

    response = client.get("/")
    assert response.status_code == 200


def test_remembered_device_hitting_login_redirects_straight_to_index(client):
    client.post("/login", data={"pin": "123456", "remember": "on"})
    client.delete_cookie("session")

    response = client.get("/login")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_forget_device_clears_cookie_and_revokes_trust(client):
    client.post("/login", data={"pin": "123456", "remember": "on"})
    assert len(uploader_app._trusted_hashes) == 1

    response = client.post("/forget-device")
    assert response.status_code == 302
    assert uploader_app._trusted_hashes == set()

    client.delete_cookie("session")
    assert client.get("/").status_code == 302


def test_forget_device_without_a_remembered_cookie_is_a_safe_noop(client):
    response = client.post("/forget-device")
    assert response.status_code == 302
    assert uploader_app._trusted_hashes == set()


# -- /internal/shutdown (PhoneUploadDialog's stale-server recovery) -------
#
# Every test here monkeypatches _delayed_exit() to a no-op first. The real
# one spawns a background thread that calls os._exit(0) after a short
# delay -- since Flask's test client runs the view function in-process,
# leaving the real target in place would eventually kill this very test
# process (and the whole pytest run with it) a fraction of a second after
# the request returns, whether or not the test itself has finished.

def test_internal_shutdown_rejects_non_loopback_callers(client, monkeypatch):
    monkeypatch.setattr(uploader_app, "_delayed_exit", lambda: None)
    response = client.post("/internal/shutdown", environ_overrides={"REMOTE_ADDR": "203.0.113.5"})
    assert response.status_code == 403


def test_internal_shutdown_accepts_loopback_ipv4(client, monkeypatch):
    monkeypatch.setattr(uploader_app, "_delayed_exit", lambda: None)
    response = client.post("/internal/shutdown", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_internal_shutdown_accepts_loopback_ipv6(client, monkeypatch):
    monkeypatch.setattr(uploader_app, "_delayed_exit", lambda: None)
    response = client.post("/internal/shutdown", environ_overrides={"REMOTE_ADDR": "::1"})
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_internal_shutdown_does_not_require_the_pin(client, monkeypatch):
    # Deliberately reachable without a session/PIN -- see the route's own
    # docstring for why (a new instance has no way to know an old one's
    # PIN). The loopback-only guard above is the actual protection.
    monkeypatch.setattr(uploader_app, "_delayed_exit", lambda: None)
    response = client.post(
        "/internal/shutdown", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}
    )
    assert response.status_code == 200


def test_internal_shutdown_schedules_the_exit_target(client, monkeypatch):
    calls = []
    monkeypatch.setattr(uploader_app, "_delayed_exit", lambda: calls.append(True))
    monkeypatch.setattr(uploader_app.threading.Thread, "start", lambda self: self.run())

    client.post("/internal/shutdown", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})

    assert calls == [True]
