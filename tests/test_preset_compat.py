"""Gate G5: the three witness presets still render byte-identically to their 1.0 baselines."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

import lattice_core.dither  # noqa: F401
import lattice_core.effects  # noqa: F401
from lattice_core.color import to_float
from lattice_core.pipeline import render
from lattice_core.presets import load_preset

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "data" / "baseline"
WITNESSES = ("01_gameboy", "05_ega_riemersma", "07_grey16_stucki")


def _source() -> np.ndarray:
    """Load the committed witness source as a float32 image."""
    return to_float(PILImage.open(BASELINE / "source.png"))


def _baseline(name: str) -> np.ndarray:
    """Load one committed baseline render as a uint8 RGB array."""
    return np.asarray(PILImage.open(BASELINE / f"{name}.png").convert("RGB"))


@pytest.mark.parametrize("name", WITNESSES)
def test_witness_preset_matches_its_baseline(name: str) -> None:
    """The preset renders exactly the bytes committed before the 1.1 pipeline change."""
    spec = load_preset(ROOT / "presets" / f"{name}.json")
    assert np.array_equal(render(_source(), spec), _baseline(name))


@pytest.mark.parametrize("name", WITNESSES)
def test_witness_preset_loads_as_version_one(name: str) -> None:
    """The shipped presets are still version 1 and take the v2 defaults."""
    spec = load_preset(ROOT / "presets" / f"{name}.json")
    assert spec.version == 1
    assert spec.saturation == 0.0
    assert spec.pre_blur == 0.0
    assert spec.auto_levels is False
    assert spec.color_metric == "srgb"


@pytest.mark.parametrize("name", WITNESSES)
def test_witness_preset_survives_a_v2_round_trip(name: str) -> None:
    """Saving a witness as v2 and reloading it renders the same bytes."""
    from lattice_core.presets import from_json, to_json

    spec = load_preset(ROOT / "presets" / f"{name}.json")
    upgraded = from_json(to_json(spec))
    assert upgraded.version == 2
    assert np.array_equal(render(_source(), upgraded), _baseline(name))
