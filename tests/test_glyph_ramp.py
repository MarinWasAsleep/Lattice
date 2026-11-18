"""Tests for the glyph_ramp renderer (§3, §9, AMD-010) — cards L6 and L9c.

Expected glyph sequences are pinned as literals derived from the contract, never recomputed
with the renderer's own formula: §9 + AMD-010 say ``luma`` (S2) indexes the ramp through its
sRGB-perceptual encoding, so a linear luma of 0.05 encodes to sRGB 0.2478, lands in bucket 2
of a 10-character ramp and must draw ``'#'``. Since H12 (2026-11-18) ``bg_colour`` glyphs
follow the |luma - background| gap divided by the palette's LINEAR luma span (max-min,
epsilon-guarded; never a tuned exponent), over the ramp bounded to its medium densities;
its ink and ``palette``'s ink are the palette entry two ranks off the cell colour, and
``palette`` honours the declared ``bg`` (explicit ``"auto"`` = the palette's darkest entry).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
from lattice_core import color
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
from lattice_core.palettes.builtin import get_builtin
from lattice_core.pipeline import (
    RESERVED_METRIC,
    PipelineSpec,
    _cell_geometry,
    _make_grid,
    _pad_to_cells,
    _to_cells,
    render_with_palette,
)
from lattice_core.registry import get_algorithm, resolve_params
from lattice_core.renderers import glyph_ramp
from lattice_core.renderers.glyph_ramp import (
    DEFAULT_RAMP,
    GlyphPlacement,
    GlyphRampRenderer,
    _font_size,
    _glyph_mask,
)
from lattice_core.types import Palette

RAMP = "@%#*+=-:. "
BOUNDED = RAMP[1:-1]  # "%#*+=-:." — H12 bg_colour ramp, extremes (space, '@') removed
PICO8_RAMP = " .:-=+*#%@"
BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
GREYS: Palette = np.array([[0.0, 0.0, 0.0], [0.25, 0.25, 0.25], [0.5, 0.5, 0.5],
                           [0.75, 0.75, 0.75], [1.0, 1.0, 1.0]], dtype=np.float32)
COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
                           dtype=np.float32)
CELL_W, CELL_H = 8, 16
SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
# Vendored H12 reference (L9c-4, disposition 5): the physical accept must not skip in CI.
PORTRAIT = Path(__file__).resolve().parent / "data" / "A_portrait.jpg"
_PAD = 64
_LUMAS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
_PLAIN = "@#*+=:.  "
def _srgb_grid(steps: int, palette: np.ndarray = BW) -> CellGrid:
    """Return the grid the pipeline builds for a black-to-white sRGB gradient of steps cells."""
    ramp = np.linspace(0.0, 1.0, steps, dtype=np.float32)[None, :, None]
    cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
    return _make_grid(cells, np.zeros((1, steps), np.int32), CELL_W, CELL_H, palette)
def _linear_grid(luma: list[float], index: list[int] | None = None,
                 cell_w: int = CELL_W, cell_h: int = CELL_H) -> CellGrid:
    """Return a one-row grid carrying the given literal linear luma values (S2)."""
    values = np.asarray(luma, dtype=np.float32)[None, :]
    cells = (np.zeros(values.shape, np.int32) if index is None
             else np.asarray(index, np.int32)[None, :])
    return CellGrid(cols=values.shape[1], rows=1, cell_w=cell_w, cell_h=cell_h,
                    index=np.ascontiguousarray(cells), coverage=values.copy(), luma=values.copy(),
                    samples=np.ascontiguousarray(values[:, :, None]))
def _style(**options: object) -> RenderStyle:
    """Return a RenderStyle carrying the given glyph_ramp options."""
    return RenderStyle(options=dict(options))
def _chars(grid: CellGrid, palette: np.ndarray = BW, **options: object) -> str:
    """Return the glyph characters layout() places, row-major, as one string."""
    placed = GlyphRampRenderer().layout(grid, palette, _style(**options))
    return "".join(e.character for e in placed)
def _cells(img) -> np.ndarray:
    """Return the rendered image as a (rows, cols, cell_h, cell_w, 3) uint8 array."""
    a = np.asarray(img)
    rows, cols = a.shape[0] // CELL_H, a.shape[1] // CELL_W
    return a.reshape(rows, CELL_H, cols, CELL_W, 3).transpose(0, 2, 1, 3, 4)
def _pillow_canvas(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
    """Return Pillow's own padded L canvas of glyph centred in a cell: an independent reference."""
    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
    ImageDraw.Draw(canvas).text((_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph,
                                font=ImageFont.load_default(size=size), fill=255, anchor="mm")
    return np.asarray(canvas)
def _pillow_ink(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
    """Return Pillow's own float32 ink of glyph centred in a cell, cropped to the cell."""
    patch = _pillow_canvas(glyph, cell_w, cell_h, size)[_PAD:_PAD + cell_h, _PAD:_PAD + cell_w]
    return np.ascontiguousarray(patch.astype(np.float32) / 255.0)
def _pillow_ink_bbox(glyph: str, cell_w: int, cell_h: int, size: int) -> tuple[int, int, int, int]:
    """Return the unclipped (top, bottom, left, right) ink box of glyph, relative to the cell."""
    rows, cols = np.nonzero(_pillow_canvas(glyph, cell_w, cell_h, size) > 0)
    return (int(rows.min()) - _PAD, int(rows.max()) - _PAD,
            int(cols.min()) - _PAD, int(cols.max()) - _PAD)
def _srgb_luma(rgb: np.ndarray) -> np.ndarray:
    """Return the sRGB-coded (γ-encoded) Rec.709 luma of a uint8 RGB image."""
    c = np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0)
    return (np.float32(.2126) * c[..., 0] + np.float32(.7152) * c[..., 1]
            + np.float32(.0722) * c[..., 2])
def _linear_luma(rgb: np.ndarray) -> np.ndarray:
    """Return the linear-light Rec.709 luma of a uint8 RGB image as a float32 array."""
    lin = color.srgb_to_linear(np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0))
    return (np.float32(.2126) * lin[..., 0] + np.float32(.7152) * lin[..., 1]
            + np.float32(.0722) * lin[..., 2])
