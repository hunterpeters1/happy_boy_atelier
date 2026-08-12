# Happy Boy Atelier — Architecture

A digital drafting table for traditional painters: canvas planning,
reference arrangement, and composition/perspective/lighting study. Not a
paint program, not a generator.

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
      point_handle.py            TwoPointHandle: shared draggable endpoint handle for two-point
                                 markers (DirectionArrowItem, MeasurementItem)
      context_toolbar.py         SelectionContextToolbar: floating single-item action toolbar
                                 (Duplicate/Flip/Lock/Delete), a CanvasView.viewport() child widget
      resize_math.py            corner-drag resize math (anchor/rotation-aware)
    layers/
      reference_layer.py        ReferenceImageItem + ReferenceLayerGroup (import, crop, opacity, lock,
                                 rotation/position snapping)
      composition_layer.py      FocalPointItem, MovementLineItem, MeasurementItem, NoteItem
      perspective_layer.py      HorizonLineItem, VanishingPointItem, PerspectiveGridItem (1/2/3-pt)
      lighting_layer.py         LightSourceItem, DirectionArrowItem, NoteItem (reused)
      guide_overlay.py          RuleOfThirdsOverlay, GoldenRatioOverlay (non-interactive, top z-order)
    panels/
      layers_panel.py           Project Panel dock: one outliner (every placed item, not just
                                 references), search filter, tool-activation buttons, perspective settings
      row_hover.py               hover-reveal for Project Panel item-row icons (fades _RowButtons
                                 via app/scrollbars.OpacityFade, not a QStyledItemDelegate)
      dock_title_bar.py          custom QDockWidget title bar — same look as the QSS default, plus a
                                 pair of corner rivets (see Icons/visual-language section below)
      properties_panel.py       Inspector dock: contextual single-item editor + multi-select batch edit
    dialogs/
      new_project_dialog.py     one always-editable W/H/unit picker + orientation-filtered presets
      export_dialog.py          format/DPI/destination on one panel, no second native Save dialog
      command_palette.py        Ctrl+K fuzzy search over every QAction in the menu bar
      start_screen.py           launch-time recent-paintings picker with real thumbnails
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
  "guides": {"rule_of_thirds": false, "golden_ratio": false}
}
```

Images are embedded (never referenced by external path), satisfying the
"self-contained project file" requirement. Loading is fully offline.
Older files saved while projector mode existed may still carry a
`"projector_state"` field — it's simply ignored on load and dropped on
next save.

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
center, to another visible reference image's center, or — only while the
corresponding guide is actually turned on — to a Rule of Thirds/Golden
Ratio intersection (`ReferenceImageItem._snap_position()` in
`app/layers/reference_layer.py`; the intersection fractions are read
straight off `GuidesLayerGroup.thirds`/`.golden`, not recomputed
separately, so the two can't drift apart). All of this is within a
zoom-independent catch radius — bypassed by holding Alt/Option, and
guarded so it only applies during an actual interactive drag, never to a
programmatic `setPos()` from undo/redo, batch align, or the Inspector's
position fields.

## Two-point markers: the shared endpoint handle

`DirectionArrowItem` (`app/layers/lighting_layer.py`) and `MeasurementItem`
(`app/layers/composition_layer.py`, the on-canvas ruler/angle tool) are
both two-endpoint markers whose endpoints drag independently after
placement, via small square handles — `TwoPointHandle`
(`app/canvas/point_handle.py`). Extracted to that shared location (not
either layer module) specifically because composition_layer.py and
lighting_layer.py already have a one-way import relationship (lighting
imports `NoteItem` from composition), so a handle class defined in either
layer module couldn't be reached from the other without a cycle. `owner`
just needs to expose `points()`/`set_point(which, local)`/
`set_points(points)`/`color()`; the handle owns press/move/release, and
release pushes exactly one `SetPropertyCommand(owner.set_points, old, new,
label)` if anything actually changed. `MeasurementItem.set_point()` adds
one thing `DirectionArrowItem` doesn't: while Shift is held, the dragged
endpoint's angle around the *other* endpoint snaps to the nearest
`ROTATION_SNAP_DEG` (`_snap_to_angle()`, same round-to-nearest pattern
`reference_layer.py`'s rotate-handle snap already uses, applied to an
endpoint-around-a-pivot instead of a whole-image rotation). A
`MeasurementItem`'s length/angle label is never stored — `display_label()`
computes it fresh from the two points every time, in the canvas's own
display unit (`CanvasSpec.unit`), so there's no shadow value that could
drift from the geometry.

## Modes

- **Draft mode** (default): full editing, all panels visible.
- **Locked setup**: `Project.locked = True` freezes every layer
  (`ItemIsMovable`/`ItemIsSelectable` cleared everywhere); a status-bar
  banner and toolbar toggle make the state unmistakable. Unlock requires an
  explicit action (no accidental edits).
- **Focus Mode** (`MainWindow.toggle_focus_mode()`, View menu,
  Ctrl+Shift+F): a UI-chrome-only toggle, not a `Project`/undo-stack
  state — hides the toolbar and every dock so only the canvas and menu
  bar remain, then restores each dock's exact prior visibility on exit
  (not a blanket re-show, since Properties/Swatches are tabified and only
  one may have been the visible/active tab going in). The structural
  lesson taken from PureRef's canvas-first identity without adopting its
  chrome-less floating-window model, which doesn't fit this app's docked,
  project-based shape.

Projector mode (a separate fullscreen tracing-aid window) existed here
through the UX redesign below but has been removed entirely, along with
its `.atelier` `projector_state` field — see git history if reviving it.

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

## Hover-reveal row icons (`app/panels/row_hover.py`)

The Project Panel's item-row eye/lock (and, where present, reorder)
buttons rest at a dim opacity and rise to full opacity only while the
pointer is over that row — previously always fully visible, which read as
UI clutter across a painting with many placed items. `layers_panel.py`'s
own docstring long assumed this needed a custom `QStyledItemDelegate`
rewrite; it doesn't. `_RowButtons` is already a persistent `QWidget`
embedded per row via `setItemWidget()`, so it can be faded with the exact
`OpacityFade` class `app/scrollbars.py` already uses for scrollbar
handles (same 150ms fade / 500ms hide-delay timing, reused not
reinvented — both symbols were promoted from that module's own
underscore-private names to public ones specifically so this second
consumer could import them without duplicating the animation
bookkeeping). `row_hover.py` is a thin `QObject` event filter on the
tree's viewport that tells whichever row's `_RowButtons` is under the
cursor to reveal itself and the previously-hovered one to rest back down;
`_RowButtons` itself owns `is_default_state()`/`set_row_hovered()` and
keeps a non-default row (one whose lock/visibility was actually toggled
away from the default) at a near-full rest opacity rather than fading it
to near-invisible — losing the only visual cue that an item is
locked/hidden until you happen to hover it would be a regression, not
polish. Layer-header rows are never marked `hoverable` and stay
full-opacity structural navigation, not per-item detail.

## Contact-sheet thumbnails (`_reference_thumbnail_icon()` in `layers_panel.py`)

Reference-image rows show a small square crop of the actual photo instead
of the generic "image" glyph every other marker type still uses — the
outliner reads closer to a photographer's contact sheet than a generic
file tree. Built from the same downscaled proxy `paint()` already reads
(`ReferenceImageItem._get_display_pixmap()`) — no extra render. The
proxy's own crop sub-rect is copied out, scaled with
`Qt.KeepAspectRatioByExpanding`, then center-cropped to an exact square;
plain scale-to-fit would visibly distort a non-square photo. Recomputed
on every `refresh_structure()` rebuild rather than cached separately —
that's already a full tree rebuild on any relevant change, so a second
cache-invalidation path isn't worth adding.

## Drag-to-reorder (`_ReorderableTree` in `layers_panel.py`)

`StackedLayerMixin` plus `ReorderItemCommand`/`SendToBackCommand`/
`BringToFrontCommand` already gave every reorderable layer group real
forward/backward/to-back/to-front operations, wired to `_RowButtons`'
arrow buttons — the only missing piece was the drag *gesture* itself.
`_ReorderableTree` (a small `QTreeWidget` subclass used in place of a
plain one) enables Qt's `InternalMove` drag/drop mode for the gesture,
drop-indicator line, and accept/reject cursor only — its `dropEvent()`
override never lets Qt actually move a `QTreeWidgetItem`; doing so would
make the tree's own item order a second source of truth alongside each
layer group's bucket list. Instead it computes the target bucket index
(`LayersPanel._handle_reorder_drop()`) and pushes one new
`MoveItemToIndexCommand` (`app/canvas/undo_commands.py`, same
capture-on-redo/restore-on-undo shape as `SendToBackCommand`), then lets
the resulting `refresh_structure()` (already wired to
`undo_stack.indexChanged`) redraw the tree from the corrected model —
so the two can never drift apart. Item rows list top-to-bottom in *print*
order (top row = prints on top), the layer group's own bucket order
*reversed* (see `layers_panel.py`'s own module docstring), so
`_handle_reorder_drop()` computes the desired final top-to-bottom row
order directly from the current rows and reverses it back for the target
index, rather than doing delta arithmetic across the two orderings.
Rejects: dropping on empty space, on a different layer section
(`source_row.parent() is not target_row.parent()` — this single check
also transparently rejects drops on header/separator rows, which are
always top-level with `parent() is None`), or a non-linear `OnItem`/
`OnViewport` drop indicator. Only genuinely reorderable rows
(`_add_item_row()` called with a real `group`) keep
`Qt.ItemIsDragEnabled`/`ItemIsDropEnabled` — every other row (headers,
separators, tool/toggle/settings rows, and perspective's non-reorderable
horizon/vanishing-point item rows) has both cleared, since
`QTreeWidgetItem`'s own default flags make every row drag/drop-capable
otherwise.

## Floating selection context toolbar (`app/canvas/context_toolbar.py`)

`SelectionContextToolbar` is a small `QWidget` parented to
`CanvasView.viewport()` (not a top-level window, so no OS floating-window
quirks) showing Duplicate/Flip Horizontal/Lock/Delete for whichever
single item is currently selected, positioned just below its
`sceneBoundingRect()` — below, not above, so it never collides with
`HandleFrame`'s rotate handle. Driven by `CanvasScene.selection_changed`;
deliberately scoped to exactly one selected item (multi-select already
has the Properties panel's Batch Edit section for bulk actions, so this
widget's job is purely cutting eye-travel for the common single-selection
case). Every button calls the exact same method the right-click context
menu or Edit menu already calls (`item.flip_horizontal()`,
`scene.duplicate_selected_items()`, `scene.delete_selected_items()`,
`item.set_locked()`) — an additional low-travel trigger surface, not new
action logic, so undo/redo behaves identically regardless of which
surface was used. Repositions on `zoom_changed` and both scrollbars'
`valueChanged` (pan) so it tracks the selection through any view
transform change, not just a selection change. `CanvasView.
mousePressEvent()`/`mouseReleaseEvent()` call `set_suspended(True)`/
`(False)` around every canvas press — a body drag can move the selected
item right through where the toolbar is sitting, and it must never steal
a press meant for the item/canvas underneath it; presses on the
toolbar's own buttons never reach `CanvasView` at all, since they're
delivered to the toolbar's child widgets directly. Styled with the
existing `role="compact"` `QToolButton` QSS (hairline border, brass
hover/checked) rather than a new widget style. Locking the selected item
deselects it (`InteractiveItem.set_locked()`'s existing behavior — a
locked item isn't interactively selectable), so clicking Lock here
correctly makes the toolbar disappear along with the item's selection;
that's the intended consequence of existing lock semantics, not a bug
this widget needs to work around.

## Hardware motifs: rivets and trim marks

Two small `QPainter`-level additions, both reusing painters/pens/fonts
already set up at their call sites (no new assets, no gradients, no
rounded shapes, matching this file's "machined panel plate" rule):

- **Corner rivets** — `CanvasScene._draw_corner_rivets()` paints four
  small filled `C.COLOR_LINE` marks just inside each canvas corner
  (`drawBackground()`), and `app/panels/dock_title_bar.py`'s
  `DockTitleBar` (set via `QDockWidget.setTitleBarWidget()`, replacing
  the QSS-only default title bar for the Project/Properties/Swatches
  docks) paints the same pair at its own left/right edges in its
  `paintEvent()`. Deliberately neutral-line-colored, not brass — rivets
  read as structural hardware, not an interactive accent. `C.RIVET_RADIUS_PX`
  is the one shared size constant between the two call sites.
- **Trim marks + dimension callout** — `CanvasView.drawForeground()`
  (the same view-space painter already drawing the brass ruler ticks)
  gains short L-shaped crop-mark ticks just outside each canvas corner
  (`_draw_trim_marks()`, the actual print-production/technical-drawing
  trim-mark convention) plus a monospace readout of the canvas's real
  physical dimensions in the artist's chosen unit near the bottom-right
  corner (`_draw_dimension_callout()`, reading `CanvasSpec.width`/
  `.height`/`.unit` directly — those are already in the artist's chosen
  unit, no conversion needed). Turns the canvas from "a rectangle" into a
  labeled technical artifact — the app's ownable identity marker, since
  neither PureRef's chrome-less canvas nor Milanote's card-based one
  frames its content this way.

## Value Check (`app/canvas/study_blur.py`, `app/layers/reference_layer.py`)

A non-destructive per-image desaturate, extending the Study Blur family
(Blur/Line Clarity) with a third slider rather than a parallel mechanism:
`apply_study_effect()` gained a `grayscale_pct` parameter, applied
*before* blur/clarity so a squint-test and a value-check compose in one
pass sharing one processed-pixmap cache (`ReferenceImageItem.
_processed_cache_key` is now `(blur, clarity, grayscale, crop)` — note the
index shift this caused in `_get_processed_display_pixmap()`'s own
crop-changed check). `ReferenceImageItem.grayscale_amount()`/
`set_grayscale_amount()` mirror `blur_amount()`/`set_blur_amount()`
exactly, including reuse of the same `set_defer_blur_refresh()` flag
during an active Properties-panel slider drag — one deferred-recompute
flag already covers "any of the three sliders is mid-drag." Serialized as
a `"grayscale"` key on reference entries, defaulting to `0.0` for every
pre-existing `.atelier` file; exported only when the artist opts in via
the Export dialog's existing "Include Study Blur effect" checkbox
(`export_study_effect`) — no second export flag.

`CanvasScene.toggle_grayscale_all()` (Edit menu: "Toggle Value Check (All
References)") is a macro over the same per-item `SetPropertyCommand` the
Properties panel's slider already pushes, one command per visible+
unlocked reference image — there is deliberately no second, scene-wide
boolean anywhere; "is the layer grayscale" is derived from actual
per-item state (majority already on → turn all off, else turn all on)
each time the action runs, not shadowed.

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
`.atelier` → lock setup → PNG/JPG/PDF export), the app
now also covers: undo/redo, crash recovery, a real outliner-based
Project Panel, a unified selection model, an Inspector with editable
vanishing-point/horizon coordinates and multi-select batch editing, a
single-panel export flow, a command palette, OS drag-and-drop import,
live two-click-tool previews, rotation/position snapping, right-click
context menus, and recent files with thumbnails. See `CHANGELOG.md` for
the itemized history. Still explicitly excluded per spec: AI generation,
brush/paint tools, cloud accounts, social/marketplace features. See
`V2_ROADMAP.md` for what's actually still ahead.
