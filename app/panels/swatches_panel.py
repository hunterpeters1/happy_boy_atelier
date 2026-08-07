"""Swatches dock: the eyedropper tool's output. Hovering a reference image
with the eyedropper armed updates a live color/value readout continuously;
clicking pins that color into a per-project list to reference while mixing
paint at the easel. Per-project, not shared between projects -- see
meta.color_swatches (project.py) and MainWindow's dock rebuild on project
load/new.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import icons

_CHIP_ICON_PX = 14


def _value_percent(color: QColor) -> int:
    """0-100 relative-luminance "value" reading -- the thing a painter
    judging value relationships cares about, not just raw RGB brightness.
    """
    r, g, b = color.red(), color.green(), color.blue()
    return round((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 * 100)


class _SwatchChip(QFrame):
    """A small fixed-size color square, used for both the live readout and
    each pinned-swatch row.
    """

    def __init__(self, size: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setFrameShape(QFrame.Box)
        self.set_color(None)

    def set_color(self, color: QColor | None) -> None:
        if color is None:
            self.setStyleSheet("background: transparent; border: 1px solid #8888;")
        else:
            self.setStyleSheet(f"background: {color.name()}; border: 1px solid #0006;")


class SwatchesPanel(QWidget):
    def __init__(self, scene, meta, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.meta = meta
        # Kept in the same order as meta.color_swatches so a remove click
        # can drop the right entry from both by shared index -- value-based
        # removal would misfire on duplicate colors.
        self._swatch_rows: list[QWidget] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        live_row = QHBoxLayout()
        self._live_chip = _SwatchChip(28)
        self._live_label = QLabel("Arm the eyedropper and hover a reference image")
        self._live_label.setWordWrap(True)
        live_row.addWidget(self._live_chip)
        live_row.addWidget(self._live_label, 1)
        outer.addLayout(live_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        outer.addWidget(divider)

        outer.addWidget(QLabel("Pinned swatches"))
        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(4)
        self._empty_label = QLabel("Click a reference image with the eyedropper to pin a swatch.")
        self._empty_label.setWordWrap(True)
        self._list_layout.addWidget(self._empty_label)

        list_container = QWidget()
        list_container.setLayout(self._list_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(list_container)
        outer.addWidget(scroll, 1)

        for hex_color in self.meta.color_swatches:
            self._add_row(hex_color)

        scene.color_hovered.connect(self.update_live_color)
        scene.color_sampled.connect(self.add_swatch)

    # -- live readout ------------------------------------------------------
    def update_live_color(self, color: QColor | None) -> None:
        self._live_chip.set_color(color)
        if color is None:
            self._live_label.setText("Arm the eyedropper and hover a reference image")
        else:
            self._live_label.setText(
                f"{color.name().upper()}   RGB {color.red()}, {color.green()}, {color.blue()}"
                f"   Value {_value_percent(color)}%"
            )

    # -- pinned list ---------------------------------------------------------
    def add_swatch(self, color: QColor) -> None:
        self.update_live_color(color)
        hex_color = color.name()
        self.meta.color_swatches.append(hex_color)
        self._add_row(hex_color)

    def _add_row(self, hex_color: str) -> None:
        self._empty_label.setVisible(False)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        chip = _SwatchChip(18)
        chip.set_color(QColor(hex_color))
        label = QLabel(hex_color.upper())
        remove_btn = QToolButton()
        remove_btn.setProperty("role", "compact")
        remove_btn.setIcon(icons.icon("delete", _CHIP_ICON_PX))
        remove_btn.setAutoRaise(True)
        remove_btn.setToolTip("Remove this swatch")
        remove_btn.clicked.connect(lambda: self._remove_row(row))
        layout.addWidget(chip)
        layout.addWidget(label, 1)
        layout.addWidget(remove_btn)
        self._list_layout.addWidget(row)
        self._swatch_rows.append(row)

    def _remove_row(self, row: QWidget) -> None:
        index = self._swatch_rows.index(row)
        del self.meta.color_swatches[index]
        del self._swatch_rows[index]
        self._list_layout.removeWidget(row)
        row.deleteLater()
        if not self.meta.color_swatches:
            self._empty_label.setVisible(True)
