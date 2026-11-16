"""Tests for the render pipeline (T09 and §3/§5 L2b), using test-only registry entries."""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager

import numpy as np
import pytest

import lattice_core.cell as cell_module
import lattice_core.pipeline as pipeline
from lattice_core import color, registry
from lattice_core.cell import RenderStyle, register_renderer
from lattice_core.pipeline import (
    POST_EFFECT_SEED_OFFSET,
    EffectInstance,
    PaletteSpec,
    PipelineSpec,
    _coverage_table,
    prepare_image,
    render,
    render_with_palette,
    resolve_palette,
)
from lattice_core.registry import AlgorithmInfo, EffectInfo
from lattice_core.types import ParamSpec

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


@pytest.fixture(autouse=True)
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
    fake = types.ModuleType("lattice_core.palettes.builtin")
    fake.get_builtin = lambda name: np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], np.float32)
    monkeypatch.setitem(sys.modules, "lattice_core.palettes.builtin", fake)
    palette = resolve_palette(PaletteSpec(source="builtin", name="bw"), _image())
    assert palette.shape == (2, 3)
    assert "get_builtin" not in vars(pipeline)


def test_resolve_palette_extracted(monkeypatch):
    """The extracted source forwards k and method to the extraction module."""
    calls: dict = {}
    fake = types.ModuleType("lattice_core.palettes.extract")

    def extract_palette(img, k, method, seed=0):
        calls["args"] = (img.shape, k, method)
        return np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], np.float32)

    fake.extract_palette = extract_palette
    fake.MIN_K, fake.MAX_K = 2, 32
    monkeypatch.setitem(sys.modules, "lattice_core.palettes.extract", fake)
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
    fake = types.ModuleType("lattice_core.palettes.extract")

    def extract_palette(img, k, method, seed=0):
        seen["shape"] = img.shape
        return np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], np.float32)

    fake.extract_palette = extract_palette
    fake.MIN_K, fake.MAX_K = 2, 32
    monkeypatch.setitem(sys.modules, "lattice_core.palettes.extract", fake)
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


# ---------------------------------------------------------------------------
# L2b (§3/§5 H11): continuous mode, sub-points, geometry, stencil, render_frame
# ---------------------------------------------------------------------------

BW_FLOAT = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)


def _bw_palette() -> np.ndarray:
    """The BW palette as the float32 array the renderer receives."""
    return BW_FLOAT.copy()


class _Stub:
    """Configurable stub renderer for the pipeline tests, recording every grid."""

    def __init__(self, name, aspect=1.0, subgrid=(1, 1), points=None,
                 forbid=False, bad_frame=False):
        self.name = name
        self._aspect, self._subgrid = aspect, subgrid
        self._points, self._forbid = points, forbid
        self._bad_frame = bad_frame
        self.calls, self.grid, self.style = 0, None, None
        if points is not None:
            self.sample_points = self._sample_points
        if forbid or bad_frame:
            self.render_frame = self._render_frame

    def _sample_points(self):
        return list(self._points)

    def _render_frame(self, grid, palette, style):
        if self._forbid:
            raise AssertionError(f"{self.name}.render_frame called")
        return np.zeros((1, 1, 3), dtype=np.float32)

    def cell_aspect(self):
        return self._aspect

    def subgrid(self):
        return self._subgrid

    def consumes(self):
        return frozenset({"index"})

    def render(self, grid, palette, style):
        if self._forbid:
            raise AssertionError(f"{self.name}.render called")
        self.calls += 1
        self.grid = grid
        self.style = style
        blank = np.zeros((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3), dtype=np.uint8)
        return color.to_pil(blank)


@contextmanager
def _registered(renderer):
    """Register a stub renderer for the block, then unregister it."""
    register_renderer(renderer)
    try:
        yield
    finally:
        cell_module._RENDERERS.pop(renderer.name, None)


def _luma(img: np.ndarray) -> np.ndarray:
    """Linear-light luminance of a float32 image, as the pipeline computes it."""
    linear = color.srgb_to_linear(img)
    return (0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1]
            + 0.0722 * linear[:, :, 2]).astype(np.float32)


