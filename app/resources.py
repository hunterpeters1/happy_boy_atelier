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


def app_icon_path() -> str:
    return resource_path("resources", "icons", "app.ico")
