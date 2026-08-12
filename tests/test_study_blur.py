"""Correctness tests for the pure-numpy Study Blur image-processing
function (app/canvas/study_blur.py) — isolated from ReferenceImageItem/Qt
widget code entirely, same spirit as test_resize_math.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QImage

from app.canvas.study_blur import apply_study_effect


def _solid_image(w: int, h: int, color: QColor) -> QImage:
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(color)
    return img


def _line_image(delta: int) -> QImage:
    """120x120 mid-gray field with a single horizontal line `delta`
    luminance units darker than the background at row 60.
    """
    img = _solid_image(120, 120, QColor(180, 180, 180, 255))
    line_color = QColor(180 - delta, 180 - delta, 180 - delta, 255)
    for x in range(120):
        img.setPixelColor(x, 60, line_color)
    return img


def _line_contrast(image: QImage) -> int:
    """Background sample (far from the line) minus the line's own value —
    how visually distinct the line still is.
    """
    return image.pixelColor(60, 30).red() - image.pixelColor(60, 60).red()


def test_zero_amounts_is_a_noop(qapp):
    img = _solid_image(40, 40, QColor(200, 200, 200, 255))
    out = apply_study_effect(img, 0, 0)
    assert out is img


def test_output_dimensions_match_input(qapp):
    img = _solid_image(37, 53, QColor(100, 100, 100, 255))  # odd, non-square
    out = apply_study_effect(img, blur_pct=40, clarity_pct=30)
    assert out.width() == img.width()
    assert out.height() == img.height()


def test_blur_alone_softens_a_hard_edge(qapp):
    img = _line_image(delta=40)
    before = _line_contrast(img)
    blurred_only = apply_study_effect(img, blur_pct=60, clarity_pct=0)
    after = _line_contrast(blurred_only)
    assert after < before


def test_high_clarity_makes_faint_lines_more_visible_than_original(qapp):
    """The concrete, testable form of "ensure lines show up even if
    darkness is very low": across several very-faint-to-moderate line
    contrasts, a high Line Clarity setting must leave the line more
    distinct than it was in the untouched original — not just less
    washed-out than a plain blur, but actually enhanced.
    """
    for delta in (5, 10, 15, 30):
        img = _line_image(delta)
        before = _line_contrast(img)
        processed = apply_study_effect(img, blur_pct=50, clarity_pct=90)
        after = _line_contrast(processed)
        assert after > before, f"delta={delta}: expected {after} > {before}"


def test_clarity_beats_plain_blur_at_every_faintness(qapp):
    """Whatever the clarity mechanism does, it should never leave a dark
    line *less* visible than plain blur alone would.
    """
    for delta in (5, 10, 15, 30):
        img = _line_image(delta)
        blurred_only = _line_contrast(apply_study_effect(img, blur_pct=50, clarity_pct=0))
        with_clarity = _line_contrast(apply_study_effect(img, blur_pct=50, clarity_pct=90))
        assert with_clarity > blurred_only


def test_clarity_effect_is_monotonic_with_slider_value(qapp):
    img = _line_image(delta=12)
    contrasts = [
        _line_contrast(apply_study_effect(img, blur_pct=50, clarity_pct=c))
        for c in (0, 25, 50, 75, 100)
    ]
    assert contrasts == sorted(contrasts)


def test_alpha_channel_is_preserved(qapp):
    img = _solid_image(30, 30, QColor(120, 60, 200, 128))
    out = apply_study_effect(img, blur_pct=50, clarity_pct=50)
    assert out.pixelColor(15, 15).alpha() == 128


# -- Value Check (grayscale_pct) --------------------------------------------

def test_zero_grayscale_is_still_a_noop(qapp):
    img = _solid_image(40, 40, QColor(200, 100, 50, 255))
    out = apply_study_effect(img, blur_pct=0, clarity_pct=0, grayscale_pct=0)
    assert out is img


def test_full_grayscale_produces_equal_rgb_channels(qapp):
    img = _solid_image(30, 30, QColor(220, 40, 40, 255))
    out = apply_study_effect(img, blur_pct=0, clarity_pct=0, grayscale_pct=100)
    c = out.pixelColor(15, 15)
    assert c.red() == c.green() == c.blue()


def test_partial_grayscale_is_between_original_and_full(qapp):
    img = _solid_image(30, 30, QColor(220, 40, 40, 255))
    original_spread = 220 - 40  # red channel minus green/blue
    half = apply_study_effect(img, blur_pct=0, clarity_pct=0, grayscale_pct=50).pixelColor(15, 15)
    half_spread = half.red() - half.green()
    assert 0 < half_spread < original_spread


def test_grayscale_composes_with_blur_and_clarity(qapp):
    """The three effects share one pass (see apply_study_effect's
    docstring) -- confirm turning all three on at once doesn't raise and
    still desaturates.
    """
    img = _line_image(delta=20)
    out = apply_study_effect(img, blur_pct=40, clarity_pct=40, grayscale_pct=100)
    c = out.pixelColor(10, 10)
    assert c.red() == c.green() == c.blue()


def test_grayscale_alpha_channel_is_preserved(qapp):
    img = _solid_image(30, 30, QColor(120, 60, 200, 128))
    out = apply_study_effect(img, blur_pct=0, clarity_pct=0, grayscale_pct=100)
    assert out.pixelColor(15, 15).alpha() == 128