def _dither_grid(src: np.ndarray, palette: np.ndarray, pixel_size: int) -> CellGrid:
    """Run the pipeline's dithering of src against palette and return the CellGrid it builds."""
    cell_w, cell_h = _cell_geometry(GlyphRampRenderer(), pixel_size)
    cells = _to_cells(_pad_to_cells(src, cell_w, cell_h), cell_w, cell_h)
    info = get_algorithm("floyd_steinberg")
    params = resolve_params(info.params, {})
    params[RESERVED_METRIC] = color.metric_code("srgb")
    idx = info.fn(color.to_working_space(cells, 0), color.to_working_space(palette, 0), params)
    return _make_grid(cells, np.ascontiguousarray(idx, np.int32), cell_w, cell_h, palette)
def _darkest_cells(grid: CellGrid) -> list[int]:
    """Return the flat positions of the darkest 20 % of cells, by source luma (S2)."""
    flat = grid.luma.ravel()
    count = max(1, int(round(0.2 * flat.size)))  # >= 1 even for n < 5 (L9c-4 restored guard)
    return np.argsort(flat)[:count].tolist()
def _placed(grid: CellGrid, palette: np.ndarray, **options: object) -> list[GlyphPlacement]:
    """Return the glyphs layout() places for grid on palette with the given options."""
    return GlyphRampRenderer().layout(grid, palette, _style(**options))
def _portrait_grid(pixel_size: int) -> tuple[CellGrid, np.ndarray]:
    """Return the dithered grid of the vendored H12 portrait on pico8 (never skips)."""
    pico8 = np.asarray(get_builtin("pico8"), np.float32)
    src = np.asarray(PILImage.open(PORTRAIT).convert("RGB"), np.float32) / 255.0
    return _dither_grid(src, pico8, pixel_size), pico8
