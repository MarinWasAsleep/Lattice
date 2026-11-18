"""Tests for the text export of a CellGrid (card L11, §11, P3).

``.txt`` must contain ``cols * rows`` tokens over ``rows`` lines, ``.ansi`` must carry 24-bit
SGR sequences and nothing else, and ``.html`` must render the same grid while escaping its
glyph text. Every format is derived from the renderer's ``layout()`` (H11), so the tests pin
the layout's characters rather than re-deriving them from luma.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

import lattice_core.renderers  # noqa: F401  (registers the built-in renderers)
from lattice_core.cell import CellGrid, RenderStyle, get_renderer
from lattice_core.textout import BLANK, FORMATS, render_text
from lattice_core.types import Palette

BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
FOUR: Palette = np.array(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32
)
CELL_W, CELL_H = 8, 16
SGR = re.compile(r"\x1b\[([0-9;]*)m")
TRUECOLOR = re.compile(r"^(0|38;2;\d{1,3};\d{1,3};\d{1,3}|48;2;\d{1,3};\d{1,3};\d{1,3})$")


def _grid(index: np.ndarray, cell_w: int = CELL_W, cell_h: int = CELL_H,
          luma: np.ndarray | None = None, subindex: np.ndarray | None = None,
          samples_k: int = 6) -> CellGrid:
    """Build a CellGrid with the given indices, luma and optional sub-point indices."""
    rows, cols = index.shape
    shape = (rows, cols)
    return CellGrid(
        cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
        index=np.asarray(index, dtype=np.int32),
        coverage=np.full(shape, 0.5, dtype=np.float32),
        luma=np.asarray(luma, dtype=np.float32) if luma is not None else np.full(
            shape, 0.5, dtype=np.float32),
        samples=np.full(shape + (samples_k,), 0.5, dtype=np.float32),
        subindex=subindex,
    )


def _ramp(rows: int, cols: int) -> np.ndarray:
    """Return a left-to-right luma ramp from 0 to 1 over the whole glyph ramp."""
    return np.tile(np.linspace(0.0, 1.0, cols, dtype=np.float32), (rows, 1))


def _chars(rows: int, cols: int) -> list[str]:
    """Return the tokens glyph_ramp places for a ramp grid, row-major, blanks as the dot."""
    grid = _grid(np.zeros((rows, cols), np.int32), luma=_ramp(rows, cols))
    renderer = get_renderer("glyph_ramp")
    return [BLANK if not entry.character.strip() else entry.character
            for entry in renderer.layout(grid, RenderStyle(options={}))]  # type: ignore


# --- accept: txt has cols * rows tokens and rows lines ---


def test_txt_has_one_token_per_cell_and_one_line_per_row() -> None:
    grid = _grid(np.zeros((5, 7), np.int32), luma=_ramp(5, 7))
    text = render_text(grid, BW, get_renderer("glyph_ramp"))
    lines = text.splitlines()
    assert len(lines) == 5
    assert sum(len(line.split(" ")) for line in lines) == 35


def test_txt_tokens_are_the_layout_characters() -> None:
    grid = _grid(np.zeros((3, 4), np.int32), luma=_ramp(3, 4))
    text = render_text(grid, BW, get_renderer("glyph_ramp"))
    assert [token for line in text.splitlines() for token in line.split(" ")] == _chars(3, 4)


def test_txt_ends_every_line_with_a_newline() -> None:
    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
    text = render_text(grid, BW, get_renderer("glyph_ramp"))
    assert text.endswith("\n")
    assert text.count("\n") == 2


def test_txt_is_utf8_without_escape_codes() -> None:
    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
    text = render_text(grid, BW, get_renderer("glyph_ramp"))
    assert "\x1b" not in text
    assert text.encode("utf-8").decode("utf-8") == text


def test_txt_keeps_a_blank_glyph_as_its_own_token() -> None:
    grid = _grid(np.zeros((1, 3), np.int32),
                 luma=np.array([[0.0, 1.0, 0.0]], dtype=np.float32))
    text = render_text(grid, BW, get_renderer("glyph_ramp"))
    tokens = text.rstrip("\n").split(" ")
    assert len(tokens) == 3
    assert tokens[1] == BLANK  # the white cell's space glyph stays one token (E1)


@pytest.mark.parametrize(("name", "geometry"), [("braille", (2, 4)), ("sextant", (2, 3))])
def test_a_bitmask_render_exports_txt_from_its_layout(name: str, geometry: tuple[int, int]) -> None:
    sx, sy = geometry
    grid = _grid(np.zeros((3, 3), np.int32), subindex=np.zeros((3, 3, sx * sy), np.int32))
    text = render_text(grid, BW, get_renderer(name))
    lines = text.splitlines()
    assert len(lines) == 3
    assert sum(len(line.split(" ")) for line in lines) == 9


# --- accept: ansi contains SGR 24-bit sequences only ---


def test_ansi_uses_only_24_bit_sequences() -> None:
    grid = _grid(np.zeros((3, 4), np.int32), luma=_ramp(3, 4))
    text = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
    sequences = SGR.findall(text)
    assert sequences
    assert all(TRUECOLOR.match(sequence) for sequence in sequences)


def test_ansi_carries_the_cell_ink_and_paper() -> None:
    grid = _grid(np.zeros((1, 1), np.int32), luma=np.zeros((1, 1), np.float32))
    text = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
    assert "\x1b[48;2;255;255;255m" in text  # paper #ffffff
    assert "\x1b[38;2;0;0;0m" in text  # ink #000000
    assert text.endswith("\x1b[0m\n")


def test_ansi_resets_each_line() -> None:
    grid = _grid(np.zeros((3, 3), np.int32), luma=_ramp(3, 3))
    lines = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi").splitlines()
    assert len(lines) == 3
    assert all(line.endswith("\x1b[0m") for line in lines)


def test_ansi_strips_back_to_the_same_characters() -> None:
    grid = _grid(np.zeros((2, 3), np.int32), luma=_ramp(2, 3))
    ansi = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
    plain = SGR.sub("", ansi)
    # ANSI paints one terminal cell per cell, so it carries no separators: the stripped
    # output is the row tokens joined, with no space between them.
    rows = ["".join(_chars(2, 3)[row * 3 : row * 3 + 3]) for row in range(2)]
    assert plain.splitlines() == rows


def test_ansi_never_leaks_into_the_text_path() -> None:
    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
    assert "\x1b" not in render_text(grid, BW, get_renderer("glyph_ramp"))


# --- accept: html renders the same grid and escapes < / & ---


def test_html_renders_the_same_grid() -> None:
    grid = _grid(np.zeros((2, 3), np.int32), luma=_ramp(2, 3))
    page = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="html")
    spans = re.findall(r"<span[^>]*>(.*?)</span>", page)
    assert spans == _chars(2, 3)
    assert page.count("\n") >= 2
    assert page.startswith("<!DOCTYPE html>")


def test_html_escapes_glyph_text() -> None:
    grid = _grid(np.zeros((1, 2), np.int32),
                 luma=np.array([[0.0, 1.0]], dtype=np.float32))
    page = render_text(grid, BW, get_renderer("glyph_ramp"),
                       RenderStyle(options={"ramp": "<&"}), fmt="html")
    assert "&lt;" in page and "&amp;" in page
    assert "<&" not in page


def test_html_states_the_grid_accessibly() -> None:
    grid = _grid(np.zeros((4, 5), np.int32), luma=_ramp(4, 5))
    page = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="html")
    assert '<meta charset="utf-8">' in page
    assert 'data-cols="5"' in page and 'data-rows="4"' in page
    assert "<pre" in page and "</pre>" in page


# --- interface: format validation and refusal to mislead ---


def test_every_documented_format_is_accepted() -> None:
    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
    assert FORMATS == ("txt", "ansi", "html")
    for fmt in FORMATS:
        assert render_text(grid, BW, get_renderer("glyph_ramp"), fmt=fmt)


def test_an_unknown_format_is_named() -> None:
    grid = _grid(np.zeros((1, 1), np.int32))
    with pytest.raises(ValueError, match="rtf"):
        render_text(grid, BW, get_renderer("glyph_ramp"), fmt="rtf")


def test_a_renderer_without_layout_is_refused() -> None:
    grid = _grid(np.zeros((2, 2), np.int32))
    with pytest.raises(ValueError, match="pixel"):
        render_text(grid, BW, get_renderer("pixel"))


def test_a_layout_that_is_not_one_per_cell_is_refused() -> None:
    grid = _grid(np.zeros((3, 4), np.int32), luma=_ramp(3, 4))
    with pytest.raises(ValueError, match="text"):
        render_text(grid, BW, get_renderer("text"), fmt="ansi")


def test_render_text_is_pure_and_writes_no_file(tmp_path) -> None:
    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
    renderer = get_renderer("glyph_ramp")
    before = sorted(tmp_path.iterdir())
    assert render_text(grid, BW, renderer) == render_text(grid, BW, renderer)
    assert sorted(tmp_path.iterdir()) == before


def test_the_ansi_escapes_are_only_resets_and_truecolor() -> None:
    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
    text = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
    heads = {sequence.split(";")[0] for sequence in SGR.findall(text)}
    assert heads <= {"0", "38", "48"}
