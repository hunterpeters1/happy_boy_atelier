# Happy Boy Atelier — V2 Engineering Assessment & Roadmap

**From:** Senior Engineer
**To:** Hunter (Art Director), ChatGPT (Producer/Product Designer)
**Status:** Phases 0 through 4 below have now all shipped in some form
(unreleased, see `CHANGELOG.md`) — this document's original assessment and
phase plan are kept below as the historical record they were written as,
with a status note against every item. **Section 7, added after the fact
and kept up to date since, is the current forward-looking roadmap** — read
that first if you just want "what's next."

This was the first deliverable requested before any V2 code got written: an
honest read on what v1.0 actually was under the hood, what that meant for
where to take it next, and a phased plan sized so each phase shipped
something real rather than one long rebuild. Sections 5 and 6's open
questions are mostly still live — they were never explicitly answered —
but enough of Sections 3–4 shipped anyway that this needed a status pass
rather than staying frozen as an unstarted proposal.

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

*(Status against each item added — the assessment itself is left as
originally written.)*

- ✅ **Shipped.** ~~No undo/redo.~~ Every mutation (move, scale, rotate,
  crop, delete, lock, property edit) is applied directly and permanently.
  For a tool people will spend hours in, this is the single biggest trust
  gap. → `QUndoStack` per project, content mutations only.
- ✅ **Shipped.** ~~No autosave / crash recovery.~~ Manual Save only. →
  periodic snapshot + recovery prompt; the recovery-deletion-timing gap
  this created (see Section 7) is now also fixed.
- ✅ **Shipped.** ~~No automated tests.~~ Zero. → 49 tests, run against
  offscreen Qt; the click-to-select bug turned out to be one symptom of
  selection not working *at all*, not "unreliably" — see Section 7.
- ✅ **Shipped.** ~~Duplicated interaction logic.~~ Eight call sites
  across four files hand-roll the same `mousePressEvent` override +
  selection call. → unified into `InteractiveItem`
  (`app/canvas/interactive_item.py`).
- ✅ **Mitigated, and now actually measured.** Reference images are
  hard-capped at 15 per project (`MAX_REFERENCE_IMAGES`,
  `app/constants.py`) — this app plans a painting with a handful of
  references, not a bulk photo library, so an unbounded count was never
  actually needed. Real numbers, not just the cap, now back this up:
  Hunter tested with 20 real iPhone photos (deliberately past the cap,
  via a project loaded from before the limit existed) and Task Manager
  reported 800MB. That lines up almost exactly with the architecture's
  own math — a 12MP `QPixmap` held uncompressed in memory is ~49MB
  (4032×3024 px × 4 bytes/px), so 20 images plus ~100-150MB of baseline
  Qt/Python/UI overhead lands right around 800MB. Unremarkable on any
  machine with 8GB+ RAM, and at the actual 15-image ceiling the expected
  total is meaningfully lower still. The long-standing "unvalidated"
  status is retired — this was checked with real photos, not assumed.
- ✅ **Shipped, further than proposed.** ~~The Layers panel does two
  jobs.~~ Simultaneously a layer visibility/lock tree and a tool palette,
  reading like a debug panel. → rebuilt as the Project Panel: a real
  outliner listing every placed item (not just references), search, and
  the tool-activation buttons kept but demoted to a compact row rather
  than being the panel's main content.
- ✅ **Shipped.** ~~`thumb.png` is speced but unused.~~ → every save
  renders and embeds a real thumbnail; a recent-projects start screen
  uses it.
- **Unchanged by design, not fixed.** Packaging is fragile and manual. →
  investigated further and the conclusion changed: every *script* tried
  around the spec file got flagged/blocked by Windows on this machine, so
  the supported path is now deliberately a manual command sequence
  (`HappyBoyAtelier.spec` + `requirements-build.txt`, see `CLAUDE.md`),
  not a script. Revisit only if that changes (see Section 7's packaging
  note).

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

### Phase 0 — Foundation & Safety Net — ✅ done
*Nothing here is visible as a "feature," but everything after this phase
is safer and cheaper to build because of it.*

