"""Algorithm panel: algorithm choice, its parameters, pixel size and tone controls."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lattice_dither.core.pipeline import MAX_PIXEL_SIZE, MIN_PIXEL_SIZE, PipelineSpec
from lattice_dither.core.registry import get_algorithm, list_algorithms
from lattice_dither.ui.param_form import ParamForm

LOGGER = logging.getLogger(__name__)

SLIDER_STEPS = 1000
BRIGHTNESS_RANGE = (-1.0, 1.0)
CONTRAST_RANGE = (-1.0, 1.0)
GAMMA_RANGE = (0.1, 5.0)
TONE_DECIMALS = 2
DEFAULT_BRIGHTNESS = 0.0
DEFAULT_CONTRAST = 0.0
DEFAULT_GAMMA = 1.0
DEFAULT_PIXEL_SIZE = 1
FLOAT_TOLERANCE = 1e-9


def _differs(value: object, default: object) -> bool:
    """Return True when a parameter value differs from its spec default."""
    if default is None:
        return True
    if isinstance(value, bool) or isinstance(default, bool):
        return bool(value) != bool(default)
    if isinstance(value, (int, float)) and isinstance(default, (int, float)):
        return abs(float(value) - float(default)) > FLOAT_TOLERANCE
    return value != default


class _SliderRow(QWidget):
    """Slider plus spinbox pair for one float field, emitting changed on user edits."""

    changed = Signal()

    def __init__(
        self,
        low: float,
        high: float,
        value: float,
        decimals: int = TONE_DECIMALS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._low = float(low)
        self._high = float(high)
        self._loading = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, SLIDER_STEPS)
        self.spin = QDoubleSpinBox(self)
        self.spin.setRange(self._low, self._high)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep((self._high - self._low) / 100.0)
        self.spin.setKeyboardTracking(False)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin, 0)
        self.set_value(value)
        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

    def value(self) -> float:
        """Return the current value of the row."""
        return float(self.spin.value())

    def set_value(self, value: float) -> None:
        """Set the value without emitting changed, clamping it to the row range."""
        self._loading = True
        try:
            clamped = min(max(float(value), self._low), self._high)
            self.spin.setValue(clamped)
            self.slider.setValue(self._to_position(clamped))
        finally:
            self._loading = False

    def _to_position(self, value: float) -> int:
        """Map a value onto a slider position."""
        span = self._high - self._low
        if span <= 0.0:
            return 0
        position = int(round((float(value) - self._low) / span * SLIDER_STEPS))
        return max(0, min(SLIDER_STEPS, position))

    def _on_slider(self, position: int) -> None:
        """Mirror a slider move into the spinbox and emit changed once."""
        if self._loading:
            return
        self._loading = True
        try:
            self.spin.setValue(self._low + (self._high - self._low) * position / SLIDER_STEPS)
        finally:
            self._loading = False
        self.changed.emit()

    def _on_spin(self, value: float) -> None:
        """Mirror a spinbox edit into the slider and emit changed once."""
        if self._loading:
            return
        self._loading = True
        try:
            self.slider.setValue(self._to_position(float(value)))
        finally:
            self._loading = False
        self.changed.emit()


class AlgorithmPanel(QWidget):
    """Panel editing the algorithm, its parameters, the pixel size and the tone controls."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("algorithm_panel")
        self._loading = False
        self._param_keys: set[str] = set()
        self.algorithm_combo = QComboBox(self)
        self.algorithm_combo.setObjectName("algorithm_combo")
        self.param_form = ParamForm((), self)
        self.pixel_size_spin = QSpinBox(self)
        self.pixel_size_spin.setObjectName("pixel_size_spin")
        self.pixel_size_spin.setRange(MIN_PIXEL_SIZE, MAX_PIXEL_SIZE)
        self.pixel_size_spin.setValue(DEFAULT_PIXEL_SIZE)
        self.pixel_size_spin.setKeyboardTracking(False)
        self.brightness = _SliderRow(*BRIGHTNESS_RANGE, DEFAULT_BRIGHTNESS, parent=self)
        self.contrast = _SliderRow(*CONTRAST_RANGE, DEFAULT_CONTRAST, parent=self)
        self.gamma = _SliderRow(*GAMMA_RANGE, DEFAULT_GAMMA, parent=self)
        self.reset_button = QPushButton("Reset", self)
        self.reset_button.setObjectName("reset_button")
        self._build_layout()
        self._populate_algorithms()
        self._connect()

    def load_from(self, spec: PipelineSpec) -> None:
        """Show the algorithm fields of spec without emitting changed."""
        self._loading = True
        try:
            algorithm_id = self._select_algorithm(spec.algorithm_id)
            if algorithm_id is not None:
                self._rebuild_params(algorithm_id, dict(spec.algorithm_params))
            self._param_keys = set(spec.algorithm_params)
            self.pixel_size_spin.setValue(int(spec.pixel_size))
            self.brightness.set_value(spec.brightness)
            self.contrast.set_value(spec.contrast)
            self.gamma.set_value(spec.gamma)
        finally:
            self._loading = False

    def apply_to(self, spec: PipelineSpec) -> None:
        """Write the panel fields into spec, leaving every other field untouched."""
        algorithm_id = self._current_algorithm_id()
        if algorithm_id is not None:
            spec.algorithm_id = algorithm_id
            spec.algorithm_params = self._changed_params(algorithm_id)
        spec.pixel_size = int(self.pixel_size_spin.value())
        spec.brightness = self.brightness.value()
        spec.contrast = self.contrast.value()
        spec.gamma = self.gamma.value()

    def _build_layout(self) -> None:
        """Create the layout: algorithm choice, parameter group, tone rows and reset."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        top = QFormLayout()
        top.addRow("Algorithm", self.algorithm_combo)
        top.addRow("Pixel size", self.pixel_size_spin)
        outer.addLayout(top)
        self.param_group = QGroupBox("Parameters", self)
        group_layout = QVBoxLayout(self.param_group)
        group_layout.addWidget(self.param_form)
        outer.addWidget(self.param_group)
        tone = QFormLayout()
        tone.addRow("Brightness", self.brightness)
        tone.addRow("Contrast", self.contrast)
        tone.addRow("Gamma", self.gamma)
        outer.addLayout(tone)
        outer.addWidget(self.reset_button)
        outer.addStretch(1)

    def _populate_algorithms(self) -> None:
        """Fill the combo with every registered algorithm, separated by family."""
        self._loading = True
        try:
            self.algorithm_combo.clear()
            family: str | None = None
            for info in list_algorithms():
                if family is not None and info.family != family:
                    self.algorithm_combo.insertSeparator(self.algorithm_combo.count())
                family = info.family
                self.algorithm_combo.addItem(info.name, info.id)
        finally:
            self._loading = False

    def _connect(self) -> None:
        """Connect every editor to the changed signal and the reset button."""
        self.algorithm_combo.currentIndexChanged.connect(self._on_algorithm_changed)
        self.param_form.changed.connect(self._emit_changed)
        self.pixel_size_spin.valueChanged.connect(self._emit_changed)
        self.brightness.changed.connect(self._emit_changed)
        self.contrast.changed.connect(self._emit_changed)
        self.gamma.changed.connect(self._emit_changed)
        self.reset_button.clicked.connect(self._on_reset)

    def _current_algorithm_id(self) -> str | None:
        """Return the id of the selected algorithm, or None when the combo is empty."""
        data = self.algorithm_combo.currentData()
        return str(data) if data else None

    def _select_algorithm(self, algorithm_id: str) -> str | None:
        """Select algorithm_id in the combo and return the id actually selected."""
        index = self.algorithm_combo.findData(algorithm_id)
        if index < 0:
            LOGGER.warning("unknown algorithm id %r, keeping the first entry", algorithm_id)
            if self.algorithm_combo.count() == 0:
                return None
            index = 0
        self.algorithm_combo.setCurrentIndex(index)
        return self._current_algorithm_id()

    def _rebuild_params(self, algorithm_id: str, params: dict) -> None:
        """Rebuild the parameter form for algorithm_id and apply params over the defaults."""
        try:
            info = get_algorithm(algorithm_id)
        except KeyError:
            LOGGER.warning("unknown algorithm id %r, clearing the parameters", algorithm_id)
            self.param_form.set_specs(())
            return
        self.param_form.set_specs(info.params)
        self.param_form.set_values(params)

    def _changed_params(self, algorithm_id: str) -> dict:
        """Return the parameter values that were loaded or differ from the defaults."""
        values = self.param_form.values()
        try:
            specs = get_algorithm(algorithm_id).params
        except KeyError:
            return {}
        defaults = {spec.id: spec.default for spec in specs}
        return {
            key: value
            for key, value in values.items()
            if key in self._param_keys or _differs(value, defaults.get(key))
        }

    def _on_algorithm_changed(self, _index: int) -> None:
        """Rebuild the parameter form with defaults and report the user edit."""
        if self._loading:
            return
        algorithm_id = self._current_algorithm_id()
        if algorithm_id is None:
            return
        self._param_keys = set()
        self._rebuild_params(algorithm_id, {})
        self._emit_changed()

    def _on_reset(self, *_args: object) -> None:
        """Restore the parameter, pixel size and tone defaults of the current algorithm."""
        if self._loading:
            return
        self._loading = True
        try:
            algorithm_id = self._current_algorithm_id()
            self._param_keys = set()
            if algorithm_id is not None:
                self._rebuild_params(algorithm_id, {})
            self.pixel_size_spin.setValue(DEFAULT_PIXEL_SIZE)
            self.brightness.set_value(DEFAULT_BRIGHTNESS)
            self.contrast.set_value(DEFAULT_CONTRAST)
            self.gamma.set_value(DEFAULT_GAMMA)
        finally:
            self._loading = False
        self.changed.emit()

    def _emit_changed(self, *_args: object) -> None:
        """Emit changed unless the panel is loading a spec."""
        if not self._loading:
            self.changed.emit()
