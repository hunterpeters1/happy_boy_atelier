"""MainWindow: menus, toolbar, docks, and the top-level project lifecycle
(new / open / save / import / export / lock / projector)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from . import constants as C
from . import icons
from . import recovery
from .atelier_io import (
    AtelierIOError,
    export_jpg,
    export_pdf_planning_sheet,
    export_png,
    load_atelier,
    save_atelier,
)
from .canvas.canvas_scene import CanvasScene
from .canvas.canvas_view import CanvasView
from .canvas.undo_commands import AddItemCommand
from .dialogs.export_dialog import ExportDialog
from .dialogs.new_project_dialog import NewProjectDialog
from .panels.layers_panel import LayersPanel
from .panels.properties_panel import PropertiesPanel
from .project import CanvasSpec, ProjectMeta, empty_manifest
from .projector.projector_window import ProjectorWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(C.APP_NAME)
        self.resize(1440, 920)

        self.current_path: Path | None = None
        self.meta = ProjectMeta()
        self.projector_state = empty_manifest(CanvasSpec(), self.meta)["projector_state"]
        self._projector_window: ProjectorWindow | None = None

        self.scene: CanvasScene | None = None
        self.view: CanvasView | None = None
        self.layers_dock: QDockWidget | None = None
        self.properties_dock: QDockWidget | None = None

        self.status_hint = QLabel("")
        self.status_lock_banner = QLabel("SETUP LOCKED")
        self.status_lock_banner.setProperty("role", "banner-locked")
        self.status_lock_banner.setVisible(False)
        self.statusBar().addPermanentWidget(self.status_lock_banner)
        self.statusBar().addWidget(self.status_hint)

        self._build_menu_and_toolbar()
        self._start_project_or_offer_recovery()

        # Phase 0.3: periodic crash-recovery snapshot. Independent of the
        # user's own Save/Save As — see app/recovery.py for the full
        # lifecycle. Interval is hardcoded per the Phase 0 decision
        # (constants.AUTOSAVE_INTERVAL_MS); not user-configurable yet.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(C.AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()

    # -- crash recovery -------------------------------------------------
    def _start_project_or_offer_recovery(self) -> None:
        """Called once at startup, before the default new-project workspace
        is built. If a recovery snapshot exists, that means the last
        session ended uncleanly (crash, force-quit, power loss) — offer to
        recover it with a blocking choice before anything else loads.
        """
        if not recovery.has_recovery_file():
            self._new_project(CanvasSpec())
            return

        box = QMessageBox(self)
        box.setWindowTitle("Recover Unsaved Work")
        box.setIcon(QMessageBox.Warning)
        box.setText(
            "Happy Boy Atelier didn't close normally last time.\n\n"
            "A more recent, unsaved version of your painting setup was "
            "found. Would you like to recover it?"
        )
        recover_btn = box.addButton("Recover Previous Session", QMessageBox.AcceptRole)
        box.addButton("Discard Recovery", QMessageBox.DestructiveRole)
        box.setDefaultButton(recover_btn)
        box.exec()

        if box.clickedButton() is recover_btn:
            try:
                manifest, images = recovery.load_recovery_snapshot()
            except AtelierIOError as exc:
                QMessageBox.warning(
                    self, "Recovery Failed",
                    f"The recovery snapshot couldn't be read and will be discarded.\n\n{exc}",
                )
                recovery.delete_recovery_file()
                self._new_project(CanvasSpec())
                return

            spec = CanvasSpec.from_dict(manifest.get("canvas", {}))
            self.meta = ProjectMeta.from_dict(manifest.get("meta", {}))
            self.projector_state = manifest.get("projector_state", self.projector_state)

            scene = CanvasScene(spec)
            scene.load_manifest_layers(manifest, images)
            scene.set_global_locked(self.meta.locked)

            # Recovered content isn't tied to any file on disk yet — the
            # artist needs to Save As to give it a home. It also isn't the
            # last-clean-save state, so leave the undo stack dirty.
            self.current_path = None
            self._rebuild_workspace(scene)
            self.layers_panel.refresh_reference_list()
            self.lock_action.setChecked(self.meta.locked)
            self._update_lock_banner()
            self.statusBar().showMessage("Recovered your last unsaved session — Save to keep it.", 6000)
        else:
            self._new_project(CanvasSpec())

        recovery.delete_recovery_file()

    # -- workspace construction --------------------------------------------
    def _rebuild_workspace(self, scene: CanvasScene) -> None:
        self.scene = scene
        self.view = CanvasView(scene, self)
        self.setCentralWidget(self.view)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        # A fresh CanvasView always starts with rulers visible; keep the
        # View menu's checkbox honest if the artist had hidden them earlier.
        self.view.set_ruler_visible(self.ruler_action.isChecked())
        scene.tool_finished.connect(self._on_tool_finished)

        # Undo/redo menu wiring — each new/opened project gets its own
        # QUndoStack, so these connections are (re)made per scene rather
        # than once at startup.
        self.undo_action.setEnabled(scene.undo_stack.canUndo())
        self.redo_action.setEnabled(scene.undo_stack.canRedo())
        scene.undo_stack.canUndoChanged.connect(self.undo_action.setEnabled)
        scene.undo_stack.canRedoChanged.connect(self.redo_action.setEnabled)
        scene.undo_stack.undoTextChanged.connect(
            lambda t: self.undo_action.setText(f"Undo {t}" if t else "Undo")
        )
        scene.undo_stack.redoTextChanged.connect(
            lambda t: self.redo_action.setText(f"Redo {t}" if t else "Redo")
        )
        scene.undo_stack.indexChanged.connect(self._on_undo_index_changed)

        if self.layers_dock is not None:
            self.removeDockWidget(self.layers_dock)
        if self.properties_dock is not None:
            self.removeDockWidget(self.properties_dock)

        self.layers_panel = LayersPanel(scene, self)
        self.layers_panel.request_import.connect(self.import_images)
        # Tree-selection <-> canvas-selection is two-way: clicking a row
        # drives scene.set_selection() (inside the panel itself), and this
        # is the other direction — a canvas click highlights the matching
        # row without tearing down and rebuilding the whole tree.
        scene.selection_changed.connect(self.layers_panel._sync_selection_highlight)
        self.layers_dock = QDockWidget("Project", self)
        self.layers_dock.setWidget(self.layers_panel)
        self.layers_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.layers_dock)

        self.properties_panel = PropertiesPanel(scene, self)
        self.properties_panel.request_delete.connect(self._delete_selected)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setWidget(self.properties_panel)
        self.properties_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)

        # The Inspector has exactly one source of truth: CanvasScene's own
        # selection_changed signal (see canvas_scene.py — Qt's native
        # selectionChanged/selectedItems() don't work for these items at
        # all, not just unreliably). Previously the Inspector was *also*
        # wired to item_activated via a show_item() method that forced
        # single-item display even when several items were Shift-selected
        # — that's what let the Inspector and the actual selection
        # disagree with each other on screen. item_activated now drives
        # only the resize/rotate handle frame (_on_item_activated, in
        # canvas_scene.py), a separate concern.
        scene.selection_changed.connect(self.properties_panel.refresh)

        self._update_window_title()
        self._update_status_hint()
        self.view.viewport().update()

        def _fit():
            self.view.fit_canvas(scene.canvas_rect())
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, _fit)

    def _on_tool_finished(self) -> None:
        self.layers_panel._sync_tool_buttons(None)
        self._update_status_hint()

    def _on_undo_index_changed(self, _index: int) -> None:
        """Undo commands mutate the scene directly, bypassing whatever
        widget originally triggered the change — so after any undo/redo
        (or push), refresh the panels that could now be showing stale
        values for the current selection or the reference image list.
        """
        if self.scene is None:
            return
        self.properties_panel.refresh()
        self.layers_panel.sync_from_scene()
        self.layers_panel.refresh_reference_list()

    def _update_status_hint(self) -> None:
        if self.scene is None:
            return
        spec = self.scene.canvas_spec
        zoom = self.view.current_zoom() if self.view else 1.0
        self.status_hint.setText(
            f"  {spec.name}  ·  {spec.width:g} x {spec.height:g} {spec.unit}  ·  {int(zoom * 100)}%"
        )

    def _on_zoom_changed(self, _zoom: float) -> None:
        self._update_status_hint()

    def _update_window_title(self) -> None:
        name = self.current_path.stem if self.current_path else (self.scene.canvas_spec.name if self.scene else "Untitled")
        self.setWindowTitle(f"{C.APP_NAME} — {name}")

    # -- menu / toolbar -----------------------------------------------------
    def _build_menu_and_toolbar(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        self.new_action = self._add_action(file_menu, "New Painting…", "Ctrl+N", self.new_project_dialog, icon_name="new")
        self.open_action = self._add_action(file_menu, "Open…", "Ctrl+O", self.open_project, icon_name="open")
        self.save_action = self._add_action(file_menu, "Save", "Ctrl+S", self.save_project, icon_name="save")
        self._add_action(file_menu, "Save As…", "Ctrl+Shift+S", lambda: self.save_project(force_dialog=True))
        file_menu.addSeparator()
        self.import_action = self._add_action(
            file_menu, "Import Reference Image(s)…", "Ctrl+I", self.import_images, icon_name="import"
        )
        self.export_action = self._add_action(file_menu, "Export…", "Ctrl+E", self.export_project, icon_name="export")
        file_menu.addSeparator()
        self._add_action(file_menu, "Exit", "Ctrl+Q", self.close)

        edit_menu = menu.addMenu("&Edit")
        self.undo_action = QAction(icons.icon("undo"), "Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(lambda: self.scene.undo_stack.undo() if self.scene else None)
        self._set_tooltip(self.undo_action)
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction(icons.icon("redo"), "Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(lambda: self.scene.undo_stack.redo() if self.scene else None)
        self._set_tooltip(self.redo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Delete Selected", "Del", self._delete_selected, icon_name="delete")

        view_menu = menu.addMenu("&View")
        self._add_action(view_menu, "Zoom In", "Ctrl+=", lambda: self.view.zoom_in())
        self._add_action(view_menu, "Zoom Out", "Ctrl+-", lambda: self.view.zoom_out())
        self.fit_action = self._add_action(
            view_menu, "Fit Canvas", "Ctrl+0", lambda: self.view.fit_canvas(self.scene.canvas_rect()), icon_name="fit"
        )
        view_menu.addSeparator()
        # set_ruler_visible() has existed on CanvasView since Phase 0 with
        # no menu item, toolbar button, or shortcut ever wired to it — a
        # dead feature nobody could discover. This is that wiring.
        self.ruler_action = self._add_action(
            view_menu, "Show Rulers", "Ctrl+R",
            lambda checked: self.view.set_ruler_visible(checked) if self.view else None,
            checkable=True,
        )
        self.ruler_action.setChecked(True)

        mode_menu = menu.addMenu("&Mode")
        self.lock_action = self._add_action(
            mode_menu, "Lock Setup", "Ctrl+L", self.toggle_lock_setup, checkable=True, icon_name="lock"
        )
        self.projector_action = self._add_action(
            mode_menu, "Enter Projector Mode", "F5", self.enter_projector_mode, icon_name="projector"
        )

        help_menu = menu.addMenu("&Help")
        self._add_action(help_menu, "About Happy Boy Atelier", None, self._show_about)

        # One QAction per action, shared verbatim by menu and toolbar — a
        # QAction built for the toolbar alone (the old toolbar.addAction(
        # text, slot) pattern) can't carry the menu's shortcut into its own
        # tooltip and the two copies can silently drift out of sync. There
        # is exactly one object per action now, so that's structurally
        # impossible.
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.export_action)
        toolbar.addSeparator()
        toolbar.addAction(self.fit_action)
        toolbar.addSeparator()
        toolbar.addAction(self.lock_action)
        toolbar.addAction(self.projector_action)

    def _set_tooltip(self, action: QAction) -> None:
        shortcut = action.shortcut().toString()
        label = action.text().replace("&", "")
        action.setToolTip(f"{label} ({shortcut})" if shortcut else label)

    def _add_action(
        self, menu, text, shortcut, slot, checkable: bool = False, icon_name: str | None = None
    ) -> QAction:
        action = QAction(icons.icon(icon_name), text, self) if icon_name else QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self._set_tooltip(action)
        menu.addAction(action)
        return action

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About Happy Boy Atelier",
            f"{C.APP_NAME}  ·  v{C.APP_VERSION}\n\n"
            "A digital drafting table for traditional painters.\n"
            "Plan composition, perspective, and lighting before you touch the physical canvas.",
        )

    # -- project lifecycle --------------------------------------------------
    def _new_project(self, spec: CanvasSpec) -> None:
        self.current_path = None
        self.meta = ProjectMeta()
        scene = CanvasScene(spec)
        self._rebuild_workspace(scene)

    def new_project_dialog(self) -> None:
        dialog = NewProjectDialog(self)
        if dialog.exec():
            self._new_project(dialog.canvas_spec())

    def import_images(self) -> None:
        if self.scene is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Reference Images", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not paths:
            return
        rect = self.scene.canvas_rect()
        center = rect.center()
        cascade = 0
        for path in paths:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            offset_center = center + QPointF(cascade * 18, cascade * 18)
            item = self.scene.reference_layer.build_image_item(
                pixmap, rect.width(), rect.height(), offset_center, display_name=Path(path).name
            )
            self.scene.undo_stack.push(AddItemCommand(self.scene.reference_layer, item, "Add reference image"))
            cascade += 1
        self.layers_panel.refresh_reference_list()

    def _build_manifest(self) -> tuple[dict, dict]:
        """Assemble the current (manifest, images) pair from live scene
        state. Shared by save_project() and the autosave tick so the two
        never drift out of sync with each other.
        """
        self.meta.touch()
        self.meta.locked = self.scene.is_globally_locked()
        manifest = {
            "format_version": C.FORMAT_VERSION,
            "canvas": self.scene.canvas_spec.to_dict(),
            "meta": self.meta.to_dict(),
        }
        layers, images = self.scene.to_manifest_layers()
        manifest.update(layers)
        manifest["projector_state"] = self.projector_state
        return manifest, images

    def save_project(self, force_dialog: bool = False) -> None:
        if self.scene is None:
            return
        path = self.current_path
        if path is None or force_dialog:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Painting", "", "Happy Boy Atelier (*.atelier)")
            if not filename:
                return
            if not filename.lower().endswith(".atelier"):
                filename += ".atelier"
            path = Path(filename)

        manifest, images = self._build_manifest()

        try:
            save_atelier(path, manifest, images)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self.current_path = path
        self.scene.undo_stack.setClean()
        # A real save now supersedes any crash-recovery snapshot — leaving
        # a stale one behind would be a second save location the artist
        # never asked for.
        recovery.delete_recovery_file()
        self._update_window_title()
        self.statusBar().showMessage(f"Saved to {path.name}", 4000)

    def _autosave_tick(self) -> None:
        """Write a crash-recovery snapshot if there's unsaved work. Never
        touches the user's own project file — see app/recovery.py.
        """
        if self.scene is None or self.scene.undo_stack.isClean():
            return
        manifest, images = self._build_manifest()
        try:
            recovery.write_recovery_snapshot(manifest, images)
        except OSError:
            # Autosave is a safety net, not a user-facing operation — a
            # failure here (e.g. disk full) shouldn't interrupt work with
            # a dialog. It'll simply retry on the next tick.
            pass

    def open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open Painting", "", "Happy Boy Atelier (*.atelier)")
        if not filename:
            return
        try:
            manifest, images = load_atelier(filename)
        except AtelierIOError as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        spec = CanvasSpec.from_dict(manifest.get("canvas", {}))
        self.meta = ProjectMeta.from_dict(manifest.get("meta", {}))
        self.projector_state = manifest.get("projector_state", self.projector_state)

        scene = CanvasScene(spec)
        scene.load_manifest_layers(manifest, images)
        scene.set_global_locked(self.meta.locked)

        self.current_path = Path(filename)
        self._rebuild_workspace(scene)
        self.layers_panel.refresh_reference_list()
        self.lock_action.setChecked(self.meta.locked)
        self._update_lock_banner()

    def export_project(self) -> None:
        if self.scene is None:
            return
        dialog = ExportDialog(self)
        if not dialog.exec():
            return
        fmt = dialog.selected_format()
        dpi = dialog.dpi()
        filters = {"png": "PNG Image (*.png)", "jpg": "JPEG Image (*.jpg)", "pdf": "PDF Planning Sheet (*.pdf)"}
        filename, _ = QFileDialog.getSaveFileName(self, "Export", "", filters[fmt])
        if not filename:
            return
        if not filename.lower().endswith(f".{fmt}"):
            filename += f".{fmt}"

        rect = self.scene.canvas_rect()
        try:
            if fmt == "png":
                export_png(self.scene, rect, filename, dpi=dpi, px_per_inch=C.SCENE_PX_PER_INCH)
            elif fmt == "jpg":
                export_jpg(self.scene, rect, filename, dpi=dpi, px_per_inch=C.SCENE_PX_PER_INCH)
            else:
                notes = [n.text() for n in self.scene.composition_layer.notes]
                notes += [n.text() for n in self.scene.lighting_layer.notes]
                spec = self.scene.canvas_spec
                label = f"{spec.name} — {spec.width:g} x {spec.height:g} {spec.unit}"
                export_pdf_planning_sheet(self.scene, rect, filename, label, notes, px_per_inch=C.SCENE_PX_PER_INCH)
        except AtelierIOError as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return
        self.statusBar().showMessage(f"Exported to {Path(filename).name}", 4000)

    # -- lock / projector ----------------------------------------------
    def toggle_lock_setup(self) -> None:
        if self.scene is None:
            return
        locked = not self.scene.is_globally_locked()
        self.scene.set_global_locked(locked)
        self.lock_action.setChecked(locked)
        self.layers_panel.setEnabled(not locked)
        self._update_lock_banner()

    def _update_lock_banner(self) -> None:
        locked = self.scene.is_globally_locked() if self.scene else False
        self.status_lock_banner.setVisible(locked)

    def enter_projector_mode(self) -> None:
        if self.scene is None:
            return
        self._projector_window = ProjectorWindow(self.scene, initial_state=self.projector_state)
        self._projector_window.closed.connect(self._on_projector_closed)

    def _on_projector_closed(self) -> None:
        if self._projector_window is not None:
            self.projector_state = self._projector_window.get_state()
            self._projector_window = None

    # -- misc -----------------------------------------------------------
    def _delete_selected(self) -> None:
        if self.scene is None:
            return
        self.scene.delete_selected_items()
        self.layers_panel.refresh_reference_list()
        self.properties_panel.refresh()

    def closeEvent(self, event) -> None:
        # Clean-shutdown marker (Phase 0.3): a normal exit removes the
        # crash-recovery snapshot, so the next launch only offers recovery
        # after an actual unclean exit (crash, force-quit, power loss).
        recovery.delete_recovery_file()
        super().closeEvent(event)
