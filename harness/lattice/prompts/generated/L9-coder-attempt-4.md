# Coder prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are a senior Python engineer implementing one task of the Lattice project: a family of free,
open-source desktop applications that transform images, each running standalone and also plugging
into the ArtCraft suite (Python + numpy + numba + Pillow + PySide6, Windows and Linux).

The suite has four packages: `lattice-core` (the shared engine), `lattice-dither` (the existing
dithering application, 33 algorithms, 10 effects, ~1212 passing tests), `lattice-glyph` and
`lattice-glitch` (new). You work alone on this task; other tasks run in parallel on other files.

HARD RULES
1. Write only the files listed in `owns`. Any other file you need changed → DEVIATIONS block, not code.
2. Follow the contract excerpts exactly: names, signatures, dtypes, value ranges, ordering, error types.
   If the contract is silent, choose the simplest conservative behaviour and record it as E1.
   If the task is impossible without changing the contract, output no FILE blocks, only an E2 deviation.
3. No new dependency. No network. Only numpy, numba (where allowed), Pillow, PySide6, stdlib, pytest.
   `lattice-core` base install must not import PySide6; Qt lives behind the `[ui]` extra.
4. **Core must not import any application.** `lattice_core` may not reference `lattice_dither`,
   `lattice_glyph` or `lattice_glitch`. If you need application-specific behaviour in core, that is
   an E8 deviation: stop and declare it.
5. **Every application must work with no host present.** A missing ArtCraft, a refused connection or
   an absent token file is a normal state, never a crash. If your change makes an app depend on a
   running host, that is an E9 deviation.
6. Each file ≤ 400 lines, each function ≤ 60 lines, typed public API, 1 to 3 line docstrings.
7. Tests: cover every `accept` item of the card, deterministic seeds, fast.
8. **Do not regress the dithering application.** Any behaviour that existed before your task must
   still hold. If your change alters a 1.0 or 1.1 output, that is an E6 deviation: stop and declare
   it, do not ship it.
9. Output full file contents (no diffs, no ellipsis, no "rest unchanged"). Nothing outside the blocks below.
10. Do not explain your code. NOTES is for facts the reviewer needs, ≤ 10 lines.

OUTPUT FORMAT
```
=== FILE: <relative path> ===
<complete content>
=== END FILE ===
(repeat per owned file you write)
=== NOTES ===
<≤ 10 lines or "none">
=== DEVIATIONS ===
<"none", or one block per deviation:
class: E1|E2|E3|E4|E5|E6|E8|E9
facts: <quote the contract or card line involved>
assumption_or_proposal: <...>
(E3 scope : déclarer une sortie hors `owns` ne l'autorise pas — G4 et le relecteur décident.
E7 product : déclarée par le relecteur ou l'humain, jamais par le codeur.)
```

CONTRACT EXCERPTS (version 0.1.0)

## §10 Text-halftone

`text` renderer. A flowing paragraph in a real font, not a character grid.

- Lay out the paragraph with real font metrics: kerning, line distance, word wrapping.
- Modulate per-glyph **weight, size and opacity** by the underlying `luma` (S2, decided
  2026-11-16): ink density must not collapse on a neutral palette.
- Cells may vary in size. `cell_aspect()` returns the nominal aspect; the renderer may vary a cell
  by ±50% and must still fill the output rectangle exactly.
- Options: `text` (string), `font`, `size`, `line_distance`, `kerning`, `size_mode`
  (`fixed` | `variable`), `weight_mode` (`fixed` | `variable`), `fg`/`bg`.
- `size_mode: fixed` keeps every glyph the same size and modulates only opacity. `variable` is the
  mode that makes the output look like art rather than ASCII.



TASK CARD

