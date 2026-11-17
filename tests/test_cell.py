"""Tests for the CellRenderer contract (§3) and the PixelRenderer."""

from __future__ import annotations

import json

import numpy as np
import pytest

import lattice_core.cell as cell_module
import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
import lattice_core.effects  # noqa: F401  (registers the effects the pipeline resolves)
from lattice_core import color
from lattice_core.cell import (
    CellGrid,
    CellRenderer,
    RenderStyle,
    get_renderer,
    list_renderers,
    register_renderer,
)
from lattice_core.palettes.extract import extract_palette
from lattice_core.pipeline import (
    MAX_PIXEL_SIZE,
    MIN_PIXEL_SIZE,
    POST_EFFECT_SEED_OFFSET,
    EffectInstance,
    PipelineSpec,
    _coverage_table,
    _make_grid,
    render_with_palette,
)
from lattice_core.registry import get_algorithm, get_effect, resolve_params
from lattice_core.renderers.pixel import PixelRenderer
from lattice_core.types import Image, Palette

BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
GREY_PALETTE: Palette = np.array([[v / 255.0] * 3 for v in (0, 85, 170, 255)], dtype=np.float32)
PRIMARY: Palette = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
FLOAT_PALETTE: Palette = np.array(
    [[0.2, 0.4, 0.6], [0.9, 0.1, 0.3], [0.05, 0.77, 0.13]], dtype=np.float32
)


def _grid(rows: int = 3, cols: int = 4, cell: int = 2, index: np.ndarray | None = None) -> CellGrid:
    """Build a deterministic CellGrid with the given geometry."""
    if index is None:
        index = np.arange(rows * cols, dtype=np.int32).reshape(rows, cols) % 2
    luma = np.full((rows, cols), 0.5, dtype=np.float32)
    return CellGrid(
        cols=cols,
        rows=rows,
        cell_w=cell,
        cell_h=cell,
        index=index,
        coverage=np.full((rows, cols), 0.5, dtype=np.float32),
        luma=luma,
        samples=luma[:, :, None].copy(),
    )


def _style(options: dict | None = None) -> RenderStyle:
    """Return a RenderStyle carrying options, defaulting to {"scale": 1}."""
    return RenderStyle(options=options or {"scale": 1})


# --- The frozen 1.0 reference: apply_palette + upscale_nearest + effects + to_rgb8 ---


def _legacy_effects(img: Image, instances: list, seed: int, offset: int) -> Image:
    """Replay the 1.0 post/pre-effect loop: seed + offset + i per enabled effect."""
    out = img
    index = 0
    for instance in instances:
        if not instance.enabled:
            continue
        info = get_effect(instance.effect_id)
        params = resolve_params(info.params, instance.params)
        rng = np.random.default_rng(seed + offset + index)
        out = np.ascontiguousarray(np.clip(info.fn(out, params, rng), 0.0, 1.0), dtype=np.float32)
        index += 1
    return out


