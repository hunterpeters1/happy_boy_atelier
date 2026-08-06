"""Visual language: a precision instrument, not a productivity dashboard.

Dark graphite chassis, brass/copper accent lines, thin hairline borders,
monospaced numeric readouts. No gradients, no rounded "app" bubbles, no
drop shadows — panels read like machined panel plates.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from . import constants as C


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C.COLOR_BG_DARK))
    pal.setColor(QPalette.WindowText, QColor(C.COLOR_INK))
    pal.setColor(QPalette.Base, QColor(C.COLOR_BG_DARKEST))
    pal.setColor(QPalette.AlternateBase, QColor(C.COLOR_BG_PANEL))
    pal.setColor(QPalette.ToolTipBase, QColor(C.COLOR_BG_RAISED))
    pal.setColor(QPalette.ToolTipText, QColor(C.COLOR_INK))
    pal.setColor(QPalette.Text, QColor(C.COLOR_INK))
    pal.setColor(QPalette.Button, QColor(C.COLOR_BG_RAISED))
    pal.setColor(QPalette.ButtonText, QColor(C.COLOR_INK))
    pal.setColor(QPalette.BrightText, QColor(C.COLOR_BRASS_BRIGHT))
    pal.setColor(QPalette.Highlight, QColor(C.COLOR_BRASS))
    pal.setColor(QPalette.HighlightedText, QColor(C.COLOR_BG_DARKEST))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(C.COLOR_INK_DIM))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(C.COLOR_INK_DIM))
    app.setPalette(pal)

    font = QFont(C.FONT_FAMILY_UI, 9)
    app.setFont(font)

    app.setStyleSheet(_stylesheet())


def _stylesheet() -> str:
    return f"""
    QMainWindow, QDialog {{
        background: {C.COLOR_BG_DARK};
    }}

    QWidget {{
        color: {C.COLOR_INK};
        font-family: "{C.FONT_FAMILY_UI}";
    }}

    QMenuBar {{
        background: {C.COLOR_BG_DARKEST};
        border-bottom: 1px solid {C.COLOR_LINE};
        padding: 2px;
    }}
    QMenuBar::item {{
        padding: 5px 10px;
        background: transparent;
    }}
    QMenuBar::item:selected {{
        background: {C.COLOR_BG_RAISED};
        color: {C.COLOR_BRASS_BRIGHT};
    }}
    QMenu {{
        background: {C.COLOR_BG_PANEL};
        border: 1px solid {C.COLOR_LINE};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 5px 24px 5px 12px;
    }}
    QMenu::item:selected {{
        background: {C.COLOR_BRASS};
        color: {C.COLOR_BG_DARKEST};
    }}
    QMenu::separator {{
        height: 1px;
        background: {C.COLOR_LINE};
        margin: 4px 6px;
    }}

    QToolBar {{
        background: {C.COLOR_BG_DARKEST};
        border-bottom: 1px solid {C.COLOR_LINE};
        spacing: 4px;
        padding: 4px;
    }}
    QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 2px;
        padding: 5px 8px;
        color: {C.COLOR_INK};
    }}
    QToolButton:hover {{
        border: 1px solid {C.COLOR_LINE};
        background: {C.COLOR_BG_RAISED};
    }}
    QToolButton:checked {{
        background: {C.COLOR_BRASS};
        color: {C.COLOR_BG_DARKEST};
        border: 1px solid {C.COLOR_BRASS_BRIGHT};
    }}

    QStatusBar {{
        background: {C.COLOR_BG_DARKEST};
        border-top: 1px solid {C.COLOR_LINE};
    }}

    QDockWidget {{
        titlebar-close-icon: none;
        color: {C.COLOR_INK};
    }}
    QDockWidget::title {{
        background: {C.COLOR_BG_DARKEST};
        border-bottom: 1px solid {C.COLOR_LINE};
        padding: 6px 8px;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    QGroupBox {{
        border: 1px solid {C.COLOR_LINE};
        border-radius: 2px;
        margin-top: 14px;
        padding-top: 6px;
        color: {C.COLOR_INK_DIM};
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: {C.COLOR_BRASS};
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    QPushButton {{
        background: {C.COLOR_BG_RAISED};
        border: 1px solid {C.COLOR_LINE};
        border-radius: 2px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        border: 1px solid {C.COLOR_BRASS};
    }}
    QPushButton:pressed {{
        background: {C.COLOR_BG_DARKEST};
    }}
    QPushButton:default {{
        border: 1px solid {C.COLOR_BRASS};
        color: {C.COLOR_BRASS_BRIGHT};
    }}
    QPushButton:disabled {{
        color: {C.COLOR_INK_DIM};
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
        background: {C.COLOR_BG_DARKEST};
        border: 1px solid {C.COLOR_LINE};
        border-radius: 2px;
        padding: 4px 6px;
        selection-background-color: {C.COLOR_BRASS};
        selection-color: {C.COLOR_BG_DARKEST};
        font-family: "{C.FONT_FAMILY_MONO}";
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {C.COLOR_BRASS};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QSlider::groove:horizontal {{
        height: 3px;
        background: {C.COLOR_LINE};
        border-radius: 1px;
    }}
    QSlider::handle:horizontal {{
        width: 12px;
        margin: -6px 0;
        background: {C.COLOR_BRASS};
        border: 1px solid {C.COLOR_BRASS_BRIGHT};
        border-radius: 6px;
    }}
    QSlider::sub-page:horizontal {{
        background: {C.COLOR_COPPER};
        border-radius: 1px;
    }}

    QCheckBox::indicator, QRadioButton::indicator {{
        width: 13px;
        height: 13px;
        border: 1px solid {C.COLOR_LINE};
        background: {C.COLOR_BG_DARKEST};
    }}
    QCheckBox::indicator:checked {{
        background: {C.COLOR_BRASS};
        border: 1px solid {C.COLOR_BRASS_BRIGHT};
    }}
    QRadioButton::indicator {{
        border-radius: 7px;
    }}
    QRadioButton::indicator:checked {{
        background: {C.COLOR_BRASS};
        border: 1px solid {C.COLOR_BRASS_BRIGHT};
    }}

    QTreeWidget, QListWidget {{
        background: {C.COLOR_BG_DARKEST};
        border: 1px solid {C.COLOR_LINE};
        outline: none;
    }}
    QTreeWidget::item, QListWidget::item {{
        padding: 4px 2px;
    }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {C.COLOR_BRASS};
        color: {C.COLOR_BG_DARKEST};
    }}
    QHeaderView::section {{
        background: {C.COLOR_BG_PANEL};
        border: none;
        border-bottom: 1px solid {C.COLOR_LINE};
        padding: 4px;
        color: {C.COLOR_INK_DIM};
    }}

    QScrollBar:vertical {{
        background: {C.COLOR_BG_DARKEST};
        width: 12px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {C.COLOR_BG_RAISED};
        border: 1px solid {C.COLOR_LINE};
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {C.COLOR_LINE};
    }}
    QScrollBar:horizontal {{
        background: {C.COLOR_BG_DARKEST};
        height: 12px;
    }}
    QScrollBar::handle:horizontal {{
        background: {C.COLOR_BG_RAISED};
        border: 1px solid {C.COLOR_LINE};
        min-width: 24px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0; height: 0; border: none;
    }}

    QLabel[role="section"] {{
        color: {C.COLOR_BRASS};
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    QLabel[role="hint"] {{
        color: {C.COLOR_INK_DIM};
        font-style: italic;
    }}
    QLabel[role="banner-locked"] {{
        background: {C.COLOR_COPPER};
        color: {C.COLOR_BG_DARKEST};
        font-weight: 600;
        padding: 4px 10px;
        letter-spacing: 1px;
    }}

    QToolTip {{
        background: {C.COLOR_BG_RAISED};
        color: {C.COLOR_INK};
        border: 1px solid {C.COLOR_BRASS};
        padding: 4px;
    }}
    """