### L9 · Text-halftone renderer
- wave: 1 · deps: L2b · executor: OMH deep · review: strict · size: L
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §3 §10
- spec: implement `text` per §10. Lay out a flowing paragraph with real font metrics: kerning, line
  distance, word wrapping. Modulate per-glyph weight, size and opacity by `luma` (S2/H11 —
  l'encre ne doit pas s'effondrer sur une palette neutre). Cells may vary
  in size by ±50 % and must still fill the output rectangle exactly. Options: `text`, `font`,
  `size`, `line_distance`, `kerning`, `size_mode` (`fixed` | `variable`), `weight_mode`
  (`fixed` | `variable`), `fg`, `bg`.
- accept:
  - `size_mode: "fixed"` produces glyphs of identical size; `"variable"` produces at least 5
    distinct sizes on a gradient.
  - the output rectangle is filled exactly, with no gap and no overflow, for both modes.
  - a 200-word paragraph wraps without clipping and without a single glyph outside the canvas.
  - the same text and seed produce identical output across two calls.
  - an empty `text` raises `ValueError` naming the option.



CURRENT CONTENT OF `tests/test_text.py` (le module `text.py` est GELÉ : ne le renvoie pas)

"""Tests for the text renderer (§3, §10) — card L9.

Font metrics are pinned against Pillow's own, computed independently here.
The renderer is palette-independent by contract (S2), so renders compare across palettes.
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


def _ink_bbox(glyph: TextGlyph) -> tuple[float, float, float, float]:
    """Return true ink bounds from font metrics, at the glyph's reported real position."""
    font = _default_font(glyph.size)
    ascent = float(font.getmetrics()[0])
    x0, y0, x1, y1 = font.getbbox(glyph.character, anchor="ls")
    return (glyph.x + x0, glyph.y + ascent + y0, glyph.x + x1, glyph.y + ascent + y1)


# --- accept 1: fixed keeps one size; variable gives at least five on a gradient ---


def test_fixed_size_mode_gives_every_glyph_the_same_size():
    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="fixed keeps glyphs identical")
    assert len(glyphs) > 20
    assert {glyph.size for glyph in glyphs} == {glyphs[0].size}


def test_variable_size_mode_gives_at_least_five_distinct_sizes_on_a_gradient():
    glyphs = _layout(_canvas(18, 6), text="variable size spreads ink across the canvas")
    assert len({glyph.size for glyph in glyphs}) >= 5
    default = _layout(_canvas(20, 6))
    assert len(default) > 10 and {glyph.character for glyph in default} <= set(
        text_module.DEFAULT_TEXT
    )


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
    paper_frame = _frame(_canvas(30, 4), text="short")
    assert np.all(paper_frame[-1, -1] == np.float32(1.0)), DEFAULT_BG
    assert np.all(paper_frame == np.float32(1.0), axis=-1).mean() > 0.3


@pytest.mark.parametrize("mode", ["fixed", "variable"])
def test_every_glyph_ink_lies_inside_the_canvas(mode):
    grid = _canvas(10, 4)
    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
    for glyph in _layout(grid, size_mode=mode, text="ink stays inside the canvas"):
        x0, y0, x1, y1 = _ink_bbox(glyph)
        assert 0 <= x0 and x1 <= width and 0 <= y0 and y1 <= height


# --- accept 3: a 200-word paragraph wraps, unclipped ---


@pytest.mark.parametrize("mode", ["fixed", "variable"])
@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16), (20, 40, 3, 5)])
def test_200_words_wrap_unclipped_on_neutral_and_gradient(mode, cols, rows, cell_w, cell_h):
    grid = _canvas(cols, rows, cell_w, cell_h)
    width, height = cols * cell_w, rows * cell_h
    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
    assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
    assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
    assert len(_line_tops(glyphs)) >= 10
    for glyph in glyphs:  # real positions from layout(), not a clamped advance box
        x0, y0, x1, y1 = _ink_bbox(glyph)
        assert 0 <= x0 and x1 <= width, "glyph ink overflows the horizontal edge"
        assert 0 <= y0 and y1 <= height, "glyph ink overflows the vertical edge"
    frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
    assert frame.shape == (height, width, 3) and frame.min() >= 0.0 and frame.max() <= 1.0


