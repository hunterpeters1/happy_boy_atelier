# Happy Boy Atelier

A digital drafting table for traditional painters. Prepare a physical
painting before you touch the canvas: pick a format, arrange reference
photos, and plan composition, perspective, and lighting. It is not a painting app and not an image
generator — every mark on the canvas is placed by the artist.

See `ARCHITECTURE.md` for the technical design.

## Run it (Windows)

1. Install Python 3.10 or newer from python.org (check "Add to PATH").
2. Open a terminal in this folder and install the one dependency:

   ```
   pip install -r requirements.txt
   ```

3. Launch the app:

   ```
   python main.py
   ```

## Build a standalone .exe (Windows)

This project no longer ships any build script — every one tried
(`build.bat`, `create_desktop_shortcut.ps1`, `scripts\build_windows.ps1`)
got flagged and blocked by Windows on this machine, because "a downloaded
file that installs things and/or calls other scripts" is exactly what
antivirus/SmartScreen heuristics watch for. The commands below are the
only build path now — nothing pre-packaged ever executes, since you're
typing (or pasting) each line into your own PowerShell session yourself,
so there's nothing for a heuristic to catch:

```
py -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-build.txt
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python -m PyInstaller HappyBoyAtelier.spec --noconfirm
```

The exe lands at `dist\Happy Boy Atelier.exe` — a single file, no console
window, with the app icon correctly baked into both the file/taskbar icon
and the running window's title-bar icon. `HappyBoyAtelier.spec` bakes in
the PySide6 bundling and icon-resource fixes directly, so this short
sequence is all it takes; you don't need to reconstruct any
`--collect-all`/`--add-data` flags by hand.

Re-run the same commands (skip the `venv` creation step once `.venv`
already exists) any time you want to rebuild after making changes.

To put a shortcut on your Desktop: right-click the built exe in File
Explorer → **Show more options → Send to → Desktop (create shortcut)** —
five seconds, no script needed.

Note: this has to be built on a Windows machine — PyInstaller packages for
whatever OS it's run on, it can't cross-build a Windows .exe from another
platform.

## Running tests

```
pip install -r requirements-dev.txt
pytest
```

The suite runs headless (`QT_QPA_PLATFORM=offscreen`, set automatically in
`tests/conftest.py`), so it doesn't need a display — safe to run in CI or
over SSH. `tests/test_project.py` has no Qt dependency at all;
`tests/test_atelier_io.py` and `tests/test_undo_commands.py` exercise real
`.atelier` files and a real `CanvasScene` respectively.

## Feature tour

The app has more surface area than the toolbar suggests — several tools
only exist as buttons inside the **Project Panel** (left dock), not the
menu bar or toolbar. This section is written to be exhaustive; if you're
looking for "is there a way to…", check here before assuming there isn't.

### Getting started

- **Start screen** — on launch, if you have recent paintings and there's
  no crash to recover (see below), pick one by its embedded thumbnail,
  start a new one, or open something else. A fresh install skips straight
  to a blank canvas.
- **File > New Painting…** (Ctrl+N) — width/height/unit are always
  visible and editable; portrait/landscape/square presets just fill them
  in, no separate "custom" mode to switch into.
