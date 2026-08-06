""".atelier save/load round-trip tests, including embedded image bytes.

Needs QImage (hence the qapp fixture, since even headless/offscreen Qt
wants an application instance to exist first) but not a full GUI event
loop — no widgets, windows, or QGraphicsScene involved here.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.atelier_io import AtelierIOError, load_atelier, save_atelier
from app.project import CanvasSpec, ProjectMeta, empty_manifest


def _sample_png_bytes(color: str = "#c9482f", size: tuple[int, int] = (4, 4)) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(size[0], size[1], QImage.Format_ARGB32)
    image.fill(QColor(color))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def test_atelier_round_trip_without_images(tmp_path, qapp):
    spec = CanvasSpec(name="Still Life", width=11.0, height=14.0, unit="in")
    meta = ProjectMeta()
    manifest = empty_manifest(spec, meta)

    path = tmp_path / "project.atelier"
    save_atelier(path, manifest, {})
    assert path.exists()

    loaded_manifest, loaded_images = load_atelier(path)
    assert loaded_manifest["canvas"] == manifest["canvas"]
    assert loaded_manifest["format_version"] == manifest["format_version"]
    assert loaded_images == {}


def test_atelier_round_trip_with_embedded_image(tmp_path, qapp):
    spec = CanvasSpec()
    meta = ProjectMeta()
    manifest = empty_manifest(spec, meta)
    manifest["references"] = [
        {"id": "abc123", "x": 12.0, "y": -4.0, "rotation": 15.0, "scale": 1.0,
         "crop": [0, 0, 4, 4], "image": "images/abc123.png"},
    ]

    png_bytes = _sample_png_bytes()
    images = {"abc123": png_bytes}

    path = tmp_path / "with_image.atelier"
    save_atelier(path, manifest, images)

    loaded_manifest, loaded_images = load_atelier(path)
    assert loaded_manifest["references"] == manifest["references"]
    assert loaded_images.keys() == images.keys()
    assert loaded_images["abc123"] == png_bytes


def test_save_atelier_is_atomic_tmp_file_not_left_behind(tmp_path, qapp):
    # save_atelier writes to a .tmp file and replaces the target so a
    # crash mid-write can't leave a half-written .atelier file in place
    # (also exercised indirectly by the autosave recovery path).
    manifest = empty_manifest(CanvasSpec(), ProjectMeta())
    path = tmp_path / "project.atelier"
    save_atelier(path, manifest, {})

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    assert path.exists()


def test_load_atelier_missing_file_raises(tmp_path):
    with pytest.raises(AtelierIOError):
        load_atelier(tmp_path / "does_not_exist.atelier")


def test_load_atelier_missing_manifest_raises(tmp_path):
    path = tmp_path / "corrupt.atelier"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("not_a_manifest.txt", "oops")

    with pytest.raises(AtelierIOError):
        load_atelier(path)
