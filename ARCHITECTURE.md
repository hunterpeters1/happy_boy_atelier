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
"arrange references" feeling precise rather than fiddly.

A *default* (no-modifier) rotate-handle drag additionally has its own
lighter-touch snap: `ROTATION_MAGNETIC_SNAP_DEG` (`reference_layer.py`,
`_update_handle_drag()`'s "rotate" branch) magnetically catches the
nearest cardinal orientation (0/90/180/270 — any multiple of 90) when
the drag is already within 4° of one, the same "on by default, Alt
bypasses" posture `_snap_position()` uses for position dragging (see
below), rather than a hard grid applied across the whole drag. Deliberately
independent of Shift's own 15°-grid hard snap, which is unchanged and
takes priority when held (both happen to agree at exact multiples of 90,
since 90 is itself a multiple of 15, but a Shift-held drag can land on
75°/105°/etc. that the default magnetic snap would never produce, and a
default-only drag well away from a cardinal — e.g. 40° — snaps to
neither). Scoped to reference images' own whole-item rotation only —
`MeasurementItem`'s Shift-held endpoint-angle-around-pivot snap (see Two-point
markers below) still only has the 15°-grid behavior, not this magnetic one.
A plain body drag (not a handle drag) also snaps the image's center to the canvas
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

  Also makes the desk truly transparent for the duration — a real
  per-pixel hole through to the desktop, not a fill color — via
  `CanvasScene.set_desk_transparent()` (`app/canvas/canvas_scene.py`):
  `drawBackground()` skips its desk `fillRect()` call entirely when the
  flag is set, leaving those pixels unpainted; the canvas rect and
  everything on it (paper, shadow, rivets, every placed item) keeps
  painting fully opaque underneath regardless, so only the void goes
  clear. Getting an actual hole requires two things to line up: (1)
  `MainWindow` itself needs `Qt.WA_TranslucentBackground`, enabling
  per-pixel alpha compositing on the top-level window at all; (2)
  `CanvasView.set_desk_transparent()` (`app/canvas/canvas_view.py`)
  clears its own fallback `backgroundBrush` (used only for the sliver
  beyond the scene's padded rect) to `Qt.NoBrush`, and sets
  `WA_TranslucentBackground` + disables `autoFillBackground` on the
  view's *viewport* widget specifically, since it would otherwise
  auto-paint an opaque backdrop before the scene's own `drawBackground()`
  gets a chance to leave the desk area untouched. The menu bar and status
  bar stay solid throughout, since both carry an explicit `background:`
  rule in `theme.py`'s stylesheet, which Qt still paints opaquely
  regardless of the top-level window's translucency attribute.

  `MainWindow`'s own `WA_TranslucentBackground` is set exactly once, in
  `__init__`, before the window is ever shown, and stays on permanently
  — it is **not** toggled per Focus Mode entry/exit. An earlier version
  toggled it at runtime alongside the rest of this method, matching how
  every other Focus Mode state here is snapshotted/restored; confirmed
  on a real Windows machine that this silently does not work, because
  per Qt's own docs the attribute is only reliable when set before the
  native window handle exists — toggling it after the window is already
  showing (as every `toggle_focus_mode()` call necessarily would, since
  `MainWindow` is the app's one persistent top-level window) doesn't
  actually change how the OS composites it. Setting it once at
  construction and controlling the *visible* effect purely through what
  `CanvasScene`/`CanvasView` paint or skip is the fix, and is harmless
  outside Focus Mode since normal Draft-mode rendering always paints the
  desk area fully opaque regardless of the flag.

  Also reveals a status-bar window-opacity slider
  (`MainWindow.focus_opacity_slider`, `QWidget.setWindowOpacity()`) — a
  separate, complementary control from the desk transparency above: the
  slider uniformly dims the *entire* window, chrome and canvas alike,
  while the desk stays a clean hole regardless of where the slider sits.

  Neither the transparency flag nor the opacity slider touches
  `self.meta.bg_color` (the project's saved desk color, `_change_desk_color()`)
  or `CanvasScene._bg_color` itself, and neither persists past the
  toggle — both reset on exit, same session-only footing as dock
  visibility.

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
- **Presets** — a named `{format, dpi, include_study_effect}` combo,
  recalled via a combo box beside the format radios. Deliberately never
  stores the destination, which is per-export by nature (a preset reused
  on a different painting shouldn't silently point at the last painting's
  folder). Serialized as a JSON string under one `QSettings` key
  (`_PRESETS_SETTINGS_KEY = "exportPresets"`) rather than relying on
  `QSettings`' own dict/bool marshalling, which isn't guaranteed to
  round-trip identically across every backend (registry/plist/INI).

## Reference library (`app/library.py`, `app/panels/library_panel.py`)

A personal, cross-project asset collection — explicitly **not** part of
any project's scene or `.atelier` file, so it can't become shadow project
state (same boundary Recent Files already sits on). `library.py` stores a
flat folder of copied-in images plus per-item thumbnails under
`QStandardPaths.AppDataLocation`, the same location pattern
`app/recovery.py` already uses. `LibraryPanel` is a `QDockWidget`,
constructed once in `MainWindow.__init__` (unlike the Project/Properties/
Swatches docks, which are rebuilt fresh on every `_new_project()` via
`_rebuild_workspace()`) and tabified with the Project Panel dock each time
a new one is built. Dragging a thumbnail out carries a real
`QUrl.fromLocalFile()` (`_LibraryList.mimeData()`), which `CanvasView`'s
existing OS drag-and-drop handler already accepts unmodified — placing a
library image is an ordinary `AddItemCommand`-backed import, not a new
undo path. Double-clicking a thumbnail does the same import via
`LibraryPanel.import_requested`, connected straight to
`MainWindow._import_image_paths()`.

## Phone upload integration (`app/dialogs/phone_upload_dialog.py`, `app/library.py`)

`uploader/` (see its own module docstring) is a fully standalone Flask
tool with its own venv/dependencies — that boundary is deliberate and
this integration doesn't cross it. Two separate pieces bridge it to the
main app without ever importing from it:

- **Launching it** (Help > Upload From Phone…, non-modal — a modal
  dialog would block watching the library update live, defeating the
  point). `PhoneUploadDialog` locates the uploader's own venv Python
  (`.venv/Scripts/python.exe`, falling back to a plain `venv/` name some
  existing setups use) and starts `uploader/app.py` as a `QProcess`.
  Since the uploader generates its own random PIN independently and has
  no PySide6 dependency to report it back through, the dialog instead
  *dictates* the PIN: it generates one itself and passes it via the
  `HAPPY_BOY_UPLOADER_PIN` env var, which `uploader/app.py` reads
  (falling back to its own random generation when unset, so a manual
  `python app.py` run is completely unaffected). The LAN URL is computed
  independently too, via the same UDP-socket "which interface would
  reach the internet" trick `uploader/app.py`'s own `get_lan_ip()` uses,
  duplicated rather than imported for the same standalone-boundary
  reason. A real QR code image renders via `qrcode` + its pure-Python
  `PyPNGImage` factory (no Pillow needed in the main app — the uploader
  already depends on Pillow for its own thumbnailing, but that's a
  separate venv). `QProcess` only reports "launched" vs. "exited," not
  "actually bound the port," so a short grace-period timer catches a
  fast failure (e.g. port 5000 already in use) and swaps to an error
  state instead of showing a QR code for a dead server. Closing the
  dialog terminates the process (`closeEvent()`); `MainWindow.closeEvent()`
  closes the dialog too, so the app never orphans a background uploader.

  `resources.uploader_root()` is why this works in a packaged exe, not
  just running from source: `project_root()` resolves to PyInstaller's
  `_MEIPASS` temp extraction dir in a frozen build, and `uploader/` is
  deliberately never bundled into that (it's a separate tool with its
  own dependencies) — a path built under `_MEIPASS` would point at a
  folder that can never exist. `uploader_root()` uses `sys.executable`'s
  actual on-disk location instead when frozen (stable across runs, unlike
  `_MEIPASS`), matching this project's documented build layout where the
  built exe lands at `<repo root>/dist/Happy Boy Atelier.exe` — one level
  below the repo root, with `uploader/` a sibling of `dist/`.

- **Getting uploads into the library live**: `library.sync_from_uploader()`
  scans `uploader_photos_dir()` for files not yet in the library index
  and imports each one through the exact same `add_image()` path a
  manual "Add Images to Library…" click uses — same copy, same
  thumbnail generation, same index entry. "Not yet in the library" is
  tracked via a new `LibraryItem.uploaded_from` field (the uploader's
  own generated filename, e.g. `20260813-172233-abc123.jpg`; `None` for
  every image added any other way, including every pre-existing library
  entry from before this field existed — the usual `.get(key, default)`
  back-compat fallback), so re-scanning never re-copies or
  re-thumbnails a photo already pulled in. `LibraryPanel` drives this
  with a 3-second `QTimer` poll (`_poll_for_uploads()`) rather than a
  `QFileSystemWatcher` — deliberately: `uploader/photos/` may not exist
  yet the first time the panel is built (the uploader creates it lazily
  on its own first run), which a watcher needs extra handling for, and a
  plain directory listing + set lookup is cheap enough that a few
  seconds of polling latency costs nothing noticeable while still
  reading as "live" to someone watching photos land mid-upload. Only
  calls `refresh()` when something actually changed, so an idle poll
  tick never disrupts the panel's current scroll position/selection.

## Project templates (`app/project_templates.py`)

A named `{width, height, unit, guides}` starting point for New Painting —
explicitly *not* reference images or composition/lighting content, since
auto-populating those would cross into "software infers the composition,"
out of scope by design. Saved via `MainWindow.save_as_template()` (File
menu) from the current project's `CanvasSpec` and
`GuidesLayerGroup.to_dict()`; applied via `NewProjectDialog`'s My
Templates list, which calls `_apply_template()` to fill width/height/unit
and stage the guides dict, returned by `selected_template_guides()` and
passed through to `MainWindow._new_project(spec, guides)`, which applies
it via `GuidesLayerGroup.load_from_dict()` after scene construction.
Picking a plain size preset afterward clears the staged guides back to
`None` — a template's guides shouldn't silently leak onto an unrelated
format choice. Same JSON-string-in-`QSettings` storage as export presets.

## About dialog (`app/dialogs/about_dialog.py`)

A `QDialog` styled entirely via `theme.py`'s existing global `QDialog`
rule (no bespoke stylesheet), replacing the previous plain
`QMessageBox.about()` call from `MainWindow._show_about()` (Options
menu — see below for why it's not called Help). Shows the app icon
(`resources.app_icon_path()`), name/version from `constants.py`, the
mission line, and credits — a pre-`MainWindow` launch splash screen was
explicitly scoped out as real added complexity for a fast-starting
desktop app.

## Options menu and Settings (`app/settings.py`, `app/dialogs/settings_dialog.py`)

The menu conventionally named "Help" is `&Options` here instead
(`MainWindow._build_menu_and_toolbar()`) — this app's Help-equivalent
menu was never really a documentation-lookup menu (there's no help
content to look up); it's this app's one catch-all for app-level, not
project-level, actions: Settings, the phone uploader, and app identity.

`app/settings.py` holds four standard, low-risk preferences — autosave
interval (with a 0 sentinel for "off," never handed to
`QTimer.setInterval()` directly, since a real 0ms interval would fire
continuously), default unit for New Painting, default export DPI, and
whether new windows show rulers by default. Persisted as plain scalar
`QSettings` keys (`settings/autosaveIntervalMs` etc.), not the
JSON-blob-in-one-key pattern `project_templates.py`/`export_dialog.py`'s
presets need — those exist to reliably round-trip nested dict/bool
structures across `QSettings` backends, which a single scalar doesn't
need. Every getter validates and falls back to the historical default on
a missing/corrupt/out-of-range value (never trusts a raw `QSettings`
read blindly) — same defensive posture `project_templates.py`'s
`_load_templates()` already takes for a corrupt index.

Deliberately **not** project state: nothing here is saved into any
`.atelier` file, none of it is undoable, and none of it retroactively
touches an already-open project or an already-built dialog — each
preference only seeds a *default* the next time it's relevant:
`NewProjectDialog` reads `settings.default_unit()` once at construction,
converting `CanvasSpec()`'s own default physical size (16×20 real
inches) into that unit via `constants.from_inches()` rather than
reinterpreting the raw 16/20 numbers in a different unit (which would
silently shrink the intended default canvas to a tiny ~6×8in-equivalent
if the preferred unit were, say, cm); `ExportDialog` reads
`settings.default_export_dpi()` the same way. The one preference that
*does* need live re-application is autosave, since it drives an
already-running `QTimer` on the one persistent `MainWindow` — accepting
`SettingsDialog` calls `MainWindow._apply_autosave_interval()`
immediately afterward, the same method `__init__` calls at startup, so
a changed interval (or turning autosave off) takes effect without a
restart.

`SettingsDialog` follows `NewProjectDialog`/`ExportDialog`'s own
accept/reject convention: fields seed from current settings, and only
Save (not Cancel) writes anything back.

## Current scope

Beyond the original MVP (create canvas → import & arrange references →
composition guides → perspective grids → lighting notes → save/reopen
`.atelier` → lock setup → PNG/JPG/PDF export), the app
now also covers: undo/redo, crash recovery, a real outliner-based
Project Panel, a unified selection model, an Inspector with editable
vanishing-point/horizon coordinates and multi-select batch editing, a
single-panel export flow with batch presets, a command palette, OS
drag-and-drop import, a cross-project reference library, project
templates, live two-click-tool previews, rotation/position/edge
snapping, right-click context menus, recent files with thumbnails, and a
proper About dialog. See `CHANGELOG.md` for the itemized history. Still
explicitly excluded per spec: AI generation, brush/paint tools, cloud
accounts, social/marketplace features. See `V2_ROADMAP.md` for what's
actually still ahead.
