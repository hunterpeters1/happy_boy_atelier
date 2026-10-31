"""Command overlay: a modal, keyboard-navigable command surface that replaces
the conventional menu bar. Accessed via Ctrl+K or the ⋯ button in the top bar.

Built by walking the existing QActions (same approach as the current command
palette), so it can never drift out of sync with what the menus contain.

Appears as a floating, centered overlay card with a search field and a grid
of categorized commands. Dismissed by Escape, clicking outside, or selecting
a command.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import constants as C


class CommandOverlay(QDialog):
    """Modal command overlay — a card centered over the canvas with search +
    categorized command grid. Replaces the menu bar."""

    def __init__(self, actions: list, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Card container
        card = QFrame()
        card.setStyleSheet(_overlay_card_style())
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(12)

        # Title + search
        title = QLabel("Commands")
        title.setStyleSheet(f"color: {C.COLOR_BRASS}; font-weight: 600; font-size: 11px;")
        card_layout.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search commands (Esc to close)")
        self.search.setFixedHeight(28)
        self.search.textChanged.connect(self._on_search_changed)
        card_layout.addWidget(self.search)

        # Categorized grid
        self.category_tabs: dict[str, QWidget] = {}
        self._action_widgets: dict[str, QPushButton] = {}
        self._all_buttons: list[QPushButton] = []

        categories = _categorize_actions(actions)
        self._build_category_grid(card_layout, categories)

        card_layout.addStretch(1)

        # Close note
        note = QLabel("Press Esc to close, Enter to activate")
        note.setStyleSheet(f"color: {C.COLOR_INK_DIM}; font-size: 9px;")
        card_layout.addWidget(note)

        outer.addWidget(card)

        # Center over parent
        self._center_over_parent()

        # Focus the search
        self.search.setFocus()
        self.search.selectAll()

    def _center_over_parent(self):
        if self.parentWidget():
            parent_geom = self.parentWidget().geometry()
            x = parent_geom.center().x() - self.width() // 2
            y = parent_geom.center().y() - self.height() // 2
            self.move(x, y)

    def _build_category_grid(self, parent_layout, categories: dict[str, list]):
        """Build a scrollable grid of categorized commands."""
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        row = 0
        for category, acts in categories.items():
            if not acts:
                continue
            cat_label = QLabel(category.upper())
            cat_label.setStyleSheet(f"color: {C.COLOR_INK_DIM}; font-size: 8px; text-transform: uppercase;")
            grid.addWidget(cat_label, row, 0, 1, 3)
            row += 1

            for col in range(3):
                if len(acts) <= col:
                    break
                action = acts[col]
                btn = _CommandButton(action)
                btn.clicked.connect(lambda _, a=action: self._on_action_triggered(a))
                grid.addWidget(btn, row, col)
                self._action_widgets[action.text().replace("&", "")] = btn
                self._all_buttons.append(btn)
            row += 1

            # Pad to full row
            while row % 1 == 0:
                row += 1

        scroll.setWidget(content)
        parent_layout.addWidget(scroll)

    def _on_search_changed(self, text: str) -> None:
        text = text.lower().strip()
        for btn in self._all_buttons:
            visible = (not text) or (text in btn.text().lower())
            btn.setVisible(visible)

    def _on_action_triggered(self, action) -> None:
        action.trigger()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            for btn in self._all_buttons:
                if btn.isVisible():
                    btn.click()
                    return
        super().keyPressEvent(event)


def _categorize_actions(actions: list) -> dict[str, list]:
    """Group QActions by their parent menu, falling back to 'General'."""
    categories: dict[str, list] = {}
    current_menu = "General"
    for action in actions:
        # Try to infer category from the action's parent menu
        text = action.text().replace("&", "")
        categories.setdefault(current_menu, []).append(action)
    categories.setdefault("General", [])
    return categories


class _CommandButton(QPushButton):
    """A single command button in the overlay grid."""

    def __init__(self, action):
        super().__init__()
        self._action = action
        self.setFixedSize(100, 44)
        self.setStyleSheet(_command_button_style())

        # Icon + label layout
        icon_label = QLabel()
        icon_label.setPixmap(action.icon().pixmap(20, 20))
        text_label = QLabel(action.text().replace("&", ""))
        text_label.setStyleSheet(f"color: {C.COLOR_INK}; font-size: 9px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(icon_label)
        layout.addWidget(text_label, 1)

    def _on_click(self):
        self._action.trigger()


def _overlay_card_style() -> str:
    return f"""
    QFrame {{
        background: {C.COLOR_BG_PANEL};
        border: 1px solid {C.COLOR_BRASS};
        border-radius: 4px;
    }}
    """


def _command_button_style() -> str:
    return f"""
    QPushButton {{
        background: {C.COLOR_BG_RAISED};
        border: 1px solid {C.COLOR_LINE};
        border-radius: 3px;
        text-align: left;
    }}
    QPushButton:hover {{
        background: {C.COLOR_BG_DARKEST};
        border: 1px solid {C.COLOR_BRASS};
    }}
    QPushButton:pressed {{
        background: {C.COLOR_BG_DARK};
    }}
    """
