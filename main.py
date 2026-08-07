"""Happy Boy Atelier — entry point.

A digital drafting table for traditional painters: plan canvas format,
reference arrangement, composition, perspective, and lighting before
touching the physical canvas. Not a paint program, not a generator.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from app import constants as C
from app import scrollbars
from app import themes
from app.main_window import MainWindow
from app.resources import app_icon_path, space_grotesk_font_path
from app.theme import apply_theme


def _load_theme_mode() -> themes.ThemeMode:
    raw = QSettings().value("appearance/theme", themes.DEFAULT_THEME.value)
    try:
        return themes.ThemeMode(raw)
    except ValueError:
        return themes.DEFAULT_THEME


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    app.setApplicationVersion(C.APP_VERSION)
    app.setOrganizationName(C.APP_ORG)

    icon = QIcon(app_icon_path())
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Register the bundled Space Grotesk font before anything builds a
    # QFont from it (themes.py's palettes name it by family string, "Space
    # Grotesk", for every mode but Hack) — if this fails to load for any
    # reason, Qt just falls back to a substitute font rather than raising,
    # so no further guarding is needed here.
    QFontDatabase.addApplicationFont(space_grotesk_font_path())

    # QSettings() above needs org/app name set first (done above) to read
    # the right registry-backed key. Applying the palette before
    # apply_theme() means the stylesheet is generated from the persisted
    # theme's colors on this very first paint, not the hardcoded defaults.
    theme_mode = _load_theme_mode()
    themes.apply_palette(theme_mode)
    apply_theme(app)
    scrollbars.install(app)

    window = MainWindow(theme_mode=theme_mode)
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