def test_ten_character_ramp_on_a_gradient_places_the_ramp_in_order():
    assert _chars(_srgb_grid(10), ramp=RAMP) == "@%#*+=-:. "
    assert len(set(_chars(_srgb_grid(10), ramp=RAMP))) == 10
def test_five_step_gradient_pins_the_contract_buckets():
    assert _chars(_srgb_grid(5), ramp=RAMP) == "@#=: "
def test_ten_character_ramp_renders_ten_distinct_cells_with_monotone_ink():
    cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
    assert len({cells[0, c].tobytes() for c in range(10)}) == 10
    ink = [float(cells[0, c].mean()) for c in range(10)]
    assert ink[0] < ink[-1] and ink[0] == min(ink) and ink[-1] == max(ink)
def test_black_and_white_palette_keeps_all_ten_glyphs():
    assert len(set(_chars(_srgb_grid(10, BW), BW, ramp=RAMP))) == 10
def test_glyph_choice_is_independent_of_the_palette():
    assert _chars(_srgb_grid(10), BW, ramp=RAMP) == _chars(_srgb_grid(10), COLOUR, ramp=RAMP)
def test_consumes_is_exactly_luma_and_index():
    assert GlyphRampRenderer().consumes() == frozenset({"luma", "index"})
# L6 accept 3: offset is measured in RAMP units — 1/len(ramp) shifts exactly one glyph.
@pytest.mark.parametrize("offset,expected", [(0.0, _PLAIN), (1 / len(RAMP), "%*+=-.   "),
    (2 / len(RAMP), "#+=-:    "), (0.3, "*=-:.    "), (0.4, "+-:.     "), (0.5, "=:.      ")])
def test_offset_shifts_the_mapping_in_ramp_units(offset, expected):
    assert _chars(_linear_grid(_LUMAS), ramp=RAMP, offset=offset) == expected
def test_offset_is_clamped_at_both_ends():
    grid = _linear_grid([0.0, 0.3, 0.7, 1.0])
    assert _chars(grid, ramp=RAMP, offset=-5.0) == "@@@@"
    assert _chars(grid, ramp=RAMP, offset=5.0) == "    "
def test_invert_reverses_the_ramp():
    assert _chars(_linear_grid(_LUMAS), ramp=RAMP, invert=True) == " :-=+#%@@"
    assert _chars(_srgb_grid(10), ramp=RAMP, invert=True) == " .:-=+*#%@"
def test_palette_mode_renders_the_relative_ink():
    # H12 spec 2 (ÉCART 1): palette ink is relative too. COLOUR ranks: black 0, blue 1, red 2;
    # both fonds are dark (luma < 0.5) -> +2 ranks, clamped to red for both cells.
    grid = _linear_grid([0.05, 0.05], index=[1, 2])
    cells = _cells(GlyphRampRenderer().render(grid, COLOUR,
                                              _style(ramp=RAMP, mode="palette", bg="auto")))
    for cell in (cells[0, 0].reshape(-1, 3), cells[0, 1].reshape(-1, 3)):
        assert cell[:, 0].max() > 0 and cell[:, 1].max() == 0 and cell[:, 2].max() == 0
def test_palette_mode_fill_is_the_relative_ink_on_the_declared_bg():
    grid = _linear_grid([0.05, 0.05, 0.05], index=[0, 3, 4])
    placed = GlyphRampRenderer().layout(grid, GREYS, _style(mode="palette", bg="#ffffff"))
    assert [e.paper for e in placed] == ["#ffffff"] * 3
    assert [e.fill for e in placed] == ["#808080", "#404040", "#808080"]
def test_fg_colour_mode_takes_the_ink_from_the_palette_and_the_paper_from_bg():
    grid = _linear_grid([0.05], index=[1])
    style = _style(ramp=RAMP, mode="fg_colour", bg="#00ff00")
    flat = _cells(GlyphRampRenderer().render(grid, COLOUR, style))[0, 0].reshape(-1, 3)
    assert flat[:, 0].max() > 0 and flat[:, 2].max() == 0
    assert flat[:, 1].max() == 255 and flat[:, 0].max() < 255