def test_layout_reports_real_unclamped_positions():
    """layout() exposes the raw pen/baseline: a reintroduced clamp must fail this."""
    para = text_module._Paragraph(_canvas(10, 4),
                                  text_module._read_options(_style(text="real positions")))
    para._modulate()
    placed, dx, dy = para._fit()
    glyphs = para._place(placed, dx, dy)
    for raw, glyph in zip(placed, glyphs, strict=True):
        ascent = _default_font(raw.size).getmetrics()[0]
        assert (glyph.x, glyph.y) == pytest.approx((raw.pen + dx, raw.baseline + dy - ascent))
    assert len(glyphs) == len(placed)


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


def test_size_and_colour_options_set_size_and_report_colours():
    sized = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
    assert {glyph.size for glyph in sized} == {9}
    glyph = _layout(_canvas(6, 3), text="colours", fg="#AABBCC", bg="#FFEEDD")[0]
    assert glyph.fill == "#aabbcc" and glyph.paper == "#ffeedd"


def test_weight_mode_is_ignored_only_under_fixed_size_mode():
    """§10: fixed size modulates opacity only, so weight_mode applies only to variable."""
    grid = _canvas(18, 6, flat=0.0)
    fixed = _layout(grid, size_mode="fixed", weight_mode="variable", text="ink weight")
    variable = _layout(grid, size_mode="variable", weight_mode="variable", text="ink weight")
    assert fixed and all(glyph.stroke == 0 for glyph in fixed)
    assert any(glyph.stroke > 0 for glyph in variable)


def test_font_errors_name_the_path_and_distinguish_missing_from_unreadable(tmp_path):
    missing = "/nonexistent/fonts/definitely-not-a-font.ttf"
    with pytest.raises(ValueError, match=missing):
        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=missing))
    bad = tmp_path / "broken.ttf"
    bad.write_bytes(b"not a font")
    with pytest.raises(ValueError, match="usable font") as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=str(bad)))
    assert str(bad) in str(excinfo.value)


def test_a_real_font_file_is_used():
    if not SYSTEM_FONT.is_file():
        pytest.skip("no system TrueType font available")
    img = RENDERER.render(_canvas(10, 4), BW, _style(text="DejaVu", font=str(SYSTEM_FONT)))
    assert img.size == (10 * CELL_W, 4 * CELL_H)


@pytest.mark.parametrize("options", [
    {"size": 0}, {"size": -3}, {"size": True}, {"size": 10_000},
    {"size_mode": "huge"}, {"weight_mode": "bold"},
    {"kerning": -0.5}, {"kerning": 2.5}, {"line_distance": 0.0}, {"line_distance": -1.0},
    {"fg": "not-a-colour"}, {"fg": "#12345"}, {"fg": "#gggggg"}, {"fg": 12},
])
def test_invalid_options_raise_value_error(options):
    with pytest.raises(ValueError) as excinfo:
        RENDERER.render(_canvas(6, 3), BW, _style(text="invalid", **options))
    if "mode" in options:
        assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)


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


def test_registration_metadata_and_layout_call_forms():
    renderer = TextRenderer()
    assert renderer.name == "text" and get_renderer("text").name == "text"
    assert list_renderers().count("text") == 1 and isinstance(renderer, CellRenderer)
    assert renderer.cell_aspect() == 0.5 and renderer.subgrid() == (1, 1)
    assert renderer.consumes() == frozenset({"luma"})
    grid, style = _canvas(8, 4), _style(text="both forms")
    assert renderer.layout(grid, style) == renderer.layout(  # type: ignore[arg-type]
        grid, BW, style
    )


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


RETRY attempt 4 — CYCLE 3 BORNÉ (DEV-217, budget de revue épuisé). **TEST-ONLY.**
Interdiction formelle : ne touche pas à `lattice_core/renderers/text.py`. Le comportement de rendu est
mesuré correct ; c'est la PREUVE qui manque. Si tu modifies le module, la livraison est rejetée.

