"""The GlyphShapeRenderer: one monospace character per cell, chosen by shape (§9).

Six sampling circles per cell (top/middle/bottom x left/right) give every glyph a
six-component shape vector: the fraction of each circle covered by the glyph's ink. Each
component of that vector is divided by the maximum of that component across the alphabet
(the §9 normalisation, AMD-011), so every circle spans the full [0, 1] range instead of
clustering near zero; the cell vector itself stays in raw fractions, so a flat cell reads
as flat instead of being stretched into a shape it does not have. A cell's vector is read
from ``grid.samples`` -- the six circle centres, which the pipeline samples through
``sample_points()`` -- and matched to the nearest glyph vector. Both sides are compared in
the coverage domain: ``ink = 1 - linear_to_srgb(samples)``, so a 50% grey reads as 0.5 ink,
the same unit as a disk's covered area. Shape vectors are precomputed per (font, cell size,
alphabet) in one bounded module-level cache that never changes the output (§3 invariant 2,
H11).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

import numpy as np
from PIL import Image as PILImage

from lattice import color
from lattice.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
from lattice.renderers.glyph_ramp import GlyphPlacement, _font_key, _glyph_mask, _groups
from lattice.types import Palette

NAME = "glyph_shape"
CELL_ASPECT = 0.5
DEFAULT_ALPHABET = "".join(chr(code) for code in range(32, 127))  # printable ASCII, blank first
DEFAULT_FG = "#000000"
DEFAULT_BG = "#ffffff"
CIRCLES = 6
# Circle centres in cell coordinates, y-major: top/middle/bottom x left/right (§3, §9).
_CIRCLE_X = (0.28, 0.72)
_CIRCLE_Y = (0.22, 0.50, 0.78)
_CIRCLE_RADIUS = 0.13  # of the cell's short side: a disk, not a point
_SHAPE_CACHE_SIZE = 32  # one table is (alphabet x 6) floats per cell size; 32 bounds it to ~12 MB
_HEX_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class GlyphShapeOptions:
    """Validated options of one glyph_shape render; there is no size option (H11)."""

    alphabet: str = DEFAULT_ALPHABET
    font: str | None = None
    fg: str = DEFAULT_FG
    bg: str = DEFAULT_BG
    normalise: bool = True


class ShapeTable(NamedTuple):
    """The alphabet's shape vectors: raw disk fractions and their normalised form (§9)."""

    raw: np.ndarray  # (n, 6) float32, ink fraction per circle
    maxima: np.ndarray  # (6,) float32, the alphabet maximum of each component
    normalised: np.ndarray  # (n, 6) float32, raw divided by maxima


class GlyphShapeRenderer:
    """Draw one monospace character per cell, its shape chosen by the six-circle stencil."""

    name = NAME

    def cell_aspect(self) -> float:
        """Return 0.5: the default monospace font ratio, width over height (§9)."""
        return CELL_ASPECT

    def subgrid(self) -> tuple[int, int]:
        """Return (1, 1): one glyph covers the whole cell, with no sub-points."""
        return (1, 1)

    def consumes(self) -> frozenset[str]:
        """Return {"samples"}: the six circle samples pick the glyph, nothing else is read.

        Colour comes from the ``fg``/``bg`` options, so neither ``index`` nor the palette
        changes the output, and ``luma`` is never read: the six circle luminances in
        ``samples`` are the whole input (§3, §9, AMD-011).
        """
        return frozenset({"samples"})

    def sample_points(self) -> np.ndarray:
        """Return the (6, 2) stencil: circle centres, top/middle/bottom x left/right (§3)."""
        return np.asarray([(x, y) for y in _CIRCLE_Y for x in _CIRCLE_X], dtype=np.float32)

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
        """Rasterise the shape-matched glyphs of grid into an image of the grid geometry."""
        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))

    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
        """Return the unrounded frame: glyph ink over paper, float32 (H, W, 3) in [0, 1]."""
        return _frame(grid, _read_options(style))

    def layout(
        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
    ) -> list[GlyphPlacement]:
        """Return one placed glyph per cell, row-major (§3, §11).

        Both the §3 ``layout(grid, style)`` form and the ``layout(grid, palette, style)`` form
        the other glyph renderers use are accepted; the palette never changes the character.
        """
        palette, style = _layout_arguments(palette, style)
        options = _read_options(style)
        index = _assignments(grid, options)
        placed: list[GlyphPlacement] = []
        for row in range(grid.rows):
            for col in range(grid.cols):
                placed.append(GlyphPlacement(
                    options.alphabet[int(index[row, col])],
                    float(col * grid.cell_w), float(row * grid.cell_h),
                    float(grid.cell_w), float(grid.cell_h),
                    options.fg.lower(), options.bg.lower(),
                ))
        return placed


