"""Tests for the displacement effect (card L14 / CONTRACT §13)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice.effects.displace import displace
from lattice.registry import get_effect, resolve_params

EFFECT_ID = "displace"
MODES = ("luma", "r", "g", "b", "hue")
SHAPES = ((1, 1), (1, 7), (7, 1), (37, 23), (64, 64))
SEED = 11
K = 8.0


def _params(**overrides: object) -> dict:
    """Return a full displacement parameter dict with deterministic test defaults."""
    params: dict = {
        "amount": K,
        "mode": "r",
        "map_source": "sequence",
        "iterations": 1,
        "decay": 0.5,
    }
    params.update(overrides)
    return params


def _run(
    img: np.ndarray,
    overrides: dict | None = None,
    seed: int = SEED,
    **kwargs: object,
) -> np.ndarray:
    """Run the effect with a freshly seeded generator and the given overrides."""
    return displace(img, _params(**(overrides or {})), np.random.default_rng(seed), **kwargs)


def _noise_image(shape: tuple[int, int] = (32, 32), seed: int = 7) -> np.ndarray:
    """Return a deterministic non-constant float32 RGB image."""
    return np.random.default_rng(seed).random((*shape, 3), dtype=np.float32)


def _x_ramp(width: int, height: int) -> np.ndarray:
    """Return an (H, W) field rising linearly from 0 to 1 across the width."""
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    return np.repeat(ramp, height, axis=0)


def _plateau(width: int, height: int, low: float, high: float) -> np.ndarray:
    """Return an (H, W) field that is 0 left of low, 1 right of high, linear between."""
    x = np.arange(width, dtype=np.float32)
    ramp = np.clip((x - np.float32(low)) / np.float32(high - low), 0.0, 1.0)[None, :]
    return np.repeat(ramp, height, axis=0)


def _x_gradient_image(width: int, height: int) -> np.ndarray:
    """Return an (H, W, 3) image whose value encodes its own x coordinate."""
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
    return np.ascontiguousarray(np.repeat(np.repeat(ramp, height, axis=0), 3, axis=2))


def _y_gradient_image(width: int, height: int) -> np.ndarray:
    """Return an (H, W, 3) image whose value encodes its own y coordinate."""
    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    return np.ascontiguousarray(np.repeat(np.repeat(ramp, width, axis=1), 3, axis=2))


def _edge_image(height: int, width: int, split: int) -> np.ndarray:
    """Return a black image with a white right half."""
    img = np.zeros((height, width, 3), dtype=np.float32)
    img[:, split:, :] = 1.0
    return img


def _edge_spread(img: np.ndarray, row: int) -> int:
    """Return how many pixels of row are strictly between black and white."""
    values = img[row, :, 0]
    return int(np.count_nonzero((values > 0.02) & (values < 0.98)))


def test_registration_and_name() -> None:
    """The effect is registered under the card id with a human name."""
    info = get_effect(EFFECT_ID)
    assert info.name == "Displacement"
    assert info.fn is displace


def test_param_specs_cover_the_contract_options() -> None:
    """The five options carry the ids, kinds, defaults and bounds the card needs."""
    info = get_effect(EFFECT_ID)
    actual = tuple((s.id, s.kind, s.default, s.min, s.max) for s in info.params)
    assert actual == (
        ("amount", "float", 8.0, 0.0, 64.0),
        ("mode", "choice", "luma", None, None),
        ("map_source", "choice", "image", None, None),
        ("iterations", "int", 1, 1, 8),
        ("decay", "float", 0.5, 0.0, 0.99),
    )
    assert get_effect(EFFECT_ID).params[1].choices == MODES
    assert get_effect(EFFECT_ID).params[2].choices == ("image", "sequence", "noise", "feedback")


def test_resolve_params_fills_defaults_and_clamps() -> None:
    """Defaults resolve cleanly and every numeric bound clamps."""
    info = get_effect(EFFECT_ID)
    assert resolve_params(info.params, {}) == {
        "amount": 8.0,
        "mode": "luma",
        "map_source": "image",
        "iterations": 1,
        "decay": 0.5,
    }
    clamped = resolve_params(info.params, {"amount": 999.0, "iterations": 99, "decay": 5.0})
    assert clamped["amount"] == 64.0
    assert clamped["iterations"] == 8
    assert clamped["decay"] == 0.99
    assert resolve_params(info.params, {"amount": -3.0, "iterations": 0})["amount"] == 0.0
    assert resolve_params(info.params, {"iterations": 0})["iterations"] == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("iterations", [1, 2, 3, 8])
def test_a_flat_grey_map_leaves_the_image_unchanged(mode: str, iterations: int) -> None:
    """A map of constant 0.5 drives no shift, so the image comes back bit-identical."""
    img = _noise_image()
    grey = np.full(img.shape[:2], 0.5, dtype=np.float32)
    out = _run(img, {"mode": mode, "iterations": iterations}, map_img=grey)
    assert np.array_equal(out, img)


@pytest.mark.parametrize("mode", MODES)
def test_a_flat_grey_three_channel_map_also_leaves_the_image_unchanged(mode: str) -> None:
    """A grey RGB map has R = G = B = 0.5, so neither driver moves."""
    img = _noise_image()
    grey = np.full((*img.shape[:2], 3), 0.5, dtype=np.float32)
    out = _run(img, {"mode": mode, "iterations": 3}, map_img=grey)
    assert np.array_equal(out, img)


@pytest.mark.parametrize("mode", MODES)
def test_a_flat_grey_source_is_its_own_map_and_stays_unchanged(mode: str) -> None:
    """With the source as map, a grey image has a neutral field on both axes."""
    img = np.full((16, 16, 3), 0.5, dtype=np.float32)
    out = _run(img, {"mode": mode, "map_source": "image", "iterations": 3})
    assert np.array_equal(out, img)


def test_a_horizontal_ramp_shifts_by_exactly_half_k_at_the_extremes() -> None:
    """Where the ramp saturates at 0 and 1 the shift is exactly -k/2 and +k/2."""
    height, width = 64, 192
    src = _x_gradient_image(width, height)
    field = _plateau(width, height, 48.0, 96.0)
    out = _run(src, {"mode": "r", "amount": K}, map_img=field)
    half = int(K // 2)
    for px in (10, 20, 40, 48):
        assert np.array_equal(out[0, px], src[0, px - half]), px
    for px in (96, 120, 150):
        assert np.array_equal(out[0, px], src[0, px + half]), px
    assert float(out[0, 10, 0]) * (width - 1) - 10 == pytest.approx(-K / 2, abs=1e-4)
    assert float(out[0, 150, 0]) * (width - 1) - 150 == pytest.approx(K / 2, abs=1e-4)


def test_the_shift_follows_the_formula_along_a_linear_ramp() -> None:
    """On the linear part of the ramp the shift is k * (mapR - 0.5) in pixels."""
    height, width = 32, 128
    src = _x_gradient_image(width, height)
    field = _x_ramp(width, height)
    out = _run(src, {"mode": "r", "amount": K}, map_img=field)
    for px in (16, 32, 48, 64, 80, 96):
        shift = float(out[0, px, 0]) * (width - 1) - px
        assert shift == pytest.approx(K * (float(field[0, px]) - 0.5), abs=1e-3)


def test_the_vertical_driver_is_the_green_channel() -> None:
    """A neutral red channel with a green ramp shifts vertically and not horizontally."""
    height, width = 64, 192
    src = _y_gradient_image(width, height)
    field = _plateau(width, height, 48.0, 96.0)
    neutral = np.full((height, width), 0.5, dtype=np.float32)
    map_rgb = np.stack([neutral, field, neutral], axis=-1)
    out = _run(src, {"mode": "r", "amount": K}, map_img=map_rgb)
    half = int(K // 2)
    assert np.array_equal(out[0, 96], src[half, 96])
    assert np.array_equal(out[60, 10], src[60 - half, 10])
    # The red driver is neutral, so an image that varies only along x does not move.
    # The vertical bilinear pass of a y-constant image is exact up to float32 rounding.
    x_src = _x_gradient_image(width, height)
    moved = _run(x_src, {"mode": "r", "amount": K}, map_img=map_rgb)
    assert np.allclose(moved, x_src, atol=1e-6)


def test_hue_mode_reads_the_hue_of_the_map() -> None:
    """A red map reads hue 0 and shifts by -k/2; a grey map reads 0.5 and does not."""
    height, width = 32, 128
    src = _x_gradient_image(width, height)
    red = np.zeros((height, width, 3), dtype=np.float32)
    red[:, :, 0] = 1.0
    shifted = _run(src, {"mode": "hue", "amount": K}, map_img=red)
    assert np.array_equal(shifted[0, 40], src[0, 40 - int(K // 2)])
    grey = np.full((height, width), 0.5, dtype=np.float32)
    assert np.array_equal(_run(src, {"mode": "hue", "amount": K}, map_img=grey), src)


def test_every_mode_produces_a_distinct_output() -> None:
    """The five modes read five different fields, so no two agree on one image."""
    img = _noise_image((48, 48))
    outputs = {
        mode: _run(img, {"mode": mode, "map_source": "image", "iterations": 2}) for mode in MODES
    }
    for index, first in enumerate(MODES):
        for second in MODES[index + 1 :]:
            assert not np.array_equal(outputs[first], outputs[second]), (first, second)


def test_three_iterations_smear_further_than_one() -> None:
    """Iterations widen the transition of a hard edge: that is the measured smear."""
    height, width = 64, 192
    src = _edge_image(height, width, 96)
    field = _plateau(width, height, 48.0, 96.0)
    single = _run(src, {"mode": "r", "amount": 24.0, "iterations": 1}, map_img=field)
    triple = _run(src, {"mode": "r", "amount": 24.0, "iterations": 3}, map_img=field)
    spread_one = _edge_spread(single, 32)
    spread_three = _edge_spread(triple, 32)
    assert spread_three > spread_one
    assert spread_three >= _edge_spread(
        _run(src, {"mode": "r", "amount": 24.0, "iterations": 2}, map_img=field), 32
    )


def test_the_smear_grows_with_the_iteration_count() -> None:
    """Edge spread is non-decreasing in iterations and strictly larger at the card value."""
    height, width = 64, 192
    src = _edge_image(height, width, 96)
    field = _plateau(width, height, 48.0, 96.0)
    spreads = [
        _edge_spread(
            _run(
                src,
                {"mode": "r", "amount": 24.0, "iterations": n, "decay": 0.6},
                map_img=field,
            ),
            32,
        )
        for n in (1, 2, 3, 4, 8)
    ]
    assert spreads == sorted(spreads)
    assert spreads[2] > spreads[0]


def test_decay_zero_keeps_only_the_first_pass() -> None:
    """With decay 0 every later pass is weighted out, so iterations stop mattering."""
    img = _noise_image()
    field = _x_ramp(32, 32)
    once = _run(img, {"mode": "r", "amount": 6.0, "iterations": 1}, map_img=field)
    many = _run(img, {"mode": "r", "amount": 6.0, "iterations": 6, "decay": 0.0}, map_img=field)
    assert np.allclose(once, many, atol=1e-6)


def test_a_mask_of_zeros_leaves_the_image_unchanged() -> None:
    """Mask 0 means no effect anywhere, so the source passes through untouched."""
    img = _noise_image()
    mask = np.zeros(img.shape[:2], dtype=np.float32)
    out = _run(img, {"map_source": "noise", "iterations": 3}, mask=mask)
    assert np.array_equal(out, img)


def test_a_mask_of_ones_equals_no_mask() -> None:
    """Mask 1 means full effect everywhere, which is exactly the unmasked result."""
    img = _noise_image()
    mask = np.ones(img.shape[:2], dtype=np.float32)
    unmasked = _run(img, {"map_source": "noise", "iterations": 3}, seed=5)
    masked = _run(img, {"map_source": "noise", "iterations": 3}, seed=5, mask=mask)
    assert np.array_equal(masked, unmasked)


def test_a_half_mask_blends_half_way() -> None:
    """A uniform 0.5 mask returns the midpoint of the source and the displaced image."""
    img = _noise_image()
    mask = np.full(img.shape[:2], 0.5, dtype=np.float32)
    unmasked = _run(img, {"map_source": "noise", "iterations": 2}, seed=3)
    masked = _run(img, {"map_source": "noise", "iterations": 2}, seed=3, mask=mask)
    assert np.allclose(masked, 0.5 * img + 0.5 * unmasked, atol=1e-6)


def test_a_mask_of_the_wrong_size_is_rejected() -> None:
    """A mask that does not match the image is a programming error, not a silent no-op."""
    img = _noise_image((16, 16))
    with pytest.raises(ValueError, match="mask must be"):
        _run(img, {"map_source": "noise"}, mask=np.zeros((8, 8), dtype=np.float32))


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("shape", SHAPES)
def test_output_shape_equals_input_shape_for_every_mode(mode: str, shape: tuple[int, int]) -> None:
    """Every mode on every shape returns the input shape, float32 and contiguous."""
    img = np.random.default_rng(1).random((*shape, 3), dtype=np.float32)
    out = _run(img, {"mode": mode, "map_source": "noise"})
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert out.flags["C_CONTIGUOUS"]
    assert np.isfinite(out).all()
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_sampling_is_bilinear_not_nearest() -> None:
    """A half-pixel shift returns the average of the two neighbours, not one of them."""
    width, height = 9, 8
    src = _x_gradient_image(width, height)
    field = np.full((height, width), 0.625, dtype=np.float32)
    out = _run(src, {"mode": "r", "amount": 4.0}, map_img=field)
    midpoint = 0.5 * (src[0, :-1, 0] + src[0, 1:, 0])
    assert np.allclose(out[0, :-1, 0], midpoint, atol=1e-6)
    assert not np.array_equal(out[0, :-1, 0], src[0, :-1, 0])


def test_edges_clamp() -> None:
    """Coordinates past the border read the border pixel instead of wrapping."""
    width, height = 32, 16
    src = _x_gradient_image(width, height)
    field = np.ones((height, width), dtype=np.float32)
    out = _run(src, {"mode": "r", "amount": K}, map_img=field)
    assert np.array_equal(out[0, -1], src[0, -1])
    assert np.array_equal(out[0, -2], src[0, -1])
    assert np.array_equal(out[0, 0], src[0, int(K // 2)])


def test_the_noise_source_is_seeded_and_seed_dependent() -> None:
    """The noise field is drawn from the generator: same seed equal, other seed not."""
    img = _noise_image()
    first = _run(img, {"map_source": "noise", "iterations": 2}, seed=4)
    again = _run(img, {"map_source": "noise", "iterations": 2}, seed=4)
    other = _run(img, {"map_source": "noise", "iterations": 2}, seed=5)
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)


def test_the_sequence_and_feedback_sources_read_the_supplied_map() -> None:
    """Both external sources consume the same map_img and give the same result."""
    img = _noise_image()
    field = _x_ramp(32, 32)
    sequence = _run(img, {"mode": "r", "map_source": "sequence"}, map_img=field)
    feedback = _run(img, {"mode": "r", "map_source": "feedback"}, map_img=field)
    assert np.array_equal(sequence, feedback)
    assert not np.array_equal(sequence, img)


def test_the_image_source_reads_the_source_itself() -> None:
    """map_source 'image' is the same as passing the source as the map."""
    img = _noise_image()
    implicit = _run(img, {"mode": "g", "map_source": "image", "iterations": 2})
    explicit = _run(img, {"mode": "g", "map_source": "sequence", "iterations": 2}, map_img=img)
    assert np.array_equal(implicit, explicit)


def test_unknown_mode_and_source_are_rejected() -> None:
    """Unknown enumerations raise ValueError naming the offending value."""
    img = _noise_image((8, 8))
    with pytest.raises(ValueError, match="shear"):
        _run(img, {"mode": "shear", "map_source": "noise"})
    with pytest.raises(ValueError, match="webcam"):
        _run(img, {"map_source": "webcam"})


def test_a_missing_or_mismatched_map_is_rejected() -> None:
    """An external source without a map, or with the wrong size, raises ValueError."""
    img = _noise_image((16, 16))
    with pytest.raises(ValueError, match="needs a map"):
        _run(img, {"map_source": "sequence"})
    with pytest.raises(ValueError, match="map must be"):
        _run(img, {"map_source": "sequence"}, map_img=np.zeros((8, 8), dtype=np.float32))


def test_amount_zero_is_the_identity() -> None:
    """A zero amount multiplies the field to nothing, whatever the mode."""
    img = _noise_image()
    for mode in MODES:
        out = _run(img, {"mode": mode, "map_source": "noise", "amount": 0.0})
        assert np.array_equal(out, img), mode


def test_the_effect_does_not_mutate_its_input() -> None:
    """Running the effect leaves the source array and the map untouched."""
    img = _noise_image()
    field = _x_ramp(32, 32)
    before, map_before = img.copy(), field.copy()
    _run(img, {"mode": "r", "map_source": "sequence", "iterations": 3}, map_img=field)
    assert np.array_equal(img, before)
    assert np.array_equal(field, map_before)


def test_a_greyscale_input_comes_back_greyscale() -> None:
    """A 2-D source returns a 2-D image of the same shape."""
    img = np.random.default_rng(2).random((24, 24), dtype=np.float32)
    out = _run(img, {"map_source": "noise", "iterations": 2})
    assert out.shape == img.shape
    assert out.dtype == np.float32