def test_bg_colour_mode_puts_the_palette_colour_in_the_background():
    grid, style = _linear_grid([0.05], index=[1]), _style(mode="bg_colour")
    placed = GlyphRampRenderer().layout(grid, COLOUR, style)
    assert placed[0].paper == "#ff0000"  # the paper is the cell's palette colour
    pixels = np.asarray(GlyphRampRenderer().render(grid, COLOUR, style)).reshape(-1, 3)
    mask = _glyph_mask(placed[0].character, None, CELL_W, CELL_H).reshape(-1)
    assert np.all(pixels[mask <= 0.0] == np.array([255, 0, 0], np.uint8))
def test_bg_colour_ink_is_two_ranks_off_the_fond():
    grid = _linear_grid([0.05, 0.05, 0.05], index=[0, 3, 4])  # black, 0.75-grey, white fonds
    placed = _placed(grid, GREYS, mode="bg_colour")
    assert [e.paper for e in placed] == ["#000000", "#bfbfbf", "#ffffff"]
    assert placed[0].fill == placed[2].fill == "#808080"  # dark fond -> +2 ranks
    assert placed[1].fill == "#404040"  # 0.75-grey fond -> ink at rank 1
def test_bg_colour_ink_ignores_fg():
    grid = _linear_grid([0.05, 0.05], index=[0, 1])
    with_fg = _placed(grid, GREYS, mode="bg_colour", fg="#00ff00")
    without = _placed(grid, GREYS, mode="bg_colour")
    assert [(p.fill, p.paper) for p in with_fg] == [(p.fill, p.paper) for p in without]
    assert all(p.fill != "#00ff00" for p in with_fg)  # fg superseded by the relative ink
def test_bg_colour_ink_clamps_at_the_palette_edges():
    tiny = np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5], [1.0, 1.0, 1.0]], np.float32)
    grid = _linear_grid([0.05, 0.05], index=[0, 2])  # black and white fonds
    placed = _placed(grid, tiny, mode="bg_colour")
    assert placed[0].fill == "#ffffff"  # +2 above the darkest, clamped to white
    assert placed[1].fill == "#000000"  # -2 below the lightest, clamped to black
def test_bg_colour_ramp_excludes_the_two_extreme_glyphs():
    chars = _chars(_srgb_grid(10), BW, mode="bg_colour")
    assert set(chars) <= set(BOUNDED) and " " not in chars and "@" not in chars
def test_bg_colour_gap_pins_the_srgb_buckets():
    # A black fond (linear luma 0) makes the gap equal to the source luma; the BW span is 1
    # (identity), so each glyph is the sRGB-re-encoded bucket of the bounded ramp (AMD-010
    # extended to the gap). Pinned literals, never recomputed with the renderer's formula:
    assert _chars(_linear_grid([0.01, 0.05, 0.1, 0.2, 0.35, 0.6, 0.8, 0.95]),
                  BW, mode="bg_colour") == "%#*+-:.."
def test_bg_colour_offset_moves_one_glyph_per_bucket():
    grid = _linear_grid([0.1, 0.2, 0.35, 0.6])
    assert _chars(grid, BW, mode="bg_colour") == "*+-:"
    assert _chars(grid, BW, mode="bg_colour", offset=1 / len(BOUNDED)) == "+=:."
def test_bg_colour_invert_reverses_the_bounded_ramp():
    chars = _chars(_linear_grid([0.01, 0.6, 0.95]), BW, mode="bg_colour")
    inverted = _chars(_linear_grid([0.01, 0.6, 0.95]), BW, mode="bg_colour", invert=True)
    assert inverted == "".join(BOUNDED[::-1][BOUNDED.index(c)] for c in chars)
def test_bg_colour_glyph_follows_the_gap_not_the_absolute_luma():
    # Same absolute luma, different fonds -> different gaps -> different glyphs; an absolute-
    # luma implementation would draw the same character in both cells (H12 decision 3):
    grid = _linear_grid([0.05, 0.05], index=[0, 1])  # black fond, then mid-grey fond
    assert set(_chars(grid, GREYS, mode="bg_colour")) == {"%", "#"}
