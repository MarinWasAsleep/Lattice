"""SVG export of a CellGrid, from ``layout()`` when the renderer has one (§11, H11).

``pixel`` exports merged ``<rect>`` runs of palette colour; a renderer with ``layout()``
exports editable typography, the paper as rects plus one ``<text>`` per placed glyph. The
document is capped in UTF-8 bytes by ``max_bytes``: a glyph export over the cap degrades to
rectangles of cell ink at its coverage, and a body that still does not fit is coalesced into
square blocks, each step recorded as a warning naming the cap. Strings only, no file.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from lattice_core.cell import CellGrid, CellRenderer, RenderStyle
from lattice_core.types import Palette

SVG_NS = "http://www.w3.org/2000/svg"
DEFAULT_MAX_BYTES = 8_000_000
TRANSPARENT = "transparent"
NONE = 'fill="none"'
MONOSPACE = "monospace"
_HEX_DIGITS = frozenset("0123456789abcdef")
_PLACEMENT_FIELDS = 6
_BASELINE = 0.8  # baseline as a fraction of the font size, measured from a glyph box's top
_MIN_RECT_BYTES = 40  # lower bound on one <rect>; below it a run merge is worth attempting
_Layer = tuple[np.ndarray, list[str]]


@dataclass(frozen=True)
class Glyph:
    """One placed glyph, normalised from any renderer's layout entry (§3, §11)."""

    character: str
    x: float
    y: float
    width: float
    height: float
    fill: str
    paper: str | None = None
    size: float | None = None
    opacity: float | None = None


