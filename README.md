# Happy Boy Atelier

A digital drafting table for traditional painters. Prepare a physical
painting before you touch the canvas: pick a format, arrange reference
photos, plan composition, perspective, and lighting, then throw the setup
onto the wall in projector mode. It is not a painting app and not an image
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

## Quick tour

- **File > New Painting…** — choose a portrait/landscape/square preset or a
  custom width/height/unit.
- **Import** — bring in reference photos; each becomes its own object you
  can drag, resize (corner handles — free by default, hold Shift to lock
  proportions), rotate (handle above the image), or crop (Properties
  panel).
- **Layers & Tools** (left dock) — toggle visibility/lock per layer, and
  place composition markers, perspective grids, and lighting notes.
- **Properties** (right dock) — edit whatever is currently selected.
- **Mode > Lock Setup** — freezes every layer so nothing moves by accident
  once the plan is final.
- **Mode > Enter Projector Mode (F5)** — fullscreen view of the reference
  layer with its own opacity/zoom/pan/rotation/flip and a Lock Projection
  toggle, for tracing the setup onto the physical canvas.
- **File > Save / Open** — projects are single portable `.atelier` files;
  reference images are embedded, never linked externally.
- **File > Export…** — PNG, JPG, or a one-page PDF planning sheet.

## What's intentionally not here

AI image generation, a brush/paint engine, cloud accounts, and social or
marketplace features are out of scope by design — see the "Out of Scope"
section of the product spec and `ARCHITECTURE.md`.

## Status

**v1.0.0** — see `CHANGELOG.md`. Covers the full MVP workflow: create canvas
→ import & arrange references → composition guides → perspective grids →
lighting notes → save/reopen → projector mode → lock setup.