- ✅ Undo/redo (`QUndoStack`) wired through all existing mutating actions
- ✅ Autosave (periodic recovery snapshot, separate from manual Save) —
  plus a timing bug this created (recovery deleted before the artist's
  first post-recovery save) found and fixed since
- ✅ Consolidate the eight duplicated interaction call sites into one
  shared base — and the deeper selection bug this consolidation exposed
  is now also fixed (Section 7)
- ⬜ Canonical, versioned build script — superseded by policy, see the
  "Unchanged by design" note in Section 1
- ✅ Baseline automated tests for serialization + undo-stack behavior —
  49 tests as of this writing

### Phase 1 — Workflow Polish — ✅ done, one item partial
*Highest visible-impact-per-effort phase; depends on Phase 0's command
infrastructure to do move/edit actions correctly.*

- ✅ Split Layers panel into Toolbar + Layers panel — went further: the
  Layers panel became a real outliner (the Project Panel), not just a
  visibility/lock tree
- ✅ Save-time thumbnail generation (format already supports it)
- ✅ Recent Projects / start screen using those thumbnails
- ✅ Properties panel visual pass: live numeric readouts (vanishing
  point/horizon coordinates are now editable, not a read-only label);
  cleaner crop flow — done in v1.3 ("crop workflow" commit): crop is now
  direct in-place edge-handle manipulation, no Crop…/Apply/Cancel
  buttons or crop mode to enter/exit.

### Phase 2 — Precision Tools for Traditional Painters — ✅ done
*Directly serves the "prepare before you paint" mission; each is additive,
doesn't touch existing layers.*

- ✅ On-canvas ruler / angle measurement tool — `MeasurementItem`
  (`app/layers/composition_layer.py`), placed via the existing two-click
  tool pattern; reports length and angle from horizontal in one placed
  segment.
- ✅ Snapping — angle snap on rotate (Shift, 15°), reference-image
  center-to-center/center-to-canvas-center snapping, rule-of-thirds/
  golden-ratio-intersection snapping, and true edge-to-edge (not just
  center-to-center) snapping have all shipped
  (`ReferenceImageItem._snap_position()`).
- ✅ Non-destructive grayscale/value-check toggle for the reference layer
  — per-image `grayscale_amount()` field (same shape as Blur/Line
  Clarity) plus a `toggle_grayscale_all()` macro for the whole reference
  set at once.
- ✅ Closed, superseded. Optional user-defined custom grid spacing
  beyond thirds/golden ratio was never built — a fixed 1-inch grid
  overlay shipped instead (`InchGridOverlay`, `app/layers/guide_overlay.py`,
  sized off `C.SCENE_PX_PER_INCH` so its lines land exactly on the
  ruler's own inch ticks — for the classic grid-method drawing
  technique). Hunter's call: that single fixed spacing already covers
  the real use case well enough that arbitrary custom spacing isn't
  worth building.

### Phase 3 — Projector Mode Pro — ⬜ cut, moot
*Most technically involved phase — real geometric complexity (quad-warp
homography), not just UI. Should only be scoped in if Section 5's
question about it comes back "yes, this matters."* Moot: projector mode
itself (the foundation this phase would have built on) has since been
removed from the app entirely, not just left unstarted.

- ⬜ Corner-pin/keystone correction for off-axis projectors
- ⬜ Multi-monitor target selection for fullscreen

### Phase 4 — Studio Features — 🟨 mostly done, see Section 7
*Evaluate after Phases 0–2 land and get used for real. Flagged explicitly
because these are the features most likely to either earn their keep or
turn into scope creep — see Section 5.* Phases 0–3 have now landed and
been used for real; this phase was re-proposed and mostly landed, per the
UI upgrade plan's own Section D.

- ✅ Project templates (save canvas + guide setup as a reusable starting
  point) — `app/project_templates.py`, `MainWindow.save_as_template()`
- ✅ Color eyedropper / swatch reference from imported photos — shipped
  earlier than this document tracked (README's Eyedropper + Swatches
  dock)
