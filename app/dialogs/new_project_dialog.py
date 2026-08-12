"""New Painting dialog: one size picker, always editable.

Previously "Custom" was a fourth peer category next to Portrait/Landscape/
Square, switched to via a dropdown that hid the width/height/unit fields
entirely unless "Custom" was chosen — meaning even a one-inch tweak to a
preset required switching into an entirely different mode instead of just
editing a number. There was also a latent bug: the dialog's own default
(the first Portrait preset, 8x10in) didn't match CanvasSpec's own
dataclass default (16x20in) — nothing kept the two in sync since they
were two independently-authored defaults.

Now there is exactly one size — width/height/unit fields, always visible
and always editable — seeded directly from a fresh CanvasSpec() so the
dialog's default and the data model's default are structurally the same
value, not two numbers someone has to remember to keep matching. An
orientation filter (Portrait/Landscape/Square) narrows which preset list
is shown; clicking a preset just fills in the fields, it doesn't switch
modes or hide anything.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QRadioButton,
    QVBoxLayout,
)

from .. import constants as C
from .. import project_templates
from ..project import CanvasSpec

_CATEGORIES = {
    "Portrait": C.PORTRAIT_FORMATS,
    "Landscape": C.LANDSCAPE_FORMATS,
    "Square": C.SQUARE_FORMATS,
}


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Painting")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit("Untitled Painting")
        form.addRow("Title", self.name_edit)
        layout.addLayout(form)

        orient_row = QHBoxLayout()
        orient_row.addWidget(QLabel("Presets"))
        self._orient_group = QButtonGroup(self)
        for category in _CATEGORIES:
            radio = QRadioButton(category)
            if category == "Portrait":
                radio.setChecked(True)
            radio.toggled.connect(lambda on, c=category: on and self._show_presets(c))
            self._orient_group.addButton(radio)
            orient_row.addWidget(radio)
        orient_row.addStretch(1)
        layout.addLayout(orient_row)

        self.preset_list = QListWidget()
        self.preset_list.setMaximumHeight(120)
        self.preset_list.itemClicked.connect(self._apply_preset)
        layout.addWidget(self.preset_list)

        # -- templates: a named {width, height, unit, guides} starting
        # point saved from an existing project (MainWindow.
        # save_as_template()) -- deliberately never reference images or
        # composition/lighting content, just workspace setup. Section
        # only shown at all once at least one template exists.
        self._selected_template_guides: dict | None = None
        self._templates = project_templates.load_templates()
        self.template_section_label = QLabel("My Templates")
        self.template_section_label.setProperty("role", "section")
        layout.addWidget(self.template_section_label)
        self.template_list = QListWidget()
        self.template_list.setMaximumHeight(90)
        self.template_list.itemClicked.connect(self._apply_template)
        for name in sorted(self._templates):
            self.template_list.addItem(QListWidgetItem(name))
        layout.addWidget(self.template_list)
        has_templates = bool(self._templates)
        self.template_section_label.setVisible(has_templates)
        self.template_list.setVisible(has_templates)

        size_form = QFormLayout()
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 500)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.5, 500)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(C.UNITS)
        size_form.addRow("Width", self.width_spin)
        size_form.addRow("Height", self.height_spin)
        size_form.addRow("Unit", self.unit_combo)
        layout.addLayout(size_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Seeded from the data model's own default — not a second,
        # independently-chosen number that can drift out of sync with it.
        default = CanvasSpec()
        self.width_spin.setValue(default.width)
        self.height_spin.setValue(default.height)
        self.unit_combo.setCurrentText(default.unit)

        self._show_presets("Portrait")

    def _show_presets(self, category: str) -> None:
        self.preset_list.clear()
        for label, w, h in _CATEGORIES[category]:
            entry = QListWidgetItem(f"{label} in")
            entry.setData(Qt.UserRole, (w, h))
            self.preset_list.addItem(entry)

    def _apply_preset(self, entry: QListWidgetItem) -> None:
        w, h = entry.data(Qt.UserRole)
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)
        self.unit_combo.setCurrentText("in")
        # A plain size preset is a different starting point than any
        # previously-clicked template -- don't silently carry the old
        # template's guide toggles onto an unrelated format choice.
        self._selected_template_guides = None

    def _apply_template(self, entry: QListWidgetItem) -> None:
        template = self._templates.get(entry.text())
        if template is None:
            return
        self.width_spin.setValue(float(template.get("width", CanvasSpec().width)))
        self.height_spin.setValue(float(template.get("height", CanvasSpec().height)))
        self.unit_combo.setCurrentText(template.get("unit", CanvasSpec().unit))
        self._selected_template_guides = template.get("guides")

    def selected_template_guides(self) -> dict | None:
        """The `guides` dict of whichever template was last clicked, or
        None if the dialog is closed with a plain size preset (or no
        preset at all) instead — MainWindow._new_project() applies this
        to the freshly-created scene's GuidesLayerGroup.load_from_dict()
        after construction.
        """
        return self._selected_template_guides

    def canvas_spec(self) -> CanvasSpec:
        name = self.name_edit.text().strip() or "Untitled Painting"
        return CanvasSpec(
            name=name, width=self.width_spin.value(),
            height=self.height_spin.value(), unit=self.unit_combo.currentText(),
        )
