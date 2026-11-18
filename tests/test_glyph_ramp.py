"""Tests for the glyph_ramp renderer (§3, §9, AMD-010) — cards L6 and L9c.

Expected glyph sequences are pinned as literals derived from the contract, never recomputed
with the renderer's own formula: §9 + AMD-010 say ``luma`` (S2) indexes the ramp through its
sRGB-perceptual encoding, so a linear luma of 0.05 encodes to sRGB 0.2478, lands in bucket 2
of a 10-character ramp and must draw ``'#'``. Since H12 (2026-11-18) ``bg_colour`` glyphs
follow the |luma - background| gap over the ramp bounded to its medium densities, its ink is
the palette entry two ranks off the cell colour, and ``palette`` honours the declared ``bg``
(whose explicit value ``"auto"`` is the palette's darkest entry).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

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
BOUNDED = RAMP[1:-1]  # "%#*+=-:." — the H12 bg_colour ramp, extremes (space, '@') removed
PICO8_RAMP = " .:-=+*#%@"
BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
GREYS: Palette = np.array([[0.0, 0.0, 0.0], [0.25, 0.25, 0.25], [0.5, 0.5, 0.5],
                           [0.75, 0.75, 0.75], [1.0, 1.0, 1.0]], dtype=np.float32)
COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
                           dtype=np.float32)
CELL_W, CELL_H = 8, 16
SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
PORTRAIT = Path("/home/mar1/Téléchargements/H12/A_portrait.jpg")
_PAD = 64


def _srgb_grid(steps: int, palette: np.ndarray = BW) -> CellGrid:
    """Return the grid the pipeline builds for a black-to-white sRGB gradient of steps cells."""
    ramp = np.linspace(0.0, 1.0, steps, dtype=np.float32)[None, :, None]
    cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
    return _make_grid(cells, np.zeros((1, steps), np.int32), CELL_W, CELL_H, palette)


def _linear_grid(
    luma: list[float], index: list[int] | None = None,
    cell_w: int = CELL_W, cell_h: int = CELL_H,
) -> CellGrid:
    """Return a one-row grid carrying the given literal linear luma values (S2)."""
    values = np.asarray(luma, dtype=np.float32)[None, :]
    cells = np.zeros(values.shape, dtype=np.int32) if index is None else np.asarray(
        index, dtype=np.int32
    )[None, :]
    return CellGrid(
        cols=values.shape[1], rows=1, cell_w=cell_w, cell_h=cell_h,
        index=np.ascontiguousarray(cells), coverage=values.copy(), luma=values.copy(),
        samples=np.ascontiguousarray(values[:, :, None]),
    )


def _style(**options: object) -> RenderStyle:
    """Return a RenderStyle carrying the given glyph_ramp options."""
    return RenderStyle(options=dict(options))


def _chars(grid: CellGrid, palette: np.ndarray = BW, **options: object) -> str:
    """Return the glyph characters layout() places, row-major, as one string."""
    return "".join(entry.character for entry in GlyphRampRenderer().layout(
        grid, palette, _style(**options)
    ))


def _cells(img) -> np.ndarray:
    """Return the rendered image as a (rows, cols, cell_h, cell_w, 3) uint8 array."""
    array = np.asarray(img)
    rows, cols = array.shape[0] // CELL_H, array.shape[1] // CELL_W
    return array.reshape(rows, CELL_H, cols, CELL_W, 3).transpose(0, 2, 1, 3, 4)


def _pillow_ink(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
    """Return Pillow's own float32 ink of glyph centred in a cell: an independent reference."""
    font = _default_font(size)
    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
    ImageDraw.Draw(canvas).text(
        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
    )
    patch = np.asarray(canvas, dtype=np.float32)[_PAD : _PAD + cell_h, _PAD : _PAD + cell_w]
    return np.ascontiguousarray(patch / 255.0)


def _pillow_ink_bbox(glyph: str, cell_w: int, cell_h: int, size: int) -> tuple[int, int, int, int]:
    """Return the unclipped (top, bottom, left, right) ink box of glyph, relative to the cell."""
    font = ImageFont.load_default(size=size)
    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
    ImageDraw.Draw(canvas).text(
        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
    )
    rows, cols = np.nonzero(np.asarray(canvas) > 0)
    return (int(rows.min()) - _PAD, int(rows.max()) - _PAD,
            int(cols.min()) - _PAD, int(cols.max()) - _PAD)


