"""Reference-image rotation snapping (ReferenceImageItem._update_handle_drag()'s
"rotate" branch): a default (no-modifier) drag magnetically catches the
nearest cardinal orientation (0/90/180/270) when already close to it --
squaring up a photo is common enough to deserve a snap-into-place feel
without requiring Shift, the same "on by default, Alt bypasses" posture
_snap_position() already uses for position dragging. Shift's existing
hard 15°-grid snap (ROTATION_SNAP_DEG) is unchanged and tested here too,
as a regression guard -- there was previously no direct test of
_update_handle_drag()'s rotate branch at all, only of setRotation()
called directly (test_undo_commands.py), which bypasses this logic
entirely.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.layers.reference_layer import ReferenceImageItem
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def _add_exact_item(scene, natural_w: float, natural_h: float, pos: QPointF) -> ReferenceImageItem:
    pixmap = QPixmap(round(natural_w), round(natural_h))
    item = ReferenceImageItem(f"test-{id(pixmap)}", pixmap, natural_w, natural_h)
    item.setPos(pos)
    scene.reference_layer.addToGroup(item)
    return item


class _FakeMouseEvent:
    def __init__(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier = Qt.NoModifier):
        self._scene_pos = scene_pos
        self._modifiers = modifiers

    def scenePos(self) -> QPointF:
        return self._scene_pos

    def modifiers(self) -> Qt.KeyboardModifier:
        return self._modifiers


def _scene_pos_at_angle(center: QPointF, angle_deg: float, radius: float = 100.0) -> QPointF:
    """A scene point at `angle_deg` around `center`, using the same
    atan2(dx, -dy) convention _begin_handle_drag()/_update_handle_drag()
    measure the rotate handle's angle with (0° = straight up).
    """
    theta = math.radians(angle_deg)
    return QPointF(center.x() + radius * math.sin(theta), center.y() - radius * math.cos(theta))


def _drag_rotate_to(item: ReferenceImageItem, angle_deg: float, modifiers=Qt.NoModifier) -> float:
    """Resets the item to rotation 0, then starts a fresh rotate-handle
    drag at angle 0 (so the press-time mouse angle is a known baseline)
    and updates it to `angle_deg`, returning the item's resulting
    rotation. The reset matters because each call is meant to be an
    independent "drag from level" scenario, not a continuation of
    whatever a previous call in the same test left the item's rotation at
    -- _begin_handle_drag() captures the *current* rotation as its own
    baseline, so without resetting, a second call in the same test would
    silently compound onto the first call's result instead of starting
    fresh.
    """
    item.setRotation(0)
    center = item.mapToScene(QPointF(0, 0))
    item._begin_handle_drag("rotate", _scene_pos_at_angle(center, 0))
    item._update_handle_drag(_FakeMouseEvent(_scene_pos_at_angle(center, angle_deg), modifiers))
    return item.rotation()


def test_default_drag_snaps_to_90_when_close(qapp):
    scene = _scene(qapp)
    item = _add_exact_item(scene, 100, 100, QPointF(0, 0))

    assert _drag_rotate_to(item, 88.0) == 90.0
    assert _drag_rotate_to(item, 92.0) == 90.0


def test_default_drag_snaps_to_0_when_close(qapp):
    scene = _scene(qapp)
    item = _add_exact_item(scene, 100, 100, QPointF(0, 0))

    assert _drag_rotate_to(item, 3.0) == 0.0
    assert _drag_rotate_to(item, -3.0) == 0.0


def test_default_drag_snaps_to_180_and_270_when_close(qapp):
    scene = _scene(qapp)
    item = _add_exact_item(scene, 100, 100, QPointF(0, 0))

    # atan2's range is (-180, 180], so a mouse angle just past 180° comes
    # back as e.g. -178° rather than 182° -- snapping that to -180.0 is
    # exactly as correct as +180.0 (the same visual orientation either
    # way, a full half-turn); % 360 normalizes both to compare cleanly.
    assert _drag_rotate_to(item, 182.0) % 360 == 180.0
    assert _drag_rotate_to(item, 268.0) % 360 == 270.0


def test_default_drag_stays_free_outside_the_magnetic_threshold(qapp):
    scene = _scene(qapp)
    item = _add_exact_item(scene, 100, 100, QPointF(0, 0))

    assert _drag_rotate_to(item, 84.0) == 84.0
    assert _drag_rotate_to(item, 40.0) == 40.0


def test_alt_bypasses_the_magnetic_snap(qapp):
    scene = _scene(qapp)
    item = _add_exact_item(scene, 100, 100, QPointF(0, 0))

    assert _drag_rotate_to(item, 88.0, modifiers=Qt.AltModifier) == 88.0


def test_shift_still_hard_snaps_to_the_15_degree_grid(qapp):
    """Regression guard for the pre-existing Shift behavior -- unchanged
    by the new default magnetic snap, and independent of it (82° isn't
    close enough to 90 for the *default* magnetic snap to catch, but
    Shift's grid still rounds it to the nearest 15° multiple, 75).
    """
    scene = _scene(qapp)
    item = _add_exact_item(scene, 100, 100, QPointF(0, 0))

    assert _drag_rotate_to(item, 82.0, modifiers=Qt.ShiftModifier) == 75.0
    assert _drag_rotate_to(item, 88.0, modifiers=Qt.ShiftModifier) == 90.0
