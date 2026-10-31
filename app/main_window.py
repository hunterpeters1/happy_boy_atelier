"""MainWindow: the project lifecycle (new/open/save/import/export/lock)
and the floating, chrome-free UI surface (top bar, tool strip, floating
panels, command overlay, radial menu).

The menu bar, toolbar, and status bar are gone — replaced by hover-revealed
floating overlays and a command palette accessible via Ctrl+K. The three dock
panels (Project, Properties, Swatches) are now borderless floating cards
that snap to canvas edges."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QSettings, QSize, QStandardPaths, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QWidget,
)

from . import constants as C
from . import debug_tools
from . import icons
from . import recovery
from . import themes
from . import ui_chrome
from . import radial_menu as radial_mod
from .command_overlay import CommandOverlay
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
        # No menu bar, no toolbar, no status bar — just the canvas with
        # floating, hover-revealed chrome on top of it.

        self.current_path: Path | None = None
        self.meta = ProjectMeta()

        self.scene: CanvasScene | None = None
        self.view: CanvasView | None = None

        # Floating chrome elements
        self._top_bar: ui_chrome.TopBar | None = None
        self._tool_strip: ui_chrome.ToolStrip | None = None
        self._bottom_bar: ui_chrome.BottomStatusBar | None = None
        self._command_overlay: CommandOverlay | None = None

        # Floating panels (replaces QDockWidget)
        self._project_panel: ui_chrome.FloatingPanel | None = None
        self._properties_panel: ui_chrome.FloatingPanel | None = None
        self._swatches_panel: ui_chrome.FloatingPanel | None = None

        # Store the inner widget panels (LayersPanel, PropertiesPanel, SwatchesPanel)
        # so they survive panel hide/show
        self._layers_panel_inner: LayersPanel | None = None
        self._properties_inner: PropertiesPanel | None = None
        self._swatches_inner: SwatchesPanel | None = None

        self._debug_menu = None
        self._hacker_widget: HackerStatusWidget | None = None
        self._stats_label: QLabel | None = None
        self._stats_timer: QTimer | None = None

        # Appearance theme tracking
        self._theme_mode = theme_mode
        self._set_hack_mode_active(self._theme_mode == themes.ThemeMode.HACK)

        # Build all the QAction objects up front (even though we no longer
        # have a menu bar, the actions are used by the command overlay,
        # toolbar strip, keyboard shortcuts, and the radial menu).
        self._build_actions()
        self._build_floating_chrome()

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

            scene = CanvasScene(spec, bg_color=self.meta.bg_color)
            scene.load_manifest_layers(manifest, images)
            scene.set_global_locked(self.meta.locked)

            # Recovered content isn't tied to any file on disk yet — the
            # artist needs to Save As to give it a home. It also isn't the
            # last-clean-save state, so leave the undo stack dirty.
            self.current_path = None
            self._rebuild_workspace(scene)
            if self._layers_panel_inner is not None:
                self._layers_panel_inner.refresh_structure()
            self.lock_action.setChecked(self.meta.locked)
            self._update_lock_banner()
            if self._bottom_bar is not None:
                self._bottom_bar.set_hint("Recovered your last unsaved session — Save to keep it.")
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
        # Set the view's desk color to match the scene's bg_color, so the
        # void beyond the canvas rect matches what drawBackground paints.
        self.view.set_desk_color(self.scene._bg_color)
        self.setCentralWidget(self.view)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        # A fresh CanvasView always starts with rulers visible; keep the
        # View menu's checkbox honest if the artist had hidden them earlier.
        self.view.set_ruler_visible(self.ruler_action.isChecked())
        # Dropping image files from the OS onto the canvas imports them —
        # previously the file dialog was the only way in.
        self.view.files_dropped.connect(self._import_image_paths)
        scene.tool_finished.connect(self._on_tool_finished)

        # Undo/redo action wiring — each new/opened project gets its own
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

        # Remove old dock widgets if they exist (from a previous scene)
        for dock_attr in ("layers_dock", "properties_dock", "swatches_dock"):
            dock = getattr(self, dock_attr, None)
            if dock is not None:
                self.removeDockWidget(dock)
                dock.deleteLater()
                setattr(self, dock_attr, None)

        # Create inner panel widgets (the actual content)
        self._layers_panel_inner = LayersPanel(scene, self)
        self._layers_panel_inner.request_import.connect(self.import_images)
        scene.selection_changed.connect(self._layers_panel_inner._sync_selection_highlight)

        self._properties_inner = PropertiesPanel(scene, self)
        self._properties_inner.request_delete.connect(self._delete_selected)

        # Eyedropper output — per-project swatch list (see meta.color_swatches),
        # rebuilt alongside Properties so a fresh self.meta (just assigned by
        # the new-project/open-project caller above) is what it reads from.
        # SwatchesPanel wires scene.color_hovered/color_sampled to itself
        # in its own __init__ — nothing further to connect here.
        self._swatches_inner = SwatchesPanel(scene, self.meta, self)

        # Wire the inner panels into the floating cards
        if self._project_panel is not None:
            self._project_panel.set_content_widget(self._layers_panel_inner)
        if self._properties_panel is not None:
            self._properties_panel.set_content_widget(self._properties_inner)
        if self._swatches_panel is not None:
            self._swatches_panel.set_content_widget(self._swatches_inner)

        # Inspector is driven by CanvasScene's selection_changed signal
        scene.selection_changed.connect(self._properties_inner.refresh)

        self._update_window_title()
        self._update_status_hint()
        self.view.viewport().update()

        def _fit():
            self.view.fit_canvas(scene.canvas_rect())
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, _fit)

        # Now that the view exists, install hover tracking for chrome auto-show
        self._install_canvas_hover_tracking()
        # Show floating panels now that they have content
        if self._project_panel is not None:
            self._project_panel.fade_in()
        if self._properties_panel is not None:
            self._properties_panel.fade_in()
        if self._swatches_panel is not None:
            self._swatches_panel.fade_in()

    def _on_tool_finished(self) -> None:
        if self._layers_panel_inner is not None:
            self._layers_panel_inner._sync_tool_buttons(None)
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
        if self._properties_inner is not None:
            self._properties_inner.refresh()
        if self._layers_panel_inner is not None:
            self._layers_panel_inner.refresh_structure()

    def _update_status_hint(self) -> None:
        if self.scene is None or self._bottom_bar is None:
            return
        spec = self.scene.canvas_spec
        zoom = self.view.current_zoom() if self.view else 1.0
        self._bottom_bar.set_hint(
            f"  {spec.name}  ·  {spec.width:g} x {spec.height:g} {spec.unit}  ·  {int(zoom * 100)}%"
        )
        self._bottom_bar.set_zoom(int(zoom * 100))

    def _on_zoom_changed(self, _zoom: float) -> None:
        self._update_status_hint()

    def _update_window_title(self) -> None:
        name = self.current_path.stem if self.current_path else (self.scene.canvas_spec.name if self.scene else "Untitled")
        self.setWindowTitle(f"{C.APP_NAME} — {name}")

    # -- actions (replacing menu + toolbar) ----------------------------------
    def _build_actions(self) -> None:
        """Build all QAction objects once. These are shared between the
        command overlay (Ctrl+K / ⋯ button), the floating tool strip,
        keyboard shortcuts, and the radial menu — unlike the old design
        where the toolbar built separate, un-synced QAction instances.
        There is exactly one object per action now."""

        # File actions
        self.new_action = self._add_action("New Painting…", "Ctrl+N", self.new_project_dialog, icon_name="new")
        self.open_action = self._add_action("Open…", "Ctrl+O", self.open_project, icon_name="open")
        self.save_action = self._add_action("Save", "Ctrl+S", self.save_project, icon_name="save")
        self.save_as_action = self._add_action("Save As…", "Ctrl+Shift+S", lambda: self.save_project(force_dialog=True))
        self.import_action = self._add_action("Import Reference Image(s)…", "Ctrl+I", self.import_images, icon_name="import")
        self.export_action = self._add_action("Export…", "Ctrl+E", self.export_project, icon_name="export")
        self.exit_action = self._add_action("Exit", "Ctrl+Q", self.close)

        # Edit actions
        self.undo_action = QAction(icons.icon("undo"), "Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(lambda: self.scene.undo_stack.undo() if self.scene else None)
        self._set_tooltip(self.undo_action)
        icons.register(self.undo_action, lambda obj, ic: obj.setIcon(ic), "undo")

        self.redo_action = QAction(icons.icon("redo"), "Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(lambda: self.scene.undo_stack.redo() if self.scene else None)
        self._set_tooltip(self.redo_action)
        icons.register(self.redo_action, lambda obj, ic: obj.setIcon(ic), "redo")

        self.delete_action = self._add_action("Delete Selected", "Del", self._delete_selected, icon_name="delete")
        self.duplicate_action = self._add_action("Duplicate", "Ctrl+D", self._duplicate_selected, icon_name="image")
        self.bring_to_front_action = self._add_action("Bring to Front", None, self._bring_to_front)
        self.send_to_back_action = self._add_action("Send to Back", None, self._send_to_back)
        self.flip_h_action = self._add_action("Flip Horizontal", None, self._flip_horizontal)
        self.flip_v_action = self._add_action("Flip Vertical", None, self._flip_vertical)
        self.magnify_action = self._add_action("Magnify 2×", None, self._magnify_selected)
        self.shrink_action = self._add_action("Shrink to 50%", None, self._demagnify_selected)
        self.lock_action = self._add_action("Lock Setup", "Ctrl+L", self.toggle_lock_setup, checkable=True, icon_name="lock")

        # View actions
        self.fit_action = self._add_action("Fit Canvas", "Ctrl+0", lambda: self.view.fit_canvas(self.scene.canvas_rect()), icon_name="fit")
        self.ruler_action = self._add_action("Show Rulers", "Ctrl+R",
            lambda checked: self.view.set_ruler_visible(checked) if self.view else None,
            checkable=True)
        self.ruler_action.setChecked(True)
        self.desk_color_action = self._add_action("Change Desk Color…", None, self._change_desk_color, icon_name="eye")
        self.palette_action = self._add_action("Command Palette…", "Ctrl+K", self.open_command_palette)

        # Theme actions
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
            self._theme_actions[mode] = action

        self.help_action = self._add_action("About Happy Boy Atelier", None, self._show_about)

        # Register all actions on the window so keyboard shortcuts work
        # without a menu bar — QMainWindow picks up shortcuts from actions
        # added via addAction().
        for attr_name in self._ALL_ACTIONS:
            action = getattr(self, attr_name, None)
            if action is not None:
                self.addAction(action)
        for action in self._theme_actions.values():
            self.addAction(action)

    def _build_floating_chrome(self) -> None:
        """Build the floating, chrome-free UI surface: top bar, tool strip,
        bottom status bar, and the three floating panels."""

        # -- Top bar (floating, at the top of the window) --
        self._top_bar = ui_chrome.TopBar(self)
        self._top_bar.hide()  # shown on hover
        self._top_bar.menu_requested.connect(self.open_command_palette)
        self._top_bar.lock_button.toggled.connect(self.toggle_lock_setup)
        self._top_bar.lock_button.setChecked(False)

        # Theme picker menu for the top bar
        theme_menu = QMenu(self)
        for mode, action in self._theme_actions.items():
            theme_menu.addAction(action)
        self._top_bar.theme_button.setMenu(theme_menu)

        # -- Tool strip (floating, left canvas edge, hover-revealed) --
        self._tool_strip = ui_chrome.ToolStrip(self)
        self._tool_strip.hide()
        # Wire the tool strip buttons to actions
        self._tool_strip.set_buttons([
            ("new", "New Painting", self.new_project_dialog),
            ("open", "Open", self.open_project),
            ("save", "Save", self.save_project),
            ("undo", "Undo", lambda: self.scene.undo_stack.undo() if self.scene else None),
            ("redo", "Redo", lambda: self.scene.undo_stack.redo() if self.scene else None),
            ("import", "Import", self.import_images),
            ("export", "Export", self.export_project),
            ("fit", "Fit Canvas", lambda: self.view.fit_canvas(self.scene.canvas_rect()) if self.view and self.scene else None),
            ("lock", "Lock Setup", self.toggle_lock_setup),
            ("eye", "Desk Color", self._change_desk_color),
        ])

        # -- Bottom status bar (floating, bottom canvas edge, hover-revealed) --
        self._bottom_bar = ui_chrome.BottomStatusBar(self)
        self._bottom_bar.hide()

        # -- Floating panels --
        # Project panel (left side)
        self._recent_menu = QMenu(self)
        self._populate_recent_menu()
        self._project_panel = self._create_floating_panel("Project", ui_chrome.FloatingPanel, side="left")

        # Properties panel (right side)
        self._properties_panel = self._create_floating_panel("Properties", ui_chrome.FloatingPanel, side="right")

        # Swatches panel (right side, below properties)
        self._swatches_panel = self._create_floating_panel("Swatches", ui_chrome.FloatingPanel, side="right")

        # Install canvas hover tracking for auto-hiding chrome
        self._install_canvas_hover_tracking()

    def _create_floating_panel(self, title: str, panel_cls, side: str = "left") -> ui_chrome.FloatingPanel:
        """Create a FloatingPanel with standard brass styling and position it
        along the specified canvas edge."""
        panel = panel_cls(title, self)
        panel.setFixedWidth(328)  # Standard panel width
        # Position near the edge
        if side == "left":
            panel.move(16, 56)  # Below the top bar
        else:
            panel.move(self.width() - 328 - 16, 56)
        return panel

    def _install_canvas_hover_tracking(self) -> None:
        """Install an event filter on the canvas view's viewport to show/hide
        floating chrome based on mouse proximity to canvas edges."""
        if self.view is not None:
            self.view.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle mouse move events on the canvas viewport for chrome auto-show."""
        from PySide6.QtCore import QEvent, QTimer

        if obj is self.view and obj is not None:
            if event.type() == QEvent.MouseMove:
                pos = event.position().toQPoint()
                margin = 24  # hover margin

                # Show top bar near the top edge
                if self._top_bar is not None:
                    if pos.y() < margin:
                        if not self._top_bar.isVisible():
                            self._top_bar.fade_in()
                    elif pos.y() > margin * 2 and self._top_bar.isVisible():
                        self._top_bar.fade_out()

                    # Auto-hide after delay
                    if self._top_bar.is_actually_visible():
                        QTimer.singleShot(2000, self._top_bar.fade_out)

                # Show tool strip near the left edge
                if self._tool_strip is not None:
                    if pos.x() < margin:
                        if not self._tool_strip.isVisible():
                            self._tool_strip.fade_in()
                    elif pos.x() > margin * 2 and self._tool_strip.isVisible():
                        self._tool_strip.fade_out()

                # Show bottom bar near the bottom edge
                if self._bottom_bar is not None:
                    if obj.height() - pos.y() < margin:
                        if not self._bottom_bar.isVisible():
                            self._bottom_bar.fade_in()
                    elif obj.height() - pos.y() > margin * 2 and self._bottom_bar.isVisible():
                        self._bottom_bar.fade_out()

        return super().eventFilter(obj, event)

    # -- appearance -----------------------------------------------------
    def _change_desk_color(self) -> None:
        """Open a color dialog to pick the desk color (the void behind the
        canvas rect). This is a per-project, non-undoable workflow
        preference — saved in the .atelier file's meta.bg_color field.
        """
        if self.scene is None:
            return
        current = QColor(self.meta.bg_color)
        color = QColorDialog.getColor(current, self, "Choose Desk Color")
        if color.isValid() and color.name() != current.name():
            self.meta.bg_color = color.name()
            self.scene.set_bg_color(self.meta.bg_color)
            self.view.set_desk_color(self.meta.bg_color)
            debug_tools.log(f"desk color -> {self.meta.bg_color}")

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
        if self._bottom_bar is not None:
            self._bottom_bar.set_hint("Theme changed.")

    def _refresh_icon_colors(self) -> None:
        """Re-bake every menu/toolbar/Properties-panel icon with the
        theme's current colors (icons.icon() bakes a QPixmap at call
        time, so already-set QIcons don't update on their own — see
        icons.py's registry). The Project Panel isn't registered
        individually; its whole tree is cheap to rebuild from scratch and
        that already re-renders every icon it contains.
        """
        icons.refresh_all()
        layers_panel = getattr(self, "_layers_panel_inner", None)
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
            # Build debug menu as a popup menu attached to the top bar's ⋯ button area
            self._debug_menu = QMenu(self)
            self.verbose_log_action = self._add_action_obj(
                "Verbose Console Logging", None,
                self._toggle_verbose_logging, checkable=True,
            )
            self._debug_menu.addAction(self.verbose_log_action)
            self.stats_overlay_action = self._add_action_obj(
                "Scene Stats Overlay", None,
                self._toggle_stats_overlay, checkable=True,
            )
            self._debug_menu.addAction(self.stats_overlay_action)
            self._reload_action = self._add_action_obj(
                "Reload Stylesheet", None, self._reload_stylesheet
            )
            self._debug_menu.addAction(self._reload_action)
            # Attach the debug menu to the menu button
            self._top_bar._menu_btn.setMenu(self._debug_menu)
            self._top_bar._menu_btn.setPopupMode(QToolButton.InstantPopup)
        elif not active and self._debug_menu is not None:
            self._debug_menu.deleteLater()
            self._debug_menu = None
            self._top_bar._menu_btn.setMenu(None)
            debug_tools.VERBOSE_LOGGING = False
            self._stop_stats_overlay()

        if active and self._hacker_widget is None:
            self._hacker_widget = HackerStatusWidget()
            if self._bottom_bar is not None:
                self._bottom_bar.layout().insertWidget(1, self._hacker_widget)
        elif not active and self._hacker_widget is not None:
            if self._bottom_bar is not None:
                self._bottom_bar.layout().removeWidget(self._hacker_widget)
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
            if self._bottom_bar is not None:
                self._bottom_bar.layout().insertWidget(0, self._stats_label)
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
            if self._bottom_bar is not None:
                self._bottom_bar.layout().removeWidget(self._stats_label)
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
        self, text, shortcut, slot, checkable: bool = False, icon_name: str | None = None,
    ) -> QAction:
        """Create a QAction with icon, shortcut, and tooltip. No menu association —
        actions are collected separately for the command overlay."""
        action = QAction(icons.icon(icon_name), text, self) if icon_name else QAction(text, self)
        if icon_name:
            icons.register(action, lambda obj, ic: obj.setIcon(ic), icon_name)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self._set_tooltip(action)
        return action

    # Alias for hack-mode debug actions that don't need an icon/shortcut
    def _add_action_obj(self, text, shortcut, slot, checkable=False, icon_name=None):
        return self._add_action(text, shortcut, slot, checkable=checkable, icon_name=icon_name)

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About Happy Boy Atelier",
            f"{C.APP_NAME}  ·  v{C.APP_VERSION}\n\n"
            "A digital drafting table for traditional painters.\n"
            "Plan composition, perspective, and lighting before you touch the physical canvas.",
        )

    # All actions collected into a flat list — the command overlay walks
    # this list and categorizes it, so there's nothing to walk from a menu
    # bar (there isn't one anymore).
    _ALL_ACTIONS: list[str] = [
        "new_action", "open_action", "save_action", "save_as_action",
        "import_action", "export_action", "exit_action",
        "undo_action", "redo_action",
        "delete_action", "duplicate_action", "bring_to_front_action", "send_to_back_action",
        "flip_h_action", "flip_v_action", "magnify_action", "shrink_action",
        "lock_action",
        "fit_action", "ruler_action", "desk_color_action", "palette_action",
        "help_action",
    ]

    def _collect_actions(self) -> list[QAction]:
        """Return all registered QAction objects for the command overlay.
        Themes are handled separately (they're a QActionGroup, not in the
        flat list)."""
        result = []
        for attr_name in self._ALL_ACTIONS:
            action = getattr(self, attr_name, None)
            if action is not None and not action.isSeparator():
                result.append(action)
        # Add theme actions
        result.extend(self._theme_actions.values())
        return result

    def open_command_palette(self) -> None:
        dialog = CommandOverlay(self._collect_actions(), self)
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
        if self._recent_menu is None:
            return
        self._recent_menu.clear()
        recents = self._recent_files()
        if not recents:
            empty_action = self._recent_menu.addAction("No Recent Paintings")
            empty_action.setEnabled(False)
            return
        for path in recents:
            action = self._recent_menu.addAction(path.stem)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _checked, p=path: self._open_path(p))
        self._recent_menu.addSeparator()
        clear_action = self._recent_menu.addAction("Clear Recent")
        clear_action.triggered.connect(self._clear_recent_files)

    # -- project lifecycle --------------------------------------------------
    def _new_project(self, spec: CanvasSpec) -> None:
        self.current_path = None
        self.meta = ProjectMeta()
        scene = CanvasScene(spec, bg_color=self.meta.bg_color)
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
        if self._layers_panel_inner is not None:
            self._layers_panel_inner.refresh_structure()

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
        if self._bottom_bar is not None:
            self._bottom_bar.set_hint(f"Saved to {path.name}")

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

        scene = CanvasScene(spec, bg_color=self.meta.bg_color)
        scene.load_manifest_layers(manifest, images)
        scene.set_global_locked(self.meta.locked)

        self.current_path = path
        self._rebuild_workspace(scene)
        if self._layers_panel_inner is not None:
            self._layers_panel_inner.refresh_structure()
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
        if self._bottom_bar is not None:
            self._bottom_bar.set_hint(f"Exported to {Path(filename).name}")

    # -- lock -------------------------------------------------------------
    def toggle_lock_setup(self) -> None:
        """Toggle the setup lock — called from Ctrl+L shortcut, the lock_action
        QAction, and the top-bar lock button. The top-bar button is also
        connected to this method via its `toggled` signal, so we block
        signals on it during the programmatic setChecked below to avoid
        a feedback loop."""
        if self.scene is None:
            return
        locked = not self.scene.is_globally_locked()
        self.scene.set_global_locked(locked)
        self.lock_action.setChecked(locked)
        # Update the top bar lock button without triggering its signal
        if self._top_bar is not None:
            self._top_bar.lock_button.blockSignals(True)
            self._top_bar.lock_button.setChecked(locked)
            self._top_bar.lock_button.blockSignals(False)
        if self._bottom_bar is not None:
            self._bottom_bar.set_locked(locked)
        debug_tools.log(f"setup lock -> {locked}")

    def _update_lock_banner(self) -> None:
        locked = self.scene.is_globally_locked() if self.scene else False
        if self._bottom_bar is not None:
            self._bottom_bar.set_locked(locked)

    # -- misc -----------------------------------------------------------
    def _delete_selected(self) -> None:
        if self.scene is None:
            return
        n = len(self.scene.selected_items())
        self.scene.delete_selected_items()
        debug_tools.log(f"deleted {n} selected item(s)")
        if self._layers_panel_inner is not None:
            self._layers_panel_inner.refresh_structure()
        if self._properties_inner is not None:
            self._properties_inner.refresh()

    def _duplicate_selected(self) -> None:
        if self.scene is None:
            return
        self.scene.duplicate_selected_items()
        if self._layers_panel_inner is not None:
            self._layers_panel_inner.refresh_structure()
        if self._properties_inner is not None:
            self._properties_inner.refresh()

    def _bring_to_front(self) -> None:
        if self.scene is None:
            return
        self.scene.bring_to_front_selected()
        if self._properties_inner is not None:
            self._properties_inner.refresh()

    def _send_to_back(self) -> None:
        if self.scene is None:
            return
        self.scene.send_to_back_selected()
        if self._properties_inner is not None:
            self._properties_inner.refresh()

    def _flip_horizontal(self) -> None:
        if self.scene is None:
            return
        items = [i for i in self.scene.selected_items() if hasattr(i, "flip_horizontal")]
        if not items:
            return
        # One undo step per user action, not one per item — matches
        # duplicate_selected_items()/send_to_back_selected()'s convention
        # (canvas/canvas_scene.py). Each item's flip_horizontal() already
        # pushes its own TransformCommand; the macro just groups them.
        multi = len(items) > 1
        if multi:
            self.scene.undo_stack.beginMacro("Flip Horizontal")
        try:
            for item in items:
                item.flip_horizontal()
        finally:
            if multi:
                self.scene.undo_stack.endMacro()

    def _flip_vertical(self) -> None:
        if self.scene is None:
            return
        items = [i for i in self.scene.selected_items() if hasattr(i, "flip_vertical")]
        if not items:
            return
        multi = len(items) > 1
        if multi:
            self.scene.undo_stack.beginMacro("Flip Vertical")
        try:
            for item in items:
                item.flip_vertical()
        finally:
            if multi:
                self.scene.undo_stack.endMacro()

    def _magnify_selected(self) -> None:
        if self.scene is None:
            return
        items = [i for i in self.scene.selected_items() if hasattr(i, "magnify")]
        if not items:
            return
        multi = len(items) > 1
        if multi:
            self.scene.undo_stack.beginMacro("Magnify")
        try:
            for item in items:
                item.magnify()
        finally:
            if multi:
                self.scene.undo_stack.endMacro()

    def _demagnify_selected(self) -> None:
        if self.scene is None:
            return
        items = [i for i in self.scene.selected_items() if hasattr(i, "demagnify")]
        if not items:
            return
        multi = len(items) > 1
        if multi:
            self.scene.undo_stack.beginMacro("Shrink")
        try:
            for item in items:
                item.demagnify()
        finally:
            if multi:
                self.scene.undo_stack.endMacro()

    def closeEvent(self, event) -> None:
        # Clean-shutdown marker (Phase 0.3): a normal exit removes the
        # crash-recovery snapshot, so the next launch only offers recovery
        # after an actual unclean exit (crash, force-quit, power loss).
        recovery.delete_recovery_file()
        super().closeEvent(event)
