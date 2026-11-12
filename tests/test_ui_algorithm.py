"""Tests for the algorithm panel (T11), driven by a monkeypatched registry."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDoubleSpinBox  # noqa: E402

from lattice_dither.core import registry  # noqa: E402
from lattice_dither.core.pipeline import PaletteSpec, PipelineSpec  # noqa: E402
from lattice_dither.core.registry import AlgorithmInfo  # noqa: E402
from lattice_dither.core.types import ParamSpec  # noqa: E402
from lattice_dither.ui.algorithm_panel import AlgorithmPanel  # noqa: E402


def _noop(img: np.ndarray, palette: np.ndarray, params: dict) -> np.ndarray:
    """Fake algorithm: return index 0 for every pixel."""
    return np.zeros(img.shape[:2], dtype=np.int32)


ALPHA = AlgorithmInfo(
    id="fake_alpha",
    name="Alpha",
    family="error_diffusion",
    params=(
        ParamSpec(
            id="strength", label="Strength", kind="float", default=1.0, min=0.0, max=1.0, step=0.01
        ),
        ParamSpec(id="serpentine", label="Serpentine", kind="bool", default=True),
    ),
    fn=_noop,
)

BETA = AlgorithmInfo(
    id="fake_beta",
    name="Beta",
    family="ordered",
    params=(
        ParamSpec(
            id="spread", label="Spread", kind="float", default=1.0, min=0.0, max=2.0, step=0.01
        ),
        ParamSpec(
            id="matrix",
            label="Matrix",
            kind="choice",
            default="bayer",
            choices=("bayer", "noise"),
        ),
        ParamSpec(id="scale", label="Scale", kind="int", default=1, min=1, max=8, step=1),
    ),
    fn=_noop,
)

ALPHA_DEFAULTS = {"strength": 1.0, "serpentine": True}
BETA_DEFAULTS = {"spread": 1.0, "matrix": "bayer", "scale": 1}


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, AlgorithmInfo]:
    """Install exactly two fake algorithms in the registry."""
    algorithms = {info.id: info for info in (ALPHA, BETA)}
    monkeypatch.setattr(registry, "_ALGORITHMS", algorithms)
    return algorithms


@pytest.fixture
def panel(qapp: QApplication, fakes: dict[str, AlgorithmInfo]) -> AlgorithmPanel:
    """Return an algorithm panel built on the fake registry."""
    widget = AlgorithmPanel()
    yield widget
    widget.close()


def _counter(panel: AlgorithmPanel) -> list[int]:
    """Connect a counting slot to changed and return its storage list."""
    calls: list[int] = []
    panel.changed.connect(lambda: calls.append(1))
    return calls


def _spec(**overrides: object) -> PipelineSpec:
    """Build a spec that exercises every field the panel owns."""
    base: dict = {
        "algorithm_id": "fake_beta",
        "algorithm_params": {"spread": 0.5, "matrix": "noise", "scale": 4},
        "pixel_size": 3,
        "brightness": 0.25,
        "contrast": -0.5,
        "gamma": 2.0,
    }
    base.update(overrides)
    return PipelineSpec(**base)


def _select(panel: AlgorithmPanel, algorithm_id: str) -> None:
    """Select an algorithm in the combo as a user would."""
    panel.algorithm_combo.setCurrentIndex(panel.algorithm_combo.findData(algorithm_id))


def test_combo_groups_families_with_separators(panel: AlgorithmPanel) -> None:
    """The combo lists both algorithms with one separator between the families."""
    combo = panel.algorithm_combo
    assert combo.count() == 3
    assert combo.itemText(0) == "Alpha"
    assert combo.itemData(0) == "fake_alpha"
    assert combo.itemData(1) is None
    assert combo.itemText(1) == ""
    assert combo.itemText(2) == "Beta"
    assert combo.itemData(2) == "fake_beta"


def test_same_family_has_no_separator(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two algorithms of one family are listed without a separator."""
    twin = AlgorithmInfo(
        id="fake_gamma", name="Gamma", family="error_diffusion", params=(), fn=_noop
    )
    monkeypatch.setattr(registry, "_ALGORITHMS", {ALPHA.id: ALPHA, twin.id: twin})
    widget = AlgorithmPanel()
    assert widget.algorithm_combo.count() == 2
    assert widget.algorithm_combo.itemData(0) == "fake_alpha"
    assert widget.algorithm_combo.itemData(1) == "fake_gamma"
    widget.close()


def test_load_from_then_apply_to_round_trips(panel: AlgorithmPanel) -> None:
    """load_from followed by apply_to reproduces every field the panel owns."""
    spec = _spec()
    panel.load_from(spec)
    out = PipelineSpec()
    panel.apply_to(out)
    assert out.algorithm_id == "fake_beta"
    assert out.algorithm_params == {"spread": 0.5, "matrix": "noise", "scale": 4}
    assert out.pixel_size == 3
    assert out.brightness == pytest.approx(0.25)
    assert out.contrast == pytest.approx(-0.5)
    assert out.gamma == pytest.approx(2.0)


def test_apply_to_leaves_other_fields_untouched(panel: AlgorithmPanel) -> None:
    """apply_to writes only the algorithm, parameter, pixel size and tone fields."""
    panel.load_from(_spec())
    out = PipelineSpec(seed=11, palette=PaletteSpec(source="custom", colors=["#000000"]))
    panel.apply_to(out)
    assert out.seed == 11
    assert out.version == 1
    assert out.pre_effects == []
    assert out.post_effects == []
    assert out.palette.source == "custom"
    assert out.palette.colors == ["#000000"]


