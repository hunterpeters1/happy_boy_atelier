"""About dialog: the app's one proper identity moment.

Same QDialog-via-global-stylesheet pattern start_screen.py already
establishes -- theme.py's QDialog rule already covers this, so there's
no bespoke styling here. Replaces MainWindow's old plain
QMessageBox.about() call, which couldn't carry the app icon or format
credits/mission line as separate visual blocks. A pre-MainWindow launch
splash screen was explicitly scoped out of this feature (see the UI
upgrade plan's Section E1) -- real added complexity for a fast-starting
desktop app, and this dialog alone covers "the app has a proper identity
moment."
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from .. import constants as C
from ..resources import app_icon_path


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Happy Boy Atelier")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignHCenter)

        icon_label = QLabel()
        pixmap = QPixmap(app_icon_path())
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        icon_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(icon_label)

        self.name_label = QLabel(f"{C.APP_NAME}  ·  v{C.APP_VERSION}")
        self.name_label.setProperty("role", "section")
        self.name_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.name_label)

        # Mission line pulled verbatim from README.md/CLAUDE.md -- this
        # app is not a paint program and not an AI image generator; every
        # mark is placed by the artist.
        mission_label = QLabel(
            "Plan the painting before you touch the canvas.\n"
            "A digital drafting table for traditional painters — never a\n"
            "paint program, never an AI image generator."
        )
        mission_label.setAlignment(Qt.AlignHCenter)
        mission_label.setWordWrap(True)
        layout.addWidget(mission_label)

        credits_label = QLabel("Built by the Happy Boy Atelier team.")
        credits_label.setProperty("role", "hint")
        credits_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(credits_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
