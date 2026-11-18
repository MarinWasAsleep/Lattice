"""Tests for the text renderer (§3, §10) — card L9.

Wrap points, leading and kerning are pinned against Pillow's own font metrics, computed
independently here: a change that moves both the renderer and its arithmetic still fails.
The renderer is palette-independent by contract (S2), so renders are compared across very
different palettes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import ImageFont

from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
from lattice_core.renderers import text as text_module
from lattice_core.renderers.text import DEFAULT_BG, MIN_OPACITY, TextGlyph, TextRenderer
from lattice_core.types import Palette

BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
COLOUR: Palette = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
NEUTRAL: Palette = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
CELL_W, CELL_H = 8, 16
SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_WORDS = (
    "lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
    "canvas grid luma ink paper palette neutral source image renderer"
).split()
PARAGRAPH = " ".join(_WORDS[(index * 7) % len(_WORDS)] for index in range(200))
RENDERER = TextRenderer()


def _canvas(
    cols: int = 12, rows: int = 6, cell_w: int = CELL_W, cell_h: int = CELL_H,
    flat: float | None = None,
) -> CellGrid:
    """Return a grid over a black-to-white gradient, or over one flat linear luma."""
    cols = int(cols)
    rows = int(rows)
    if flat is None:
        luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
    else:
        luma = np.full((rows, cols), flat, np.float32)
    return CellGrid(
        cols=cols, rows=rows, cell_w=int(cell_w), cell_h=int(cell_h),
        index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma.copy(),
        samples=luma[:, :, None].copy(),
    )


def _style(**options: object) -> RenderStyle:
    """Return a RenderStyle carrying the given text options."""
    return RenderStyle(options=dict(options))


def _layout(grid: CellGrid, palette: Palette = BW, **options: object) -> list[TextGlyph]:
    """Return the glyphs layout() places for these options."""
    return RENDERER.layout(grid, palette, _style(**options))


def _frame(grid: CellGrid, palette: Palette = BW, **options: object) -> np.ndarray:
    """Return the float frame render_frame() draws for these options."""
    return RENDERER.render_frame(grid, palette, _style(**options))


def _image(grid: CellGrid, palette: Palette = BW, **options: object) -> np.ndarray:
    """Return the rendered image as a uint8 array."""
    return np.asarray(RENDERER.render(grid, palette, _style(**options)))


def _line_tops(glyphs: list[TextGlyph]) -> list[float]:
    """Return the distinct top edges of the placed glyph boxes, in reading order."""
    return sorted({round(glyph.y, 6) for glyph in glyphs})


def _default_font(size: int) -> ImageFont.FreeTypeFont:
    """Return Pillow's bundled default font at size, as the FreeType font it is."""
    return ImageFont.load_default(size=size)  # type: ignore[return-value]


# --- accept 1: fixed keeps one size; variable gives at least five on a gradient ---


def test_fixed_size_mode_gives_every_glyph_the_same_size():
    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="fixed keeps glyphs identical")
    assert len(glyphs) > 20
    assert {glyph.size for glyph in glyphs} == {glyphs[0].size}


def test_variable_size_mode_gives_at_least_five_distinct_sizes_on_a_gradient():
    glyphs = _layout(_canvas(18, 6), text="variable size spreads ink across the canvas")
    assert len({glyph.size for glyph in glyphs}) >= 5


def test_fixed_size_mode_modulates_opacity_instead_of_size():
    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="opacity carries the modulation")
    assert len({round(glyph.opacity, 6) for glyph in glyphs}) >= 5


# --- accept 2: the rectangle is filled exactly, with no gap and no overflow ---


