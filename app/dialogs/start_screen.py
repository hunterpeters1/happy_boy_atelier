"""Start screen: shown at launch when there's no crash to recover from
and at least one recent painting exists — instead of dropping straight
into a blank Untitled Painting with zero memory of what you were last
working on. Recent paintings show as real thumbnails (thumb.png, cached
in the .atelier file itself), titled by their actual in-app project
name — not a bare, memory-less native file dialog, which is what File >
Open still is otherwise.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class StartScreen(QDialog):
    open_recent = Signal(Path)
    new_painting_requested = Signal()
    open_requested = Signal()

    def __init__(self, recents: list[tuple[Path, bytes | None]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Happy Boy Atelier")
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)

        title = QLabel("Recent Paintings")
        title.setProperty("role", "section")
        layout.addWidget(title)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(140, 140))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setSpacing(10)
        for path, thumb_bytes in recents:
            item = QListWidgetItem(path.stem)
            if thumb_bytes:
                pixmap = QPixmap()
                if pixmap.loadFromData(thumb_bytes):
                    item.setIcon(pixmap)
            item.setData(Qt.UserRole, path)
            item.setToolTip(str(path))
            self.list.addItem(item)
        self.list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list, 1)

        button_row = QHBoxLayout()
        new_btn = QPushButton("New Painting…")
        new_btn.clicked.connect(self._on_new)
        open_btn = QPushButton("Open…")
        open_btn.clicked.connect(self._on_open)
        button_row.addWidget(new_btn)
        button_row.addWidget(open_btn)
        button_row.addStretch(1)
        skip_btn = QPushButton("Start Blank")
        skip_btn.clicked.connect(self.reject)
        button_row.addWidget(skip_btn)
        layout.addLayout(button_row)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        self.open_recent.emit(path)
        self.accept()

    def _on_new(self) -> None:
        self.new_painting_requested.emit()
        self.accept()

    def _on_open(self) -> None:
        self.open_requested.emit()
        self.accept()