def _default_font(size: int) -> ImageFont.FreeTypeFont:
    """Return Pillow's bundled default font at size, typed as the FreeType font it is."""
    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))


def _linear_luma(rgb: np.ndarray) -> np.ndarray:
    """Return the linear-light Rec.709 luma of a uint8 RGB image as a float32 array."""
    linear = color.srgb_to_linear(np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0))
    return np.float32(0.2126) * linear[..., 0] + np.float32(0.7152) * linear[..., 1] \
        + np.float32(0.0722) * linear[..., 2]


def _srgb_luma(rgb: np.ndarray) -> np.ndarray:
    """Return the sRGB-coded (γ-encoded) Rec.709 luma of a uint8 RGB image."""
    code = np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0)
    return np.float32(0.2126) * code[..., 0] + np.float32(0.7152) * code[..., 1] \
        + np.float32(0.0722) * code[..., 2]


def _dither_grid(src: np.ndarray, palette: np.ndarray, pixel_size: int) -> CellGrid:
    """Run the pipeline's dithering of src against palette and return the CellGrid it builds."""
    cell_w, cell_h = _cell_geometry(GlyphRampRenderer(), pixel_size)
    cells = _to_cells(_pad_to_cells(src, cell_w, cell_h), cell_w, cell_h)
    info = get_algorithm("floyd_steinberg")
    params = resolve_params(info.params, {})
    params[RESERVED_METRIC] = color.metric_code("srgb")
    indices = info.fn(color.to_working_space(cells, 0), color.to_working_space(palette, 0),
                      params)
    return _make_grid(cells, np.ascontiguousarray(indices, np.int32), cell_w, cell_h, palette)


def _darkest_cells(grid: CellGrid) -> list[int]:
    """Return the flat positions of the darkest 20 % of cells, by source luma (S2)."""
    count = max(1, int(round(0.2 * int(grid.luma.size))))
    return np.argpartition(grid.luma.ravel(), count)[:count].tolist()


def _placed(grid: CellGrid, palette: np.ndarray, **options: object) -> list[GlyphPlacement]:
    """Return the glyphs layout() places for grid on palette with the given options."""
    return GlyphRampRenderer().layout(grid, palette, _style(**options))


# --- accept 1 (L6): a 10-character ramp on a black-to-white gradient ---


def test_ten_character_ramp_on_a_gradient_places_the_ramp_in_order():
    assert _chars(_srgb_grid(10), ramp=RAMP) == "@%#*+=-:. "
    assert len(set(_chars(_srgb_grid(10), ramp=RAMP))) == 10


def test_five_step_gradient_pins_the_contract_buckets():
    ramp = np.linspace(0.0, 1.0, 5, dtype=np.float32)[None, :, None]
    cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
    grid = _make_grid(cells, np.zeros((1, 5), np.int32), CELL_W, CELL_H, BW)
    assert _chars(grid, ramp=RAMP) == "@#=: "


def test_ten_character_ramp_renders_ten_distinct_cells():
    cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
    assert len({cells[0, col].tobytes() for col in range(10)}) == 10


def test_glyph_ink_decreases_as_the_cell_luma_rises():
    cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
    ink = [float(cells[0, col].mean()) for col in range(10)]
    assert ink[0] < ink[-1]
    assert ink[0] == min(ink) and ink[-1] == max(ink)


# --- accept 2 (L6): a black/white palette does not collapse the ramp (S2/H11) ---


def test_black_and_white_palette_keeps_all_ten_glyphs():
    assert len(set(_chars(_srgb_grid(10, BW), BW, ramp=RAMP))) == 10


def test_glyph_choice_is_independent_of_the_palette():
    grid = _srgb_grid(10)
    assert _chars(grid, BW, ramp=RAMP) == _chars(grid, COLOUR, ramp=RAMP)


def test_consumes_is_exactly_luma_and_index():
    assert GlyphRampRenderer().consumes() == frozenset({"luma", "index"})


# --- accept 3 (L6): offset shifts the mapping by exactly one glyph per 1/len(ramp) ---

_LUMAS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
_PLAIN = "@#*+=:.  "


def test_offset_zero_draws_the_pinned_ramp_positions():
    assert _chars(_linear_grid(_LUMAS), ramp=RAMP) == _PLAIN


def test_offset_shifts_the_mapping_by_exactly_one_glyph():
    grid = _linear_grid(_LUMAS)
    assert _chars(grid, ramp=RAMP, offset=1 / len(RAMP)) == "%*+=-.   "
    assert _chars(grid, ramp=RAMP, offset=2 / len(RAMP)) == "#+=-:    "


