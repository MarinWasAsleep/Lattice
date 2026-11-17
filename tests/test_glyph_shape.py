"""Tests for the glyph_shape renderer (§3, §9) — card L7.

Every test that needs a glyph's shape vector recomputes it with Pillow's own rasteriser
(``_reference_mask`` / ``_reference_vector``), never with the renderer's helpers, so a
change that moves both the renderer and its own mask helper still fails here. The accept
items of the card are covered one by one, in order.

Ink domain: the renderer compares a cell's ink with a glyph's covered *area*, so a cell's
ink is ``1 - linear_to_srgb(samples)`` — a 50% grey reads as 0.5 ink, not 0.786. The
helpers below build grids in that same domain (``_one_cell_grid`` encodes an ink vector
into linear-light samples), so a round trip means what it says.

``sample_points()`` is an extension, not part of the §3 Protocol: §3 documents the optional
method and the pipeline probes it with ``getattr``. ``test_the_pipeline_reads_the_renderer_stencil``
pins that the pipeline really uses it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
from lattice_core import color, pipeline
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
from lattice_core.pipeline import PipelineSpec, render_with_palette
from lattice_core.renderers import glyph_shape
from lattice_core.renderers.glyph_ramp import GlyphRampRenderer, _font_size
from lattice_core.renderers.glyph_shape import (
    _CIRCLE_RADIUS,
    _CIRCLE_X,
    _CIRCLE_Y,
    CIRCLES,
    DEFAULT_ALPHABET,
    GlyphPlacement,
    GlyphShapeOptions,
    GlyphShapeRenderer,
    ShapeTable,
    _assignments,
    _circle_weights,
    _ink_vectors,
    _read_options,
    _shape_table,
)
from lattice_core.types import Palette

BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
CELL_W, CELL_H = 8, 16
SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
_PAD = 64


def _style(**options: object) -> RenderStyle:
    """Return a RenderStyle carrying the given glyph_shape options."""
    return RenderStyle(options=dict(options))


def _grid_of(
    src: np.ndarray, pixel_size: int = 8, style: dict | None = None, palette: Palette = BW
) -> CellGrid:
    """Return the CellGrid the pipeline hands the renderer for src (spy on _render_frame)."""
    captured: dict[str, CellGrid] = {}
    original = pipeline._render_frame

    def spy(renderer, grid, render_palette, render_style):
        captured["grid"] = grid
        return original(renderer, grid, render_palette, render_style)

    pipeline._render_frame = spy
    try:
        render_with_palette(
            src,
            PipelineSpec(pixel_size=pixel_size, renderer="glyph_shape", renderer_style=style or {}),
            palette,
        )
    finally:
        pipeline._render_frame = original
    return captured["grid"]


def _chars(
    grid: CellGrid, normalise: bool = True, alphabet: str = DEFAULT_ALPHABET
) -> np.ndarray:
    """Return the glyph character chosen for every cell, row-major, as an array."""
    options = GlyphShapeOptions(alphabet=alphabet, normalise=normalise)
    index = _assignments(grid, options)
    return np.array([alphabet[int(value)] for value in index.ravel()])


def _top_share(chars: np.ndarray, k: int) -> float:
    """Return the share of cells carrying one of the k most frequent characters."""
    _, counts = np.unique(chars, return_counts=True)
    return float(np.sort(counts)[::-1][:k].sum() / len(chars))


def _glyphs_covering(chars: np.ndarray, share: float) -> int:
    """Return how many distinct glyphs are needed to cover `share` of the cells."""
    _, counts = np.unique(chars, return_counts=True)
    cumulative = np.cumsum(np.sort(counts)[::-1] / len(chars))
    return int(np.searchsorted(cumulative, share) + 1)


def _gradient(size: int = 1024) -> np.ndarray:
    """Return a black-to-white horizontal sRGB ramp, size x size, as float32."""
    ramp = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :, None]
    return np.ascontiguousarray(np.repeat(np.repeat(ramp, size, axis=0), 3, axis=2))


def _diagonal_edge(size: int = 512) -> np.ndarray:
    """Return a hard diagonal edge: dark where col + row < size, white beyond it."""
    rows, cols = np.mgrid[0:size, 0:size]
    edge = ((cols + rows) > size).astype(np.float32)
    return np.ascontiguousarray(np.repeat(edge[:, :, None], 3, axis=2))


def _vertical_ink(cell_w: int, cell_h: int, band: float = 0.34) -> np.ndarray:
    """Return two cells that differ only by the vertical position of their ink."""
    height, width = cell_h, cell_w * 2
    image = np.ones((height, width), dtype=np.float32)
    rows = max(1, int(round(band * height)))
    image[:rows, :cell_w] = 0.0
    image[height - rows :, cell_w:] = 0.0
    return np.ascontiguousarray(np.repeat(image[:, :, None], 3, axis=2))


def _glyph_pair(left: str, right: str, cell_w: int, cell_h: int) -> np.ndarray:
    """Return two cells carrying left and right in the renderer's own font and size."""
    font = _default_font(_font_size(cell_w, cell_h, None))
    canvas = PILImage.new("L", (cell_w * 2, cell_h), 255)
    draw = ImageDraw.Draw(canvas)
    draw.text((cell_w / 2.0, cell_h / 2.0), left, font=font, fill=0, anchor="mm")
    draw.text((cell_w * 1.5, cell_h / 2.0), right, font=font, fill=0, anchor="mm")
    grey = np.asarray(canvas, dtype=np.float32) / 255.0
    return np.ascontiguousarray(np.repeat(grey[:, :, None], 3, axis=2))


