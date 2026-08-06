# Happy Boy Atelier — Architecture

A digital drafting table for traditional painters: canvas planning, reference
arrangement, composition/perspective/lighting study, and projector-assisted
transfer. Not a paint program, not a generator.

## Stack

- Python 3.10+
- PySide6 (Qt 6) — `QGraphicsView`/`QGraphicsScene` as the drafting surface
- Zip + JSON for the `.atelier` project container (stdlib `zipfile`, no DB)
- `QPdfWriter` for the PDF planning sheet export

Qt's graphics view framework is the right tool here: it gives real coordinate
space, hit-testing, transforms, and layered z-ordering for free, which is
exactly what "arrange references / plan perspective / plan lighting" needs.

## Guiding principle

The **scene is the single source of truth**. There is no separate live data
model shadowing the graphics items — every custom `QGraphicsItem` carries its
own state (position, rotation, opacity, lock, notes, etc.). Serialization
walks the scene once at save time and rebuilds it once at load time. This
avoids two-state sync bugs, which matter more here than raw performance.

## File structure

```
happy_boy_atelier/
  main.py                     entry point, QApplication bootstrap
  app/
    constants.py               canvas format presets, units, layer ids, palette
    theme.py                   palette + QSS ("machined panel plate" look)
    icons.py                   line-icon set, rendered at runtime from SVG shape strings
    project.py                 dataclasses: CanvasSpec, ProjectMeta; pure (de)serialization helpers
    atelier_io.py               .atelier save/load (zip), thumbnail render/read, PNG/JPG/PDF export
    recovery.py                 crash-recovery snapshot lifecycle (see below)
    main_window.py              QMainWindow: menu, toolbar, docks, mode switching, lock-setup, recent files
    canvas/
      canvas_view.py            QGraphicsView: zoom (ctrl+wheel), pan (space+drag/middle-drag), rulers,
                                 OS drag-and-drop import, right-click context menu
      canvas_scene.py           QGraphicsScene: layer groups, tool routing, the app's own selection model
      interactive_item.py       InteractiveItem base: click-to-select, lock state, transform undo capture
      selection.py               select_on_left_click() — routes clicks into CanvasScene's selection API
      undo_commands.py          QUndoCommand classes (content mutations only — see Undo/redo below)
      handle_frame.py           reusable interactive transform box (move/scale/rotate handles)
      resize_math.py            corner-drag resize math (anchor/rotation-aware)
    layers/
      reference_layer.py        ReferenceImageItem + ReferenceLayerGroup (import, crop, opacity, lock,
                                 rotation/position snapping)
      composition_layer.py      FocalPointItem, MovementLineItem, NoteItem
      perspective_layer.py      HorizonLineItem, VanishingPointItem, PerspectiveGridItem (1/2/3-pt)
      lighting_layer.py         LightSourceItem, DirectionArrowItem, NoteItem (reused)
      guide_overlay.py          RuleOfThirdsOverlay, GoldenRatioOverlay (non-interactive, top z-order)
    panels/
      layers_panel.py           Project Panel dock: one outliner (every placed item, not just
                                 references), search filter, tool-activation buttons, perspective settings
      properties_panel.py       Inspector dock: contextual single-item editor + multi-select batch edit
    dialogs/
      new_project_dialog.py     one always-editable W/H/unit picker + orientation-filtered presets
      export_dialog.py          format/DPI/destination on one panel, no second native Save dialog
      command_palette.py        Ctrl+K fuzzy search over every QAction in the menu bar
      start_screen.py           launch-time recent-paintings picker with real thumbnails
    projector/
      projector_window.py       fullscreen projector mode + Lock Projection
  resources/
    icons/                      app.ico / app.png (window & taskbar icon only — the in-app toolbar/
                                 panel icon language lives in app/icons.py, not as files here)
  requirements.txt
  README.md
```

## Data model (`app/project.py`)

Pure dataclasses, no Qt dependency, used for (de)serialization only:

- `CanvasSpec(name, width, height, unit)` — real physical dimensions
- `ProjectMeta(created_at, modified_at, locked)`
- `to_dict()/from_dict()` pairs for every layer payload (see below)

## `.atelier` file format (`app/atelier_io.py`)

A `.atelier` file is a zip archive:

```
manifest.json        canvas spec, all layer data, guide toggles, lock state
images/<uuid>.png     one file per imported reference image, original pixels
thumb.png             cached thumbnail for the recent-files start screen
```

