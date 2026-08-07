"""MainWindow: menus, toolbar, docks, and the top-level project lifecycle
(new / open / save / import / export / lock)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QSettings, QSize, QStandardPaths, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from . import constants as C
from . import debug_tools
from . import icons
from . import recovery
from . import themes
from .hacker_status import HackerStatusWidget
from .theme import apply_theme
from .atelier_io import (
    AtelierIOError,
    export_jpg,
    export_pdf_planning_sheet,
    export_png,
    load_atelier,
    read_thumbnail,
    render_thumbnail,
    save_atelier,
)
from .canvas.canvas_scene import CanvasScene
from .canvas.canvas_view import CanvasView
from .canvas.undo_commands import AddItemCommand
from .dialogs.command_palette import CommandPalette
from .dialogs.export_dialog import ExportDialog
from .dialogs.new_project_dialog import NewProjectDialog
from .dialogs.start_screen import StartScreen
from .panels.layers_panel import LayersPanel
from .panels.properties_panel import PropertiesPanel
from .panels.swatches_panel import SwatchesPanel
from .project import CanvasSpec, ProjectMeta

MAX_RECENT_FILES = 10


class MainWindow(QMainWindow):
    def __init__(self, theme_mode: themes.ThemeMode = themes.DEFAULT_THEME):
        super().__init__()
        self.setWindowTitle(C.APP_NAME)
        self.resize(1440, 920)

        self.current_path: Path | None = None
        self.meta = ProjectMeta()

        self.scene: CanvasScene | None = None
        self.view: CanvasView | None = None
        self.layers_dock: QDockWidget | None = None
        self.properties_dock: QDockWidget | None = None
        self.swatches_dock: QDockWidget | None = None

        # Appearance (see themes.py) — caller (main.py) already applied
        # this mode's palette to constants.py and ran apply_theme() before
        # constructing us, so our own widgets are built with the right
        # colors from the start; this just tracks what's active so the
        # Appearance menu shows the right radio checked and so hack-mode
        # extras (Debug menu, hacker status widget) can be set up if we're
        # starting directly in Hack Mode.
        self._theme_mode = theme_mode
        self._debug_menu = None
        self._hacker_widget: HackerStatusWidget | None = None
        self._stats_label: QLabel | None = None
        self._stats_timer: QTimer | None = None

        self.status_hint = QLabel("")
        self.status_lock_banner = QLabel("SETUP LOCKED")
        self.status_lock_banner.setProperty("role", "banner-locked")
        self.status_lock_banner.setVisible(False)
        self.statusBar().addPermanentWidget(self.status_lock_banner)
        self.statusBar().addWidget(self.status_hint)

        self._build_menu_and_toolbar()
        self._set_hack_mode_active(self._theme_mode == themes.ThemeMode.HACK)
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
        recover it with a blocking choice before anything else loads. With
        no recovery pending, a recent-files start screen replaces dropping
        straight into a blank Untitled Painting — but only if there's
        anything recent to show, so a fresh install still opens straight
        to a blank canvas with zero extra clicks.
        """
        if not recovery.has_recovery_file():
            self._offer_start_screen()
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
            # Deliberately NOT deleting the recovery file here. It used to
            # be removed the instant either button was clicked — meaning a
            # second crash before the artist's first post-recovery Save
            # lost the work again, with no safety net at all in between.
            # save_project() already deletes it on a real save; that's now
            # the only thing that does, for a recovered session.
        else:
            recovery.delete_recovery_file()
            self._new_project(CanvasSpec())

    def _offer_start_screen(self) -> None:
        recents = self._recent_files()
        if not recents:
            self._new_project(CanvasSpec())
            return
        thumbs = [(path, read_thumbnail(path)) for path in recents]
        dialog = StartScreen(thumbs, self)
        dialog.open_recent.connect(self._open_path)
        dialog.new_painting_requested.connect(self.new_project_dialog)
        dialog.open_requested.connect(self.open_project)
        dialog.exec()
        # Any of the three signals above already builds a real workspace
        # via _rebuild_workspace(); "Start Blank" (reject) or closing the
        # dialog without picking anything leaves self.scene unset, so
        # this is the one place that needs an explicit fallback.
        if self.scene is None:
            self._new_project(CanvasSpec())

    # -- workspace construction --------------------------------------------
    def _rebuild_workspace(self, scene: CanvasScene) -> None:
        self.scene = scene
        self.view = CanvasView(scene, self)
        self.setCentralWidget(self.view)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        # A fresh CanvasView always starts with rulers visible; keep the
        # View menu's checkbox honest if the artist had hidden them earlier.
        self.view.set_ruler_visible(self.ruler_action.isChecked())
        # Dropping image files from the OS onto the canvas imports them —
        # previously the file dialog was the only way in.
        self.view.files_dropped.connect(self._import_image_paths)
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
        if self.swatches_dock is not None:
            self.removeDockWidget(self.swatches_dock)

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

        # Eyedropper output — per-project swatch list (see meta.color_swatches),
        # rebuilt alongside Properties so a fresh self.meta (just assigned by
        # the new-project/open-project caller above) is what it reads from.
        # SwatchesPanel wires scene.color_hovered/color_sampled to itself
        # in its own __init__ — nothing further to connect here.
        self.swatches_panel = SwatchesPanel(scene, self.meta, self)
        self.swatches_dock = QDockWidget("Swatches", self)
        self.swatches_dock.setWidget(self.swatches_panel)
        self.swatches_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.swatches_dock)
        self.tabifyDockWidget(self.properties_dock, self.swatches_dock)

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
        if debug_tools.VERBOSE_LOGGING:
            cmd_text = self.scene.undo_stack.command(_index - 1).text() if _index > 0 else "clean"
            debug_tools.log(f"undo_stack.index -> {_index} ({cmd_text})")
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
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
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
        icons.register(self.undo_action, lambda obj, ic: obj.setIcon(ic), "undo")
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction(icons.icon("redo"), "Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(lambda: self.scene.undo_stack.redo() if self.scene else None)
        self._set_tooltip(self.redo_action)
        icons.register(self.redo_action, lambda obj, ic: obj.setIcon(ic), "redo")
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Delete Selected", "Del", self._delete_selected, icon_name="delete")
        edit_menu.addSeparator()
        self.lock_action = self._add_action(
            edit_menu, "Lock Setup", "Ctrl+L", self.toggle_lock_setup, checkable=True, icon_name="lock"
        )

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
        view_menu.addSeparator()
        self.palette_action = self._add_action(
            view_menu, "Command Palette…", "Ctrl+K", self.open_command_palette
        )
        view_menu.addSeparator()
        appearance_menu = view_menu.addMenu("Appearance")
        self._theme_actions: dict[themes.ThemeMode, QAction] = {}
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for mode in (themes.ThemeMode.LIGHT, themes.ThemeMode.DARK,
                     themes.ThemeMode.CURRENT, themes.ThemeMode.HACK):
            action = QAction(themes.THEME_LABELS[mode], self)
            action.setCheckable(True)
            action.setChecked(mode == self._theme_mode)
            action.triggered.connect(lambda _checked, m=mode: self._set_theme(m))
            theme_group.addAction(action)
            appearance_menu.addAction(action)
            self._theme_actions[mode] = action

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
        toolbar.setIconSize(QSize(22, 22))
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

    # -- appearance -----------------------------------------------------
    def _set_theme(self, mode: themes.ThemeMode) -> None:
        if mode == self._theme_mode:
            return
        self._theme_mode = mode
        QSettings().setValue("appearance/theme", mode.value)
        themes.apply_palette(mode)
        apply_theme(QApplication.instance())
        self._set_hack_mode_active(mode == themes.ThemeMode.HACK)
        self._refresh_icon_colors()
        if self.scene is not None:
            self.scene.update()
        if self.view is not None:
            self.view.refresh_theme_colors()
        debug_tools.log(f"theme changed -> {mode.value}")
        self.statusBar().showMessage("Theme changed.", 4000)

    def _refresh_icon_colors(self) -> None:
        """Re-bake every menu/toolbar/Properties-panel icon with the
        theme's current colors (icons.icon() bakes a QPixmap at call
        time, so already-set QIcons don't update on their own — see
        icons.py's registry). The Project Panel isn't registered
        individually; its whole tree is cheap to rebuild from scratch and
        that already re-renders every icon it contains.
        """
        icons.refresh_all()
        layers_panel = getattr(self, "layers_panel", None)
        if layers_panel is not None:
            layers_panel.refresh_structure()

    def _set_hack_mode_active(self, active: bool) -> None:
        """Crazy Hack Mode's extras: a Debug menu (verbose logging, a live
        scene-stats readout, a stylesheet-reload action) and the fake
        status-bar hacker widget — see debug_tools.py and
        hacker_status.py. Both are created/torn down here rather than
        just hidden, so they don't sit around doing nothing (or, for the
        status widget, animating on a timer) while some other theme is
        active.
        """
        if active and self._debug_menu is None:
            self._debug_menu = self.menuBar().addMenu("&Debug")
            self.verbose_log_action = self._add_action(
                self._debug_menu, "Verbose Console Logging", None,
                self._toggle_verbose_logging, checkable=True,
            )
            self.stats_overlay_action = self._add_action(
                self._debug_menu, "Scene Stats in Status Bar", None,
                self._toggle_stats_overlay, checkable=True,
            )
            self._add_action(self._debug_menu, "Reload Stylesheet", None, self._reload_stylesheet)
        elif not active and self._debug_menu is not None:
            self.menuBar().removeAction(self._debug_menu.menuAction())
            self._debug_menu.deleteLater()
            self._debug_menu = None
            debug_tools.VERBOSE_LOGGING = False
            self._stop_stats_overlay()

        if active and self._hacker_widget is None:
            self._hacker_widget = HackerStatusWidget()
            self.statusBar().addPermanentWidget(self._hacker_widget)
        elif not active and self._hacker_widget is not None:
            self.statusBar().removeWidget(self._hacker_widget)
            self._hacker_widget.stop()
            self._hacker_widget.deleteLater()
            self._hacker_widget = None

    def _toggle_verbose_logging(self, on: bool) -> None:
        debug_tools.VERBOSE_LOGGING = on
        debug_tools.log("verbose logging enabled" if on else "verbose logging disabled")

    def _toggle_stats_overlay(self, on: bool) -> None:
        if not on:
            self._stop_stats_overlay()
            return
        if self._stats_label is None:
            self._stats_label = QLabel()
            self._stats_label.setStyleSheet(
                f"color: {C.COLOR_INK_DIM}; font-family: '{C.FONT_FAMILY_MONO}'; font-size: 10px;"
            )
            self.statusBar().addPermanentWidget(self._stats_label)
        if self._stats_timer is None:
            self._stats_timer = QTimer(self)
            self._stats_timer.timeout.connect(self._update_stats_label)
            self._stats_timer.start(500)
        self._update_stats_label()

    def _stop_stats_overlay(self) -> None:
        if self._stats_timer is not None:
            self._stats_timer.stop()
            self._stats_timer = None
        if self._stats_label is not None:
            self.statusBar().removeWidget(self._stats_label)
            self._stats_label.deleteLater()
            self._stats_label = None
        if hasattr(self, "stats_overlay_action"):
            self.stats_overlay_action.setChecked(False)

    def _update_stats_label(self) -> None:
        if self._stats_label is None:
            return
        self._stats_label.setText(debug_tools.scene_stats(self.scene) if self.scene is not None else "no project open")

    def _reload_stylesheet(self) -> None:
        apply_theme(QApplication.instance())
        self._refresh_icon_colors()
        if self.scene is not None:
            self.scene.update()
        if self.view is not None:
            self.view.refresh_theme_colors()
        debug_tools.log("stylesheet reloaded")

    def _set_tooltip(self, action: QAction) -> None:
        shortcut = action.shortcut().toString()
        label = action.text().replace("&", "")
        action.setToolTip(f"{label} ({shortcut})" if shortcut else label)

    def _add_action(
        self, menu, text, shortcut, slot, checkable: bool = False, icon_name: str | None = None
    ) -> QAction:
        action = QAction(icons.icon(icon_name), text, self) if icon_name else QAction(text, self)
        if icon_name:
            icons.register(action, lambda obj, ic: obj.setIcon(ic), icon_name)
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

    def _collect_actions(self) -> list[QAction]:
        """Walk the menu bar's own QActions rather than maintaining a
        second, separately-authored command list — anything added to a
        menu in the future is automatically searchable in the palette
        with no extra step, and the two can never drift apart.
        """
        result: list[QAction] = []

        def walk(actions) -> None:
            for action in actions:
                if action.isSeparator() or action is self.palette_action:
                    continue
                submenu = action.menu()
                if submenu is not None:
                    walk(submenu.actions())
                else:
                    result.append(action)

        walk(self.menuBar().actions())
        return result

    def open_command_palette(self) -> None:
        dialog = CommandPalette(self._collect_actions(), self)
        dialog.exec()

    # -- recent files ---------------------------------------------------
    def _recent_files(self) -> list[Path]:
        raw = QSettings().value("recentFiles", [])
        if isinstance(raw, str):
            raw = [raw]
        # Silently drop entries for files that have since been moved,
        # renamed, or deleted rather than showing a dead link.
        return [p for p in (Path(s) for s in raw if s) if p.exists()]

    def _note_recent_file(self, path: Path) -> None:
        existing = [str(p) for p in self._recent_files() if p != path]
        updated = [str(path)] + existing
        QSettings().setValue("recentFiles", updated[:MAX_RECENT_FILES])

    def _clear_recent_files(self) -> None:
        QSettings().remove("recentFiles")

    def _populate_recent_menu(self) -> None:
        self.recent_menu.clear()
        recents = self._recent_files()
        if not recents:
            empty_action = self.recent_menu.addAction("No Recent Paintings")
            empty_action.setEnabled(False)
            return
        for path in recents:
            action = self.recent_menu.addAction(path.stem)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _checked, p=path: self._open_path(p))
        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Clear Recent")
        clear_action.triggered.connect(self._clear_recent_files)

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
        self._import_image_paths(paths)

    def _import_image_paths(self, paths: list[str]) -> None:
        """Shared by the Import dialog and CanvasView's OS drag-and-drop
        (there was previously no way to import except the file dialog).
        A multi-file import is now one undo step, not one per file —
        matching how multi-delete already batches into a single macro.
        """
        if self.scene is None or not paths:
            return
        rect = self.scene.canvas_rect()
        center = rect.center()
        cascade = 0
        multi = len(paths) > 1
        if multi:
            self.scene.undo_stack.beginMacro("Import reference images")
        try:
            for path in paths:
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    continue
                offset_center = center + QPointF(cascade * 18, cascade * 18)
                src = Path(path)
                try:
                    original_file_size = src.stat().st_size
                except OSError:
                    original_file_size = None
                item = self.scene.reference_layer.build_image_item(
                    pixmap, rect.width(), rect.height(), offset_center, display_name=src.name,
                    original_format=src.suffix.lstrip(".").upper() or None,
                    original_file_size=original_file_size,
                )
                self.scene.undo_stack.push(AddItemCommand(self.scene.reference_layer, item, "Add reference image"))
                cascade += 1
        finally:
            if multi:
                self.scene.undo_stack.endMacro()
        debug_tools.log(f"imported {cascade} reference image(s)")
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
        thumbnail = render_thumbnail(self.scene, self.scene.canvas_rect())

        try:
            save_atelier(path, manifest, images, thumbnail=thumbnail)
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
        self._note_recent_file(path)
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
        self._open_path(Path(filename))

    def _open_path(self, path: Path) -> None:
        """Shared by the Open dialog, Open Recent, and the start screen."""
        try:
            manifest, images = load_atelier(path)
        except AtelierIOError as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        spec = CanvasSpec.from_dict(manifest.get("canvas", {}))
        self.meta = ProjectMeta.from_dict(manifest.get("meta", {}))

        scene = CanvasScene(spec)
        scene.load_manifest_layers(manifest, images)
        scene.set_global_locked(self.meta.locked)

        self.current_path = path
        self._rebuild_workspace(scene)
        self.layers_panel.refresh_reference_list()
        self.lock_action.setChecked(self.meta.locked)
        self._update_lock_banner()
        self._note_recent_file(path)

    def export_project(self) -> None:
        if self.scene is None:
            return
        # Destination defaults to the project's own save folder if it has
        # one, else the OS Pictures folder — either way a real, existing
        # directory, so the export panel never opens pointed at nowhere.
        default_dir = (
            self.current_path.parent if self.current_path
            else Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or str(Path.home()))
        )
        dialog = ExportDialog(self.scene.canvas_spec.name, default_dir, self)
        if not dialog.exec():
            return
        fmt = dialog.selected_format()
        dpi = dialog.dpi()
        filename = str(dialog.destination_path())

        rect = self.scene.canvas_rect()
        # Only True for the duration of this export call — reset in
        # finally regardless of outcome, so a later Save's thumbnail
        # generation (a separate rendering_for_export-covered call) never
        # picks up a stale "bake the effect in" flag from a past export.
        self.scene.export_study_effect = dialog.include_study_effect()
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
        except (AtelierIOError, OSError) as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return
        finally:
            self.scene.export_study_effect = False
        debug_tools.log(f"exported {fmt} @ {dpi}dpi -> {filename}")
        self.statusBar().showMessage(f"Exported to {Path(filename).name}", 4000)

    # -- lock -------------------------------------------------------------
    def toggle_lock_setup(self) -> None:
        if self.scene is None:
            return
        locked = not self.scene.is_globally_locked()
        self.scene.set_global_locked(locked)
        self.lock_action.setChecked(locked)
        self.layers_panel.setEnabled(not locked)
        self._update_lock_banner()
        debug_tools.log(f"setup lock -> {locked}")

    def _update_lock_banner(self) -> None:
        locked = self.scene.is_globally_locked() if self.scene else False
        self.status_lock_banner.setVisible(locked)

    # -- misc -----------------------------------------------------------
    def _delete_selected(self) -> None:
        if self.scene is None:
            return
        n = len(self.scene.selected_items())
        self.scene.delete_selected_items()
        debug_tools.log(f"deleted {n} selected item(s)")
        self.layers_panel.refresh_reference_list()
        self.properties_panel.refresh()

    def closeEvent(self, event) -> None:
        # Clean-shutdown marker (Phase 0.3): a normal exit removes the
        # crash-recovery snapshot, so the next launch only offers recovery
        # after an actual unclean exit (crash, force-quit, power loss).
        recovery.delete_recovery_file()
        super().closeEvent(event)
