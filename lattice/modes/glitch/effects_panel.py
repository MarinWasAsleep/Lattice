"""Effect stack panel of the Glitch shell: add, reorder, enable, tune and mask (§12-§18).

The list shows the stack in render order; the form below edits the selected slot with
the registry's own parameter specs, and a combo assigns one of the document's masks.
Every edit mutates the shared ``EffectStack`` and emits ``changed`` once, so the window
rebuilds the spec and requests a preview; nothing renders inside the panel.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import lattice.effects  # noqa: F401  (registers every effect the combo offers)
from lattice.effects.ntsc import LABEL_NOTES, PRESET_NAMES, params_for_mode
from lattice.effects.ntsc import preset as ntsc_preset
from lattice.modes.glitch.params import ParamForm
from lattice.modes.glitch.stack import EffectStack
from lattice.registry import get_effect, list_effects
from lattice.types import ParamSpec

NO_MASK = "No mask"
NTSC_ID = "ntsc"


class EffectsPanel(QWidget):
    """Stack list, add/remove/move buttons, mask assignment and the parameter form."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the stack controls over an empty stack."""
        super().__init__(parent)
        self.setObjectName("effects_panel")
        self._stack = EffectStack()
        self._mask_ids: list[str] = []
        self._loading = False
        self.add_box = QComboBox(self)
        self.add_box.setObjectName("effect_add_box")
        for info in list_effects():
            self.add_box.addItem(info.name, info.id)
        self.add_button = QPushButton("Add", self)
        self.add_button.setObjectName("effect_add")
        add_row = QHBoxLayout()
        add_row.addWidget(self.add_box, 1)
        add_row.addWidget(self.add_button)
        self.list = QListWidget(self)
        self.list.setObjectName("effect_list")
        self.up_button = QPushButton("Up", self)
        self.up_button.setObjectName("effect_up")
        self.down_button = QPushButton("Down", self)
        self.down_button.setObjectName("effect_down")
        self.remove_button = QPushButton("Remove", self)
        self.remove_button.setObjectName("effect_remove")
        move_row = QHBoxLayout()
        for button in (self.up_button, self.down_button, self.remove_button):
            move_row.addWidget(button)
        self.mask_box = QComboBox(self)
        self.mask_box.setObjectName("effect_mask_box")
        mask_row = QHBoxLayout()
        mask_row.addWidget(QLabel("Mask", self))
        mask_row.addWidget(self.mask_box, 1)
        self.form = ParamForm(parent=self)
        self.form.setObjectName("effect_params")
        self.ntsc_row = self._build_ntsc_row()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(add_row)
        layout.addWidget(self.list, 1)
        layout.addLayout(move_row)
        layout.addLayout(mask_row)
        layout.addWidget(self.ntsc_row)
        layout.addWidget(self.form)
        self.add_button.clicked.connect(lambda: self.add_effect())
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.remove_button.clicked.connect(self.remove_selected)
        self.list.currentRowChanged.connect(self._on_selection)
        self.list.itemChanged.connect(self._on_item_changed)
        self.mask_box.currentIndexChanged.connect(self._on_mask)
        self.form.changed.connect(self._on_params)
        self.ntsc_advanced.toggled.connect(self._on_ntsc_mode)
        self.ntsc_preset_box.currentIndexChanged.connect(self._on_ntsc_preset)
        self.set_mask_ids([])

    def _build_ntsc_row(self) -> QWidget:
        """Build the §16 usability row: six named presets and the simple/advanced toggle."""
        row = QWidget(self)
        row.setObjectName("ntsc_row")
        self.ntsc_preset_box = QComboBox(row)
        self.ntsc_preset_box.setObjectName("ntsc_preset")
        for name in PRESET_NAMES:
            self.ntsc_preset_box.addItem(name, name)
        self.ntsc_preset_box.setToolTip("Apply one of the six named NTSC / VHS presets.")
        self.ntsc_advanced = QCheckBox("Advanced", row)
        self.ntsc_advanced.setObjectName("ntsc_advanced")
        self.ntsc_advanced.setToolTip("Show all 14 signal parameters instead of the four sliders.")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ntsc_preset_box, 1)
        layout.addWidget(self.ntsc_advanced)
        row.hide()
        return row

    def stack(self) -> EffectStack:
        """Return the stack this panel edits (the window's own object)."""
        return self._stack

    def effect_choices(self) -> list[str]:
        """Return the effect ids the add combo offers, in display order."""
        return [str(self.add_box.itemData(i)) for i in range(self.add_box.count())]

    def load(self, stack: EffectStack, mask_ids: list[str]) -> None:
        """Adopt a stack and the available mask ids, rebuilding the list silently."""
        self._stack = stack
        self.set_mask_ids(mask_ids)
        self.refresh()

    def set_mask_ids(self, mask_ids: list[str]) -> None:
        """Offer exactly these mask ids, keeping the selection; drop orphan assignments."""
        self._mask_ids = list(mask_ids)
        for position, mask_id in enumerate(self._stack.mask_ids()):
            if mask_id is not None and mask_id not in self._mask_ids:
                self._stack.set_mask(position, None)
        current = self.mask_box.currentData()
        self._loading = True
        try:
            self.mask_box.clear()
            self.mask_box.addItem(NO_MASK, None)
            for mask_id in self._mask_ids:
                self.mask_box.addItem(mask_id, mask_id)
            index = self.mask_box.findData(current)
            self.mask_box.setCurrentIndex(max(0, index))
        finally:
            self._loading = False

    def refresh(self) -> None:
        """Rebuild the list from the stack, keeping the current row when possible."""
        row = self.list.currentRow()
        self._loading = True
        try:
            self.list.clear()
            for position, slot in enumerate(self._stack.slots()):
                info = get_effect(slot.instance.effect_id)
                item = QListWidgetItem(f"{position + 1}. {info.name}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                state = Qt.CheckState.Checked if slot.instance.enabled else Qt.CheckState.Unchecked
                item.setCheckState(state)
                self.list.addItem(item)
            if self.list.count():
                self.list.setCurrentRow(min(max(0, row), self.list.count() - 1))
        finally:
            self._loading = False
        self._on_selection(self.list.currentRow())

    def selected_index(self) -> int | None:
        """Return the selected stack position, or None when the list is empty."""
        row = self.list.currentRow()
        return None if row < 0 else row

    def add_effect(self, effect_id: str | None = None, params: dict | None = None) -> int:
        """Append the chosen effect (or effect_id) to the stack and select it."""
        chosen = effect_id if effect_id is not None else str(self.add_box.currentData())
        position = self._stack.add(chosen, params)
        self.refresh()
        self.list.setCurrentRow(position)
        self.changed.emit()
        return position

    def remove_selected(self) -> None:
        """Remove the selected slot, if any, and emit changed."""
        row = self.selected_index()
        if row is None:
            return
        self._stack.remove(row)
        self.refresh()
        self.changed.emit()

    def move_selected(self, delta: int) -> None:
        """Move the selected slot by delta positions, clamped to the stack bounds."""
        row = self.selected_index()
        if row is None:
            return
        target = max(0, min(len(self._stack) - 1, row + delta))
        if target == row:
            return
        self._stack.move(row, target)
        self.refresh()
        self.list.setCurrentRow(target)
        self.changed.emit()

    def _on_selection(self, row: int) -> None:
        """Load the parameter form and mask combo of the selected slot."""
        self._loading = True
        try:
            if row < 0 or row >= len(self._stack):
                self.form.set_specs(())
                self.ntsc_row.hide()
                self.mask_box.setCurrentIndex(0)
                return
            slot = self._stack.slots()[row]
            effect_id = slot.instance.effect_id
            self.ntsc_row.setVisible(effect_id == NTSC_ID)
            specs = self._ntsc_specs() if effect_id == NTSC_ID else get_effect(effect_id).params
            self.form.set_specs(specs)
            self.form.set_values(slot.instance.params)
            if effect_id == NTSC_ID:
                self._ntsc_tooltips(specs)
            index = self.mask_box.findData(slot.mask_id)
            self.mask_box.setCurrentIndex(max(0, index))
        finally:
            self._loading = False

    def _ntsc_specs(self) -> tuple[ParamSpec, ...]:
        """Return the §16 parameters of the current mode: four sliders, or all fourteen."""
        return params_for_mode("advanced" if self.ntsc_advanced.isChecked() else "simple")

    def _ntsc_tooltips(self, specs: tuple[ParamSpec, ...]) -> None:
        """Give every ntsc editor the honest reading of its catalogue label."""
        for spec in specs:
            note = LABEL_NOTES.get(spec.id, "")
            if note:
                self.form.widget(spec.id).setToolTip(note)

    def _on_ntsc_mode(self, _checked: bool) -> None:
        """Rebuild the ntsc form for the toggled mode, keeping every current value."""
        if self._loading:
            return
        row = self.selected_index()
        if row is None or self._stack.effect_ids()[row] != NTSC_ID:
            return
        values = dict(self._stack.params_of(row))
        values.update(self.form.values())
        specs = self._ntsc_specs()
        self.form.set_specs(specs)
        self.form.set_values(values)
        self._ntsc_tooltips(specs)

    def _on_ntsc_preset(self, index: int) -> None:
        """Apply the chosen named preset over the slot's parameters and emit changed."""
        if self._loading or index < 0:
            return
        row = self.selected_index()
        if row is None or self._stack.effect_ids()[row] != NTSC_ID:
            return
        values = dict(self._stack.params_of(row))
        values.update(ntsc_preset(str(self.ntsc_preset_box.itemText(index))))
        self._stack.set_params(row, values)
        self.form.set_values(values)
        self.changed.emit()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Mirror a list check state into the slot's enabled flag."""
        if self._loading:
            return
        row = self.list.row(item)
        self._stack.set_enabled(row, item.checkState() == Qt.CheckState.Checked)
        self.changed.emit()

    def _on_params(self) -> None:
        """Merge the form's values into the selected slot (hidden params kept) and emit."""
        row = self.selected_index()
        if row is None or self._loading:
            return
        params = dict(self._stack.params_of(row))
        params.update(self.form.values())
        self._stack.set_params(row, params)
        self.changed.emit()

    def _on_mask(self, _index: int) -> None:
        """Assign the combo's mask id to the selected slot and emit changed."""
        if self._loading:
            return
        row = self.selected_index()
        if row is None:
            return
        data = self.mask_box.currentData()
        self._stack.set_mask(row, None if data is None else str(data))
        self.changed.emit()


__all__ = ["NO_MASK", "NTSC_ID", "EffectsPanel"]
