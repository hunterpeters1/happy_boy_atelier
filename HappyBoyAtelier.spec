# PyInstaller build spec for Happy Boy Atelier.
#
# There is deliberately no build script (build.bat, PowerShell helpers,
# etc.) — every one tried got flagged/blocked by Windows on the dev
# machine, since a downloaded script that installs things and calls
# other scripts is exactly what SmartScreen/AV heuristics watch for.
# Build by typing the commands yourself (see CLAUDE.md's "Building the
# .exe" section for the full sequence, including requirements-build.txt):
#     python -m PyInstaller HappyBoyAtelier.spec --noconfirm
#
# Produces a single-file, windowed (no console) executable at
# dist/Happy Boy Atelier.exe. PyInstaller cannot cross-compile, so this must
# be run on a Windows machine to produce a Windows .exe.
#
# Two things this spec bakes in on purpose, both found the hard way during
# v1.0 packaging:
#   - collect_all("PySide6"): without it, the built exe raises
#     ModuleNotFoundError: No module named 'PySide6' at runtime even though
#     the build itself reports success.
#   - datas=[("resources", "resources")]: without it, setWindowIcon() silently
#     no-ops inside the frozen exe (the *file* icon from --icon still works,
#     but the title-bar/Alt-Tab icon doesn't), because app_icon_path() can't
#     find resources/icons/app.ico inside the bundle at runtime.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

pyside_datas, pyside_binaries, pyside_hiddenimports = collect_all("PySide6")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=pyside_binaries,
    datas=pyside_datas + [("resources", "resources")],
    hiddenimports=pyside_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Happy Boy Atelier",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/icons/app.ico",
)
