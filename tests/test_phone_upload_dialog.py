"""PhoneUploadDialog's pure-logic helpers -- venv lookup, LAN IP
detection, and QR image generation. The actual QProcess launch/lifecycle
is exercised by test_main_window.py's phone-upload tests instead, since
those only need the process to exist (or fail to start, which is exactly
what happens on this non-Windows test machine anyway) rather than a real
Flask server actually serving pages.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dialogs import phone_upload_dialog as dlg_module


def test_venv_python_finds_dot_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg_module.resources, "uploader_root", lambda: str(tmp_path))
    python_path = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("")

    assert dlg_module._venv_python() == python_path


def test_venv_python_falls_back_to_plain_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg_module.resources, "uploader_root", lambda: str(tmp_path))
    python_path = tmp_path / "venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("")

    assert dlg_module._venv_python() == python_path


def test_venv_python_prefers_dot_venv_when_both_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg_module.resources, "uploader_root", lambda: str(tmp_path))
    for name in (".venv", "venv"):
        p = tmp_path / name / "Scripts" / "python.exe"
        p.parent.mkdir(parents=True)
        p.write_text("")

    assert dlg_module._venv_python() == tmp_path / ".venv" / "Scripts" / "python.exe"


def test_venv_python_none_when_neither_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg_module.resources, "uploader_root", lambda: str(tmp_path))
    assert dlg_module._venv_python() is None


def test_lan_ip_returns_a_nonempty_string():
    # Real network-dependent (falls back to 127.0.0.1 on failure, same as
    # uploader/app.py's own get_lan_ip()) -- this only needs to confirm it
    # never raises and always returns something usable in a URL.
    ip = dlg_module._lan_ip()
    assert isinstance(ip, str) and ip


def test_qr_pixmap_produces_a_valid_square_image(qapp):
    pixmap = dlg_module._qr_pixmap("http://192.168.1.100:5000")
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.width() == pixmap.height()


def test_qr_pixmap_none_when_qrcode_not_installed(qapp, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "qrcode":
            raise ImportError("simulated missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert dlg_module._qr_pixmap("http://192.168.1.100:5000") is None
