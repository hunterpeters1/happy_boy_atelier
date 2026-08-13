"""app/resources.py: locating bundled/sibling files whether running from
source or a PyInstaller-frozen exe. uploader_root() specifically, since
it deliberately does NOT follow project_root()'s _MEIPASS logic -- see
its own docstring for why a path built under _MEIPASS would always be
wrong for the uploader/ tool.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import resources


def test_uploader_root_not_frozen_is_sibling_of_app_package(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    root = Path(resources.uploader_root())

    assert root == Path(resources.project_root()) / "uploader"
    assert root.name == "uploader"


def test_uploader_root_frozen_uses_executable_location_not_meipass(monkeypatch, tmp_path):
    # Simulates the documented build layout: <repo root>/dist/Happy Boy
    # Atelier.exe, with uploader/ a sibling of dist/ -- see
    # resources.uploader_root()'s own docstring.
    repo_root = tmp_path / "happy_boy_atelier"
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True)
    fake_exe = dist_dir / "Happy Boy Atelier.exe"
    fake_exe.write_text("")

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "totally_unrelated_temp_extraction"), raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    assert Path(resources.uploader_root()) == repo_root / "uploader"
