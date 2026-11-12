"""Parameter form widget built from a tuple of ParamSpec objects."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QWidget,
)

from lattice_dither.core.types import ParamSpec
from lattice_dither.i18n import tr

SLIDER_STEPS = 1000
MAX_SLIDER_STEPS = 10000
DEFAULT_FLOAT_RANGE = (0.0, 1.0)
DEFAULT_INT_RANGE = (0, 100)

Value = float | int | bool | str


def _bounds(spec: ParamSpec, fallback: tuple[float, float]) -> tuple[float, float]:
    """Return the (min, max) range of a spec, falling back when it is incomplete."""
    low = fallback[0] if spec.min is None else float(spec.min)
    high = fallback[1] if spec.max is None else float(spec.max)
    if high <= low:
        high = low + 1.0
    return low, high


def _decimals(spec: ParamSpec) -> int:
    """Return the number of decimals implied by the step of a float spec."""
    step = spec.step
    if not step:
        return 2
    text = f"{float(step):.6f}".rstrip("0")
    if "." not in text:
        return 0
    return max(0, min(4, len(text.split(".")[1])))


def _slider_steps(spec: ParamSpec, low: float, high: float) -> int:
    """Return the number of slider divisions for a float spec."""
    step = spec.step
    if step and float(step) > 0.0:
        steps = int(round((high - low) / float(step)))
        return max(1, min(MAX_SLIDER_STEPS, steps))
    return SLIDER_STEPS


def _to_slider(value: float, low: float, high: float, steps: int) -> int:
    """Map a float value onto a slider position."""
    if high <= low or steps <= 0:
        return 0
    position = int(round((float(value) - low) / (high - low) * steps))
    return max(0, min(steps, position))


class ParamForm(QWidget):
    """Form with one editor per ParamSpec that emits changed on user edits."""

    changed = Signal()

    def __init__(self, specs: tuple[ParamSpec, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._specs: tuple[ParamSpec, ...] = ()
        self._editors: dict[str, QWidget] = {}
        self._loading = False
        self._form = QFormLayout(self)
        self._form.setContentsMargins(4, 4, 4, 4)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.set_specs(specs)

    def specs(self) -> tuple[ParamSpec, ...]:
        """Return the parameter specs currently shown by the form."""
        return self._specs

    def widget(self, spec_id: str) -> QWidget:
        """Return the editor widget of one parameter."""
        return self._editors[spec_id]

    def set_specs(self, specs: tuple[ParamSpec, ...]) -> None:
        """Rebuild the form for a new parameter tuple without emitting changed."""
        self._loading = True
        try:
            while self._form.rowCount():
                self._form.removeRow(0)
            self._editors.clear()
            self._specs = tuple(specs)
            for spec in self._specs:
                editor = self._build_editor(spec)
                self._editors[spec.id] = editor
                self._form.addRow(tr(spec.label), editor)
        finally:
            self._loading = False

    def values(self) -> dict[str, Value]:
        """Return the current value of every parameter, keyed by spec id."""
        result: dict[str, Value] = {}
        for spec in self._specs:
            editor = self._editors[spec.id]
            if spec.kind == "float":
                spin = editor.findChild(QDoubleSpinBox)
                result[spec.id] = float(spin.value()) if spin is not None else 0.0
            elif spec.kind == "int":
                result[spec.id] = int(editor.value())
            elif spec.kind == "bool":
                result[spec.id] = bool(editor.isChecked())
            else:
                result[spec.id] = str(editor.currentText())
        return result

    def set_values(self, d: dict) -> None:
        """Apply values without emitting changed; out-of-range values are clamped."""
        self._loading = True
        try:
            for spec in self._specs:
                if spec.id in d:
                    self._apply(spec, d[spec.id])
        finally:
            self._loading = False

    def _apply(self, spec: ParamSpec, value: object) -> None:
        """Write one value into its editor, clamping and ignoring unknown choices."""
        editor = self._editors[spec.id]
        if spec.kind == "float":
            low, high = _bounds(spec, DEFAULT_FLOAT_RANGE)
            spin = editor.findChild(QDoubleSpinBox)
            slider = editor.findChild(QSlider)
            spin.setValue(min(max(float(value), low), high))
            if slider is not None:
                slider.setValue(_to_slider(spin.value(), low, high, slider.maximum()))
        elif spec.kind == "int":
            low, high = _bounds(spec, DEFAULT_INT_RANGE)
            editor.setValue(int(min(max(int(value), int(round(low))), int(round(high)))))
        elif spec.kind == "bool":
            editor.setChecked(bool(value))
        else:
            index = editor.findText(str(value))
            if index >= 0:
                editor.setCurrentIndex(index)

    def _build_editor(self, spec: ParamSpec) -> QWidget:
        """Create the editor widget matching the kind of a spec."""
        if spec.kind == "float":
            return self._build_float(spec)
        if spec.kind == "int":
            return self._build_int(spec)
        if spec.kind == "bool":
            return self._build_bool(spec)
        if spec.kind == "choice":
            return self._build_choice(spec)
        raise ValueError(f"unknown parameter kind {spec.kind!r}")

    def _build_float(self, spec: ParamSpec) -> QWidget:
        """Build a slider plus spinbox row for a float parameter."""
        low, high = _bounds(spec, DEFAULT_FLOAT_RANGE)
        steps = _slider_steps(spec, low, high)
        box = QWidget(self)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal, box)
        slider.setRange(0, steps)
        spin = QDoubleSpinBox(box)
        spin.setRange(low, high)
        spin.setDecimals(_decimals(spec))
        spin.setSingleStep(float(spec.step) if spec.step else (high - low) / 100.0)
        spin.setKeyboardTracking(False)
        value = min(max(float(spec.default), low), high)
        slider.setValue(_to_slider(value, low, high, steps))
        spin.setValue(value)
        slider.valueChanged.connect(
            lambda position: self._on_slider(position, spin, low, high, steps)
        )
        spin.valueChanged.connect(lambda v: self._on_spin(v, slider, low, high, steps))
        row.addWidget(slider, 1)
        row.addWidget(spin, 0)
        return box

    def _build_int(self, spec: ParamSpec) -> QWidget:
        """Build a spinbox for an int parameter."""
        low, high = _bounds(spec, DEFAULT_INT_RANGE)
        spin = QSpinBox(self)
        spin.setRange(int(round(low)), int(round(high)))
        spin.setSingleStep(int(spec.step) if spec.step else 1)
        spin.setKeyboardTracking(False)
        spin.setValue(int(min(max(int(spec.default), int(round(low))), int(round(high)))))
        spin.valueChanged.connect(self._emit_changed)
        return spin

    def _build_bool(self, spec: ParamSpec) -> QWidget:
        """Build a checkbox for a bool parameter."""
        check = QCheckBox(self)
        check.setChecked(bool(spec.default))
        check.toggled.connect(self._emit_changed)
        return check

    def _build_choice(self, spec: ParamSpec) -> QWidget:
        """Build a combobox for a choice parameter."""
        combo = QComboBox(self)
        combo.addItems([str(choice) for choice in spec.choices])
        index = combo.findText(str(spec.default))
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(self._emit_changed)
        return combo

    def _emit_changed(self, *_args: object) -> None:
        """Emit changed unless the form is being loaded programmatically."""
        if not self._loading:
            self.changed.emit()

    def _on_slider(
        self, position: int, spin: QDoubleSpinBox, low: float, high: float, steps: int
    ) -> None:
        """Mirror a slider move into the spinbox and emit changed once."""
        if self._loading:
            return
        value = low + (high - low) * position / steps
        self._loading = True
        try:
            spin.setValue(value)
        finally:
            self._loading = False
        self.changed.emit()

    def _on_spin(
        self, value: float, slider: QSlider, low: float, high: float, steps: int
    ) -> None:
        """Mirror a spinbox edit into the slider and emit changed once."""
        if self._loading:
            return
        self._loading = True
        try:
            slider.setValue(_to_slider(value, low, high, steps))
        finally:
            self._loading = False
        self.changed.emit()
