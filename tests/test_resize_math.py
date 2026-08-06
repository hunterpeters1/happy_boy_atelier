"""Corner-drag resize math (app/canvas/resize_math.py) — pure Python, no
Qt dependency, so this runs anywhere PySide6 isn't installed.

The one property that must hold in every case, rotated or not, locked or
free, clamped or not: the anchor corner (the one *not* being dragged)
never moves. That's the whole point of anchoring the resize there instead
of at the center, and it's the thing most likely to break silently if the
rotation math is ever off by a sign or a transpose.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.canvas.resize_math import compute_corner_resize


def _corner_scene_pos(center, half_size, sign, scale, rotation_deg):
    """Reference implementation of "where is corner `sign` in scene
    space", independent of compute_corner_resize, used only to verify the
    anchor-stays-fixed invariant from first principles.
    """
    hw, hh = half_size
    sx, sy = scale
    sign_x, sign_y = sign
    local = (sign_x * hw * sx, sign_y * hh * sy)
    a = math.radians(rotation_deg)
    c, s = math.cos(a), math.sin(a)
    rotated = (local[0] * c - local[1] * s, local[0] * s + local[1] * c)
    return (center[0] + rotated[0], center[1] + rotated[1])


def _approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def _approx_point(p, q, tol=1e-6):
    return _approx(p[0], q[0], tol) and _approx(p[1], q[1], tol)


# -- anchor invariant, across rotation/lock/clamp combinations ------------------

def test_anchor_stays_fixed_no_rotation_free_resize():
    # 100x100 image (half=50,50) centered at origin, unscaled, unrotated.
    anchor = (-50.0, -50.0)   # top-left, opposite the dragged bottom-right corner
    cursor = (120.0, 80.0)    # drag the bottom-right corner out and to a new spot
    new_center, sx, sy = compute_corner_resize(
        anchor, cursor, drag_sign=(1, 1), half_size=(50, 50),
        rotation_deg=0.0, press_scale=(1.0, 1.0), locked=False,
    )
    anchor_after = _corner_scene_pos(new_center, (50, 50), (-1, -1), (sx, sy), 0.0)
    assert _approx_point(anchor_after, anchor)
    # Free resize: the dragged corner should land exactly on the cursor.
    dragged_after = _corner_scene_pos(new_center, (50, 50), (1, 1), (sx, sy), 0.0)
    assert _approx_point(dragged_after, cursor)


def test_anchor_stays_fixed_with_rotation():
    anchor = (10.0, 10.0)
    cursor = (200.0, 160.0)
    for rotation in (0.0, 30.0, 90.0, 137.0, -45.0, 359.0):
        new_center, sx, sy = compute_corner_resize(
            anchor, cursor, drag_sign=(1, -1), half_size=(80, 40),
            rotation_deg=rotation, press_scale=(1.2, 0.9), locked=False,
        )
        anchor_after = _corner_scene_pos(new_center, (80, 40), (-1, 1), (sx, sy), rotation)
        assert _approx_point(anchor_after, anchor, tol=1e-4), f"failed at rotation={rotation}"


def test_anchor_stays_fixed_when_locked_proportional():
    anchor = (0.0, 0.0)
    cursor = (300.0, 40.0)  # a very off-axis drag; locked mode must still preserve aspect
    for rotation in (0.0, 45.0, -60.0):
        new_center, sx, sy = compute_corner_resize(
            anchor, cursor, drag_sign=(1, 1), half_size=(50, 50),
            rotation_deg=rotation, press_scale=(1.0, 1.0), locked=True,
        )
        anchor_after = _corner_scene_pos(new_center, (50, 50), (-1, -1), (sx, sy), rotation)
        assert _approx_point(anchor_after, anchor, tol=1e-4)
        # Locked mode must preserve the press-time aspect ratio (1:1 here).
        assert _approx(sx, sy, tol=1e-6)


def test_anchor_stays_fixed_when_clamped():
    # Drag far enough to hit max_scale, and confirm the anchor is still
    # exactly fixed even though the raw cursor position would have
    # implied a larger scale than what actually gets applied.
    anchor = (-50.0, -50.0)
    cursor = (5000.0, 5000.0)
    new_center, sx, sy = compute_corner_resize(
        anchor, cursor, drag_sign=(1, 1), half_size=(50, 50),
        rotation_deg=20.0, press_scale=(1.0, 1.0), locked=False,
        max_scale=5.0,
    )
    assert sx == 5.0 and sy == 5.0  # actually clamped, not just close
    anchor_after = _corner_scene_pos(new_center, (50, 50), (-1, -1), (sx, sy), 20.0)
    assert _approx_point(anchor_after, anchor, tol=1e-4)


# -- free vs. locked resize actually differ -----------------------------------

def test_free_resize_allows_independent_axes():
    anchor = (-50.0, -50.0)
    cursor = (150.0, -20.0)  # stretch X a lot, barely move Y
    _, sx, sy = compute_corner_resize(
        anchor, cursor, drag_sign=(1, 1), half_size=(50, 50),
        rotation_deg=0.0, press_scale=(1.0, 1.0), locked=False,
    )
    assert not _approx(sx, sy, tol=0.05)  # genuinely non-uniform


def test_locked_resize_forces_equal_axes_even_for_off_axis_drag():
    anchor = (-50.0, -50.0)
    cursor = (150.0, -20.0)  # same off-axis drag as above
    _, sx, sy = compute_corner_resize(
        anchor, cursor, drag_sign=(1, 1), half_size=(50, 50),
        rotation_deg=0.0, press_scale=(1.0, 1.0), locked=True,
    )
    assert _approx(sx, sy, tol=1e-6)


# -- degenerate / no-op cases --------------------------------------------------

def test_no_drag_returns_press_scale_and_original_corner():
    # Cursor exactly at the original (unmoved) corner position should
    # reproduce the press-time scale almost exactly.
    half_size = (50.0, 50.0)
    press_scale = (1.3, 0.8)
    rotation = 15.0
    anchor = (-50.0 * press_scale[0], -50.0 * press_scale[1])
    # Rotate the anchor into scene space around an arbitrary center to
    # make this a non-trivial case.
    center = (40.0, -20.0)
    anchor_scene = _corner_scene_pos(center, half_size, (-1, -1), press_scale, rotation)
    original_corner_scene = _corner_scene_pos(center, half_size, (1, 1), press_scale, rotation)

    new_center, sx, sy = compute_corner_resize(
        anchor_scene, original_corner_scene, drag_sign=(1, 1), half_size=half_size,
        rotation_deg=rotation, press_scale=press_scale, locked=False,
    )
    assert _approx(sx, press_scale[0], tol=1e-4)
    assert _approx(sy, press_scale[1], tol=1e-4)
    assert _approx_point(new_center, center, tol=1e-4)
