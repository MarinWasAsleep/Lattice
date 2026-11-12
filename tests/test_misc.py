"""Tests for the threshold, random and Riemersma algorithms (T04)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_dither.algorithms import misc  # noqa: F401
from lattice_dither.core.color import nearest_index
from lattice_dither.core.registry import get_algorithm, resolve_params
from lattice_dither.core.types import Image, Palette


def _run(algorithm_id: str, img: Image, palette: Palette, **params) -> np.ndarray:
    """Run a registered algorithm with resolved parameters."""
    info = get_algorithm(algorithm_id)
    return info.fn(img, palette, resolve_params(info.params, params))


def _grey(level: float, size: int = 64) -> Image:
    """Return a constant grey image."""
    return np.full((size, size, 3), level, dtype=np.float32)


def test_registration_family_and_params() -> None:
    """The three algorithms are registered in the "other" family with the documented params."""
    expected = {
        "threshold": {"level": 0.5},
        "random": {"spread": 1.0, "seed": 0},
        "riemersma": {"history": 16, "ratio": 1.0 / 16.0},
    }
    for algorithm_id, defaults in expected.items():
        info = get_algorithm(algorithm_id)
        assert info.family == "other"
        assert resolve_params(info.params, {}) == pytest.approx(defaults)


def test_threshold_is_monotonic_in_level(gradient: Image, pal_bw: Palette) -> None:
    """A higher level can only turn more pixels dark."""
    counts = [
        int((_run("threshold", gradient, pal_bw, level=level) == 0).sum())
        for level in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
    ]
    assert counts == sorted(counts)
    assert counts[0] == 0
    # The comparison is strict, so the pure white rightmost column stays light at level 1.
    assert counts[-1] == gradient.shape[0] * (gradient.shape[1] - 1)
    assert counts[3] > counts[1]


def test_threshold_uses_darkest_and_lightest(pal_4: Palette) -> None:
    """Threshold maps to the darkest and lightest palette entries, not to indices 0 and 1."""
    palette = pal_4[[3, 1, 0, 2]]
    out = _run("threshold", _grey(0.1), palette, level=0.5)
    assert set(np.unique(out).tolist()) == {2}
    out = _run("threshold", _grey(0.9), palette, level=0.5)
    assert set(np.unique(out).tolist()) == {0}


def test_threshold_extremes(pal_bw: Palette) -> None:
    """A black image is entirely dark and a white image entirely light."""
    assert (_run("threshold", _grey(0.0), pal_bw) == 0).all()
    assert (_run("threshold", _grey(1.0), pal_bw) == 1).all()


def test_random_is_deterministic_per_seed(pal_bw: Palette, photo_like: Image) -> None:
    """The same seed reproduces the output, another seed changes it."""
    first = _run("random", photo_like, pal_bw, seed=7)
    second = _run("random", photo_like, pal_bw, seed=7)
    other = _run("random", photo_like, pal_bw, seed=8)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, other)


def test_random_without_spread_is_nearest(pal_4: Palette, photo_like: Image) -> None:
    """A spread of zero leaves the plain nearest-colour mapping."""
    out = _run("random", photo_like, pal_4, spread=0.0, seed=3)
    assert np.array_equal(out, nearest_index(photo_like, pal_4))


def test_random_keeps_mean_on_grey(pal_bw: Palette) -> None:
    """White noise around mid grey keeps roughly half of the pixels white."""
    out = _run("random", _grey(0.5), pal_bw, seed=0)
    assert 0.45 <= float((out == 1).mean()) <= 0.55


def test_riemersma_white_fraction(pal_bw: Palette) -> None:
    """Riemersma on mid grey with a black and white palette yields about half white."""
    out = _run("riemersma", _grey(0.5), pal_bw)
    assert out.dtype == np.int32
    assert 0.45 <= float((out == 1).mean()) <= 0.55


def test_riemersma_extremes(pal_bw: Palette) -> None:
    """A black image is entirely dark and a white image entirely light."""
    assert (_run("riemersma", _grey(0.0), pal_bw) == 0).all()
    assert (_run("riemersma", _grey(1.0), pal_bw) == 1).all()


def test_riemersma_is_deterministic(pal_4: Palette, photo_like: Image) -> None:
    """Riemersma has no randomness, so two runs agree exactly."""
    first = _run("riemersma", photo_like, pal_4)
    second = _run("riemersma", photo_like, pal_4)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("shape", [(37, 23), (23, 37), (1, 5), (5, 1), (1, 1)])
def test_riemersma_covers_every_pixel(shape: tuple[int, int]) -> None:
    """The Hilbert traversal visits every in-bounds pixel of any shape."""
    palette = np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]], dtype=np.float32)
    img = np.zeros((*shape, 3), dtype=np.float32)
    out = _run("riemersma", img, palette)
    assert out.shape == shape
    assert out.dtype == np.int32
    assert set(np.unique(out).tolist()) <= {0, 1}
    # Index 0 is white here, so a pixel left at the kernel's zero initialisation would show up.
    assert np.all(out == 1)


def test_riemersma_history_and_ratio_change_output(pal_bw: Palette, gradient: Image) -> None:
    """The history length and the ratio both influence the result."""
    base = _run("riemersma", gradient, pal_bw)
    assert not np.array_equal(base, _run("riemersma", gradient, pal_bw, history=4))
    assert not np.array_equal(base, _run("riemersma", gradient, pal_bw, ratio=0.5))


def test_algorithms_do_not_mutate_inputs(pal_bw: Palette, photo_like: Image) -> None:
    """Every algorithm leaves the image and the palette untouched."""
    img = photo_like.copy()
    palette = pal_bw.copy()
    for algorithm_id in ("threshold", "random", "riemersma"):
        _run(algorithm_id, img, palette)
    assert np.array_equal(img, photo_like)
    assert np.array_equal(palette, pal_bw)


