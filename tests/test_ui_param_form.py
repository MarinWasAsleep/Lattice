"""Tests for the parameter form widget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QSlider,
    QSpinBox,
)

from lattice_core.types import ParamSpec  # noqa: E402
from lattice_dither.ui.param_form import ParamForm  # noqa: E402

SPECS: tuple[ParamSpec, ...] = (
    ParamSpec(
        id="strength", label="Strength", kind="float", default=0.5, min=0.0, max=1.0, step=0.01
    ),
    ParamSpec(id="radius", label="Radius", kind="int", default=3, min=1, max=9, step=1),
    ParamSpec(id="serpentine", label="Serpentine", kind="bool", default=True),
    ParamSpec(
        id="matrix",
        label="Matrix",
        kind="choice",
        default="bayer",
        choices=("bayer", "blue_noise"),
    ),
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def form(qapp: QApplication) -> ParamForm:
    """Return a form built from the shared spec tuple."""
    widget = ParamForm(SPECS)
    yield widget
    widget.close()


def _counter(form: ParamForm) -> list[int]:
    """Connect a counting slot to changed and return its storage list."""
    calls: list[int] = []
    form.changed.connect(lambda: calls.append(1))
    return calls


def test_builds_one_editor_per_kind(form: ParamForm) -> None:
    """Every kind gets its documented editor widget."""
    strength = form.widget("strength")
    assert strength.findChild(QSlider) is not None
    assert strength.findChild(QDoubleSpinBox) is not None
    assert isinstance(form.widget("radius"), QSpinBox)
    assert isinstance(form.widget("serpentine"), QCheckBox)
    assert isinstance(form.widget("matrix"), QComboBox)
    assert form.specs() == SPECS


def test_values_returns_defaults(form: ParamForm) -> None:
    """values() reports the spec defaults before any edit."""
    assert form.values() == {
        "strength": 0.5,
        "radius": 3,
        "serpentine": True,
        "matrix": "bayer",
    }


def test_set_values_does_not_emit_changed(form: ParamForm) -> None:
    """Loading values programmatically stays silent."""
    calls = _counter(form)
    form.set_values({"strength": 0.25, "radius": 7, "serpentine": False, "matrix": "blue_noise"})
    assert calls == []
    assert form.values() == {
        "strength": 0.25,
        "radius": 7,
        "serpentine": False,
        "matrix": "blue_noise",
    }


def test_user_edits_emit_changed(form: ParamForm) -> None:
    """Each editor emits changed exactly once per user edit."""
    calls = _counter(form)
    form.widget("radius").setValue(5)
    assert len(calls) == 1
    form.widget("serpentine").setChecked(False)
    assert len(calls) == 2
    form.widget("matrix").setCurrentIndex(1)
    assert len(calls) == 3
    form.widget("strength").findChild(QDoubleSpinBox).setValue(0.75)
    assert len(calls) == 4
    assert form.values()["strength"] == pytest.approx(0.75)


def test_set_values_clamps_out_of_range(form: ParamForm) -> None:
    """Out-of-range values are clamped to the spec bounds."""
    form.set_values({"strength": 5.0, "radius": 99})
    assert form.values()["strength"] == pytest.approx(1.0)
    assert form.values()["radius"] == 9
    form.set_values({"strength": -3.0, "radius": -4})
    assert form.values()["strength"] == pytest.approx(0.0)
    assert form.values()["radius"] == 1


def test_slider_and_spinbox_stay_in_sync(form: ParamForm) -> None:
    """The float slider and its spinbox mirror each other."""
    strength = form.widget("strength")
    slider = strength.findChild(QSlider)
    spin = strength.findChild(QDoubleSpinBox)
    slider.setValue(slider.maximum())
    assert spin.value() == pytest.approx(1.0)
    spin.setValue(0.25)
    assert slider.value() == 25
    assert form.values()["strength"] == pytest.approx(0.25)


def test_unknown_keys_and_choices_are_ignored(form: ParamForm) -> None:
    """Unknown keys and unknown choice values leave the form untouched."""
    form.set_values({"nope": 1, "matrix": "not_a_matrix"})
    assert form.values()["matrix"] == "bayer"
    assert "nope" not in form.values()


def test_empty_specs(qapp: QApplication) -> None:
    """A form without specs has no values and never emits."""
    empty = ParamForm(())
    calls = _counter(empty)
    empty.set_values({"strength": 0.1})
    assert empty.values() == {}
    assert calls == []
    empty.close()


def test_set_specs_rebuilds_without_changed(form: ParamForm) -> None:
    """Rebuilding the form for new specs keeps the signal silent."""
    calls = _counter(form)
    other = (ParamSpec(id="amount", label="Amount", kind="int", default=2, min=0, max=4),)
    form.set_specs(other)
    assert calls == []
    assert form.values() == {"amount": 2}
    assert form.widget("amount") is not None


def test_float_without_step_uses_defaults(qapp: QApplication) -> None:
    """A float spec without step still builds a usable slider and spinbox."""
    specs = (ParamSpec(id="gain", label="Gain", kind="float", default=0.3, min=0.0, max=2.0),)
    widget = ParamForm(specs)
    gain = widget.widget("gain")
    slider = gain.findChild(QSlider)
    spin = gain.findChild(QDoubleSpinBox)
    assert slider.maximum() == 1000
    assert spin.decimals() == 2
    spin.setValue(1.5)
    assert widget.values()["gain"] == pytest.approx(1.5)
    widget.close()
