"""LibraryPanel (app/panels/library_panel.py): the Library dock's content
widget. Focuses on the panel <-> app/library.py wiring (refresh, search,
add/remove) and the drag-out mime data _LibraryList.mimeData() builds --
that's what lets a dragged thumbnail reuse CanvasView's existing OS
drag-and-drop import path unmodified. Core library.py logic itself is
covered in test_library.py.
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
from app.panels.library_panel import LibraryPanel


@pytest.fixture
def library_dir_tmp(qapp):
    QStandardPaths.setTestModeEnabled(True)
    path = library.library_dir()
    shutil.rmtree(path, ignore_errors=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _make_source_image(tmp_path: Path, name: str = "photo.png") -> Path:
    path = tmp_path / name
    pixmap = QPixmap(60, 60)
    pixmap.fill(QColor(200, 80, 40))
    pixmap.save(str(path), "PNG")
    return path


def test_fresh_panel_shows_the_empty_hint(library_dir_tmp):
    panel = LibraryPanel()
    assert panel.list.count() == 0
    # isHidden() (not isVisible()): the panel is never shown as a real
    # top-level window in this test, so isVisible() would read False
    # regardless of the widget's own explicit visibility intent.
    assert panel.hint.isHidden() is False


def test_refresh_populates_rows_from_the_library(library_dir_tmp, tmp_path):
    source = _make_source_image(tmp_path)
    library.add_image(source, display_name="Sunset")

    panel = LibraryPanel()  # __init__ calls refresh() already
    assert panel.list.count() == 1
    assert panel.list.item(0).text() == "Sunset"
    assert panel.hint.isHidden() is True
    assert not panel.list.item(0).icon().isNull()


def test_search_filter_hides_non_matching_rows(library_dir_tmp, tmp_path):
    library.add_image(_make_source_image(tmp_path, "a.png"), display_name="Mountain")
    library.add_image(_make_source_image(tmp_path, "b.png"), display_name="Beach")
    panel = LibraryPanel()

    panel.search_edit.setText("beach")

    hidden = [panel.list.item(i).isHidden() for i in range(panel.list.count())]
    texts = [panel.list.item(i).text() for i in range(panel.list.count())]
    visible_texts = {t for t, h in zip(texts, hidden) if not h}
    assert visible_texts == {"Beach"}


def test_remove_entry_deletes_from_library_and_refreshes(library_dir_tmp, tmp_path):
    item = library.add_image(_make_source_image(tmp_path), display_name="Gone Soon")
    panel = LibraryPanel()
    assert panel.list.count() == 1

    panel._remove_entry(item)

    assert panel.list.count() == 0
    assert library.list_items() == []


def test_double_click_activation_emits_import_requested_with_image_path(library_dir_tmp, tmp_path):
    item = library.add_image(_make_source_image(tmp_path), display_name="Click Me")
    panel = LibraryPanel()
    received = []
    panel.import_requested.connect(received.append)

    panel._on_item_activated(panel.list.item(0))

    assert received == [[str(item.image_path())]]


def test_dragging_a_row_produces_a_local_file_url_for_the_image(library_dir_tmp, tmp_path):
    """This is what lets a dragged thumbnail reuse CanvasView's existing
    OS drag-and-drop import handler unmodified -- it only ever looks for
    a local file:// URL with a supported extension.
    """
    item = library.add_image(_make_source_image(tmp_path), display_name="Drag Me")
    panel = LibraryPanel()

    mime = panel.list.mimeData([panel.list.item(0)])

    assert mime.hasUrls()
    urls = mime.urls()
    assert len(urls) == 1
    assert urls[0].isLocalFile()
    assert Path(urls[0].toLocalFile()) == item.image_path()


def test_add_images_with_no_selection_produces_empty_mime_data(library_dir_tmp):
    panel = LibraryPanel()
    mime = panel.list.mimeData([])
    assert not mime.hasUrls()


def test_poll_for_uploads_imports_and_refreshes_when_new_photos_land(
    library_dir_tmp, tmp_path, monkeypatch
):
    photos_dir = tmp_path / "uploader_photos"
    photos_dir.mkdir()
    monkeypatch.setattr(library, "uploader_photos_dir", lambda: photos_dir)

    panel = LibraryPanel()
    assert panel.list.count() == 0

    _make_source_image(photos_dir, name="20260813-100000-abc.png")
    panel._poll_for_uploads()

    assert panel.list.count() == 1
    assert library.list_items()[0].uploaded_from == "20260813-100000-abc.png"


def test_poll_for_uploads_does_not_refresh_when_nothing_new(library_dir_tmp, tmp_path, monkeypatch):
    photos_dir = tmp_path / "uploader_photos"
    photos_dir.mkdir()
    monkeypatch.setattr(library, "uploader_photos_dir", lambda: photos_dir)

    panel = LibraryPanel()
    refresh_calls = []
    panel.refresh = lambda: refresh_calls.append(1)

    panel._poll_for_uploads()  # nothing in photos_dir yet

    assert refresh_calls == []
