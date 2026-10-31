"""Floating, borderless UI chrome that replaces the conventional Qt
menubar/toolbar/statusbar layout with a canvas-first, chrome-free interface.

All elements auto-hide when not in use and appear on demand:
  - TopBar: minimal, hovering the top edge (title / lock / theme / menu button)
  - ToolStrip: floating icon strip on the left canvas edge, hover-revealed
  - StatusBar: floating strip at the bottom canvas edge, hover-revealed
  - FloatingPanel: base class for Project/Properties/Swatches as draggable
    borderless cards that can snap to canvas edges as thin stripes
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import constants as C
from . import icons


# -- Fade animation duration (ms) -------------------------------------------
_FADE_MS = 150
_EDGE_HOVER_MARGIN = 24  # px from canvas edge that triggers a strip


class _FadeWidget(QWidget):
    """Base class for floating UI elements that fade in/out.

    Subclasses set self._content (a layout) and call _setup_fade().
    The widget is transparent outside its content via WA_TransparentForMousePositions
    while fading out, so it doesn't steal mouse events from the canvas.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(_FADE_MS)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._visible = False

    def _setup_fade(self):
        """Call after laying out content. Sets initial hidden state."""
        self.setWindowOpacity(0.0)
        self._visible = False

    def fade_in(self):
        if self._visible:
            return
        self._visible = True
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self.show()

    def fade_out(self):
        if not self._visible:
            return
        self._visible = False
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_out_done, type=Qt.ConnectionType.SingleShotConnection)
        self._fade_anim.start()

    def _on_fade_out_done(self):
        self.hide()
        self._fade_anim.finished.disconnect(self._on_fade_out_done)

    def is_actually_visible(self) -> bool:
        """True if the widget is shown AND fully opaque (fade-in complete)."""
        return self._visible and self.isVisible()

    def force_hide(self):
        """Immediately hide without animation."""
        self._visible = False
        self._fade_anim.stop()
        self.hide()


class ToolStrip(_FadeWidget):
    """Floating vertical icon strip that appears on the left canvas edge
    when the mouse hovers near it. Contains the most-used actions."""

    # (icon_name, tooltip, callback) — set by MainWindow
    _buttons: list[tuple[str, str, object]] = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = []
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(8)

        # Cards hold each icon in a small square frame
        self._containers: list[QFrame] = []
        for icon_name, tooltip, _ in self._buttons:
            frame = _ToolCard(icon_name, tooltip)
            layout.addWidget(frame)
            self._containers.append(frame)

        # Brass accent line on the right edge of the strip
        edge = _BrassEdge()
        layout.addWidget(edge)

        self._setup_fade()

    def set_buttons(self, buttons: list[tuple[str, str, object]]) -> None:
        """Reconfigure the strip's buttons."""
        # Clear existing
        for container in self._containers:
            self.layout().removeWidget(container)
            container.deleteLater()
        self._containers.clear()

        self._buttons = buttons
        for icon_name, tooltip, _ in buttons:
            frame = _ToolCard(icon_name, tooltip)
            self.layout().insertWidget(len(self._containers), frame)
            self._containers.append(frame)

    def connect_buttons(self, callbacks: dict[str, object]) -> None:
        """Wire click callbacks to the tool cards by icon_name."""
        for frame in self._containers:
            name = frame._icon_name
            cb = callbacks.get(name)
            if cb:
                frame.clicked.connect(cb)
        self._setup_fade()


class _ToolCard(QFrame):
    """A single floating icon card in the tool strip."""

    clicked = Signal()

    def __init__(self, icon_name: str, tooltip: str):
        super().__init__()
        self._icon_name = icon_name
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setFixedSize(44, 44)

        self._icon_label = QLabel()
        self._icon_label.setPixmap(icons.icon(icon_name, 24).pixmap(24, 24))
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._icon_label)

        # Brass border that glows on hover
        self.setStyleSheet(_tool_card_style())

    def _enter(self):
        self._hovered = True
        self.update()

    def _leave(self):
        self._hovered = False
        self.update()

    def enterEvent(self, event):
        self._enter()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._leave()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(C.COLOR_BRASS_BRIGHT if self._hovered else C.COLOR_LINE))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QColor(C.COLOR_BG_RAISED))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 3, 3)
        super().paintEvent(event)


def _tool_card_style() -> str:
    return f"""
    QFrame {{
        background: {C.COLOR_BG_RAISED};
        border: 1px solid {C.COLOR_LINE};
        border-radius: 3px;
    }}
    """


