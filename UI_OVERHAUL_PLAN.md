# Happy Boy Atelier — UI Overhaul: "Studio Mode"

## Current State Assessment

The app is built on PySide6 (Qt 6) with a conventional desktop application topology:
- `QMainWindow` with a standard `QMenuBar` (File/Edit/View/Help)
- A fixed `QToolBar` below the menu (new, open, save, undo/redo, import, export, fit, lock)
- Three `QDockWidget` panels: Project (left, as a `QTreeWidget` outliner), Properties (right), Swatches (right, tabbed with Properties)
- A central `CanvasView` (`QGraphicsView`) with rulers along top/right
- A `QStatusBar` at the bottom with a lock banner and zoom/format hint

The visual styling is already quite distinctive — dark graphite panels, brass/copper accents, Space Grotesk font, hairline borders, monospaced numeric readouts. But the **interface topology** (menu + toolbar + docks + status bar) is identical to Photoshop, GIMP, or any corporate Windows app. The uniqueness lives in the *visual language* and *feature set*, not in the *interface structure*.

### What we want: PureRef's philosophy, with our own aesthetic

PureRef's uniqueness comes from:
1. No permanent chrome — no menu bar, no toolbar, no status bar
2. A canvas that fills the screen, with UI appearing only on demand
3. Floating, borderless micro-panels that feel like tools laid on a desk
4. Right-click context as the primary interaction model
5. The interface recedes entirely when the artist is working

We keep our "machined panel plate" brass/graphite instrument aesthetic, but restructure the topology to be canvas-first and chrome-free.

---

## Phase 1: Chrome Removal

### 1.1 Remove the Menu Bar
**What moves where:**
- **File actions** (New, Open, Save, Import, Export): become accessible via the **Command Palette** (Ctrl+K, already implemented) and a **floating hamburger menu** (⋯) in the top-right corner. The start screen and file dialog already handle the first-run/new-project flow.
- **Edit actions** (Undo, Redo, Delete, Duplicate, Flip, Magnify, Lock Setup): become **contextual actions** — they appear in the selection tool card, or in the right-click context menu. Undo/Redo stay keyboard-accessible (Ctrl+Z / Ctrl+Y).
- **View actions** (Zoom, Rulers, Desk Color, Command Palette): move to a **floating view strip** that appears on hover at the top edge of the canvas.
- **Appearance (themes)**: moves to a small **theme picker chip** in the floating top bar.
- **Help (About)**: becomes a small **Ⓔ** icon in the corner.