def _layout_arguments(
    palette: Palette | None, style: RenderStyle | None
) -> tuple[Palette | None, RenderStyle]:
    """Disambiguate layout()'s two call forms: (grid, style) and (grid, palette, style)."""
    if isinstance(palette, RenderStyle):
        return None, palette
    if style is None:
        raise TypeError("layout() needs a RenderStyle: layout(grid, style)")
    return palette, style


def _read_options(style: RenderStyle) -> GlyphShapeOptions:
    """Validate style.options and return the typed options of one glyph_shape render.

    Unknown keys are ignored, so a preset written by a newer app still renders (§6).
    """
    raw = dict(style.options)
    alphabet = raw.get("alphabet", DEFAULT_ALPHABET)
    if not isinstance(alphabet, str) or not alphabet:
        raise ValueError(f"glyph_shape alphabet must be a non-empty string, got {alphabet!r}")
    font = raw.get("font")
    if font is not None and not isinstance(font, str):
        raise ValueError(f"glyph_shape font must be a path string or null, got {font!r}")
    _font_identity(font)  # ValueError naming the path, before anything is drawn or laid out
    normalise = raw.get("normalise", True)
    if not isinstance(normalise, bool):
        raise ValueError(f"glyph_shape normalise must be a boolean, got {normalise!r}")
    return GlyphShapeOptions(
        alphabet=alphabet,
        font=font,
        fg=_colour_option(raw, "fg", DEFAULT_FG),
        bg=_colour_option(raw, "bg", DEFAULT_BG),
        normalise=normalise,
    )


def _font_identity(path: str | None) -> tuple[str | None, int, int]:
    """Return glyph_ramp's font cache key, re-raising its error under this renderer's name."""
    try:
        return _font_key(path)
    except ValueError as exc:
        raise ValueError(f"glyph_shape font file not found: {path}") from exc


def _colour_option(raw: dict, key: str, default: str) -> str:
    """Return one #rrggbb option as text, validating it before any drawing happens."""
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"glyph_shape {key} must be a colour string, got {value!r}")
    digits = value.strip().lower().lstrip("#")
    if len(digits) != 6 or not _HEX_DIGITS.issuperset(digits):
        raise ValueError(f"glyph_shape {key} must be #rrggbb, got {value!r}")
    return value


def _parse_colour(value: str) -> np.ndarray:
    """Parse #rrggbb into a float32 (3,) sRGB row in [0, 1]."""
    digits = value.strip().lower().lstrip("#")
    return np.asarray([int(digits[at : at + 2], 16) / 255.0 for at in (0, 2, 4)],
                      dtype=np.float32)


def _circle_weights(cell_w: int, cell_h: int) -> np.ndarray:
    """Return the (6, cell_h*cell_w) float32 disk weights of the six sampling circles.

    Row k holds the normalised disk of circle k, so a glyph's shape vector is one matmul.
    A cell too small to contain a disk falls back to its nearest pixel, never to an empty row.
    """
    rows, cols = np.mgrid[0:cell_h, 0:cell_w]
    radius = max(0.5, _CIRCLE_RADIUS * float(min(cell_w, cell_h)))
    weights = np.zeros((CIRCLES, cell_h * cell_w), dtype=np.float32)
    for k, (centre_x, centre_y) in enumerate((x, y) for y in _CIRCLE_Y for x in _CIRCLE_X):
        x, y = centre_x * cell_w, centre_y * cell_h
        disk = (cols + 0.5 - x) ** 2 + (rows + 0.5 - y) ** 2 <= radius * radius
        if not disk.any():
            disk[min(cell_h - 1, int(y)), min(cell_w - 1, int(x))] = True
        weights[k] = disk.reshape(-1) / np.float32(disk.sum())
    return weights


