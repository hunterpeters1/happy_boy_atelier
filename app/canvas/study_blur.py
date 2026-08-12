"""Pure-numpy image processing for the reference-image "Study Blur" and
"Value Check" features: blur the image (a painter's classic squint-test
for judging overall shapes/values without being distracted by fine
detail) while boosting the local contrast of dark lines/edges so they
stay legible even at very low contrast, instead of getting washed out by
the blur; and non-destructively desaturate toward luminance for judging
value relationships without color as a confound. No QGraphicsItem/widget
coupling — mirrors canvas/resize_math.py's pattern of independently-
testable pure logic kept separate from the Qt item classes that use it
(see layers/reference_layer.py).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)
# Luminance-delta units (0-255 scale) at which a dark edge reaches ~63%
# mask strength — small on purpose, so even a subtle line reads as "a
# line worth protecting from the blur," not just strong contours.
_EDGE_SENSITIVITY = 4.0
# How many multiples of the raw edge signal to darken by at full mask
# strength — deliberately > 1 so a confidently-detected line lands
# noticeably past its original darkness, not merely back at it.
_EDGE_DARKEN_BOOST = 2.2


def _qimage_to_array(image: QImage) -> np.ndarray:
    """RGBA8888 uint8 array, shape (h, w, 4) — always a copy, detached
    from the QImage's own buffer lifetime.
    """
    image = image.convertToFormat(QImage.Format_RGBA8888)
    w, h, stride = image.width(), image.height(), image.bytesPerLine()
    buf = np.frombuffer(image.bits(), dtype=np.uint8).reshape(h, stride)
    return buf[:, : w * 4].reshape(h, w, 4).copy()


def _array_to_qimage(arr: np.ndarray) -> QImage:
    h, w = arr.shape[:2]
    arr = np.ascontiguousarray(arr)
    image = QImage(arr.data, w, h, w * 4, QImage.Format_RGBA8888)
    # .copy() so the returned QImage owns its own buffer — `arr` (and the
    # memory QImage's constructor points into) is a local that would
    # otherwise be garbage-collected out from under it.
    return image.copy()


def _box_blur(image: np.ndarray, radius: int) -> np.ndarray:
    """Box blur via a 2D integral image (cumulative-sum trick) — O(H*W)
    regardless of radius, no scipy dependency. `image` is (H, W) or
    (H, W, C) float32 — all channels are blurred in one vectorized pass
    rather than looping per-channel in Python, which matters at this
    array size (measured ~3x faster for 3 channels than calling this
    once per channel). Edge pixels are extended (not zero-padded) so the
    blur doesn't darken toward the image border.
    """
    if radius <= 0:
        return image
    extra_dims = image.ndim - 2
    pad_width = ((radius, radius), (radius, radius)) + ((0, 0),) * extra_dims
    padded = np.pad(image, pad_width, mode="edge")
    integral = np.cumsum(np.cumsum(padded, axis=0), axis=1)
    zero_pad = ((1, 0), (1, 0)) + ((0, 0),) * extra_dims
    integral = np.pad(integral, zero_pad, mode="constant")
    size = 2 * radius + 1
    total = (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )
    return total / (size * size)


def apply_study_effect(
    image: QImage, blur_pct: float, clarity_pct: float, grayscale_pct: float = 0.0
) -> QImage:
    """blur_pct/clarity_pct/grayscale_pct: 0-100, matching the Properties
    panel sliders (and the existing opacity-slider convention elsewhere in
    this app). `(0, 0, 0)` returns `image` unchanged — a guaranteed fast
    no-op path so images nobody has adjusted pay zero processing cost.

    grayscale_pct lerps each pixel toward its own luminance -- a
    non-destructive "Value Check" desaturate -- applied *before*
    blur/clarity so a squint-test and a value-check can be judged on the
    same photo at once, sharing the one processed-pixmap cache
    ReferenceImageItem already maintains, rather than needing a second,
    independent effect pipeline.
    """
    blur_pct = max(0.0, min(100.0, blur_pct))
    clarity_pct = max(0.0, min(100.0, clarity_pct))
    grayscale_pct = max(0.0, min(100.0, grayscale_pct))
    if blur_pct <= 0 and clarity_pct <= 0 and grayscale_pct <= 0:
        return image

    arr = _qimage_to_array(image)
    rgb = arr[:, :, :3].astype(np.float32)
    h, w = rgb.shape[:2]
    short_edge = max(1, min(h, w))

    if grayscale_pct > 0:
        t = grayscale_pct / 100.0
        luminance = (rgb @ _LUMA)[:, :, None]
        rgb = rgb * (1 - t) + luminance * t

    # Radius scales with both the slider and the image's own size, so the
    # effect feels consistent across differently-sized crops rather than a
    # fixed pixel radius that's invisible on a huge photo and overwhelming
    # on a small one.
    blur_radius = int(round((blur_pct / 100.0) * short_edge * 0.03))
    if blur_radius > 0:
        blurred = _box_blur(rgb, blur_radius)
    else:
        blurred = rgb

    result = blurred
    if clarity_pct > 0:
        luminance = rgb @ _LUMA
        local_radius = max(1, round(short_edge * 0.01))
        local_avg = _box_blur(luminance, local_radius)
        # Positive wherever a pixel is darker than its immediate
        # surroundings — i.e. a dark line/edge. Zero (clipped) everywhere
        # else, including light-side edges, which this feature deliberately
        # leaves alone.
        dark_edge = np.clip(local_avg - luminance, 0, None)
        # Absolute soft threshold, not peak-relative: a handful of
        # luminance units of "darker than surroundings" already saturates
        # most of the way to full mask strength, regardless of whatever
        # the single strongest edge elsewhere in the photo happens to be.
        # A peak-relative normalization would make a faint line's boost
        # depend on how strong OTHER edges in the same image are, which
        # directly undermines "ensure lines show up if darkness is very
        # low" for photos that also contain strong shadow edges.
        edge_signal = 1.0 - np.exp(-dark_edge / _EDGE_SENSITIVITY, dtype=np.float32)
        mask = np.clip(edge_signal * (clarity_pct / 100.0), 0.0, 1.0)[:, :, None]
        # Blend toward a further-darkened version of the ORIGINAL sharp
        # pixel at dark-edge locations, rather than subtracting a delta
        # from the already-blurred value — a delta has to first overcome
        # how much the blur itself softened that pixel before it can
        # restore any contrast, which left lines murkier, not clearer.
        # Blending guarantees a confidently-detected edge (mask -> 1)
        # lands past the crisp original, not just back at it.
        darkened_original = np.clip(rgb - dark_edge[:, :, None] * _EDGE_DARKEN_BOOST, 0, 255)
        result = blurred * (1 - mask) + darkened_original * mask

    result = np.clip(result, 0, 255).astype(np.uint8)
    out = np.dstack([result, arr[:, :, 3]])
    return _array_to_qimage(out)
