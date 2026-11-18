"""Renderer panel: every registered renderer, with the option form of the selected one.

The selector's list is ``lattice_core.cell.list_renderers()``, never a table, so a renderer
added to the core becomes selectable here without touching this module (L12 accept). The
option form is built from ``lattice_glyph.options``: one widget per declared option, at its
default; a renderer this table does not name shows an honest "no option" line.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lattice_core.cell import list_renderers
from lattice_glyph import options as option_tools


class RendererPanel(QWidget):
    """Renderer selector plus the option widgets of the selected renderer."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the selector and the option host, then show the first renderer."""
        super().__init__(parent)
        self.setObjectName("renderer_panel")
        self._loading = False
        self._renderer = ""
        self._widgets: dict[str, QWidget] = {}
        self.selector = QComboBox(self)
        self.selector.setObjectName("renderer_selector")
        for name in list_renderers():
            self.selector.addItem(name, name)
        self.host = QWidget(self)
        self.host.setObjectName("renderer_options")
        self.form = QFormLayout(self.host)
        self.form.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel("Renderer", self))
        layout.addWidget(self.selector)
        layout.addWidget(self.host)
        layout.addStretch(1)
        self.selector.currentIndexChanged.connect(self._on_renderer_chosen)
        self._show(str(self.selector.currentData() or ""))

    def renderers(self) -> list[str]:
        """Return every renderer name the selector offers, in display order."""
        return [str(self.selector.itemData(index)) for index in range(self.selector.count())]

    def current(self) -> str:
        """Return the renderer currently selected."""
        return str(self.selector.currentData())

    def option_widget(self, key: str) -> QWidget | None:
        """Return the widget of one option key, or None for a renderer that lacks it."""
        return self._widgets.get(key)

    def style_options(self) -> dict:
        """Return the style options the widgets hold, defaults already dropped."""
        values: dict = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QLineEdit):
                values[key] = widget.text()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[key] = widget.value()
        return option_tools.clean(self._renderer, values)

    def set_renderer(self, name: str, style: dict | None = None) -> None:
        """Select name without emitting, then load style into its widgets."""
        index = self.selector.findData(name)
        if index < 0:
            raise ValueError(f"unknown renderer {name!r}")
        self._loading = True
        try:
            self.selector.setCurrentIndex(index)
            self._show(name)
            self._load(style or {})
        finally:
            self._loading = False

    def _on_renderer_chosen(self) -> None:
        """Show the option widgets of the chosen renderer and announce the change."""
        if self._loading:
            return
        self._show(str(self.selector.currentData()))
        self.changed.emit()

    def _show(self, name: str) -> None:
        """Rebuild the option form for name, every widget at its default."""
        self._renderer = name
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._widgets = {}
        for spec in option_tools.specs_for(name):
            widget = _widget_for(spec, self.host)
            self._widgets[spec.key] = widget
            label = QLabel(spec.label, self.host)
            if spec.hint:
                label.setToolTip(spec.hint)
            self.form.addRow(label, widget)
        for widget in self._widgets.values():
            _connect(widget, self._emit_changed)
        if not self._widgets:
            self.form.addRow(QLabel("This renderer has no option.", self.host))

    def _emit_changed(self) -> None:
        """Announce one user edit of an option, unless the panel is being loaded."""
        if not self._loading:
            self.changed.emit()

    def _load(self, style: dict) -> None:
        """Write style into the widgets, leaving every absent key at its default."""
        for spec in option_tools.specs_for(self._renderer):
            widget = self._widgets.get(spec.key)
            if widget is None:
                continue
            value = style.get(spec.key, spec.default)
            if isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value) if value is not None else int(spec.minimum or 0))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value) if value is not None else float(spec.minimum or 0.0))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))


def _widget_for(spec: option_tools.OptionSpec, parent: QWidget) -> QWidget:
    """Return the input widget a spec kind calls for, at its default value."""
    default = spec.default
    if spec.kind == "bool":
        box = QCheckBox(parent)
        box.setChecked(bool(default))
        return box
    if spec.kind == "choice":
        combo = QComboBox(parent)
        for choice in spec.choices:
            combo.addItem(choice, choice)
        combo.setCurrentIndex(max(0, combo.findData(default)))
        return combo
    if spec.kind == "float":
        spin = QDoubleSpinBox(parent)
        spin.setDecimals(2)
        spin.setSingleStep(float(spec.step))
        spin.setRange(-1e6, 1e6)
        if spec.minimum is not None and spec.maximum is not None:
            spin.setRange(float(spec.minimum), float(spec.maximum))
        spin.setValue(float(default))  # type: ignore[arg-type]
        return spin
    if spec.kind == "int":
        spin = QSpinBox(parent)
        spin.setRange(0, 1_000_000)
        if spec.minimum is not None and spec.maximum is not None:
            spin.setRange(int(spec.minimum), int(spec.maximum))
        spin.setValue(int(default))  # type: ignore[arg-type]
        return spin
    edit = QLineEdit(parent)
    edit.setText("" if default is None else str(default))
    return edit


def _connect(widget: QWidget, slot: Callable[[], None]) -> None:
    """Connect the change signal the widget actually has to slot."""
    if isinstance(widget, QLineEdit):
        widget.textChanged.connect(lambda _text: slot())
    elif isinstance(widget, QCheckBox):
        widget.toggled.connect(lambda _state: slot())
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(lambda _index: slot())
    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.valueChanged.connect(lambda _value: slot())
