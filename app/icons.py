"""Single-weight line icons, rendered at runtime instead of shipped as
color-baked files.

ARCHITECTURE.md documents a "brass/graphite line-art" icon language for
resources/icons/ that was never actually built — the toolbar has always
been text-only. This module is that language, finally implemented: each
shape is defined once, stroke-only, in a 20x20 viewBox, and tinted per
QIcon mode so the same glyph reads clearly both on the toolbar's resting
dark background and on a checked action's brass fill.
"""

from __future__ import annotations

import weakref
from typing import Callable

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import constants as C

# Body markup only (no outer <svg> tag) — kept minimal, single stroke
# weight, no fills, matching the "machined panel plate" brief in theme.py.
_SHAPES: dict[str, str] = {
    "new": '<path d="M5 2.5h6l4 4v11H5z"/><path d="M11 2.5v4h4"/><path d="M7.5 11.5h5M7.5 14.5h5"/>',
    "open": '<path d="M3 6.5h5l1.3 2H17v8.5H3z"/>',
    "save": '<path d="M4 3.5h9.5l3 3v10H4z"/><path d="M7 3.5v5h6.5v-5"/><path d="M7 13.5h6.5"/>',
    # A photo frame plus a "+" badge — reads as "add a reference image,"
    # distinct from "export"'s tray-arrow (the two used to be mirror
    # images of each other: down-arrow-into-tray vs. up-arrow-out-of-tray,
    # which read as generic download/upload rather than image import).
    "import": '<rect x="2" y="3.5" width="11" height="10" rx="1"/><path d="m3 11.5 2.8-2.8 2 2 2.7-3.2 2.5 2.5"/><circle cx="6" cy="6.5" r="1.1"/><path d="M17 8.5v7M13.5 12h7"/>',
    "export": '<path d="M10 15.5v-9.5M6.5 9.5l3.5-3.5 3.5 3.5"/><path d="M4 15h12v2.5H4z"/>',
    "fit": '<path d="M3 8V3.5h4.5M17 8V3.5h-4.5M3 12v4.5h4.5M17 12v4.5h-4.5"/>',
    "undo": '<path d="M6.5 6H3V2.5"/><path d="M3 6a7.5 7.5 0 1 1 2 7.8"/>',
    "redo": '<path d="M13.5 6H17V2.5"/><path d="M17 6a7.5 7.5 0 1 0-2 7.8"/>',
    "delete": '<path d="M4 5.5h12M8 5.5v-2h4v2"/><path d="M6 5.5l.9 12h6.2l.9-12"/>',
    "lock": '<rect x="5" y="9" width="10" height="8" rx="1"/><path d="M7.5 9V6.2a2.5 2.5 0 0 1 5 0V9"/>',
    "unlock": '<rect x="5" y="9" width="10" height="8" rx="1"/><path d="M7.5 9V6.2a2.5 2.5 0 0 1 4.7-1.2"/>',
    "focal": '<circle cx="10" cy="10" r="3.4"/><path d="M10 2v2.4M10 15.6V18M2 10h2.4M15.6 10H18"/>',
    "movement": '<path d="M3.5 15c3-6 10-11 13-3"/><path d="M13.5 9.5l3 2.5-3.5 1"/>',
    "note": '<path d="M4 3h9l3 3v11H4z"/><path d="M13 3v3h3"/><path d="M7 10h6M7 13h6"/>',
    "vanishing": '<path d="M10 2v16M1 10h18"/><path d="M4.5 4.5L10 10l-5.5 5.5M15.5 4.5L10 10l5.5 5.5"/>',
    "light": '<circle cx="10" cy="9" r="4"/><path d="M10 1.5v2M10 16.5v2M2.3 9h2M15.7 9h2M4.7 3.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 3.7l-1.4 1.4M5.1 13.9l-1.4 1.4"/>',
    "shadow": '<circle cx="10" cy="9" r="4"/><path d="M4 17c2-2 10-2 12 0"/>',
    "search": '<circle cx="8.5" cy="8.5" r="5.5"/><path d="m17 17-4-4"/>',
    "eye": '<path d="M1 10s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6Z"/><circle cx="10" cy="10" r="2.6"/>',
    "chevron": '<path d="m6 4 6 6-6 6"/>',
    "image": '<rect x="2" y="3" width="16" height="14" rx="1"/><circle cx="7" cy="8" r="1.6"/><path d="m3 15 5-5 3 3 3-4 5 6"/>',
    "shapes": '<circle cx="6.5" cy="6.5" r="3.3"/><rect x="11" y="3.2" width="6" height="6"/><path d="M6.5 12 2.5 18h8Z"/>',
    # Batch-align glyphs: an edge marker plus an arrow pointing toward it —
    # previously rendered as raw Unicode double-arrow characters (e.g.
    # U+27F8), which several UI fonts (including this app's default,
    # Segoe UI) don't carry a glyph for, so the buttons showed nothing at
    # all rather than falling back to a visible tofu box.
    "align_left": '<path d="M4 3v14"/><path d="M16 10H7"/><path d="M10.5 6.5 7 10l3.5 3.5"/>',
    "align_right": '<path d="M16 3v14"/><path d="M4 10h9"/><path d="M9.5 6.5 13 10l-3.5 3.5"/>',
    "align_top": '<path d="M3 4h14"/><path d="M10 16V7"/><path d="M6.5 10.5 10 7l3.5 3.5"/>',
    "align_bottom": '<path d="M3 16h14"/><path d="M10 4v9"/><path d="M6.5 9.5 10 13l3.5-3.5"/>',
    # Project Panel per-row stacking-order controls: move an item forward
    # (prints closer to the top of its layer) / backward within its layer.
    "reorder_up": '<path d="M10 16V4"/><path d="M5 9l5-5 5 5"/>',
    "reorder_down": '<path d="M10 4v12"/><path d="M5 11l5 5 5-5"/>',
    # Eyedropper: a diamond-bodied pipette (bulb top-right, tip bottom-left)
    # with a band line near the tip and a small sampled-drop dot below it.
    "eyedropper": '<path d="M14.5 2.5l3 3-9 9-4 1 1-4z"/><path d="M12 5l3 3"/><circle cx="4" cy="16" r="1"/>',
}