`thumb.png` is now actually generated — `atelier_io.render_thumbnail()` renders a
small preview (sized off the canvas's longer side) on every save, and
`atelier_io.read_thumbnail()` pulls just that entry back out without decoding the
full manifest/images, which is what the start screen's thumbnail grid uses.

`manifest.json` shape (abbreviated):

```json
{
  "format_version": 1,
  "canvas": {"name": "...", "width": 16, "height": 20, "unit": "in"},
  "meta": {"created_at": "...", "modified_at": "...", "locked": false},
  "references": [
    {"id": "uuid", "name": "harbor_dawn.jpg", "image": "images/uuid.png",
     "x":.., "y":.., "scale":.., "scale_x":.., "scale_y":..,
     "rotation":.., "opacity":.., "visible":true, "locked": false,
     "crop": [x, y, w, h]}
  ],
  "composition": {
    "focal_points": [{"kind": "primary|secondary", "x":.., "y":..}],
    "movement_lines": [{"points": [[x,y], ...]}],
    "notes": [{"x":.., "y":.., "text": "..."}]
  },
  "perspective": {
    "mode": "1pt|2pt|3pt", "horizon_y": .., "vanishing_points": [[x,y], ...],
    "grid_spacing": .., "opacity": .., "visible": true, "locked": false
  },
  "lighting": {
    "sources": [{"x":.., "y":..}],
    "arrows": [{"kind": "light|shadow", "x1":..,"y1":..,"x2":..,"y2":..}],
    "notes": [{"x":.., "y":.., "text": "..."}]
  },
  "guides": {"rule_of_thirds": false, "golden_ratio": false},
  "projector_state": {"opacity":.., "zoom":.., "pan": [x,y], "rotation":..,
                       "flip_h": false, "locked": false}
}
```

Images are embedded (never referenced by external path), satisfying the
"self-contained project file" requirement. Loading is fully offline.

Reference entries carry two back-compat fallbacks worth preserving when
touching (de)serialization: `"name"` (the Project Panel's display name,
`ReferenceImageItem.display_name`) falls back to the image `"id"` for
files saved before the field existed, and `"scale"` is a legacy
single-value mirror of `"scale_x"`/`"scale_y"` (free corner-drag resize)
for files saved before independent-axis scaling existed. Both exist so
older `.atelier` files keep opening looking the way they did.

## Coordinate system

Scene coordinates are physical units of the canvas (e.g. inches), scaled to
screen pixels only at paint time via the view's transform. This keeps
"actual painting dimensions" as the ground truth and makes zoom/export
resolution-independent. `CanvasSpec` converts to a DPI-scaled scene rect;
the ruler widgets read the same scale factor.

## Layer model

Each layer is a `QGraphicsItemGroup` owned by the scene, added in fixed
z-order (back to front): **Reference → Composition → Perspective →
Lighting → Guides (top, non-interactive)**. Each group exposes
`set_visible`, `set_locked`, `set_opacity` where applicable, driven by the
Project Panel (`app/panels/layers_panel.py` — a real outliner tree now,
one row per placed item across all five layers, not just reference
images; see `ARCHITECTURE.md` history / `CHANGELOG.md` Phase 3 for what
it replaced). Locking a layer clears `ItemIsMovable`/`ItemIsSelectable`
on its children rather than removing them from the scene, so a locked
layer is still visible and still exports.

The software never infers composition, perspective, or lighting — every
marker, line, and grid is placed by the artist. Automation is limited to
arithmetic (e.g. computing grid geometry from a vanishing point), never
aesthetic judgment.

## Selection model — deliberately not Qt's

`CanvasScene` tracks selection itself (`selected_items()`, `set_selection()`,
`add_to_selection()`, `remove_from_selection()`, backed by a plain list and a
`selection_changed` signal) instead of using
`QGraphicsItem.isSelected()`/`setSelected()`/`QGraphicsScene.selectedItems()`.
This isn't a style preference — those Qt APIs were confirmed at runtime
(a real `QTest.mouseClick`/rubber-band simulation, not just informal
suspicion) to not work **at all** for any item here, because every layer
is a `QGraphicsItemGroup` with `setHandlesChildEvents(False)`. Every
consumer (the Inspector, Delete, the selected-item paint highlight,
`InteractiveItem.set_locked()`) goes through `CanvasScene`'s own API. If
you're adding a new selectable item type, checking `is_app_selected()`
(set via `InteractiveItem.set_app_selected()`) in its `paint()` method is
the equivalent of checking `isSelected()` in a normal Qt app — using the
real `isSelected()` here will silently always read `False`.

A second, separate signal, `item_activated`, drives only the
resize/rotate handle frame's notion of "primary" selected item — keep
these two concerns apart; the Inspector used to also listen to
`item_activated` and that's exactly what let it disagree with the actual
selection during a Shift-multi-select.

## Interaction: the handle frame

`handle_frame.py` implements one reusable interactive transform widget used
by any movable/scalable/rotatable item (currently reference images): eight
resize handles at the corners/edges of the item's bounding box plus one
rotate handle above it. Dragging a corner updates a `QTransform` combining
scale; dragging the rotate handle updates rotation around the item's
center, snapping to 15° increments while Shift is held. This keeps
"arrange references" feeling precise rather than fiddly. A plain body
drag (not a handle drag) also snaps the image's center to the canvas
center or to another visible reference image's center, within a
zoom-independent catch radius — bypassed by holding Alt/Option, and
guarded so it only applies during an actual interactive drag, never to a
programmatic `setPos()` from undo/redo, batch align, or the Inspector's
position fields.

## Modes

- **Draft mode** (default): full editing, all panels visible.
- **Locked setup**: `Project.locked = True` freezes every layer
  (`ItemIsMovable`/`ItemIsSelectable` cleared everywhere); a status-bar
  banner and toolbar toggle make the state unmistakable. Unlock requires an
  explicit action (no accidental edits).
- **Projector mode**: separate fullscreen `QWidget` (own window, own
  `QGraphicsView`) rendering the reference layer + optional guide overlay,
  with its own opacity/zoom/pan/rotation/flip and a "Lock Projection"
  toggle that disables further transform input until unlocked.

## Undo/redo

A `QUndoStack` per `CanvasScene`, scoped to *content* mutations only —
add/delete, move/scale/rotate, crop, note text edits, perspective mode
switches, grid/opacity properties, batch-edit and align operations
(`app/canvas/undo_commands.py`). Lock and visibility toggles are
deliberately direct, un-undoable calls — undo represents reversing
changes to the artwork, not application/UI state. Commands follow a
"capture on press, commit one command on release, only if something
changed" shape; multi-item operations (multi-delete, multi-file import,
batch align/opacity/scale) are wrapped in a single
`beginMacro()`/`endMacro()` so one undo reverses the whole batch.

