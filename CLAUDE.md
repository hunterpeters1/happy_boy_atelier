# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This project has more than one agent working on it — see `TEAM_ROLES.md`
for the vision statement, top-level architecture rules, and current
agent roles (Claude: architecture, Hermes: implementation). This file
(`CLAUDE.md`) is the detailed engineering reference `TEAM_ROLES.md`
points back to; it's loaded automatically for Claude Code sessions, but
not for other agents, so don't assume its contents are already known.

Read `README.md` before starting any task — it documents the full
user-facing feature scope, including features that exist in the code but
aren't obviously discoverable from the UI alone. Don't propose or plan a
"new" feature without first checking whether it already exists there.

Check the repo root for a `proposal.txt` at the start of any session —
Hermes drops audits, findings, or questions there for architecture
review (per `TEAM_ROLES.md`'s division of labor). It's not committed
(stays untracked in `git status`), so nothing in `git log` will surface
its presence or flag that it changed. If it exists, review it before
starting other work — it may be blocking Hermes on an answer.

## What this is

Happy Boy Atelier — a Windows desktop app (PySide6/Qt) for traditional
painters to plan a physical painting before touching canvas: pick a
format, arrange reference photos, and plan composition/perspective/
lighting. It is **not** a paint program and **not** an AI image
generator — every mark is placed by the artist; the software never
infers composition, perspective, or lighting. AI generation, a brush
engine, cloud accounts, and social/marketplace features are explicitly
out of scope. Projector mode (a fullscreen tracing-aid view) was removed
— see git history if you need to resurrect it.

This is a git repository (initialized partway through the UX redesign
below — there is no history before the "Baseline commit before UX
redesign" commit). Local repo-scoped `user.name`/`user.email` are set;
don't touch global git config.

## Commands

Run everything from the repo root, with the venv active.

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt          # PySide6, numpy, qrcode, pypng
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

`qrcode`/`pypng` were added to the main app's own `requirements.txt` for
the in-app phone-upload launcher's QR code (`pypng`'s pure-Python
`PyPNGImage` factory avoids needing Pillow in the main app). `uploader/`
is a fully separate Flask tool with its own venv, dependencies
(`uploader/requirements.txt`: Flask, Pillow, pillow-heif, qrcode) and
test suite (`uploader/tests/test_app.py`, its own pytest run from inside
`uploader/`) — never import from it, and don't fold its dependencies
into the main app's `requirements.txt`. See "Phone upload integration"
below for how the two stay bridged without crossing that boundary.

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
PyInstaller doesn't cross-compile. `scripts/` doesn't exist — there is no
build-helper directory, deliberately (see above); `Happy Boy Atelier.spec`
(with spaces, an older/stale spec file this note used to tell you to
avoid in favor of `HappyBoyAtelier.spec`) has been deleted entirely, so
there's now only the one spec file.

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
(free-transform); hold Shift to lock aspect ratio. The same manager also
owns four edge (left/right/top/bottom midpoint) handles for crop —
`HandleFrame.set_crop_handles_visible()` — shown any time a reference
image is selected and unlocked, same condition as the corner/rotate
handles, **not** gated on whether a crop is already applied: dragging an
edge inward from the full-image bounds is how the first crop gets
created, so gating on "crop already non-full" (a real bug caught in
review right after v1.3 landed) makes cropping impossible for every
freshly-imported image. Actual hit-testing/drag handling for both corner
and edge handles lives in `ReferenceImageItem` itself, not on the handle
items — see the corner-handle docstring in `handle_frame.py` for the Qt
child-over-transformed-parent reason. Crop drags commit one
`CropItemCommand` on release (`ReferenceImageItem._commit_crop()`), the
same pattern as move/resize/rotate's `TransformCommand`.

**Interactive painting vs. export/render (`app/layers/reference_layer.py`,
`app/canvas/canvas_scene.py`, `app/atelier_io.py`):** `ReferenceImageItem`
never draws its full-resolution `_source_pixmap` on screen — `paint()`
draws a cached, capped-size (`MAX_DISPLAY_DIM`) downscaled proxy instead
(`_get_display_pixmap()`), regenerated only when the crop changes. A
multi-megapixel camera photo bilinear-resampled on every repaint frame of
every drag/resize was the main cost behind sluggish interaction; this
(plus `InteractiveItem.setCacheMode(DeviceCoordinateCache)` in the shared
base class, and `CanvasView`'s `SmartViewportUpdate` instead of
`FullViewportUpdate`) is what fixed it. Export/thumbnail rendering must
still use the full-resolution source — `CanvasScene.rendering_for_export`
is an explicit flag set/reset in a `try`/`finally` around every
`scene.render()` call in `atelier_io.py`, which `paint()` checks. **Not**
the `widget` parameter Qt passes to `paint()` — confirmed at runtime that
`widget is None` is not a reliable "is this an export" signal (it came
through `None` even for normal on-screen `QGraphicsView` painting under
the offscreen QPA platform tests run under), which is why this explicit
flag exists instead of the more obvious-looking shortcut.

**Study Blur / Value Check (`app/canvas/study_blur.py`):** a
per-reference-image, non-destructive "squint test" filter family — blur
the displayed image while boosting the contrast of dark lines/edges so
they stay legible even at very low contrast, plus a third sibling,
Value Check, that desaturates toward luminance for judging value
relationships without color — via `apply_study_effect(image, blur_pct,
clarity_pct, grayscale_pct)`, a pure numpy function (this app's first
dependency beyond PySide6 — `qrcode`/`pypng` were added later, for the
phone-upload QR code) with no Qt/item coupling, same spirit as
`resize_math.py`. Grayscale is applied *first*, before blur/clarity, so
all three compose in one pass sharing one cache rather than needing a
second pipeline. `ReferenceImageItem.blur_amount()`/`line_clarity()`/
`grayscale_amount()` are plain 0-100 float fields (`to_dict`/`from_dict`
keys `"blur"`/`"line_clarity"`/`"grayscale"`, each defaulting to 0.0 for
every pre-existing `.atelier` file) driving a separately-cached processed
pixmap (`_get_processed_display_pixmap()`/`_refresh_processed_pixmap()`),
processed at an even smaller `BLUR_WORKING_DIM` than the display proxy
above and scaled back up — the numpy pass is real work (~100ms+ even
capped), measured at the better part of a second at full display-proxy
resolution. `_processed_cache_key` is `(blur, clarity, grayscale, crop)`
— crop lives at index 3, not 2, so if you're touching
`_get_processed_display_pixmap()`'s own crop-changed check, re-check that
index rather than assuming it's still where it was before grayscale was
added. Recomputing this synchronously on every Properties-panel slider
tick would reintroduce exactly the per-frame-cost problem the paragraph
above fixed, so `ReferenceImageItem.set_defer_blur_refresh()` lets
`PropertiesPanel` suppress the setters' normal immediate-recompute
behavior for the duration of an active slider drag, batching to a
debounced timer plus one forced recompute on release — every *other*
caller of `set_blur_amount()`/`set_line_clarity()`/
`set_grayscale_amount()` (undo/redo, project load) is not deferred and
always recomputes immediately, or the cache goes stale relative to the
actual current values. Never baked into exports unless the artist opts in
via the Export dialog's checkbox (`ExportDialog.include_study_effect()` →
`CanvasScene.export_study_effect`, a second flag alongside
`rendering_for_export`, also reset in `finally` — thumbnails must never
pick it up). `CanvasScene.toggle_grayscale_all()` (Edit menu) is a macro
of the same per-item `SetPropertyCommand` the slider itself pushes over
every visible+unlocked reference image — there's no second, scene-wide
grayscale flag anywhere; "mostly on" vs. "mostly off" is derived from
actual per-item state each call.