def _render(name: str, color: str, size: int) -> QPixmap:
    body = _SHAPES[name]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
        f'fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def icon(name: str, size: int = 22) -> QIcon:
    """A QIcon tinted so it reads on both a resting dark toolbar surface
    (Normal/Off) and a checked action's brass fill (Normal/On), matching
    how QToolButton:checked already inverts to a brass background with
    dark text in theme.py.
    """
    ic = QIcon()
    ic.addPixmap(_render(name, C.COLOR_INK, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(_render(name, C.COLOR_BG_DARKEST, size), QIcon.Normal, QIcon.On)
    ic.addPixmap(_render(name, C.COLOR_INK_DIM, size), QIcon.Disabled, QIcon.Off)
    return ic


# -- live theme switching ---------------------------------------------------
# icon() bakes a QPixmap at call time from whatever C.COLOR_INK/
# COLOR_BG_DARKEST/COLOR_INK_DIM currently are (see themes.py's
# apply_palette() docstring) — an already-baked QIcon on an existing
# QAction/QToolButton doesn't update on its own when those change. Any
# long-lived icon consumer (menu/toolbar actions, the Properties panel's
# align buttons — not the Project Panel, which fully rebuilds its tree from
# scratch on any refresh anyway, or the canvas context menu, which is
# rebuilt fresh on every right-click) should register() here so
# refresh_all() can re-set its icon after a live theme switch. Held as
# weakrefs so a destroyed consumer just gets skipped/pruned rather than
# kept alive by this module.
_REGISTRY: list[tuple["weakref.ReferenceType", Callable[[object, QIcon], None], object]] = []


def register(consumer, apply: Callable[[object, QIcon], None], name) -> None:
    """`apply(consumer, icon)` performs whatever call actually sets the
    icon (setIcon(), setIcon(column, ...), setPixmap(icon.pixmap(...)),
    etc.). `name` is either a fixed icon name, or a zero-arg callable
    returning the current one for consumers whose glyph depends on live
    state (e.g. a lock/unlock toggle) rather than being fixed at
    registration time.
    """
    _REGISTRY.append((weakref.ref(consumer), apply, name))


def refresh_all() -> None:
    """Re-render every still-alive registered consumer's icon using
    whatever theme is active right now. Call after a live theme switch —
    see MainWindow._set_theme()/_reload_stylesheet().
    """
    alive = []
    for ref, apply, name in _REGISTRY:
        consumer = ref()
        if consumer is None:
            continue
        resolved_name = name() if callable(name) else name
        try:
            apply(consumer, icon(resolved_name))
        except RuntimeError:
            continue  # underlying C++ object already deleted
        alive.append((ref, apply, name))
    _REGISTRY[:] = alive