def _default_font(size: int) -> ImageFont.FreeTypeFont:
    """Return Pillow's bundled default font at size, typed as the FreeType font it is."""
    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))


def _reference_mask(glyph: str, cell_w: int, cell_h: int) -> np.ndarray:
    """Draw glyph with Pillow alone, centred in a cell, and return its float32 ink in [0, 1]."""
    font = _default_font(_font_size(cell_w, cell_h, None))
    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
    ImageDraw.Draw(canvas).text(
        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
    )
    patch = np.asarray(canvas, dtype=np.float32)[_PAD : _PAD + cell_h, _PAD : _PAD + cell_w]
    return np.ascontiguousarray(patch / 255.0)


def _reference_vector(glyph: str, cell_w: int, cell_h: int) -> np.ndarray:
    """Return one glyph's six raw disk fractions, drawn with Pillow and a plain disk mask."""
    mask = _reference_mask(glyph, cell_w, cell_h)
    rows, cols = np.mgrid[0:cell_h, 0:cell_w]
    radius = max(0.5, _CIRCLE_RADIUS * float(min(cell_w, cell_h)))
    vector = np.zeros(CIRCLES, dtype=np.float32)
    for k, (centre_x, centre_y) in enumerate((x, y) for y in _CIRCLE_Y for x in _CIRCLE_X):
        x, y = centre_x * cell_w, centre_y * cell_h
        disk = (cols + 0.5 - x) ** 2 + (rows + 0.5 - y) ** 2 <= radius * radius
        if disk.any():
            vector[k] = float(mask[disk].mean())
    return vector


def _density_ramp(cell_w: int, cell_h: int) -> str:
    """Return DEFAULT_ALPHABET ordered darkest first by Pillow-measured ink density (§9).

    This is the ramp the ``glyph_ramp`` comparator must use: the ramp contract is
    "darkest character first, lightest last", so an ASCII-ordered alphabet is not a ramp
    at all and would make the comparison meaningless.
    """
    density = np.array([_reference_mask(char, cell_w, cell_h).mean() for char in DEFAULT_ALPHABET])
    return "".join(DEFAULT_ALPHABET[index] for index in np.argsort(-density, kind="stable"))


def _ramp_chars(grid: CellGrid, ramp: str) -> np.ndarray:
    """Return the character glyph_ramp chooses for every cell of grid, row-major."""
    placed = GlyphRampRenderer().layout(grid, BW, RenderStyle(options={"ramp": ramp}))
    return np.array([entry.character for entry in placed])


def _one_cell_grid(ink: np.ndarray, cell_w: int = CELL_W, cell_h: int = CELL_H) -> CellGrid:
    """Return a one-cell grid whose samples encode the given coverage-domain ink vector.

    ``samples`` are linear-light luminance (§3, S2), so an ink vector is encoded back
    through the sRGB transfer function: ``samples = srgb_to_linear(1 - ink)``.
    """
    samples = color.srgb_to_linear(np.clip(1.0 - np.asarray(ink, np.float32), 0.0, 1.0))
    return CellGrid(
        cols=1, rows=1, cell_w=cell_w, cell_h=cell_h,
        index=np.zeros((1, 1), np.int32), coverage=np.zeros((1, 1), np.float32),
        luma=np.zeros((1, 1), np.float32),
        samples=np.ascontiguousarray(samples.reshape(1, 1, CIRCLES), np.float32),
    )


# --- accept 1: a diagonal edge picks different glyphs on either side ---


