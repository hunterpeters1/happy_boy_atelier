"""Generates resources/icons/app.png and resources/icons/app.ico -- the
window/taskbar icon (see resources.app_icon_path(), CLAUDE.md). Run this
directly (`python make_icon.py`) after changing anything below; nothing
imports this script, it's a source-of-truth generator, not app code.

An "HB" monogram in the app's own bundled UI typeface (Space Grotesk
Bold), brass on a dark-graphite tile with a brass border -- the same
palette used throughout the rest of the app's own chrome. The one
distinctive accent is four small corner rivets, pulled directly from the
real app's own hardware motif (CanvasScene._draw_corner_rivets() in
app/canvas/canvas_scene.py, and app/panels/dock_title_bar.py) rather than
an invented decoration -- same idea ("rivets holding the panel plate
together"), brightened slightly from the real COLOR_LINE value since
those two spots place rivets against a lighter background than this
icon's near-black tile, which would otherwise swallow them at small sizes.

Supersampled 4x then downscaled with LANCZOS for clean antialiased edges
-- PIL's ImageDraw/text calls have no AA of their own at 1x.
"""

import os

from PIL import Image, ImageDraw, ImageFont

SS = 4
FINAL_SIZE = 256
SIZE = FINAL_SIZE * SS

BG_DARK = (21, 23, 26, 255)
BRASS = (201, 160, 92, 255)
BRASS_BRIGHT = (224, 184, 118, 255)
RIVET = (74, 84, 94, 255)  # COLOR_LINE (#3a4048), brightened for visibility on this near-black tile

FONT_PATH = os.path.join("resources", "static", "SpaceGrotesk-Bold.ttf")

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

# -- "HB" mark --------------------------------------------------------------
text = "HB"
font_size = int(SIZE * 0.46)
font = ImageFont.truetype(FONT_PATH, font_size)

# Tight negative tracking between the two letters, drawn as two separate
# glyphs rather than one string -- a plain string draw at this weight
# left visibly loose, generic-looking letterspacing; a real logotype
# tightens it.
letters = list(text)
widths = []
for ch in letters:
    bbox = d.textbbox((0, 0), ch, font=font)
    widths.append(bbox[2] - bbox[0])
tracking = -font_size * 0.09
total_w = sum(widths) + tracking * (len(letters) - 1)

# Visual cap-height centering (not ascent/descent, which include room for
# lowercase descenders this all-caps mark never uses and would push the
# whole mark visually low).
cap_bbox = d.textbbox((0, 0), "H", font=font)
cap_h = cap_bbox[3] - cap_bbox[1]

x = cx - total_w / 2
y = cy - cap_h / 2 - cap_bbox[1]
for ch, w in zip(letters, widths):
    d.text((x, y), ch, font=font, fill=BRASS_BRIGHT)
    x += w + tracking

# Thin brass rule beneath the mark -- a small logotype flourish, ties it
# to the hairline-stroke language used throughout the app's own UI
# (never a thick underline/box, just a fine line).
rule_w = total_w * 0.62
rule_y = cy + cap_h * 0.62
rule_thick = max(2, int(SIZE * 0.006))
d.line([cx - rule_w / 2, rule_y, cx + rule_w / 2, rule_y], fill=BRASS, width=rule_thick)

out = img.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)

os.makedirs("resources/icons", exist_ok=True)
out.save("resources/icons/app.png")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
out.save("resources/icons/app.ico", sizes=sizes)
print("Icon written to resources/icons/app.ico and resources/icons/app.png")
