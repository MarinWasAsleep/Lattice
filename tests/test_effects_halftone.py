"""Tests for the CMYK halftone effect (T20 / CONTRACT §15.2)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_core.effects.halftone import plates
from lattice_core.registry import get_effect, resolve_params

EFFECT_ID = "halftone_cmyk"
SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))


def _apply(img: np.ndarray, seed: int = 0, **params: object) -> np.ndarray:
    """Run the effect with resolved parameters."""
    info = get_effect(EFFECT_ID)
    return info.fn(img, resolve_params(info.params, params), np.random.default_rng(seed))


def _flat(level: float, shape: tuple[int, int] = (32, 32)) -> np.ndarray:
    """Return a constant grey image."""
    return np.full((*shape, 3), level, dtype=np.float32)


def test_registration_and_params() -> None:
    """The effect is registered with the five documented parameters."""
    info = get_effect(EFFECT_ID)
    assert [spec.id for spec in info.params] == [
        "lpi",
        "dot_shape",
        "black_pullout",
        "oversample",
        "ink_colors",
    ]
    assert resolve_params(info.params, {}) == {
        "lpi": 60,
        "dot_shape": "round",
        "black_pullout": 0.5,
        "oversample": 2,
        "ink_colors": False,
    }


def test_white_produces_no_ink() -> None:
    """Pure white leaves every plate empty and the output white."""
    white = _flat(1.0)
    assert all(float(plate.max()) == 0.0 for plate in plates(white, 0.5))
    out = _apply(white)
    assert np.allclose(out, 1.0)


def test_black_pullout_moves_the_grey_component_to_k() -> None:
    """At pullout 1 black is K only; at pullout 0 it is C, M and Y only."""
    black = _flat(0.0)
    full = [float(plate.mean()) for plate in plates(black, 1.0)]
    none = [float(plate.mean()) for plate in plates(black, 0.0)]
    assert full == [0.0, 0.0, 0.0, 1.0]
    assert none == [1.0, 1.0, 1.0, 0.0]


def test_black_ink_colors_show_which_plates_are_used() -> None:
    """With ink colours, a mid grey renders grey at pullout 1 and coloured at pullout 0."""
    grey = _flat(0.5)
    k_only = _apply(grey, black_pullout=1.0, ink_colors=True)
    cmy = _apply(grey, black_pullout=0.0, ink_colors=True)
    assert np.allclose(k_only[:, :, 0], k_only[:, :, 1])
    assert np.allclose(k_only[:, :, 1], k_only[:, :, 2])
    assert not np.allclose(cmy[:, :, 0], cmy[:, :, 1])


@pytest.mark.parametrize("shape", SHAPES)
def test_shape_dtype_and_range(shape: tuple[int, int]) -> None:
    """Any image shape yields a float32 image in [0, 1] of the same shape."""
    out = _apply(_flat(0.5, shape))
    assert out.shape == (*shape, 3)
    assert out.dtype == np.float32
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_ink_colors_is_not_greyscale_on_a_coloured_input() -> None:
    """The four plates are rendered in their own inks, so the output keeps colour."""
    red = np.zeros((32, 32, 3), dtype=np.float32)
    red[:, :, 0] = 1.0
    coloured = _apply(red, ink_colors=True)
    grey = _apply(red, ink_colors=False)
    assert not np.allclose(coloured[:, :, 0], coloured[:, :, 1])
    assert np.allclose(grey[:, :, 0], grey[:, :, 1])


def test_lpi_changes_the_cell_size() -> None:
    """A coarser screen produces a different pattern than a finer one."""
    img = _flat(0.5)
    coarse = _apply(img, lpi=20)
    fine = _apply(img, lpi=200)
    assert not np.array_equal(coarse, fine)


def test_oversample_changes_the_pattern() -> None:
    """Oversampling the spot function changes the rendered screen."""
    img = _flat(0.5)
    assert not np.array_equal(_apply(img, oversample=1), _apply(img, oversample=4))


@pytest.mark.parametrize("shape", ("round", "square", "diamond", "ellipse"))
def test_every_dot_shape_is_accepted(shape: str) -> None:
    """The four print shapes all render, and no two of them render the same thing."""
    img = _flat(0.5)
    outputs = {
        name: _apply(img, dot_shape=name) for name in ("round", "square", "diamond", "ellipse")
    }
    assert outputs[shape].shape == img.shape
    names = list(outputs)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            assert not np.array_equal(outputs[first], outputs[second]), (first, second)


def test_unknown_dot_shape_raises() -> None:
    """A shape outside the four print shapes is rejected."""
    info = get_effect(EFFECT_ID)
    with pytest.raises(ValueError):
        resolve_params(info.params, {"dot_shape": "cross"})


def test_does_not_mutate_the_input(photo_like: np.ndarray) -> None:
    """The source image is left untouched."""
    source = photo_like.copy()
    _apply(photo_like)
    assert np.array_equal(photo_like, source)
