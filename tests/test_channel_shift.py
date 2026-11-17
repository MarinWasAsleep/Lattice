"""Tests for the L16 channel shift effect (CONTRACT §15)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_core.effects.channel_shift import (
    DEFAULT_CHANNELS,
    channel_shift,
    validate_params,
)
from lattice_core.registry import get_effect, resolve_params

MODES = ("translate", "scale", "radial")
SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))


def _apply(
    img: np.ndarray, params: dict | None = None, seed: int = 0
) -> np.ndarray:
    """Run the registered effect with resolved params and a seeded generator."""
    info = get_effect("channel_shift")
    resolved = resolve_params(info.params, dict(params or {}))
    return info.fn(img.copy(), resolved, np.random.default_rng(seed))


def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """Return a seeded random float32 RGB image of shape (H, W, 3)."""
    return np.random.default_rng(seed).random((shape[0], shape[1], 3), dtype=np.float32)


def test_registration_matches_card() -> None:
    """The module registers one effect with the three documented options."""
    info = get_effect("channel_shift")
    assert info.fn is channel_shift
    assert tuple(spec.id for spec in info.params) == ("amount", "mode", "channels")
    assert tuple(spec.default for spec in info.params) == (4.0, "translate", DEFAULT_CHANNELS)
    assert info.params[1].choices == MODES
    assert DEFAULT_CHANNELS == 0b101


def test_amount_zero_returns_input_unchanged() -> None:
    """A zero amount yields an unchanged copy for every mode and mask."""
    img = _random_image((13, 17))
    for mode in MODES:
        out = _apply(img, {"amount": 0.0, "mode": mode, "channels": 0b111})
        np.testing.assert_array_equal(out, img)
        assert out.dtype == np.float32


def test_amount_zero_does_not_mutate_input() -> None:
    """The source array is never written to, even on the no-op path."""
    img = _random_image((9, 11), seed=5)
    before = img.copy()
    out = channel_shift(img, {"amount": 0.0}, np.random.default_rng(0))
    np.testing.assert_array_equal(img, before)
    np.testing.assert_array_equal(out, before)
    assert out is not img


def test_translate_shifts_red_and_blue_in_opposite_directions() -> None:
    """A translate shifts R left and B right by the same amount; G stays put."""
    width = 17
    img = np.zeros((1, width, 3), dtype=np.float32)
    img[0, 8, 0] = 1.0
    img[0, 8, 2] = 1.0
    img[:, :, 1] = 0.25
    out = _apply(img, {"amount": 2.0, "mode": "translate", "channels": 0b111})
    red_x = int(np.argmax(out[0, :, 0]))
    blue_x = int(np.argmax(out[0, :, 2]))
    assert red_x == 6
    assert blue_x == 10
    assert blue_x - red_x == 4
    np.testing.assert_array_equal(out[:, :, 1], img[:, :, 1])


def test_channels_restricted_to_r_leaves_g_and_b_untouched() -> None:
    """A mask of R only changes the red channel; a zero mask changes nothing."""
    img = _random_image((24, 32))
    params = {"amount": 3.0, "mode": "translate", "channels": 0b001}
    out = _apply(img, params)
    np.testing.assert_array_equal(out[:, :, 1], img[:, :, 1])
    np.testing.assert_array_equal(out[:, :, 2], img[:, :, 2])
    assert not np.array_equal(out[:, :, 0], img[:, :, 0])
    unchanged = _apply(img, {**params, "channels": 0})
    np.testing.assert_array_equal(unchanged, img)


def test_radial_shifts_edges_more_than_the_centre() -> None:
    """The radial displacement grows with distance from the image centre."""
    width = 33
    centre = (width - 1) // 2
    params = {"amount": 8.0, "mode": "radial", "channels": 0b001}

    def displacement(x: int) -> float:
        """Return how far a one-pixel red marker at column x is moved."""
        img = np.zeros((1, width, 3), dtype=np.float32)
        img[0, x, 0] = 1.0
        out = _apply(img, params)
        reached = float(np.average(np.arange(width), weights=out[0, :, 0]))
        return abs(reached - x)

    centre_shift = displacement(centre)
    edge_shift = displacement(width - 3)
    assert centre_shift < 0.5
    assert edge_shift > centre_shift + 1.0


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("mode", MODES)
def test_output_shape_dtype_and_no_mutation(shape: tuple[int, int], mode: str) -> None:
    """Every mode preserves shape and dtype and leaves the input untouched."""
    img = _random_image(shape, seed=13)
    before = img.copy()
    out = channel_shift(
        img, {"amount": 2.0, "mode": mode, "channels": 0b111}, np.random.default_rng(0)
    )
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert out.flags["C_CONTIGUOUS"]
    np.testing.assert_array_equal(img, before)


def test_output_is_deterministic_and_bounded() -> None:
    """The effect ignores rng and always returns values inside [0, 1]."""
    img = _random_image((29, 41), seed=3)
    params = {"amount": 5.0, "mode": "radial", "channels": 0b111}
    first = _apply(img, params, seed=1)
    second = _apply(img, params, seed=99)
    np.testing.assert_array_equal(first, second)
    assert np.isfinite(first).all()
    assert first.min() >= 0.0
    assert first.max() <= 1.0


@pytest.mark.parametrize(
    "params", [{"mode": "warp"}, {"amount": -1.0}, {"amount": np.nan}, {"channels": 8}]
)
def test_invalid_params_raise(params: dict) -> None:
    """Unknown modes, negative amounts and out-of-range masks are rejected."""
    with pytest.raises(ValueError):
        validate_params(params)