CE QUE TU DOIS FAIRE

1. major tests/test_text.py:82 — `_ink_bbox` mesure l'encre avec `font.getbbox(char, anchor="ls")`
   en IGNORANT `glyph.stroke`, alors que le mode `variable` épaissit le trait de
   `round(ink * max(1, size // 8))` px. Conséquence : l'assertion « aucun glyphe hors du canevas » ne
   peut pas détecter un débordement causé par le trait. Corrige le helper pour inclure le trait :
   la bbox d'encre réelle doit élargir la bbox de police de `glyph.stroke` pixels de chaque côté, ou
   mieux, mesurer l'encre sur le masque réellement rastérisé (le module expose déjà une fonction de
   masque avec padding de trait — utilise-la si elle est accessible depuis le test ; sinon reconstruis
   l'élargissement et documente-le).
   Puis VÉRIFIE que le test corrigé est fort : il doit échouer si tu simules un trait trop épais. Tu
   peux le prouver par un test paramétré avec un `stroke` artificiel, sans toucher au module.
   Mesure de l'orchestrateur, pour t'éviter de douter : avec le masque réel (padding de trait inclus),
   1008 glyphes × 6 combinaisons (cellules 8×16, 6×12, 3×5 × modes fixed/variable) donnent 0 glyphe
   hors canevas, dépassement max 0,0 px. Le code est donc bon ; il faut juste une preuve honnête.

2. minor tests/test_text.py:168 — `test_layout_reports_real_unclamped_positions` appelle
   `_Paragraph._modulate`, `_fit`, `_place` puis RE-DÉRIVE `pen + dx` et `baseline + dy - ascent` :
   c'est la même arithmétique que le code, donc le test le récite. Réécris-le pour comparer la sortie
   publique `layout()` à une position calculée indépendamment (par exemple : le pen d'un glyphe connu
   de la première ligne est exactement la somme des avances mesurées par Pillow sur les glyphes
   précédents de cette ligne), de sorte qu'un décalage du clamp réapparaisse.

3. minor tests/test_text.py:316 — 14 cas de validation fusionnés en une paramétrisation ; la
   vérification « l'option est nommée dans le message » ne s'applique qu'aux modes. Rétablis
   l'assertion du nom de l'option pour `size`, `kerning`, `line_distance`, `font` et `text` (chaque
   message doit nommer son option).

4. minor `text.py:31` et `text.py:336` — TU N'Y TOUCHES PAS (le module est gelé par cette consigne).
   Ces deux minors sont consignés au registre pour une carte de nettoyage ultérieure.

CONTRAINTES : `test_text.py` ≤ 400 lignes (actuellement 397 — si ta correction le fait déborder,
extrais un helper dans le même fichier ou fusionne des cas, mais reste sous 400), fonctions ≤ 60
lignes, ruff clean. Les 60 tests existants doivent rester verts, et la suite complète aussi
(2052 passed au départ). Livre UNIQUEMENT `tests/test_text.py`, plus NOTES et DEVIATIONS.

