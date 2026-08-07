"""Swappable UI chrome palettes, layered on top of the fixed canvas/marker
colors in constants.py (COLOR_CANVAS, COLOR_FOCAL_*, COLOR_PERSPECTIVE,
COLOR_LIGHT, COLOR_SHADOW, COLOR_GUIDE). Those represent the physical
painting surface and the artist's own planning marks — they mean the same
thing regardless of which UI theme is active, so they are never
theme-dependent and are not listed here.

Every module in this app does `from . import constants as C` (or
`from .. import constants as C`) and reads colors as `C.COLOR_X` — that is
an attribute lookup on the shared `constants` module object, not a
value copied at import time, so mutating `constants.COLOR_X` here takes
effect for every subsequent read anywhere in the process. Canvas painting
and the stylesheet (theme.py, regenerated fresh from these values on
every apply_theme() call) both pick up a change immediately with no
restart needed.

The one exception is icon glyphs: icons.icon() bakes a QPixmap at call
time from whatever C.COLOR_INK/COLOR_BG_DARKEST/COLOR_INK_DIM currently
are, and every QAction/QToolButton built before a theme switch keeps its
already-baked QIcon. Re-rendering every icon everywhere (menus, toolbar,
every Project Panel row) live would mean tracking every icon consumer in
the app just to recolor a stroke line — not worth it for that cosmetic
detail, so icon colors catch up on the next restart while everything
else (backgrounds, borders, text, canvas chrome) updates immediately.
"""

from __future__ import annotations

from enum import Enum


class ThemeMode(str, Enum):
    CURRENT = "current"
    DARK = "dark"
    LIGHT = "light"
    HACK = "hack"


THEME_LABELS: dict[ThemeMode, str] = {
    ThemeMode.CURRENT: "Current Configuration",
    ThemeMode.DARK: "Dark Mode",
    ThemeMode.LIGHT: "Light Mode",
    ThemeMode.HACK: "Crazy Hack Mode",
}

DEFAULT_THEME = ThemeMode.LIGHT

# Every key here must match a real COLOR_*/FONT_FAMILY_UI attribute in
# constants.py. FONT_FAMILY_MONO is deliberately absent — it's reserved
# for genuine numeric readouts regardless of theme (see theme.py).
_PALETTES: dict[ThemeMode, dict[str, str]] = {
    # Verbatim today's brass/graphite "machined panel plate" look —
    # unchanged, kept selectable so switching themes is never a one-way
    # door away from what the app already looked like.
    ThemeMode.CURRENT: {
        "COLOR_BG_DARKEST": "#15171a",
        "COLOR_BG_DARK": "#1b1e22",
        "COLOR_BG_PANEL": "#20242a",
        "COLOR_BG_RAISED": "#282d34",
        "COLOR_LINE": "#3a4048",
        "COLOR_LINE_SUBTLE": "#2a2e34",
        "COLOR_INK": "#e8e6df",
        "COLOR_INK_DIM": "#9a9d9f",
        "COLOR_BRASS": "#c9a05c",
        "COLOR_BRASS_BRIGHT": "#e0b876",
        "COLOR_COPPER": "#b06a4a",
        "COLOR_CANVAS_BG": "#000000",
        "FONT_FAMILY_UI": "Space Grotesk",
    },
    # A distinct dark palette — cooler slate/steel-blue rather than warm
    # brass/graphite, so it actually reads as a different mode rather than
    # a re-skin of Current Configuration.
    ThemeMode.DARK: {
        "COLOR_BG_DARKEST": "#0d1117",
        "COLOR_BG_DARK": "#12161d",
        "COLOR_BG_PANEL": "#171c24",
        "COLOR_BG_RAISED": "#1f2530",
        "COLOR_LINE": "#2d3542",
        "COLOR_LINE_SUBTLE": "#1c212a",
        "COLOR_INK": "#e6e8eb",
        "COLOR_INK_DIM": "#8b93a1",
        "COLOR_BRASS": "#5b9dd9",
        "COLOR_BRASS_BRIGHT": "#7ab8ec",
        "COLOR_COPPER": "#3f6f93",
        "COLOR_CANVAS_BG": "#000000",
        "FONT_FAMILY_UI": "Space Grotesk",
    },
    # Default. Light neutral chrome; keeps the brass/copper accent (a
    # darker, higher-contrast shade of it) for visual continuity with the
    # other modes rather than switching accent families entirely.
    ThemeMode.LIGHT: {
        "COLOR_BG_DARKEST": "#ffffff",
        "COLOR_BG_DARK": "#f2f0ec",
        "COLOR_BG_PANEL": "#e9e6df",
        "COLOR_BG_RAISED": "#f7f5f0",
        "COLOR_LINE": "#c9c4b8",
        "COLOR_LINE_SUBTLE": "#dedad0",
        "COLOR_INK": "#26241f",
        "COLOR_INK_DIM": "#6b675d",
        "COLOR_BRASS": "#a8783a",
        "COLOR_BRASS_BRIGHT": "#c99a52",
        "COLOR_COPPER": "#8a4f34",
        # The one mode that keeps a light desk — pitch black would fight
        # the whole point of a *light* theme. A soft warm gray still gives
        # the canvas some edge/shadow definition against the desk.
        "COLOR_CANVAS_BG": "#f2f0ec",
        "FONT_FAMILY_UI": "Space Grotesk",
    },
    # The joke mode: black background, terminal green, monospace chrome
    # font. Paired with a hacker-message status widget and a Debug menu —
    # see main_window.py's _apply_theme()/_set_hack_mode_active().
    ThemeMode.HACK: {
        "COLOR_BG_DARKEST": "#000000",
        "COLOR_BG_DARK": "#000000",
        "COLOR_BG_PANEL": "#030a03",
        "COLOR_BG_RAISED": "#0a1c0a",
        "COLOR_LINE": "#00ff41",
        "COLOR_LINE_SUBTLE": "#0d3d17",
        "COLOR_INK": "#00ff41",
        "COLOR_INK_DIM": "#00b32d",
        "COLOR_BRASS": "#00ff41",
        "COLOR_BRASS_BRIGHT": "#7cff9b",
        "COLOR_COPPER": "#00cc37",
        "COLOR_CANVAS_BG": "#000000",
        "FONT_FAMILY_UI": "Consolas",
    },
}


def apply_palette(mode: ThemeMode) -> None:
    """Overwrite constants.py's chrome-color/UI-font attributes in place
    with `mode`'s values. Callers still need to re-run theme.apply_theme()
    afterward to regenerate the QPalette/stylesheet from the new values,
    and should repaint any open canvas view — see MainWindow._apply_theme().
    """
    from . import constants

    for key, value in _PALETTES[mode].items():
        setattr(constants, key, value)