**Modes:** Draft (default, full editing) → Locked setup
(`Project.locked = True`, freezes every layer, explicit unlock required).
Focus Mode (`MainWindow.toggle_focus_mode()`, View menu, Ctrl+Shift+F) is
a separate, UI-chrome-only toggle — not `Project`/undo-stack state —
hiding the toolbar and every dock down to just the canvas and menu bar,
restoring each dock's exact prior visibility (not a blanket re-show) on
exit. Projector mode (a separate fullscreen snapshot view of the
reference layer) existed through the UX redesign below but has since
been removed entirely, including its `.atelier` `projector_state`
manifest field — don't reintroduce a manifest field or menu item for it
without checking
whether the removal was deliberate for the specific task at hand.

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

**Themes & Appearance (`app/themes.py`, `app/theme.py`):** four
`ThemeMode`s — Current Configuration (the original brass/graphite look,
kept selectable so switching is never a one-way door), Dark, Light
(default), and Crazy Hack Mode (black/terminal-green, monospace chrome).
`themes.apply_palette(mode)` **mutates `constants.py`'s `COLOR_*`/
`FONT_FAMILY_UI` attributes in place** — every module reads colors as
`C.COLOR_X` (attribute lookup on the shared module object, not a
value copied at import time), so this takes effect everywhere
immediately, no restart needed, once the caller also re-runs
`theme.apply_theme()` to regenerate the QPalette/stylesheet and repaints
the canvas (see `MainWindow._apply_theme()`). The one exception is
already-baked icon `QIcon`s (`icons.icon()` bakes a `QPixmap` from the
current colors at call time) — those only catch up on next restart,
deliberately, rather than tracking every icon consumer just to recolor a
stroke line. Fixed canvas/marker colors (`COLOR_CANVAS`, `COLOR_FOCAL_*`,
`COLOR_PERSPECTIVE`, `COLOR_LIGHT`/`COLOR_SHADOW`, `COLOR_GUIDE`) are
**not** theme-dependent — they represent the physical painting surface
and the artist's own marks, which mean the same thing regardless of UI
theme, so `themes.py`'s palettes never touch them.

