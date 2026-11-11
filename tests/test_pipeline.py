"""Tests for the render pipeline (T09), using test-only registry entries."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from dithercraft.core import color, pipeline, registry
from dithercraft.core.pipeline import (
    EffectInstance,
    PaletteSpec,
    PipelineSpec,
    render,
    resolve_palette,
)
from dithercraft.core.registry import AlgorithmInfo, EffectInfo
from dithercraft.core.types import ParamSpec

BW = PaletteSpec(source="custom", colors=["#000000", "#FFFFFF"])
GREYS = [f"#{value:02X}{value:02X}{value:02X}" for value in range(256)]


def _algorithm(identifier: str, fn, params: tuple = ()) -> AlgorithmInfo:
    """Build an AlgorithmInfo for a test-only algorithm."""
    return AlgorithmInfo(id=identifier, name=identifier, family="other", params=params, fn=fn)


def _effect(identifier: str, fn, params: tuple = ()) -> EffectInfo:
    """Build an EffectInfo for a test-only effect."""
    return EffectInfo(id=identifier, name=identifier, params=params, fn=fn)


def _nearest(img, palette, params):
    """Test algorithm: plain nearest-colour mapping."""
    return color.nearest_index(img, palette)


def _level(img, palette, params):
    """Test algorithm: index 0 below the level, index 1 above it."""
    return (img[:, :, 0] >= params["level"]).astype(np.int32)


def _invert(img, params, rng):
    """Test effect: invert every channel."""
    return np.ascontiguousarray(1.0 - img, dtype=np.float32)


def _add_half(img, params, rng):
    """Test effect: add 0.5 to every channel."""
    return np.ascontiguousarray(np.clip(img + 0.5, 0.0, 1.0), dtype=np.float32)


def _noise(img, params, rng):
    """Test effect: add a monochrome random field scaled by amount."""
    field = rng.random(img.shape[:2], dtype=np.float32)[:, :, None]
    return np.ascontiguousarray(np.clip(img + field * params["amount"], 0.0, 1.0), dtype=np.float32)


def _constant(value: float):
    """Return a test effect that replaces the image with a constant colour."""

    def effect(img, params, rng):
        return np.full(img.shape, value, dtype=np.float32)

    return effect


@pytest.fixture
def test_registry(monkeypatch):
    """Register test-only algorithms and effects by patching the registry dicts."""
    algorithms = {
        "test_nearest": _algorithm("test_nearest", _nearest),
        "test_level": _algorithm(
            "test_level", _level, (ParamSpec("level", "Level", "float", 0.5, 0.0, 1.0),)
        ),
    }
    effects = {
        "test_invert": _effect("test_invert", _invert),
        "test_add_half": _effect("test_add_half", _add_half),
        "test_noise": _effect(
            "test_noise", _noise, (ParamSpec("amount", "Amount", "float", 1.0, 0.0, 1.0),)
        ),
        "test_black": _effect("test_black", _constant(0.0)),
        "test_white": _effect("test_white", _constant(1.0)),
    }
    for identifier, info in algorithms.items():
        monkeypatch.setitem(registry._ALGORITHMS, identifier, info)
    for identifier, info in effects.items():
        monkeypatch.setitem(registry._EFFECTS, identifier, info)
    return algorithms, effects


def _image(height: int = 37, width: int = 23, seed: int = 7) -> np.ndarray:
    """Return a deterministic random float32 image."""
    rng = np.random.default_rng(seed)
    return np.ascontiguousarray(rng.random((height, width, 3), dtype=np.float32))


def _spec(**overrides) -> PipelineSpec:
    """Build a spec that uses the test-only nearest algorithm and a custom BW palette."""
    base: dict = {"algorithm_id": "test_nearest", "palette": BW}
    base.update(overrides)
    return PipelineSpec(**base)


@pytest.mark.parametrize("pixel_size", [1, 3, 7])
def test_output_shape_and_dtype(test_registry, pixel_size):
    """Output is uint8 RGB with the source shape for every pixel size."""
    out = render(_image(), _spec(pixel_size=pixel_size))
    assert out.dtype == np.uint8
    assert out.shape == (37, 23, 3)


def test_pixel_size_produces_uniform_blocks(test_registry):
    """A pixel size of 3 yields aligned 3x3 blocks of one colour."""
    out = render(_image(), _spec(pixel_size=3))
    for y in range(0, 36, 3):
        for x in range(0, 21, 3):
            block = out[y : y + 3, x : x + 3]
            assert np.array_equal(block, np.broadcast_to(block[0, 0], block.shape))


def test_max_side_reduces_shape(test_registry):
    """max_side shrinks the output and keeps the aspect ratio roughly intact."""
    out = render(_image(), _spec(), max_side=16)
    assert max(out.shape[:2]) <= 16
    assert out.shape[:2] != (37, 23)
    assert out.shape[2] == 3


def test_max_side_keeps_small_images(test_registry):
    """max_side larger than the image leaves the shape untouched."""
    assert render(_image(8, 6), _spec(), max_side=64).shape == (8, 6, 3)


def test_max_side_rejects_zero(test_registry):
    """max_side below 1 is a programming error."""
    with pytest.raises(ValueError):
        render(_image(), _spec(), max_side=0)


def test_disabled_effects_are_skipped(test_registry):
    """A disabled effect changes nothing, an enabled one does."""
    src = _image()
    plain = render(src, _spec())
    disabled = render(src, _spec(pre_effects=[EffectInstance("test_black", enabled=False)]))
    enabled = render(src, _spec(pre_effects=[EffectInstance("test_black")]))
    assert np.array_equal(plain, disabled)
    assert np.all(enabled == 0)


def test_pre_effect_order_matters(test_registry):
    """Two non-commuting pre-effects give different results in the two orders."""
    src = np.full((4, 4, 3), 0.25, dtype=np.float32)
    first = _spec(pre_effects=[EffectInstance("test_invert"), EffectInstance("test_add_half")])
    second = _spec(pre_effects=[EffectInstance("test_add_half"), EffectInstance("test_invert")])
    assert not np.array_equal(render(src, first), render(src, second))


def test_post_effect_order_matters(test_registry):
    """Two non-commuting post-effects give different results in the two orders."""
    src = np.full((4, 4, 3), 0.25, dtype=np.float32)
    first = _spec(post_effects=[EffectInstance("test_invert"), EffectInstance("test_add_half")])
    second = _spec(post_effects=[EffectInstance("test_add_half"), EffectInstance("test_invert")])
    assert not np.array_equal(render(src, first), render(src, second))


def test_same_spec_same_output(test_registry):
    """Rendering the same spec twice is deterministic, noise included."""
    src = _image()
    spec = _spec(
        pre_effects=[EffectInstance("test_noise", {"amount": 0.5})],
        post_effects=[EffectInstance("test_noise", {"amount": 0.2})],
    )
    assert np.array_equal(render(src, spec), render(src, spec))


def test_seed_changes_noise(test_registry):
    """A different spec seed changes the random effects."""
    src = np.zeros((8, 8, 3), dtype=np.float32)
    effects = [EffectInstance("test_noise", {"amount": 1.0})]
    first = render(src, _spec(post_effects=effects, seed=0))
    second = render(src, _spec(post_effects=effects, seed=1))
    assert not np.array_equal(first, second)


def test_pre_effect_rng_is_seeded_with_index(test_registry):
    """Pre-effect i receives default_rng(seed + i)."""
    src = np.zeros((8, 8, 3), dtype=np.float32)
    spec = _spec(
        palette=PaletteSpec(source="custom", colors=GREYS),
        pre_effects=[EffectInstance("test_noise", {"amount": 1.0})],
        seed=0,
    )
    field = np.random.default_rng(0).random((8, 8), dtype=np.float32)[:, :, None]
    expected = color.to_rgb8(np.repeat(field, 3, axis=2))
    assert np.abs(render(src, spec).astype(int) - expected.astype(int)).max() <= 1


def test_post_effect_rng_is_seeded_with_offset(test_registry):
    """Post-effect j receives default_rng(seed + 1000 + j)."""
    src = np.zeros((6, 5, 3), dtype=np.float32)
    spec = _spec(post_effects=[EffectInstance("test_noise", {"amount": 1.0})], seed=0)
    field = np.random.default_rng(1000).random((6, 5), dtype=np.float32)[:, :, None]
    expected = color.to_rgb8(np.repeat(field, 3, axis=2))
    assert np.array_equal(render(src, spec), expected)


def test_brightness_applied_before_dither(test_registry):
    """Extreme brightness values saturate the palette choice."""
    src = _image()
    assert np.all(render(src, _spec(brightness=1.0)) == 255)
    assert np.all(render(src, _spec(brightness=-1.0)) == 0)


def test_pre_effects_run_before_adjust(test_registry):
    """A pre-effect that whitens the image is then darkened by brightness."""
    spec = _spec(pre_effects=[EffectInstance("test_white")], brightness=-1.0)
    assert np.all(render(_image(), spec) == 0)


def test_post_effects_run_last(test_registry):
    """A post-effect that whitens the image wins over the dither result."""
    spec = _spec(post_effects=[EffectInstance("test_white")])
    assert np.all(render(_image(), spec) == 255)


def test_algorithm_params_are_resolved(test_registry):
    """Algorithm params reach the algorithm, clamped to their bounds."""
    src = _image()
    low = render(src, _spec(algorithm_id="test_level", algorithm_params={"level": 0.2}))
    high = render(src, _spec(algorithm_id="test_level", algorithm_params={"level": 0.8}))
    assert (low == 0).mean() < (high == 0).mean()
    clamped = render(src, _spec(algorithm_id="test_level", algorithm_params={"level": 5.0}))
    assert np.all(clamped == 0)


def test_unknown_algorithm_param_raises(test_registry):
    """An unknown algorithm parameter is rejected by resolve_params."""
    with pytest.raises(ValueError):
        render(_image(), _spec(algorithm_params={"bogus": 1}))


def test_render_does_not_mutate_source(test_registry):
    """The source image is left untouched."""
    src = _image()
    before = src.copy()
    render(src, _spec(pre_effects=[EffectInstance("test_invert")], pixel_size=3))
    assert np.array_equal(src, before)


def test_render_rejects_bad_shape(test_registry):
    """A non (H, W, 3) source is rejected."""
    with pytest.raises(ValueError):
        render(np.zeros((4, 4), dtype=np.float32), _spec())


def test_resolve_palette_custom():
    """Custom hex colours become a float32 palette, with or without the hash."""
    palette = resolve_palette(PaletteSpec(source="custom", colors=["#FF0000", "00ff00"]), _image())
    assert palette.dtype == np.float32
    assert palette.shape == (2, 3)
    assert np.allclose(palette, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


@pytest.mark.parametrize("colors", [["#000000"], ["#000000", "#zzzzzz"], ["#000000", "#FFF"]])
def test_resolve_palette_custom_errors(colors):
    """Bad colour counts and bad hex strings raise ValueError."""
    with pytest.raises(ValueError):
        resolve_palette(PaletteSpec(source="custom", colors=colors), _image())


def test_resolve_palette_custom_too_many():
    """More than 256 colours is rejected."""
    with pytest.raises(ValueError):
        resolve_palette(PaletteSpec(source="custom", colors=GREYS + ["#000000"]), _image())


def test_resolve_palette_unknown_source():
    """An unknown palette source raises ValueError."""
    with pytest.raises(ValueError):
        resolve_palette(PaletteSpec(source="bogus"), _image())


def test_resolve_palette_builtin_is_lazy(monkeypatch):
    """The builtin palette module is imported inside resolve_palette, not at import time."""
    fake = types.ModuleType("dithercraft.palettes.builtin")
    fake.get_builtin = lambda name: np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], np.float32)
    monkeypatch.setitem(sys.modules, "dithercraft.palettes.builtin", fake)
    palette = resolve_palette(PaletteSpec(source="builtin", name="bw"), _image())
    assert palette.shape == (2, 3)
    assert "get_builtin" not in vars(pipeline)


def test_resolve_palette_extracted(monkeypatch):
    """The extracted source forwards k and method to the extraction module."""
    calls: dict = {}
    fake = types.ModuleType("dithercraft.palettes.extract")

    def extract_palette(img, k, method, seed=0):
        calls["args"] = (img.shape, k, method)
        return np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], np.float32)

    fake.extract_palette = extract_palette
    monkeypatch.setitem(sys.modules, "dithercraft.palettes.extract", fake)
    spec = PaletteSpec(source="extracted", extract_k=4, extract_method="median_cut")
    palette = resolve_palette(spec, np.zeros((5, 7, 3), dtype=np.float32))
    assert calls["args"] == ((5, 7, 3), 4, "median_cut")
    assert palette.shape == (2, 3)


def test_custom_palette_drives_render(test_registry):
    """A custom palette is used for the final colours."""
    src = np.zeros((4, 4, 3), dtype=np.float32)
    src[:, :, 0] = 0.9
    src[:, :, 1] = 0.1
    src[:, :, 2] = 0.1
    spec = _spec(palette=PaletteSpec(source="custom", colors=["#FF0000", "#00FF00"]))
    out = render(src, spec)
    assert np.all(out == np.array([255, 0, 0], dtype=np.uint8))


def test_extract_palette_receives_the_downscaled_image(test_registry, monkeypatch):
    """Step 5 extracts from the image produced by step 4, not from the source."""
    seen: dict = {}
    fake = types.ModuleType("dithercraft.palettes.extract")

    def extract_palette(img, k, method, seed=0):
        seen["shape"] = img.shape
        return np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], np.float32)

    fake.extract_palette = extract_palette
    monkeypatch.setitem(sys.modules, "dithercraft.palettes.extract", fake)
    spec = _spec(pixel_size=3, palette=PaletteSpec(source="extracted", extract_k=4))
    out = render(_image(), spec)
    assert seen["shape"] == (13, 8, 3)
    assert out.shape == (37, 23, 3)


def test_post_effects_run_after_upscale(test_registry):
    """A per-pixel post-effect is not blocky, so it runs after upscale_nearest."""
    src = np.zeros((9, 9, 3), dtype=np.float32)
    spec = _spec(pixel_size=3, post_effects=[EffectInstance("test_noise", {"amount": 1.0})])
    out = render(src, spec)
    assert out.shape == (9, 9, 3)
    for y in range(0, 9, 3):
        for x in range(0, 9, 3):
            block = out[y : y + 3, x : x + 3]
            assert not np.array_equal(block, np.broadcast_to(block[0, 0], block.shape))


@pytest.mark.parametrize("field", ["pre_effects", "post_effects"])
def test_disabled_effect_does_not_shift_the_seed(test_registry, field):
    """A disabled effect is not counted: the i-th enabled effect keeps its own seed."""
    src = np.zeros((8, 8, 3), dtype=np.float32)
    noise = EffectInstance("test_noise", {"amount": 1.0})
    disabled = EffectInstance("test_noise", {"amount": 1.0}, enabled=False)
    alone = render(src, _spec(**{field: [noise]}))
    shifted = render(src, _spec(**{field: [disabled, noise]}))
    assert np.array_equal(alone, shifted)