def test_diagonal_edge_picks_different_glyphs_on_either_side():
    grid = _grid_of(_diagonal_edge())
    chars = _chars(grid).reshape(grid.rows, grid.cols)
    middle = grid.rows // 2
    dark_side = set(chars[middle, : grid.cols // 4].tolist())
    light_side = set(chars[middle, -grid.cols // 4 :].tolist())
    assert dark_side and light_side
    assert dark_side.isdisjoint(light_side), f"the edge did not separate glyphs: {dark_side}"


def test_diagonal_edge_separates_the_dark_and_light_corners():
    grid = _grid_of(_diagonal_edge())
    chars = _chars(grid).reshape(grid.rows, grid.cols)
    assert len(set(chars[: grid.rows // 4, : grid.cols // 4].ravel().tolist())) == 1
    assert len(set(chars[-grid.rows // 4 :, -grid.cols // 4 :].ravel().tolist())) == 1
    assert chars[0, 0] != chars[-1, -1]


def test_the_reference_ramp_is_ordered_darkest_first_by_ink_density():
    """The comparator's ramp must be a real density ramp, not the alphabet in ASCII order."""
    ramp = _density_ramp(CELL_W, CELL_H)
    density = np.array([_reference_mask(char, CELL_W, CELL_H).mean() for char in ramp])
    assert np.all(np.diff(density) <= 1e-7), "the reference ramp is not darkest-first"
    assert len(set(ramp)) == len(DEFAULT_ALPHABET)
    assert ramp != DEFAULT_ALPHABET, "an ASCII-ordered alphabet is not a density ramp"


def test_diagonal_edge_differs_from_glyph_ramp_on_at_least_twenty_percent_of_cells():
    grid = _grid_of(_diagonal_edge())
    shape_chars = _chars(grid)
    ramp_chars = _ramp_chars(grid, _density_ramp(grid.cell_w, grid.cell_h))
    share = float((shape_chars != ramp_chars).mean())
    assert share >= 0.20, f"glyph_shape agrees with glyph_ramp on {1 - share:.0%} of cells"
    assert share < 1.0, "the two renderers must agree somewhere, or the ramp is still arbitrary"


def test_near_the_edge_the_shape_and_the_density_ramp_disagree_most():
    """The disagreement is concentrated where shape, not density, decides the glyph."""
    grid = _grid_of(_diagonal_edge())
    shape_chars = _chars(grid).reshape(grid.rows, grid.cols)
    ramp_chars = _ramp_chars(grid, _density_ramp(grid.cell_w, grid.cell_h))
    ramp_chars = ramp_chars.reshape(grid.rows, grid.cols)
    differ = (shape_chars != ramp_chars)
    xs = (np.arange(grid.cols) + 0.5) * grid.cell_w
    ys = (np.arange(grid.rows) + 0.5) * grid.cell_h
    distance = np.abs(ys[:, None] + xs[None, :] - 512.0) / np.sqrt(2.0)
    band = distance < float(grid.cell_h)
    assert 0 < int(band.sum()) < differ.size
    assert float(differ[band].mean()) >= 0.20
    assert float(differ[band].mean()) > float(differ[~band].mean())
    dark = shape_chars[grid.rows // 2, : grid.cols // 4]
    ramp_dark = ramp_chars[grid.rows // 2, : grid.cols // 4]
    assert set(dark.tolist()) != set(ramp_dark.tolist()), "the dark side drew the same glyphs"


def test_diagonal_edge_holds_at_every_pipeline_cell_size():
    for pixel_size in (4, 8, 12, 16, 24, 32):
        grid = _grid_of(_diagonal_edge(384), pixel_size)
        chars = _chars(grid).reshape(grid.rows, grid.cols)
        middle = grid.rows // 2
        dark = set(chars[middle, : max(1, grid.cols // 4)].tolist())
        light = set(chars[middle, -max(1, grid.cols // 4) :].tolist())
        assert dark.isdisjoint(light), f"pixel_size={pixel_size} did not separate the edge"


# --- accept 2: the §9 normalisation is what stops the collapse ---


def test_without_normalisation_over_eighty_percent_of_cells_collapse_onto_three_glyphs():
    """The card's literal clause: >80% of cells on fewer than three distinct glyphs."""
    grid = _grid_of(_gradient())
    raw = _chars(grid, normalise=False)
    collapsed = _top_share(raw, 2)
    assert collapsed > 0.80, (
        f"only {collapsed:.0%} of cells carry one of the two commonest glyphs; the card asks "
        f"for more than 80% of cells on fewer than three distinct glyphs"
    )
    assert _glyphs_covering(raw, 0.80) < 3


def test_with_normalisation_at_least_eight_distinct_glyphs_appear_on_a_gradient():
    grid = _grid_of(_gradient())
    normalised = _chars(grid, normalise=True)
    assert len(set(normalised.tolist())) >= 8
    assert _glyphs_covering(normalised, 0.80) > _glyphs_covering(_chars(grid, False), 0.80)
    assert _top_share(normalised, 3) < _top_share(_chars(grid, normalise=False), 3)


def test_normalisation_also_spreads_a_vertical_gradient():
    ramp = np.linspace(0.0, 1.0, 1024, dtype=np.float32)[:, None, None]
    src = np.ascontiguousarray(np.repeat(np.repeat(ramp, 1024, axis=1), 3, axis=2))
    grid = _grid_of(src)
    normalised, raw = _chars(grid, normalise=True), _chars(grid, normalise=False)
    assert len(set(normalised.tolist())) > len(set(raw.tolist()))
    assert len(set(normalised.tolist())) >= 5


def test_normalisation_is_measured_against_the_alphabet_maximum():
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    assert isinstance(table, ShapeTable)
    assert table.maxima.shape == (CIRCLES,)
    assert np.allclose(table.normalised.max(axis=0), 1.0, atol=1e-6)
    assert np.allclose(table.normalised, table.raw / table.maxima, atol=1e-6)


def test_normalised_vectors_span_more_of_every_component_than_raw_ones():
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    raw_spread = table.raw.max(axis=0) - table.raw.min(axis=0)
    normalised_spread = table.normalised.max(axis=0) - table.normalised.min(axis=0)
    assert np.all(normalised_spread >= raw_spread - 1e-6)
    assert normalised_spread.mean() > raw_spread.mean()


def test_the_alphabet_maximum_is_taken_per_component_not_over_the_whole_table():
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    assert not np.allclose(table.maxima, table.maxima.max())
    assert np.allclose(table.maxima, table.raw.max(axis=0))


# --- accept 3: the module-level cache is hit on the second call ---


def test_shape_table_cache_is_hit_on_the_second_call(monkeypatch):
    calls = {"count": 0}
    original = glyph_shape._glyph_mask

    def counting(char, path, cell_w, cell_h):
        calls["count"] += 1
        return original(char, path, cell_w, cell_h)

    glyph_shape._shape_table.cache_clear()
    monkeypatch.setattr(glyph_shape, "_glyph_mask", counting)
    key = glyph_shape._font_key(None)
    first = _shape_table(key, CELL_W, CELL_H, DEFAULT_ALPHABET)
    assert calls["count"] == len(DEFAULT_ALPHABET)
    second = _shape_table(key, CELL_W, CELL_H, DEFAULT_ALPHABET)
    assert calls["count"] == len(DEFAULT_ALPHABET), "the second call re-rasterised the alphabet"
    assert second is first


def test_render_hits_the_cache_on_the_second_call():
    grid = _grid_of(_gradient(256))
    renderer, style = GlyphShapeRenderer(), _style()
    glyph_shape._shape_table.cache_clear()
    renderer.render_frame(grid, BW, style)
    misses_after_first = glyph_shape._shape_table.cache_info().misses
    renderer.render_frame(grid, BW, style)
    info = glyph_shape._shape_table.cache_info()
    assert misses_after_first == 1
    assert info.misses == 1, "the second render rebuilt the shape table"
    assert info.hits == 1


def test_the_shape_cache_is_bounded_and_input_keyed():
    cache = glyph_shape._shape_table
    cache.cache_clear()
    keys = [(cell_w, cell_w * 2) for cell_w in range(2, 14)]
    for cell_w, cell_h in keys:
        _shape_table(glyph_shape._font_key(None), cell_w, cell_h, DEFAULT_ALPHABET)
    info = cache.cache_info()
    assert info.maxsize is not None and info.maxsize == glyph_shape._SHAPE_CACHE_SIZE
    assert info.currsize == len(keys)
    for cell_w, cell_h in keys:
        _shape_table(glyph_shape._font_key(None), cell_w, cell_h, DEFAULT_ALPHABET)
    assert cache.cache_info().misses == len(keys)


def test_the_shape_cache_evicts_beyond_its_bound():
    cache = glyph_shape._shape_table
    cache.cache_clear()
    for index in range(glyph_shape._SHAPE_CACHE_SIZE + 8):
        _shape_table(glyph_shape._font_key(None), 2 + index, 4 + 2 * index, DEFAULT_ALPHABET)
    info = cache.cache_info()
    assert info.currsize == info.maxsize


def test_cached_shape_vectors_are_read_only():
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    for array in (table.raw, table.maxima, table.normalised):
        assert not array.flags.writeable
    with pytest.raises(ValueError):
        table.normalised[0, 0] = 1.0


# --- accept 4: the §9 budget ---


def test_budget_1024_square_sixty_four_glyphs_under_two_hundred_milliseconds():
    alphabet = "".join(chr(code) for code in range(32, 96))
    assert len(alphabet) == 64
    rng = np.random.default_rng(0)
    src = rng.random((1024, 1024, 3), dtype=np.float32)
    grid = _grid_of(src, 8, {"alphabet": alphabet})
    renderer, style = GlyphShapeRenderer(), _style(alphabet=alphabet)
    renderer.render_frame(grid, BW, style)  # warm up: the shape table and the glyph masks
    started = time.perf_counter()
    renderer.render_frame(grid, BW, style)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.200, f"render_frame took {elapsed * 1000:.1f} ms, budget 200 ms"


def test_budget_holds_on_a_1024_square_image_at_every_cell_size():
    alphabet = "".join(chr(code) for code in range(32, 96))
    rng = np.random.default_rng(1)
    src = rng.random((1024, 1024, 3), dtype=np.float32)
    for pixel_size in (4, 8, 16):
        grid = _grid_of(src, pixel_size, {"alphabet": alphabet})
        renderer, style = GlyphShapeRenderer(), _style(alphabet=alphabet)
        renderer.render_frame(grid, BW, style)
        started = time.perf_counter()
        renderer.render_frame(grid, BW, style)
        elapsed = time.perf_counter() - started
        assert elapsed < 0.200, f"pixel_size={pixel_size} took {elapsed * 1000:.1f} ms"


# --- accept 5: p and q are distinguished by vertical ink position ---


def test_p_and_q_are_distinguished_on_an_image_differing_only_in_vertical_ink():
    grid = _grid_of(_vertical_ink(CELL_W, CELL_H), CELL_H)
    chars = _chars(grid)
    assert chars.shape == (2,)
    assert chars[0] != chars[1], f"both cells drew {chars[0]!r}"


def test_vertical_ink_is_distinguished_at_every_pipeline_cell_size():
    for pixel_size in (4, 8, 12, 16, 20, 24, 32):
        cell_w, cell_h = pixel_size // 2, pixel_size
        grid = _grid_of(_vertical_ink(cell_w, cell_h), pixel_size)
        chars = _chars(grid)
        assert chars[0] != chars[1], f"pixel_size={pixel_size} drew {chars[0]!r} twice"


def test_p_and_q_drawn_in_the_font_are_distinguished():
    """p and q differ only by which side of the cell their stem descends on (§9).

    The samples carry that difference at every cell size; the six-disk nearest neighbour
    resolves it once the cell is tall enough for the disks to fall on different rows
    (measured: cell_h >= 10). Below that the stencil cannot separate them, so the vector
    assertion is the one that holds there.
    """
    for pixel_size in (8, 10, 12, 16, 20, 24, 32, 40):
        cell_w, cell_h = pixel_size // 2, pixel_size
        grid = _grid_of(_glyph_pair("p", "q", cell_w, cell_h), pixel_size)
        ink = _ink_vectors(grid)[0]
        assert not np.allclose(ink[0], ink[1]), f"pixel_size={pixel_size} lost the difference"
        if cell_h < 10:
            continue
        chars = _chars(grid)
        assert chars[0] != chars[1], f"pixel_size={pixel_size} drew {chars[0]!r} for both"


# --- §3 invariants ---


def test_renderer_is_registered_under_a_unique_stable_name():
    renderer = GlyphShapeRenderer()
    assert renderer.name == "glyph_shape"
    assert get_renderer("glyph_shape").name == "glyph_shape"
    assert "glyph_shape" in list_renderers()
    assert isinstance(renderer, CellRenderer)


def test_cell_aspect_subgrid_and_consumes():
    renderer = GlyphShapeRenderer()
    assert renderer.cell_aspect() == 0.5
    assert renderer.subgrid() == (1, 1)
    assert renderer.consumes() == frozenset({"samples"})


def test_consumes_declares_only_what_render_reads():
    """render reads grid.samples and nothing else: no luma, no index, no palette."""
    consumed = GlyphShapeRenderer().consumes()
    assert consumed == frozenset({"samples"})
    assert "index" not in consumed, "the palette never colours a glyph: fg/bg do"
    assert "luma" not in consumed, "the six circle samples are the whole input"
    assert consumed <= {"index", "luma", "samples", "coverage", "subindex"}


def test_sample_points_is_the_six_circle_stencil():
    points = GlyphShapeRenderer().sample_points()
    assert points.shape == (CIRCLES, 2)
    assert points.dtype == np.float32
    assert np.all((points >= 0.0) & (points <= 1.0))
    assert len({tuple(row) for row in points.tolist()}) == CIRCLES
    assert sorted(set(points[:, 0].tolist())) == pytest.approx([0.28, 0.72])
    assert sorted(set(points[:, 1].tolist())) == pytest.approx([0.22, 0.50, 0.78])


def test_sample_points_are_the_centres_of_the_disk_weights():
    """The stencil the pipeline samples and the disks the table integrates are one geometry.

    Matching a cell vector to a glyph vector only means anything if both are read at the
    same six places; this pins that the declared centres are the disks' own centroids.
    """
    points = GlyphShapeRenderer().sample_points()
    for cell_w, cell_h in ((CELL_W, CELL_H), (4, 8), (2, 4)):
        weights = _circle_weights(cell_w, cell_h)
        rows, cols = np.mgrid[0:cell_h, 0:cell_w]
        declared = np.asarray([(x * cell_w, y * cell_h) for x, y in points])
        for k in range(CIRCLES):
            weight = weights[k].reshape(cell_h, cell_w)
            centroid = np.array([(weight * (cols + 0.5)).sum(),
                                 (weight * (rows + 0.5)).sum()]) / weight.sum()
            nearest = int(np.argmin(((declared - centroid) ** 2).sum(axis=1)))
            assert nearest == k, f"cell {cell_w}x{cell_h}: disk {k} is nearest another centre"
            assert float(np.abs(centroid - declared[k]).max()) <= 0.75


def test_pipeline_samples_land_on_the_six_circle_centres():
    """Ink at exactly one circle centre lights exactly that component of grid.samples."""
    points = GlyphShapeRenderer().sample_points()
    for k, (centre_x, centre_y) in enumerate(points):
        pixel_x = int(np.floor(float(centre_x) * CELL_W))
        pixel_y = int(np.floor(float(centre_y) * CELL_H))
        src = np.ones((CELL_H, CELL_W, 3), dtype=np.float32)
        src[pixel_y, pixel_x] = 0.0
        grid = _grid_of(src, CELL_H)
        assert grid.samples.shape == (1, 1, CIRCLES)
        row = grid.samples[0, 0]
        assert int(np.argmin(row)) == k, f"circle {k} at ({pixel_x}, {pixel_y}) landed elsewhere"
        assert np.all(np.delete(row, k) == 1.0), f"circle {k} bled into another component"


def test_the_pipeline_reads_the_renderer_stencil(monkeypatch):
    """sample_points() is an extension, not §3 Protocol: the pipeline must still honour it."""
    renderer = get_renderer("glyph_shape")
    src = np.ones((CELL_H, CELL_W, 3), dtype=np.float32)
    src[3, 2] = 0.0  # the top-left circle centre
    plain = _grid_of(src, CELL_H).samples[0, 0]
    assert int(np.argmin(plain)) == 0
    stencil = GlyphShapeRenderer().sample_points()
    monkeypatch.setattr(renderer, "sample_points", lambda: np.ascontiguousarray(stencil[::-1]))
    moved = _grid_of(src, CELL_H).samples[0, 0]
    assert int(np.argmin(moved)) == CIRCLES - 1, "the pipeline ignored sample_points()"


@pytest.mark.parametrize(("rows", "cols", "cell_w", "cell_h"), [(3, 4, 8, 16), (1, 1, 5, 7)])
def test_output_size_is_exactly_the_grid_geometry(rows, cols, cell_w, cell_h):
    luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
    grid = CellGrid(
        cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
        index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma,
        samples=np.ascontiguousarray(np.repeat(luma[:, :, None], CIRCLES, axis=2)),
    )
    image = GlyphShapeRenderer().render(grid, BW, _style())
    assert image.size == (cols * cell_w, rows * cell_h)


def test_render_is_pure():
    grid = _grid_of(_gradient(256))
    renderer = GlyphShapeRenderer()
    assert np.array_equal(
        np.asarray(renderer.render(grid, BW, _style())),
        np.asarray(renderer.render(grid, BW, _style())),
    )


def test_render_does_not_mutate_grid_or_palette():
    grid = _grid_of(_gradient(256))
    palette = BW.copy()
    snapshot = (grid.index.copy(), grid.luma.copy(), grid.samples.copy(), grid.coverage.copy())
    GlyphShapeRenderer().render(grid, palette, _style())
    assert np.array_equal(grid.index, snapshot[0])
    assert np.array_equal(grid.luma, snapshot[1])
    assert np.array_equal(grid.samples, snapshot[2])
    assert np.array_equal(grid.coverage, snapshot[3])
    assert np.array_equal(palette, BW)


def test_render_frame_matches_render():
    grid = _grid_of(_gradient(256))
    renderer = GlyphShapeRenderer()
    frame = renderer.render_frame(grid, BW, _style())
    assert frame.shape == (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
    assert frame.dtype == np.float32
    assert np.array_equal(color.to_rgb8(frame), np.asarray(renderer.render(grid, BW, _style())))


def test_the_glyph_choice_is_independent_of_the_palette():
    src = _gradient(256)
    black_and_white = _chars(_grid_of(src, 8, palette=BW))
    colour = _chars(_grid_of(src, 8, palette=COLOUR))
    assert np.array_equal(black_and_white, colour)
    assert len(set(black_and_white.tolist())) > 1


def test_layout_places_one_glyph_per_cell_row_major():
    grid = _grid_of(_gradient(256))
    placed = GlyphShapeRenderer().layout(grid, BW, _style())
    assert len(placed) == grid.rows * grid.cols
    assert all(isinstance(entry, GlyphPlacement) for entry in placed)
    for col, entry in enumerate(placed[: grid.cols]):
        assert entry.x == col * grid.cell_w and entry.y == 0.0
        assert entry.width == grid.cell_w and entry.height == grid.cell_h


def test_layout_accepts_both_call_forms():
    grid, style = _grid_of(_gradient(256)), _style()
    assert GlyphShapeRenderer().layout(grid, style) == GlyphShapeRenderer().layout(grid, BW, style)


def test_layout_characters_match_the_rendered_glyphs():
    grid = _grid_of(_gradient(256))
    placed = GlyphShapeRenderer().layout(grid, BW, _style())
    assert np.array_equal(np.array([entry.character for entry in placed]), _chars(grid))


def test_layout_reports_the_ink_and_paper_colours():
    grid = _grid_of(_gradient(128))
    entry = GlyphShapeRenderer().layout(grid, BW, _style(fg="#112233", bg="#445566"))[0]
    assert entry.fill == "#112233" and entry.paper == "#445566"


def test_style_options_round_trip_through_the_renderer():
    options = {"alphabet": DEFAULT_ALPHABET, "fg": "#112233", "bg": "#445566", "font": None}
    grid = _grid_of(_gradient(128))
    style = _style(**options)
    assert json.loads(json.dumps(dict(style.options))) == options
    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
    assert np.array_equal(
        np.asarray(GlyphShapeRenderer().render(grid, BW, style)),
        np.asarray(GlyphShapeRenderer().render(grid, BW, reloaded)),
    )


def test_fg_and_bg_colours_are_honoured():
    grid = _grid_of(_gradient(128))
    dark_ink = GlyphShapeRenderer().render_frame(grid, BW, _style(fg="#000000", bg="#ffffff"))
    light_ink = GlyphShapeRenderer().render_frame(grid, BW, _style(fg="#ffffff", bg="#000000"))
    assert np.allclose(dark_ink + light_ink, 1.0, atol=1e-6)
    assert np.allclose(dark_ink.reshape(-1, 3).max(axis=0), 1.0)
    assert float(dark_ink.min()) < 0.5, "no glyph was drawn in the ink colour"
    red_ink = GlyphShapeRenderer().render_frame(grid, BW, _style(fg="#ff0000", bg="#0000ff"))
    assert np.allclose(red_ink[:, :, 1], 0.0), "the green channel must stay empty"
    assert float(red_ink[:, :, 0].max()) > 0.5, "the ink never reached the red channel"
    assert float(red_ink[:, :, 2].max()) == pytest.approx(1.0), "the paper is not pure blue"


def test_unknown_style_keys_are_ignored_for_forward_compatibility():
    grid = _grid_of(_gradient(128))
    plain = np.asarray(GlyphShapeRenderer().render(grid, BW, _style()))
    future = np.asarray(GlyphShapeRenderer().render(grid, BW, _style(glow=0.7)))
    assert np.array_equal(plain, future)


def test_missing_font_file_raises_value_error_naming_the_path():
    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
    with pytest.raises(ValueError) as excinfo:
        GlyphShapeRenderer().render(_grid_of(_gradient(64)), BW, _style(font=path))
    assert path in str(excinfo.value)


def test_font_option_accepts_a_real_font_file():
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    grid = _grid_of(_gradient(128))
    image = GlyphShapeRenderer().render(grid, BW, _style(font=str(SYSTEM_FONT)))
    assert image.size == (grid.cols * grid.cell_w, grid.rows * grid.cell_h)


# --- option validation ---


def test_empty_alphabet_raises_value_error():
    with pytest.raises(ValueError):
        _read_options(_style(alphabet=""))


def test_invalid_colour_raises_value_error():
    with pytest.raises(ValueError):
        _read_options(_style(fg="not-a-colour"))


def test_non_boolean_normalise_raises_value_error():
    with pytest.raises(ValueError):
        _read_options(_style(normalise="yes"))


def test_samples_of_the_wrong_width_raise_value_error():
    grid = CellGrid(
        cols=2, rows=1, cell_w=CELL_W, cell_h=CELL_H,
        index=np.zeros((1, 2), np.int32), coverage=np.zeros((1, 2), np.float32),
        luma=np.zeros((1, 2), np.float32), samples=np.zeros((1, 2, 3), np.float32),
    )
    with pytest.raises(ValueError) as excinfo:
        _assignments(grid, GlyphShapeOptions())
    assert "samples" in str(excinfo.value)


# --- the shape vector itself ---


def test_shape_vectors_match_an_independent_pillow_reference():
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    for glyph in " @|_-oO0#%WM":
        expected = _reference_vector(glyph, CELL_W, CELL_H)
        assert np.allclose(table.raw[DEFAULT_ALPHABET.index(glyph)], expected, atol=1e-5), glyph


def test_circle_weights_are_normalised_disks():
    weights = _circle_weights(CELL_W, CELL_H)
    assert weights.shape == (CIRCLES, CELL_H * CELL_W)
    assert np.allclose(weights.sum(axis=1), 1.0, atol=1e-6)
    assert np.all(weights >= 0.0)


def test_ink_vectors_are_the_srgb_complement_of_the_samples():
    """Ink is a covered area, so the linear-light samples are re-encoded before the complement."""
    grid = _grid_of(_gradient(128))
    ink = _ink_vectors(grid)
    assert np.allclose(ink, 1.0 - color.linear_to_srgb(grid.samples), atol=1e-6)
    assert float(ink.min()) >= 0.0 and float(ink.max()) <= 1.0


def test_a_mid_grey_patch_reads_as_half_ink():
    """A 50% sRGB grey is 0.21 in linear light: the raw complement would read 0.79 ink."""
    grey = np.full((CELL_H, CELL_W, 3), 0.5, dtype=np.float32)
    grid = _grid_of(grey)
    ink = _ink_vectors(grid)
    assert np.allclose(ink, 0.5, atol=1e-6), f"mid grey read as {float(ink[0, 0, 0]):.3f} ink"
    assert float(np.mean(1.0 - grid.samples)) > 0.7, "the linear complement is not 0.5"


def test_a_cell_carrying_a_glyph_maps_back_to_that_glyph_without_normalisation():
    for glyph in ("@", "%", "W", "M", "O"):
        vector = _reference_vector(glyph, CELL_W, CELL_H)
        chosen = _chars(_one_cell_grid(vector), normalise=False)[0]
        assert chosen == glyph, f"{glyph!r} was read back as {chosen!r}"


def test_a_cell_carrying_a_glyph_maps_back_to_that_glyph_on_the_default_path():
    """The default (normalise=True) path must round-trip a cell that really carries a glyph."""
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    for glyph in "@%WMB8Q$&0#g":
        position = DEFAULT_ALPHABET.index(glyph)
        chosen = _chars(_one_cell_grid(table.normalised[position]))[0]
        assert chosen == glyph, f"{glyph!r} was read back as {chosen!r}"


def test_every_normalised_alphabet_vector_maps_back_to_its_own_vector():
    """Not necessarily the same character (duplicate vectors exist), but never another shape."""
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    for position in range(len(DEFAULT_ALPHABET)):
        grid = _one_cell_grid(table.normalised[position])
        chosen = int(_assignments(grid, GlyphShapeOptions())[0, 0])
        assert np.array_equal(table.normalised[chosen], table.normalised[position]), (
            f"{DEFAULT_ALPHABET[position]!r} was read back as {DEFAULT_ALPHABET[chosen]!r}"
        )


def test_the_default_path_is_the_argmin_of_the_squared_distance():
    """An independent, naive argmin must agree with the renderer's matrix formulation."""
    table = _shape_table(glyph_shape._font_key(None), CELL_W, CELL_H, DEFAULT_ALPHABET)
    for position in range(len(DEFAULT_ALPHABET)):
        grid = _one_cell_grid(table.normalised[position])
        ink = _ink_vectors(grid).reshape(-1, CIRCLES)
        chosen = int(_assignments(grid, GlyphShapeOptions())[0, 0])
        expected = int(np.argmin(((table.normalised - ink) ** 2).sum(axis=1)))
        assert chosen == expected, f"{DEFAULT_ALPHABET[position]!r} disagrees with the naive argmin"


def test_a_flat_cell_maps_to_the_blank_glyph():
    grid = CellGrid(
        cols=1, rows=1, cell_w=CELL_W, cell_h=CELL_H,
        index=np.zeros((1, 1), np.int32), coverage=np.zeros((1, 1), np.float32),
        luma=np.ones((1, 1), np.float32),
        samples=np.ones((1, 1, CIRCLES), np.float32),
    )
    assert _chars(grid)[0] == DEFAULT_ALPHABET[0]


def test_default_alphabet_is_the_printable_ascii_range():
    assert DEFAULT_ALPHABET[0] == " "
    assert len(DEFAULT_ALPHABET) == len(set(DEFAULT_ALPHABET))
    assert DEFAULT_ALPHABET == "".join(chr(code) for code in range(32, 127))
    assert len(DEFAULT_ALPHABET) == 95


def test_the_six_circles_are_top_middle_bottom_by_left_right():
    assert _CIRCLE_X == (0.28, 0.72)
    assert _CIRCLE_Y == (0.22, 0.50, 0.78)
    assert 0.0 < _CIRCLE_RADIUS < 0.5
    assert _CIRCLE_Y[0] < _CIRCLE_Y[1] < _CIRCLE_Y[2]


def test_every_cell_size_in_the_pipeline_gets_at_least_eight_glyphs_on_a_gradient():
    ramp = np.linspace(0.0, 1.0, 2048, dtype=np.float32)[None, :, None]
    src = np.ascontiguousarray(np.repeat(np.repeat(ramp, 64, axis=0), 3, axis=2))
    for pixel_size in (4, 6, 8, 12, 16, 20, 24, 32):
        grid = _grid_of(src, pixel_size)
        assert len(set(_chars(grid).tolist())) >= 8, f"pixel_size={pixel_size} collapsed"
