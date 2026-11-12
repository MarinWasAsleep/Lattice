"""Tests for the 1.1 pre-dither conditioning steps (CONTRACT §13)."""

from __future__ import annotations

import numpy as np
import pytest

import lattice_dither.algorithms  # noqa: F401
import lattice_dither.effects  # noqa: F401
from lattice_dither.core import color
from lattice_dither.core.pipeline import PaletteSpec, PipelineSpec, render, resolve_palette


def _image(height: int = 37, width: int = 23, seed: int = 7) -> np.ndarray:
    """Return a deterministic random float32 image."""
    rng = np.random.default_rng(seed)
    return np.ascontiguousarray(rng.random((height, width, 3), dtype=np.float32))


def _spec(**overrides) -> PipelineSpec:
    """Build a spec that uses the real nearest-colour algorithm and a BW palette."""
    base: dict = {
        "algorithm_id": "threshold",
        "palette": PaletteSpec(source="custom", colors=["#000000", "#FFFFFF"]),
    }
    base.update(overrides)
    return PipelineSpec(**base)

def test_saturation_minus_one_makes_every_pixel_grey():
    """saturation = -1 collapses every pixel to its luminance, exactly."""
    src = _image()
    out = color.adjust(src, 0.0, 0.0, 1.0, -1.0)
    assert np.array_equal(out[:, :, 0], out[:, :, 1])
    assert np.array_equal(out[:, :, 1], out[:, :, 2])


def test_saturation_leaves_grey_untouched():
    """A grey image is unchanged by any saturation, because its chroma is zero."""
    grey = np.repeat(np.linspace(0.0, 1.0, 16, dtype=np.float32)[None, :, None], 8, axis=0)
    grey = np.ascontiguousarray(np.repeat(grey, 3, axis=2))
    for saturation in (-1.0, -0.5, 0.5, 1.0):
        assert np.allclose(color.adjust(grey, 0.0, 0.0, 1.0, saturation), grey, atol=1e-6)


def test_positive_saturation_increases_channel_spread():
    """saturation = 1 pushes the channels further apart on a coloured image."""
    src = _image()
    plain = color.adjust(src, 0.0, 0.0, 1.0, 0.0)
    vivid = color.adjust(src, 0.0, 0.0, 1.0, 1.0)
    assert (vivid.max(axis=2) - vivid.min(axis=2)).mean() > (
        plain.max(axis=2) - plain.min(axis=2)
    ).mean()


def test_saturation_zero_is_the_identity():
    """The default saturation reproduces the pre-1.1 adjust exactly."""
    src = _image()
    assert np.array_equal(color.adjust(src, 0.1, -0.2, 1.5), color.adjust(src, 0.1, -0.2, 1.5, 0.0))


def test_auto_levels_stretches_a_ramp():
    """A 0.2..0.8 ramp is stretched to 0..1 within 1/255."""
    ramp = np.linspace(0.2, 0.8, 64, dtype=np.float32)
    img = np.ascontiguousarray(np.repeat(np.repeat(ramp[None, :, None], 8, axis=0), 3, axis=2))
    out = color.auto_levels(img)
    assert abs(float(out.min()) - 0.0) <= 1.0 / 255.0
    assert abs(float(out.max()) - 1.0) <= 1.0 / 255.0


def test_auto_levels_leaves_a_flat_channel_alone():
    """A channel with no range is not divided by zero."""
    img = np.full((4, 4, 3), 0.5, dtype=np.float32)
    assert np.allclose(color.auto_levels(img), img)


def test_pre_blur_preserves_the_mean_and_is_a_no_op_at_zero():
    """Blurring keeps the average brightness; sigma 0 returns the input unchanged."""
    src = _image(64, 64)
    assert np.array_equal(color.gaussian_blur(src, 0.0), src)
    blurred = color.gaussian_blur(src, 2.0)
    assert abs(float(blurred.mean()) - float(src.mean())) < 1e-3
    assert blurred.shape == src.shape


def test_pre_blur_reduces_local_variance():
    """Blurring a noisy image lowers its pixel-to-pixel variance."""
    src = _image(64, 64)
    blurred = color.gaussian_blur(src, 3.0)
    assert float(blurred.var()) < float(src.var())


def test_conditioning_defaults_reproduce_the_plain_render():
    """The three new steps are no-ops at their defaults."""
    src = _image()
    plain = render(src, _spec())
    conditioned = render(
        src, _spec(saturation=0.0, pre_blur=0.0, auto_levels=False, color_metric="srgb")
    )
    assert np.array_equal(plain, conditioned)


def test_auto_levels_runs_before_adjust():
    """auto_levels is step 3, so brightness still applies afterwards."""
    src = np.full((8, 8, 3), 0.4, dtype=np.float32)
    spec = _spec(auto_levels=True, brightness=-1.0)
    assert np.all(render(src, spec) == 0)


def test_pre_blur_runs_before_downscale():
    """pre_blur is step 5, so a pixel_size of 3 still yields uniform blocks."""
    out = render(_image(30, 30), _spec(pre_blur=6.0, pixel_size=3))
    for y in range(0, 30, 3):
        for x in range(0, 30, 3):
            block = out[y : y + 3, x : x + 3]
            assert np.array_equal(block, np.broadcast_to(block[0, 0], block.shape))


def test_palette_order_must_be_a_permutation():
    """A repeated index, an out-of-range index and a short order are all rejected."""
    img = _image()
    bw = ["#000000", "#FFFFFF"]
    with pytest.raises(ValueError, match="repeated"):
        resolve_palette(PaletteSpec(source="custom", colors=bw, order=[0, 0]), img)
    with pytest.raises(ValueError, match="outside"):
        resolve_palette(PaletteSpec(source="custom", colors=bw, order=[0, 2]), img)
    with pytest.raises(ValueError, match="missing"):
        resolve_palette(PaletteSpec(source="custom", colors=bw, order=[0]), img)


def test_palette_order_does_not_change_the_palette():
    """A valid order is accepted and leaves the rendered palette untouched."""
    img = _image()
    plain = resolve_palette(PaletteSpec(source="custom", colors=["#000000", "#FFFFFF"]), img)
    ordered = resolve_palette(
        PaletteSpec(source="custom", colors=["#000000", "#FFFFFF"], order=[1, 0]), img
    )
    assert np.array_equal(plain, ordered)


def test_locked_beyond_extract_k_raises():
    """More locked colours than extract_k is rejected before extraction runs."""
    spec = PaletteSpec(source="extracted", extract_k=4, locked=[0, 1, 2, 3, 4])
    with pytest.raises(ValueError, match="locked"):
        resolve_palette(spec, _image())