def test_mono_and_fg_colour_keep_absolute_luma_indexing():
    grid = _srgb_grid(10)
    assert _chars(grid, BW, ramp=RAMP) == _chars(grid, BW, ramp=RAMP, mode="fg_colour")
    assert _chars(grid, BW, ramp=RAMP) != _chars(grid, BW, mode="bg_colour")
def test_bg_colour_short_ramp_is_used_whole():
    chars = _chars(_srgb_grid(6), BW, mode="bg_colour", ramp=" x")
    assert set(chars) <= {" ", "x"}  # a ramp too short to bound is used as-is (E1)
def test_bg_colour_dark_palette_spreads_glyphs_without_saturation():
    # L9c-4 major fix: span³ amplified a max-luma-0.3 palette x37 and saturated the last rank;
    # the LINEAR span (max-min = 0.2957) keeps the gap in [0, 1]: 4 distinct medium glyphs,
    # no collapse onto either extreme (pinned literal, default ramp).
    dark = np.array([[0.0, 0.0, 0.0], [0.2, 0.2, 0.2], [0.4, 0.4, 0.4], [0.58, 0.58, 0.58]],
                    dtype=np.float32)
    assert float(glyph_ramp._palette_luma(dark).max()) <= 0.3
    grid = _linear_grid([0.01, 0.03, 0.06, 0.10, 0.15, 0.20, 0.25, 0.29],
                        index=[0, 0, 1, 1, 2, 2, 3, 3])
    chars = _chars(grid, dark, mode="bg_colour")
    assert chars == "#**=*=+#" and len(set(chars)) >= 4
    assert set(chars) != {BOUNDED[0]} and set(chars) != {BOUNDED[-1]}  # non-saturated
def test_bg_colour_single_entry_palette_keeps_the_raw_gap():
    # Degenerate palette (size 1): span <= epsilon -> 1, the raw gap indexes the bounded ramp.
    one = np.array([[0.2, 0.2, 0.2]], dtype=np.float32)
    grid = _linear_grid([0.0, 0.05, 0.2, 0.5, 1.0], index=[0] * 5)
    assert _chars(grid, one, mode="bg_colour") == "##+-."
def test_palette_mode_respects_a_declared_light_bg():
    # H12 accept 1: the declared white paper must carry the render (luma > 0.60), not the
    # letter alone; the ink is the relative +2-rank colour (red on the COLOUR palette).
    grid = _srgb_grid(16)
    img = GlyphRampRenderer().render(grid, COLOUR, _style(ramp=RAMP, mode="palette", bg="#ffffff"))
    assert float(_linear_luma(np.asarray(img)).mean()) > 0.60
    placed = _placed(grid, COLOUR, mode="palette", bg="#ffffff")
    assert [e.paper for e in placed] == ["#ffffff"] * 16
    assert [e.fill for e in placed] == ["#ff0000"] * 16  # H12 relative ink (+2 ranks)
def test_bg_auto_reproduces_the_old_palette_paper():
    # H12 ÉCART 1 (E1 declared): bg:"auto" selects the PAPER (old fond = darkest entry) and the
    # absolute-luma glyphs are kept; spec 2 mandates the relative ink in BOTH modes, so the ink
    # (hence the pixels) legitimately changes — the non-regression compares paper + glyphs only.
    grid = _srgb_grid(10)
    placed = _placed(grid, COLOUR, mode="palette", bg="auto")
    assert [p.paper for p in placed] == ["#000000"] * 10
    assert "".join(p.character for p in placed) == "@%#*+=-:. "
def test_bg_auto_without_a_palette_raises():
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().layout(_srgb_grid(4), _style(mode="palette", bg="auto"))
    assert "auto" in str(excinfo.value)
def test_fg_colour_mode_accepts_bg_auto_as_the_darkest_paper():
    grid = _linear_grid([0.05], index=[1])
    placed = GlyphRampRenderer().layout(grid, COLOUR, _style(mode="fg_colour", bg="auto"))
    assert placed[0].paper == "#000000" and placed[0].fill == "#ff0000"