- ⬜ Multiple open projects (tabs) — **high complexity, changes the app's
  mental model from "one project, one window."** Not recommended without
  explicit sign-off; current workaround (launch the app again) may simply
  be fine. Still unanswered — see Section 6, item 5.

---

## 5. Technical risks

1. **Retrofitting undo/redo is easier now than later.** Every phase after
   Phase 0 adds more direct-mutation call sites if we don't fix this
   first. This is the main argument for Phase 0 being first, not a
   "someday" item.
2. **Reference image memory footprint — bounded AND measured now.** No
   proxy/preview resolution strategy exists for the *stored*
   full-resolution copy, and the project count is hard-capped at 15 per
   project (see Section 1's matching note) rather than that cost being
   engineered away. But it's no longer just a guess: real-world testing
   with 20 actual iPhone photos measured 800MB, matching the
   architecture's own math (~49MB per 12MP `QPixmap` held uncompressed
   in memory, plus baseline app overhead) almost exactly. Unremarkable
   on any machine with 8GB+ RAM. Worth a fresh look only if a future
   feature needs more than 15 references per project.
3. **Packaging fragility is a real cost, not a one-time annoyance.**
   Every future release repeats the icon/`--add-data`/`--collect-all`
   debugging unless the build script is fixed once and reused. — ✅
   `HappyBoyAtelier.spec` now bakes both fixes in permanently; what
   didn't survive was the *script* wrapped around it (see Section 1's
   packaging note) — the fixes themselves did.
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
   Moot as of the projector mode removal — nothing to correct keystone
   *of* anymore.
2. **Installer vs. portable exe:** ✅ **answered in direction.** For a
   real product, Hunter wants an installer, not a portable exe. The
   condition attached: the deciding factor is how annoying it is to get
   a new build in front of users after a fresh idea, not the initial
   install experience — so this isn't fully scoped until that update
   workflow (checking for/delivering a new version, not just the first
   install) is actually designed. See Section 7's "concrete next phase."
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
   UI polish while that work is already happening? — the naming half
   shipped ("Start Screen"); a proper About dialog (app icon, name/
   version, mission line, credits — Help menu) has since shipped too. A
   pre-launch splash screen is still open, and was deliberately scoped
   out again in the UI upgrade plan as real added complexity for a
   fast-starting desktop app.

---

## 7. Where things actually stand, and what's next