**Implementation:** Delete `self.menuBar()` usage in `_build_menu_and_toolbar()`. Keep all `QAction` objects (they're already shared between menu and toolbar — this is the one good structural decision already in place). Rebuild them into a modal command overlay.

### 1.2 Replace the Fixed Toolbar
**What it becomes:** A **floating vertical icon strip** (8 icons) that:
- Lives on the **left edge of the canvas**, 6px inset, appearing on canvas-hover
- Auto-hides (fades to 0 opacity) when the mouse isn't near it
- Contains the 6 most-used actions: New, Open, Save, Undo, Redo, Import, Export, Lock
- Each icon is a small floating card (32×32, brass border, graphite fill) that appears on hover with a tooltip

**Implementation:** Replace `QToolBar` with a custom `QWidget` positioned absolutely over the canvas viewport. Use `QGraphicsOpacityEffect` for fade animations.

### 1.3 Replace the Status Bar
**What it becomes:** A **floating strip** that appears at the **bottom of the canvas** on hover, showing:
- Canvas name + dimensions + zoom level
- The "SETUP LOCKED" banner (when locked), appearing as a small brass tag
- Auto-hides when not in use

**Implementation:** Replace `self.statusBar()` with a `QWidget` overlay on the canvas. Show/hide via mouse tracking on the canvas view.

---

## Phase 2: Floating Panels (Replacing DockWidgets)

### 2.1 Convert All Three Panels to Floating Cards

**Project Panel → "Setup List"**
- Becomes a **floating card** (borderless, rounded corners, subtle shadow)
- Default position: **left side of the canvas**, attached as a thin stripe (icons only, ~40px wide)
- Hovering the stripe or clicking a small ⊕ expands it to full width (328px)
- Can be **dragged free** as a standalone window
- Can be **re-attached** to the canvas edge by dragging to the edge
- The tree structure, search, tool buttons, and visibility/lock toggles all stay as-is

**Properties Panel → "Inspector Card"**
- Becomes a **floating card** that:
  - **Appears anchored to the right edge of the canvas** when an item is selected
  - **Auto-hides** (collapses to a thin 4px brass line on the right edge) when nothing is selected
  - Hovering the brass line or selecting an item expands it to 300px
  - Contains all the same contextual property editors, but in a cleaner card layout
  - Multi-select batch edit stays as a sub-card

**Swatches Panel → "Color Strip"**
- Becomes a **floating horizontal strip** of color chips
- Default: collapsed to a **thin bar** (30px tall) at the bottom of the canvas showing only the live eyedropper readout
- Expanded: shows pinned swatches row below
- Can be **dragged to any edge** of the canvas

### 2.2 Panel Behaviors (Shared)
- All panels use `Qt.FramelessWindowHint` + `Qt.WindowStaysOnTopHint` when floating
- A small **drag handle** (brass dot pattern) in the top-left corner of each card
- A **pin button** (📌) in the top-right corner: pinned = always visible; unpinned = auto-hide when losing focus
- Panels remember their position/size per-project via `QSettings`
- **Edge-snap**: dragging a panel near a canvas edge snaps it into a "magnetic attachment" that auto-hides to a thin stripe

---

## Phase 3: Contextual Tool Presentation

### 3.1 Selection Tool Card (PureRef-style)
When any item is selected, a **floating card** appears near the selection (or centered in the canvas if no clear nearness) with:
- **Transform controls**: Move (cursor keys hint), Scale (numeric), Rotation (numeric + 15° snap), Flip H/V, Duplicate, Delete
- **Layer controls**: Send to Back / Bring to Front, Lock/Unlock
- **Item-specific controls**: Crop reset (for references), Blur/Clarity (for references), Text edit (for notes)
- **Close (✕)** button and **Pin (📌)** button

This card replaces the current toolbar's reliance on hotkeys for the most common operations. It's a **direct manipulation interface** — the artist sees the controls right where they're working.

### 3.2 Canvas-Embedded Tool Activation
- Instead of a tool row in the Project Panel, tools appear as **small icon overlays** on the canvas when the relevant layer is visible:
  - Composition active → a small crosshair icon appears at canvas center; clicking arms the focal point tool
  - Perspective active → vanishing point + horizon icons appear; click to place
  - Lighting active → sunburst icon appears; click to place
- These are **gesture hints**, not permanent UI — they fade when the tool is armed or when the mouse moves away
- Right-click on empty canvas → opens a **radial menu** of all layer tools (reference, composition, perspective, lighting, guides)

### 3.3 Right-Click Radial Menu
Replace the current context menu with a **radial menu** (pie menu) that appears on right-click:
- **Inner ring**: Delete, Lock/Unlock, Duplicate, Send to Back, Bring to Front
- **Outer ring**: layer-specific tools (Import for reference, Add Focal Point for composition, 1/2/3-pt for perspective, Add Light for lighting, Guides toggle)
- Each segment highlights on hover with its label and icon
- This becomes the **primary tool navigation** — replacing most of the Project Panel's tool rows

---

## Phase 4: Start Screen & Lifecycle

### 4.1 Immersive Start Screen
Replace the current modal `StartScreen` dialog with an **immersive full-canvas screen**:
- The canvas area fills with a subtle grid of recent project thumbnails
- A large **"+"** button (brass, centered) for New Painting
- An **"∅"** (folder) button for Open
- Recent projects appear as **floating thumbnail cards** with a hover-elevation effect
- The desk color extends to fill the entire window — the start screen feels like walking into a studio

### 4.2 Canvas as the Only Permanent UI
The **entire window** is either:
- The **canvas** (with its desk color background filling everything)
- Or a **temporary overlay** (panels, tool cards, command palette, radial menu)

There is no "chrome" that persists. When fully in work mode, the artist sees only their canvas and their marks.

---

## Phase 5: Visual Identity Evolution

### 5.1 Extended "Machined Panel Plate" Aesthetic
- All floating cards use the **same stroke weight** as canvas markers (1-2px brass lines)
- Cards have **subtle drop shadows** (2px offset, low opacity brass-tinted) to feel like they're floating above the desk
- **No rounded corners** on cards — they're rectangular with sharp brass borders, matching the "machined" language
- The **canvas rect** gets a subtle **glow** (1px brass outline, 20% opacity) when it has focus
- **Brass micro-bevels**: a 1px inner highlight on card borders to suggest depth

### 5.2 Animation & Micro-interactions
- **Fade in/out**: All overlays (tool strip, status strip, tool card) use 150ms `QPropertyAnimation` on opacity
- **Slide**: Panels slide in from the canvas edge when expanded from their stripe state
- **Hover elevation**: Tool icons in the floating strip lift slightly on hover (2px translate)
- **Selection glow**: The selected canvas item's highlight border pulses subtly (brass, 10% brightness oscillation)

### 5.3 No Window Decorations on Floating Cards
- Cards use `Qt.FramelessWindowHint`
- Drag via any non-interactive area
- Close via small ✕ in the top-right corner
- Pin via 📌 in the top-right corner (next to close)
- Resize via a small brass drag handle in the bottom-right corner of each card

---

## Implementation Priority (MVP → Full)

### MVP (Phase A — "Chrome Removal")
1. Remove `QMenuBar` — build a modal command overlay accessible via Ctrl+K and a floating ⋯ button
2. Replace `QToolBar` with a floating hover-revealed icon strip on the left canvas edge
3. Replace `QStatusBar` with a floating hover-revealed strip at the bottom canvas edge
4. Convert the three `QDockWidget`s to floating, frameless cards with pin/auto-hide
5. Add canvas-edge hover detection for all floating elements

*Result: The app no longer looks like a conventional Windows app. It's a canvas with tools that appear on demand.*

### Extended (Phase B — "Contextual Interaction")
6. Add the selection tool card (floating card near selection with transform controls)
7. Add the radial right-click menu
8. Add canvas-embedded tool activation hints
9. Replace the modal start screen with the immersive full-canvas version

*Result: Tools are contextual and canvas-centric. The artist interacts with marks, not menus.*

### Polish (Phase C — "Animation & Micro-interactions")
10. Add fade/slide animations for all UI elements
11. Add hover elevation and selection glow effects
12. Fine-tune the visual identity (shadows, bevels, border weights)

*Result: The interface breathes and recedes, feeling like a digital desk rather than software.*

---

## Technical Considerations

### Qt-Specific Implementation Notes

**Floating card widgets:**
```python
# Each panel card becomes a FramelessWindowHint widget
card = QWidget(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
card.setAttribute(Qt.WA_TranslucentBackground)
# Position absolutely over the canvas viewport
card.setGeometry(canvas_view.mapToGlobal(QPoint(0, 0)), QSize(328, 600))
```

**Fade animations:**
```python
# Use QPropertyAnimation on a QGraphicsOpacityEffect
effect = QGraphicsOpacityEffect(card)
card.setGraphicsEffect(effect)
anim = QPropertyAnimation(effect, b"opacity")
anim.setDuration(150)
anim.setStartValue(0)
anim.setEndValue(1)
```

**Canvas-edge hover detection:**
In `CanvasView`, override `mouseMoveEvent` and `leaveEvent` to show/hide edge strips based on mouse position relative to canvas edges (e.g., within 30px of left edge → show tool strip).

**Radial menu:**
A custom `QWidget` that draws pie segments with `QPainterPath`, with `mousePressEvent`/`mouseMoveEvent` to detect which segment is under the cursor. Can be built as a standalone class in `app/dialogs/` or a new `app/widgets/` directory.

### What This Isn't

This is **not** a rewrite of the core architecture:
- The `InteractiveItem` base class stays
- The `CanvasScene` selection model stays
- The `.atelier` format stays
- The layer system stays
- The undo/redo system stays
- All existing tools and features stay

This is **purely a re-skin and re-structuring of the UI topology** — moving from "Qt standard desktop app" to "canvas-first, chrome-free studio tool."

### Risk Assessment

**Low risk:** The core data model and scene are untouched. All new UI elements are additive — we're replacing Qt widgets (QMenuBar, QToolBar, QDockWidget) with custom QWidgets that call the same underlying methods.

**Medium risk:** The radial menu and floating card positioning need careful event handling to avoid stealing focus from the canvas or creating z-order conflicts. Testing on a real display (not offscreen Qt) is essential for positioning and animation judgment.

**Low risk:** Theme/stylesheet changes are isolated. The `theme.py` stylesheet already supports this — we just need to add styles for the new floating card classes.