- **Import** — File > Import Reference Image(s)… (Ctrl+I), or drag image
  files from your OS straight onto the canvas (multiple at once is fine —
  it's one undo step either way). Supported: PNG, JPG/JPEG, BMP, WEBP.
  **HEIC/HEIF is not supported here** — Qt has no HEIC decoder, so those
  files are silently ignored by drag-and-drop. Convert HEIC to JPEG first
  (the `uploader/` tool below does this automatically for phone photos).

### Reference images

Each imported photo is its own object:

- **Drag** to move — snaps its center to the canvas center, to any other
  *visible* reference image's center, to a Rule of Thirds/Golden Ratio
  guide intersection if that guide is currently turned on (Project Panel
  > Guides), or edge-to-edge against the canvas bounds or another visible
  image (its own edge landing flush with the target edge, not just
  center-to-center); hold **Alt** to bypass snapping entirely.
- **Selection toolbar** — selecting exactly one item on the canvas shows a
  small floating toolbar just below it with Duplicate, Flip Horizontal
  (reference images only), Lock, and Delete — the same actions as the
  right-click menu and Edit menu, just closer to the item so you don't
  have to travel to a dock for the common ones. Hides for a multi-select
  (use the Properties panel's Batch Edit section there) and while
  actively dragging the item.
- **Resize** via corner handles — free (independent width/height) by
  default; hold **Shift** to lock aspect ratio.
- **Rotate** via the handle above the image; hold **Shift** to snap to
  15° increments.
- **Crop** — direct manipulation: select the image and drag any of the
  four edge handles (left/right/top/bottom midpoints) inward, same
  commit-on-release behavior as move/resize/rotate. No separate crop
  mode to enter or exit. Properties panel has a "Reset Crop" button to
  clear back to the full source image (disabled on locked images).
- **Flip Horizontal / Flip Vertical** — right-click a reference image for
  one-click mirror flips (via negative axis scaling). Useful for checking
  composition asymmetries. Also available in the Edit menu.
- **Magnify 2× / Shrink to 50%** — one-click uniform scale-up / scale-down
  from the context menu, handy for quickly sizing references without
  fiddling with the Properties spin box.
- **Duplicate** — Edit > Duplicate (Ctrl+D), or right-click → "Duplicate",
  creates a copy of the selected image placed slightly offset, ready to
  move around. Fully undoable. Also supports multi-selection (duplicates
  all selected items in one undo step).
- **Send to Back / Bring to Front** — right-click a reference image (or
  use the up/down/to-back/to-front buttons in the Project Panel's row) to
  adjust its stacking order within the reference layer. Step-by-step
  reorder and absolute to-back/to-front, all undoable.
- **Study Blur** — Properties panel has **Blur** and **Line Clarity**
  sliders (0–100) per image. This is a "squint test": blurs the image
  while boosting contrast on dark edges/lines, so you can judge overall
  shapes and values without fine detail pulling your eye. It's a display
  filter only — the saved image is never altered — and is **not included
  in exports by default**; the Export dialog has an explicit "Include
  Study Blur effect" checkbox if you want it baked into a specific
  export.
- **Value Check** — a **Value Check** slider (0–100) alongside Blur/Line
  Clarity non-destructively desaturates the image, for judging light/dark
  value relationships without color as a distraction. Same display-only,
  export-opt-in behavior as Study Blur, and composes with it (squint-test
  and check values on the same photo at once). **Edit > Toggle Value
  Check (All References)** flips every visible, unlocked reference image
  at once — "step back and squint at the whole board" — as one undo step.
- **Eyedropper** — tool button in the Project Panel's Reference section
  (not the toolbar). Arm it, then hover any reference image: a
  **Swatches** dock (tabbed with Properties) shows a live readout of the
  color under the cursor — hex, RGB, and a value/luminance percentage for
  judging value relationships while mixing paint. Click to pin that color
  into a per-project swatch list (not shared between projects); each
  pinned swatch has its own remove button. The tool stays armed for
  repeated sampling — Esc, re-clicking the button, or arming a different
  tool exits it.

### Composition tools

Placed via tool buttons at the top of the **Project Panel's Composition
section** (not the toolbar):

- **Focal point (primary / secondary)** — one click on canvas places a
  crosshair marker; primary is filled/brighter, secondary is hollow.
- **Movement line** — click-drag-click: first click sets the start,
  second sets the end, with a dashed preview line following your cursor
  in between. Draws an arrowed path showing how the eye should move
  through the composition.
- **Measurement** — a ruler and protractor in one: click-drag-click like
  a movement line, but the placed segment shows a live readout of its
  length (in the canvas's own unit) and its angle from horizontal, e.g.
  `12.4 in · 37°`. Once placed, drag either end independently to adjust
  it — hold **Shift** while dragging an endpoint to snap its angle to 15°
  increments. Persists and undoes like any other composition marker.
- **Note** — click to place a pin marker with an editable text label;
  double-click it on canvas, or use the Properties panel's text box, to
  edit.

Any armed tool shows a crosshair cursor; **Esc** or right-click → "Cancel
Tool" backs out without placing anything.

### Perspective tools

Live entirely inside the **Project Panel's Perspective section** — there
is no toolbar or menu entry for this at all. The layer starts hidden on a
new project until you pick a mode:

- **1-pt / 2-pt / 3-pt mode** — radio buttons; switching modes
  auto-creates the horizon line and the matching vanishing point(s).
- **Horizon line** — drag vertically (its horizontal position is fixed);
  exact Y position is also editable numerically in the Properties panel.
- **Vanishing points** (VP1–VP3 depending on mode) — draggable, with
  construction grid lines radiating from each; also editable by exact
  X/Y in the Properties panel.
- **Grid lines** spinbox (2–48) — how many construction lines per
  vanishing point.
- **Line weight** spinbox (1.0–8.0) — thicken the lines if you're
  projecting the grid onto a wall/canvas and fine lines wash out.
- **Opacity** slider for the whole perspective overlay.

### Lighting tools

Also placed via tool buttons in the **Project Panel's Lighting section**:

- **Light source** — one click, places a sunburst marker.
- **Light direction arrow** / **Shadow direction arrow** — click-drag-click
  like movement lines; uniquely, these two support dragging each endpoint
  independently after placement (small square handles), not just moving
  the whole arrow.
- **Note** — same as composition notes, lighting-colored.

### Guides

Project Panel's **Guides** section has three checkboxes — **Rule of
Thirds**, **Golden Ratio**, and **1" Grid** overlays. Purely visual,
always drawn on top, nothing to place or select. The grid is spaced using
the canvas's real physical scale (the same one the rulers use), for the
classic grid-method technique of transferring a composition to a
physical canvas — and since it's a normal layer like the other guides, it
shows up in PNG/JPG/PDF exports automatically, no separate export step
needed.

### Selecting, organizing, and editing

- **Project Panel** (left dock) — one outliner listing every layer and
  every item placed in it (not just reference images), each a named,
  searchable row with inline visibility/lock toggles. Reference images
  show a small square thumbnail of the actual photo instead of a generic
  icon, so the list reads like a contact sheet. A search box at the top
  filters items by name across all layers. Reference/composition/lighting
  rows can be reordered within their own layer either by dragging a row
  to a new position, or with the up/down (step-by-step) and to-back/
  to-front (absolute) buttons — perspective and guide items don't reorder,
  and a drag can't cross into a different layer's section. Item rows'
  eye/lock icons rest dim and rise to full opacity on hover — a row
  you've actually hidden or locked stays legible even at rest, so you
  don't have to hover every row to notice.
- **Properties panel** (right dock) — edits whatever's currently
  selected. Select 2+ items to get a **Batch Edit** section: opacity
  nudges (±5%), scale nudges (×0.95/×1.05, only shown if every selected
  item supports scaling), and **align left/right/top/bottom** buttons
  that line up all selected items to the group's min/max edge.
- **Right-click** an item for Delete / Lock / Unlock; right-click an
  unlocked reference image for Flip Horizontal/Vertical, Magnify 2×,
  Shrink to 50%, and Duplicate; right-click empty canvas for Fit Canvas,
  plus Cancel Tool if one's armed. Cropping a reference image is done via
  its on-canvas edge handles, not the context menu — see Reference images
  above.
- **Ctrl+K** — command palette. It's built by walking the entire live
  menu bar, so *every* menu action is searchable there, including ones
  that are easy to forget exist (Show Rulers, Appearance themes, etc.).

### Workspace

- **Pan** — hold Space and drag, or drag with the middle mouse button.
- **Zoom** — plain mouse wheel (no modifier needed), 5%–2400% range;
  View > Zoom In/Out (Ctrl+=/Ctrl+-) or Fit Canvas (Ctrl+0).
- **Rulers** — View > Show Rulers (Ctrl+R), on by default. The canvas
  corners also carry small print-production-style trim marks, plus a
  monospace readout of the canvas's real physical dimensions near the
  bottom-right corner, in whichever unit you set at New Painting.
- **Focus Mode** — View > Focus Mode (Ctrl+Shift+F) hides the toolbar and
  every dock so only the canvas (and the menu bar) remain, for stepping
  back and just looking at the arrangement. Exiting restores every panel
  to exactly the visibility it had going in — a panel you'd already
  closed stays closed, nothing gets blanket-reshown.
- **Desk Color** — View > Change Desk Color… opens a color picker for the
  void behind the canvas rect (the "desk" the painting sits on). Per-project
  and saved in the .atelier file — each painting can have a different desk
  color to match its intended framing (e.g. mid-tone grey for charcoal
  studies, warm paper for pastels). Defaults to near-black, matching the
  previous fixed behavior.

### Locking

Two independent lock mechanisms:

- **Per-item / per-layer locks** — padlock icons in the Project Panel.
  Lock a layer and its contents stay visible but stop being
  draggable/selectable.
- **Edit > Lock Setup** (Ctrl+L, also a toolbar toggle) — a global lock
  for when the plan is final. Freezes every layer regardless of
  individual lock states, disables the Project Panel entirely, cancels
  any active tool, and shows a permanent "SETUP LOCKED" banner in the
  status bar. Turning it back off restores whatever the individual
  per-layer locks were set to before. This state is saved in the file but
  deliberately excluded from Undo/Redo.

### Saving, opening, and crash recovery

- **File > Save / Save As / Open / Open Recent** — projects are single
  portable `.atelier` files (a zip: manifest + embedded reference images
  + thumbnail) — nothing is ever a link to an external file, so a
  `.atelier` file is self-contained and safe to move or send. Recent
  Files quietly drops entries whose files were since moved or deleted.
- **Crash recovery** — the app silently autosaves every 3 minutes to a
  single fixed recovery slot (separate from your own save files), but
  only while there's unsaved work. If the app didn't exit cleanly last
  time (crash, force-quit, power loss), the *next* launch shows a prompt
  — before the start screen — offering to recover that snapshot or
  discard it. A recovered project opens unsaved (no file path attached);
  the recovery snapshot itself isn't deleted until you do save, so a
  second crash before then doesn't lose the recovery again.

### Exporting

**File > Export…** (Ctrl+E), one panel, destination pre-filled from the
project name and updated live as you change format:

- **PNG or JPG** at a chosen **Output DPI** (72–1200, default 300).
- **PDF Planning Sheet** — a single-page, letter-size, 300dpi PDF with
  the canvas rendered at the top and a bulleted list of every
  composition and lighting note's text underneath, meant to print and
  bring to the easel. (DPI setting doesn't apply to PDF — it's vector.)
- **Include Study Blur effect** checkbox (off by default) — bakes each
  reference image's current Blur/Line Clarity sliders into that export
  only; the saved project and any thumbnails are never affected.

### Appearance

View > Appearance offers Light, Dark, Current (matches OS), and **Hack
Mode**. Hack Mode is a developer/debug theme — switching to it also adds
a **Debug menu** (verbose console logging, a live scene-stats readout in
the status bar, reload stylesheet) and a decorative status-bar widget.
Harmless to poke at, but not part of the normal painting workflow.

## Upload from Phone

`uploader/` is a small, **standalone** tool (its own dependencies, its
own venv — deliberately not part of the desktop app or its PyInstaller
build) for getting phone photos onto this machine over local WiFi with no
app install on the phone:

```
cd uploader
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

It prints a URL, a QR code, and a one-time PIN. Scan the QR (or type the
URL) from a phone **on the same WiFi network**, enter the PIN once, then
upload photos through the browser — they land in `uploader/photos/` with
a live gallery/thumbnail preview on the same page. HEIC/HEIF photos
(the iPhone default) are automatically converted to a full-resolution
JPEG and the original HEIC is discarded, since Qt can't decode HEIC and
a raw `.heic` file can't be imported into the atelier app at all. Every
other format lands unmodified.

From there, bring photos into a project the normal way: File > Import
Reference Image(s)… (or drag-and-drop) pointed at `uploader/photos/`.
There's no automatic link between the uploader and an open project —
by design, so switching to a different phone-transfer method later
doesn't require touching the app.

Known limitations: no authentication beyond the one-time PIN (fine for a
single trusted home network, not for a public/guest WiFi); requires the
phone and laptop to actually be on the same network segment — a WiFi
mesh extender/satellite or a phone's "Private WiFi Address" setting can
put the phone on an isolated subnet that can't reach the laptop even
though it looks like the same network.

## Status

**v1.0.0** was the last tagged release, covering the full MVP workflow:
create canvas → import & arrange references → composition guides →
perspective grids → lighting notes → save/reopen → projector mode → lock
setup. Since then, an unreleased but substantial ground-up UX pass has
landed — undo/redo, crash recovery, a real Project Panel outliner, a
unified selection model, batch editing, a command palette, drag-and-drop
import, and recent files with thumbnails, among other things. See
`CHANGELOG.md` for the itemized history and `V2_ROADMAP.md` for what's
still ahead.
