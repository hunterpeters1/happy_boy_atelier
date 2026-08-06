"""Happy Boy Atelier — entry point.

A digital drafting table for traditional painters: plan canvas format,
reference arrangement, composition, perspective, and lighting before
touching the physical canvas. Not a paint program, not a generator.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import constants as C
from app.main_window import MainWindow
from app.resources import app_icon_path
from app.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    app.setApplicationVersion(C.APP_VERSION)
    app.setOrganizationName(C.APP_ORG)

    icon = QIcon(app_icon_path())
    if not icon.isNull():
        app.setWindowIcon(icon)

    apply_theme(app)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