# H12 accept 2 on the vendored A_portrait (pico8, floyd_steinberg): contrast = std of the sRGB
# luma; shadow glyphs = distinct layout() characters in the darkest 20 % of cells (argsort of
# grid.luma). The 12 px case is the H12 reference size: under the mandated LINEAR span it gives
# 4 shadow glyphs, not 5 — the 5th was only reachable by the rejected span³ knob. Human decision
# 2026-11-18 (E2 amended): contrast > 0.30 stays the product criterion (0.326 held), the count
# relaxes to >= 4 at 12 px while 8 px keeps its >= 5 pin. The literal (cell_w, cell_h) pins
# restore the 12 px geometry check.
@pytest.mark.parametrize("pixel_size,cell_w,cell_h,min_glyphs", [
    (8, 4, 8, 5),
    (12, 6, 12, 4),
])
def test_bg_colour_portrait_contrast_and_shadow_glyphs(pixel_size, cell_w, cell_h, min_glyphs):
    grid, pico8 = _portrait_grid(pixel_size)
    assert (grid.cell_w, grid.cell_h) == (cell_w, cell_h)  # literal §5 step-6 pin (L9c-4)
    img = GlyphRampRenderer().render(grid, pico8, _style(ramp=PICO8_RAMP, mode="bg_colour"))
    assert img.size == (grid.cols * cell_w, grid.rows * cell_h)  # literal (cols*6, rows*12) pin
    assert float(_srgb_luma(np.asarray(img)).std()) > 0.30
    chars = [p.character for p in _placed(grid, pico8, ramp=PICO8_RAMP, mode="bg_colour")]
    assert len({chars[i] for i in _darkest_cells(grid)}) >= min_glyphs  # H12 décision 18/11
def test_bg_colour_darkest_cells_carry_distinct_glyphs():
    # 25 cells: 5 dark (luma 0.01..0.35) on a black fond among 20 light; the darkest 20 % are
    # exactly the 5 dark cells and must span >= 5 distinct bounded glyphs (pinned literals).
    grid = _linear_grid([0.01, 0.05, 0.1, 0.2, 0.35] + [0.95] * 20, index=[0] * 5 + [1] * 20)
    chars = [p.character for p in _placed(grid, BW, mode="bg_colour")]
    assert "".join(chars[:5]) == "%#*+-"
    assert len({chars[i] for i in _darkest_cells(grid)}) >= 5
    assert set(chars) <= set(BOUNDED)
@pytest.mark.parametrize(("rows", "cols", "cell_w", "cell_h"), [(3, 4, 8, 16), (1, 1, 5, 7)])
def test_output_size_is_exactly_the_grid_geometry(rows, cols, cell_w, cell_h):
    luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
    grid = CellGrid(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma,
                    samples=luma[:, :, None].copy())
    size = GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)).size
    assert size == (cols * cell_w, rows * cell_h)
def test_output_size_matches_the_pipeline_geometry():
    src = np.linspace(0.0, 1.0, 64 * 96, dtype=np.float32).reshape(64, 96, 1)
    src = np.ascontiguousarray(np.repeat(src, 3, axis=2))
    spec = PipelineSpec(pixel_size=8, renderer="glyph_ramp", renderer_style={"ramp": RAMP})
    out = render_with_palette(src, spec, BW)
    assert out.shape == (64, 96, 3) and out.dtype == np.uint8
def test_missing_font_file_raises_value_error_naming_the_path():
    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, font=path))
    assert path in str(excinfo.value)
def test_missing_font_file_raises_from_layout_and_from_an_empty_grid():
    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
    style = _style(ramp=RAMP, font=path)
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().layout(_srgb_grid(4), BW, style)
    assert path in str(excinfo.value)
    empty = CellGrid(cols=0, rows=0, cell_w=CELL_W, cell_h=CELL_H,
                     index=np.zeros((0, 0), np.int32), coverage=np.zeros((0, 0), np.float32),
                     luma=np.zeros((0, 0), np.float32), samples=np.zeros((0, 0, 1), np.float32))
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().render(empty, BW, style)
    assert path in str(excinfo.value)