def render_svg(
    grid: CellGrid,
    palette: Palette,
    renderer: CellRenderer,
    style: RenderStyle | None = None,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[str, list[str]]:
    """Return the SVG document of grid and the warnings raised while keeping its budget.

    A renderer with ``layout()`` exports one ``<text>`` per placed glyph over its paper; any
    other renderer exports merged ``<rect>`` runs of palette colour (§11). A document that
    would exceed max_bytes is degraded to rectangles, then to blocks, with a warning each.
    """
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be a positive number of UTF-8 bytes, got {max_bytes!r}")
    style = RenderStyle(options={}) if style is None else style
    header = _header(grid.cols * grid.cell_w, grid.rows * grid.cell_h)
    allowance = int(max_bytes) - _size([header, "</svg>"])
    glyphs = _placements(grid, palette, renderer, style)
    warnings: list[str] = []
    parts: list[str] | None = None
    if glyphs is not None:
        parts = _text_body(glyphs, grid, style, allowance)
        if parts is None:
            warnings.append(
                f"svg export exceeded the {int(max_bytes)}-byte budget: "
                f"{len(glyphs)} glyphs merged into cell rectangles"
            )
    if parts is None:
        parts, warning = _rect_body(grid, palette, glyphs, style, allowance)
        if warning is not None:
            warnings.append(f"svg export over the {int(max_bytes)}-byte budget: {warning}")
    return "\n".join([header, *parts, "</svg>"]) + "\n", warnings


def _size(parts: list[str]) -> int:
    """Return the UTF-8 size of a body in bytes."""
    return sum(len(part.encode("utf-8")) for part in parts)


def _header(width: int, height: int) -> str:
    """Return the root element, carrying the exact output pixel geometry."""
    return (
        f'<svg xmlns="{SVG_NS}" version="1.1" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" xml:space="preserve">'
    )


def _text_body(
    glyphs: list[Glyph], grid: CellGrid, style: RenderStyle, allowance: int
) -> list[str] | None:
    """Return the paper rects then one <text> per glyph, or None once the body is too large.

    Sizes are charged as the fragments are built, so a document that cannot fit never
    materialises: memory stays bounded by the budget, not by the glyph count (§11).
    """
    paper = _rects(*_encode(_paper_codes(glyphs, grid, style)), grid.cell_w, grid.cell_h)
    used = _size(paper)
    if used > allowance:
        return None
    family = _family(style)
    parts = list(paper)
    for glyph in glyphs:
        element = _text_element(glyph, family)
        used += len(element.encode("utf-8"))
        if used > allowance:
            return None
        parts.append(element)
    return parts


def _rect_body(grid: CellGrid, palette: Palette, glyphs: list[Glyph] | None,
               style: RenderStyle, allowance: int) -> tuple[list[str], str | None]:
    """Return the rectangle body and the warning of the degradation applied to fit it.

    Runs of equal cells give the finest body; one that does not fit is coalesced into 2x2,
    4x4, ... blocks painted with their top-left cell (E1). The exact count picks the first
    block size, so a huge source is never expanded into millions of fragments.
    """
    layers = _layers(grid, palette, glyphs, style)

    def at(step: int) -> list[str]:
        """Return the rect elements of every layer sampled every step cells."""
        return [rect for ids, paints in layers
                for rect in _rects(ids[::step, ::step], paints,
                                   grid.cell_w * step, grid.cell_h * step)]

    limit = max(grid.rows, grid.cols)
    block = 1
    while block < limit and sum(_box_count(ids[::block, ::block]) for ids, _ in layers
                                ) * _MIN_RECT_BYTES > allowance:
        block *= 2
    parts = at(block)
    while _size(parts) > allowance and block < limit:
        block *= 2
        parts = at(block)
    if _size(parts) > allowance:
        return parts, f"one {limit}-cell block still does not fit"
    return parts, None if block == 1 else f"cells coalesced into {block}x{block} blocks"


def _box_count(ids: np.ndarray) -> int:
    """Return the exact number of merged rectangles ``_rects`` emits for ids.

    One per horizontal run, minus the runs continuing the run above with the same label,
    start and end; each row is numpy work, so 2048x2048 costs seconds (§11).
    """
    rows, cols = ids.shape
    if rows == 0 or cols == 0:
        return 0
    span = np.int64(cols + 1)
    boxes, previous = 0, np.empty(0, dtype=np.int64)
    for row in range(rows):
        line = ids[row]
        starts = np.ones(cols, dtype=bool)
        if cols > 1:
            starts[1:] = line[1:] != line[:-1]
        at = np.nonzero(starts)[0].astype(np.int64)
        ends = np.empty(at.size, dtype=np.int64)
        ends[:-1], ends[-1] = at[1:], cols
        keys = line[at] * span * span + at * span + ends
        boxes += int(at.size) - (np.intersect1d(keys, previous).size if previous.size else 0)
        previous = keys
    return boxes


def _layers(
    grid: CellGrid, palette: Palette, glyphs: list[Glyph] | None, style: RenderStyle
) -> list[_Layer]:
    """Return the paint layers of the rectangle body, painted in order: paper, then ink."""
    if glyphs is None:
        return [_encode(_palette_codes(grid, palette))]
    paper = _paper_codes(glyphs, grid, style)
    ink = _layout_codes(glyphs, grid, "fill")
    coverage = np.asarray(grid.coverage, dtype=np.float32).reshape(grid.rows, grid.cols)
    alpha = np.where(ink == TRANSPARENT, np.float32(0.0), coverage)
    return [_encode(paper), _encode(ink, alpha)]


def _family(style: RenderStyle) -> str:
    """Return the SVG font-family of style: the font file's stem, or monospace."""
    font = style.options.get("font")
    if isinstance(font, str) and font.strip():
        stem = Path(font).stem.strip().replace("_", " ")
        if stem:
            return _escape(stem)
    return MONOSPACE


def _escape(text: str) -> str:
    """Return text with the XML metacharacters escaped, quotes included."""
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return out.replace('"', "&quot;").replace("'", "&apos;")


def _placements(
    grid: CellGrid, palette: Palette, renderer: CellRenderer, style: RenderStyle
) -> list[Glyph] | None:
    """Return the placed glyphs of renderer's layout(), or None when it has none (§11)."""
    layout = getattr(renderer, "layout", None)
    if not callable(layout):
        return None
    background = _style_colour(style, "bg") or TRANSPARENT
    return [_glyph(item, background) for item in _call_layout(layout, grid, palette, style)]


def _call_layout(
    layout: Callable[..., Any], grid: CellGrid, palette: Palette, style: RenderStyle
) -> list[Any]:
    """Call layout() in the three-argument form, or §3's two-argument form if it takes it.

    ``glyph_ramp`` and ``glyph_shape`` accept ``layout(grid, style)``; ``bitmask`` and
    ``text`` need ``layout(grid, palette, style)``. The signature decides, never a retry.
    """
    try:
        parameters = list(inspect.signature(layout).parameters.values())
    except (TypeError, ValueError):
        return list(layout(grid, palette, style))
    positional = [
        value for value in parameters
        if value.kind in (value.POSITIONAL_ONLY, value.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 3 or any(value.kind is value.VAR_POSITIONAL for value in parameters):
        return list(layout(grid, palette, style))
    return list(layout(grid, style))


def _style_colour(style: RenderStyle, key: str) -> str | None:
    """Return one style colour option as normalised text when it is a colour, else None."""
    value = style.options.get(key)
    if isinstance(value, str) and _digits(value) is not None:
        return value.strip().lower()
    return None


def _glyph(item: Any, background: str) -> Glyph:
    """Normalise one layout entry (GlyphPlacement, TextGlyph or 6-tuple), paper defaulting to bg."""
    fields = tuple(item)
    if len(fields) < _PLACEMENT_FIELDS:
        raise ValueError(
            f"layout() must place at least {_PLACEMENT_FIELDS} fields per glyph, got {fields!r}"
        )
    character, x, y, width, height, fill = fields[:_PLACEMENT_FIELDS]
    paper = fields[6] if len(fields) > 6 and isinstance(fields[6], str) else background
    size = fields[7] if len(fields) > 7 and isinstance(fields[7], (int, float)) else None
    opacity = getattr(item, "opacity", None)
    return Glyph(
        character=str(character), x=float(x), y=float(y), width=float(width),
        height=float(height), fill=str(fill).strip().lower(),
        paper=str(paper).strip().lower(),
        size=float(size) if size is not None else None,
        opacity=float(opacity) if isinstance(opacity, (int, float)) else None,
    )


def _text_element(glyph: Glyph, family: str) -> str:
    """Return one <text> element: its position, font size, family and ink colour (§11)."""
    size = glyph.size if glyph.size and glyph.size > 0.0 else glyph.height
    baseline = glyph.y + _BASELINE * size
    return (
        f'<text x="{_number(glyph.x)}" y="{_number(baseline)}" '
        f'font-family="{_escape(family)}" font-size="{_number(size)}" '
        f'{_paint(glyph.fill, glyph.opacity)}>{_escape(glyph.character)}</text>'
    )


def _number(value: float) -> str:
    """Format one coordinate or size without trailing zeros."""
    return str(int(value)) if float(value).is_integer() else f"{round(float(value), 3):g}"


def _digits(colour: str | None) -> str | None:
    """Return the hex digits of #rrggbb or #rrggbbaa, or None for transparent or unknown."""
    digits = "" if colour is None else str(colour).strip().lower().lstrip("#")
    if len(digits) in (6, 8) and _HEX_DIGITS.issuperset(digits):
        return digits
    return None


def _paint(colour: str | None, opacity: float | None = None) -> str:
    """Return the fill attributes of one colour: a hex fill with its opacity, or fill="none"."""
    digits = _digits(colour)
    if digits is None:
        return NONE
    attributes = f'fill="#{digits[:6]}"'
    alpha = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
    if opacity is not None:
        alpha *= min(1.0, max(0.0, opacity))
    if alpha < 1.0:
        attributes += f' fill-opacity="{round(alpha, 2):g}"'
    return attributes


def _palette_codes(grid: CellGrid, palette: Palette) -> np.ndarray:
    """Return the (rows, cols) string array of #rrggbb cell colours of a pixel render."""
    array = np.asarray(palette, dtype=np.float32)[np.asarray(grid.index, dtype=np.intp), :3]
    rgb8 = np.floor(np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.int32)
    packed = (rgb8[..., 0] << 16) | (rgb8[..., 1] << 8) | rgb8[..., 2]
    codes, ids = np.unique(packed, return_inverse=True)
    return np.array([f"#{int(code):06x}" for code in codes], dtype=object)[
        np.asarray(ids).reshape(grid.rows, grid.cols)]


def _layout_codes(glyphs: list[Glyph], grid: CellGrid, field: str) -> np.ndarray:
    """Return one layout colour per cell, row-major when the layout is exactly one per cell."""
    codes = np.full((grid.rows, grid.cols), TRANSPARENT, dtype=object)
    if len(glyphs) == grid.rows * grid.cols:
        codes.flat[:] = [getattr(glyph, field) or TRANSPARENT for glyph in glyphs]
        return codes
    for glyph in glyphs:
        row, col = _cell_of(glyph, grid)
        codes[row, col] = getattr(glyph, field) or TRANSPARENT
    return codes


def _paper_codes(glyphs: list[Glyph], grid: CellGrid, style: RenderStyle) -> np.ndarray:
    """Return the paper colour of every cell, complete when the layout does not tile the grid.

    A renderer whose layout does not place one glyph per cell (``text`` lays out a paragraph,
    not a grid) leaves cells uncovered: those cells take the style's ``bg`` colour, exactly as
    its rasterisation paints them, so the vector and raster outputs agree (§3, §11, E1).
    """
    codes = _layout_codes(glyphs, grid, "paper")
    if len(glyphs) == grid.rows * grid.cols:
        return codes
    background = _style_colour(style, "bg") or TRANSPARENT
    return np.where(codes == TRANSPARENT, background, codes)


def _cell_of(glyph: Glyph, grid: CellGrid) -> tuple[int, int]:
    """Return the (row, col) cell a placed glyph box starts in, clamped to the grid."""
    col = int(glyph.x // grid.cell_w) if grid.cell_w > 0 else 0
    row = int(glyph.y // grid.cell_h) if grid.cell_h > 0 else 0
    return min(grid.rows - 1, max(0, row)), min(grid.cols - 1, max(0, col))


def _encode(codes: np.ndarray, alpha: np.ndarray | None = None) -> _Layer:
    """Return the (rows, cols) int32 ids of codes and the paint string of every label."""
    labels, ids = np.unique(np.asarray(codes, dtype=object).astype(str), return_inverse=True)
    ids = np.asarray(ids).reshape(np.shape(codes)).astype(np.int64)
    if alpha is None:
        return ids.astype(np.int32), [_paint(str(label)) for label in labels]
    levels = np.round(np.clip(np.asarray(alpha, np.float32), 0.0, 1.0), 2)
    alphas, aid = np.unique(levels, return_inverse=True)
    aid = np.asarray(aid).reshape(ids.shape).astype(np.int64)
    keys, combined = np.unique(ids * alphas.size + aid, return_inverse=True)
    paints = [
        _paint(str(labels[int(key) // alphas.size]), float(alphas[int(key) % alphas.size]))
        for key in keys
    ]
    return np.asarray(combined).reshape(ids.shape).astype(np.int32), paints


def _rects(ids: np.ndarray, paints: list[str], cell_w: int, cell_h: int) -> list[str]:
    """Return one <rect> per rectangle of equal cells, merged along rows then down columns."""
    ids = np.asarray(ids)
    open_runs: dict[tuple[int, int, int], list[int]] = {}
    boxes: list[tuple[int, int, int, int, int]] = []
    for row in range(ids.shape[0]):
        line = ids[row]
        changes = (np.nonzero(np.diff(line))[0] + 1).tolist() if line.size > 1 else []
        starts = [0, *changes]
        ends = [*changes, int(line.size)]
        current: dict[tuple[int, int, int], list[int]] = {}
        for start, end in zip(starts, ends, strict=True):
            key = (int(line[start]), start, end - start)
            current[key] = [open_runs[key][0] if key in open_runs else row, row]
        for key, (first, last) in open_runs.items():
            if key not in current:
                boxes.append((first, key[1], key[2], last - first + 1, key[0]))
        open_runs = current
    for key, (first, last) in open_runs.items():
        boxes.append((first, key[1], key[2], last - first + 1, key[0]))
    parts: list[str] = []
    for top, left, width, height, label in sorted(boxes):
        paint = paints[label]
        if paint != NONE:
            parts.append(
                f'<rect x="{left * cell_w}" y="{top * cell_h}" '
                f'width="{width * cell_w}" height="{height * cell_h}" {paint}/>'
            )
    return parts


__all__ = ["DEFAULT_MAX_BYTES", "SVG_NS", "Glyph", "render_svg"]