@pytest.mark.parametrize("mode", ["fixed", "variable"])
def test_the_output_rectangle_is_exactly_the_grid_geometry(mode):
    grid = _canvas(12, 5, 6, 18)
    img = RENDERER.render(grid, BW, _style(size_mode=mode, text="exact geometry"))
    assert img.size == (grid.cols * grid.cell_w, grid.rows * grid.cell_h)
    assert img.mode == "RGB"
    frame = _frame(grid, size_mode=mode)
    assert frame.shape == (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
    assert frame.dtype == np.float32 and np.isfinite(frame).all()


@pytest.mark.parametrize("mode", ["fixed", "variable"])
def test_every_pixel_is_paper_or_ink_blended_over_paper(mode):
    frame = _frame(_canvas(10, 4), size_mode=mode, text="no gap and no overflow",
                   fg="#ff0000", bg="#0000ff")
    assert frame.min() >= 0.0 and frame.max() <= 1.0
    assert np.all(frame[:, :, 1] == 0.0), "a colour outside fg/bg reached the canvas"
    ink, paper = frame[:, :, 0], 1.0 - frame[:, :, 2]
    assert np.allclose(ink, paper, atol=2e-6), "pixels are not blends of the two colours"
    assert ink.max() > 0.5 and ink.min() == 0.0


@pytest.mark.parametrize("mode", ["fixed", "variable"])
def test_every_glyph_box_lies_inside_the_canvas(mode):
    grid = _canvas(10, 4)
    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
    for glyph in _layout(grid, size_mode=mode, text="boxes stay inside the canvas"):
        assert 0.0 <= glyph.x and glyph.x + glyph.width <= width
        assert 0.0 <= glyph.y and glyph.y + glyph.height <= height


def test_the_paper_paints_the_whole_rectangle():
    frame = _frame(_canvas(30, 4), text="short")
    assert np.all(frame[-1, -1] == np.float32(1.0)), DEFAULT_BG
    assert np.all(frame == np.float32(1.0), axis=-1).mean() > 0.3


# --- accept 3: a 200-word paragraph wraps, unclipped ---


@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"), [(40, 20, 8, 16), (20, 40, 6, 12)])
def test_a_200_word_paragraph_wraps_over_many_lines(cols, rows, cell_w, cell_h):
    tops = _line_tops(_layout(_canvas(cols, rows, cell_w, cell_h), text=PARAGRAPH))
    assert len(tops) >= 20


@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16)])
def test_a_200_word_paragraph_never_places_a_glyph_outside_the_canvas(cols, rows, cell_w, cell_h):
    grid = _canvas(cols, rows, cell_w, cell_h)
    width, height = cols * cell_w, rows * cell_h
    glyphs = _layout(grid, text=PARAGRAPH)
    assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
    assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
    for glyph in glyphs:
        assert 0.0 <= glyph.x and glyph.x + glyph.width <= width
        assert 0.0 <= glyph.y and glyph.y + glyph.height <= height
    frame = _frame(grid, text=PARAGRAPH)
    assert frame.shape == (height, width, 3)
    assert frame.min() >= 0.0 and frame.max() <= 1.0


# --- accept 4: the same text and seed render identically ---


def test_the_same_text_and_seed_render_and_lay_out_identically():
    grid, options = _canvas(14, 6), {"text": "seed me", "seed": 3}
    assert np.array_equal(_frame(grid, **options), _frame(grid, **options))
    assert _layout(grid, **options) == _layout(grid, **options)
    assert np.array_equal(_frame(grid, **options),
                          TextRenderer().render_frame(grid, BW, _style(**options)))
    assert not np.array_equal(_frame(grid, **options), _frame(grid, text="seed me", seed=4))


# --- accept 5: empty text raises ValueError naming the option ---


@pytest.mark.parametrize("value", ["", "   ", "\n\t ", " \r\n "])
def test_empty_text_raises_value_error_naming_the_option(value):
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 4), BW, _style(text=value))
    assert "text" in str(excinfo.value) and "option" in str(excinfo.value)


# --- §10: real font metrics — kerning, leading, wrapping ---


@pytest.mark.parametrize("kerning", [0.0, 0.5, 1.0, 2.0])
def test_pair_kerning_moves_the_second_glyph_by_the_font_pair(kerning):
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    first, second = _layout(_canvas(30, 14), font=str(SYSTEM_FONT), size=12, kerning=kerning,
                            size_mode="fixed", text="AV")
    reference = ImageFont.truetype(str(SYSTEM_FONT), 12)
    pair = reference.getlength("AV") - reference.getlength("A") - reference.getlength("V")
    assert pair != 0.0, "the pinned font must kern AV for this test to mean anything"
    assert second.x - first.x == pytest.approx(
        float(reference.getlength("A")) + kerning * float(pair), abs=1e-6
    )