def test_offset_is_measured_in_ramp_units_not_pixels():
    grid = _linear_grid(_LUMAS)
    for offset, expected in {
        0.1: "%*+=-.   ", 0.2: "#+=-:    ", 0.3: "*=-:.    ",
        0.4: "+-:.     ", 0.5: "=:.      ",
    }.items():
        assert _chars(grid, ramp=RAMP, offset=offset) == expected


def test_offset_is_clamped_at_both_ends():
    grid = _linear_grid([0.0, 0.3, 0.7, 1.0])
    assert _chars(grid, ramp=RAMP, offset=-5.0) == "@@@@"
    assert _chars(grid, ramp=RAMP, offset=5.0) == "    "


# --- accept 4 (L6): invert reverses the ramp ---


def test_invert_reverses_the_ramp():
    grid = _linear_grid(_LUMAS)
    assert _chars(grid, ramp=RAMP, invert=True) == " :-=+#%@@"
    assert _chars(_srgb_grid(10), ramp=RAMP, invert=True) == " .:-=+*#%@"


# --- accept 5 (L6): mode "palette" gives each glyph the palette colour of its cell ---


def test_palette_mode_gives_each_glyph_its_cell_palette_colour():
    grid = _linear_grid([0.05, 0.05], index=[1, 2])
    cells = _cells(GlyphRampRenderer().render(grid, COLOUR,
                                              _style(ramp=RAMP, mode="palette", bg="auto")))
    red, blue = cells[0, 0].reshape(-1, 3), cells[0, 1].reshape(-1, 3)
    assert red[:, 0].max() > 0 and red[:, 1].max() == 0 and red[:, 2].max() == 0
    assert blue[:, 2].max() > 0 and blue[:, 0].max() == 0 and blue[:, 1].max() == 0


def test_palette_mode_fill_is_the_cell_palette_colour():
    grid = _linear_grid([0.05, 0.05], index=[1, 2])
    placed = GlyphRampRenderer().layout(grid, COLOUR, _style(mode="palette"))
    assert [entry.fill for entry in placed] == ["#ff0000", "#0000ff"]


def test_fg_colour_mode_takes_the_ink_from_the_palette_and_the_paper_from_bg():
    grid = _linear_grid([0.05], index=[1])
    style = _style(ramp=RAMP, mode="fg_colour", bg="#00ff00")
    flat = _cells(GlyphRampRenderer().render(grid, COLOUR, style))[0, 0].reshape(-1, 3)
    assert flat[:, 0].max() > 0 and flat[:, 2].max() == 0
    assert flat[:, 1].max() == 255 and flat[:, 0].max() < 255


# --- accept 6 (L6) + H12: bg_colour paper is the cell colour, ink is relative (two ranks) ---


def test_bg_colour_mode_puts_the_palette_colour_in_the_background():
    grid = _linear_grid([0.05], index=[1])
    style = _style(mode="bg_colour")
    renderer = GlyphRampRenderer()
    placed = renderer.layout(grid, COLOUR, style)
    assert placed[0].paper == "#ff0000"  # the paper is the cell's palette colour
    pixels = np.asarray(renderer.render(grid, COLOUR, style)).reshape(-1, 3)
    mask = _glyph_mask(placed[0].character, None, CELL_W, CELL_H).reshape(-1)
    assert np.all(pixels[mask <= 0.0] == np.array([255, 0, 0], np.uint8))


def test_bg_colour_ink_is_two_ranks_off_the_fond():
    grid = _linear_grid([0.05, 0.05, 0.05], index=[0, 3, 4])  # black, 0.75-grey, white fonds
    placed = _placed(grid, GREYS, mode="bg_colour")
    assert [entry.paper for entry in placed] == ["#000000", "#bfbfbf", "#ffffff"]
    # a dark fond (luma < 0.5) takes the ink two ranks above (rank 2), a light one two below
    assert placed[0].fill == placed[2].fill == "#808080"
    assert placed[1].fill == "#404040"  # 0.75-grey fond -> ink at rank 1


def test_bg_colour_ink_ignores_fg():
    grid = _linear_grid([0.05, 0.05], index=[0, 1])
    with_fg = _placed(grid, GREYS, mode="bg_colour", fg="#00ff00")
    without = _placed(grid, GREYS, mode="bg_colour")
    assert [(p.fill, p.paper) for p in with_fg] == [(p.fill, p.paper) for p in without]
    assert all(p.fill != "#00ff00" for p in with_fg)  # fg is superseded by the relative ink


