# Changelog

## Unreleased — new features

- **Free corner-drag resize for reference images**: dragging a corner
  handle now stretches width and height independently (anchored at the
  opposite corner, matching Photoshop/Figma-style free transform) instead
  of only scaling proportionally. Hold **Shift** while dragging to lock
  the aspect ratio, matching the old behavior. The Properties panel's
  single Scale field still sets both axes uniformly. `.atelier` files now
  store `scale_x`/`scale_y` alongside the legacy `scale` field, so older
  projects still open looking exactly as they did.

## Unreleased — Phase 0 (foundation work, not yet version-tagged)

Internal work per V2_ROADMAP.md / PHASE_0_PLAN.md — nothing here is a new
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
