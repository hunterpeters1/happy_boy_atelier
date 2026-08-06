"""`.atelier` container I/O and export (PNG / JPG / PDF planning sheet).

A `.atelier` file is a zip archive:

    manifest.json        canvas spec + every layer's serialized data
    images/<id>.png       one file per embedded reference image
    thumb.png             cached preview thumbnail

Images are always embedded — never referenced by external path — so a
`.atelier` file is fully self-contained and portable.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QGraphicsScene

MANIFEST_NAME = "manifest.json"
THUMB_NAME = "thumb.png"
IMAGES_DIR = "images"


class AtelierIOError(RuntimeError):
    pass


def save_atelier(path: str | Path, manifest: dict, images: dict[str, bytes],
                  thumbnail: QImage | None = None) -> None:
    """Write a project to `path`.

    `images` maps reference-image id -> already-encoded PNG bytes.
    """
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
        for image_id, png_bytes in images.items():
            zf.writestr(f"{IMAGES_DIR}/{image_id}.png", png_bytes)
        if thumbnail is not None and not thumbnail.isNull():
            zf.writestr(THUMB_NAME, _qimage_to_png_bytes(thumbnail))

    tmp_path.replace(path)


def load_atelier(path: str | Path) -> tuple[dict, dict[str, bytes]]:
    """Read a project from `path`.

    Returns (manifest, images) where images maps id -> raw PNG bytes.
    """
    path = Path(path)
    if not path.exists():
        raise AtelierIOError(f"No such file: {path}")

    images: dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as zf:
        try:
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        except KeyError as exc:
            raise AtelierIOError("Not a valid .atelier file (missing manifest)") from exc

        for name in zf.namelist():
            if name.startswith(f"{IMAGES_DIR}/") and name.endswith(".png"):
                image_id = Path(name).stem
                images[image_id] = zf.read(name)

    return manifest, images


def _qimage_to_png_bytes(image: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def render_scene_to_image(scene: QGraphicsScene, source_rect: QRectF,
                           dpi: int = 300, px_per_inch: float = 100.0) -> QImage:
    """Render `source_rect` (in scene units, where `px_per_inch` scene units
    equal one physical inch) to a raster image at the requested output DPI.
    """
    inches_w = source_rect.width() / px_per_inch
    inches_h = source_rect.height() / px_per_inch
    out_w = max(1, round(inches_w * dpi))
    out_h = max(1, round(inches_h * dpi))

    image = QImage(out_w, out_h, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.white)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    scene.render(painter, QRectF(0, 0, out_w, out_h), source_rect)
    painter.end()
    return image


def export_png(scene: QGraphicsScene, source_rect: QRectF, path: str | Path,
                dpi: int = 300, px_per_inch: float = 100.0) -> None:
    image = render_scene_to_image(scene, source_rect, dpi, px_per_inch)
    if not image.save(str(path), "PNG"):
        raise AtelierIOError(f"Failed to write PNG: {path}")


def export_jpg(scene: QGraphicsScene, source_rect: QRectF, path: str | Path,
               dpi: int = 300, px_per_inch: float = 100.0, quality: int = 92) -> None:
    image = render_scene_to_image(scene, source_rect, dpi, px_per_inch)
    if not image.save(str(path), "JPG", quality):
        raise AtelierIOError(f"Failed to write JPG: {path}")


def export_pdf_planning_sheet(scene: QGraphicsScene, source_rect: QRectF,
                               path: str | Path, canvas_label: str,
                               notes: list[str], px_per_inch: float = 100.0) -> None:
    """A single-page PDF: the rendered canvas plus a printed list of notes,
    meant to be brought to the easel alongside the physical canvas.
    """
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setResolution(300)

    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    page_rect = painter.viewport()
    margin = int(page_rect.width() * 0.06)
    content_rect = page_rect.adjusted(margin, margin, -margin, -margin)

    title_h = int(content_rect.height() * 0.05)
    painter.setPen(Qt.black)
    font = painter.font()
    font.setPointSize(16)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(content_rect.x(), content_rect.y(), content_rect.width(),
                      title_h, Qt.AlignLeft | Qt.AlignVCenter, canvas_label)

    canvas_area_h = int(content_rect.height() * 0.62)
    canvas_top = content_rect.y() + title_h + 10
    canvas_rect = QRectF(content_rect.x(), canvas_top, content_rect.width(), canvas_area_h)

    # fit source_rect (aspect-correct) inside canvas_rect
    src_w, src_h = source_rect.width(), source_rect.height()
    scale = min(canvas_rect.width() / src_w, canvas_rect.height() / src_h)
    fit_w, fit_h = src_w * scale, src_h * scale
    fit_x = canvas_rect.x() + (canvas_rect.width() - fit_w) / 2
    fit_y = canvas_rect.y() + (canvas_rect.height() - fit_h) / 2
    fit_rect = QRectF(fit_x, fit_y, fit_w, fit_h)

    painter.setPen(Qt.black)
    painter.drawRect(fit_rect)
    scene.render(painter, fit_rect, source_rect)

    notes_top = canvas_rect.y() + canvas_rect.height() + 24
    font.setPointSize(12)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(content_rect.x(), int(notes_top), content_rect.width(), 20,
                      Qt.AlignLeft, "Notes")

    font.setPointSize(10)
    font.setBold(False)
    painter.setFont(font)
    line_h = 18
    y = int(notes_top) + 26
    for note in notes:
        painter.drawText(content_rect.x(), y, content_rect.width(), line_h,
                          Qt.AlignLeft | Qt.TextWordWrap, f"• {note}")
        y += line_h

    painter.end()