**Crazy Hack Mode's extras (`app/debug_tools.py`, `app/hacker_status.py`,
`MainWindow._set_hack_mode_active()`):** a Debug menu (verbose console
logging, a live scene-stats status-bar readout via
`debug_tools.scene_stats()`, a "Reload Stylesheet" action) and a fake
green-on-black "hacker" status-bar widget with rotating messages
(`resources/hacker_messages.txt` — one per line, editable with no code
change or restart needed, hot-reloaded each time Hack Mode turns on) and
jittering fake progress bars — purely decorative. Both are created and
torn down (not just hidden) on theme switch, so their `QTimer`s don't
keep firing while some other theme is active.

**Options menu & Settings (`app/settings.py`,
`app/dialogs/settings_dialog.py`):** the conventionally-"Help" menu is
`&Options` here — this app's Help-equivalent was never a
documentation-lookup menu, it's the one catch-all for app-level (not
project-level) actions: Settings, the phone uploader launcher, and About.
`settings.py` holds four low-risk preferences as plain scalar `QSettings`
keys (not the JSON-blob pattern presets/templates need) — autosave
interval (`AUTOSAVE_OFF_MS = 0` is a sentinel for "off," never handed to
`QTimer.setInterval()` directly, since a real 0ms interval fires
continuously), default New Painting unit, default export DPI, whether
new windows show rulers by default — plus a fifth, `futuristic_accents_enabled()`
(default on), covered below. **None of this is project state**: nothing
here is saved into any `.atelier` file, none of it is undoable, and none
of it retroactively touches an already-open project or already-built
dialog — each preference only seeds a *default* the next time it's
relevant (a future New Painting, a future Export, a future autosave
tick). Autosave is the one exception that needs live re-application,
since it drives an already-running `QTimer` on the one persistent
`MainWindow` — `SettingsDialog` acceptance calls
`MainWindow._apply_autosave_interval()` immediately.

**Futuristic UI accents (gated by `settings.futuristic_accents_enabled()`,
default on):** a small, additive motion/glow layer, not a re-skin — the
hairline-stroke, no-gradient, no-drop-shadow visual language stays
intact, and every accent has a plain/instant fallback when the setting
is off. Covers: a breathing glow-pulse on whichever placement tool is
currently armed in the Project Panel (`layers_panel.py`,
`_start_tool_glow()`); a fade-in for the resize/rotate handle frame on
selection (`handle_frame.py`, `HandleFrame.set_active()` — deliberately
one-directional, deactivating still snaps instantly, since a lingering
fade-out right after deselect reads as unresponsive); a fade-in for docks
restored on Focus Mode *exit* only (`MainWindow._fade_dock_in()` — entry/
hiding stays instant, since `test_focus_mode.py` asserts dock visibility
synchronously and "clear the bench" should read as decisive); and
softened Bezier-curved movement lines instead of hard `lineTo()` segments
(`composition_layer.py`, `_smooth_polyline_path()` — pixel-identical to
the straight-line fallback with only 2 points, the default). **Gotcha
confirmed at runtime:** a `QGraphicsDropShadowEffect`/
`QGraphicsOpacityEffect` constructed with no parent and attached via
`setGraphicsEffect()` gets garbage-collected by PySide6 the moment the
enclosing function returns, silently vanishing off the widget despite
Qt's documented ownership transfer — always construct these with the
target widget as parent (`QGraphicsDropShadowEffect(btn)`, not
`QGraphicsDropShadowEffect()` then `btn.setGraphicsEffect(...)`).

