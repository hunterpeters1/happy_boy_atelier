"""Pure geometry for corner-drag resize of reference images — deliberately
Qt-free so the trickiest new math in this feature can be unit tested
without a QApplication (see tests/test_resize_math.py).

The model: an item's local origin is always the *center* of its unscaled
bounding box (see ReferenceImageItem.natural_size()/boundingRect()), and
rotation/scale apply around that origin. Dragging a corner handle should
behave the way every other resize handle in every other creative tool
behaves: the *opposite* corner stays fixed in scene space, and the near
corner follows the cursor (subject to the min/max scale clamp and, when
proportions are locked, to the aspect ratio captured at the start of the
drag).

Because the item can be rotated, "follows the cursor" has to be resolved
in the item's own (rotated) local axes, not screen axes — otherwise
dragging a corner of a rotated image would skew it sideways instead of
resizing it along its own edges.
"""

from __future__ import annotations

import math

Vec2 = tuple[float, float]


def _rotate(v: Vec2, degrees: float) -> Vec2:
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    x, y = v
    return (x * c - y * s, x * s + y * c)


def compute_corner_resize(
    anchor: Vec2,
    cursor: Vec2,
    drag_sign: Vec2,
    half_size: Vec2,
    rotation_deg: float,
    press_scale: Vec2,
    locked: bool,
    min_scale: float = 0.05,
    max_scale: float = 40.0,
) -> tuple[Vec2, float, float]:
    """Given a corner-drag interaction, return the new (center, scale_x,
    scale_y) that keeps the opposite corner exactly fixed at `anchor`.

    - `anchor`: scene position of the corner NOT being dragged (opposite
      the one under the cursor). Captured once at mouse-press time.
    - `cursor`: current scene position of the mouse.
    - `drag_sign`: (+/-1, +/-1) identifying which corner is being
      dragged, e.g. (1, 1) for the bottom-right corner.
    - `half_size`: (half_w, half_h) of the item's *unscaled* natural
      size — natural_size() / 2. Constant through the drag (crop doesn't
      change during a resize).
    - `rotation_deg`: the item's current rotation. Constant through the
      drag (rotation and resize are separate handles).
    - `press_scale`: (scale_x, scale_y) captured at mouse-press time —
      used as the aspect-ratio reference when `locked` is True.
    - `locked`: True to preserve the press-time aspect ratio (typically
      the Shift-held case); False for free/independent resize.

    Returns ((new_center_x, new_center_y), new_scale_x, new_scale_y).
    """
    sign_x, sign_y = drag_sign
    hw = max(half_size[0], 1e-6)
    hh = max(half_size[1], 1e-6)
    sx_press, sy_press = press_scale

    ax, ay = anchor
    px, py = cursor
    # Vector from the fixed anchor to the cursor, rotated back into the
    # item's own (unrotated) local axes, halved because both the anchor
    # and the dragged corner move by half of any size change relative to
    # the center.
    local_delta = _rotate((px - ax, py - ay), -rotation_deg)
    d = (local_delta[0] / 2.0, local_delta[1] / 2.0)

    if locked:
        press_half_vec = (sign_x * hw * sx_press, sign_y * hh * sy_press)
        press_mag = math.hypot(*press_half_vec)
        cur_mag = math.hypot(*d)
        ratio = (cur_mag / press_mag) if press_mag > 1e-9 else 1.0
        new_sx = sx_press * ratio
        new_sy = sy_press * ratio
    else:
        new_sx = (d[0] / (sign_x * hw)) if sign_x != 0 else sx_press
        new_sy = (d[1] / (sign_y * hh)) if sign_y != 0 else sy_press

    new_sx = max(min_scale, min(max_scale, new_sx))
    new_sy = max(min_scale, min(max_scale, new_sy))

    # Recompute the center from the (possibly clamped) new scale, rather
    # than from the raw cursor position, so the anchor corner stays
    # *exactly* fixed even when clamping kicks in.
    half_vec_local = (sign_x * hw * new_sx, sign_y * hh * new_sy)
    half_vec_scene = _rotate(half_vec_local, rotation_deg)
    new_center = (ax + half_vec_scene[0], ay + half_vec_scene[1])

    return new_center, new_sx, new_sy
