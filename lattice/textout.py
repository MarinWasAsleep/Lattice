"""Text export of a CellGrid from the renderer's ``layout()``: txt, ansi and html (§11, P3).

One placement per cell is the premise of every format: a renderer whose layout does not place
exactly ``cols * rows`` boxes has no cell grid to print, so this module raises instead of
producing a misleading file. ``.txt`` is UTF-8, cells separated by one space, one ``\\n`` per
row. ``.ansi`` is truecolor only: each cell sets its 24-bit background then foreground, and
every line ends with a bare SGR reset, so no 8- or 16-colour code is ever emitted. ``.html``
is a standalone page whose ``<pre>`` carries the same grid, with the glyph text escaped.
Strings only: this module never writes a file (the caller does).
"""

from __future__ import annotations

import html
import re

from lattice.cell import CellGrid, CellRenderer, RenderStyle
from lattice.svg import Glyph, _digits, _placements
from lattice.types import Palette

FORMATS = ("txt", "ansi", "html")
BLANK = "\u00b7"  # the token written for a cell whose glyph is whitespace (E1, §11)
_RESET = "\x1b[0m"
_WHITESPACE = re.compile(r"[\t\r\n]+")


def render_text(
    grid: CellGrid,
    palette: Palette,
    renderer: CellRenderer,
    style: RenderStyle | None = None,
    *,
    fmt: str = "txt",
) -> str:
    """Return grid printed in fmt ("txt", "ansi" or "html"), one token per cell.

    fmt is case-sensitive; any other value raises ValueError naming it. A renderer without a
    layout, or whose layout does not place exactly cols * rows glyphs, raises ValueError
    naming the renderer and the format (§11: no misleading text export is written).
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown text format {fmt!r}; expected one of {FORMATS}")
    style = RenderStyle(options={}) if style is None else style
    placements = _placements(grid, palette, renderer, style)
    cells = _cell_rows(placements, grid, renderer, fmt)
    if fmt == "ansi":
        return _ansi(cells)
    if fmt == "html":
        return _html(cells, grid)
    return _txt(cells)


def _cell_rows(
    placements: list[Glyph] | None, grid: CellGrid, renderer: CellRenderer, fmt: str
) -> list[list[Glyph]]:
    """Return the placements as rows of cells, refusing a layout that is not one per cell."""
    name = getattr(renderer, "name", type(renderer).__name__)
    if placements is None:
        raise ValueError(f"renderer {name!r} has no layout() and cannot export {fmt!r}")
    expected = grid.cols * grid.rows
    if len(placements) != expected:
        raise ValueError(
            f"renderer {name!r} cannot export {fmt!r}: its layout places "
            f"{len(placements)} glyphs for {expected} cells"
        )
    return [[placements[row * grid.cols + col] for col in range(grid.cols)]
            for row in range(grid.rows)]


def _token(glyph: Glyph) -> str:
    """Return one glyph's text token: never blank, so every cell stays exactly one token.

    A renderer may place a space (a blank glyph, a white cell); space-separated, such a token
    would vanish and shift the row's columns. A whitespace glyph is therefore written as a
    middle dot (E1, §11): the grid keeps ``cols * rows`` tokens over ``rows`` lines, and the
    dot reads as the empty cell.
    """
    token = _WHITESPACE.sub(" ", glyph.character)
    return BLANK if not token.strip() else token


def _txt(cells: list[list[Glyph]]) -> str:
    """Return the cells space-separated, one newline-terminated line per row."""
    return "".join(" ".join(_token(glyph) for glyph in row) + "\n" for row in cells)


def _rgb(colour: str | None) -> tuple[int, int, int] | None:
    """Return the (r, g, b) bytes of a colour, or None when it paints nothing."""
    digits = _digits(colour)
    if digits is None:
        return None
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def _ansi(cells: list[list[Glyph]]) -> str:
    """Return the cells as 24-bit SGR coloured characters, one reset-terminated line per row."""
    lines: list[str] = []
    for row in cells:
        parts: list[str] = []
        coloured = False
        for glyph in row:
            sequence = _sgr(glyph)
            coloured = coloured or bool(sequence)
            parts.append(sequence + _token(glyph))
        lines.append("".join(parts) + (_RESET if coloured else "") + "\n")
    return "".join(lines)


def _sgr(glyph: Glyph) -> str:
    """Return the 24-bit background then foreground SGR of a cell, empty if it paints nothing."""
    sequence = ""
    background = _rgb(glyph.paper)
    if background is not None:
        sequence += f"\x1b[48;2;{background[0]};{background[1]};{background[2]}m"
    foreground = _rgb(glyph.fill)
    if foreground is not None:
        sequence += f"\x1b[38;2;{foreground[0]};{foreground[1]};{foreground[2]}m"
    return sequence


def _html(cells: list[list[Glyph]], grid: CellGrid) -> str:
    """Return a standalone HTML page whose <pre> renders the same grid, text escaped."""
    body = "".join("".join(_span(glyph) for glyph in row) + "\n" for row in cells)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>Lattice export ({grid.cols}x{grid.rows})</title>\n"
        "<style>pre{font-family:monospace;line-height:1;margin:0;padding:0}</style>\n"
        "</head>\n<body>\n"
        f'<pre data-cols="{grid.cols}" data-rows="{grid.rows}">'
        + body
        + "</pre>\n</body>\n</html>\n"
    )


def _span(glyph: Glyph) -> str:
    """Return one escaped <span> carrying the cell's ink and paper colours."""
    styles: list[str] = []
    paper = _rgb(glyph.paper)
    if paper is not None:
        styles.append(f"background:#{paper[0]:02x}{paper[1]:02x}{paper[2]:02x}")
    ink = _rgb(glyph.fill)
    if ink is not None:
        styles.append(f"color:#{ink[0]:02x}{ink[1]:02x}{ink[2]:02x}")
    attributes = f' style="{";".join(styles)}"' if styles else ""
    return f"<span{attributes}>{html.escape(_token(glyph))}</span>"


__all__ = ["FORMATS", "render_text"]
