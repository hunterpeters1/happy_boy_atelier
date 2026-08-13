"""Locate bundled files (icons, etc.) whether running from source or from a
PyInstaller-frozen executable.

PyInstaller's onefile mode extracts bundled data to a temporary directory
at `sys._MEIPASS` at runtime; running from source, the project root is two
levels up from this file (`happy_boy_atelier/app/resources.py` -> project
root is `happy_boy_atelier/`).
"""

from __future__ import annotations

import os
import sys


def project_root() -> str:
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return frozen_base
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*relative_parts: str) -> str:
    return os.path.join(project_root(), *relative_parts)


def uploader_root() -> str:
    """Where the standalone uploader/ tool (its own venv, its own
    dependencies — see uploader/app.py's module docstring) lives on disk,
    for the app to launch it and find its photos/ folder (Help > Upload
    From Phone…, app/library.py's uploader sync). This is deliberately
    NOT project_root()/"uploader": project_root() resolves to _MEIPASS,
    PyInstaller's temp per-launch extraction directory, in a frozen exe
    — and uploader/ is intentionally never bundled into that exe at all
    (it's a separate tool with its own dependencies), so a path built
    under _MEIPASS would point at a folder that can never exist.

    Instead: not-frozen (running from source) uses the same project-root
    logic project_root() does; frozen uses the actual .exe file's own
    location on disk (sys.executable, stable across runs, unlike
    _MEIPASS) and goes up to the repo root from there, matching this
    project's own documented build layout (CLAUDE.md/HappyBoyAtelier.spec)
    where the built exe lands at <repo root>/dist/Happy Boy Atelier.exe —
    one level below the repo root, with uploader/ a sibling of dist/.
    This holds for the documented, intended distribution shape (a desktop
    shortcut pointing at that exe) but not if someone copies the exe file
    itself out of the repo checkout.
    """
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        repo_root = project_root()
    return os.path.join(repo_root, "uploader")


def app_icon_path() -> str:
    return resource_path("resources", "icons", "app.ico")


def space_grotesk_font_path() -> str:
    return resource_path("resources", "SpaceGrotesk-VariableFont_wght.ttf")
