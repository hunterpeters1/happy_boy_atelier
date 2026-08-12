"""Project templates: a named {width, height, unit, guides} starting
point for New Painting — explicitly *not* reference images or
composition/lighting content. Auto-populating those from a saved
template would cross into "software infers the composition," which is
out of scope by design (see CLAUDE.md/TEAM_ROLES.md); a template only
ever pre-fills the blank canvas format and which guide overlays start
turned on, both pure workspace setup, never artwork content.

Saved from an existing project's current state
(`MainWindow.save_as_template()`); applied when starting a New Painting
(`NewProjectDialog`'s Templates list). Serialized as a JSON string under
one `QSettings` key — same reasoning as
`app/dialogs/export_dialog.py`'s presets: a plain string always
round-trips exactly, unlike relying on `QSettings`' own dict/bool
marshalling across backends.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings

_SETTINGS_KEY = "projectTemplates"


def load_templates() -> dict[str, dict]:
    raw = QSettings().value(_SETTINGS_KEY, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def save_templates(templates: dict[str, dict]) -> None:
    QSettings().setValue(_SETTINGS_KEY, json.dumps(templates))


def save_template(name: str, *, width: float, height: float, unit: str, guides: dict) -> None:
    templates = load_templates()
    templates[name] = {"width": width, "height": height, "unit": unit, "guides": guides}
    save_templates(templates)


def delete_template(name: str) -> None:
    templates = load_templates()
    templates.pop(name, None)
    save_templates(templates)