def _legacy_steps_1_to_7(src: Image, spec: PipelineSpec, max_side: int | None) -> tuple:
    """Replay 1.0 steps 1 to 7 inline and return the grid image, the target and the factor."""
    work = np.ascontiguousarray(np.asarray(src, dtype=np.float32))
    if max_side is not None and max(work.shape[:2]) > max_side:
        work = color.downscale(work, -(-max(work.shape[:2]) // max_side))
    target = work.shape[:2]
    work = _legacy_effects(work, spec.pre_effects, spec.seed, 0)
    if spec.auto_levels:
        work = color.auto_levels(work)
    work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma, spec.saturation)
    if spec.pre_blur > 0.0:
        work = color.gaussian_blur(work, spec.pre_blur / 3.0)
    factor = max(MIN_PIXEL_SIZE, min(MAX_PIXEL_SIZE, int(spec.pixel_size)))
    return color.downscale(work, factor), target, factor


def _legacy_render(
    src: Image,
    spec: PipelineSpec,
    palette: Palette,
    max_side: int | None = None,
    *,
    round_frame: bool = False,
) -> np.ndarray:
    """Replay the whole 1.0 render path inline, as the frozen reference output.

    With round_frame, replay the reviewed defect instead: the frame is rounded to 8 bits
    before the post-effects, which is what the L2 wiring did before this fix.
    """
    work, target, factor = _legacy_steps_1_to_7(src, spec, max_side)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    code = color.metric_code(spec.color_metric)
    params["_color_metric"] = code
    indices = info.fn(
        color.to_working_space(work, code), color.to_working_space(palette, code), params
    )
    work = color.apply_palette(indices, palette)
    work = color.upscale_nearest(work, factor, target)
    if round_frame:
        work = color.to_float(color.to_pil(color.to_rgb8(work)))[: target[0], : target[1]]
    work = _legacy_effects(work, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
    return color.to_rgb8(work)


# --- Invariant 1: output size is exactly (cols*cell_w, rows*cell_h) ---


def test_invariant_output_size_matches_grid_geometry():
    assert PixelRenderer().render(_grid(rows=3, cols=4, cell=2), BW, _style()).size == (8, 6)
    assert PixelRenderer().render(_grid(rows=5, cols=7, cell=1), BW, _style()).size == (7, 5)


def test_invariant_output_size_with_non_square_cells():
    grid = CellGrid(
        cols=4,
        rows=3,
        cell_w=2,
        cell_h=3,
        index=np.zeros((3, 4), dtype=np.int32),
        coverage=np.zeros((3, 4), dtype=np.float32),
        luma=np.zeros((3, 4), dtype=np.float32),
        samples=np.zeros((3, 4, 1), dtype=np.float32),
    )
    assert PixelRenderer().render(grid, BW, _style()).size == (4 * 2, 3 * 3)


# --- Invariant 2: purity ---


def test_invariant_render_is_pure():
    grid = _grid()
    renderer = PixelRenderer()
    first = np.asarray(renderer.render(grid, BW, _style()))
    second = np.asarray(renderer.render(grid, BW, _style()))
    assert np.array_equal(first, second)


# --- Invariant 3: no mutation of grid or palette ---


def test_invariant_render_does_not_mutate_inputs():
    grid = _grid()
    palette = BW.copy()
    snapshot = (
        grid.index.copy(),
        grid.coverage.copy(),
        grid.luma.copy(),
        grid.samples.copy(),
    )
    PixelRenderer().render(grid, palette, _style())
    assert np.array_equal(grid.index, snapshot[0])
    assert np.array_equal(grid.coverage, snapshot[1])
    assert np.array_equal(grid.luma, snapshot[2])
    assert np.array_equal(grid.samples, snapshot[3])
    assert np.array_equal(palette, BW)


# --- Invariant 4: the pipeline chooses the grid from cell_aspect() ---


class _RecordingRenderer:
    """Stub renderer with a configurable cell aspect that records the grid it is given."""

    def __init__(self, aspect: float) -> None:
        self.name = f"recording_stub_{aspect!s}"
        self.aspect = aspect
        self.grid: CellGrid | None = None

    def cell_aspect(self) -> float:
        """Return the configured width / height of one cell."""
        return self.aspect

    def subgrid(self) -> tuple[int, int]:
        """Return (1, 1): the stub packs no sub-points."""
        return (1, 1)

    def consumes(self) -> frozenset[str]:
        """Return {"index"}: the stub draws palette indices only."""
        return frozenset({"index"})

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle):
        """Record the grid and return a blank image of the exact grid geometry."""
        self.grid = grid
        blank = np.zeros((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3), dtype=np.uint8)
        return color.to_pil(blank)


def _render_with_stub(aspect: float, src: Image, pixel_size: int) -> CellGrid:
    """Register a stub renderer at aspect, render src through the pipeline, then unregister."""
    stub = _RecordingRenderer(aspect)
    register_renderer(stub)
    try:
        spec = PipelineSpec(pixel_size=pixel_size)
        render_with_palette(src, spec, BW, renderer=stub.name)
    finally:
        cell_module._RENDERERS.pop(stub.name, None)
    assert stub.grid is not None
    return stub.grid


def test_invariant_cell_aspect_is_width_over_height():
    assert PixelRenderer().cell_aspect() == 1.0


def test_pipeline_derives_grid_geometry_from_cell_aspect():
    src = np.full((20, 30, 3), 0.5, dtype=np.float32)
    # règle H11 §5-6 (gelée 0.1.0) : a=0.5 < 1 → cell_h = pixel_size = 2,
    # cell_w = max(1, floor(2*0.5+0.5)) = 1 → (1, 2) ; à pixel_size=1 la règle
    # donne (1, 1) — le test pré-gel assertait (1, 2) par l'arrondi half-to-even
    grid = _render_with_stub(0.5, src, pixel_size=2)
    assert (grid.cell_w, grid.cell_h) == (1, 2)
    out_aspect = (grid.cols * grid.cell_w) / (grid.rows * grid.cell_h)
    assert out_aspect == pytest.approx(30 / 20)


def test_pipeline_preserves_source_aspect_with_square_cells():
    src = np.full((15, 40, 3), 0.5, dtype=np.float32)
    grid = _render_with_stub(1.0, src, pixel_size=3)
    assert (grid.cell_w, grid.cell_h) == (3, 3)
    out_aspect = (grid.cols * grid.cell_w) / (grid.rows * grid.cell_h)
    assert out_aspect == pytest.approx(40 / 15, rel=0.1)


# --- Invariant 5: unique, stable name ---


def test_invariant_renderer_name_is_stable():
    assert PixelRenderer().name == "pixel"
    assert get_renderer("pixel").name == "pixel"
    names = [get_renderer(name).name for name in list_renderers()]
    assert len(names) == len(set(names))


# --- Invariant 6: style.options round-trips through JSON ---


def test_invariant_style_options_round_trip_json():
    options = {"scale": 2, "label": "demo", "flags": [True, False], "ratio": 0.25}
    style = RenderStyle(options=options)
    assert json.loads(json.dumps(dict(style.options))) == options
    default = RenderStyle(options={})
    assert json.loads(json.dumps(dict(default.options))) == dict(default.options)


def test_style_rejects_non_serialisable_options():
    with pytest.raises(ValueError):
        RenderStyle(options={"x": object()})


def test_style_rejects_options_that_lose_their_type():
    with pytest.raises(ValueError):
        RenderStyle(options={"flags": (True, False)})


# --- Registry behaviour ---


def test_list_renderers_returns_pixel():
    # "at this point" (L2) est passé : les renderers des vagues 1+ s'ajoutent au registre
    # (glyph_ramp L6, bitmask L8…). L'assertion devient structurelle (DEV-211) : pixel reste
    # enregistré et chaque renderer est unique ; les invariants par renderer sont couverts par G8.
    names = list_renderers()
    assert "pixel" in names
    assert len(names) == len(set(names))
    assert {"glyph_ramp", "braille", "sextant", "quadrant", "half_block"} <= set(names)


def test_get_renderer_unknown_raises_key_error_naming_it():
    with pytest.raises(KeyError) as excinfo:
        get_renderer("nope")
    assert "nope" in str(excinfo.value)


def test_register_duplicate_name_raises_value_error():
    with pytest.raises(ValueError):
        register_renderer(PixelRenderer())


def test_protocol_conformance():
    assert isinstance(PixelRenderer(), CellRenderer)


# --- The pipeline reproduces the 1.0 path byte for byte ---


def _random_case(trial: int) -> tuple[Image, PipelineSpec, Palette]:
    """Return one deterministic (source, spec, palette) case for the parity sweep."""
    rng = np.random.default_rng(20261116 + trial)
    height = int(rng.integers(9, 25))
    width = int(rng.integers(9, 25))
    src = rng.random((height, width, 3), dtype=np.float32)
    palettes = [BW, GREY_PALETTE, PRIMARY, FLOAT_PALETTE, rng.random((5, 3)).astype(np.float32)]
    pixel_size = int(rng.integers(1, 4))
    if trial % 3 == 0:
        post = [EffectInstance("gaussian_blur", {"radius": 1.0})]
    elif trial % 3 == 1:
        post = [EffectInstance("noise", {"amount": 0.2, "monochrome": True})]
    else:
        post = []
    spec = PipelineSpec(pixel_size=pixel_size, post_effects=post, seed=trial)
    return src, spec, palettes[trial % len(palettes)]


@pytest.mark.parametrize("trial", range(20))
def test_pipeline_matches_legacy_finish_on_random_images(trial: int) -> None:
    src, spec, palette = _random_case(trial)
    got = render_with_palette(src, spec, palette)
    want = _legacy_render(src, spec, palette)
    assert got.shape == want.shape
    assert np.array_equal(got, want), f"mismatch on trial {trial}"


def test_pipeline_matches_legacy_finish_with_max_side_and_effects():
    rng = np.random.default_rng(99)
    src = rng.random((40, 57, 3), dtype=np.float32)
    spec = PipelineSpec(
        pixel_size=2,
        post_effects=[EffectInstance("gaussian_blur", {"radius": 1.0})],
        pre_effects=[EffectInstance("noise", {"amount": 0.1})],
        seed=5,
    )
    got = render_with_palette(src, spec, FLOAT_PALETTE, max_side=20)
    want = _legacy_render(src, spec, FLOAT_PALETTE, max_side=20)
    assert np.array_equal(got, want)


def test_extracted_palette_with_post_effect_matches_legacy_finish():
    rng = np.random.default_rng(424242)
    src = rng.random((37, 53, 3), dtype=np.float32)
    palette = extract_palette(src, 5, "kmeans")
    assert not np.allclose(palette * 255.0, np.round(palette * 255.0)), "palette is 8-bit aligned"
    spec = PipelineSpec(
        pixel_size=2,
        post_effects=[EffectInstance("gaussian_blur", {"radius": 1.0})],
        seed=3,
    )
    got = render_with_palette(src, spec, palette)
    assert np.array_equal(got, _legacy_render(src, spec, palette))
    assert not np.array_equal(got, _legacy_render(src, spec, palette, round_frame=True))


def test_median_cut_palette_with_noise_matches_legacy_finish():
    rng = np.random.default_rng(8181)
    src = rng.random((24, 31, 3), dtype=np.float32)
    palette = extract_palette(src, 6, "median_cut")
    spec = PipelineSpec(
        pixel_size=3,
        post_effects=[EffectInstance("noise", {"amount": 0.3, "monochrome": False})],
        seed=11,
    )
    got = render_with_palette(src, spec, palette)
    assert np.array_equal(got, _legacy_render(src, spec, palette))


# --- Coverage derivation ---


def test_coverage_zero_on_single_colour_palette():
    palette = np.array([[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]], dtype=np.float32)
    coverage = _coverage_table(palette)
    assert np.all(coverage == 0.0)
    assert coverage.shape == (2,)


def test_coverage_monotone_in_palette_luminance():
    palette = np.array([[v / 255.0] * 3 for v in (0, 64, 128, 192, 255)], dtype=np.float32)
    linear = color.srgb_to_linear(palette)
    lum = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
    coverage = _coverage_table(palette)
    assert np.all(np.diff(coverage[np.argsort(lum)]) >= 0)


def test_luma_is_continuous_and_palette_independent():
    rng = np.random.default_rng(7)
    work = rng.random((4, 6, 3)).astype(np.float32)
    index = np.zeros((4, 6), dtype=np.int32)
    grid_bw = _make_grid(work, index, 1, 1, BW)
    grid_grey = _make_grid(work, index, 1, 1, GREY_PALETTE)
    assert np.array_equal(grid_bw.luma, grid_grey.luma)
    linear = color.srgb_to_linear(work)
    expected = (
        0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1] + 0.0722 * linear[:, :, 2]
    ).astype(np.float32)
    assert np.allclose(grid_bw.luma, expected, atol=1e-6)
