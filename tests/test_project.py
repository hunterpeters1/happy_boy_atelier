"""CanvasSpec / ProjectMeta / empty_manifest round-trip tests.

Pure Python, no Qt dependency at all (app/project.py and app/constants.py
are deliberately Qt-free) — these can run in any environment, even one
without PySide6 installed, and don't need the qapp fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import constants as C
from app.project import CanvasSpec, ProjectMeta, empty_manifest


# -- CanvasSpec ---------------------------------------------------------------

def test_canvas_spec_round_trip():
    spec = CanvasSpec(name="Portrait Study", width=18.0, height=24.0, unit="in")
    restored = CanvasSpec.from_dict(spec.to_dict())
    assert restored == spec


def test_canvas_spec_from_dict_defaults_missing_fields():
    restored = CanvasSpec.from_dict({})
    assert restored == CanvasSpec()


def test_canvas_spec_from_dict_ignores_unknown_keys():
    # Forward-compat: a manifest from a newer format_version shouldn't
    # crash an older build trying to open it.
    restored = CanvasSpec.from_dict({"name": "X", "width": 10, "height": 10, "unit": "in", "future_field": 123})
    assert restored == CanvasSpec(name="X", width=10, height=10, unit="in")


def test_canvas_spec_unit_conversion_to_inches():
    spec = CanvasSpec(width=10.0, height=20.0, unit="cm")
    assert abs(spec.width_in - (10.0 / 2.54)) < 1e-9
    assert abs(spec.height_in - (20.0 / 2.54)) < 1e-9

    spec_in = CanvasSpec(width=10.0, height=20.0, unit="in")
    assert spec_in.width_in == 10.0
    assert spec_in.height_in == 20.0


# -- ProjectMeta ----------------------------------------------------------------

def test_project_meta_round_trip():
    meta = ProjectMeta(
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-02T00:00:00+00:00",
        locked=True,
    )
    restored = ProjectMeta.from_dict(meta.to_dict())
    assert restored == meta


def test_project_meta_from_dict_defaults_missing_fields():
    restored = ProjectMeta.from_dict({})
    assert restored.locked is False
    assert restored.created_at  # a fresh ISO timestamp was generated
    assert restored.modified_at


def test_project_meta_touch_updates_modified_at_only():
    meta = ProjectMeta(created_at="2026-01-01T00:00:00+00:00", modified_at="2026-01-01T00:00:00+00:00")
    meta.touch()
    assert meta.modified_at != "2026-01-01T00:00:00+00:00"
    assert meta.created_at == "2026-01-01T00:00:00+00:00"  # never changes on touch()


# -- empty_manifest -------------------------------------------------------------

def test_empty_manifest_shape():
    spec = CanvasSpec()
    meta = ProjectMeta()
    manifest = empty_manifest(spec, meta)

    assert manifest["format_version"] == C.FORMAT_VERSION
    assert manifest["canvas"] == spec.to_dict()
    assert manifest["meta"] == meta.to_dict()
    assert manifest["references"] == []
    assert manifest["composition"] == {"focal_points": [], "movement_lines": [], "notes": []}
    assert manifest["lighting"] == {"sources": [], "arrows": [], "notes": []}
    assert manifest["guides"] == {"rule_of_thirds": False, "golden_ratio": False}


def test_empty_manifest_perspective_defaults_visible():
    # Regression guard: the Layers panel's "Visible" checkbox and the
    # actual perspective layer disagreed on first launch before this was
    # fixed (see CHANGELOG.md v1.0.0) — a fresh manifest must default to
    # visible so a newly-created project can't reintroduce that mismatch.
    manifest = empty_manifest(CanvasSpec(), ProjectMeta())
    assert manifest["perspective"]["visible"] is True
    assert manifest["perspective"]["mode"] == C.PerspectiveMode.ONE_POINT.value