def test_bg_colour_ink_clamps_at_the_palette_edges():
    tiny = np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5], [1.0, 1.0, 1.0]], np.float32)
    grid = _linear_grid([0.05, 0.05], index=[0, 2])  # black and white fonds
    placed = _placed(grid, tiny, mode="bg_colour")
    assert placed[0].fill == "#ffffff"  # two ranks above the darkest, clamped to white
    assert placed[1].fill == "#000000"  # two ranks below the lightest, clamped to black


# --- H12 accept 2: bg_colour glyphs follow the |luma - background| gap (not absolute luma) ---


def test_bg_colour_ramp_excludes_the_two_extreme_glyphs():
    chars = _chars(_srgb_grid(10), BW, mode="bg_colour")
    assert set(chars) <= set(BOUNDED)
    assert " " not in chars and "@" not in chars  # space (density 0) and '@' are removed


def test_bg_colour_gap_pins_the_srgb_buckets():
    # A black fond (linear luma 0) makes the gap equal to the source luma; each glyph is the
    # sRGB-re-encoded bucket of the bounded ramp (AMD-010 extended to the gap). Pinned literals:
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
    # Same absolute luma, different fonds -> different gaps -> different glyphs (an absolute-
    # luma implementation would draw the same character in both cells):
    grid = _linear_grid([0.05, 0.05], index=[0, 1])  # black fond, then mid-grey fond
    assert set(_chars(grid, GREYS, mode="bg_colour")) == {"%", "#"}


def test_mono_and_fg_colour_keep_absolute_luma_indexing():
    grid = _srgb_grid(10)
    assert _chars(grid, BW, ramp=RAMP) == _chars(grid, BW, ramp=RAMP, mode="fg_colour")
    assert _chars(grid, BW, ramp=RAMP) != _chars(grid, BW, mode="bg_colour")


def test_bg_colour_short_ramp_is_used_whole():
    chars = _chars(_srgb_grid(6), BW, mode="bg_colour", ramp=" x")
    assert set(chars) <= {" ", "x"}  # a ramp too short to bound is used as-is (E1)


# --- H12 accept 1: palette mode respects the declared bg, auto = the darkest palette tone ---


def test_palette_mode_respects_a_declared_light_bg():
    grid = _srgb_grid(16)
    img = GlyphRampRenderer().render(grid, COLOUR, _style(ramp=RAMP, mode="palette",
                                                          bg="#ffffff"))
    assert float(_linear_luma(np.asarray(img)).mean()) > 0.60
    placed = _placed(grid, COLOUR, mode="palette", bg="#ffffff")
    assert [entry.paper for entry in placed] == ["#ffffff"] * 16
    assert [entry.fill for entry in placed] == ["#000000"] * 16  # ink stays the cell colour


def test_bg_auto_reproduces_the_old_palette_mode():
    grid = _srgb_grid(10)
    placed = _placed(grid, COLOUR, mode="palette", bg="auto")
    assert [p.paper for p in placed] == ["#000000"] * 10          # darkest paper preserved
    assert [p.fill for p in placed] == ["#000000"] * 10           # cell-palette ink preserved
    assert "".join(p.character for p in placed) == "@%#*+=-:. "   # absolute-luma glyphs kept


def test_bg_auto_without_a_palette_raises():
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().layout(_srgb_grid(4), _style(mode="palette", bg="auto"))
    assert "auto" in str(excinfo.value)


def test_fg_colour_mode_accepts_bg_auto_as_the_darkest_paper():
    grid = _linear_grid([0.05], index=[1])
    placed = GlyphRampRenderer().layout(grid, COLOUR, _style(mode="fg_colour", bg="auto"))
    assert placed[0].paper == "#000000" and placed[0].fill == "#ff0000"


# --- H12 accept 2 (physical): bg_colour on the H12 portrait (pico8, 4x8 mesh) ---


