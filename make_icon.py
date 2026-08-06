from PIL import Image, ImageDraw
import math
import os

SIZE = 256
BG_DARK = (21, 23, 26, 255)
BRASS = (201, 160, 92, 255)
BRASS_BRIGHT = (224, 184, 118, 255)
CANVAS = (239, 233, 221, 255)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

pad = 6
radius = 46
d.rounded_rectangle([pad, pad, SIZE - pad, SIZE - pad], radius=radius, fill=BG_DARK, outline=BRASS, width=6)

cx, cy = SIZE / 2, SIZE / 2

canvas_w, canvas_h = 108, 138
canvas_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
cd = ImageDraw.Draw(canvas_img)
cd.rectangle([0, 0, canvas_w - 1, canvas_h - 1], fill=CANVAS, outline=(12, 13, 14, 255), width=4)
canvas_img = canvas_img.rotate(-8, expand=True, resample=Image.BICUBIC)
img.alpha_composite(canvas_img, (int(cx - canvas_img.width / 2 - 18), int(cy - canvas_img.height / 2 + 6)))

ring_cx, ring_cy, ring_r = cx + 30, cy - 26, 66
d.ellipse([ring_cx - ring_r, ring_cy - ring_r, ring_cx + ring_r, ring_cy + ring_r], outline=BRASS_BRIGHT, width=9)
d.ellipse([ring_cx - 6, ring_cy - 6, ring_cx + 6, ring_cy + 6], fill=BRASS_BRIGHT)

needle_len = ring_r + 34
angle = math.radians(-35)
x1 = ring_cx - math.cos(angle) * needle_len
y1 = ring_cy - math.sin(angle) * needle_len
x2 = ring_cx + math.cos(angle) * needle_len
y2 = ring_cy + math.sin(angle) * needle_len
d.line([x1, y1, x2, y2], fill=BRASS_BRIGHT, width=7)

for i in range(12):
    a = math.radians(i * 30)
    x1 = ring_cx + math.cos(a) * (ring_r - 14)
    y1 = ring_cy + math.sin(a) * (ring_r - 14)
    x2 = ring_cx + math.cos(a) * (ring_r - 4)
    y2 = ring_cy + math.sin(a) * (ring_r - 4)
    d.line([x1, y1, x2, y2], fill=BRASS, width=3)

os.makedirs("resources/icons", exist_ok=True)
img.save("resources/icons/app.png")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save("resources/icons/app.ico", sizes=sizes)
print("Icon written to resources/icons/app.ico")