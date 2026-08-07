"""ReferenceImageItem metadata (file name/format/size) capture and
round-trip, plus the perspective layer's default-hidden state for a
brand-new project.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap

from app.canvas.canvas_scene import CanvasScene
from app.layers.reference_layer import ReferenceImageItem
from app.project import CanvasSpec


def _scene(qapp) -> CanvasScene:
    return CanvasScene(CanvasSpec())


def test_reference_image_metadata_round_trips_through_to_dict(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(
        pixmap, 500, 500, QPointF(0, 0), display_name="photo.jpg",
        original_format="JPG", original_file_size=123456,
    )

    d = item.to_dict()
    assert d["original_format"] == "JPG"
    assert d["original_file_size"] == 123456

    restored = ReferenceImageItem.from_dict(d, pixmap)
    assert restored.original_format == "JPG"
    assert restored.original_file_size == 123456
    assert restored.display_name == "photo.jpg"


def test_reference_image_metadata_missing_from_legacy_dict_falls_back_to_none(qapp):
    scene = _scene(qapp)
    pixmap = QPixmap(50, 50)
    item = scene.reference_layer.add_image(pixmap, 500, 500, QPointF(0, 0), display_name="old.png")
    d = item.to_dict()
    d.pop("original_format")
    d.pop("original_file_size")

    restored = ReferenceImageItem.from_dict(d, pixmap)
    assert restored.original_format is None
    assert restored.original_file_size is None


def test_perspective_layer_hidden_by_default_on_a_new_scene(qapp):
    scene = _scene(qapp)
    assert scene.perspective_layer.isVisible() is False
