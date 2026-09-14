"""Generates resources/icons/app.png and resources/icons/app.ico -- the
window/taskbar icon (see resources.app_icon_path(), CLAUDE.md). Run this
directly (`python make_icon.py`) after changing anything below; nothing
imports this script, it's a source-of-truth generator, not app code.

A viewfinder/crop-frame mark -- four brass corner brackets around a single
focal-point dot dead center -- on a dark-graphite tile with a brass
border, the same palette used throughout the rest of the app's own
chrome. This replaced an earlier "HB" monogram (see git history): the app
is a composition-planning tool, not a lettering exercise, and the four
corner brackets are the same shape a photographer's viewfinder or a crop
tool uses to frame a shot -- closer to what the app actually does than
initials are. The center dot echoes the real Composition layer's own
focal-point marker (FocalPointItem in app/layers/composition_layer.py),
so the mark isn't just an empty frame. The four small corner rivets are
pulled directly from the real app's own hardware motif
(CanvasScene._draw_corner_rivets() in app/canvas/canvas_scene.py, and
app/panels/dock_title_bar.py) rather than an invented decoration -- same
idea ("rivets holding the panel plate together"), brightened slightly
from the real COLOR_LINE value since those two spots place rivets against
a lighter background than this icon's near-black tile, which would
otherwise swallow them at small sizes. They sit closer to the tile's
outer border than the viewfinder brackets do, so the two corner elements
read as separate layers (frame hardware vs. the framing mark itself)
rather than overlapping into a cluttered blob at small sizes.

Supersampled 4x then downscaled with LANCZOS for clean antialiased edges
-- PIL's ImageDraw calls have no AA of their own at 1x.
"""

import os

from PIL import Image, ImageDraw

SS = 4
FINAL_SIZE = 256
SIZE = FINAL_SIZE * SS

BG_DARK = (21, 23, 26, 255)
BRASS = (201, 160, 92, 255)
BRASS_BRIGHT = (224, 184, 118, 255)
RIVET = (74, 84, 94, 255)  # COLOR_LINE (#3a4048), brightened for visibility on this near-black tile

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
cx, cy = SIZE / 2, SIZE / 2

pad = int(SIZE * 0.035)
radius = int(SIZE * 0.20)
border_w = int(SIZE * 0.018)
d.rounded_rectangle([pad, pad, SIZE - pad, SIZE - pad], radius=radius, fill=BG_DARK,
                     outline=BRASS, width=border_w)

# -- corner rivets ---------------------------------------------------------
# Inset along the diagonal (not a fixed x/y inset like the real app's
# straight-cornered canvas rect and title bar) so each rivet clears the
# tile's own rounded corner arc and sits on the flat body of the plate.
rivet_r = SIZE * 0.018
diag_inset = radius * 0.62
for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
    rx = cx + sx * (SIZE / 2 - pad - diag_inset)
    ry = cy + sy * (SIZE / 2 - pad - diag_inset)
    d.ellipse([rx - rivet_r, ry - rivet_r, rx + rivet_r, ry + rivet_r], fill=RIVET)

# -- viewfinder mark ---------------------------------------------------------
# Four L-shaped corner brackets standing in for a viewfinder/crop frame --
# drawn well inside the tile's own border/rivets so the two corner
# elements read as distinct layers rather than merging into clutter.
vf_half = SIZE / 2 - SIZE * 0.30
arm = SIZE * 0.14
stroke = int(SIZE * 0.045)
for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
    corner_x = cx + dx * vf_half
    corner_y = cy + dy * vf_half
    d.line(
        [(corner_x - dx * arm, corner_y), (corner_x, corner_y), (corner_x, corner_y - dy * arm)],
        fill=BRASS_BRIGHT, width=stroke, joint="curve",
    )

# -- focal point ------------------------------------------------------------
# A single brass dot dead center -- the same primary focal-point marker
# used on the real Composition layer (FocalPointItem in
# app/layers/composition_layer.py) -- so the mark reads as "framing a
# subject" rather than an empty frame.
dot_r = SIZE * 0.05
d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=BRASS)

out = img.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)

os.makedirs("resources/icons", exist_ok=True)
out.save("resources/icons/app.png")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
out.save("resources/icons/app.ico", sizes=sizes)
print("Icon written to resources/icons/app.ico and resources/icons/app.png")
