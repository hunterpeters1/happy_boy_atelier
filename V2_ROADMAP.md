# Happy Boy Atelier — V2 Engineering Assessment & Roadmap

**From:** Senior Engineer
**To:** Hunter (Art Director), ChatGPT (Producer/Product Designer)
**Status:** For review — no V2 implementation has started

This is the first deliverable requested before any V2 code gets written: an
honest read on what v1.0 actually is under the hood, what that means for
where we take it next, and a phased plan sized so each phase ships
something real rather than one long rebuild. Sections 5 and 6 are where I
need your calls before Phase 0 starts.

---

## 1. Current project assessment

### What v1.0 actually is

A PySide6 desktop app built around `QGraphicsView`/`QGraphicsScene` as the
drafting surface. The scene is the single source of truth — every
reference image, focal point, note, vanishing point, and light marker is a
live `QGraphicsItem`; there's no separate data model shadowing it. Save/
load walks the scene once in each direction. Five fixed layers (Reference,
Composition, Perspective, Lighting, Guides) stack in a locked z-order.
Projects are self-contained `.atelier` zip files with images embedded, not
linked. Projector mode renders a snapshot rather than sharing live items
with the editor, so its own zoom/pan/rotation/flip/opacity can't disturb
the working project.

This is a sound foundation. Nothing here needs to be torn out for V2.

### What's solid and should be preserved as-is

- **The scene-is-truth model.** No dual-state bugs, easy to reason about,
  serialization is a straightforward walk. Keep it.
- **The `.atelier` format.** Self-contained, portable, embeds images.
  Right call, no reason to change the container format in V2.
- **The projector-as-snapshot design.** Deliberately decoupled from the
  live editing scene so projector adjustments can never corrupt the
  working project. Correct tradeoff.
- **The "artist decides, software doesn't infer" philosophy.** Every
  marker, grid, and note is placed by hand. This is the actual product
  identity, not an implementation detail — it should be the filter every
  V2 feature gets run through (see Section 4).
- **The instrument-panel visual language** (theme.py) — brass/graphite,
  no corporate-dashboard chrome. Worth extending, not replacing.

### What's missing that a "professional, polished" app needs

- **No undo/redo.** Every mutation (move, scale, rotate, crop, delete,
  lock, property edit) is applied directly and permanently. For a tool
  people will spend hours in, this is the single biggest trust gap.
- **No autosave / crash recovery.** Manual Save only.
- **No automated tests.** Zero. Every fix so far has been manual
  inspection + reasoning, including the click-to-select bug — which is a
  symptom of a deeper issue (next point).
- **Duplicated interaction logic.** Eight call sites across four files
  hand-roll the same `mousePressEvent` override + selection call
  (`ReferenceImageItem`, `FocalPointItem`, `MovementLineItem`, `NoteItem`,
  `LightSourceItem`, `DirectionArrowItem`, `VanishingPointItem`,
  `HorizonLineItem`). That's why the "can't select, only drag" bug could
  exist in the first place, and why the fix had to be applied eight
  separate times instead of once. This should be unified.
- **No performance validation with real reference photo sizes.** Full-
  resolution `QPixmap`s are held in memory per reference image with no
  proxy/thumbnail strategy for on-screen display. Fine for a handful of
  moderate images; untested for what an artist actually imports (a dozen
  12+ MP phone photos).
