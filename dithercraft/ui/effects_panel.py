"""Effects panel: ordered pre- and post-dither effect stacks with parameter editing."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import dithercraft.effects  # noqa: F401  (importing the package registers every effect)
from dithercraft.core.pipeline import EffectInstance, PipelineSpec
from dithercraft.core.registry import get_effect, list_effects, resolve_params
from dithercraft.ui.param_form import ParamForm

LOGGER = logging.getLogger(__name__)

EFFECT_ID_ROLE = int(Qt.ItemDataRole.UserRole)
PARAMS_ROLE = EFFECT_ID_ROLE + 1
PRE_TITLE = "Before dither"
POST_TITLE = "After dither"
PARAMS_TITLE = "Parameters"
NO_SELECTION_TEXT = "No effect selected"


class EffectList(QListWidget):
    """Effect list that reorders its own items by internal drag and drop."""

    order_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setUniformItemSizes(True)

    def move_item(self, from_row: int, to_row: int) -> None:
        """Move the item at from_row so that it ends up at index to_row."""
        if not 0 <= from_row < self.count():
            return
        target = max(0, min(self.count() - 1, to_row))
        if target == from_row:
            return
        item = self.takeItem(from_row)
        self.insertItem(target, item)
        self.setCurrentItem(item)
        self.order_changed.emit()

    def dropEvent(self, event: QDropEvent) -> None:
        """Reorder the dragged row in place so the item keeps its data."""
        if event.source() is not self:
            event.ignore()
            return
        rows = [self.row(item) for item in self.selectedItems()]
        if not rows:
            event.ignore()
            return
        insertion = self._insertion_row(event)
        source_row = rows[0]
        target = insertion - 1 if insertion > source_row else insertion
        self.move_item(source_row, target)
        event.accept()

    def _insertion_row(self, event: QDropEvent) -> int:
        """Return the insertion index implied by the drop position."""
        position = event.position().toPoint()
        index = self.indexAt(position)
        if not index.isValid():
            return self.count()
        row = index.row()
        if position.y() > self.visualRect(index).center().y():
            row += 1
        return row


class EffectsPanel(QWidget):
    """Panel editing the ordered pre-dither and post-dither effect stacks."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._active = "pre"
        self.pre_list = EffectList(self)
        self.pre_list.setObjectName("pre_list")
        self.post_list = EffectList(self)
        self.post_list.setObjectName("post_list")
        self.add_button = QPushButton("Add", self)
        self.remove_button = QPushButton("Remove", self)
        self.duplicate_button = QPushButton("Duplicate", self)
        self.add_menu = QMenu(self.add_button)
        self.add_button.setMenu(self.add_menu)
        self.param_label = QLabel(NO_SELECTION_TEXT, self)
        self.param_form = ParamForm((), self)
        self._build_layout()
        self._connect()
        self._rebuild_add_menu()
        self._show_params(None)
        self._update_buttons()

    def load_from(self, spec: PipelineSpec) -> None:
        """Fill both lists from spec without emitting changed."""
        self._loading = True
        try:
            self._fill(self.pre_list, spec.pre_effects)
            self._fill(self.post_list, spec.post_effects)
            self._active = "pre"
        finally:
            self._loading = False
        self._show_params(None)
        self._update_buttons()

    def apply_to(self, spec: PipelineSpec) -> None:
        """Write both effect stacks, in list order, into spec."""
        spec.pre_effects = self._instances(self.pre_list)
        spec.post_effects = self._instances(self.post_list)

    def _build_layout(self) -> None:
        """Assemble the two lists, the button row and the parameter form."""
        layout = QVBoxLayout(self)
        layout.addWidget(self._group(PRE_TITLE, self.pre_list), 1)
        layout.addWidget(self._group(POST_TITLE, self.post_list), 1)
        buttons = QHBoxLayout()
        for button in (self.add_button, self.remove_button, self.duplicate_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        box = QGroupBox(PARAMS_TITLE, self)
        inner = QVBoxLayout(box)
        inner.addWidget(self.param_label)
        inner.addWidget(self.param_form)
        layout.addWidget(box, 1)

    def _group(self, title: str, widget: QWidget) -> QGroupBox:
        """Wrap one list in a titled group box."""
        box = QGroupBox(title, self)
        inner = QVBoxLayout(box)
        inner.addWidget(widget)
        return box

    def _connect(self) -> None:
        """Wire list, button and form signals to the panel slots."""
        for widget in (self.pre_list, self.post_list):
            widget.currentItemChanged.connect(
                lambda current, _previous, source=widget: self._on_current_changed(source, current)
            )
            widget.itemChanged.connect(self._on_item_changed)
            widget.order_changed.connect(self._emit_changed)
        self.add_menu.aboutToShow.connect(self._rebuild_add_menu)
        self.remove_button.clicked.connect(self._remove_current)
        self.duplicate_button.clicked.connect(self._duplicate_current)
        self.param_form.changed.connect(self._on_param_changed)

    def _rebuild_add_menu(self) -> None:
        """Fill the Add menu with one action per registered effect."""
        self.add_menu.clear()
        for info in list_effects():
            action = self.add_menu.addAction(info.name)
            action.setData(info.id)
            action.triggered.connect(lambda _checked=False, eid=info.id: self._add_effect(eid))
        self.add_button.setEnabled(bool(self.add_menu.actions()))

    def _add_effect(self, effect_id: str) -> None:
        """Append a new instance of effect_id to the active list and select it."""
        try:
            info = get_effect(effect_id)
        except KeyError:
            LOGGER.warning("unknown effect id: %s", effect_id)
            return
        instance = EffectInstance(effect_id, resolve_params(info.params, {}), True)
        widget = self._target_list()
        item = self._make_item(instance)
        self._loading = True
        try:
            widget.addItem(item)
            widget.setCurrentItem(item)
        finally:
            self._loading = False
        self._on_current_changed(widget, item)
        self.changed.emit()

    def _remove_current(self) -> None:
        """Remove the selected effect from its list."""
        widget, item = self._selection()
        if item is None:
            return
        row = widget.row(item)
        self._loading = True
        try:
            widget.takeItem(row)
            if widget.count():
                widget.setCurrentRow(min(row, widget.count() - 1))
        finally:
            self._loading = False
        self._show_params(widget.currentItem())
        self._update_buttons()
        self.changed.emit()

    def _duplicate_current(self) -> None:
        """Insert a copy of the selected effect directly below it."""
        widget, item = self._selection()
        if item is None:
            return
        copy = self._make_item(self._instance(item))
        row = widget.row(item)
        self._loading = True
        try:
            widget.insertItem(row + 1, copy)
            widget.setCurrentItem(copy)
        finally:
            self._loading = False
        self._on_current_changed(widget, copy)
        self.changed.emit()

    def _on_current_changed(self, widget: EffectList, current: QListWidgetItem | None) -> None:
        """Show the parameters of the selected item and remember the active list."""
        if self._loading or current is None:
            return
        self._active = "post" if widget is self.post_list else "pre"
        other = self.pre_list if widget is self.post_list else self.post_list
        if other.currentItem() is not None:
            self._loading = True
            try:
                other.setCurrentItem(None)
                other.clearSelection()
            finally:
                self._loading = False
        self._show_params(current)
        self._update_buttons()

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        """Emit changed when the user toggles the enabled checkbox."""
        self._emit_changed()

    def _on_param_changed(self) -> None:
        """Store the edited parameters in the selected item and emit changed."""
        if self._loading:
            return
        _widget, item = self._selection()
        if item is None:
            return
        self._loading = True
        try:
            item.setData(PARAMS_ROLE, json.dumps(self.param_form.values(), sort_keys=True))
        finally:
            self._loading = False
        self.changed.emit()

    def _emit_changed(self) -> None:
        """Emit changed unless the panel is loading or syncing itself."""
        if not self._loading:
            self.changed.emit()

    def _show_params(self, item: QListWidgetItem | None) -> None:
        """Show the parameters of item in the form, or clear the form."""
        self._loading = True
        try:
            if item is None:
                self.param_form.set_specs(())
                self.param_form.setEnabled(False)
                self.param_label.setText(NO_SELECTION_TEXT)
                return
            instance = self._instance(item)
            info = get_effect(instance.effect_id)
            self.param_form.set_specs(info.params)
            self.param_form.set_values(instance.params)
            self.param_form.setEnabled(True)
            self.param_label.setText(info.name)
        finally:
            self._loading = False

    def _update_buttons(self) -> None:
        """Enable Remove and Duplicate only while an effect is selected."""
        _widget, item = self._selection()
        self.remove_button.setEnabled(item is not None)
        self.duplicate_button.setEnabled(item is not None)

    def _selection(self) -> tuple[EffectList, QListWidgetItem | None]:
        """Return the list holding the selection and its current item."""
        for widget in (self.pre_list, self.post_list):
            item = widget.currentItem()
            if item is not None:
                return widget, item
        return self._target_list(), None

    def _target_list(self) -> EffectList:
        """Return the list that Add appends to."""
        if self.post_list.hasFocus():
            return self.post_list
        if self.pre_list.hasFocus():
            return self.pre_list
        return self.post_list if self._active == "post" else self.pre_list

    def _make_item(self, instance: EffectInstance) -> QListWidgetItem:
        """Build a list item for instance; KeyError if its effect is unknown."""
        info = get_effect(instance.effect_id)
        item = QListWidgetItem(info.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            Qt.CheckState.Checked if instance.enabled else Qt.CheckState.Unchecked
        )
        item.setData(EFFECT_ID_ROLE, instance.effect_id)
        item.setData(PARAMS_ROLE, json.dumps(instance.params, sort_keys=True))
        item.setToolTip(info.name)
        return item

    def _instance(self, item: QListWidgetItem) -> EffectInstance:
        """Return the EffectInstance stored in item."""
        effect_id = str(item.data(EFFECT_ID_ROLE) or "")
        params = json.loads(str(item.data(PARAMS_ROLE) or "{}"))
        enabled = item.checkState() == Qt.CheckState.Checked
        return EffectInstance(effect_id, params, enabled)

    def _instances(self, widget: EffectList) -> list[EffectInstance]:
        """Return the instances of widget in visual order."""
        return [self._instance(widget.item(row)) for row in range(widget.count())]

    def _fill(self, widget: EffectList, instances: list[EffectInstance]) -> None:
        """Replace the contents of widget with instances, skipping unknown ids."""
        widget.clear()
        for instance in instances:
            try:
                item = self._make_item(instance)
            except KeyError:
                LOGGER.warning("skipping unknown effect id: %s", instance.effect_id)
                continue
            widget.addItem(item)
        widget.setCurrentItem(None)
