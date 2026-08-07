"""The Crazy Hack Mode status-bar widget: a small green-on-black panel with
a rotating fake "hacker" message and a couple of jittering fake progress
bars. Purely decorative — added to the status bar's permanent (right-hand)
area only while Hack Mode is the active theme, see
MainWindow._set_hack_mode_active().

Messages come from resources/hacker_messages.txt (one per line, '#'
comments and blank lines skipped) — edit that file to add your own; no
code change or restart needed, it's re-read each time Hack Mode turns on.
"""

from __future__ import annotations

import random

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from . import constants as C
from .resources import resource_path

_FALLBACK_MESSAGES = [
    "ACCESSING MAINFRAME...",
    "BYPASSING FIREWALL...",
    "DECRYPTING DATA...",
]

_MESSAGE_INTERVAL_MS = 1700
_BAR_TICK_MS = 150


def load_messages() -> list[str]:
    path = resource_path("resources", "hacker_messages.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f]
    except OSError:
        return list(_FALLBACK_MESSAGES)
    messages = [line for line in lines if line and not line.startswith("#")]
    return messages or list(_FALLBACK_MESSAGES)


class _FakeLoadBar(QProgressBar):
    """A progress bar with no real work behind it — the value jitters
    toward a randomly-chosen target, occasionally resetting, purely for
    the "busy hacking montage" look.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setTextVisible(False)
        self.setFixedHeight(6)
        self._target = random.randint(20, 100)
        self.setValue(random.randint(0, 30))

    def tick(self) -> None:
        if self.value() >= self._target:
            if random.random() < 0.15:
                self.setValue(0)  # "restarting" a fresh pass
            self._target = random.randint(10, 100)
            return
        self.setValue(min(100, self.value() + random.randint(1, 6)))


class HackerStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        self.message_label = QLabel()
        self.message_label.setStyleSheet(
            f"color: {C.COLOR_INK}; font-family: '{C.FONT_FAMILY_MONO}'; font-size: 10px;"
        )
        self.message_label.setFixedWidth(228)
        col.addWidget(self.message_label)

        self.bar1 = _FakeLoadBar()
        self.bar2 = _FakeLoadBar()
        for bar in (self.bar1, self.bar2):
            bar.setStyleSheet(
                f"QProgressBar {{ background: #000000; border: 1px solid {C.COLOR_LINE}; }}"
                f"QProgressBar::chunk {{ background: {C.COLOR_INK}; }}"
            )
            col.addWidget(bar)

        layout.addLayout(col)

        self._messages = load_messages()
        self._message_timer = QTimer(self)
        self._message_timer.timeout.connect(self._next_message)
        self._message_timer.start(_MESSAGE_INTERVAL_MS)
        self._next_message()

        self._bar_timer = QTimer(self)
        self._bar_timer.timeout.connect(self._tick_bars)
        self._bar_timer.start(_BAR_TICK_MS)

    def _next_message(self) -> None:
        text = random.choice(self._messages)
        self.message_label.setText(text)

    def _tick_bars(self) -> None:
        self.bar1.tick()
        self.bar2.tick()

    def stop(self) -> None:
        """Called right before this widget is torn down (theme switched
        away from Hack Mode) so its timers don't keep firing into a
        widget nobody's showing anymore.
        """
        self._message_timer.stop()
        self._bar_timer.stop()
