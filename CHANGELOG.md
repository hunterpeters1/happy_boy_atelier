# Changelog

## Unreleased — UI upgrade ("A Unique Instrument, Not a PureRef Clone")

A second design pass, informed by studying PureRef/Milanote/etc. for what
makes each of *their* UIs distinctive, then deliberately not copying
either — deepening the existing brass/graphite instrument-panel identity
and finishing several pieces the prior UX redesign explicitly cut for
scope. See `V2_ROADMAP.md`'s Section 7 and `ARCHITECTURE.md` for the full
design rationale. Landed in phases.

### Phase 1 (lowest-risk, highest-identity-payoff — nothing touches undo/serialization)
- **Rule of Thirds / Golden Ratio intersection snapping** — dragging a
  reference image now also snaps to a guide intersection while that guide
  is turned on, alongside the existing canvas-center/other-image-center
  snapping (`ReferenceImageItem._snap_position()`).
- **Hover-reveal Project Panel row icons** — item rows' eye/lock icons
  now rest dim and rise to full opacity on hover, via the same fade
  `app/scrollbars.py` already uses for scrollbar handles
  (`app/panels/row_hover.py`). A row whose lock/visibility was actually
  toggled away from its default stays legible even at rest.
- **Focus Mode** ("Clear the Bench," View menu, Ctrl+Shift+F) — hides the
  toolbar and every dock so only the canvas remains; restores each
  panel's exact prior visibility on exit.
- **Two hardware motifs**: hairline corner rivets on the canvas rect and
  every dock's title bar (`app/panels/dock_title_bar.py`), and
  print-production-style trim marks plus a live physical-dimension
  readout on the canvas corners (`CanvasView.drawForeground()`).

