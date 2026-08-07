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
