"""Library dock: a personal, cross-project reference-image collection
(see app/library.py) — a thumbnail grid, tabified with the Project Panel
on the left rather than a fourth always-visible chrome region. Turns
reference-gathering into an ongoing practice independent of any one
painting, a natural complement to the recent-files/thumbnails work.

Getting an image from here onto the canvas is deliberately just an
ordinary import, not a special path: dragging a thumbnail out carries a
real local-file:// URL (`_LibraryList.mimeData()`), which
`CanvasView`'s existing OS drag-and-drop handler already accepts —
zero changes needed there. Double-clicking does the same import,
just without the drag.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QSize, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import library

_THUMB_PX = 96
# How often to check uploader/photos/ for new phone uploads (see
# library.sync_from_uploader()). A plain directory listing + set lookup
# is cheap enough that a short interval costs nothing noticeable, and a
# few seconds reads as "live" for someone watching photos land while
# uploading from their phone -- see _poll_for_uploads().
_UPLOAD_POLL_INTERVAL_MS = 3000


class _LibraryList(QListWidget):
    def mimeData(self, items):
        mime = QMimeData()
        urls = []
        for row in items:
            entry = row.data(Qt.UserRole)
            if entry is not None:
                urls.append(QUrl.fromLocalFile(str(entry.image_path())))
        if urls:
            mime.setUrls(urls)
        return mime


class LibraryPanel(QWidget):
    # Emitted with a list of local file paths -- MainWindow connects this
    # straight to the same _import_image_paths() the file-dialog Import
    # and OS drag-and-drop already use, so a double-click import is one
    # undo step exactly like any other import.
    import_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)

        top_row = QHBoxLayout()
        add_btn = QToolButton()
        add_btn.setProperty("role", "compact")
        add_btn.setIconSize(QSize(22, 22))
        add_btn.setIcon(icons.icon("import", 22))
        add_btn.setAutoRaise(True)
        add_btn.setToolTip("Add Images to Library…")
        add_btn.clicked.connect(self._add_images)
        top_row.addWidget(add_btn)
        search_icon = QLabel()
        search_icon.setPixmap(icons.icon("search", 22).pixmap(22, 22))
        icons.register(search_icon, lambda obj, ic: obj.setPixmap(ic.pixmap(22, 22)), "search")
        top_row.addWidget(search_icon)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search library…")
        self.search_edit.textChanged.connect(self._apply_search_filter)
        top_row.addWidget(self.search_edit, 1)
        outer.addLayout(top_row)

        self.list = _LibraryList()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(_THUMB_PX, _THUMB_PX))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setSpacing(8)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_context_menu)
        self.list.itemActivated.connect(self._on_item_activated)
        outer.addWidget(self.list, 1)

        self.hint = QLabel("No reference images yet — Add Images to start a personal collection.")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        self.refresh()

        # Phone uploads (Help > Upload From Phone…, app/library.py's
        # sync_from_uploader()) land on disk from a separate process --
        # nothing here would otherwise know a new photo arrived. Polling
        # is simpler and more robust than a QFileSystemWatcher for this:
        # uploader/photos/ may not exist yet the first time this panel is
        # built (the uploader creates it lazily, on its own first run),
        # and a watcher would need extra handling for "start watching once
        # the directory appears" that a timer just doesn't need.
        self._upload_poll_timer = QTimer(self)
        self._upload_poll_timer.setInterval(_UPLOAD_POLL_INTERVAL_MS)
        self._upload_poll_timer.timeout.connect(self._poll_for_uploads)
        self._upload_poll_timer.start()

    # -- structural rebuild -------------------------------------------------
    def refresh(self) -> None:
        self.list.clear()
        entries = library.list_items()
        for entry in entries:
            row = QListWidgetItem(entry.name)
            thumb_path = entry.thumbnail_path()
            if thumb_path.exists():
                pixmap = QPixmap(str(thumb_path))
                if not pixmap.isNull():
                    row.setIcon(QIcon(pixmap))
            row.setData(Qt.UserRole, entry)
            row.setToolTip(entry.name)
            self.list.addItem(row)
        self.hint.setVisible(not entries)
        self._apply_search_filter()

    # -- search -----------------------------------------------------------
    def _apply_search_filter(self) -> None:
        text = self.search_edit.text().strip().lower()
        for i in range(self.list.count()):
            row = self.list.item(i)
            match = not text or text in row.text().lower()
            row.setHidden(not match)

    # -- live phone-upload sync ----------------------------------------------
    def _poll_for_uploads(self) -> None:
        if library.sync_from_uploader():
            self.refresh()

    # -- adding / removing --------------------------------------------------
    def _add_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Images to Library", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        added = False
        for path in paths:
            if library.add_image(Path(path)) is not None:
                added = True
        if added:
            self.refresh()

    def _show_context_menu(self, pos) -> None:
        row = self.list.itemAt(pos)
        if row is None:
            return
        entry = row.data(Qt.UserRole)
        menu = QMenu(self)
        import_action = menu.addAction(icons.icon("import"), "Import to Painting")
        import_action.triggered.connect(lambda: self._on_item_activated(row))
        menu.addSeparator()
        remove_action = menu.addAction(icons.icon("delete"), "Remove from Library")
        remove_action.triggered.connect(lambda: self._remove_entry(entry))
        menu.exec(self.list.mapToGlobal(pos))

    def _remove_entry(self, entry) -> None:
        library.remove_item(entry.id)
        self.refresh()

    # -- import onto the current painting ------------------------------------
    def _on_item_activated(self, row: QListWidgetItem) -> None:
        entry = row.data(Qt.UserRole)
        if entry is not None:
            self.import_requested.emit([str(entry.image_path())])