def test_line_distance_scales_the_leading():
    grid = _canvas(12, 30)
    options = {"text": "one two three four five six seven eight nine ten",
               "size": 8, "size_mode": "fixed"}
    tight = _line_tops(_layout(grid, line_distance=1.0, **options))
    loose = _line_tops(_layout(grid, line_distance=2.0, **options))
    ascent, descent = _default_font(8).getmetrics()
    assert len(tight) == 2 and len(loose) == 2
    assert loose[1] - tight[1] == pytest.approx(float(ascent + descent), abs=1e-6)


def test_words_wrap_when_they_no_longer_fit_the_width():
    font = _default_font(10)
    word, space = float(font.getlength("ab")), float(font.getlength(" "))
    wide, narrow = int(3 * word + 3 * space), int(2 * word + space)
    options = {"text": "ab ab ab", "size": 10, "size_mode": "fixed"}
    assert _line_tops(_layout(_canvas(wide, 8, 1, 16), **options)) == [0.0]
    assert len(_line_tops(_layout(_canvas(narrow, 8, 1, 16), **options))) == 3


def test_default_text_is_a_usable_paragraph():
    glyphs = _layout(_canvas(20, 6))
    assert len(glyphs) > 10
    assert {glyph.character for glyph in glyphs} <= set(text_module.DEFAULT_TEXT)


# --- §10: luma modulation, independent of the palette (S2) ---


def test_dark_cells_get_larger_heavier_and_darker_glyphs_than_light_cells():
    dark = _layout(_canvas(8, 4, flat=0.0), text="ink")[0]
    light = _layout(_canvas(8, 4, flat=1.0), text="ink")[0]
    assert dark.size > light.size
    assert dark.stroke > light.stroke
    assert dark.opacity == pytest.approx(1.0)
    assert light.opacity == pytest.approx(MIN_OPACITY, abs=1e-6)


def test_ink_never_collapses_on_a_neutral_palette():
    grid = _canvas(18, 6)
    glyphs = _layout(grid, NEUTRAL, text="neutral ink must survive the palette")
    assert len({glyph.size for glyph in glyphs}) >= 5
    assert all(glyph.opacity >= MIN_OPACITY for glyph in glyphs)


@pytest.mark.parametrize("palette", [BW, COLOUR, NEUTRAL])
def test_the_choice_of_palette_never_changes_the_output(palette):
    grid = _canvas(14, 5)
    assert np.array_equal(_frame(grid, BW, text="palette free"),
                          _frame(grid, palette, text="palette free"))


# --- options ---


def test_size_option_sets_the_base_point_size_in_fixed_mode():
    glyphs = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
    assert {glyph.size for glyph in glyphs} == {9}


def test_layout_reports_the_ink_and_paper_colours():
    glyph = _layout(_canvas(6, 3), text="colours", fg="#AABBCC", bg="#FFEEDD")[0]
    assert glyph.fill == "#aabbcc" and glyph.paper == "#ffeedd"


def test_missing_font_file_raises_value_error_naming_the_path():
    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=path))
    assert path in str(excinfo.value)


def test_a_real_font_file_is_used():
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    img = RENDERER.render(_canvas(10, 4), BW, _style(text="DejaVu", font=str(SYSTEM_FONT)))
    assert img.size == (10 * CELL_W, 4 * CELL_H)


@pytest.mark.parametrize("size", [0, -3, True, 10_000])
def test_invalid_size_raises_value_error(size):
    with pytest.raises(ValueError):
        RENDERER.render(_canvas(6, 3), BW, _style(text="size", size=size))


@pytest.mark.parametrize(("key", "value"), [("size_mode", "huge"), ("weight_mode", "bold")])
def test_unknown_modes_raise_value_error_naming_the_choices(key, value):
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="mode", **{key: value}))
    assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)


@pytest.mark.parametrize(("key", "value"), [("kerning", -0.5), ("kerning", 2.5),
                                            ("line_distance", 0.0), ("line_distance", -1.0)])
def test_out_of_range_numbers_raise_value_error(key, value):
    with pytest.raises(ValueError):
        RENDERER.render(_canvas(6, 3), BW, _style(text="numbers", **{key: value}))