### Phase 2 (mission-critical content features — the two items `V2_ROADMAP.md` itself called out as highest-fit-and-not-yet-started)
- **On-canvas measurement tool** — a ruler-and-protractor composition
  marker (`MeasurementItem`, Project Panel's Composition section): place
  via click-drag-click like a movement line, reporting live length (in
  the canvas's own unit) and angle from horizontal. Drag either endpoint
  independently afterward; hold Shift to snap the angle to 15° increments.
  Persists, undoes, and exports like any other composition marker.
  Endpoint dragging is now shared infrastructure (`TwoPointHandle`,
  `app/canvas/point_handle.py`) — `DirectionArrowItem` (lighting layer)
  was refactored onto the same class instead of keeping its own copy.
- **Value Check** — a third Study Blur–family slider
  (`ReferenceImageItem.grayscale_amount()`) that non-destructively
  desaturates a reference image, for judging value relationships without
  color as a distraction; composes with Blur/Line Clarity in one pass.
  **Edit > Toggle Value Check (All References)** flips every visible,
  unlocked reference image at once as one undo step — "squint at the
  whole board," not just one photo.

### Phase 3 (remaining structural/interaction work)
- **Floating selection context toolbar** — selecting exactly one item
  shows a small toolbar (Duplicate/Flip Horizontal/Lock/Delete) just
  below it (`app/canvas/context_toolbar.py`), cutting the eye-travel to
  a dock for the most common single-item actions. Hides during multi-
  select and while actively dragging the item.
- **Contact-sheet thumbnails** — reference-image rows in the Project
  Panel show a small square crop of the actual photo instead of a
  generic glyph (`_reference_thumbnail_icon()`).
- **Drag-to-reorder** — reference/composition/lighting rows can now be
  dragged to a new position within their own layer section, not just
  moved via the up/down/to-back/to-front buttons (`_ReorderableTree`,
  `MoveItemToIndexCommand`). A drag can't cross into a different layer's
  section.
- **True edge-to-edge snapping** — dragging a reference image now also
  snaps its own edge flush against the canvas bounds or another visible
  image's edge, not just center-to-center (`ReferenceImageItem.
  _half_extent()`, extending `_snap_position()`).

### Phase 4 (pulled-forward studio features, per `V2_ROADMAP.md`'s own deferred-pending-real-use list)
- **Reference library** — a new dock (`app/panels/library_panel.py`,
  tabified with the Project Panel) holding a personal, cross-project
  collection of reference images (`app/library.py`), stored outside any
  `.atelier` file or undo stack — explicitly not project/scene state, the
  same boundary Recent Files already sits on. Import via a file picker or
  drag-and-drop; drag a thumbnail onto the canvas to place it, routed
  through the exact same drop path OS file drag-and-drop already used, so
  it's an ordinary undoable `AddItemCommand` with no new placement logic.
- **Batch export presets** — the Export panel (`app/dialogs/
  export_dialog.py`) gains a Preset combo to save/recall a named
  `{format, DPI, include Study Blur}` combo, for exporting a batch of
  paintings the same way repeatedly. Never stores the destination path,
  which stays per-export by design.
- **Project templates** — "New Painting" gains a My Templates list
  seeded from `MainWindow.save_as_template()` (File menu), each entry a
  named `{width, height, unit, guide toggles}` starting point saved from
  an existing project's current canvas format — deliberately never
  reference images or composition/lighting content, since auto-populating
  those would cross into "software infers the composition." Picking a
  plain size preset afterward clears any staged template guides back out.
- **About dialog** (`app/dialogs/about_dialog.py`, Help menu) — a proper
  styled identity screen (app icon, name/version, the "plan the painting
  before you touch the canvas" mission line, credits) replacing the old
  plain `QMessageBox.about()` call.

### Post-launch refinement
- **Focus Mode's desk is now truly transparent** — entering Focus Mode
  makes the void behind the canvas a real see-through hole to the
  desktop (not a fill color, and not black), regardless of the
  painting's own saved desk color or active theme, while the painting
  itself stays fully opaque and visible. A **Window Opacity** slider in
  the status bar (Focus Mode only) is a separate, complementary control
  that dims the whole window — chrome and canvas alike — if you want to
  see through more than just the desk. Both are pure session state —
  neither touches the project's saved desk color, and both reset
  automatically on exit. (An earlier version of this dropped the desk to
  pure black instead of making it transparent; changed after review.)
  Fixed a follow-up bug in the transparency itself: it was toggling
  `Qt.WA_TranslucentBackground` on entering/exiting Focus Mode, which a
  real Windows test showed silently doesn't work, since that flag is
  only reliable when set before the window's native handle exists. It's
  now set once, permanently, at startup instead, with no visible effect
  outside Focus Mode.
- **Phone uploads now flow straight into the Reference Library, live** —
  photos sent through the `uploader/` tool land in the library
  automatically, usually within a couple of seconds, no manual import
  step. **Options > Upload From Phone…** also starts the uploader itself
  and shows the QR code/URL/PIN right in the app, so a terminal + separate
  venv activation is no longer required for day-to-day use (the manual
  `python app.py` path still works exactly as before, unaffected).
- **The phone uploader's web page has a proper look now** — same
  brass/graphite palette as the desktop app instead of a generic dark-mode
  blue accent, tying it visibly to the rest of the product. Purely visual;
  no behavior changed.
- **The Help menu is now Options, and it has real Settings** — renamed
  since this menu was never really documentation-lookup content, it's
  this app's one catch-all for app-level (not project-level) actions.
  **Options > Settings…** exposes four standard preferences: autosave
  interval (or off entirely), the unit New Painting starts with, the DPI
  Export starts with, and whether new windows show rulers by default.
  None of this is project state — nothing here is saved into any
  painting, and each preference only seeds a default the next time it's
  relevant (autosave is the one exception: turning it off or changing
  the interval takes effect immediately, since it drives an
  already-running timer).
- **Reference images magnetically snap to level/90°/180°/270° while
  rotating** — a default (no-modifier) drag now catches the nearest
  cardinal orientation when you're already close to it, for squaring up
  a photo without fighting a fiddly freehand angle. Independent of the
  existing Shift-held hard snap to 15° increments, which is unchanged;
  hold **Alt** to rotate with no snapping at all.
- **The phone uploader can now remember a device** — checking "Remember
  this device" (default checked) on the PIN screen skips the PIN
  entirely on every future visit from that phone, via a separate
  long-lived, hashed-at-rest trust token that survives the uploader
  restarting — the fresh-PIN-per-launch behavior for a *new* device is
  unchanged. A **"Forget this device"** link on the gallery page revokes
  it again, for a borrowed or shared phone.
- **Futuristic UI accents** (Options > Settings…, default on) — a small
  layer of motion/glow on top of the existing brass/graphite look, not a
  replacement for it: a soft breathing glow on whichever placement tool
  is currently armed in the Project Panel, an eased fade-in for the
  resize/rotate handles on selection (and for docks restored after Focus
  Mode), and softened, curved rendering for movement lines instead of
  hard straight segments. Toggling it off reverts each of those to its
  plain/instant equivalent — nothing is gated behind it, only the
  animation/softening itself.
- **The phone uploader now recovers on its own from "port 5000 is
  busy"** — previously a dead end (close the dialog, hunt down the
  leftover process by hand, try again), now the dialog automatically
  asks whatever's holding that port to identify itself and step aside
  before showing an error, and retries once. This only ever succeeds
  against a genuine previous copy of this exact tool (a fresh, hard exit
  the new instance requests over a loopback-only connection) — an
  unrelated app on port 5000 is left alone, and you still get the
  original error message in that case.

## Unreleased — UX redesign ("Studio, Not Software")

A ground-up interaction and visual-design pass, driven by a full-source
UX audit rather than a stylistic refresh — several items below are real
functional bugs the audit surfaced, not polish. Landed as seven phases,
each its own commit.

### Phase 1 — Design system foundation
- A real single-weight line-icon set (`app/icons.py`, rendered at runtime
  from hand-authored SVG shapes), finally implementing the "brass/
  graphite line-art" toolbar language `ARCHITECTURE.md` had documented
  since v1.0 but that was never actually built — the toolbar was
  text-only. Icon buttons were bumped slightly larger since.
- Every action is one shared `QAction` between its menu entry and
  toolbar button (previously the toolbar built separate, un-synced
  `QAction` instances with no shortcut shown in their tooltips).
- Fixed a real color collision: `COLOR_FOCAL_SECONDARY` and
  `COLOR_GUIDE` were both literally `COLOR_BRASS` — a secondary focal
  point, a rule-of-thirds line, and "this menu item is selected" all
  the same paint. Each now has its own reserved hue.
- Base font 9pt → 10pt; monospace is now reserved for genuine numeric
  readouts instead of forced onto every text field, including the
  project Title and Note text.
- Zoom convention flipped to match every other creative tool:
  Ctrl/Cmd+scroll zooms, plain scroll pans vertically, Shift+scroll
  pans horizontally (previously plain wheel zoomed).
- Escape now backs out of crop mode (previously it only cancelled an
  armed placement tool — there was no keyboard way out of cropping at
  all). A locked reference image's Crop… button is now disabled instead
  of staying clickable and silently doing nothing. Wired the
  `Show Rulers` toggle (`View` menu, Ctrl+R) that existed in code with
  no menu item, toolbar button, or shortcut pointing to it.

### Phase 2 — Selection model
Set out to unify two selection-notification systems the design audit
flagged; turned up something bigger along the way. Confirmed at
runtime (a real `QTest.mouseClick` and rubber-band simulation) that
`QGraphicsItem.setSelected()`/`isSelected()`/`QGraphicsScene.
selectedItems()` did not work **at all** for any item in the app —
not unreliably, never — because every layer is a `QGraphicsItemGroup`
with `setHandlesChildEvents(False)`. In the shipped app this meant
**Delete-after-click and rubber-band multi-select never worked**, and
the selected-item highlight for focal points, movement lines, light
sources, and direction arrows never rendered.

- Replaced Qt's selection model outright with `CanvasScene`'s own
  (`selected_items()`/`set_selection()`/`add_to_selection()`/
  `remove_from_selection()`, backed by a plain list and a
  `selection_changed` signal) — the one thing every consumer (Inspector,
  Delete, the selected-item paint highlight, lock/unlock) now goes
  through.
- Fixed the Inspector's dual-signal bug this phase originally set out
  for: `item_activated` used to also drive the Inspector directly,
  forcing single-item display even during a Shift-multi-select. It now
  drives only the resize/rotate handle frame.
- Fixed a related bug in the same code path: the empty-click deselect
  check used `itemAt()` (topmost item only, ignoring
  `acceptedMouseButtons`), so it always hit the non-interactive Guides
  overlay sitting on top of the whole canvas and treated every click as
  empty. Switched to scanning the full z-stack.
- A background click now actually clears the Inspector to "Nothing
  selected" — there was previously no path back to that state at all.

### Phase 3 — Project Panel
- Replaced the Layers dock's five hardcoded `QGroupBox` sections (no
  tree, no reordering, Guides missing its own Visible/Locked row) with
  one real outliner (`app/panels/layers_panel.py`, dock title now
  "Project"): every placed item — not just reference images — gets a
  named, selectable row, with inline eye/lock icon buttons and a live
  search field across the whole tree.
- Reference images are named by their actual filename now, not
  "Reference 1/2/3" — `ReferenceImageItem.display_name`, threaded
  through import and the `.atelier` format's new `"name"` field on
  reference entries (older files without it fall back to the image id).
- Guides gets a real visibility toggle — previously the only layer with
  zero interaction surface beyond its two checkboxes.
- Not included this pass, called out rather than half-built:
  drag-to-reorder within a layer (no layer group exposes a reorder
  operation yet) and true hover-reveal row icons (always visible
  instead).

### Phase 4 — Inspector
- Vanishing point and horizon position are editable fields now, not a
  read-only label — the only previous way to reposition either was a
  canvas drag. Shown in the canvas's own unit (in/cm/mm/px), not raw
  scene coordinates.
- Multi-selecting more than one item used to hide every control and
  show only "Multiple items selected." A Batch Edit panel now offers
  relative opacity/scale nudges, four-way align, and batch delete, each
  as one undo step.
- Found and fixed a rebuild/selection race surfaced by chaining two
  batch edits back to back: the Project Panel's structural rebuild
  cleared the tree's selection unguarded, which fed back into
  `scene.set_selection([])` and silently wiped the real selection
  mid-operation.

### Phase 5 — Export & New Painting
- Export is one panel now, not two dialogs — destination (pre-filled
  from the project name and save folder, live-updating as the format
  changes) lives alongside format/DPI; no second native Save dialog.
- New Painting's "Custom" category (a fourth peer next to Portrait/
  Landscape/Square that hid the size fields entirely) is gone — Width/
  Height/Unit are always visible and editable; presets just fill them
  in. Fixes a latent bug where the dialog's own default (8×10in) didn't
  match `CanvasSpec`'s dataclass default (16×20in) — the dialog now
  seeds directly from `CanvasSpec()`.

### Phase 6 — Interaction polish
- Command palette (Ctrl+K / View menu): fuzzy-searchable list of every
  menu action, built by walking the menu bar's own `QAction`s so it can
  never drift out of sync with what the menus actually contain.
- OS drag-and-drop image import onto the canvas (previously the file
  dialog was the only way in); a multi-file import/drop is now one undo
  step instead of one per file.
- Live rubber-band preview line while placing the second point of a
  movement line or light/shadow direction arrow — previously no
  feedback existed between the two clicks at all.
- Shift-snap rotation to 15° increments; dragging a reference image
  snaps its center to the canvas center or another image's center
  (Alt/Option bypasses it).
- Real right-click context menus (Delete/Lock/Crop… on an item, Fit
  Canvas/Cancel Tool on empty canvas) — right-click was previously dead
  everywhere.

### Phase 7 — Recent files & start screen
- Recent files (`QSettings`-backed, capped at 10, `File > Open Recent`)
  — there was no `QSettings` usage anywhere in the app before this and
  no recent-files mechanism at all.
- Thumbnails: `save_atelier`'s `thumbnail` parameter has existed since
  v1.0 with nothing ever generating one. Every save now renders and
  embeds a real `thumb.png`.
- A start screen shown at launch when there's no crash to recover from
  and at least one recent painting exists — real thumbnails, titled by
  actual project name, with New Painting/Open…/Start Blank alternatives.
  A fresh install with no recent files still opens straight to a blank
  canvas with zero extra clicks.
- Fixed the crash-recovery timing gap: the recovery snapshot used to be
  deleted the instant either "Recover" or "Discard" was clicked, so a
  second crash before the first post-recovery Save lost the work again
  with no safety net in between. It's now only cleared by Discard (or a
  failed read) immediately, or by an actual successful save on the
  Recover path.

## Unreleased — new features

- **Free corner-drag resize for reference images**: dragging a corner
  handle now stretches width and height independently (anchored at the
  opposite corner, matching Photoshop/Figma-style free transform) instead
  of only scaling proportionally. Hold **Shift** while dragging to lock
  the aspect ratio, matching the old behavior. The Properties panel's
  single Scale field still sets both axes uniformly. `.atelier` files now
  store `scale_x`/`scale_y` alongside the legacy `scale` field, so older
  projects still open looking exactly as they did.
- **Flip Horizontal / Flip Vertical**: right-click a reference image for
  one-click mirror flips (negative axis scaling). Also in the Edit menu.
- **Magnify 2× / Shrink to 50%** — one-click uniform scale-up / scale-down
  from the context menu.
- **Duplicate**: Edit > Duplicate (Ctrl+D) or right-click → "Duplicate".
  Supports multi-selection (duplicates all selected items in one undo step).
- **Send to Back / Bring to Front**: absolute stacking order within a
  layer — right-click context menu, Edit menu, and Project Panel row
  buttons (to-back/to-front alongside existing step-by-step up/down).
- **Desk Color**: View > Change Desk Color… picks the void behind the
  canvas rect. Per-project, saved in the .atelier file's meta.bg_color
  field. Defaults to near-black for back-compat with older .atelier files.

## Unreleased — Phase 0 (foundation work, not yet version-tagged)

Internal work per V2_ROADMAP.md — nothing here is a new
user-facing feature; the goal is a foundation the V2 phases can build on
without redoing work.

- **Interaction consolidation**: the eight marker classes that each
  duplicated click-to-select and lock logic now share one
  `InteractiveItem` base class (`app/canvas/interactive_item.py`).
- **Undo/redo**: a `QUndoStack` on every project (`Ctrl+Z` / `Ctrl+Y`,
  Edit menu) covers add/delete, move/scale/rotate, crop, note text edits,
  perspective mode switches, and grid/opacity properties. Scoped to
  content mutations only — lock and visibility toggles stay direct,
  un-undoable calls, per the Phase 0 decision that undo represents
  reversing changes to the artwork, not application state.
- **Crash recovery**: a background snapshot (every 3 minutes, only when
  there are unsaved changes) is kept outside your project files. If the
  app doesn't close cleanly, the next launch offers to recover it. A
  normal Save or a clean exit leaves no recovery file behind.
- **Build packaging fixed, then de-scripted**: `HappyBoyAtelier.spec` now
  bakes the PySide6 bundling and icon-resource fixes directly into the
  spec file (`collect_all("PySide6")`, `resources` data folder) instead of
  relying on flags someone has to remember. Every *script* built around
  it — `build.bat`, a desktop-shortcut helper, then a PowerShell
  `build_windows.ps1` — ended up getting flagged and blocked by Windows
  on this machine in turn, so none of them are shipped anymore. See
  "Build a standalone .exe" in README.md for the manual command sequence,
  which is now the only supported build path.

## v1.0.0

First tagged build. Full MVP workflow: create canvas, import and arrange
references, composition guides, perspective grids, lighting notes, save and
reopen `.atelier` projects, projector mode, lock setup, and PNG/JPG/PDF
export.

Fixes rolled into this tag from the prototype:

- Reference images, focal points, notes, movement lines, light sources,
  direction arrows, vanishing points, and the horizon line now all
  reliably become "selected" on a plain click (not just while dragging),
  so the Properties panel and the reference image's resize/rotate handles
  show up as expected.
- Added a **Line weight** control to the Perspective section of the Layers
  panel (1–8px, default 2px) so the horizon, vanishing points, and grid
  rays can be thickened for projectors that wash out fine lines.
- Perspective grid is now visible by default, matching the "Visible"
  checkbox state in the Layers panel (previously the checkbox and the
  actual layer disagreed on first launch).
- Packaged with a Windows desktop icon and a PyInstaller build script to
  produce a standalone `.exe`.
