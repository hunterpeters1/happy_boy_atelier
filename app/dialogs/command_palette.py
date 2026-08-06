"""Command palette: a fuzzy-searchable list of every action in the app,
opened with Ctrl/Cmd+K.

Never maintains its own separate list of commands — MainWindow builds it
by walking the menu bar's own QActions (see MainWindow._collect_actions),
so it can never drift out of sync with what the menus actually contain,
and it is the answer to "I know this app can do X, where is it" for
anything that doesn't have a permanent, memorized home. This is exactly
the discoverability gap that left CanvasView.set_ruler_visible() with no
menu item, toolbar button, or shortcut at all in earlier versions.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


class CommandPalette(QDialog):
    def __init__(self, actions: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setMinimumWidth(480)
        self._actions = actions

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type a command…")
        self.search_edit.textChanged.connect(self._filter)
        self.search_edit.installEventFilter(self)
        layout.addWidget(self.search_edit)

        self.list = QListWidget()
        self.list.itemActivated.connect(self._trigger)
        layout.addWidget(self.list)

        self._filter("")
        self.search_edit.setFocus()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search_edit and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key_Down, Qt.Key_Up):
                self.list.setFocus()
                self.list.keyPressEvent(event)
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                current = self.list.currentItem() or (self.list.item(0) if self.list.count() else None)
                if current is not None:
                    self._trigger(current)
                return True
        return super().eventFilter(obj, event)

    def _filter(self, text: str) -> None:
        self.list.clear()
        needle = text.strip().lower()
        for action in self._actions:
            label = action.text().replace("&", "")
            if needle and needle not in label.lower():
                continue
            shortcut = action.shortcut().toString()
            item = QListWidgetItem(f"{label}    {shortcut}" if shortcut else label)
            item.setData(Qt.UserRole, action)
            if not action.isEnabled():
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _trigger(self, item: QListWidgetItem) -> None:
        action = item.data(Qt.UserRole)
        if action is None or not action.isEnabled():
            return
        self.accept()
        action.trigger()