def test_bg_colour_portrait_contrast_and_distinct_shadow_glyphs():
    if not PORTRAIT.is_file():
        pytest.skip("no H12 portrait image available")
    pico8 = np.asarray(get_builtin("pico8"), np.float32)
    src = np.asarray(PILImage.open(PORTRAIT).convert("RGB"), np.float32) / 255.0
    grid = _dither_grid(src, pico8, 8)
    img = GlyphRampRenderer().render(grid, pico8, _style(ramp=PICO8_RAMP, mode="bg_colour"))
    assert float(_srgb_luma(np.asarray(img)).std()) > 0.30   # contrast on the H12 reference scale
    chars = [p.character for p in _placed(grid, pico8, ramp=PICO8_RAMP, mode="bg_colour")]
    distinct = len({chars[i] for i in _darkest_cells(grid)})
    assert distinct >= 5, "the darkest 20 % of cells must carry at least 5 distinct glyphs"


def test_bg_colour_portrait_cell_size_12_holds():
    if not PORTRAIT.is_file():
        pytest.skip("no H12 portrait image available")
    pico8 = np.asarray(get_builtin("pico8"), np.float32)
    src = np.asarray(PILImage.open(PORTRAIT).convert("RGB"), np.float32) / 255.0
    grid = _dither_grid(src, pico8, 12)
    img = GlyphRampRenderer().render(grid, pico8, _style(ramp=PICO8_RAMP, mode="bg_colour"))
    assert img.size == (grid.cols * 6, grid.rows * 12)         # exact 12 px geometry
    assert float(_srgb_luma(np.asarray(img)).std()) > 0.30     # contrast still holds
    chars = [p.character for p in _placed(grid, pico8, ramp=PICO8_RAMP, mode="bg_colour")]
    distinct = len({chars[i] for i in _darkest_cells(grid)})
    assert distinct >= 3, "shadows are not mute even at 12 px cells (cell size is not the fix)"


# --- H12 accept 2 (synthetic): deterministic and independent of any external image ---


def test_bg_colour_darkest_cells_carry_distinct_glyphs():
    # 25 cells: 5 dark (luma 0.01..0.35) on a black fond among 20 light; the darkest 20 % are
    # exactly the 5 dark cells and must span >= 5 distinct bounded glyphs (pinned literals).
    dark = [0.01, 0.05, 0.1, 0.2, 0.35]
    grid = _linear_grid(dark + [0.95] * 20, index=[0] * 5 + [1] * 20)
    chars = [p.character for p in _placed(grid, BW, mode="bg_colour")]
    assert "".join(chars[:5]) == "%#*+-"
    assert len({chars[i] for i in _darkest_cells(grid)}) >= 5
    assert set(chars) <= set(BOUNDED)


# --- accept 7 (L6): output size is exactly (cols * cell_w, rows * cell_h) ---


@pytest.mark.parametrize(("rows", "cols", "cell_w", "cell_h"), [(3, 4, 8, 16), (1, 1, 5, 7)])
def test_output_size_is_exactly_the_grid_geometry(rows, cols, cell_w, cell_h):
    luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
    grid = CellGrid(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma,
                    samples=luma[:, :, None].copy())
    expected = (cols * cell_w, rows * cell_h)
    assert GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)).size == expected


def test_output_size_matches_the_pipeline_geometry():
    src = np.linspace(0.0, 1.0, 64 * 96, dtype=np.float32).reshape(64, 96, 1)
    src = np.ascontiguousarray(np.repeat(src, 3, axis=2))
    spec = PipelineSpec(pixel_size=8, renderer="glyph_ramp", renderer_style={"ramp": RAMP})
    out = render_with_palette(src, spec, BW)
    assert out.shape == (64, 96, 3)
    assert out.dtype == np.uint8


# --- accept 8 (L6): a missing font file raises ValueError naming the path ---


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


# --- §3 invariants ---


def test_render_is_pure():
    grid = _srgb_grid(10)
    renderer = GlyphRampRenderer()
    assert np.array_equal(
        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
    )


def test_bg_colour_render_is_pure():
    grid = _srgb_grid(10)
    renderer = GlyphRampRenderer()
    style = _style(ramp=RAMP, mode="bg_colour")
    assert np.array_equal(np.asarray(renderer.render(grid, GREYS, style)),
                          np.asarray(renderer.render(grid, GREYS, style)))


def test_render_does_not_mutate_grid_or_palette():
    grid = _srgb_grid(10)
    palette = BW.copy()
    snapshot = (grid.index.copy(), grid.luma.copy(), grid.samples.copy(), grid.coverage.copy())
    GlyphRampRenderer().render(grid, palette, _style(ramp=RAMP, mode="palette"))
    assert np.array_equal(grid.index, snapshot[0])
    assert np.array_equal(grid.luma, snapshot[1])
    assert np.array_equal(grid.samples, snapshot[2])
    assert np.array_equal(grid.coverage, snapshot[3])
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
    assert GlyphRampRenderer().cell_aspect() == 0.5
    assert GlyphRampRenderer().subgrid() == (1, 1)