class _BrassEdge(QLabel):
    """A thin vertical brass accent line at the edge of the tool strip."""

    def __init__(self):
        super().__init__()
        self.setFixedWidth(2)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.COLOR_BRASS))
        super().paintEvent(event)


class BottomStatusBar(_FadeWidget):
    """Floating status strip at the bottom canvas edge, hover-revealed.
    Shows canvas name, dimensions, zoom, and the lock banner."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(16)

        self._hint_label = QLabel()
        self._hint_label.setProperty("role", "hint")
        layout.addWidget(self._hint_label)

        self._lock_banner = QLabel("SETUP LOCKED")
        self._lock_banner.setProperty("role", "banner-locked")
        self._lock_banner.setVisible(False)
        layout.addWidget(self._lock_banner)

        layout.addStretch(1)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet(
            f"color: {C.COLOR_INK_DIM}; font-family: '{C.FONT_FAMILY_MONO}'; font-size: 10px;"
        )
        layout.addWidget(self._zoom_label)

        self._setup_fade()

    def set_hint(self, text: str) -> None:
        self._hint_label.setText(text)

    def set_zoom(self, pct: int) -> None:
        self._zoom_label.setText(f"{pct}%")

    def set_locked(self, locked: bool) -> None:
        self._lock_banner.setVisible(locked)

    def paintEvent(self, event):
        # Draw a subtle brass underline
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.COLOR_BG_DARK))
        painter.setPen(QPen(QColor(C.COLOR_LINE), 1))
        painter.drawLine(0, 0, self.width(), 0)
        painter.setPen(QPen(QColor(C.COLOR_BRASS), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        super().paintEvent(event)


class TopBar(_FadeWidget):
    """Minimal floating top bar. Shows on hover at the top of the canvas window.
    Contains: window title, lock toggle, theme picker, and a menu (⋯) button
    that opens the full command overlay."""

    menu_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Title
        self._title = QLabel(C.APP_NAME)
        self._title.setStyleSheet(
            f"color: {C.COLOR_INK}; font-family: '{C.FONT_FAMILY_UI}'; font-size: 11px;"
        )
        layout.addWidget(self._title)

        layout.addStretch(1)

        # Lock toggle
        self._lock_btn = QToolButton()
        self._lock_btn.setProperty("role", "compact")
        self._lock_btn.setIconSize(QSize(18, 18))
        self._lock_btn.setIcon(icons.icon("lock", 18))
        self._lock_btn.setToolTip("Lock / unlock setup (Ctrl+L)")
        self._lock_btn.setCheckable(True)
        self._lock_btn.setAutoRaise(True)
        self._lock_btn.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._lock_btn)

        # Theme picker
        self._theme_btn = QToolButton()
        self._theme_btn.setProperty("role", "compact")
        self._theme_btn.setIconSize(QSize(18, 18))
        self._theme_btn.setIcon(icons.icon("eye", 18))
        self._theme_btn.setToolTip("Appearance themes")
        self._theme_btn.setAutoRaise(True)
        self._theme_btn.setStyleSheet("background: transparent; border: none;")
        self._theme_btn.setPopupMode(QToolButton.InstantPopup)
        layout.addWidget(self._theme_btn)

        # Menu button (⋯)
        self._menu_btn = QToolButton()
        self._menu_btn.setProperty("role", "compact")
        self._menu_btn.setIconSize(QSize(18, 18))
        # Use a simple "more" icon — three dots
        self._menu_btn.setText("⋯")
        self._menu_btn.setToolTip("All commands (Ctrl+K)")
        self._menu_btn.setAutoRaise(True)
        self._menu_btn.setStyleSheet(
            f"background: transparent; border: none; color: {C.COLOR_INK_DIM}; font-size: 14px;"
        )
        self._menu_btn.clicked.connect(self.menu_requested.emit)
        layout.addWidget(self._menu_btn)

        self._setup_fade()

    @property
    def lock_button(self) -> QToolButton:
        return self._lock_btn

    @property
    def theme_button(self) -> QToolButton:
        return self._theme_btn

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.COLOR_BG_DARK))
        painter.setPen(QPen(QColor(C.COLOR_LINE), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        super().paintEvent(event)


class FloatingPanel(_FadeWidget):
    """Base class for Project/Properties/Swatches panels when floating.
    A borderless, draggable card with a close button and a pin toggle.

    Can exist in two states:
      - Expanded: full panel content visible
      - Stripe: collapsed to a thin edge stripe (just a brass line + pin)
    """

    STRIPE_WIDTH = 8  # px when collapsed to a stripe

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._expanded = True
        self._pinned = False
        self._drag_pos: QPoint | None = None

        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header strip (drag handle + pin + close)
        self._header = _PanelHeader(title)
        self._header.drag_started.connect(self._on_drag_start)
        self._header.dragged.connect(self._on_drag)
        self._header.pin_toggled.connect(self._on_pin)
        self._header.close_requested.connect(self.force_hide)
        layout.addWidget(self._header)

        # Content area
        self._content = QWidget()
        self._content.setAttribute(Qt.WA_TranslucentBackground, False)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 12, 12, 12)
        self._content_layout.setSpacing(8)
        layout.addWidget(self._content, 1)

        # Brass border
        self.setStyleSheet(_panel_style())
        self._setup_fade()

    def _on_drag_start(self, pos: QPoint) -> None:
        self._drag_pos = pos

    def _on_drag(self, delta: QPoint) -> None:
        new_pos = self.mapToGlobal(self._drag_pos) + delta
        self.move(new_pos)

    def _on_pin(self, pinned: bool) -> None:
        self._pinned = pinned

    def set_content_widget(self, widget: QWidget) -> None:
        """Replace the panel's content with a given widget."""
        # Remove any existing content widget
        if self._content_layout.count() > 0:
            old = self._content_layout.takeAt(0)
            if old and old.widget():
                old.widget().deleteLater()
        self._content_layout.addWidget(widget)

    def set_stripe(self, is_stripe: bool) -> None:
        """Collapse to a thin stripe on the canvas edge, or expand."""
        if is_stripe and self._expanded:
            self._expanded = False
            self._content.setVisible(False)
            self.setFixedWidth(self.STRIPE_WIDTH)
        elif not is_stripe and not self._expanded:
            self._expanded = True
            self._content.setVisible(True)
            self.setFixedWidth(328)

    def paintEvent(self, event):
        if self._expanded:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(C.COLOR_BRASS), 1)
            painter.setPen(pen)
            painter.setBrush(QColor(C.COLOR_BG_PANEL))
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 4, 4)
        else:
            # Stripe: just a brass line
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(C.COLOR_BRASS))
        super().paintEvent(event)