def _render_grid(aspect, src, pixel_size, subgrid=(1, 1), points=None):
    """Render src through a stub renderer of the given aspect and return its grid."""
    spy = _Stub(f"geom_{aspect}_{subgrid}_{pixel_size}", aspect=aspect, subgrid=subgrid,
                points=points)
    with _registered(spy):
        render_with_palette(src, _spec(pixel_size=pixel_size), _bw_palette(), renderer=spy.name)
    return spy.grid


def test_continuous_mode_matches_step5_to_post():
    """Continuous mode sends the step-5 image straight to the post-effects, bit for bit."""
    src = _image(24, 20)
    spec = PipelineSpec(algorithm_id=None, palette=None)
    work = prepare_image(src, spec)
    assert np.array_equal(render(src, spec), color.to_rgb8(work))
    noisy = PipelineSpec(
        algorithm_id=None, palette=None,
        post_effects=[EffectInstance("test_noise", {"amount": 1.0})],
    )
    rng = np.random.default_rng(POST_EFFECT_SEED_OFFSET)
    field = rng.random(work.shape[:2], dtype=np.float32)[:, :, None]
    expected = color.to_rgb8(np.clip(work + field, 0.0, 1.0))
    assert np.array_equal(render(src, noisy), expected)


def test_continuous_mode_calls_no_renderer_and_builds_no_grid(monkeypatch):
    """No CellGrid is built and no renderer is called when algorithm and palette are null."""
    built = []
    monkeypatch.setattr(pipeline, "CellGrid", lambda *a, **k: built.append(k))
    with _registered(_Stub("never", forbid=True)):
        out = render(_image(16, 16),
                     PipelineSpec(algorithm_id=None, palette=None, renderer="never"))
    assert built == []
    assert out.shape == (16, 16, 3)


@pytest.mark.parametrize("kw", [{"algorithm_id": None}, {"palette": None}])
def test_half_null_spec_is_rejected_by_both_entry_points(kw):
    """prepare_image and render both reject a half-null spec with the same ValueError."""
    spec = PipelineSpec(**kw)
    with pytest.raises(ValueError, match="continuous mode"):
        render(_image(), spec)
    with pytest.raises(ValueError, match="continuous mode"):
        prepare_image(_image(), spec)


def test_spec_renderer_and_style_reach_the_pipeline():
    """PipelineSpec.renderer and renderer_style are propagated to the renderer."""
    spy = _Stub("spec_renderer")
    with _registered(spy):
        out = render(_image(16, 16),
                     _spec(pixel_size=2, renderer="spec_renderer", renderer_style={"scale": 2}))
    assert out.shape == (16, 16, 3)
    assert spy.calls == 1 and (spy.grid.cell_w, spy.grid.cell_h) == (2, 2)
    assert spy.style.options == {"scale": 2}


def test_explicit_renderer_argument_overrides_the_spec():
    """The renderer keyword argument wins over PipelineSpec.renderer."""
    spy = _Stub("explicit_renderer")
    with _registered(spy):
        render(_image(12, 12), _spec(renderer="pixel"), renderer="explicit_renderer")
    assert spy.calls == 1


@pytest.mark.parametrize(
    "overrides,exc_type,match",
    [({"renderer": "nope"}, KeyError, "nope"),
     ({"renderer_style": {"x": object()}}, ValueError, "render style")],
)
def test_invalid_renderer_spec_raises(overrides, exc_type, match):
    """An unknown renderer name is a KeyError; a non-JSON style is a ValueError."""
    with pytest.raises(exc_type) as exc:
        render(_image(), _spec(**overrides))
    assert match in str(exc.value)


def test_subindices_have_the_subgrid_shape_and_dtype():
    """A (2, 3) subgrid fills subindex with (rows, cols, 6) int32."""
    grid = _render_grid(1.0, _image(16, 20), 2, subgrid=(2, 3))
    assert grid.subindex is not None
    assert grid.subindex.shape == (grid.rows, grid.cols, 6)
    assert grid.subindex.dtype == np.int32


def test_subindices_carry_detail_from_inside_the_cell():
    """A horizontal edge inside one cell gives different sub-indices on its two rows."""
    src = np.zeros((8, 8, 3), dtype=np.float32)
    src[2:] = 1.0
    grid = _render_grid(1.0, src, 4, subgrid=(1, 2))
    assert grid.subindex.shape == (2, 2, 2)
    top, bottom = grid.subindex[0, 0]
    assert top != bottom, "sub-points of one cell must not all share one index"


