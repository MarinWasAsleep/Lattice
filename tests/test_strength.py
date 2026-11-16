"""Tests for the dither strength parameter (CONTRACT §14)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import lattice_core.dither  # noqa: F401
import lattice_core.effects  # noqa: F401
from lattice_core import color
from lattice_core.registry import get_algorithm, list_algorithms, resolve_params
from lattice_core.types import Image, Palette

BASELINE_PATH = Path(__file__).resolve().parent / "data" / "strength_baseline.json"
METRICS = ("srgb", "linear", "oklab", "lab2000")
SEEDS = (7, 11, 23)
ALGORITHM_IDS = tuple(info.id for info in list_algorithms())
FAMILIES = tuple(sorted({info.family for info in list_algorithms()}))


def _image(seed: int) -> Image:
    """Return a deterministic 24x18 float32 test image."""
    rng = np.random.default_rng(seed)
    return np.ascontiguousarray(rng.random((24, 18, 3), dtype=np.float32))


def _palettes() -> dict[str, Palette]:
    """Return the two palettes the baseline was captured with."""
    return {
        "bw": np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32),
        "four": np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 1.0]],
            dtype=np.float32,
        ),
    }


def _run(
    algorithm_id: str, img: Image, palette: Palette, metric: str = "srgb", **params: object
) -> np.ndarray:
    """Run one algorithm the way the pipeline does: working space plus metric code."""
    info = get_algorithm(algorithm_id)
    resolved = resolve_params(info.params, params)
    code = color.metric_code(metric)
    resolved["_color_metric"] = code
    return info.fn(
        color.to_working_space(img, code), color.to_working_space(palette, code), resolved
    )


def _baseline() -> dict[str, str]:
    """Return the pre-strength output digests captured at commit 3f5fbad."""
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_every_algorithm_declares_strength() -> None:
    """All 33 algorithms expose strength as a float in [0, 1] defaulting to 1."""
    for info in list_algorithms():
        specs = [spec for spec in info.params if spec.id == "strength"]
        assert len(specs) == 1, info.id
        spec = specs[0]
        assert spec.kind == "float", info.id
        assert (spec.min, spec.max) == (0.0, 1.0), info.id
        assert spec.default == 1.0, info.id


def test_baseline_covers_every_algorithm_and_palette() -> None:
    """The captured baseline has one digest per algorithm and palette pair."""
    expected = {f"{algorithm_id}|{name}" for algorithm_id in ALGORITHM_IDS for name in _palettes()}
    assert set(_baseline()) == expected


@pytest.mark.parametrize("algorithm_id", ALGORITHM_IDS)
def test_strength_zero_is_nearest(algorithm_id: str) -> None:
    """strength=0 reproduces nearest_index exactly, for every metric and palette."""
    for seed in SEEDS:
        img = _image(seed)
        for name, palette in _palettes().items():
            for metric in METRICS:
                expected = color.nearest_index(img, palette, metric)
                got = _run(algorithm_id, img, palette, metric, strength=0.0)
                assert np.array_equal(got, expected), (
                    f"{algorithm_id} palette={name} metric={metric} seed={seed}"
                )


@pytest.mark.parametrize("algorithm_id", ALGORITHM_IDS)
def test_strength_one_matches_pre_strength_output(algorithm_id: str) -> None:
    """strength=1 is byte-identical to the output before the parameter existed."""
    baseline = _baseline()
    img = _image(7)
    for name, palette in _palettes().items():
        indices = _run(algorithm_id, img, palette)
        digest = hashlib.sha256(indices.tobytes()).hexdigest()
        assert digest == baseline[f"{algorithm_id}|{name}"], f"{algorithm_id} palette={name}"


@pytest.mark.parametrize("family", FAMILIES)
def test_half_strength_sits_between_the_extremes(family: str) -> None:
    """At least one algorithm per family changes at 0.5 relative to both 0 and 1."""
    img = _image(7)
    palette = _palettes()["four"]
    differing = []
    for info in list_algorithms():
        if info.family != family:
            continue
        zero = _run(info.id, img, palette, strength=0.0)
        half = _run(info.id, img, palette, strength=0.5)
        full = _run(info.id, img, palette, strength=1.0)
        if not np.array_equal(half, zero) and not np.array_equal(half, full):
            differing.append(info.id)
    assert differing, f"no {family} algorithm changes at strength=0.5"


@pytest.mark.parametrize("algorithm_id", ALGORITHM_IDS)
def test_strength_is_clamped(algorithm_id: str) -> None:
    """resolve_params clamps strength into [0, 1] and defaults it to 1."""
    info = get_algorithm(algorithm_id)
    assert resolve_params(info.params, {"strength": -5.0})["strength"] == 0.0
    assert resolve_params(info.params, {"strength": 5.0})["strength"] == 1.0
    assert resolve_params(info.params, {})["strength"] == 1.0
