# Happy Boy Atelier — Team Roles

## Vision

A digital drafting table for traditional painters: pick a format,
arrange reference photos, and plan composition, perspective, and
lighting before touching a physical canvas. Not a paint program and not
an AI image generator — every mark is placed by the artist; the software
never infers composition, perspective, or lighting.

## Architecture Rules

- PySide6 (Qt) desktop application, Windows-targeted.
- The scene (`QGraphicsScene`) is the single source of truth — no shadow
  data model to keep in sync. Save walks the scene once; load rebuilds
  it once.
- Preserve `.atelier` project-file compatibility. Every schema addition
  needs a `.get(key, default)`-style fallback so older project files
  keep opening correctly — never a hard break tied to a format-version
  bump unless truly unavoidable.
- Avoid unnecessary rewrites. Extend existing patterns (the
  `InteractiveItem` base, the five fixed-order layer groups, the
  undo-command shapes, the tool-arming machinery) rather than
  introducing parallel ones that do the same job a different way.
- No AI generation, no brush engine, no cloud accounts, no social/
  marketplace features — explicitly out of scope.

## Agent Roles

- **Claude** — Architecture. Owns design decisions, cross-cutting
  changes, planning, and review of work before it lands.
- **Hermes** (poolside/laguna-s-2.1) — Implementation. Executes scoped
  implementation tasks handed off by Claude, within the boundaries set
  above.

## Review & Handoff Protocol

Prompted by a real incident: the v1.3 crop-workflow rework (commit
`7548a5d`) was implemented, tested (5 passing tests), and looked done —
but a gating condition Hermes added made cropping unreachable from the
UI for any newly-imported image, and the one test that touched that
state asserted the broken behavior as correct. The mechanism below
exists to catch that class of gap before it's called finished, not to
add process for its own sake.

- **`proposal.txt`** (repo root, untracked — never committed) is the
  handoff channel for anything bigger than a routine scoped task:
  audits, open design questions, "here's what I'm about to do and why."
  Hermes writes it; Claude reads it at the start of a session (see
  `CLAUDE.md`) and appends a `## Claude's Review — <date>` section
  answering it in place. Hermes should not treat silence as approval —
  wait for that section to appear before proceeding on anything the
  proposal flagged as a genuine question rather than a heads-up.
- When writing a proposal, **mark each item BLOCKING or FYI.** BLOCKING
  means Hermes waits for Claude's answer before acting on that item; FYI
  means it's a heads-up on something already decided/in progress and
  needs no reply to proceed. This lets Claude's review pass focus on
  what's actually gating Hermes, instead of re-deriving which of N
  items were genuine questions.
- Once a proposal's answers have been read and acted on, delete
  `proposal.txt` (or the answered section) rather than leaving it
  sitting there — a stale answered proposal left in place is easy to
  mistake for a new unanswered one on the next pass. A "hold off, don't
  implement this" answer still counts as fully acted on — see Decisions
  Log below for where that verdict actually needs to persist, since it
  won't survive in `proposal.txt` itself.
- **Implement exactly what was approved.** If reality forces a
  deviation from an approved approach mid-implementation, that's a new
  round-trip through `proposal.txt`, not a silent judgment call —
  scope/approach drift is exactly what let the crop bug ship as
  "done."
- **A feature isn't done until its default/first-use path is tested,
  not just its already-configured path.** The crop test suite covered
  editing an *existing* crop thoroughly and never once constructed a
  fresh, never-cropped image and tried to crop it — which was the only
  path a real user ever hits first. When adding tests for a new
  interaction, include the state a brand-new object starts in, not only
  states reached after some setup.
- **User-visible behavior changes update `README.md` in the same
  commit.** This was already the norm (`v1.1`, `v1.2` both did it) —
  `v1.3` broke that norm and shipped with README describing a workflow
  that no longer existed. Treat README staleness as a blocker on the
  same level as a failing test, not a follow-up.
- **Removing/renaming a public method requires updating every call
  site in the same change** — don't leave a back-compat alias as an
  implicit TODO for someone else to notice later.

## Decisions Log

`proposal.txt` is deleted once its answers are acted on, so a "yes, do
it" verdict is fine — the resulting commit is its own permanent record.
A "no, hold off" verdict has no commit to live in, so it goes here
instead, one line per declined/deferred item, so the same question
doesn't get silently re-litigated later without whoever's asking
knowing it was already considered. Only add an entry for a real "no,
and here's why" — don't log routine approvals.

- **Split `ReferenceImageItem` into collaborators** (CropController,
  DisplayPixmapCache, StudyBlurCache, etc.) — declined 2026-08-07. It's
  the file the crop-handle visibility regression shipped from; doing a
  large structural refactor on the highest-risk file right after finding
  a bug in it is backwards. Revisit only once it's gone through at least
  one more real change untouched by a bug, or a concrete new feature
  genuinely needs the split — not as a standalone cleanup.
- **Generic `PropertyEditor` helper** for PropertiesPanel's 7 near-
  identical baseline/commit property patterns — declined 2026-08-07 as
  a standalone effort. Only worth it if PropertiesPanel is already being
  touched for an unrelated reason in the same change.
- **Animated GIF reference support** (QMovie-driven playback, frame
  scrubbing, per-frame Study Blur) — declined 2026-08-07. Real
  complexity (timer-driven pixmap swap in the display cache, a Study
  Blur exception) for a motion-study use case that's a weak fit for a
  *pre-painting planning* tool; also new scope ahead of finishing Phase
  2, which V2_ROADMAP.md already flags as the actual next priority.
- **Image-level wheel zoom on hover** (scroll-to-zoom just the reference
  image under the cursor, instead of the whole canvas) — declined
  2026-08-07. Usability risk: users can't reliably predict what a
  wheel-scroll will zoom when it depends on cursor position over a
  specific item versus empty canvas; the existing scene-level zoom
  (5%-2400%) plus Fit Canvas already covers close study.

## Full technical reference

`CLAUDE.md` is the detailed engineering reference for this codebase —
architecture internals, file-format specifics, and the hard-won gotchas
(confirmed via runtime testing, not guessed) that make the difference
between a change that looks right and one that actually is right. It's
loaded automatically by Claude Code at the start of every session; any
other agent working on this repo, including Hermes, should read it
explicitly before making non-trivial changes.

`README.md` documents the full user-facing feature scope — read it
before proposing something as a "new" feature, since several things
here only exist as buttons inside the Project Panel rather than the
toolbar/menu and are easy to assume don't exist.
