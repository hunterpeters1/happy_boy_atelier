# PyInstaller build spec for Happy Boy Atelier -- Linux.
#
# A separate file from HappyBoyAtelier.spec (the Windows one), not a
# conditional branch inside it, so nothing about the Windows build path
# is ever at risk from a Linux-only tweak -- see CLAUDE.md's own reasons
# for keeping the build process manual and simple rather than clever.
# PyInstaller cannot cross-compile, so this must be run on Linux to
# produce a Linux binary, the same way the Windows spec must be run on
# Windows.
#
# Build (from the repo root, in an activated venv with
# requirements.txt + requirements-build.txt installed):
#     python -m PyInstaller HappyBoyAtelierLinux.spec --noconfirm
#
# Produces a single-file executable at dist/Happy Boy Atelier (no
# extension -- PyInstaller doesn't add one on Linux).
#
# Carries over both fixes HappyBoyAtelier.spec bakes in (found the hard
# way during Windows packaging, and there's no reason to expect Linux is
# exempt from either):
#   - collect_all("PySide6"): without it, the built binary raises
#     ModuleNotFoundError: No module named 'PySide6' at runtime even
#     though the build itself reports success.
#   - datas=[("resources", "resources")]: without it, setWindowIcon()
#     silently no-ops at runtime, because app_icon_path() can't find
#     resources/icons/app.png inside the bundle.
#
# What's deliberately different from the Windows spec:
#   - No `icon=` argument. PyInstaller's icon embedding is a Windows
#     (.ico, baked into the .exe's PE resources) / macOS (.icns, baked
#     into the .app bundle) concept -- Linux has no equivalent inside a
#     single ELF binary. A Linux desktop icon is a separate, later
#     concern: a .desktop launcher file plus an icon installed into the
#     system's icon theme directory, not something this spec produces.
#   - No target_arch / codesign_identity / entitlements_file -- those
#     are macOS-only EXE() options with nothing to configure here.

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
)
