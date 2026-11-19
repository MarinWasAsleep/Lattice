"""Tests for the tone effects (T07A)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice.effects.tone import _gaussian_blur
from lattice.registry import get_effect, list_effects, resolve_params

CARD_PARAMS: dict[str, tuple[tuple[str, str, object, float | None, float | None], ...]] = {
    "gaussian_blur": (("radius", "float", 0.0, 0.0, 50.0),),
    "sharpen": (("amount", "float", 1.0, 0.0, 3.0), ("radius", "float", 1.5, 0.5, 10.0)),
    "glow": (
        ("threshold", "float", 0.7, 0.0, 1.0),
        ("radius", "float", 10.0, 1.0, 50.0),
        ("intensity", "float", 1.0, 0.0, 3.0),
    ),
    "noise": (("amount", "float", 0.1, 0.0, 1.0), ("monochrome", "bool", True, None, None)),
    "posterize": (("levels", "int", 4, 2, 32),),
}

EFFECT_IDS = tuple(CARD_PARAMS)
SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))

MIN_PARAMS = {
    "gaussian_blur": {"radius": 0.0},
    "sharpen": {"amount": 0.0, "radius": 0.5},
    "glow": {"threshold": 0.0, "radius": 1.0, "intensity": 0.0},
    "noise": {"amount": 0.0, "monochrome": False},
    "posterize": {"levels": 2},
}

MAX_PARAMS = {
    "gaussian_blur": {"radius": 50.0},
    "sharpen": {"amount": 3.0, "radius": 10.0},
    "glow": {"threshold": 1.0, "radius": 50.0, "intensity": 3.0},
    "noise": {"amount": 1.0, "monochrome": True},
    "posterize": {"levels": 32},
}


def _apply(
    effect_id: str, img: np.ndarray, params: dict | None = None, seed: int = 0
) -> np.ndarray:
    """Run one registered effect with resolved parameters and a seeded generator."""
    info = get_effect(effect_id)
    resolved = resolve_params(info.params, dict(params or {}))
    return info.fn(img.copy(), resolved, np.random.default_rng(seed))


def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """Return a seeded random float32 image of the given (H, W)."""
    return np.random.default_rng(seed).random(shape + (3,), dtype=np.float32)


def test_registers_exactly_five_tone_effects() -> None:
    """The tone module registers exactly the five effects named by the card."""
    mine = [info for info in list_effects() if info.fn.__module__ == "lattice.effects.tone"]
    assert sorted(info.id for info in mine) == sorted(EFFECT_IDS)


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
def test_param_specs_match_card(effect_id: str) -> None:
    """Parameter ids, kinds, defaults and bounds match the card verbatim."""
    info = get_effect(effect_id)
    actual = tuple((s.id, s.kind, s.default, s.min, s.max) for s in info.params)
    assert actual == CARD_PARAMS[effect_id]


def test_radius_zero_blur_is_identity(gradient: np.ndarray) -> None:
    """A blur radius of 0 returns the image unchanged."""
    out = _apply("gaussian_blur", gradient, {"radius": 0.0})
    assert np.array_equal(out, gradient)


def test_blur_preserves_mean() -> None:
    """Blurring a random image keeps its mean within 1e-3."""
    img = _random_image((64, 64))
    out = _apply("gaussian_blur", img, {"radius": 9.0})
    assert abs(float(out.mean()) - float(img.mean())) < 1e-3


def test_blur_kernel_radius_is_three_sigma() -> None:
    """The kernel reaches exactly ceil(3 * sigma) pixels and no further."""
    delta = np.zeros((21, 21, 3), dtype=np.float32)
    delta[10, 10] = 1.0
    out = _gaussian_blur(delta, 1.0)
    assert out[10, 13, 0] > 0.0
    assert out[10, 14, 0] == 0.0
    assert out[13, 10, 0] > 0.0
    assert out[14, 10, 0] == 0.0


def test_blur_reduces_variance() -> None:
    """Blurring a noisy image lowers its variance."""
    img = _random_image((48, 48))
    out = _apply("gaussian_blur", img, {"radius": 6.0})
    assert float(out.var()) < float(img.var())


def test_blur_radius_maps_to_sigma_of_radius_over_three() -> None:
    """The registered blur uses sigma = radius / 3."""
    img = _random_image((32, 32))
    assert np.array_equal(_apply("gaussian_blur", img, {"radius": 9.0}), _gaussian_blur(img, 3.0))


def test_sharpen_amount_zero_is_identity(photo_like: np.ndarray) -> None:
    """An unsharp amount of 0 returns the image unchanged."""
    out = _apply("sharpen", photo_like, {"amount": 0.0})
    assert np.array_equal(out, photo_like)


def test_sharpen_increases_edge_contrast() -> None:
    """Sharpening a step edge overshoots on both sides of the edge."""
    img = np.full((32, 32, 3), 0.2, dtype=np.float32)
    img[:, 16:] = 0.8
    out = _apply("sharpen", img, {"amount": 1.0, "radius": 1.5})
    assert float(out.max()) > float(img.max())
    assert float(out.min()) < float(img.min())


@pytest.mark.parametrize(
    "params",
    [
        {"threshold": 0.7, "radius": 10.0, "intensity": 1.0},
        {"threshold": 0.0, "radius": 50.0, "intensity": 3.0},
        {"threshold": 1.0, "radius": 1.0, "intensity": 0.5},
    ],
)
def test_glow_never_darkens(params: dict) -> None:
    """The screen blend of the glow effect never lowers any pixel."""
    img = _random_image((37, 23))
    out = _apply("glow", img, params)
    assert float((out - img).min()) >= -1e-6


def test_glow_intensity_zero_is_identity(photo_like: np.ndarray) -> None:
    """A glow intensity of 0 returns the image unchanged."""
    out = _apply("glow", photo_like, {"intensity": 0.0})
    assert np.array_equal(out, photo_like)


def _bright_patch(
    size: int = 64, low: int = 28, high: int = 36, background: float = 0.05
) -> np.ndarray:
    """Return a dark image holding a white square in the middle."""
    img = np.full((size, size, 3), background, dtype=np.float32)
    img[low:high, low:high] = 1.0
    return img


def _distance_from_patch(size: int = 64, low: int = 28, high: int = 36) -> np.ndarray:
    """Return the (H, W) pixel distance from the white square of _bright_patch."""
    rows = np.arange(size)[:, None]
    cols = np.arange(size)[None, :]
    dy = np.maximum(np.maximum(low - rows, rows - (high - 1)), 0)
    dx = np.maximum(np.maximum(low - cols, cols - (high - 1)), 0)
    return np.hypot(dy, dx)


def test_glow_brightens_the_dark_ring_around_a_bright_patch() -> None:
    """A white square lifts the dark pixels around it and leaves the far background alone."""
    img = _bright_patch()
    distance = _distance_from_patch()
    ring = (distance >= 1.0) & (distance < 6.0)
    far = distance >= 20.0
    out = _apply("glow", img, {"threshold": 0.7, "radius": 10.0, "intensity": 1.0})
    assert float(out[ring].mean()) > float(img[ring].mean()) + 0.05
    assert float(out[ring].mean()) > float(out[far].mean()) + 0.05
    assert np.allclose(out[far], img[far], atol=1e-6)


def test_glow_larger_radius_spreads_the_halo_further() -> None:
    """A big radius carries the halo further out and dims the ring next to the patch."""
    img = _bright_patch()
    distance = _distance_from_patch()
    near = (distance >= 1.0) & (distance < 3.0)
    far = (distance >= 6.0) & (distance < 16.0)
    small = _apply("glow", img, {"threshold": 0.7, "radius": 4.0, "intensity": 1.0})
    large = _apply("glow", img, {"threshold": 0.7, "radius": 20.0, "intensity": 1.0})
    assert float(small[far].mean()) < float(img[far].mean()) + 0.005
    assert float(large[far].mean()) > float(small[far].mean()) + 0.015
    assert float(large[near].mean()) < float(small[near].mean())


def test_noise_amount_zero_is_identity(photo_like: np.ndarray) -> None:
    """A noise amount of 0 returns the image unchanged."""
    out = _apply("noise", photo_like, {"amount": 0.0})
    assert np.array_equal(out, photo_like)


def test_noise_is_deterministic_per_seed() -> None:
    """The same seed gives identical noise and a different seed gives different noise."""
    img = _random_image((32, 32))
    first = _apply("noise", img, {"amount": 0.3}, seed=5)
    second = _apply("noise", img, {"amount": 0.3}, seed=5)
    other = _apply("noise", img, {"amount": 0.3}, seed=6)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, other)


def test_noise_monochrome_shares_one_noise_field() -> None:
    """Monochrome noise keeps the channels equal, colour noise does not."""
    img = np.full((16, 16, 3), 0.5, dtype=np.float32)
    mono = _apply("noise", img, {"amount": 0.2, "monochrome": True})
    colour = _apply("noise", img, {"amount": 0.2, "monochrome": False})
    assert np.array_equal(mono[:, :, 0], mono[:, :, 1])
    assert np.array_equal(mono[:, :, 1], mono[:, :, 2])
    assert not np.array_equal(colour[:, :, 0], colour[:, :, 1])


@pytest.mark.parametrize("levels", [2, 3, 4, 7, 32])
def test_posterize_has_at_most_levels_unique_values(levels: int) -> None:
    """Every channel of a posterized image holds at most `levels` distinct values."""
    out = _apply("posterize", _random_image((48, 48)), {"levels": levels})
    for channel in range(3):
        assert np.unique(out[:, :, channel]).size <= levels


def test_posterize_two_levels_is_binary() -> None:
    """Two levels reduce every channel to 0 or 1."""
    out = _apply("posterize", _random_image((32, 32)), {"levels": 2})
    assert set(np.unique(out).tolist()) <= {0.0, 1.0}


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_outputs_are_float32_in_range(effect_id: str, shape: tuple[int, int]) -> None:
    """Every effect returns a float32 image of the input shape inside [0, 1]."""
    img = _random_image(shape)
    out = _apply(effect_id, img)
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
def test_effects_do_not_mutate_input(effect_id: str) -> None:
    """Effects never write into the array they were given."""
    img = _random_image((24, 24))
    before = img.copy()
    _apply(effect_id, img, MAX_PARAMS[effect_id])
    assert np.array_equal(img, before)


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
@pytest.mark.parametrize("shape", [(1, 1), (3, 2), (37, 23)])
def test_effects_never_raise_at_extreme_params(effect_id: str, shape: tuple[int, int]) -> None:
    """Minimum and maximum parameters never raise and stay inside the contract."""
    img = _random_image(shape)
    for params in (MIN_PARAMS[effect_id], MAX_PARAMS[effect_id]):
        out = _apply(effect_id, img, params)
        assert out.shape == img.shape
        assert out.dtype == np.float32
        assert float(out.min()) >= 0.0
        assert float(out.max()) <= 1.0


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
def test_effects_are_deterministic_for_a_given_rng(effect_id: str) -> None:
    """Two runs with equally seeded generators produce identical output."""
    img = _random_image((32, 32))
    first = _apply(effect_id, img, seed=11)
    second = _apply(effect_id, img, seed=11)
    assert np.array_equal(first, second)


def test_constant_image_stays_constant_under_blur() -> None:
    """Blurring a constant image returns the same constant."""
    img = np.full((16, 16, 3), 0.25, dtype=np.float32)
    out = _apply("gaussian_blur", img, {"radius": 30.0})
    assert np.allclose(out, 0.25, atol=1e-6)
