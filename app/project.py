"""Pure data model — no Qt imports.

`CanvasSpec` and `ProjectMeta` are the only long-lived Python objects; every
other piece of project state (references, composition, perspective,
lighting, guides) lives on the QGraphicsScene and is (de)serialized directly
to/from plain dicts by the layer modules. Keeping this file Qt-free makes
the on-disk schema easy to reason about and to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from . import constants as C


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CanvasSpec:
    name: str = "Untitled Painting"
    width: float = 16.0
    height: float = 20.0
    unit: str = "in"

    @property
    def width_in(self) -> float:
        return C.to_inches(self.width, self.unit)

    @property
    def height_in(self) -> float:
        return C.to_inches(self.height, self.unit)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CanvasSpec":
        return CanvasSpec(
            name=d.get("name", "Untitled Painting"),
            width=float(d.get("width", 16.0)),
            height=float(d.get("height", 20.0)),
            unit=d.get("unit", "in"),
        )


@dataclass
class ProjectMeta:
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)
    locked: bool = False
    # Eyedropper-pinned colors, as "#RRGGBB" hex strings. Per-project (not
    # QSettings()) and deliberately excluded from Undo/Redo, same as lock
    # state above -- a mixing reference, not artwork content.
    color_swatches: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.modified_at = _now_iso()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ProjectMeta":
        return ProjectMeta(
            created_at=d.get("created_at", _now_iso()),
            modified_at=d.get("modified_at", _now_iso()),
            locked=bool(d.get("locked", False)),
            color_swatches=list(d.get("color_swatches", [])),
        )


def empty_manifest(canvas: CanvasSpec, meta: ProjectMeta) -> dict:
    """Skeleton manifest for a brand-new project (no layer content yet)."""
    return {
        "format_version": C.FORMAT_VERSION,
        "canvas": canvas.to_dict(),
        "meta": meta.to_dict(),
        "references": [],
        "composition": {"focal_points": [], "movement_lines": [], "notes": []},
        "perspective": {
            "mode": C.PerspectiveMode.ONE_POINT.value,
            "horizon_y": canvas.height_in / 2,
            "vanishing_points": [],
            "grid_spacing": 1.0,
            "line_width": 2.0,
            "opacity": 0.8,
            "visible": True,
            "locked": False,
        },
        "lighting": {"sources": [], "arrows": [], "notes": []},
        "guides": {"rule_of_thirds": False, "golden_ratio": False},
    }
