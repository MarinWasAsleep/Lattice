"""Tests for the error diffusion algorithms."""

from __future__ import annotations

import time

import numpy as np
import pytest

from lattice_core.color import nearest_index
from lattice_core.dither.error_diffusion import KERNELS
from lattice_core.registry import get_algorithm, resolve_params
from lattice_core.types import Image, Palette

KERNEL_IDS = tuple(KERNELS)
EXPECTED_IDS = {
    "floyd_steinberg",
    "false_floyd_steinberg",
    "jarvis_judice_ninke",
    "stucki",
    "burkes",
    "sierra",
    "sierra_two_row",
    "sierra_lite",
    "fan",
    "shiau_fan",
    "atkinson",
    "stevenson_arce",
}


def _run(kernel_id: str, img: Image, palette: Palette, **params: object) -> np.ndarray:
    """Run one registered kernel with the given parameter overrides."""
    info = get_algorithm(kernel_id)
    return info.fn(img.copy(), palette.copy(), resolve_params(info.params, params))


def test_registered_kernels() -> None:
    """Exactly the twelve kernels are registered with the two shared params."""
    assert set(KERNELS) == EXPECTED_IDS
    for kernel_id in KERNEL_IDS:
        info = get_algorithm(kernel_id)
        assert info.family == "error_diffusion"
        assert [spec.id for spec in info.params] == ["serpentine", "strength"]
        assert resolve_params(info.params, {}) == {"serpentine": True, "strength": 1.0}


def test_weight_sums() -> None:
    """Every kernel diffuses all of the error except Atkinson, which keeps 0.75."""
    for kernel_id, (divisor, entries) in KERNELS.items():
        total = sum(weight for _, _, weight in entries) / divisor
        expected = 0.75 if kernel_id == "atkinson" else 1.0
        assert total == pytest.approx(expected), kernel_id


def test_offsets_are_forward_only() -> None:
    """No kernel writes to an already processed row."""
    for kernel_id, (_, entries) in KERNELS.items():
        assert all(dy >= 0 for _, dy, _ in entries), kernel_id
        assert all(dy > 0 or dx > 0 for dx, dy, _ in entries), kernel_id


@pytest.mark.parametrize("kernel_id", KERNEL_IDS)
def test_black_and_white_are_uniform(kernel_id: str, pal_bw: Palette) -> None:
    """A flat black image maps to black and a flat white image to white."""
    black = np.zeros((16, 16, 3), dtype=np.float32)
    white = np.ones((16, 16, 3), dtype=np.float32)
    assert np.all(_run(kernel_id, black, pal_bw) == 0)
    assert np.all(_run(kernel_id, white, pal_bw) == 1)


@pytest.mark.parametrize("kernel_id", KERNEL_IDS)
def test_grey_half_white_fraction(kernel_id: str, pal_bw: Palette) -> None:
    """A 0.5 grey image dithers to roughly half white pixels."""
    grey = np.full((64, 64, 3), 0.5, dtype=np.float32)
    out = _run(kernel_id, grey, pal_bw)
    fraction = float((out == 1).mean())
    low, high = (0.45, 0.55) if kernel_id == "atkinson" else (0.48, 0.52)
    assert low <= fraction <= high, (kernel_id, fraction)


def test_serpentine_changes_output(gradient: Image, pal_bw: Palette) -> None:
    """Serpentine and raster traversal produce different results on a ramp."""
    forward = _run("floyd_steinberg", gradient, pal_bw, serpentine=True)
    raster = _run("floyd_steinberg", gradient, pal_bw, serpentine=False)
    assert not np.array_equal(forward, raster)
    assert np.array_equal(forward, _run("floyd_steinberg", gradient, pal_bw, serpentine=True))


def test_strength_zero_matches_nearest(gradient: Image, pal_4: Palette) -> None:
    """Zero strength disables error propagation and equals plain quantisation."""
    out = _run("jarvis_judice_ninke", gradient, pal_4, strength=0.0)
    assert np.array_equal(out, nearest_index(gradient, pal_4))


def test_output_dtype_and_shape(photo_like: Image, pal_4: Palette) -> None:
    """Every kernel returns int32 indices of the input shape inside [0, K)."""
    for kernel_id in KERNEL_IDS:
        out = _run(kernel_id, photo_like, pal_4)
        assert out.dtype == np.int32
        assert out.shape == photo_like.shape[:2]
        assert int(out.min()) >= 0
        assert int(out.max()) < pal_4.shape[0]


def test_inputs_are_not_mutated(photo_like: Image, pal_4: Palette) -> None:
    """The kernel works on a copy and leaves the caller's arrays untouched."""
    img = photo_like.copy()
    palette = pal_4.copy()
    _run("stucki", img, palette)
    assert np.array_equal(img, photo_like)
    assert np.array_equal(palette, pal_4)


@pytest.mark.perf
def test_perf_floyd_steinberg_1024(rng: np.random.Generator) -> None:
    """Floyd-Steinberg on 1024x1024 with K=16 stays under 0.5 s after warm-up."""
    img = rng.random((1024, 1024, 3), dtype=np.float32)
    palette = rng.random((16, 3), dtype=np.float32)
    _run("floyd_steinberg", img, palette)
    start = time.perf_counter()
    _run("floyd_steinberg", img, palette)
    assert time.perf_counter() - start < 0.5
