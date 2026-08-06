# Happy Boy Atelier — V2 Engineering Assessment & Roadmap

**From:** Senior Engineer
**To:** Hunter (Art Director), ChatGPT (Producer/Product Designer)
**Status:** Phase 0 and most of Phase 1 below are now shipped (unreleased,
see `CHANGELOG.md`) — this document's original assessment and phase plan
are kept below as the historical record they were written as, with a
status note against every item. **Section 7, added after the fact, is
the current forward-looking roadmap** — read that first if you just want
"what's next."

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
- ⬜ **Still open.** No performance validation with real reference photo
  sizes. Full-resolution `QPixmap`s are held in memory per reference
  image with no proxy/thumbnail strategy for on-screen display. Fine for
  a handful of moderate images; untested for what an artist actually
  imports (a dozen 12+ MP phone photos). Carried into Section 7.
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
  (README's "Build a standalone .exe"), not a script. Revisit only if
  that changes (see Section 7's packaging note).

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
- 🟨 Properties panel visual pass: live numeric readouts ✅ (vanishing
  point/horizon coordinates are now editable, not a read-only label);
  cleaner crop flow — only partially: Escape now exits crop mode, but
  the two-step Apply/Cancel button flow itself is unchanged. Candidate
  for Section 7.

### Phase 2 — Precision Tools for Traditional Painters — 🟨 partial
*Directly serves the "prepare before you paint" mission; each is additive,
doesn't touch existing layers.*

- ⬜ On-canvas ruler / angle measurement tool — not started, carried into
  Section 7
- 🟨 Snapping — angle snap on rotate (Shift, 15°) ✅ and reference-image
  center-to-center/center-to-canvas-center snapping shipped, but *not*
  the rule-of-thirds/golden-ratio-intersection snapping this line
  originally proposed, nor true edge-to-edge (vs. center) snapping —
  both carried into Section 7
- ⬜ Non-destructive grayscale/value-check toggle for the reference layer
  — not started, carried into Section 7
- ⬜ Optional: user-defined custom grid spacing beyond thirds/golden ratio
  — not started (the *perspective* grid already had custom spacing
  before this doc was written; this item is specifically about the
  Guides layer's two fixed overlays)

### Phase 3 — Projector Mode Pro — ⬜ not started
*Most technically involved phase — real geometric complexity (quad-warp
homography), not just UI. Should only be scoped in if Section 5's
question about it comes back "yes, this matters."* Still an open
question — see Section 6, item 1, still unanswered.

- ⬜ Corner-pin/keystone correction for off-axis projectors
- ⬜ Multi-monitor target selection for fullscreen

### Phase 4 — Studio Features — ⬜ not started
*Evaluate after Phases 0–2 land and get used for real. Flagged explicitly
because these are the features most likely to either earn their keep or
turn into scope creep — see Section 5.* Phases 0 and (mostly) 1 have now
landed and been used for real; this phase is worth actually revisiting.

- ⬜ Project templates (save canvas + guide setup as a reusable starting
  point)
- ⬜ Color eyedropper / swatch reference from imported photos
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
2. **Reference image memory footprint is unvalidated.** No proxy/preview
   resolution strategy exists yet. Worth a deliberate look once
   real-world photo sets get tested — I'd rather flag this now than have
   it surface as "the app got slow" after Phase 2 ships.
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
   UI polish while that work is already happening? — the naming half
   shipped ("Start Screen"); splash screen/credits are still open if
   wanted.

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
- On-canvas ruler/angle measurement tool (Phase 2)
- Non-destructive grayscale/value-check toggle (Phase 2)
- Rule-of-thirds/golden-ratio-intersection snapping, and true edge-to-
  edge (not just center-to-center) reference-image snapping
- Reference-image memory footprint / proxy-resolution strategy (Section
  1, Section 5 item 2) — still genuinely unvalidated
- Projector keystone/corner-pin + multi-monitor target selection (Phase
  3) — still gated on Section 6 item 1's unanswered question
- Templates, color eyedropper, multiple open projects/tabs (Phase 4) —
  still gated on Section 6 items 4–5; worth actually re-proposing now
  that Phases 0–1 are in real use, per this doc's own original plan
- Installer vs. portable exe (Section 6 item 2) — still open, and more
  pointed now that the build path is a manual command sequence by firm
  policy rather than a placeholder

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
- **Cleaner crop flow.** Carried over from Phase 1's "partial" status
  above — Escape now exits crop mode, but entering/applying/cancelling
  is still a three-button flow (Crop…/Apply Crop/Cancel) rather than a
  more direct in-place drag-to-crop gesture.
- **A cross-project reference library.** Right now every imported image
  lives and dies inside one project's `.atelier` zip. A personal,
  taggable collection independent of any one painting — drag into any
  open project — would turn reference-gathering into an ongoing
  practice instead of a per-painting chore, and is a natural complement
  to the recent-files work in Phase 7.
- **Folder-based sync** (point the app at a Dropbox/Drive/NAS folder,
  treat `.atelier` files there like any other project) as a "work across
  two machines" answer that doesn't compromise the "no cloud accounts"
  design commitment, since there's no account or server involved — just
  a folder the artist already trusts.
- **Batch export presets** (save a named format/DPI/notes-on-off
  configuration, reuse it across paintings) and a **bundled "critique
  pack" export** (canvas render + planning notes, zipped for sending to
  a mentor without handing over the live editable project).

### A concrete next phase, if picking one
Given what's already landed, the highest-leverage next slice is probably
**"Phase 2, finished"**: the on-canvas measurement tool and the
grayscale/value-check toggle are the two items this document's own
Section 2 called out as scoring unusually well against the "does this
help an artist create better or faster" test and *not yet started* —
both are additive (don't touch existing layers), both fit the existing
`InteractiveItem`/undo-stack/Project-Panel infrastructure directly, and
neither is gated on an unanswered open question the way Phases 3–4 are.
Section 6 items 1, 4, and 5 are still worth getting explicit answers on
before scoping Phases 3–4, same as originally proposed.

---

Awaiting sign-off on the phase order and answers to Section 6 before
Phase 0 implementation starts.