def test_subpoint_coverage_is_monotone_along_a_source_ramp():
    """Sub-point coverage rises along x on a ramp, including inside a single cell."""
    palette = np.array([[v / 255.0] * 3 for v in range(256)], dtype=np.float32)
    ramp = np.repeat(np.linspace(0.0, 1.0, 20, dtype=np.float32)[None, :, None], 8, axis=0)
    src = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
    spy = _Stub("sub_mono", subgrid=(2, 3))
    with _registered(spy):
        render_with_palette(src, _spec(pixel_size=2), palette, renderer="sub_mono")
    grid = spy.grid
    flat = grid.subindex.reshape(grid.rows, grid.cols, 3, 2).transpose(0, 2, 1, 3)
    covers = _coverage_table(palette)[flat.reshape(grid.rows * 3, grid.cols * 2)]
    assert np.all(np.diff(covers, axis=1) >= 0), "coverage must not fall along the ramp"
    inside = np.diff(covers.reshape(grid.rows * 3, grid.cols, 2), axis=2)
    assert np.any(inside > 0), "the two sub-points of a cell must resolve the ramp"


def test_no_subindex_when_subgrid_is_one():
    """A (1, 1) renderer receives subindex None."""
    spy = _Stub("no_sub")
    with _registered(spy):
        render_with_palette(_image(16, 16), _spec(pixel_size=2), _bw_palette(), renderer="no_sub")
    assert spy.grid.subindex is None


def test_sample_points_count_and_positions_are_respected():
    """An explicit sample_points() stencil sets k and the sampled source positions."""
    points = [(0.25, 0.25), (0.75, 0.75)]
    src = np.zeros((8, 8, 3), dtype=np.float32)
    src[0, 0] = 1.0
    src[1, 1] = 0.5
    spy = _Stub("stencil_pos", points=points)
    with _registered(spy):
        render_with_palette(src, _spec(pixel_size=2), _bw_palette(), renderer="stencil_pos")
    lum = _luma(src)
    assert spy.grid.samples.shape == (4, 4, 2)
    assert spy.grid.samples[0, 0, 0] == pytest.approx(lum[0, 0], abs=1e-6)
    assert spy.grid.samples[0, 0, 1] == pytest.approx(lum[1, 1], abs=1e-6)


def test_stencil_positions_include_the_cell_origin():
    """Cell (1, 2) samples inside its own cell, not at the top-left of the image."""
    src = np.zeros((8, 8, 3), dtype=np.float32)
    src[2, 4] = 1.0
    spy = _Stub("stencil_origin", points=[(0.25, 0.25)])
    with _registered(spy):
        render_with_palette(src, _spec(pixel_size=2), _bw_palette(), renderer="stencil_origin")
    lum = _luma(src)
    samples = spy.grid.samples
    assert samples.shape == (4, 4, 1)
    assert samples[1, 2, 0] == pytest.approx(lum[2, 4], abs=1e-6)
    assert samples[1, 2, 0] > 0.0
    assert samples[0, 0, 0] == pytest.approx(0.0, abs=1e-6)


def test_default_stencil_is_the_cell_mean_luma_for_a_pixel_renderer():
    """Without sample_points() and subgrid (1, 1), samples hold the source cell mean luma."""
    src = np.zeros((9, 9, 3), dtype=np.float32)
    src[1, 1] = 1.0
    spy = _Stub("stencil_default")
    with _registered(spy):
        render_with_palette(src, _spec(pixel_size=3), _bw_palette(), renderer="stencil_default")
    cells = prepare_image(src, _spec(pixel_size=3))
    assert spy.grid.samples.shape == (3, 3, 1)
    assert spy.grid.samples[0, 0, 0] == pytest.approx(_luma(cells)[0, 0], abs=1e-6)


