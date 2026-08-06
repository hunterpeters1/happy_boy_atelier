"""Phase 0.3 crash-recovery snapshot: a single autosave slot kept outside
the user's own project files, entirely separate from Save/Save As.

Since multiple projects per window are explicitly out of scope (see
V2_ROADMAP.md), one recovery slot per installation is sufficient — it does
not need to be keyed by project. The slot lives in the platform app-data
directory (e.g. `%APPDATA%\\HappyBoyAtelier\\HappyBoyAtelier\\autosave\\` on
Windows), resolved via QStandardPaths so it follows whatever
organizationName/applicationName main.py has already set on QApplication.

Lifecycle:
- Written periodically by MainWindow's autosave timer, only when the
  undo stack isn't clean (see CanvasScene.undo_stack.isClean()).
- Removed after a normal Save, and on clean shutdown (MainWindow.closeEvent).
- On the *next* launch, if the file still exists, that means the last
  session ended uncleanly (crash, force-quit, power loss) — MainWindow
  offers to recover it before building the default new-project workspace.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .atelier_io import load_atelier, save_atelier

RECOVERY_FILENAME = "recovery.atelier"


def recovery_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        # Extremely unlikely fallback — QStandardPaths always returns
        # something once QApplication exists — but never crash the app
        # over a missing autosave directory.
        base = str(Path.home() / ".happy_boy_atelier")
    return Path(base) / "autosave"


def recovery_file_path() -> Path:
    return recovery_dir() / RECOVERY_FILENAME


def has_recovery_file() -> bool:
    return recovery_file_path().exists()


def write_recovery_snapshot(manifest: dict, images: dict[str, bytes]) -> None:
    path = recovery_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    save_atelier(path, manifest, images)


def load_recovery_snapshot() -> tuple[dict, dict[str, bytes]]:
    return load_atelier(recovery_file_path())


def delete_recovery_file() -> None:
    path = recovery_file_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Best-effort: a locked/missing recovery file is not worth
        # interrupting shutdown or a fresh save over.
        pass
