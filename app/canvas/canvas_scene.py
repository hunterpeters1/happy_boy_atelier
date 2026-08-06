"""The drafting table itself: owns the canvas rect and the five fixed-order
layer groups, routes placement-tool clicks, and serializes/deserializes the
full layer stack.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QTransform, QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from .. import constants as C
from ..constants import LayerKind
from ..project import CanvasSpec
from ..layers.reference_layer import ReferenceLayerGroup
from ..layers.composition_layer import CompositionLayerGroup, FocalPointItem, MovementLineItem, NoteItem
from ..layers.perspective_layer import PerspectiveLayerGroup
from ..layers.lighting_layer import LightingLayerGroup, LightSourceItem, DirectionArrowItem
from ..layers.guide_overlay import GuidesLayerGroup
from .undo_commands import AddItemCommand, DeleteItemCommand

# tools that place a single item on one click
_SINGLE_CLICK_TOOLS = {"focal_primary", "focal_secondary", "note_comp", "light_source", "note_light"}
# tools that need a start-click then an end-click
_TWO_CLICK_TOOLS = {"movement_line", "light_arrow", "shadow_arrow"}


class CanvasScene(QGraphicsScene):
    tool_finished = Signal()
    # Emitted directly by an item's own click handler (see canvas/selection.py)
    # so the Properties panel can be driven without depending on Qt's
    # internal selectedItems()/isSelected() bookkeeping alone.
    item_activated = Signal(object)

    def __init__(self, canvas_spec: CanvasSpec):
        super().__init__()
        # Content-mutation undo/redo (Phase 0.2). Scoped to artwork setup
        # changes only — lock toggles and layer/guide visibility are
        # deliberately excluded, see canvas/undo_commands.py.
        self.undo_stack = QUndoStack(self)
        self.canvas_spec = canvas_spec
        w = canvas_spec.width_in * C.SCENE_PX_PER_INCH
        h = canvas_spec.height_in * C.SCENE_PX_PER_INCH
        self._canvas_rect = QRectF(0, 0, w, h)
        self.setSceneRect(self._canvas_rect.adjusted(-4000, -4000, 4000, 4000))

        self.reference_layer = ReferenceLayerGroup()
        self.composition_layer = CompositionLayerGroup()
        self.perspective_layer = PerspectiveLayerGroup(self._canvas_rect)
        self.lighting_layer = LightingLayerGroup()
        self.guides_layer = GuidesLayerGroup(self._canvas_rect)

        for z, group in enumerate([
            self.reference_layer, self.composition_layer,
            self.perspective_layer, self.lighting_layer, self.guides_layer,
        ]):
            group.setZValue(z)
            self.addItem(group)

        self._active_tool: str | None = None
        self._pending_point = None
        self._global_locked = False
        self._layer_locked_flags = {kind: False for kind in C.LAYER_ORDER}

        # Drives the resize/rotate handles + highlight border on reference
        # images (see ReferenceImageItem.set_ui_active in reference_layer.py).
        # Deliberately independent of Qt's own isSelected(): confirmed at
        # runtime that setSelected() does not reliably stick for items
        # inside this app's QGraphicsItemGroup + setHandlesChildEvents(False)
        # layers, so this is driven directly off item_activated instead,
        # which every selectable item already emits from its own click
        # handler (see canvas/selection.py) and which the Properties panel
        # already relies on for the same reason.
        self._active_ui_item = None
        self.item_activated.connect(self._on_item_activated)

    def _on_item_activated(self, item) -> None:
        if self._active_ui_item is item:
            return
        self._deactivate_ui_item()
        self._active_ui_item = item
        if hasattr(item, "set_ui_active"):
            item.set_ui_active(True)

    def _deactivate_ui_item(self) -> None:
        prev = self._active_ui_item
        self._active_ui_item = None
        if prev is not None and hasattr(prev, "set_ui_active"):
            try:
                prev.set_ui_active(False)
            except RuntimeError:
                pass  # underlying C++ item was already deleted

    # -- geometry -----------------------------------------------------
    def canvas_rect(self) -> QRectF:
        return self._canvas_rect

    def resize_canvas(self, canvas_spec: CanvasSpec) -> None:
        self.canvas_spec = canvas_spec
        w = canvas_spec.width_in * C.SCENE_PX_PER_INCH
        h = canvas_spec.height_in * C.SCENE_PX_PER_INCH
        self._canvas_rect = QRectF(0, 0, w, h)
        self.setSceneRect(self._canvas_rect.adjusted(-4000, -4000, 4000, 4000))
        self.perspective_layer.horizon.set_canvas_width(w)
        self.guides_layer.thirds.set_rect(self._canvas_rect)
        self.guides_layer.golden.set_rect(self._canvas_rect)
        self.update()

    def drawBackground(self, painter, rect) -> None:
        painter.fillRect(rect, QColor(C.COLOR_BG_DARKEST))
        shadow = self._canvas_rect.adjusted(6, 8, 6, 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 90)))
        painter.drawRect(shadow)
        painter.setBrush(QBrush(QColor(C.COLOR_CANVAS)))
        painter.setPen(QPen(QColor(C.COLOR_CANVAS_EDGE), 2))
        painter.drawRect(self._canvas_rect)

    # -- tools -----------------------------------------------------------
    def set_active_tool(self, tool: str | None) -> None:
        self._active_tool = tool
        self._pending_point = None

    def active_tool(self) -> str | None:
        return self._active_tool

    def set_global_locked(self, locked: bool) -> None:
        self._global_locked = locked
        for kind in C.LAYER_ORDER:
            self._apply_layer_lock(kind, True if locked else self._layer_locked_flags.get(kind, False))
        if locked:
            self.set_active_tool(None)
            self.clearSelection()
            self._deactivate_ui_item()

    def is_globally_locked(self) -> bool:
        return self._global_locked

    def set_layer_locked(self, kind: LayerKind, locked: bool) -> None:
        self._layer_locked_flags[kind] = locked
        if not self._global_locked:
            self._apply_layer_lock(kind, locked)

    def layer_locked(self, kind: LayerKind) -> bool:
        return self._layer_locked_flags.get(kind, False)

    def _group_for(self, kind: LayerKind):
        return {
            LayerKind.REFERENCE: self.reference_layer,
            LayerKind.COMPOSITION: self.composition_layer,
            LayerKind.PERSPECTIVE: self.perspective_layer,
            LayerKind.LIGHTING: self.lighting_layer,
            LayerKind.GUIDES: None,
        }[kind]

    def _apply_layer_lock(self, kind: LayerKind, locked: bool) -> None:
        group = self._group_for(kind)
        if group is not None and hasattr(group, "set_layer_locked"):
            group.set_layer_locked(locked)

    def mousePressEvent(self, event) -> None:
        if self._global_locked or not self._active_tool or event.button() != Qt.LeftButton:
            if not self._global_locked and not self._active_tool and event.button() == Qt.LeftButton:
                self._maybe_deactivate_on_empty_click(event.scenePos())
            super().mousePressEvent(event)
            return
        if self._handle_tool_click(event.scenePos()):
            event.accept()
            return
        super().mousePressEvent(event)

    def _maybe_deactivate_on_empty_click(self, pos) -> None:
        """A click that doesn't land on any selectable item (empty canvas,
        or the start of a rubber-band drag) should drop the current
        resize/rotate handle target, same as clicking elsewhere always
        has. See _on_item_activated for why this isn't just isSelected().
        """
        if self._active_ui_item is None:
            return
        views = self.views()
        transform = views[0].transform() if views else QTransform()
        node = self.itemAt(pos, transform)
        while node is not None and not hasattr(node, "set_ui_active"):
            node = node.parentItem()
        if node is None:
            self._deactivate_ui_item()

    def keyPressEvent(self, event) -> None:
        # Escape always backs out exactly one level: cancel an armed
        # placement tool, then exit crop mode (previously Escape did
        # nothing here — the only way out of crop was the Properties
        # panel's Apply/Cancel buttons), then clear the selection.
        if event.key() == Qt.Key_Escape:
            if self._active_tool:
                self.set_active_tool(None)
                self.tool_finished.emit()
                event.accept()
                return
            item = self._active_ui_item
            if item is not None and hasattr(item, "is_cropping") and item.is_cropping():
                item.cancel_crop()
                event.accept()
                return
            if self.selectedItems():
                self.clearSelection()
                self._deactivate_ui_item()
                event.accept()
                return
        super().keyPressEvent(event)

    def _add(self, group, item, label: str) -> None:
        self.undo_stack.push(AddItemCommand(group, item, label))

    def _handle_tool_click(self, pos) -> bool:
        tool = self._active_tool
        if tool in _SINGLE_CLICK_TOOLS:
            if tool == "focal_primary":
                item = FocalPointItem("primary")
                item.setPos(pos)
                self._add(self.composition_layer, item, "Add focal point")
            elif tool == "focal_secondary":
                item = FocalPointItem("secondary")
                item.setPos(pos)
                self._add(self.composition_layer, item, "Add focal point")
            elif tool == "note_comp":
                item = NoteItem(text="Note")
                item.setPos(pos)
                self._add(self.composition_layer, item, "Add note")
            elif tool == "light_source":
                item = LightSourceItem()
                item.setPos(pos)
                self._add(self.lighting_layer, item, "Add light source")
            elif tool == "note_light":
                item = NoteItem(text="Lighting note", color=C.COLOR_LIGHT)
                item.setPos(pos)
                self._add(self.lighting_layer, item, "Add note")
            self.set_active_tool(None)
            self.tool_finished.emit()
            return True

        if tool in _TWO_CLICK_TOOLS:
            if self._pending_point is None:
                self._pending_point = pos
                return True
            start = self._pending_point
            if tool == "movement_line":
                item = MovementLineItem([start, pos])
                self._add(self.composition_layer, item, "Add movement line")
            elif tool == "light_arrow":
                item = DirectionArrowItem("light", start, pos)
                self._add(self.lighting_layer, item, "Add light direction")
            elif tool == "shadow_arrow":
                item = DirectionArrowItem("shadow", start, pos)
                self._add(self.lighting_layer, item, "Add shadow direction")
            self.set_active_tool(None)
            self.tool_finished.emit()
            return True

        return False

    # -- selection / deletion ----------------------------------------------
    def delete_item(self, item) -> None:
        if item in self.reference_layer.items():
            self.undo_stack.push(DeleteItemCommand(self.reference_layer, item, "Delete reference image"))
            return
        if item in self.composition_layer.all_items():
            self.undo_stack.push(DeleteItemCommand(self.composition_layer, item, "Delete item"))
            return
        if item in self.lighting_layer.all_items():
            self.undo_stack.push(DeleteItemCommand(self.lighting_layer, item, "Delete item"))
            return
        # Vanishing points / horizon are structural to the perspective mode
        # and are not individually deletable.

    def delete_selected_items(self) -> None:
        items = list(self.selectedItems())
        if not items:
            return
        # Group a multi-select delete into one undo step rather than one
        # per item, so Ctrl+Z undoes "delete these 3 things" in one press.
        multi = len(items) > 1
        if multi:
            self.undo_stack.beginMacro("Delete Selected")
        try:
            for item in items:
                self.delete_item(item)
        finally:
            if multi:
                self.undo_stack.endMacro()

    # -- serialization -----------------------------------------------------
    def to_manifest_layers(self):
        ref_records, images = self.reference_layer.to_dict()
        layers = {
            "references": ref_records,
            "composition": self.composition_layer.to_dict(),
            "perspective": self.perspective_layer.to_dict(),
            "lighting": self.lighting_layer.to_dict(),
            "guides": self.guides_layer.to_dict(),
        }
        return layers, images

    def load_manifest_layers(self, manifest: dict, images: dict) -> None:
        self.reference_layer.load_from_dict(manifest.get("references", []), images)
        self.composition_layer.load_from_dict(manifest.get("composition", {}))
        self.perspective_layer.load_from_dict(manifest.get("perspective", {}))
        self.lighting_layer.load_from_dict(manifest.get("lighting", {}))
        self.guides_layer.load_from_dict(manifest.get("guides", {}))