def test_default_stencil_for_a_subgrid_renderer_is_the_uniform_sx_by_sy_grid():
    """Without sample_points(), a (2, 3) renderer gets k = 6 points at the sub-point centres."""
    src = np.zeros((12, 12, 3), dtype=np.float32)
    src[:, 0] = 1.0
    spy = _Stub("stencil_uniform", subgrid=(2, 3))
    with _registered(spy):
        render_with_palette(src, _spec(pixel_size=2), _bw_palette(), renderer="stencil_uniform")
    samples = spy.grid.samples
    assert samples.shape == (spy.grid.rows, spy.grid.cols, 6)
    left, right = samples[0, 0, ::2], samples[0, 0, 1::2]
    assert np.allclose(left, 1.0, atol=1e-6), "the left sub-points sit on the white column"
    assert np.allclose(right, 0.0, atol=1e-6), "the right sub-points sit on the black columns"


@pytest.mark.parametrize(
    "aspect,pixel_size,expected",
    [(0.5, 4, (2, 4)), (2.0, 4, (4, 2)), (0.5, 1, (1, 1)), (2.0, 1, (1, 1)), (1.0, 3, (3, 3))],
)
def test_geometry_follows_the_h11_rule(aspect, pixel_size, expected):
    """cell_w/cell_h follow the §5 step-6 rule and the grid preserves the source aspect."""
    src = np.full((20, 30, 3), 0.5, dtype=np.float32)
    grid = _render_grid(aspect, src, pixel_size)
    assert (grid.cell_w, grid.cell_h) == expected
    ratio = (grid.cols * grid.cell_w) / (grid.rows * grid.cell_h)
    assert ratio == pytest.approx(30 / 20, rel=0.1)


def test_render_frame_wrong_shape_is_a_typed_error():
    """A render_frame of the wrong shape raises ValueError, not an IndexError."""
    with _registered(_Stub("bad_frame", bad_frame=True)):
        with pytest.raises(ValueError, match="render_frame returned shape"):
            render_with_palette(_image(16, 16), _spec(pixel_size=2), _bw_palette(),
                                renderer="bad_frame")


def test_style_stores_a_copy_of_the_caller_options():
    """Mutating the caller dict after construction does not change the style."""
    options = {"scale": 1, "fg": "#ffffff"}
    style = RenderStyle(options=options)
    options["scale"] = 99
    assert style.options == {"scale": 1, "fg": "#ffffff"}
    assert json.loads(json.dumps(dict(style.options))) == style.options


@pytest.mark.parametrize("pixel_size", [1, 2, 3, 5])
@pytest.mark.parametrize("palette_id", range(5))
def test_pixel_renderer_matches_the_frozen_1_0_path(pixel_size, palette_id):
    """pixel reproduces downscale → nearest_index → apply_palette → upscale_nearest exactly."""
    rng = np.random.default_rng(1000 + palette_id)
    src = np.ascontiguousarray(rng.random((37, 23, 3), dtype=np.float32))
    palette = np.ascontiguousarray(rng.random((4 + palette_id, 3), dtype=np.float32))
    cells = color.downscale(src, pixel_size)
    idx = color.nearest_index(cells, palette)
    want = color.upscale_nearest(color.apply_palette(idx, palette), pixel_size, (37, 23))
    spec = _spec(pixel_size=pixel_size, palette=PaletteSpec(source="custom", colors=GREYS[:4]))
    assert np.array_equal(render_with_palette(src, spec, palette), color.to_rgb8(want))


def test_pixel_renderer_matches_twenty_random_images_and_five_palettes():
    """20 seeded images x 5 float palettes stay bit-identical to the 1.0 render path."""
    rng = np.random.default_rng(4242)
    palettes = [np.ascontiguousarray(rng.random((k, 3), dtype=np.float32))
                for k in (2, 3, 5, 8, 16)]
    for index in range(20):
        height, width = 11 + index, 7 + index * 2
        src = np.ascontiguousarray(rng.random((height, width, 3), dtype=np.float32))
        for pixel_size in (1, 3):
            cells = color.downscale(src, pixel_size)
            for palette in palettes:
                idx = color.nearest_index(cells, palette)
                want = color.upscale_nearest(color.apply_palette(idx, palette), pixel_size,
                                             (height, width))
                spec = _spec(pixel_size=pixel_size)
                got = render_with_palette(src, spec, palette)
                assert np.array_equal(got, color.to_rgb8(want))