def test_style_options_round_trip_through_the_renderer():
    options = {"ramp": RAMP, "mode": "palette", "offset": 0.25, "invert": True,
               "fg": "#112233", "bg": "transparent", "font": None}
    grid, palette = _srgb_grid(6), COLOUR
    style = _style(**options)
    assert json.loads(json.dumps(dict(style.options))) == options
    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
    assert np.array_equal(
        np.asarray(GlyphRampRenderer().render(grid, palette, style)),
        np.asarray(GlyphRampRenderer().render(grid, palette, reloaded)),
    )


# --- layout() consistency with render() ---


def test_layout_places_one_glyph_per_cell_row_major():
    grid = _srgb_grid(10)
    placed = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP))
    assert len(placed) == grid.rows * grid.cols
    assert all(isinstance(entry, GlyphPlacement) for entry in placed)
    for col, entry in enumerate(placed):
        assert entry.x == col * CELL_W and entry.y == 0.0
        assert entry.width == CELL_W and entry.height == CELL_H


def test_layout_accepts_both_call_forms():
    grid, style = _srgb_grid(4), _style(ramp=RAMP)
    assert GlyphRampRenderer().layout(grid, style) == GlyphRampRenderer().layout(grid, BW, style)


def test_layout_reports_alpha_and_transparent_paper():
    grid = _linear_grid([0.05])
    clear = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="transparent"))[0]
    assert clear.paper == "transparent"
    half = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="#ff000080"))[0]
    assert half.paper == "#ff000080"


# --- H11: no size option, font size derives from cell_h ---


def test_there_is_no_size_option():
    grid = _srgb_grid(6)
    plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
    with_size = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, size=48)))
    assert np.array_equal(plain, with_size)


def test_glyph_font_size_derives_from_the_cell():
    # geometry en hauteur liante (cell non-2x1) : by_height = 4/1.20 ~= 3.33 lie
    # (by_width = 4/0.87 ~= 4.60) — un calcul largeur-seule donnerait 5 (DEV-213)
    assert _font_size(4, 4, None) == 3
    pinned = {(8, 16): 9, (6, 12): 7, (12, 24): 14, (20, 40): 23, (10, 20): 11, (4, 8): 5}
    for (cell_w, cell_h), size in pinned.items():
        assert _font_size(cell_w, cell_h, None) == size
        assert np.array_equal(
            _glyph_mask("@", None, cell_w, cell_h), _pillow_ink("@", cell_w, cell_h, size)
        )


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


# --- option validation and edge cases ---


def test_empty_ramp_raises_value_error():
    with pytest.raises(ValueError):
        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=""))


def test_unknown_mode_raises_value_error_naming_the_modes():
    with pytest.raises(ValueError) as excinfo:
        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(mode="vibrant"))
    assert "fg_colour" in str(excinfo.value)


def test_invalid_colour_raises_value_error():
    with pytest.raises(ValueError):
        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(fg="not-a-colour"))


def test_default_ramp_is_darkest_first_and_documented():
    assert DEFAULT_RAMP[0] == "@"
    assert DEFAULT_RAMP[-1] == " "
    assert float(_glyph_mask(DEFAULT_RAMP[0], None, CELL_W, CELL_H).mean()) > 0.0


def test_transparent_background_produces_an_rgba_image():
    img = GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, bg="transparent"))
    assert img.mode == "RGBA"
    assert img.size == (4 * CELL_W, CELL_H)


def test_flat_luma_collapses_to_a_single_glyph():
    assert set(_chars(_linear_grid([0.0, 0.0, 0.0]), ramp=RAMP)) == {RAMP[0]}
    assert set(_chars(_linear_grid([1.0, 1.0, 1.0]), ramp=RAMP)) == {RAMP[-1]}


def test_luma_is_linear_light_not_srgb():
    grid = _srgb_grid(10)
    ramp = np.linspace(0.0, 1.0, 10, dtype=np.float32)[None, :, None]
    linear = color.srgb_to_linear(np.ascontiguousarray(np.repeat(ramp, 3, axis=2)))[0]
    expected = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
    assert np.allclose(grid.luma[0], expected, atol=1e-6)