def _panel_style() -> str:
    return f"""
    FloatingPanel {{
        background: {C.COLOR_BG_PANEL};
        border: 1px solid {C.COLOR_LINE};
        border-radius: 4px;
    }}
    """


class _PanelHeader(QFrame):
    """Drag handle + pin + close bar at the top of a floating panel."""

    drag_started = Signal(QPoint)
    dragged = Signal(QPoint)
    pin_toggled = Signal(bool)
    close_requested = Signal()

    def __init__(self, title: str):
        super().__init__()
        self._title = title
        self._drag_active = False
        self._drag_start: QPoint | None = None
        self.setFixedHeight(32)
        self.setCursor(Qt.SizeAllCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        label = QLabel(title)
        label.setStyleSheet(f"color: {C.COLOR_BRASS}; font-weight: 600; font-size: 10px;")
        layout.addWidget(label)

        layout.addStretch(1)

        # Pin button
        self._pin_btn = QToolButton()
        self._pin_btn.setProperty("role", "compact")
        self._pin_btn.setIconSize(QSize(14, 14))
        self._pin_btn.setIcon(icons.icon("eye", 14))
        self._pin_btn.setToolTip("Pin (keep visible)")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setAutoRaise(True)
        self._pin_btn.setStyleSheet("background: transparent; border: none;")
        self._pin_btn.toggled.connect(self._on_pin_toggled)
        layout.addWidget(self._pin_btn)

        # Close button
        close_btn = QToolButton()
        close_btn.setProperty("role", "compact")
        close_btn.setIconSize(QSize(14, 14))
        close_btn.setIcon(icons.icon("delete", 14))
        close_btn.setToolTip("Close")
        close_btn.setAutoRaise(True)
        close_btn.setStyleSheet("background: transparent; border: none;")
        close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(close_btn)

    def _on_pin_toggled(self, checked: bool):
        self.pin_toggled.emit(checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_start = event.globalPosition().toPoint()
            self.drag_started.emit(self._drag_start)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active and self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self._drag_start = event.globalPosition().toPoint()
            self.dragged.emit(delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = False
        super().mouseReleaseEvent(event)
