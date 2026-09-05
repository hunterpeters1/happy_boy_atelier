"""User preferences (Options > Settings…) — pure workflow/UI defaults,
never project state: nothing here is saved in any `.atelier` file, none
of it is undoable, and none of it retroactively changes an already-open
project (each preference here only seeds a *default* the next time it's
relevant — a new painting, a new export, a freshly launched window).

Persisted as plain `QSettings` keys, the same lightweight pattern
`main.py`'s theme persistence and `MainWindow._recent_files()` already
use — these are single scalars (int/str/bool), not the nested
dict-of-bools shape `project_templates.py`/`export_dialog.py`'s presets
need to JSON-encode to round-trip reliably across `QSettings` backends,
so that extra step isn't needed here.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from . import constants as C

_AUTOSAVE_INTERVAL_KEY = "settings/autosaveIntervalMs"
_DEFAULT_UNIT_KEY = "settings/defaultUnit"
_DEFAULT_EXPORT_DPI_KEY = "settings/defaultExportDpi"
_SHOW_RULERS_KEY = "settings/showRulersByDefault"
_FUTURISTIC_ACCENTS_KEY = "settings/futuristicAccentsEnabled"
_CHECK_FOR_UPDATES_KEY = "settings/checkForUpdatesEnabled"
_LAST_DISMISSED_UPDATE_KEY = "settings/lastDismissedUpdateVersion"

# Sentinel or a real interval — 0 specifically means "autosave disabled",
# distinct from any real millisecond interval, and never itself handed to
# QTimer.setInterval() (an interval of 0 would fire continuously) — see
# MainWindow.__init__'s autosave timer setup, which checks for this first.
AUTOSAVE_OFF_MS = 0
AUTOSAVE_CHOICES_MS = [60_000, 3 * 60_000, 5 * 60_000, 10 * 60_000, AUTOSAVE_OFF_MS]
AUTOSAVE_CHOICE_LABELS = {
    60_000: "Every minute",
    3 * 60_000: "Every 3 minutes",
    5 * 60_000: "Every 5 minutes",
    10 * 60_000: "Every 10 minutes",
    AUTOSAVE_OFF_MS: "Off",
}

DEFAULT_EXPORT_DPI = 300


def _as_bool(value, default: bool) -> bool:
    # QSettings hands bools back as native bool on some backends (Windows
    # registry) and as the strings "true"/"false" on others (INI files) —
    # confirmed inconsistent by this project's own experience with export
    # presets/project templates, which is why those go through JSON
    # instead. A single scalar bool is simple enough to just normalize
    # here rather than pull in that whole extra encoding step.
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return default


def autosave_interval_ms() -> int:
    raw = QSettings().value(_AUTOSAVE_INTERVAL_KEY, C.AUTOSAVE_INTERVAL_MS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return C.AUTOSAVE_INTERVAL_MS
    return value if value in AUTOSAVE_CHOICES_MS else C.AUTOSAVE_INTERVAL_MS


def set_autosave_interval_ms(value_ms: int) -> None:
    QSettings().setValue(_AUTOSAVE_INTERVAL_KEY, int(value_ms))


def default_unit() -> str:
    raw = QSettings().value(_DEFAULT_UNIT_KEY, "in")
    return raw if raw in C.UNITS else "in"


def set_default_unit(unit: str) -> None:
    QSettings().setValue(_DEFAULT_UNIT_KEY, unit)


def default_export_dpi() -> int:
    raw = QSettings().value(_DEFAULT_EXPORT_DPI_KEY, DEFAULT_EXPORT_DPI)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_EXPORT_DPI
    return value if 72 <= value <= 1200 else DEFAULT_EXPORT_DPI


def set_default_export_dpi(value: int) -> None:
    QSettings().setValue(_DEFAULT_EXPORT_DPI_KEY, int(value))


def show_rulers_by_default() -> bool:
    return _as_bool(QSettings().value(_SHOW_RULERS_KEY, True), True)


def set_show_rulers_by_default(value: bool) -> None:
    QSettings().setValue(_SHOW_RULERS_KEY, bool(value))


def futuristic_accents_enabled() -> bool:
    """Whether the small set of motion/glow accents (active-tool glow
    pulse, handle-frame fade-in, Focus Mode's dock fade-in, softened
    movement-line curves) are on. Purely cosmetic and never gates any
    actual capability — every one of these has a plain, instant
    fallback when this is off, so turning it off never removes a
    feature, only the animation/softening around it. Defaults on: it's
    meant to be this app's new default feel, not an opt-in experiment.
    """
    return _as_bool(QSettings().value(_FUTURISTIC_ACCENTS_KEY, True), True)


def set_futuristic_accents_enabled(value: bool) -> None:
    QSettings().setValue(_FUTURISTIC_ACCENTS_KEY, bool(value))


def check_for_updates_enabled() -> bool:
    """On by default -- Hunter's explicit call: a quiet, dismissible
    startup check is the right default posture for this app, with the
    toggle here for anyone who'd rather it never phone out at all.
    """
    return _as_bool(QSettings().value(_CHECK_FOR_UPDATES_KEY, True), True)


def set_check_for_updates_enabled(value: bool) -> None:
    QSettings().setValue(_CHECK_FOR_UPDATES_KEY, bool(value))


def last_dismissed_update_version() -> str:
    """The version string (e.g. "1.2.0") of the last update notice the
    artist explicitly dismissed -- so a dismissed notice doesn't keep
    reappearing on every future launch, but a *newer* release than the
    one dismissed still gets its own fresh notice.
    """
    return str(QSettings().value(_LAST_DISMISSED_UPDATE_KEY, ""))


def set_last_dismissed_update_version(version: str) -> None:
    QSettings().setValue(_LAST_DISMISSED_UPDATE_KEY, version)