def test_font_option_accepts_a_real_font_file():
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    img = GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, font=str(SYSTEM_FONT)))
    assert img.size == (4 * CELL_W, CELL_H)
@pytest.mark.parametrize("palette,mode", [(BW, "mono"), (GREYS, "bg_colour")])
def test_render_is_pure(palette, mode):
    grid, renderer = _srgb_grid(10), GlyphRampRenderer()
    style = _style(ramp=RAMP, mode=mode)
    assert np.array_equal(np.asarray(renderer.render(grid, palette, style)),
                          np.asarray(renderer.render(grid, palette, style)))
def test_render_does_not_mutate_grid_or_palette():
    grid, palette = _srgb_grid(10), BW.copy()
    snapshot = (grid.index.copy(), grid.luma.copy(), grid.samples.copy(), grid.coverage.copy())
    GlyphRampRenderer().render(grid, palette, _style(ramp=RAMP, mode="palette"))
    arrays = (grid.index, grid.luma, grid.samples, grid.coverage)
    for arr, snap in zip(arrays, snapshot, strict=True):
        assert np.array_equal(arr, snap)
    assert np.array_equal(palette, BW)
def test_module_state_is_a_bounded_input_keyed_cache():
    cache = glyph_ramp._cached_mask
    cache.cache_clear()
    for cell_w in range(1, 24):
        for cell_h in (cell_w * 2, cell_w * 2 + 1):
            for glyph in RAMP:
                glyph_ramp._glyph_mask(glyph, None, cell_w, cell_h)
    info = cache.cache_info()
    assert info.maxsize is not None and info.currsize <= info.maxsize
    assert info.currsize < 24 * 2 * len(RAMP)
def test_cached_masks_are_read_only():
    mask = glyph_ramp._glyph_mask("@", None, CELL_W, CELL_H)
    assert not mask.flags.writeable
    with pytest.raises(ValueError):
        mask[0, 0] = 1.0
def test_a_font_replaced_at_the_same_path_is_a_new_cache_key(tmp_path):
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    copied = tmp_path / "font.ttf"
    copied.write_bytes(SYSTEM_FONT.read_bytes())
    first = glyph_ramp._font_key(str(copied))
    glyph_ramp._glyph_mask("M", str(copied), CELL_W, CELL_H)
    copied.write_bytes(SYSTEM_FONT.read_bytes() + b"\0")
    assert glyph_ramp._font_key(str(copied)) != first
def test_renderer_is_registered_under_a_unique_stable_name():
    renderer = GlyphRampRenderer()
    assert renderer.name == "glyph_ramp"
    assert get_renderer("glyph_ramp").name == "glyph_ramp"
    assert "glyph_ramp" in list_renderers()
    assert isinstance(renderer, CellRenderer)
def test_cell_aspect_is_the_monospace_ratio():
    assert GlyphRampRenderer().cell_aspect() == 0.5 and GlyphRampRenderer().subgrid() == (1, 1)
def test_style_options_round_trip_through_the_renderer():
    options = {"ramp": RAMP, "mode": "palette", "offset": 0.25, "invert": True,
               "fg": "#112233", "bg": "transparent", "font": None}
    grid, palette = _srgb_grid(6), COLOUR
    style = _style(**options)
    assert json.loads(json.dumps(dict(style.options))) == options
    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
    assert np.array_equal(np.asarray(GlyphRampRenderer().render(grid, palette, style)),
                          np.asarray(GlyphRampRenderer().render(grid, palette, reloaded)))
def test_layout_places_one_glyph_per_cell_row_major():
    grid = _srgb_grid(10)
    placed = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP))
    assert len(placed) == grid.rows * grid.cols
    assert all(isinstance(e, GlyphPlacement) for e in placed)
    for col, e in enumerate(placed):
        assert e.x == col * CELL_W and e.y == 0.0
        assert e.width == CELL_W and e.height == CELL_H