Written after Phases 0 and most of 1 above shipped, plus a full
ground-up UX/interaction audit that went beyond this document's original
scope (see `CHANGELOG.md`'s "UX redesign" entry for the itemized list).
The single biggest finding wasn't on this roadmap at all: item selection
didn't actually work — at all, not "unreliably" — for any marker in the
shipped app, which is now fixed at the root (`CanvasScene`'s own
selection model, replacing Qt's, since `QGraphicsItem.setSelected()`
never stuck for children of these `QGraphicsItemGroup` layers).

### Carried forward from Sections 4–6, still genuinely open
- Multiple open projects/tabs (Phase 4) — still gated on Section 6 item
  5; templates and the color eyedropper have since shipped (see Section
  7's Phase 4 status above)
- Installer vs. portable exe (Section 6 item 2) — **answered in
  direction, not yet in detail:** for a real product, Hunter's call is
  an installer, not a portable exe. The condition attached is update
  friction — how annoying it is to ship a new build after a fresh idea
  — so this isn't fully scoped until that update workflow is actually
  designed (see Section 6 item 2's updated note).

Custom grid spacing (Phase 2) and the bundled critique-pack export are
both now closed — see Phase 2's status above and the "removed" note
under Batch export presets below, respectively. The reference-image
memory footprint question (Section 1, Section 5 item 2) is also closed
now, not just bounded — see Section 1's updated note: real testing with
20 iPhone photos measured 800MB, matching the architecture's expected
math closely enough that this no longer needs a dedicated follow-up.

All other Phase 2 items (measurement tool, grayscale/value-check toggle,
rule-of-thirds/golden-ratio-intersection snapping, true edge-to-edge
snapping) have since shipped — see Phase 2's status above.

### New, discovered while implementing the phases above
Each of these was a deliberate, explicitly-flagged scope cut in its
phase's own commit — not an oversight — kept here so they aren't lost:

- **Drag-to-reorder within a layer** in the Project Panel. No layer
  group class exposes a reorder operation yet; needs that added first,
  then the tree's drag/drop wiring.
- **True hover-reveal row icons** in the Project Panel (visibility/lock
  icons only appearing on hover, per the original redesign vision).
  Needs a custom `QTreeWidget` item delegate; the icons are small and
  always-visible instead for now, which is a reasonable permanent state
  too if hover-reveal turns out not to be worth the delegate complexity.
- **A cross-project reference library.** — ✅ done
  (`app/library.py`, `app/panels/library_panel.py`): a personal
  collection independent of any one painting, drag-or-double-click into
  the current project, turning reference-gathering into an ongoing
  practice instead of a per-painting chore.
- **Folder-based sync** (point the app at a Dropbox/Drive/NAS folder,
  treat `.atelier` files there like any other project) as a "work across
  two machines" answer that doesn't compromise the "no cloud accounts"
  design commitment, since there's no account or server involved — just
  a folder the artist already trusts.
- **Batch export presets** — ✅ done (`app/dialogs/export_dialog.py`'s
  Preset combo: save a named format/DPI/Study-Blur configuration, reuse
  it across paintings). A bundled "critique pack" export (canvas render
  + planning notes, zipped for a mentor without handing over the live
  project) was proposed here too, but Hunter no longer wants it —
  dropped, not just deferred.
- **Reference-image cap (15 per project)** — ✅ done
  (`MAX_REFERENCE_IMAGES`, `app/constants.py`), enforced at
  `MainWindow._import_image_paths()`, the one entry point the Import
  dialog, OS drag-and-drop, and the Library panel's drag-in all already
  shared. Grew directly out of the memory-footprint risk above — see
  Section 1/5's updated notes — plus a plain judgment call that this app
  was never meant to manage a bulk photo library. All-or-nothing: an
  import that would exceed the cap is refused entirely, not silently
  truncated. A pre-existing project that already exceeds 15 (predating
  the cap, or hand-edited) still opens and loads every image untouched —
  the cap only ever blocks new imports.
- **Phone uploader hardening and polish** — ✅ done, three related
  pieces, all in `uploader/`: (1) instant per-photo preview tiles while
  uploading, using `createImageBitmap`'s resize option so the browser
  never decodes a full 12-48MP phone photo just to paint a ~100px tile;
  (2) the same 15-item cap philosophy applied to a single upload batch,
  refused outright rather than truncated; (3) real visual identity for
  both the login and gallery pages — an "instrument panel" card, the
  same corner-rivet hardware motif the desktop app uses on its canvas
  and dock title bars, and the actual "HB" app icon rendered large as a
  proper logo instead of only ever appearing tiny as a favicon.

### A concrete next phase, if picking one
Phase 2 is done, the memory-footprint risk is bounded (not fully closed
— see Section 5 item 2), custom grid spacing is superseded by the
1-inch grid, and the critique-pack export is dropped outright — none of
those are pending work anymore. What's left both genuinely open and
worth doing:

- **Design the actual update workflow**, now that Hunter's answered the
  installer question in direction ("for a product, an installer"): what
  does going from "I have a new idea" to "a user is running the new
  build" actually look like? An installer alone (e.g. Inno Setup)
  handles the icon/shortcut/Defender friction from a fresh install, but
  doesn't by itself give you *update* delivery (checking for a new
  version, prompting, re-running the installer) — that's a separate
  piece of design/scope, and it's the exact friction Hunter flagged as
  the deciding factor. Worth scoping concretely before committing
  engineering time to either half.
- **Multiple open projects/tabs** (Section 6 item 5) — still
  unanswered, still gated on explicit sign-off given the complexity/
  mental-model cost already flagged.

---

Awaiting sign-off on the phase order and answers to Section 6 before
Phase 0 implementation starts.