FINDINGS DU REVIEWER (verbatim)
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "tests/test_text.py",
      "line": 82,
      "what": "`_ink_bbox` measures ink with `font.getbbox(char, anchor='ls')` and ignores `glyph.stroke`. The `variable` mode strokes glyphs by `round(ink * max(1, size // 8))` px, which widens the real ink on every side.",
      "why": "Accept 3 says 'not a single glyph outside the canvas'. The 200-word and ink-inside tests pass `size_mode='variable'` with the default `weight_mode='variable'`, so stroked glyphs are checked as if they had no stroke. A glyph at the edge can overflow by `stroke` px and the test will not see it. Rasterisation silently clips it (`_blit`), but `layout()` now reports real positions and §11 exports (SVG, text) consume it, so the overflow would show up in those exports. The coder's claim that `_fit()` needs no change was measured on 'raw ink bbox' and so does not cover the stroke.",
      "fix": "Pass `stroke_width=glyph.stroke` to `getbbox` in `_ink_bbox`, or widen the bounds by `glyph.stroke`. If a case then fails, make `_fit()` shrink the margin to account for stroke. Run that check on neutral luma, where ink is at its maximum."
    },
    {
      "severity": "minor",
      "file": "tests/test_text.py",
      "line": 168,
      "what": "`test_layout_reports_real_unclamped_positions` calls the private `_Paragraph._modulate`, `_fit` and `_place`, then re-derives `pen + dx` and `baseline + dy - ascent`, which is the same arithmetic as `_place`.",
      "why": "It restates the implementation and breaks on any refactor. It also does not state the contract, which is that `layout()` must not clamp. The ink-bbox tests do not catch a reintroduced clamp, because a clamp would only make them pass more easily.",
      "fix": "Test through the public `layout()`. Build a case where the real position is outside the canvas (for example a glyph larger than the canvas under a tiny `size`) and assert a negative or overflowing `x` or `y`. If `_fit` makes that impossible, document the white-box test as intentional."
    },
    {
      "severity": "minor",
      "file": "tests/test_text.py",
      "line": 316,
      "what": "`test_invalid_options_raise_value_error` merges 14 cases into one parametrisation, and the 'option named in the message' check applies only to modes. The old tests named the option for size, kerning and colour.",
      "why": "Accept 5 requires the error to name the option, and that is the one rule the card spells out. Option-name coverage was lost for `size`, `kerning`, `line_distance` and `fg`. The distinct-message claim for fonts is only checked through `match=missing` and 'usable font'. The 'font file not found' text is never asserted.",
      "fix": "Assert that the option name (the dict key) appears in `str(excinfo.value)` for every case. Assert the exact 'font file not found' wording for the missing-font case."
    },
    {
      "severity": "minor",
      "file": "lattice_core/renderers/text.py",
      "line": 31,
      "what": "Constants are packed with tuple assignments (`NAME, CELL_ASPECT = ...`, `SIZE_MODES = WEIGHT_MODES = ...`, five values on one line). This looks like golfing to hit the 400-line cap.",
      "why": "Readability and hygiene. It also hides that `MAX_SIZE` and `JITTER` are unrelated to opacity and factor, and any edit becomes a multi-name diff.",
      "fix": "Restore one constant per line, grouped by theme. Cut length elsewhere if the cap needs it."
    },
    {
      "severity": "minor",
      "file": "lattice_core/renderers/text.py",
      "line": 336,
      "what": "`_place` keeps `box_w = advance` and `box_h = ...` as separate intermediates, and `TextGlyph.width` and `height` are now unclamped advance and line boxes that can extend past the canvas.",
      "why": "The `layout()` docstring should say that width and height are advance and line boxes, not visible ink. Otherwise an SVG or text exporter may treat them as bounds.",
      "fix": "Document the semantics of `width` and `height` in the `TextGlyph` docstring, and inline `box_w` and `box_h`."
    }
  ],
  "regression": "none (the new renderer adds no change to frozen behaviour; the diff is confined to text.py and test_text.py; suite 2052 passed, G3 OK)",
  "renderer_invariants": "all six hold (output size, purity, no mutation of grid or palette, cell_aspect 0.5, unique name 'text', JSON round-trip). Each has a test. Note that `layout()` is now unclamped, which the §3 invariants do not restrict.",
  "tests_that_cannot_fail": [
    "test_layout_reports_real_unclamped_positions (restates `_place`)",
    "the ink-inside and 200-word bbox checks cannot fail on stroke overflow, because stroke is not measured",
    "the 'mode' branch in test_invalid_options_raise_value_error is only reached for two of the 14 cases"
  ],
  "notes": "I reviewed from the diff only and did not run the code. I could not verify the claim that `_fit()` never lets ink leave the canvas, but it should be re-measured including stroke. The E1 deviations (weight_mode ignored under fixed size_mode, undocumented `seed`) are acceptable and documented. No E8 or E9 leaks are visible in the diff."
}

