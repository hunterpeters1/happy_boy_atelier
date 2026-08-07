"""App-wide auto-hiding, fading scrollbars.

Qt's Fusion style has no built-in "overlay scrollbar" mode (that's a
QtQuick/native-Cocoa thing, not a QWidgets one) — transparent-at-rest,
fade-in-on-demand is instead approximated here with a single global
QApplication event filter that fades a QGraphicsOpacityEffect on a
scrollbar in/out whenever the pointer enters/leaves its scroll area, over
the scrollbar itself, or while its handle is being dragged. Opacity (not
a QSS property) is what fades, since QSS has no transition/animation
syntax — see theme.py's plain, always-"visible" QScrollBar rules; this
module is entirely what makes them appear hidden at rest. The track's
width/height stays reserved at all times either way, so content never
reflows when a scrollbar fades in — a real floating overlay-over-content
would need a custom QAbstractScrollArea subclass per scrollable widget;
this is the practical approximation for a stock QTreeWidget/QListWidget/
QScrollArea.

install() is called once from main.py, after apply_theme() — every
QAbstractScrollArea and QScrollBar created for the lifetime of the app
(panels, dialogs, everything) is covered automatically since the filter
is installed on the QApplication itself, not per-widget.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QTimer
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QGraphicsOpacityEffect,
    QScrollBar,
    QWidget,
)

# Long enough that sweeping the pointer across a panel edge doesn't cause
# a visible flicker, short enough that the scrollbar doesn't linger once
# you've clearly moved on.
_HIDE_DELAY_MS = 500
# Quick enough to feel responsive rather than laggy, slow enough to read
# as a fade rather than a blink.
_FADE_MS = 150


class _BarFade:
    """One of these per scrollbar (lazily created, kept alive by being
    parented to the bar) — bundles the QGraphicsOpacityEffect actually
    doing the hiding with the QPropertyAnimation that fades its opacity,
    so repeated reveal/hide calls animate from wherever the fade
    currently is instead of jumping.
    """

    def __init__(self, bar: QScrollBar) -> None:
        self.effect = QGraphicsOpacityEffect(bar)
        self.effect.setOpacity(0.0)
        bar.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", bar)
        self.animation.setDuration(_FADE_MS)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

    def fade_to(self, target: float) -> None:
        if self.animation.endValue() == target and (
            self.animation.state() == QPropertyAnimation.Running
            or self.effect.opacity() == target
        ):
            return
        self.animation.stop()
        self.animation.setStartValue(self.effect.opacity())
        self.animation.setEndValue(target)
        self.animation.start()


class _ScrollBarRevealFilter(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._fades: dict[int, _BarFade] = {}
        self._hide_timers: dict[int, QTimer] = {}
        self._pressed: set[int] = set()
        app.installEventFilter(self)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _scroll_area_of(widget: QWidget) -> QAbstractScrollArea | None:
        """`widget` is a scroll area's own viewport() iff its parent is a
        QAbstractScrollArea and it *is* that parent's viewport — every
        other child widget living inside a scroll area (e.g. a row's
        embedded QToolButton) has the same parent chain shape but isn't
        the viewport itself, so this can't just check isinstance() on the
        parent alone.
        """
        parent = widget.parentWidget()
        if isinstance(parent, QAbstractScrollArea) and parent.viewport() is widget:
            return parent
        return None

    def _fade_for(self, bar: QScrollBar) -> _BarFade:
        fade = self._fades.get(id(bar))
        if fade is None:
            fade = _BarFade(bar)
            self._fades[id(bar)] = fade
        return fade

    def _reveal(self, bar: QScrollBar | None) -> None:
        if bar is None:
            return
        try:
            self._cancel_hide(bar)
            self._fade_for(bar).fade_to(1.0)
        except RuntimeError:
            pass  # underlying C++ scrollbar already deleted

    def _reveal_area(self, area: QAbstractScrollArea) -> None:
        self._reveal(area.verticalScrollBar())
        self._reveal(area.horizontalScrollBar())

    def _schedule_hide_area(self, area: QAbstractScrollArea) -> None:
        self._schedule_hide(area.verticalScrollBar())
        self._schedule_hide(area.horizontalScrollBar())

    def _cancel_hide(self, bar: QScrollBar) -> None:
        timer = self._hide_timers.pop(id(bar), None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _schedule_hide(self, bar: QScrollBar | None) -> None:
        if bar is None or id(bar) in self._pressed:
            return  # still being dragged — wait for the release instead
        self._cancel_hide(bar)
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _fire(b=bar) -> None:
            try:
                self._fade_for(b).fade_to(0.0)
            except RuntimeError:
                pass  # underlying C++ scrollbar already deleted

        timer.timeout.connect(_fire)
        timer.start(_HIDE_DELAY_MS)
        self._hide_timers[id(bar)] = timer

    # -- Qt event filter ---------------------------------------------------
    def eventFilter(self, watched, event) -> bool:
        etype = event.type()
        if etype not in (
            QEvent.Enter, QEvent.Leave,
            QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
        ):
            return False
        if not isinstance(watched, QWidget):
            return False

        if isinstance(watched, QScrollBar):
            if etype == QEvent.Enter:
                self._reveal(watched)
            elif etype == QEvent.Leave:
                self._schedule_hide(watched)
            elif etype == QEvent.MouseButtonPress:
                self._pressed.add(id(watched))
            elif etype == QEvent.MouseButtonRelease:
                self._pressed.discard(id(watched))
                self._schedule_hide(watched)
            return False

        area = self._scroll_area_of(watched)
        if area is not None:
            if etype == QEvent.Enter:
                self._reveal_area(area)
            elif etype == QEvent.Leave:
                self._schedule_hide_area(area)
        return False


def install(app: QApplication) -> None:
    """Idempotent — safe to call once at startup; a second call would just
    install a redundant filter, so this isn't re-entrancy-guarded beyond
    "call it once from main.py," matching how apply_theme() is used.
    """
    _ScrollBarRevealFilter(app)
