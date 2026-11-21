"""Tests for the text renderer (§3, §10) — cards L9 and L9b (H12, DEV-218).

Metrics are pinned against Pillow's own; renders compare across palettes (S2). Single-paragraph
mechanics are pinned with repeat="once"; repeat="fill" must cover the canvas (L9b).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL import ImageFont

import lattice.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
from lattice.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
from lattice.pipeline import PaletteSpec, PipelineSpec, render
from lattice.renderers import text as text_module
from lattice.renderers.text import DEFAULT_BG, MIN_OPACITY, TextGlyph, TextRenderer
from lattice.types import Palette

BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
COLOUR: Palette = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
NEUTRAL: Palette = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
CELL_W, CELL_H = 8, 16
SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_WORDS = ("lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
          "canvas grid luma ink paper palette neutral source image renderer").split()
PARAGRAPH = " ".join(_WORDS[(i * 7) % len(_WORDS)] for i in range(200))
SHORT = "Lattice renders a paragraph in a real font."
RENDERER = TextRenderer()


def _canvas(cols: int = 12, rows: int = 6, cell_w: int = CELL_W, cell_h: int = CELL_H,
            flat: float | None = None) -> CellGrid:
    """Return a grid over a black-to-white gradient, or over one flat linear luma."""
    luma = (np.full((rows, cols), flat, np.float32) if flat is not None else
            np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols))
    return CellGrid(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(),
                    luma=luma.copy(), samples=luma[:, :, None].copy())


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


def _ink_bbox(glyph: TextGlyph) -> tuple[float, float, float, float]:
    """Return real ink bounds from the rasterised mask, including the stroke (§10)."""
    mask, left, top = text_module._mask((None, 0, 0), glyph.character, glyph.size, glyph.stroke)
    cols, rows = np.flatnonzero(mask.any(axis=0)), np.flatnonzero(mask.any(axis=1))
    if not len(cols):
        return (glyph.x, glyph.y, glyph.x, glyph.y)
    ascent = float(_default_font(glyph.size).getmetrics()[0])
    return (glyph.x + left + float(cols[0]), glyph.y + ascent + top + float(rows[0]),
            glyph.x + left + float(cols[-1] + 1), glyph.y + ascent + top + float(rows[-1] + 1))


def _assert_ink_inside(glyph: TextGlyph, width: int, height: int) -> None:
    """Assert the real ink box (stroke included) lies wholly inside the canvas."""
    x0, y0, x1, y1 = _ink_bbox(glyph)
    assert 0.0 <= x0 and x1 <= width, "glyph ink overflows the horizontal edge"
    assert 0.0 <= y0 and y1 <= height, "glyph ink overflows the vertical edge"


def test_fixed_size_mode_gives_every_glyph_the_same_size():
    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="fixed keeps glyphs identical")
    assert len(glyphs) > 20
    assert {glyph.size for glyph in glyphs} == {glyphs[0].size}


def test_variable_size_mode_gives_at_least_five_distinct_sizes_on_a_gradient():
    glyphs = _layout(_canvas(18, 6), text="variable size spreads ink across the canvas")
    assert len({glyph.size for glyph in glyphs}) >= 5
    default = _layout(_canvas(20, 6))
    assert len(default) > 10 and {g.character for g in default} <= set(text_module.DEFAULT_TEXT)


def test_fixed_size_mode_modulates_opacity_instead_of_size():
    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="opacity carries the modulation")
    assert len({round(glyph.opacity, 6) for glyph in glyphs}) >= 5


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
    paper_frame = _frame(_canvas(30, 4), text="short")
    assert np.all(paper_frame[-1, -1] == np.float32(1.0)), DEFAULT_BG
    assert np.all(paper_frame == np.float32(1.0), axis=-1).mean() > 0.3


@pytest.mark.parametrize("mode", ["fixed", "variable"])
def test_every_glyph_ink_lies_inside_the_canvas(mode):
    grid = _canvas(10, 4)
    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
    for glyph in _layout(grid, size_mode=mode, text="ink stays inside the canvas"):
        _assert_ink_inside(glyph, width, height)


@pytest.mark.parametrize("extra", [2, 8])
def test_ink_bbox_detects_an_artificially_thick_stroke(extra):
    grid = _canvas(10, 4)
    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
    glyph = _layout(grid, size_mode="variable", text="edge")[0]
    thick = glyph._replace(stroke=max(1, glyph.size // 8) + extra)
    x0, y0, x1, y1 = _ink_bbox(thick)
    assert x0 < 0 or y0 < 0 or x1 > width or y1 > height, "stroke overflow went unnoticed"


def test_unbreakable_word_is_cut_and_reflows_on_a_narrower_canvas():
    word = "@" * 400
    options = {"text": word, "size_mode": "fixed", "size": 8, "repeat": "once"}
    wide, narrow = _canvas(40, 20), _canvas(20, 40)
    for grid in (wide, narrow):
        glyphs = _layout(grid, **options)
        assert len(glyphs) == len(word), "cutting a word must not drop glyphs"
        for glyph in glyphs:
            _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)
    assert len(_line_tops(_layout(narrow, **options))) > len(_line_tops(_layout(wide, **options)))


@pytest.mark.parametrize("mode", ["fixed", "variable"])
@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16), (20, 40, 3, 5)])
def test_200_words_wrap_unclipped_on_neutral_and_gradient(mode, cols, rows, cell_w, cell_h):
    grid = _canvas(cols, rows, cell_w, cell_h)
    width, height = cols * cell_w, rows * cell_h
    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode, repeat="once")
    assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
    assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
    assert len(_line_tops(glyphs)) >= 10
    for glyph in glyphs:  # real positions from layout(), including the stroke margin
        _assert_ink_inside(glyph, width, height)
    frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode, repeat="once")
    assert frame.shape == (height, width, 3) and frame.min() >= 0.0 and frame.max() <= 1.0


def test_layout_reports_real_unclamped_positions():
    text, kern = "unclamped", 1.0
    glyphs = _layout(_canvas(80, 4, 1, 60), text=text, size=12, kerning=kern,
                     size_mode="fixed", repeat="once")
    font = _default_font(glyphs[0].size)
    pen = 0.0
    for index, glyph in enumerate(glyphs):
        assert glyph.x == pytest.approx(pen, abs=1e-6), "layout() clamped a raw pen"
        pen += float(font.getlength(glyph.character))
        if index + 1 < len(glyphs):
            pair = font.getlength(glyph.character + glyphs[index + 1].character)
            pen += kern * float(pair - font.getlength(glyph.character)
                                - font.getlength(glyphs[index + 1].character))


def test_the_same_text_and_seed_render_and_lay_out_identically():
    grid, options = _canvas(14, 6), {"text": "seed me", "seed": 3}
    assert np.array_equal(_frame(grid, **options), _frame(grid, **options))
    assert _layout(grid, **options) == _layout(grid, **options)
    assert np.array_equal(_frame(grid, **options),
                          TextRenderer().render_frame(grid, BW, _style(**options)))
    assert not np.array_equal(_frame(grid, **options), _frame(grid, text="seed me", seed=4))


@pytest.mark.parametrize("value", ["", "   ", "\n\t ", " \r\n "])
def test_empty_text_raises_value_error_naming_the_option(value):
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 4), BW, _style(text=value))
    assert "text" in str(excinfo.value) and "option" in str(excinfo.value)


@pytest.mark.parametrize("kerning", [0.0, 0.5, 1.0, 2.0])
def test_pair_kerning_moves_the_second_glyph_by_the_font_pair(kerning):
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    first, second = _layout(_canvas(30, 14), font=str(SYSTEM_FONT), size=12, kerning=kerning,
                            size_mode="fixed", text="AV", repeat="once")
    reference = ImageFont.truetype(str(SYSTEM_FONT), 12)
    pair = reference.getlength("AV") - reference.getlength("A") - reference.getlength("V")
    assert pair != 0.0, "the pinned font must kern AV for this test to mean anything"
    assert second.x - first.x == pytest.approx(
        float(reference.getlength("A")) + kerning * float(pair), abs=1e-6
    )


def test_line_distance_scales_the_leading():
    grid = _canvas(12, 30)
    options = {"text": "one two three four five six seven eight nine ten",
               "size": 8, "size_mode": "fixed", "repeat": "once"}
    tight = _line_tops(_layout(grid, line_distance=1.0, **options))
    loose = _line_tops(_layout(grid, line_distance=2.0, **options))
    ascent, descent = _default_font(8).getmetrics()
    assert len(tight) == 2 and len(loose) == 2
    assert loose[1] - tight[1] == pytest.approx(float(ascent + descent), abs=1e-6)


def test_words_wrap_when_they_no_longer_fit_the_width():
    font = _default_font(10)
    word, space = float(font.getlength("ab")), float(font.getlength(" "))
    wide, narrow = int(3 * word + 3 * space), int(2 * word + space)
    options = {"text": "ab ab ab", "size": 10, "size_mode": "fixed", "repeat": "once"}
    assert _line_tops(_layout(_canvas(wide, 8, 1, 16), **options)) == [0.0]
    assert len(_line_tops(_layout(_canvas(narrow, 8, 1, 16), **options))) == 3


def test_dark_cells_get_larger_heavier_and_darker_glyphs_than_light_cells():
    dark = _layout(_canvas(8, 4, flat=0.0), text="ink")[0]
    light = _layout(_canvas(8, 4, flat=1.0), text="ink")[0]
    assert dark.size > light.size
    assert dark.stroke > light.stroke
    assert dark.opacity == pytest.approx(1.0)
    assert light.opacity == pytest.approx(MIN_OPACITY, abs=1e-6)


def test_low_luma_first_glyph_at_left_edge_has_max_size_and_no_overflow():
    grid = _canvas(8, 4, flat=0.0)
    glyphs = _layout(grid, text="MWMWMW")
    first = glyphs[0]
    assert first.x == 0.0, "a first glyph that fits must not be shifted right"
    assert first.size == max(g.size for g in glyphs) and first.stroke >= 1
    assert first.opacity == pytest.approx(1.0)
    for glyph in glyphs:
        _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)


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


def test_size_and_colour_options_set_size_and_report_colours():
    sized = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
    assert {glyph.size for glyph in sized} == {9}
    glyph = _layout(_canvas(6, 3), text="colours", fg="#AABBCC", bg="#FFEEDD")[0]
    assert glyph.fill == "#aabbcc" and glyph.paper == "#ffeedd"


def test_weight_mode_is_ignored_only_under_fixed_size_mode():
    grid = _canvas(18, 6, flat=0.0)
    fixed = _layout(grid, size_mode="fixed", weight_mode="variable", text="ink weight")
    variable = _layout(grid, size_mode="variable", weight_mode="variable", text="ink weight")
    assert fixed and all(glyph.stroke == 0 for glyph in fixed)
    assert any(glyph.stroke > 0 for glyph in variable)


def test_font_errors_name_the_path_and_distinguish_missing_from_unreadable(tmp_path):
    missing = "/nonexistent/fonts/definitely-not-a-font.ttf"
    with pytest.raises(ValueError, match=missing) as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=missing))
    assert "font file not found" in str(excinfo.value) and "font" in str(excinfo.value)
    bad = tmp_path / "broken.ttf"
    bad.write_bytes(b"not a font")
    with pytest.raises(ValueError, match="usable font") as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=str(bad)))
    assert "font" in str(excinfo.value) and str(bad) in str(excinfo.value)


def test_a_real_font_file_is_used():
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    img = RENDERER.render(_canvas(10, 4), BW, _style(text="DejaVu", font=str(SYSTEM_FONT)))
    assert img.size == (10 * CELL_W, 4 * CELL_H)


@pytest.mark.parametrize("options", [
    {"size": 0}, {"size": -3}, {"size": True}, {"size": 10_000}, {"size_mode": "huge"},
    {"weight_mode": "bold"}, {"kerning": -0.5}, {"kerning": 2.5}, {"line_distance": 0.0},
    {"line_distance": -1.0}, {"fg": "not-a-colour"}, {"fg": "#12345"}, {"fg": "#gggggg"},
    {"fg": 12},
])
def test_invalid_options_raise_value_error(options):
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="invalid", **options))
    name = next(iter(options))
    assert name in str(excinfo.value), f"the error does not name option {name!r}"
    if "mode" in name:
        assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)


def test_unknown_style_keys_are_ignored_for_forward_compatibility():
    grid = _canvas(8, 4)
    assert np.array_equal(_frame(grid, text="future"),
                          _frame(grid, text="future", glow=0.7, shimmer=True))


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


def test_registration_metadata_and_layout_call_forms():
    renderer = TextRenderer()
    assert renderer.name == "text" and get_renderer("text").name == "text"
    assert list_renderers().count("text") == 1 and isinstance(renderer, CellRenderer)
    assert renderer.cell_aspect() == 0.5 and renderer.subgrid() == (1, 1)
    assert renderer.consumes() == frozenset({"luma"})
    grid, style = _canvas(8, 4), _style(text="both forms")
    assert renderer.layout(grid, style) == renderer.layout(grid, BW, style)  # type: ignore[arg-type]


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


# --- L9b (H12, DEV-218): repeat=fill loops the paragraph until the canvas is covered ---


def _inked_cells(frame: np.ndarray, grid: CellGrid) -> np.ndarray:
    """Return the (rows, cols) map of cells carrying at least one pixel off the white paper."""
    inked = np.any(frame != np.float32(1.0), axis=-1)
    return inked.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w).any(axis=(1, 3))


def _srgb_luma(rgb: np.ndarray) -> np.ndarray:
    """Return the sRGB-coded Rec.709 luma of a uint8 RGB image (the H12 reference scale)."""
    code = np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0)
    return np.float32(0.2126) * code[..., 0] + np.float32(0.7152) * code[..., 1] \
        + np.float32(0.0722) * code[..., 2]


@pytest.mark.parametrize("flat", [0.0, 0.2, 0.5])
def test_fill_covers_over_90_percent_of_cells_on_a_short_text_and_large_canvas(flat):
    grid = _canvas(120, 108, 5, 10, flat=flat)  # DEV-218 geometry: 12 960 cells, pixel_size 10
    covered = _inked_cells(_frame(grid, text=SHORT), grid)
    assert float(covered.mean()) > 0.90, "fill must cover the canvas, not just the frame"
    assert covered[0].mean() > 0.5 and covered[-1].mean() > 0.5, "top and bottom must be reached"
    once = _inked_cells(_frame(grid, text=SHORT, repeat="once"), grid)
    assert float(once.mean()) < 0.10, "once keeps the L9 behaviour: a mostly empty canvas"
    for glyph in _layout(grid, text=SHORT):
        _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)


def test_repeat_default_is_fill_and_once_keeps_a_single_paragraph():
    grid = _canvas(40, 30)
    once = _layout(grid, text=SHORT, repeat="once")
    assert len(once) == len(SHORT.replace(" ", "")), "once lays the paragraph exactly once"
    fill = _layout(grid, text=SHORT)
    assert fill == _layout(grid, text=SHORT, repeat="fill"), "the default must be fill"
    assert len(fill) > len(once), "fill repeats the paragraph on a canvas taller than one pass"
    assert np.array_equal(_frame(grid, text=SHORT), _frame(grid, text=SHORT, repeat="fill"))


@pytest.mark.parametrize("mode", ["fixed", "variable"])
@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16), (20, 40, 3, 5)])
def test_fill_flows_the_paragraph_in_order_without_overflow(mode, cols, rows, cell_w, cell_h):
    grid = _canvas(cols, rows, cell_w, cell_h)
    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
    assert glyphs and all(isinstance(glyph, TextGlyph) for glyph in glyphs)
    chars = PARAGRAPH.replace(" ", "")
    repeated = chars * (len(glyphs) // len(chars) + 1)
    assert "".join(g.character for g in glyphs) == repeated[:len(glyphs)], "césure perdue"
    for glyph in glyphs:  # real positions from layout(), including the stroke margin
        _assert_ink_inside(glyph, cols * cell_w, rows * cell_h)


def test_fill_cuts_an_unbreakable_word_and_stays_inside_the_canvas():
    word, options = "@" * 400, {"text": "@" * 400, "size_mode": "fixed", "size": 8}
    wide, narrow = _canvas(40, 20), _canvas(20, 40)
    for grid in (wide, narrow):
        glyphs = _layout(grid, **options)
        assert len(glyphs) >= len(word), "fill must at least complete the first paragraph"
        assert "".join(g.character for g in glyphs) == "@" * len(glyphs)
        for glyph in glyphs:
            _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)
    assert len(_line_tops(_layout(narrow, **options))) > len(_line_tops(_layout(wide, **options)))


def test_fill_on_a_synthetic_portrait_drops_luma_and_raises_contrast():
    rows, cols = 40, 60  # a dark subject on a mid-tone background, deterministic
    luma = np.full((rows, cols), 0.8, np.float32)
    yy, xx = np.mgrid[0:rows, 0:cols]
    luma[((yy - 20) / 16.0) ** 2 + ((xx - 30) / 22.0) ** 2 <= 1.0] = 0.08
    grid = CellGrid(cols=cols, rows=rows, cell_w=5, cell_h=10,
                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(),
                    luma=luma.copy(), samples=luma[:, :, None].copy())
    lum = _srgb_luma(_image(grid, NEUTRAL, text=SHORT))
    assert float(lum.mean()) < 0.90, "a filled text halftone must not come out near-white"
    assert float(lum.std()) > 0.20, "the subject must show through the modulation"


def _portrait_fixture(tmp_path: Path) -> Path:
    """Write a deterministic portrait (dark head and shoulders, neutral background) as PNG."""
    width, height = 360, 480
    yy, xx = np.mgrid[0:height, 0:width]
    luma = np.full((height, width), 0.8, np.float32)
    head = ((yy - 190.0) / 120.0) ** 2 + ((xx - 180.0) / 95.0) ** 2 <= 1.0
    body = (yy > 330.0) & (((xx - 180.0) / 170.0) ** 2 + ((yy - 480.0) / 160.0) ** 2 <= 1.0)
    luma[head | body] = 0.08
    rgb = np.repeat((luma * 255.0)[..., None], 3, axis=-1).astype(np.uint8)
    path = tmp_path / "portrait.png"
    PILImage.fromarray(rgb).save(path)
    return path


@pytest.mark.parametrize("pixel_size", [10, 24])
def test_fill_on_a_generated_portrait_passes_the_dev218_thresholds(pixel_size, tmp_path):
    portrait = _portrait_fixture(tmp_path)
    if not portrait.is_file():
        pytest.skip("no portrait fixture available")
    src = np.asarray(PILImage.open(portrait).convert("RGB"), np.float32) / 255.0
    spec = PipelineSpec(pixel_size=pixel_size, algorithm_id="bayer_4",
                        palette=PaletteSpec(source="builtin", name="grey_8"), renderer="text",
                        renderer_style={"text": text_module.DEFAULT_TEXT, "size_mode": "variable",
                                        "weight_mode": "variable", "fg": "#000000",
                                        "bg": "#ffffff"})
    lum = _srgb_luma(render(src, spec))
    assert float(lum.mean()) < 0.90  # measured 0.9997 before L9b at pixel_size 10
    assert float(lum.std()) > 0.20  # measured 0.0112 before L9b at pixel_size 10


@pytest.mark.parametrize("value", ["loop", "", None, 3, True])
def test_invalid_repeat_raises_value_error_naming_the_option(value):
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="repeat", repeat=value))
    assert "repeat" in str(excinfo.value)
    assert "fill" in str(excinfo.value) and "once" in str(excinfo.value)


@pytest.mark.parametrize("repeat", ["fill", "once"])
def test_repeat_round_trips_through_json(repeat):
    options = {"text": SHORT, "repeat": repeat, "seed": 2}
    style = _style(**options)
    assert json.loads(json.dumps(dict(style.options))) == options
    grid = _canvas(40, 30)  # taller than one paragraph pass: the reloaded option must show
    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
    glyphs = RENDERER.layout(grid, BW, reloaded)
    once = _layout(grid, text=SHORT, repeat="once", seed=2)
    fill = _layout(grid, text=SHORT, repeat="fill", seed=2)
    assert len(once) == len(SHORT.replace(" ", "")) < len(fill), "fill must repeat, once must not"
    assert len(glyphs) == (len(once) if repeat == "once" else len(fill)), \
        "the reloaded 'repeat' option had no observable effect on the layout"
    assert np.array_equal(np.asarray(RENDERER.render(grid, BW, style)),
                          np.asarray(RENDERER.render(grid, BW, reloaded)))


def test_fill_is_deterministic_for_a_given_seed():
    grid, options = _canvas(24, 10), {"text": SHORT, "seed": 7}
    assert np.array_equal(_frame(grid, **options), _frame(grid, **options))
    assert _layout(grid, **options) == _layout(grid, **options)
    assert not np.array_equal(_frame(grid, **options), _frame(grid, text=SHORT, seed=8))


def test_fill_with_a_real_font_repeats_and_keeps_the_geometry():
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    grid = _canvas(20, 8)
    img = RENDERER.render(grid, BW, _style(font=str(SYSTEM_FONT), text=SHORT))
    assert img.size == (20 * CELL_W, 8 * CELL_H)
    glyphs = _layout(grid, font=str(SYSTEM_FONT), text=SHORT)
    assert len(glyphs) > len(SHORT.replace(" ", "")), "a real font must repeat too"