def test_empty_parameters_round_trip_as_empty(panel: AlgorithmPanel) -> None:
    """A spec without explicit parameters stays without explicit parameters."""
    panel.load_from(PipelineSpec(algorithm_id="fake_alpha"))
    out = PipelineSpec()
    panel.apply_to(out)
    assert out.algorithm_id == "fake_alpha"
    assert out.algorithm_params == {}


def test_load_from_does_not_emit_changed(panel: AlgorithmPanel) -> None:
    """Loading a spec never reports a user edit."""
    calls = _counter(panel)
    panel.load_from(_spec())
    assert calls == []
    panel.load_from(
        PipelineSpec(
            algorithm_id="fake_alpha",
            algorithm_params={"strength": 0.25, "serpentine": False},
            pixel_size=7,
            brightness=-1.0,
            contrast=1.0,
            gamma=0.5,
        )
    )
    assert calls == []
    assert panel.param_form.values() == {"strength": 0.25, "serpentine": False}


def test_switching_algorithm_resets_params_to_defaults(panel: AlgorithmPanel) -> None:
    """Choosing another algorithm rebuilds the form with that algorithm's defaults."""
    panel.load_from(
        _spec(algorithm_id="fake_alpha", algorithm_params={"strength": 0.25, "serpentine": False})
    )
    calls = _counter(panel)
    _select(panel, "fake_beta")
    assert len(calls) == 1
    assert panel.param_form.specs() == BETA.params
    assert panel.param_form.values() == BETA_DEFAULTS
    out = PipelineSpec()
    panel.apply_to(out)
    assert out.algorithm_id == "fake_beta"
    assert out.algorithm_params == {}


def test_user_edits_emit_changed(panel: AlgorithmPanel) -> None:
    """Every editor of the panel reports a user edit exactly once."""
    _select(panel, "fake_beta")
    calls = _counter(panel)
    panel.param_form.widget("spread").findChild(QDoubleSpinBox).setValue(1.5)
    assert len(calls) == 1
    panel.pixel_size_spin.setValue(4)
    assert len(calls) == 2
    panel.brightness.slider.setValue(panel.brightness.slider.maximum())
    assert len(calls) == 3
    panel.contrast.spin.setValue(-0.75)
    assert len(calls) == 4
    panel.gamma.slider.setValue(0)
    assert len(calls) == 5
    assert panel.brightness.value() == pytest.approx(1.0)
    assert panel.contrast.value() == pytest.approx(-0.75)
    assert panel.gamma.value() == pytest.approx(0.1)


def test_reset_restores_defaults(panel: AlgorithmPanel) -> None:
    """The reset button restores the parameter, pixel size and tone defaults."""
    panel.load_from(_spec())
    panel.pixel_size_spin.setValue(9)
    panel.brightness.slider.setValue(panel.brightness.slider.maximum())
    panel.gamma.spin.setValue(3.0)
    panel.param_form.widget("scale").setValue(6)
    calls = _counter(panel)
    panel.reset_button.click()
    assert len(calls) == 1
    assert panel.pixel_size_spin.value() == 1
    assert panel.brightness.value() == pytest.approx(0.0)
    assert panel.contrast.value() == pytest.approx(0.0)
    assert panel.gamma.value() == pytest.approx(1.0)
    assert panel.param_form.values() == BETA_DEFAULTS
    assert panel.algorithm_combo.currentData() == "fake_beta"


def test_pixel_size_spin_covers_the_contract_range(panel: AlgorithmPanel) -> None:
    """The pixel size spinbox spans 1 to 32 and clamps out-of-range specs."""
    assert panel.pixel_size_spin.minimum() == 1
    assert panel.pixel_size_spin.maximum() == 32
    panel.load_from(_spec(pixel_size=99))
    assert panel.pixel_size_spin.value() == 32
    panel.load_from(_spec(pixel_size=0))
    assert panel.pixel_size_spin.value() == 1


def test_tone_values_are_clamped(panel: AlgorithmPanel) -> None:
    """Out-of-range tone values are clamped to the contract ranges."""
    panel.load_from(_spec(brightness=5.0, contrast=-9.0, gamma=0.0))
    assert panel.brightness.value() == pytest.approx(1.0)
    assert panel.contrast.value() == pytest.approx(-1.0)
    assert panel.gamma.value() == pytest.approx(0.1)


def test_unknown_algorithm_falls_back_to_the_first_entry(panel: AlgorithmPanel) -> None:
    """An unknown algorithm id selects the first entry instead of raising."""
    calls = _counter(panel)
    panel.load_from(PipelineSpec(algorithm_id="does_not_exist", pixel_size=2))
    assert calls == []
    assert panel.algorithm_combo.currentData() == "fake_alpha"
    assert panel.param_form.values() == ALPHA_DEFAULTS
    assert panel.pixel_size_spin.value() == 2


def test_empty_registry_keeps_the_algorithm_id(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no registered algorithm the panel still loads and keeps the spec id."""
    monkeypatch.setattr(registry, "_ALGORITHMS", {})
    widget = AlgorithmPanel()
    assert widget.algorithm_combo.count() == 0
    assert widget.param_form.values() == {}
    widget.load_from(PipelineSpec(algorithm_id="keep_me", pixel_size=5))
    out = PipelineSpec(algorithm_id="keep_me")
    widget.apply_to(out)
    assert out.algorithm_id == "keep_me"
    assert out.pixel_size == 5
    widget.close()