- **The Layers panel does two jobs.** It's simultaneously a layer
  visibility/lock tree and a tool palette (the "+ Primary Focal" / "+
  Light Source" style buttons live there). Functional, but it reads like
  a debug panel, not a professional tool's UI.
- **`thumb.png` is speced but unused.** The `.atelier` format already
  reserves a thumbnail slot (`atelier_io.save_atelier` accepts one), but
  nothing generates or reads it. A recent-projects screen is effectively
  half-built already.
- **Packaging is fragile and manual.** Getting a working, correctly-
  iconed `.exe` took multiple rounds of debugging (venv activation,
  `--collect-all PySide6`, `--add-data` for the icon to apply at runtime
  and not just to the file, icon cache, file locks). None of that is
  written down anywhere durable — it lived in a chat.

### What should be removed

Nothing structural. The one thing I'd call a "rebuild," not a "removal,"
is the interaction layer — see Section 3.

---

## 2. V2 vision

**Happy Boy Atelier stays a preparation tool, not a creation tool.** V2's
job is to make the existing workflow feel trustworthy, fast, and
considered — not to add capabilities that turn it into a different kind of
application. Concretely, V2 should feel like the difference between a
well-made technical instrument and a prototype: undo/redo, autosave,
consistent interaction behavior, and a properties/tools UI that reads as
intentional rather than assembled.

The test for every proposed feature is the one already stated in the
brief: **does this help an artist create better or faster?** Two features
that pass that test unusually well and aren't in v1.0 at all: an on-canvas
measurement tool, and a non-destructive grayscale/value-check toggle.
Both are direct extensions of "prepare a painting before you touch the
canvas" — arguably more central to the mission than some things already
built. I'd weight these higher than they might initially seem.

---

## 3. Architecture recommendations for V2

- **Undo/redo via `QUndoStack`/`QUndoCommand`.** This is Qt-native, not a
  custom system. Every mutating action (move/scale/rotate/crop, add/
  remove marker, lock toggle, property edit) becomes a command pushed to
  one stack owned by `CanvasScene`. This should happen *early* — the
  longer we build new features on direct mutation, the more retrofitting
  costs later.
- **Unify item interaction into a shared base.** Introduce an
  `InteractiveItem` mixin/base that owns click-to-select, lock state, and
  (once undo/redo exists) command-wrapped moves, so new marker types get
  correct behavior for free instead of being the ninth hand-rolled copy.
- **Split the Layers panel into a Toolbar + a Layers panel.** Toolbar owns
  tool selection (icon-based, persistent). Layers panel owns visibility/
  lock/opacity and the reference image list only. This is a UI change,
  not an architecture change — low risk, meaningfully more professional.
- **Wire up the thumbnail that already has a home in the format.** Render
  a small PNG of the canvas at save time, pass it into `save_atelier`.
  This one's nearly free and unlocks a recent-projects screen.
- **Introduce `tests/` running against offscreen Qt** (`QT_QPA_PLATFORM=
  offscreen`), covering: `.atelier` round-trip serialization (pure-Python
  parts don't even need Qt), scene construction, and undo-stack behavior
  for the core mutating commands. Doesn't need to be exhaustive to be
  worth having — it's the difference between "I reasoned through this
  carefully" and "I can prove it."
- **One canonical build script**, checked into the repo, that bakes in
  everything learned the hard way this round: `--collect-all PySide6`,
  `--add-data` for resources (so the runtime icon matches the file icon),
  pinned PyInstaller version. Replaces ad hoc command reconstruction.

None of this requires touching the `.atelier` format, the five-layer
model, or the projector-as-snapshot design. This is deepening the
foundation, not replacing it.

---

## 4. Phase roadmap

Ordered by user impact vs. dependency risk. Each phase should ship as a
usable build, not a branch that sits unmerged.

### Phase 0 — Foundation & Safety Net
*Nothing here is visible as a "feature," but everything after this phase
is safer and cheaper to build because of it.*

- Undo/redo (`QUndoStack`) wired through all existing mutating actions
- Autosave (periodic recovery snapshot, separate from manual Save)
- Consolidate the eight duplicated interaction call sites into one shared
  base
- Canonical, versioned build script
- Baseline automated tests for serialization + undo-stack behavior

### Phase 1 — Workflow Polish
*Highest visible-impact-per-effort phase; depends on Phase 0's command
infrastructure to do move/edit actions correctly.*

- Split Layers panel into Toolbar + Layers panel
- Save-time thumbnail generation (format already supports it)
- Recent Projects / start screen using those thumbnails
- Properties panel visual pass: live numeric readouts, cleaner crop flow

### Phase 2 — Precision Tools for Traditional Painters
*Directly serves the "prepare before you paint" mission; each is additive,
doesn't touch existing layers.*

- On-canvas ruler / angle measurement tool
- Snapping (rule-of-thirds/golden-ratio intersections, angle snap on
  rotate)
- Non-destructive grayscale/value-check toggle for the reference layer
- Optional: user-defined custom grid spacing beyond thirds/golden ratio

### Phase 3 — Projector Mode Pro
*Most technically involved phase — real geometric complexity (quad-warp
homography), not just UI. Should only be scoped in if Section 5's
question about it comes back "yes, this matters."*

- Corner-pin/keystone correction for off-axis projectors
- Multi-monitor target selection for fullscreen

### Phase 4 — Studio Features
*Evaluate after Phases 0–2 land and get used for real. Flagged explicitly
because these are the features most likely to either earn their keep or
turn into scope creep — see Section 5.*

- Project templates (save canvas + guide setup as a reusable starting
  point)
- Color eyedropper / swatch reference from imported photos
- Multiple open projects (tabs) — **high complexity, changes the app's
  mental model from "one project, one window."** Not recommended without
  explicit sign-off; current workaround (launch the app again) may simply
  be fine.

---

## 5. Technical risks

1. **Retrofitting undo/redo is easier now than later.** Every phase after
   Phase 0 adds more direct-mutation call sites if we don't fix this
   first. This is the main argument for Phase 0 being first, not a
   "someday" item.
2. **Reference image memory footprint is unvalidated.** No proxy/preview
   resolution strategy exists yet. Worth a deliberate look once
   real-world photo sets get tested — I'd rather flag this now than have
   it surface as "the app got slow" after Phase 2 ships.
3. **Packaging fragility is a real cost, not a one-time annoyance.**
   Every future release repeats the icon/`--add-data`/`--collect-all`
   debugging unless the build script is fixed once and reused.
4. **Windows Defender/SmartScreen friction on distributed files.** This
   already happened to the `.bat` script. If V2 ships updates as raw
   `.exe`/`.zip` files, expect this to keep happening. Worth deciding now
   whether a lightweight installer (Inno Setup) or code signing is worth
   the cost — see Section 6.
5. **Scope discipline is the biggest non-technical risk.** Multi-project
   tabs, an eyedropper, templates — none of these are hard to justify
   individually, but stacked together they're how a focused tool becomes
   a bloated one. Recommend treating Phase 4 as "propose again once
   Phases 0–2 are in real use," not pre-committed.

---

## 6. Open questions — need Hunter/ChatGPT input before scoping starts

1. **Projector keystone/corner-pin correction (Phase 3):** is the current
   pan/zoom/rotate/flip actually a limitation you've hit, or is it good
   enough? This is the most technically expensive single feature in the
   roadmap — want to confirm it's earning that cost before scoping it in.
2. **Installer vs. portable exe:** given the packaging friction this
   round, is it worth investing in a proper installer (handles the icon/
   shortcut/Defender friction as a side effect), or does portable-exe-on-
   desktop stay the model?
3. **Grayscale value-check and color eyedropper — philosophy check:**
   both are informational (they help the artist see/measure) rather than
   generative. My read is they're consistent with "artist decides,
   software doesn't." Want your explicit confirmation before Phase 2/4,
   since this is a values question, not a technical one.
4. **Templates (Phase 4):** is this a near-term need (you regularly start
   new paintings from a similar canvas+guide setup) or a nice-to-have?
   Changes whether it belongs in Phase 2 or stays deferred.
5. **Multiple open projects (tabs):** genuinely changes the app's mental
   model. Confirm whether "one project per window instance" is an actual
   limitation worth the complexity, or whether it's fine as-is.
6. **Any branding/identity work** (splash screen, credits, a proper name
   for the "recent projects" screen, etc.) you want folded into Phase 1's
   UI polish while that work is already happening?

---

Awaiting sign-off on the phase order and answers to Section 6 before
Phase 0 implementation starts.
