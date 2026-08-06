# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Happy Boy Atelier — a Windows desktop app (PySide6/Qt) for traditional
painters to plan a physical painting before touching canvas: pick a
format, arrange reference photos, plan composition/perspective/lighting,
then trace it onto the wall in projector mode. It is **not** a paint
program and **not** an AI image generator — every mark is placed by the
artist; the software never infers composition, perspective, or lighting.
AI generation, a brush engine, cloud accounts, and social/marketplace
features are explicitly out of scope.

This is a git repository (initialized partway through the UX redesign
below — there is no history before the "Baseline commit before UX
redesign" commit). Local repo-scoped `user.name`/`user.email` are set;
don't touch global git config.

## Commands

Run everything from the repo root, with the venv active.

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt          # PySide6
pip install -r requirements-dev.txt      # pytest
python main.py                           # run the app
pytest                                   # full test suite
pytest tests/test_undo_commands.py       # single file
pytest tests/test_undo_commands.py -k some_test_name   # single test
```

Tests run headless: `tests/conftest.py` forces
`QT_QPA_PLATFORM=offscreen` before PySide6 is imported and provides a
session-scoped `qapp` fixture (Qt allows exactly one `QApplication` per
process). Request `qapp` in any test touching `QGraphicsScene`/
`QGraphicsItem`/`QPixmap`. `test_project.py` has no Qt dependency at all;
`test_atelier_io.py` and `test_undo_commands.py` exercise real
`.atelier` files and a real `CanvasScene` respectively.

### Building the .exe

There is deliberately no build script (`build.bat`, PowerShell helpers,
etc.) — every one tried got flagged/blocked by Windows on the dev
machine, since a downloaded script that installs things and calls other
scripts is exactly what SmartScreen/AV heuristics watch for. The only
supported path is typing the commands yourself:

```
pip install -r requirements-build.txt
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python -m PyInstaller HappyBoyAtelier.spec --noconfirm
```

Output: `dist\Happy Boy Atelier.exe`. `HappyBoyAtelier.spec` bakes in two
things found the hard way during v1.0 packaging — don't strip them if
touching the spec: `collect_all("PySide6")` (without it the frozen exe
raises `ModuleNotFoundError` at runtime despite a successful build) and
`datas=[("resources", "resources")]` (without it `setWindowIcon()`
silently no-ops in the frozen exe because `app_icon_path()` can't find
`resources/icons/app.ico` inside the bundle). Must be built on Windows —
PyInstaller doesn't cross-compile. `Happy Boy Atelier.spec` (with spaces,
no PySide6 collect_all baked in) is an older/stale spec file — prefer
`HappyBoyAtelier.spec`. `scripts/` is an empty leftover directory.

## Architecture

Full design doc: `ARCHITECTURE.md`. Key points to internalize before
editing:

**The scene is the single source of truth.** There is no separate live
data model shadowing the graphics items — every custom `QGraphicsItem`
carries its own state (position, rotation, opacity, lock, notes). Save
walks the scene once; load rebuilds it once. Don't introduce a second
state store that needs to stay in sync with the scene.

**Layer stack (`app/canvas/canvas_scene.py`), fixed z-order back to
front:** Reference → Composition → Perspective → Lighting → Guides
(non-interactive, always on top). Each layer is a `QGraphicsItemGroup`
exposing `set_visible`/`set_locked`/`set_opacity`, driven by the Project
Panel (`app/panels/layers_panel.py` — the dock is titled "Project", the
module/class names weren't renamed). Locking a layer clears
`ItemIsMovable`/`ItemIsSelectable` on its children rather than removing
them — a locked layer stays visible and still exports.

**Project Panel (`app/panels/layers_panel.py`):** a real `QTreeWidget`
outliner, not five fixed group boxes — every placed item across all five
layers gets a named, selectable row (`_row_icon_and_label()`), not just
reference images. `refresh_structure()` fully rebuilds the tree (call
after any add/delete/undo/redo); `_sync_selection_highlight()` only
updates which rows are highlighted (call on `scene.selection_changed`) —
keep these separate, conflating them was a real bug once (a full rebuild
mid-batch-edit silently wiped the live selection via an unguarded
`itemSelectionChanged` during `tree.clear()`).

**Icons (`app/icons.py`):** a small line-icon set rendered at runtime
from SVG shape strings via `QSvgRenderer`, not files — `resources/icons/`
holds only the window/taskbar icon (`app.ico`/`app.png`). Add a new glyph
by adding a shape string to `_SHAPES`, not a new file.

**Coordinate system:** scene coordinates are physical canvas units
(e.g. inches), scaled to screen pixels only at paint time via the view's
transform. `CanvasSpec` (`app/project.py`) converts to a DPI-scaled scene
rect; rulers read the same scale factor. This keeps zoom/export
resolution-independent.

**`InteractiveItem` base (`app/canvas/interactive_item.py` +
`app/canvas/selection.py`):** every selectable marker (reference image,
focal point, note, movement line, light source, direction arrow,
vanishing point, horizon line) lives inside a `QGraphicsItemGroup` with
`setHandlesChildEvents(False)`. Each item calls `select_on_left_click()`
from its own `mousePressEvent` override before deferring to the base
class for drag handling. When adding a new selectable marker type, go
through this base rather than re-deriving click-to-select or lock state
per-class.

**Selection is NOT Qt's.** `QGraphicsItem.isSelected()`/`setSelected()`/
`QGraphicsScene.selectedItems()` were confirmed at runtime (a real
`QTest.mouseClick` and rubber-band simulation, not informal suspicion)
to not work *at all* for any item here — not unreliably, never — because
of the `setHandlesChildEvents(False)` group nesting above. `CanvasScene`
tracks selection itself: `selected_items()`/`set_selection()`/
`add_to_selection()`/`remove_from_selection()`, backed by a
`selection_changed` signal. Every consumer goes through this. If you're
adding a new item type, check `is_app_selected()` in `paint()` — using
real `isSelected()` will silently always read `False`. A separate
`item_activated` signal drives only the resize/rotate handle frame's
"primary item" notion; keep that concern separate from selection itself
(the Inspector used to also listen to `item_activated` directly, which
is exactly what let it disagree with the real selection during a
Shift-multi-select).

**`.atelier` file format (`app/atelier_io.py`):** a zip archive —
`manifest.json` (canvas spec, all layer data, guide toggles, lock state)
+ `images/<uuid>.png` per imported reference (original pixels, embedded
never linked) + `thumb.png`. See `ARCHITECTURE.md` for the full
`manifest.json` shape. Reference entries carry legacy `scale` alongside
newer `scale_x`/`scale_y` (free corner-drag resize) — older projects must
still load correctly; preserve that fallback when touching (de)serialization.

**Undo/redo (`app/canvas/undo_commands.py`):** a `QUndoStack` per project
covers *content* mutations only — add/delete, move/scale/rotate, crop,
note text edits, perspective mode switches, grid/opacity properties.
Lock and visibility toggles are deliberately direct, un-undoable calls —
undo represents reversing changes to the artwork, not application/UI
state. Commands follow a "capture on press, commit one command on
release, only if something changed" shape — don't push a command per
intermediate drag event.

**Crash recovery (`app/recovery.py`):** one autosave slot (not
project-keyed — multi-project-per-window is out of scope) in the
platform app-data dir via `QStandardPaths`, written periodically by
`MainWindow`'s autosave timer only when `undo_stack.isClean()` is false.
Removed on normal Save and clean shutdown, and immediately on Discard at
the recovery prompt — but *not* immediately on Recover: it's left in
place until the next real save, so a second crash before that save still
has a safety net. Don't reintroduce an unconditional delete after the
recovery choice; that was the bug.

**Recent files & start screen (`MainWindow._recent_files()`/
`_note_recent_file()`, `app/dialogs/start_screen.py`):** `QSettings()`
with no args — relies on the org/app name set on `QApplication` in
`main.py`. If constructing a `MainWindow`/`QApplication` outside
`main.py` (tests, ad hoc scripts), set an isolated
`QCoreApplication.setOrganizationName()`/`setApplicationName()` first, or
you'll read/write the real user's actual registry-backed settings.

**Handle frame (`app/canvas/handle_frame.py`):** one reusable
move/scale/rotate transform widget (eight resize handles + one rotate
handle) used by movable/scalable/rotatable items — currently reference
images. Corner drags default to independent width/height scaling
(free-transform); hold Shift to lock aspect ratio.

**Modes:** Draft (default, full editing) → Locked setup
(`Project.locked = True`, freezes every layer, explicit unlock required)
→ Projector mode (`app/projector/projector_window.py`, a separate
fullscreen `QWidget`/`QGraphicsView` rendering a *snapshot* of the
reference layer, deliberately decoupled from the live editing scene so
projector zoom/pan/rotation/flip can never corrupt the working project —
preserve that decoupling when touching projector code).

**Export (`app/atelier_io.py`, `app/dialogs/export_dialog.py`):** PNG/JPG
via `QGraphicsScene.render()` into a `QImage` at a chosen output DPI; PDF
via `QPdfWriter`, rendering the canvas plus a printed sidebar of
composition/lighting notes and canvas spec. One panel, not a dialog
chained to a second native Save dialog — destination is pre-filled from
the project name/folder and recomputed live as the format changes
(`ExportDialog._update_destination_preview()`); `MainWindow.
export_project()` reads `dialog.destination_path()` directly.

**Command palette (`app/dialogs/command_palette.py`, Ctrl+K):** built by
walking `menuBar().actions()` recursively
(`MainWindow._collect_actions()`), not a separately-maintained command
list. Put a new action on a real menu (even a submenu) and it's
automatically palette-searchable — there's no separate registration
step, and there shouldn't be one added.

## Current development phase

v1.0.0 is the last tagged release. Since then: the "Phase 0" foundation
work already mentioned above (undo/redo, crash recovery, interaction
consolidation, free corner-drag resize), followed by a full ground-up
UX/interaction redesign done in seven phases — design system foundation,
the selection-model fix, the Project Panel outliner, Inspector batch
editing, a unified export/new-painting flow, command
palette/drag-drop/snapping/context menus, and recent files/thumbnails/
start screen. None of it is version-tagged yet. See `CHANGELOG.md` for
the itemized list and `V2_ROADMAP.md` (particularly its Section 7,
added after the fact) for status against the original plan and what's
actually next — most of that document's own Phase 0 and Phase 1 are now
done; Phases 2–4 are where real future work still lives.
