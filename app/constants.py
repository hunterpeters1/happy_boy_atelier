"""Static reference data: canvas formats, units, layer identifiers, palette.

Kept dependency-free (no Qt imports) so it can be used by both the Qt layer
and pure data/serialization code.
"""

from __future__ import annotations

from enum import Enum


APP_NAME = "Happy Boy Atelier"
APP_ORG = "HappyBoyAtelier"
APP_VERSION = "1.0.0"
FORMAT_VERSION = 1

# Phase 0.3: autosave interval for the crash-recovery snapshot (not the
# user's own Save/Save As, which stays fully manual). Hardcoded for now —
# architecture should stay flexible enough to expose this as a user
# preference later, but Phase 0 does not add settings UI.
AUTOSAVE_INTERVAL_MS = 3 * 60 * 1000

# Scene coordinates are physical inches, scaled to this many scene "pixels"
# per inch. View zoom is a separate multiplier applied on top of this, so
# the model always represents actual painting dimensions.
SCENE_PX_PER_INCH = 100.0

UNITS = ["in", "cm", "mm", "px"]

_UNIT_TO_INCHES = {
    "in": 1.0,
    "cm": 1.0 / 2.54,
    "mm": 1.0 / 25.4,
    # px assumes a 96 dpi reference, matching common screen/print defaults
    "px": 1.0 / 96.0,
}


def to_inches(value: float, unit: str) -> float:
    return value * _UNIT_TO_INCHES.get(unit, 1.0)


def from_inches(value_in: float, unit: str) -> float:
    factor = _UNIT_TO_INCHES.get(unit, 1.0)
    return value_in / factor if factor else value_in


# (label, width_in, height_in)
PORTRAIT_FORMATS = [
    ("8 x 10", 8, 10),
    ("11 x 14", 11, 14),
    ("16 x 20", 16, 20),
    ("18 x 24", 18, 24),
    ("24 x 36", 24, 36),
]

LANDSCAPE_FORMATS = [
    ("10 x 8", 10, 8),
    ("14 x 11", 14, 11),
    ("20 x 16", 20, 16),
    ("24 x 18", 24, 18),
    ("36 x 24", 36, 24),
]

SQUARE_FORMATS = [
    ("8 x 8", 8, 8),
    ("12 x 12", 12, 12),
    ("16 x 16", 16, 16),
    ("20 x 20", 20, 20),
    ("24 x 24", 24, 24),
]


class LayerKind(str, Enum):
    REFERENCE = "reference"
    COMPOSITION = "composition"
    PERSPECTIVE = "perspective"
    LIGHTING = "lighting"
    GUIDES = "guides"


LAYER_ORDER = [
    LayerKind.REFERENCE,
    LayerKind.COMPOSITION,
    LayerKind.PERSPECTIVE,
    LayerKind.LIGHTING,
    LayerKind.GUIDES,
]

LAYER_LABELS = {
    LayerKind.REFERENCE: "Reference",
    LayerKind.COMPOSITION: "Composition",
    LayerKind.PERSPECTIVE: "Perspective",
    LayerKind.LIGHTING: "Lighting",
    LayerKind.GUIDES: "Guides",
}


class PerspectiveMode(str, Enum):
    ONE_POINT = "1pt"
    TWO_POINT = "2pt"
    THREE_POINT = "3pt"


PERSPECTIVE_POINT_COUNT = {
    PerspectiveMode.ONE_POINT: 1,
    PerspectiveMode.TWO_POINT: 2,
    PerspectiveMode.THREE_POINT: 3,
}

# ---------------------------------------------------------------------------
# Palette — brass / graphite instrument-panel aesthetic
# ---------------------------------------------------------------------------

COLOR_BG_DARKEST = "#15171a"
COLOR_BG_DARK = "#1b1e22"
COLOR_BG_PANEL = "#20242a"
COLOR_BG_RAISED = "#282d34"
COLOR_LINE = "#3a4048"
COLOR_LINE_SUBTLE = "#2a2e34"

COLOR_INK = "#e8e6df"          # primary text — warm off-white, like paper
COLOR_INK_DIM = "#9a9d9f"      # secondary text

COLOR_BRASS = "#c9a05c"        # primary accent — brass/instrument gold
COLOR_BRASS_BRIGHT = "#e0b876"
COLOR_COPPER = "#b06a4a"       # secondary accent

COLOR_CANVAS = "#efe9dd"       # the painting surface itself (warm paper white)
COLOR_CANVAS_EDGE = "#0c0d0e"
COLOR_CANVAS_BG = "#15171a"    # the desk/void behind the physical canvas rect
                                # (CanvasScene.drawBackground) — theme-dependent
                                # (pitch black in every mode but Light), unlike
                                # COLOR_CANVAS itself, which never changes

COLOR_FOCAL_PRIMARY = "#c9482f"    # focal point markers
# Reserved hues below: every content-marker color is deliberately distinct
# from COLOR_BRASS (the one chrome/interactive accent) and from each other.
# COLOR_FOCAL_SECONDARY and COLOR_GUIDE used to both equal COLOR_BRASS
# verbatim, which meant a secondary focal point, a rule-of-thirds line, and
# "this menu item is selected" were visually the same paint. Never collapse
# a content color back onto COLOR_BRASS/COLOR_BRASS_BRIGHT.
COLOR_FOCAL_SECONDARY = "#9575b0"   # violet — was identical to COLOR_BRASS
COLOR_PERSPECTIVE = "#5fb3c9"       # horizon/vanishing/grid lines — cool blue,
                                     # reads distinctly from warm brass UI chrome
COLOR_LIGHT = "#e8d477"             # light source / direction
COLOR_SHADOW = "#5c6b78"            # shadow direction
COLOR_GUIDE = "#6b7480"             # rule of thirds / golden ratio — was
                                     # identical to COLOR_BRASS; now a dim,
                                     # neutral blue-grey so guides read as
                                     # "structure," not "selected UI"

FONT_FAMILY_UI = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"

# Shared with theme.py's QScrollBar QSS (width/height of the slim pill
# handle) and app/panels/layers_panel.py (right-margin clearance so
# right-pinned row buttons never render under the scrollbar's stripe) —
# one source of truth so the two can't drift out of sync.
SCROLLBAR_WIDTH_PX = 8