**Reference library (`app/library.py`, `app/panels/library_panel.py`):**
a personal, cross-project asset collection stored under
`QStandardPaths.AppDataLocation` (same location pattern as
`recovery.py`) — explicitly **not** part of any project's scene or
`.atelier` file, the same boundary Recent Files already sits on.
`LibraryPanel` is a `QDockWidget` constructed once in
`MainWindow.__init__` (unlike Project/Properties/Swatches, which are
rebuilt fresh on every `_new_project()`) and tabified with the Project
Panel each time a new one is built. Dragging a thumbnail out carries a
real `QUrl.fromLocalFile()`, which `CanvasView`'s existing OS
drag-and-drop handler already accepts unmodified — placing a library
image is an ordinary undoable `AddItemCommand`, not a new placement path.

**Phone upload integration (`app/dialogs/phone_upload_dialog.py`,
`app/library.py`, `uploader/`):** `uploader/` is a fully standalone Flask
tool with its own venv — that boundary is deliberate and nothing here
crosses it by importing from it. Two bridges instead: (1) **Launching**
— Options > Upload From Phone… starts `uploader/app.py` as a `QProcess`,
generating the PIN itself and passing it via `HAPPY_BOY_UPLOADER_PIN`
(the uploader falls back to its own random PIN when unset, so a manual
`python app.py` run is unaffected) and rendering a real QR code via
`qrcode` + `pypng` (no Pillow needed in the main app). `resources.uploader_root()`
is why this still works in a packaged exe: `project_root()` resolves to
PyInstaller's `_MEIPASS` temp dir when frozen, and `uploader/` is
deliberately never bundled there — `uploader_root()` uses
`sys.executable`'s actual on-disk location instead, matching the
documented build layout (`dist/Happy Boy Atelier.exe` one level below
the repo root, `uploader/` a sibling of `dist/`). (2) **Syncing** —
`library.sync_from_uploader()` scans `uploader/photos/` for files not yet
in the library index (tracked via `LibraryItem.uploaded_from`, `None` for
every image added any other way — the usual back-compat fallback) and
imports each through the same `add_image()` path a manual import uses.
`LibraryPanel` drives this with a 3-second `QTimer` poll, not a
`QFileSystemWatcher` — deliberate, since `uploader/photos/` may not exist
yet on first run. "Remember this device" (`uploader/app.py`) is a
separate long-lived trust layer bolted on top of the short-lived
PIN/session model: a SHA-256-hashed token in `uploader/trusted_devices.json`
(gitignored, per-artist local store) that lets a phone skip the PIN
screen on future visits; `/forget-device` revokes just that one device.

**Project templates (`app/project_templates.py`):** a named
`{width, height, unit, guides}` starting point for New Painting —
explicitly never reference images or composition/lighting content, since
auto-populating those would cross into "software infers the composition."
Saved via `MainWindow.save_as_template()` (File menu); applied through
`NewProjectDialog`'s My Templates list, which stages the guides dict and
passes it through to `MainWindow._new_project(spec, guides)`. Picking a
plain size preset afterward clears the staged guides back to `None` — a
template's guides shouldn't leak onto an unrelated format choice. Same
JSON-string-in-`QSettings` storage pattern as export presets
(`export_dialog.py`).

**Swatches / Eyedropper (`app/panels/swatches_panel.py`):** the
eyedropper tool (Project Panel, Reference section) hovers a reference
image to read a live color (hex/RGB/relative-luminance "value" %) into
the Swatches dock continuously (`scene.color_hovered`), and clicking
pins it into a per-project list (`scene.color_sampled` →
`ProjectMeta.color_swatches`) — per-project, not shared across projects,
unlike the Reference Library above. `SwatchesPanel` is rebuilt on every
project load/new, same as Properties.

