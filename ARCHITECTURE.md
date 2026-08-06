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
    constants.py               canvas format presets, units, layer ids, keys
    theme.py                   palette + QSS ("divine machinery" look)
    project.py                 dataclasses: CanvasSpec, ProjectMeta; pure (de)serialization helpers
    atelier_io.py               .atelier save/load (zip), PNG/JPG/PDF export
    main_window.py              QMainWindow: menu, toolbar, docks, mode switching, lock-setup
    canvas/
      canvas_view.py            QGraphicsView: zoom (ctrl+wheel), pan (space+drag/middle-drag), rulers
      canvas_scene.py           QGraphicsScene: owns the layer group items, hit-test routing
      handle_frame.py           reusable interactive transform box (move/scale/rotate handles)
    layers/
      reference_layer.py        ReferenceImageItem + ReferenceLayerGroup (import, crop, opacity, lock)
      composition_layer.py      FocalPointItem, MovementLineItem, NoteItem
      perspective_layer.py      HorizonLineItem, VanishingPointItem, PerspectiveGridItem (1/2/3-pt)
      lighting_layer.py         LightSourceItem, DirectionArrowItem, NoteItem (reused)
      guide_overlay.py          RuleOfThirdsOverlay, GoldenRatioOverlay (non-interactive, top z-order)
    panels/
      layers_panel.py           dock: layer tree, visibility/lock/opacity, active-tool selector
      properties_panel.py       dock: contextual inspector for the current selection
    dialogs/
      new_project_dialog.py     format grid (portrait/landscape/square) + custom W/H/unit
      export_dialog.py          PNG / JPG / PDF planning-sheet export options
    projector/
      projector_window.py       fullscreen projector mode + Lock Projection
  resources/
    icons/                      SVG line icons, brass/graphite line-art style
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
thumb.png             cached thumbnail for file browser / recents
```

`manifest.json` shape (abbreviated):

```json
{
  "format_version": 1,
  "canvas": {"name": "...", "width": 16, "height": 20, "unit": "in"},
  "meta": {"created_at": "...", "modified_at": "...", "locked": false},
  "references": [
    {"id": "uuid", "image": "images/uuid.png", "x":.., "y":.., "scale":..,
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
Layers panel. Locking a layer clears `ItemIsMovable`/`ItemIsSelectable` on
its children rather than removing them from the scene, so a locked layer is
still visible and still exports.

The software never infers composition, perspective, or lighting — every
marker, line, and grid is placed by the artist. Automation is limited to
arithmetic (e.g. computing grid geometry from a vanishing point), never
aesthetic judgment.

## Interaction: the handle frame

`handle_frame.py` implements one reusable interactive transform widget used
by any movable/scalable/rotatable item (currently reference images): eight
resize handles at the corners/edges of the item's bounding box plus one
rotate handle above it. Dragging a corner updates a `QTransform` combining
scale; dragging the rotate handle updates rotation around the item's
center. This keeps "arrange references" feeling precise rather than fiddly.

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

## Export

- PNG/JPG: render the scene rect at a chosen output DPI via
  `QGraphicsScene.render()` into a `QImage`.
- PDF planning sheet: `QPdfWriter` page with the rendered canvas plus a
  printed sidebar of notes (composition/lighting) and canvas spec — a
  physical reference sheet to bring to the easel.

## MVP scope (this build)

Create canvas → import & arrange references → composition guides →
perspective grids → lighting notes → save/reopen `.atelier` → projector
mode → lock setup. Crop is a basic rectangle-crop tool. Export (PNG/JPG/PDF)
is included since it falls out of the same render path at low extra cost.
Explicitly excluded per spec: AI generation, brush/paint tools, cloud
accounts, social/marketplace features.
