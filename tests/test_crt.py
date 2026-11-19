"""Tests for the CRT / scanlines effect (L18, CONTRACT §17)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from lattice import effects  # noqa: F401  (registers the core effects)
from lattice.effects import crt as crt_module
from lattice.modes.dither import i18n
from lattice.registry import get_effect, list_effects, resolve_params

EFFECT_ID = "crt"
NEUTRAL = {
    "seed": 0,
    "scanline_intensity": 0.0,
    "mask": "none",
    "mask_scale": 6,
    "bloom": 0.0,
    "curvature": 0.0,
    "vignette": 0.0,
    "output_width": 0,
    "roll": 0.0,
}
SHAPES = ((1, 1), (1, 7), (9, 1), (37, 23), (64, 64))
MASK_TYPES = ("slot", "aperture_grille", "shadow_mask")
CATALOGUE = json.loads((Path(i18n.__file__).parent / "en.json").read_text())


def _apply(
    img: np.ndarray,
    overrides: dict | None = None,
    seed: int = 0,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Run the registered effect with resolved parameters and a seeded generator."""
    info = get_effect(EFFECT_ID)
    params = dict(NEUTRAL)
    params.update(overrides or {})
    params["seed"] = seed
    resolved = resolve_params(info.params, params)
    return crt_module.crt(img.copy(), resolved, np.random.default_rng(seed), mask=mask)


def _image(height: int, width: int, value: float | None = None, seed: int = 7) -> np.ndarray:
    """Return a float32 (H, W, 3) image: uniform when value is given, random otherwise."""
    if value is not None:
        return np.full((height, width, 3), value, dtype=np.float32)
    return np.random.default_rng(seed).random((height, width, 3), dtype=np.float32)


