# Releasing Happy Boy Atelier

How to cut a release of the portable Windows exe. The installer (Inno
Setup) is deliberately on hold — see `V2_ROADMAP.md` Section 6 item 2 —
so this covers the portable build only. Build commands themselves live
in `CLAUDE.md` ("Building the .exe"); this file is the order of
operations around them.

A release matters beyond distribution: the in-app update check reads
this repo's GitHub Releases, so publishing one is also what makes the
check do anything at all. Until the first release is published, it gets
a 404 and stays silent.

## Where things stood when this was written (Oct 2026)

- GitHub has **no tags and no releases**. `README.md` and `CLAUDE.md`
  both describe v1.0.0 as the last tagged release, but no `v1.0.0` tag
  exists in this repo's remote. If one exists on the machine v1.0.0 was
  built on, push it; if not, nothing here depends on it.
- `C.APP_VERSION` is still `"1.0.0"` (`app/constants.py`), despite a
  large amount of unreleased work since (see `CHANGELOG.md`).
- The update check (`app/update_check.py`) was added **after** v1.0.0.
  A v1.0.0 exe does not contain it, so the first release you publish
  cannot notify anyone running that old build — only builds that already
  include the check will ever show the notice.

## What the update check needs from a release

The running app does one GET to `/releases/latest` and shows a notice
only if all of these hold:

- The release is **published** — not a draft, and not marked
  pre-release (GitHub's `latest` endpoint skips both).
- The tag is plain dot-separated integers with an optional leading `v`:
  `v1.1.0` works; `v1.1.0-beta` is ignored on purpose.
- The tag is **strictly greater** than the running build's
  `C.APP_VERSION`.

Corollary: the exe you attach must have `APP_VERSION` equal to the tag.
Ship a `v1.1.0` release built from a tree that still says `1.0.0` and
every user of that exe is told, forever, that their own release is an
available update.

## Decide before you start

1. **The version number.** `C.APP_VERSION` is the single source of
   truth — it feeds the About dialog, `QApplication.setApplicationVersion()`,
   and the update check, and the spec files carry no version of their
   own. `C.FORMAT_VERSION` is the `.atelier` file schema and is
   independent: do **not** bump it for an app release (every schema
   addition has a `.get(key, default)` fallback instead — see
   `TEAM_ROLES.md`).
2. **What ships next to the exe.** `uploader/` is never bundled into the
   exe, and its venv can't be. A lone downloaded exe will answer
   Options > Upload From Phone… with "The uploader hasn't been set up
   yet. Open a terminal in uploader/…" — instructions for a folder that
   user doesn't have. This is an open decision, not a solved one. The
   choices are roughly: ship the exe alone and say in the release notes
   that phone upload needs a source checkout; or ship a zip laid out the
   way `resources.uploader_root()` expects (`dist/Happy Boy Atelier.exe`
   with `uploader/` a sibling of `dist/`) plus setup instructions; or
   change what the dialog says when `uploader/` is absent.
3. **Whether to also publish the Linux binary.** It has its own spec
   (`HappyBoyAtelierLinux.spec`) and has to be built on Linux.

## Checklist

### 1. Prepare the release commit

- [ ] On `master`, up to date, working tree clean.
- [ ] `pytest` passes.
- [ ] Bump `APP_VERSION` in `app/constants.py`.
- [ ] `CHANGELOG.md`: fold the stacked `## Unreleased — …` sections into
      one `## vX.Y.Z — YYYY-MM-DD` heading, keeping their sub-sections.
- [ ] Update the "last tagged release" wording in `README.md` (Status),
      `CLAUDE.md` (Current development phase), and the status note at
      the top of `V2_ROADMAP.md`.
- [ ] Commit (`Release vX.Y.Z`) and push to `master`.

### 2. Build — Windows only, typed by hand

There is deliberately no build script; every one tried got flagged by
Windows. From the repo root, with the venv active:

```
pip install -r requirements-build.txt
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python -m PyInstaller HappyBoyAtelier.spec --noconfirm
```

Output: `dist\Happy Boy Atelier.exe`.

- [ ] Build from the release commit with a clean tree, so the exe and the
      tag describe the same code.
- [ ] Don't strip `collect_all("PySide6")` or `datas=[("resources", "resources")]`
      from the spec if you touch it.

### 3. Smoke-test the built exe (not `python main.py`)

- [ ] It launches, and the window/taskbar icon is the app's, not a
      generic one (that's the `resources` data folder working).
- [ ] Options > About shows `vX.Y.Z`.
- [ ] An older `.atelier` file (anything saved by an earlier build)
      opens correctly.
- [ ] New painting → import a reference → save → reopen → export a PNG.
- [ ] Options > Upload From Phone… does what you decided in step 2 of
      "Decide before you start".

### 4. Tag and publish

- [ ] Tag the release commit and push the tag:
      `git tag -a vX.Y.Z -m "vX.Y.Z"` then `git push origin vX.Y.Z`.
- [ ] On GitHub: Releases → Draft a new release from that tag. Summarize
      the `CHANGELOG.md` entry in the notes.
- [ ] Attach `Happy Boy Atelier.exe` (and the Linux binary, if built).
      Attach the exe itself — not a zip containing helper scripts.
      The exe is unsigned, so say in the notes that Windows SmartScreen
      may warn on first run.
- [ ] Publish it as the **latest** release: not a draft, not a pre-release.

### 5. Verify the update check end to end

- [ ] `https://api.github.com/repos/hunterpeters1/happy_boy_atelier/releases/latest`
      returns your release, with `tag_name` equal to `vX.Y.Z` (not a 404).
- [ ] Launch the **new** exe with a network connection: no
      "Update available" notice. (If one appears, `APP_VERSION` wasn't
      bumped in that build — see below.)
- [ ] Launch an **older** build that already contains the update check
      (e.g. `python main.py` from a pre-bump commit): the status bar
      shows "Update available: vX.Y.Z", the link opens the release
      page, and ✕ dismisses it and keeps it dismissed across a restart.

## If something goes wrong

- **The new build shows a notice for its own release.** `APP_VERSION`
  wasn't bumped in the tree it was built from. Rebuild from the correct
  commit and replace the attached exe; if the tag points at the wrong
  commit, that's a decision to make deliberately (publishing a patch
  version is usually cleaner than moving a pushed tag).
- **Old builds never show a notice.** Check, in order: the release is
  published and not a pre-release; the tag parses (no `-beta` suffix);
  the old build actually contains `app/update_check.py`; the toggle in
  Settings ("Check for updates on startup") is on.
- **Failures are silent by design.** No network, GitHub down, a rate
  limit, or a malformed response all just mean no notice — the check
  never shows an error. Verify with the API URL above, not with the app.