**Hardware motifs, hover-reveal, and drag-to-reorder (Project Panel /
canvas chrome):** hairline corner rivets on the canvas rect and every
dock's title bar (`app/panels/dock_title_bar.py`), plus print-production
trim marks and a live physical-dimension readout on the canvas corners
(`CanvasView.drawForeground()`). Project Panel item rows fade their
eye/lock icons in on hover (`app/panels/row_hover.py`, reusing the same
`OpacityFade` timing `app/scrollbars.py` uses for auto-hiding
scrollbars — one consistent fade feel app-wide) and show an actual
square crop thumbnail for reference-image rows instead of a generic
glyph (`_reference_thumbnail_icon()`). Rows can be dragged to a new
position within their own layer section (`_ReorderableTree`,
`MoveItemToIndexCommand` in `undo_commands.py`) — a drag can't cross into
a different layer's section. `app/layers/stacking_mixin.py`
(`StackedLayerMixin`) is the shared stack-order arithmetic
(`move_item_forward/backward/to_top/to_bottom/to_index`) behind both this
and the Project Panel's stacking buttons — `ReferenceLayerGroup` and
`CompositionLayerGroup`/`LightingLayerGroup` both mix it in rather than
each re-deriving the same list-index logic.

**Floating selection context toolbar (`app/canvas/context_toolbar.py`):**
selecting exactly one item shows a small floating toolbar
(Duplicate/Flip Horizontal/Lock/Delete) just below it, a
`CanvasView.viewport()` child widget — hides during multi-select and
while actively dragging the item.

**Two-point markers & the measurement tool (`app/canvas/point_handle.py`,
`app/layers/composition_layer.py`):** `TwoPointHandle` is shared
draggable-endpoint infrastructure for any two-point marker — both
`MeasurementItem` (Composition section: place via click-drag-click,
reports live length in the canvas's own unit and angle from horizontal;
Shift snaps the angle to 15° increments) and the lighting layer's
`DirectionArrowItem` (refactored onto this class rather than keeping its
own separate endpoint-drag copy) are built on it. Follow this pattern for
any future two-point marker type instead of re-deriving endpoint drag
handling per-class.

**Snapping (`app/layers/reference_layer.py`, `ReferenceImageItem`):**
dragging a reference image snaps to canvas center, another image's
center, an active guide's intersection points
(`_snap_position()` — only while that guide is toggled on), and
edge-to-edge against the canvas bounds or another visible image's edge
(`_half_extent()`). Rotating snaps to level/90°/180°/270° by default when
close to one (independent of, and in addition to, the existing
Shift-held hard-snap to 15° increments); Alt skips all snapping for both
drag and rotate.

## Current development phase

v1.0.0 is the last tagged release. Since then, none of it version-tagged
yet:

1. **"Phase 0" foundation** — undo/redo, crash recovery, interaction
   consolidation, free corner-drag resize.
2. **UX/interaction redesign ("Studio, Not Software")** — seven phases:
   design system foundation, the selection-model fix (see "Selection is
   NOT Qt's" above), the Project Panel outliner, Inspector batch editing,
   a unified export/new-painting flow, command
   palette/drag-drop/snapping/context menus, and recent files/thumbnails/
   start screen.
3. **UI upgrade ("A Unique Instrument, Not a PureRef Clone")** — a
   second design pass in four phases plus post-launch refinement,
   documented in the Architecture section above and in full in
   `CHANGELOG.md`: guide-intersection/edge/rotation snapping, hover-reveal
   rows and hardware motifs (Phase 1); the measurement tool and Value
   Check (Phase 2, the two items `V2_ROADMAP.md` itself flagged as
   highest-fit-and-not-yet-started); the floating context toolbar,
   contact-sheet thumbnails, and drag-to-reorder (Phase 3); the reference
   library, batch export presets, project templates, and the About dialog
   (Phase 4, pulled forward from `V2_ROADMAP.md`'s deferred list); then
   post-launch refinement — Focus Mode's transparent desk, live phone
   upload → library sync with an in-app launcher, the Options/Settings
   menu, and Futuristic UI accents.

See `CHANGELOG.md` for the itemized history and `V2_ROADMAP.md`
(particularly its Section 7, added after the fact) for status against
the original plan and what's actually next — most of that document's own
Phase 0 and Phase 1 are now done, and several Phase 4 "studio features"
it deferred have since been pulled forward and shipped (library, export
presets, templates, About). Re-check `V2_ROADMAP.md` rather than assuming
its phase numbers still describe what's left; whatever remains open
there is where real future work lives.
