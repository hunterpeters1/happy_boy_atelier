"""A personal, cross-project reference-image library — explicitly *not*
part of any single project's scene or `.atelier` file (see
`app/panels/library_panel.py`), so importing from it can never become a
second source of truth for project content; dragging an item onto the
canvas is a normal import that becomes an ordinary
`ReferenceImageItem`/`AddItemCommand`, indistinguishable afterward from
one imported any other way.

Images live in a flat folder under `QStandardPaths`' app-data directory —
the same pattern `app/recovery.py` already uses for its own autosave
slot — with a lightweight JSON index (name/tags) alongside them and a
small persisted thumbnail per image, generated once at import time, so
opening the panel doesn't mean re-decoding every full-resolution source
photo on every launch.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QPixmap

from . import resources

# Matches CanvasView._IMAGE_EXTENSIONS / MainWindow.import_images()'s file
# dialog filter -- a library item must be something the canvas can
# actually accept back, since drag-out reuses that exact drop path.
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
THUMBNAIL_MAX_DIM = 160

_INDEX_FILENAME = "index.json"
_IMAGES_DIRNAME = "images"
_THUMBS_DIRNAME = "thumbnails"


def library_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        # Extremely unlikely fallback — QStandardPaths always returns
        # something once QApplication exists — but never crash the app
        # over a missing library directory.
        base = str(Path.home() / ".happy_boy_atelier")
    return Path(base) / "reference_library"


@dataclass
class LibraryItem:
    id: str
    filename: str
    name: str
    tags: list[str] = field(default_factory=list)
    # The uploader's own filename (e.g. "20260813-172233-abc123.jpg") for an
    # item that arrived via sync_from_uploader(), None for everything else
    # (manually added images, and every pre-existing library entry from
    # before this field existed). Exists purely so a re-scan of the
    # uploader's photos/ folder can tell "already imported" from "new"
    # without re-copying/re-thumbnailing a file every poll tick.
    uploaded_from: str | None = None

    def image_path(self) -> Path:
        return library_dir() / _IMAGES_DIRNAME / self.filename

    def thumbnail_path(self) -> Path:
        return library_dir() / _THUMBS_DIRNAME / f"{self.id}.png"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "filename": self.filename, "name": self.name, "tags": list(self.tags),
            "uploaded_from": self.uploaded_from,
        }

    @staticmethod
    def from_dict(d: dict) -> "LibraryItem":
        return LibraryItem(
            id=d["id"], filename=d["filename"], name=d.get("name", d.get("filename", "")),
            tags=list(d.get("tags", [])), uploaded_from=d.get("uploaded_from"),
        )


def _index_path() -> Path:
    return library_dir() / _INDEX_FILENAME


def _load_index() -> list[LibraryItem]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []  # a corrupt index is treated as empty, never a crash
    return [LibraryItem.from_dict(d) for d in data.get("items", [])]


def _save_index(items: list[LibraryItem]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": [i.to_dict() for i in items]}, indent=2), encoding="utf-8")


def list_items() -> list[LibraryItem]:
    return _load_index()


def _make_thumbnail(source_path: Path, dest_path: Path) -> None:
    pixmap = QPixmap(str(source_path))
    if pixmap.isNull():
        return
    thumb = pixmap.scaled(
        THUMBNAIL_MAX_DIM, THUMBNAIL_MAX_DIM, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(str(dest_path), "PNG")


def add_image(
    source_path: Path, display_name: str | None = None, uploaded_from: str | None = None,
) -> LibraryItem | None:
    """Copy `source_path` into the library folder (original pixels, never
    linked — matches the ".atelier files never link external files" rule
    elsewhere in this app) and generate its thumbnail immediately, not
    lazily — the library panel's job is showing a fast grid, not decoding
    full-resolution photos every time it opens. Returns None (does
    nothing) for an unsupported extension or an unreadable source file,
    same "skip, don't crash" posture as `MainWindow._import_image_paths()`.

    `uploaded_from` is set only by sync_from_uploader() below — see
    LibraryItem's own docstring for what it's for.
    """
    source_path = Path(source_path)
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None
    if QPixmap(str(source_path)).isNull():
        return None

    item_id = str(uuid.uuid4())
    filename = f"{item_id}{source_path.suffix.lower()}"
    item = LibraryItem(
        id=item_id, filename=filename, name=display_name or source_path.stem,
        uploaded_from=uploaded_from,
    )

    images_dir = library_dir() / _IMAGES_DIRNAME
    images_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, images_dir / filename)
    _make_thumbnail(item.image_path(), item.thumbnail_path())

    items = _load_index()
    items.append(item)
    _save_index(items)
    return item


def uploader_photos_dir() -> Path:
    """Where uploader/app.py (the standalone phone-upload tool, see its
    own module docstring) saves incoming photos — not anything
    Qt-specific, since the uploader deliberately has no PySide6
    dependency of its own and can't compute (or even know about) this
    app's QStandardPaths-based library_dir(). See resources.uploader_root()
    for why this isn't simply resource_path("uploader", "photos").
    """
    return Path(resources.uploader_root()) / "photos"


def sync_from_uploader() -> list[LibraryItem]:
    """Pull any phone-uploaded photos not yet in the library into it, the
    same way a manual "Add Images to Library…" click would. Safe to call
    repeatedly/on a timer (see LibraryPanel) — an upload already imported
    is recognized by its uploader filename (LibraryItem.uploaded_from) and
    skipped, so this never re-copies or re-thumbnails the same photo.
    Returns only the newly-added items, so a caller can tell "nothing
    changed" from "the library grew" without a second list_items() diff.
    """
    photos_dir = uploader_photos_dir()
    if not photos_dir.is_dir():
        return []

    already_synced = {item.uploaded_from for item in _load_index() if item.uploaded_from}
    new_items = []
    for path in sorted(photos_dir.iterdir()):
        if not path.is_file() or path.name in already_synced:
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        item = add_image(path, display_name=path.stem, uploaded_from=path.name)
        if item is not None:
            new_items.append(item)
    return new_items


def remove_item(item_id: str) -> None:
    items = _load_index()
    keep = [i for i in items if i.id != item_id]
    removed = [i for i in items if i.id == item_id]
    _save_index(keep)
    for item in removed:
        for path in (item.image_path(), item.thumbnail_path()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # best-effort, same posture as recovery.delete_recovery_file()