def test_layout_accepts_both_call_forms():
    grid, style = _srgb_grid(4), _style(ramp=RAMP)
    assert GlyphRampRenderer().layout(grid, style) == GlyphRampRenderer().layout(grid, BW, style)
def test_layout_reports_alpha_and_transparent_paper():
    grid = _linear_grid([0.05])
    clear = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="transparent"))[0]
    assert clear.paper == "transparent"
    half = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="#ff000080"))[0]
    assert half.paper == "#ff000080"
def test_there_is_no_size_option():
    grid = _srgb_grid(6)
    plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
    with_size = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, size=48)))
    assert np.array_equal(plain, with_size)
def test_glyph_font_size_derives_from_the_cell():
    # Height-binding geometry (DEV-213): by_height = 4/1.20 ~= 3.33 binds, by_width = 4/0.87
    # ~= 4.60 — a width-only computation would give 5. Pinned sizes + independent Pillow ink.
    assert _font_size(4, 4, None) == 3
    pinned = {(8, 16): 9, (6, 12): 7, (12, 24): 14, (20, 40): 23, (10, 20): 11, (4, 8): 5}
    for (cell_w, cell_h), size in pinned.items():
        assert _font_size(cell_w, cell_h, None) == size
        assert np.array_equal(_glyph_mask("@", None, cell_w, cell_h),
                              _pillow_ink("@", cell_w, cell_h, size))
def test_glyph_ink_stays_inside_the_cell_and_is_horizontally_centred():
    for cell_h in (12, 24, 40):
        cell_w = cell_h // 2
        mask = _glyph_mask("@", None, cell_w, cell_h)
        assert mask.shape == (cell_h, cell_w)
        size = _font_size(cell_w, cell_h, None)
        top, bottom, left, right = _pillow_ink_bbox("@", cell_w, cell_h, size)
        assert 0 <= top and bottom <= cell_h - 1 and 0 <= left and right <= cell_w - 1
        assert abs((left + right) / 2.0 - (cell_w - 1) / 2.0) <= 1.0
        rows, cols = np.nonzero(mask > 0.0)
        assert rows.min() >= 0 and rows.max() <= cell_h - 1
        assert cols.min() >= 0 and cols.max() <= cell_w - 1
        assert 0.0 < float(mask.mean()) < 1.0
def test_unknown_style_keys_are_ignored_for_forward_compatibility():
    grid = _srgb_grid(6)
    plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
    future = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, glow=0.7)))
    assert np.array_equal(plain, future)
@pytest.mark.parametrize("options,match", [({"ramp": ""}, None), ({"mode": "vibrant"}, "fg_colour"),
                                           ({"fg": "not-a-colour"}, None)])
def test_invalid_options_raise_value_error(options, match):
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(**options))
    if match is not None:
        assert match in str(excinfo.value)
def test_default_ramp_is_darkest_first_and_documented():
    assert DEFAULT_RAMP[0] == "@" and DEFAULT_RAMP[-1] == " "
    assert float(_glyph_mask(DEFAULT_RAMP[0], None, CELL_W, CELL_H).mean()) > 0.0
def test_transparent_background_produces_an_rgba_image():
    img = GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, bg="transparent"))
    assert img.mode == "RGBA" and img.size == (4 * CELL_W, CELL_H)
def test_flat_luma_collapses_to_a_single_glyph():
    assert set(_chars(_linear_grid([0.0, 0.0, 0.0]), ramp=RAMP)) == {RAMP[0]}
    assert set(_chars(_linear_grid([1.0, 1.0, 1.0]), ramp=RAMP)) == {RAMP[-1]}
def test_luma_is_linear_light_not_srgb():
    grid = _srgb_grid(10)
    ramp = np.linspace(0.0, 1.0, 10, dtype=np.float32)[None, :, None]
    linear = color.srgb_to_linear(np.ascontiguousarray(np.repeat(ramp, 3, axis=2)))[0]
    expected = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
    assert np.allclose(grid.luma[0], expected, atol=1e-6)