def _column_period(out: np.ndarray) -> int:
    """Return the smallest horizontal pixel period of an image, or 0 if none."""
    for period in range(1, out.shape[1] // 2 + 1):
        if np.array_equal(out[:, :-period], out[:, period:]):
            return period
    return 0


def _aggressive() -> dict:
    """Return a non-neutral parameter set exercising every stage."""
    return {
        "scanline_intensity": 0.6,
        "mask": "shadow_mask",
        "mask_scale": 6,
        "bloom": 0.5,
        "curvature": 0.4,
        "vignette": 0.5,
        "output_width": 0,
    }


def test_registers_a_crt_effect_with_catalogue_labels() -> None:
    """The effect is registered with the frozen options and translated labels."""
    info = get_effect(EFFECT_ID)
    assert info.id == EFFECT_ID
    assert info.name == "CRT / scanlines"
    assert [spec.id for spec in info.params] == list(NEUTRAL)
    labels = {spec.label for spec in info.params}
    assert labels <= set(CATALOGUE), sorted(labels - set(CATALOGUE))
    assert EFFECT_ID in {registered.id for registered in list_effects()}


@pytest.mark.parametrize("shape", SHAPES)
def test_all_parameters_neutral_return_the_input(shape: tuple[int, int]) -> None:
    """A fully neutral parameter set is the identity within 1/255."""
    img = _image(*shape)
    out = _apply(img)
    assert out.shape == img.shape
    assert np.allclose(out, img, atol=1.0 / 255.0)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("overrides", (NEUTRAL, "aggressive"))
def test_output_shape_equals_input_shape(
    shape: tuple[int, int], overrides: dict | str
) -> None:
    """Every configuration preserves shape, float32 dtype and the [0, 1] range."""
    img = _image(*shape)
    settings = _aggressive() if overrides == "aggressive" else dict(NEUTRAL)
    out = _apply(img, settings)
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_effect_does_not_mutate_its_input() -> None:
    """Even with an external mask, the input array is left untouched."""
    img = _image(32, 40)
    before = img.copy()
    mask = np.linspace(0.0, 1.0, 32 * 40, dtype=np.float32).reshape(32, 40)
    _apply(img, _aggressive(), mask=mask)
    assert np.array_equal(img, before)


def test_deterministic_seed() -> None:
    """Repeated seeded calls agree, whatever the state of the supplied generator."""
    img = _image(24, 28)
    first = _apply(img, _aggressive(), seed=3)
    second = _apply(img, _aggressive(), seed=3)
    assert np.array_equal(first, second)
    direct = crt_module.crt(
        img,
        resolve_params(get_effect(EFFECT_ID).params, {**NEUTRAL, **_aggressive()}),
        np.random.default_rng(999),
    )
    assert np.array_equal(first, direct)


@pytest.mark.parametrize("kind", MASK_TYPES)
@pytest.mark.parametrize("pitch", (3, 6, 12))
def test_mask_period_in_output_pixels_equals_mask_scale(kind: str, pitch: int) -> None:
    """Each phosphor layout repeats every `mask_scale` device pixels."""
    img = _image(48, 96, value=1.0)
    out = _apply(img, {"mask": kind, "mask_scale": pitch, "output_width": 0})
    assert _column_period(out) == pitch
    assert not np.array_equal(out, img)  # the phosphor stage is effective


def test_doubling_output_resolution_doubles_the_pixel_period() -> None:
    """Twice the device resolution doubles the pixel pitch, not the visual pitch."""
    img = _image(48, 96, value=1.0)
    settings = {"mask": "slot", "mask_scale": 6}
    low = _apply(img, {**settings, "output_width": 96})
    high = _apply(img, {**settings, "output_width": 192})
    low_period, high_period = _column_period(low), _column_period(high)
    assert (low_period, high_period) == (6, 12)
    # Visual pitch, in image pixels: period_px * image_width / device_width.
    assert low_period * 96 / 96 == high_period * 96 / 192 == 6.0
    # The number of phosphor groups across the device screen is unchanged.
    assert 96 / low_period == 192 / high_period == 16.0


def test_doubling_resolution_for_each_mask_type() -> None:
    """The device-pixel rule holds for aperture grille and shadow mask too."""
    img = _image(36, 96, value=1.0)
    for kind in MASK_TYPES:
        low = _apply(img, {"mask": kind, "mask_scale": 4, "output_width": 96})
        high = _apply(img, {"mask": kind, "mask_scale": 4, "output_width": 192})
        assert _column_period(high) == 2 * _column_period(low) == 8


def test_curvature_zero_leaves_corners_untouched() -> None:
    """At zero curvature the image, corners included, is unchanged."""
    img = _image(40, 60)
    out = _apply(img, {"curvature": 0.0})
    assert np.array_equal(out, img)


def test_positive_curvature_darkens_corners() -> None:
    """A curved tube attenuates the corners more than the centre."""
    img = _image(40, 60, value=1.0)
    out = _apply(img, {"curvature": 0.6})
    corner = out[:4, :4].mean()
    centre = out[18:22, 28:32].mean()
    assert corner < img[:4, :4].mean()
    assert corner < centre


def test_vignette_darkens_edges_but_not_the_centre() -> None:
    """Vignette is a separate radial falloff, neutral at zero."""
    img = _image(40, 60, value=1.0)
    out = _apply(img, {"vignette": 0.8})
    assert np.array_equal(_apply(img, {"vignette": 0.0}), img)
    assert out[:3, :3].mean() < out[18:22, 28:32].mean()


def test_mask_is_keyword_only_and_rejects_wrong_shapes() -> None:
    """DEV-214: the external mask is keyword-only and size-checked."""
    info = get_effect(EFFECT_ID)
    params = resolve_params(info.params, dict(NEUTRAL))
    img = _image(12, 16)
    with pytest.raises(TypeError):
        info.fn(img, params, np.random.default_rng(0), np.ones((12, 16)))  # type: ignore[misc]
    with pytest.raises(ValueError, match=r"mask must be \(12, 16\)"):
        _apply(img, _aggressive(), mask=np.ones((4, 4), dtype=np.float32))
    with pytest.raises(ValueError, match=r"mask must be \(12, 16\)"):
        _apply(img, _aggressive(), mask=np.ones((12, 16, 3), dtype=np.float32))


def test_external_mask_blends_between_input_and_full_effect() -> None:
    """§18: a coverage of 0 is no effect, 1 is full effect, both shapes accepted."""
    img = _image(24, 32)
    settings = _aggressive()
    full = _apply(img, settings)
    zeros = np.zeros((24, 32, 1), dtype=np.float32)
    ones = np.ones((24, 32), dtype=np.float32)
    assert np.allclose(_apply(img, settings, mask=zeros), img, atol=1e-6)
    assert np.allclose(_apply(img, settings, mask=ones), full, atol=1e-6)
    half = np.full((24, 32), 0.5, dtype=np.float32)
    assert np.allclose(
        _apply(img, settings, mask=half), 0.5 * img + 0.5 * full, atol=1e-6
    )


def test_array_mask_in_params_channel_is_rejected() -> None:
    """DEV-214: an array cannot be smuggled into the `mask` choice parameter."""
    info = get_effect(EFFECT_ID)
    img = _image(8, 8)
    with pytest.raises(ValueError, match="unknown CRT mask"):
        info.fn(img, {**NEUTRAL, "mask": np.ones((8, 8))}, np.random.default_rng(0))


def test_curvature_zero_with_mask_is_bit_identical() -> None:
    """G7: with curvature and vignette off, the frozen masked path is bit-identical.

    Digest captured from HEAD before the phosphor/curvature order change. This is the
    frozen Dither 1.1 preset path: any drift in the neutral-curvature chain breaks it.
    """
    img = np.random.default_rng(7).random((32, 48, 3), dtype=np.float32)
    settings = {
        "bloom": 0.3,
        "scanline_intensity": 0.45,
        "mask": "aperture_grille",
        "mask_scale": 6,
        "curvature": 0.0,
        "vignette": 0.0,
    }
    out = _apply(img, settings, seed=7)
    assert out.dtype == np.float32
    assert out.shape == img.shape
    assert hashlib.sha256(out.tobytes()).hexdigest() == (
        "521ebf6afedc51acc2d10a3d5ea8dea74409444a2600495a925337b3e92190a0"
    )


def test_phosphor_after_curvature_avoids_border_colour_bands() -> None:
    """L24: curved screen edges must not clamp the mask into solid red/blue bands.

    With the mask applied before curvature, clamping stretches mask column 0 (red)
    and the last one (blue) into full-height colour casts. After the fix the stripes
    follow screen space, so both edge strips stay near colour-neutral.
    """
    img = np.full((120, 160, 3), 0.9, dtype=np.float32)
    settings = {
        "bloom": 0.3,
        "scanline_intensity": 0.45,
        "mask": "aperture_grille",
        "mask_scale": 6,
        "curvature": 0.2,
        "vignette": 0.35,
    }
    out = _apply(img, settings)
    span = float(out.max() - out.min())
    assert span > 0.0
    for strip in (out[:, :8, :], out[:, -8:, :]):
        mean = strip.mean(axis=(0, 1))
        # A solid red/blue band has a large spread between channel means.
        assert float(mean.max() - mean.min()) < 0.15 * span
        # H13b: the border is now the BLACK tube surround (no clamped smear), so a
        # column is either empty (the CRT silhouette) or still carrying detail.
        for column in range(strip.shape[1]):
            variance = float(strip[:, column, :].var())
            assert variance > 0.01 * span * span or variance == 0.0


def test_roll_scrolls_the_beam_without_moving_the_geometry() -> None:
    """The one temporal knob: the scanlines scroll while the tube silhouette stays put.

    Animating `curvature` was rejected — the whole picture swelled and shrank like a
    zoom, "aucun tube ne fait ça". `roll` moves the beam phase instead: the usable surface
    must stay identical (his threshold is 2%) while consecutive frames differ.
    """
    img = np.linspace(0.0, 1.0, 64 * 64 * 3, dtype=np.float32).reshape(64, 64, 3)
    base = {"scanline_intensity": 0.4, "mask": "slot", "mask_scale": 4, "curvature": 0.15,
            "vignette": 0.2, "output_width": 0}
    frames = [_apply(img, {**base, "roll": phase}) for phase in (0.0, 1.5, 3.0)]
    surfaces = [float((frame.max(axis=2) > 0.02).mean()) for frame in frames]
    assert max(surfaces) - min(surfaces) < 0.02  # the tube silhouette does not move
    assert all(not np.array_equal(frames[i], frames[i + 1]) for i in range(2))


def test_roll_zero_is_the_neutral_phase() -> None:
    """roll = 0 must leave the historical beam exactly where it was."""
    img = np.full((16, 16, 3), 0.5, dtype=np.float32)
    base = {"scanline_intensity": 0.5}
    assert np.array_equal(_apply(img, base), _apply(img, {**base, "roll": 0.0}))
