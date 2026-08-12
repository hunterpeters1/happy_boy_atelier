"""app/library.py: the personal, cross-project reference-image library.
Pure filesystem/JSON logic, no Qt item/scene coupling beyond QPixmap for
thumbnail generation — same spirit as test_study_blur.py/test_resize_math.py.

QStandardPaths.setTestModeEnabled(True) redirects AppDataLocation into a
sandboxed .qttest folder rather than a real user's app-data directory
(the same directory app/recovery.py's autosave slot would otherwise
share) -- library_dir_tmp additionally wipes that folder before/after
each test, since the sandbox path is shared across the whole test
session (keyed by the org/app name conftest.py sets once), not isolated
per test on its own.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QColor, QPixmap

from app import library


@pytest.fixture
def library_dir_tmp(qapp):
    QStandardPaths.setTestModeEnabled(True)
    path = library.library_dir()
    shutil.rmtree(path, ignore_errors=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _make_source_image(tmp_path: Path, name: str = "photo.png", size=(300, 200)) -> Path:
    path = tmp_path / name
    pixmap = QPixmap(*size)
    pixmap.fill(QColor(50, 120, 200))
    pixmap.save(str(path), "PNG")
    return path


def test_fresh_library_is_empty(library_dir_tmp):
    assert library.list_items() == []


def test_add_image_copies_file_and_generates_thumbnail(library_dir_tmp, tmp_path):
    source = _make_source_image(tmp_path)

    item = library.add_image(source, display_name="My Photo")

    assert item is not None
    assert item.name == "My Photo"
    assert item.image_path().exists()
    assert item.image_path() != source  # a real copy, not a link
    assert item.thumbnail_path().exists()
    assert library.list_items() == [item]


def test_add_image_defaults_name_to_source_stem(library_dir_tmp, tmp_path):
    source = _make_source_image(tmp_path, name="sunset_beach.jpg")
    item = library.add_image(source)
    assert item.name == "sunset_beach"


def test_add_image_rejects_unsupported_extension(library_dir_tmp, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not an image")

    assert library.add_image(bad) is None
    assert library.list_items() == []


def test_add_image_rejects_unreadable_image_file(library_dir_tmp, tmp_path):
    fake = tmp_path / "corrupt.png"
    fake.write_bytes(b"not actually a png")

    assert library.add_image(fake) is None
    assert library.list_items() == []


def test_thumbnail_is_downscaled_and_preserves_aspect_ratio(library_dir_tmp, tmp_path):
    source = _make_source_image(tmp_path, size=(800, 400))
    item = library.add_image(source)

    thumb = QPixmap(str(item.thumbnail_path()))
    assert max(thumb.width(), thumb.height()) <= library.THUMBNAIL_MAX_DIM
    assert thumb.width() == thumb.height() * 2  # aspect ratio preserved (800:400 = 2:1)


def test_remove_item_deletes_files_and_index_entry(library_dir_tmp, tmp_path):
    source = _make_source_image(tmp_path)
    item = library.add_image(source)

    library.remove_item(item.id)

    assert library.list_items() == []
    assert not item.image_path().exists()
    assert not item.thumbnail_path().exists()


def test_index_persists_across_calls(library_dir_tmp, tmp_path):
    source_a = _make_source_image(tmp_path, name="a.png")
    source_b = _make_source_image(tmp_path, name="b.png")
    library.add_image(source_a, display_name="A")
    library.add_image(source_b, display_name="B")

    names = sorted(i.name for i in library.list_items())
    assert names == ["A", "B"]


def test_corrupt_index_file_is_treated_as_empty_not_a_crash(library_dir_tmp):
    library.library_dir().mkdir(parents=True, exist_ok=True)
    (library.library_dir() / "index.json").write_text("{not valid json", encoding="utf-8")

    assert library.list_items() == []