## Crash recovery

One autosave slot (not project-keyed — multi-project-per-window is out
of scope) in the platform app-data dir via `QStandardPaths`
(`app/recovery.py`), written periodically by `MainWindow`'s autosave
timer only when the undo stack isn't clean. Cleared on Discard (or a
failed read) immediately at the recovery prompt, but on Recover it's
deliberately left in place until the *next actual save* clears it — a
second crash between recovering and saving still has a safety net.

## Project lifecycle: recent files, thumbnails, start screen

Recent files are tracked via `QSettings` (`MainWindow._recent_files()`/
`_note_recent_file()`, capped at 10, entries for since-deleted files
silently dropped) — recorded on every successful Save and Open, surfaced
as `File > Open Recent` (lazily rebuilt on `aboutToShow`, so it's never
stale) and, if any exist, an `app/dialogs/start_screen.py` dialog shown
at launch instead of dropping straight into a blank canvas. Each entry
shows a real thumbnail (`atelier_io.render_thumbnail()`/
`read_thumbnail()` — see the `.atelier` format section above). A fresh
install with no recent files skips the start screen entirely, so first
launch still costs zero extra clicks.

## Discoverability: the command palette

`app/dialogs/command_palette.py` (Ctrl+K) is a fuzzy-searchable list
built by walking `MainWindow.menuBar().actions()` recursively
(`MainWindow._collect_actions()`) rather than maintaining a second,
separately-authored command list — anything added to a menu is
automatically searchable with no extra step. This is the general fix
for the class of bug where `CanvasView.set_ruler_visible()` existed with
no menu item, toolbar button, or shortcut pointing to it at all; when
adding a new action, putting it on a real menu (even a submenu) is what
makes it palette-searchable, not a separate registration step.

## Icons

`app/icons.py` renders a small single-weight line-icon set at runtime
from hand-authored SVG shape strings (`QSvgRenderer` → `QPixmap`), tinted
per `QIcon` mode so the same glyph reads on both a toolbar button's
resting dark background and its checked/brass-filled state. This is the
"brass/graphite line-art" icon language `resources/icons/` was always
meant to hold per the file-structure comment below, but which was never
actually built — that folder holds only the window/taskbar icon
(`app.ico`/`app.png`).

## Export

- PNG/JPG: render the scene rect at a chosen output DPI via
  `QGraphicsScene.render()` into a `QImage`.
- PDF planning sheet: `QPdfWriter` page with the rendered canvas plus a
  printed sidebar of notes (composition/lighting) and canvas spec — a
  physical reference sheet to bring to the easel.
- One export panel (`app/dialogs/export_dialog.py`), not a settings
  dialog chained to a second native Save dialog — destination is
  pre-filled from the project name and (if saved before) its folder,
  recomputes live as the format radio changes, and is sanitized against
  filesystem-illegal characters.

## Current scope

Beyond the original MVP (create canvas → import & arrange references →
composition guides → perspective grids → lighting notes → save/reopen
`.atelier` → projector mode → lock setup → PNG/JPG/PDF export), the app
now also covers: undo/redo, crash recovery, a real outliner-based
Project Panel, a unified selection model, an Inspector with editable
vanishing-point/horizon coordinates and multi-select batch editing, a
single-panel export flow, a command palette, OS drag-and-drop import,
live two-click-tool previews, rotation/position snapping, right-click
context menus, and recent files with thumbnails. See `CHANGELOG.md` for
the itemized history. Still explicitly excluded per spec: AI generation,
brush/paint tools, cloud accounts, social/marketplace features. See
`V2_ROADMAP.md` for what's actually still ahead.