@lru_cache(maxsize=_SHAPE_CACHE_SIZE)
def _shape_table(
    font_key: tuple[str | None, int, int], cell_w: int, cell_h: int, alphabet: str
) -> ShapeTable:
    """Return the read-only shape vectors of alphabet, cached per font, cell and alphabet.

    Every input is part of the key, the cache is bounded, and the returned arrays are not
    writable, so no caller can observe or cause a change of the rendered output (§3, H11).
    """
    masks = np.stack([
        _glyph_mask(char, font_key[0], cell_w, cell_h).reshape(-1) for char in alphabet
    ])
    raw = np.ascontiguousarray(masks @ _circle_weights(cell_w, cell_h).T, dtype=np.float32)
    maxima = np.ascontiguousarray(raw.max(axis=0), dtype=np.float32)
    divisor = np.where(maxima > 0.0, maxima, np.float32(1.0)).astype(np.float32)
    normalised = np.ascontiguousarray(raw / divisor, dtype=np.float32)
    for array in (raw, maxima, normalised):
        array.setflags(write=False)
    return ShapeTable(raw=raw, maxima=maxima, normalised=normalised)


def _table(options: GlyphShapeOptions, cell_w: int, cell_h: int) -> ShapeTable:
    """Return the cached shape table of one render's font, cell size and alphabet."""
    return _shape_table(_font_key(options.font), cell_w, cell_h, options.alphabet)


def _ink_vectors(grid: CellGrid) -> np.ndarray:
    """Return the (rows, cols, 6) ink fraction of every cell, read from grid.samples.

    ``samples`` holds the source luminance at the six circle centres in linear light (§3,
    S2). The glyph vectors are covered *areas*, so the samples are re-encoded to sRGB
    before the complement: a 50% grey then reads as 0.5 ink instead of 0.786, and both
    sides of the nearest-neighbour search are the same quantity.
    """
    samples = np.asarray(grid.samples, dtype=np.float32)
    expected = (grid.rows, grid.cols, CIRCLES)
    if samples.shape != expected:
        raise ValueError(
            f"glyph_shape needs grid.samples of shape {expected} (six circles, §3), "
            f"got {samples.shape}"
        )
    ink = np.float32(1.0) - color.linear_to_srgb(samples)
    return np.ascontiguousarray(np.clip(ink, 0.0, 1.0), dtype=np.float32)


def _assignments(grid: CellGrid, options: GlyphShapeOptions) -> np.ndarray:
    """Return the (rows, cols) intp alphabet index of every cell's nearest shape vector.

    The glyph vectors are normalised per component by the alphabet maximum (§9, AMD-011),
    so each circle spans the full [0, 1] range and the sparse corners carry as much weight
    as the dense middle. Under AMD-011 the cell vector stays in raw disk fractions -- the
    unit of the un-normalised alphabet -- so a flat cell still reads as flat instead of
    being stretched into a shape it does not have. ``normalise=False`` matches raw
    fractions on both sides, which is the clustering behaviour §9's normalisation fixes.
    """
    table = _table(options, grid.cell_w, grid.cell_h)
    reference = table.normalised if options.normalise else table.raw
    flat = _ink_vectors(grid).reshape(-1, CIRCLES)
    squared = (reference * reference).sum(axis=1)[None, :]
    distance = squared - np.float32(2.0) * (flat @ reference.T)
    return np.argmin(distance, axis=1).reshape(grid.rows, grid.cols)


def _frame(grid: CellGrid, options: GlyphShapeOptions) -> np.ndarray:
    """Return the (rows*cell_h, cols*cell_w, 3) float32 frame of one glyph_shape render."""
    index = _assignments(grid, options)
    fg, bg = _parse_colour(options.fg), _parse_colour(options.bg)
    frame = np.empty((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3), dtype=np.float32)
    view = frame.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w, 3)
    view[...] = bg
    for value, cells in enumerate(_groups(index, len(options.alphabet))):
        if cells.size == 0:
            continue
        rows, cols = np.divmod(cells, grid.cols)
        mask = _glyph_mask(options.alphabet[value], options.font, grid.cell_w, grid.cell_h)
        view[rows, :, cols, :, :] = bg + mask[None, :, :, None] * (fg - bg)
    return np.ascontiguousarray(frame, dtype=np.float32)


def register_glyph_shape_renderer() -> CellRenderer:
    """Register the GlyphShapeRenderer under "glyph_shape" and return it."""
    return register_renderer(GlyphShapeRenderer())


register_glyph_shape_renderer()