@pytest.mark.parametrize("colour", ["not-a-colour", "#12345", "#gggggg", 12])
def test_invalid_colours_raise_value_error(colour):
    with pytest.raises(ValueError):
        RENDERER.render(_canvas(6, 3), BW, _style(text="colours", fg=colour))


def test_unknown_style_keys_are_ignored_for_forward_compatibility():
    grid = _canvas(8, 4)
    assert np.array_equal(_frame(grid, text="future"),
                          _frame(grid, text="future", glow=0.7, shimmer=True))


# --- §3 invariants ---


def test_render_is_pure_and_does_not_mutate_grid_or_palette():
    grid, palette = _canvas(12, 5), BW.copy()
    style = _style(text="pure")
    snapshot = [array.copy() for array in (grid.index, grid.coverage, grid.luma, grid.samples)]
    first = np.asarray(RENDERER.render(grid, palette, style))
    assert np.array_equal(first, np.asarray(RENDERER.render(grid, palette, style)))
    for array, before in zip((grid.index, grid.coverage, grid.luma, grid.samples), snapshot,
                             strict=True):
        assert np.array_equal(array, before)
    assert np.array_equal(palette, BW)


def test_render_frame_matches_render():
    grid = _canvas(12, 5)
    frame = _frame(grid, text="consistent rasterisation")
    expected = np.floor(np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    assert np.array_equal(_image(grid, text="consistent rasterisation"), expected)


def test_the_renderer_is_registered_under_a_unique_stable_name():
    renderer = TextRenderer()
    assert renderer.name == "text"
    assert get_renderer("text").name == "text"
    assert list_renderers().count("text") == 1
    assert isinstance(renderer, CellRenderer)


def test_cell_aspect_subgrid_and_consumes():
    assert RENDERER.cell_aspect() == 0.5
    assert RENDERER.subgrid() == (1, 1)
    assert RENDERER.consumes() == frozenset({"luma"})


def test_style_options_round_trip_through_json():
    options = {"text": "round trip", "font": None, "size": 12, "line_distance": 1.4,
               "kerning": 0.5, "size_mode": "fixed", "weight_mode": "variable",
               "fg": "#112233", "bg": "#ffeedd", "seed": 5}
    style = _style(**options)
    assert json.loads(json.dumps(dict(style.options))) == options
    grid = _canvas(10, 4)
    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
    assert np.array_equal(np.asarray(RENDERER.render(grid, BW, style)),
                          np.asarray(RENDERER.render(grid, BW, reloaded)))


def test_layout_accepts_both_call_forms():
    grid, style = _canvas(8, 4), _style(text="both forms")
    assert RENDERER.layout(grid, style) == RENDERER.layout(grid, BW, style)


def test_cached_masks_are_read_only_and_the_cache_is_bounded():
    text_module._mask.cache_clear()
    mask, _, _ = text_module._mask((None, 0, 0), "M", 12, 0)
    assert not mask.flags.writeable
    with pytest.raises(ValueError):
        mask[0, 0] = 1.0
    for size in range(4, 20):
        text_module._mask((None, 0, 0), "M", size, 0)
    info = text_module._mask.cache_info()
    assert info.maxsize is not None and info.currsize <= info.maxsize


def test_a_grid_whose_luma_shape_does_not_match_raises_value_error():
    grid = _canvas(6, 3)
    broken = CellGrid(cols=6, rows=3, cell_w=CELL_W, cell_h=CELL_H, index=grid.index,
                      coverage=grid.coverage, luma=grid.luma[:, :4], samples=grid.samples)
    with pytest.raises(ValueError) as excinfo:
        RENDERER.layout(broken, _style(text="shape"))
    assert "luma" in str(excinfo.value)


def test_an_empty_canvas_renders_nothing():
    empty = CellGrid(cols=0, rows=0, cell_w=CELL_W, cell_h=CELL_H,
                     index=np.zeros((0, 0), np.int32), coverage=np.zeros((0, 0), np.float32),
                     luma=np.zeros((0, 0), np.float32), samples=np.zeros((0, 0, 1), np.float32))
    assert RENDERER.layout(empty, _style(text="nothing")) == []
    assert RENDERER.render(empty, BW, _style(text="nothing")).size == (0, 0)
