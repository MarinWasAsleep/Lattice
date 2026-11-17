"""The GlyphRampRenderer: one monospace character per cell, indexed by luma (§9).

The ramp contract is explicit and documented, never detected: darkest character first,
lightest last. ``grid.luma`` (S2) picks the character through its sRGB-perceptual encoding
(AMD-010), so a black/white palette still uses the full ramp. There is no ``size`` option
(H11): the font size derives from ``cell_h``. Module state is one bounded, input-keyed glyph
mask cache that never changes the output (§3 invariant 2, H11).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from lattice_core import color
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
from lattice_core.types import Palette

NAME = "glyph_ramp"
DEFAULT_RAMP = "@%#*+=-:. "
CELL_ASPECT = 0.5
MODES = ("mono", "fg_colour", "bg_colour", "palette")
DEFAULT_FG = "#000000"
DEFAULT_BG = "#ffffff"
TRANSPARENT = "transparent"
_EPSILON = 1e-6
_PROBE_SIZE = 100
_HEX_DIGITS = frozenset("0123456789abcdef")
_MASK_CACHE_SIZE = 256


@dataclass(frozen=True)
class GlyphRampOptions:
    """Validated options of one glyph_ramp render (§9); there is no size option (H11)."""

    ramp: str = DEFAULT_RAMP
    font: str | None = None
    fg: str = DEFAULT_FG
    bg: str = DEFAULT_BG
    mode: str = "mono"
    offset: float = 0.0
    invert: bool = False


class GlyphPlacement(NamedTuple):
    """One placed glyph: §3's six fields, plus the paper colour the cell was drawn on."""

    character: str
    x: float
    y: float
    width: float
    height: float
    fill: str
    paper: str


class GlyphRampRenderer:
    """Draw one monospace character per cell, its ink density chosen by the cell luma."""

    name = NAME

    def cell_aspect(self) -> float:
        """Return 0.5: the default monospace font ratio, width over height (§9)."""
        return CELL_ASPECT

    def subgrid(self) -> tuple[int, int]:
        """Return (1, 1): one glyph covers the whole cell, with no sub-points."""
        return (1, 1)

    def consumes(self) -> frozenset[str]:
        """Return {"luma", "index"}: luma picks the glyph, index the palette colour."""
        return frozenset({"luma", "index"})

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
        """Rasterise the glyph ramp of grid into an image of the exact grid geometry.

        The image is RGBA when a colour option is ``transparent``, RGB otherwise.
        """
        frame = _frame(grid, palette, _read_options(style))
        pixels = color.to_rgb8(frame)
        return PILImage.fromarray(pixels, "RGBA" if frame.shape[2] == 4 else "RGB")

    def layout(
        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
    ) -> list[GlyphPlacement]:
        """Return one placed glyph per cell, row-major (§3, §11).

        ``fill`` is the ink colour and ``paper`` the background colour of the cell; either is
        ``#rrggbbaa`` when translucent and ``transparent`` when fully clear, so an export can
        reproduce a ``bg_colour`` or transparent render. Both the §3 ``layout(grid, style)``
        form and the ``layout(grid, palette, style)`` form the other glyph renderers use are
        accepted; the palette only feeds the palette modes.
        """
        palette, style = _layout_arguments(palette, style)
        options = _read_options(style)
        indices = _ramp_indices(grid.luma, len(options.ramp), options.offset, options.invert)
        ink, paper = _cell_colours(options, grid, palette)
        placed: list[GlyphPlacement] = []
        for row in range(grid.rows):
            for col in range(grid.cols):
                placed.append(GlyphPlacement(
                    options.ramp[int(indices[row, col])],
                    float(col * grid.cell_w), float(row * grid.cell_h),
                    float(grid.cell_w), float(grid.cell_h),
                    _hex(ink[row, col]), _hex(paper[row, col]),
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


def _read_options(style: RenderStyle) -> GlyphRampOptions:
    """Validate style.options and return the typed options of one glyph_ramp render.

    Unknown keys are ignored, so a preset written by a newer app still renders (§6).
    """
    raw = dict(style.options)
    ramp = raw.get("ramp", DEFAULT_RAMP)
    if not isinstance(ramp, str) or not ramp:
        raise ValueError(f"glyph_ramp ramp must be a non-empty string, got {ramp!r}")
    mode = raw.get("mode", "mono")
    if mode not in MODES:
        raise ValueError(f"glyph_ramp mode must be one of {MODES}, got {mode!r}")
    font = raw.get("font")
    if font is not None and not isinstance(font, str):
        raise ValueError(f"glyph_ramp font must be a path string or null, got {font!r}")
    _font_key(font)  # ValueError naming the path, before anything is drawn or laid out
    offset = raw.get("offset", 0.0)
    if isinstance(offset, bool) or not isinstance(offset, (int, float)):
        raise ValueError(f"glyph_ramp offset must be a number, got {offset!r}")
    if not math.isfinite(float(offset)):
        raise ValueError(f"glyph_ramp offset must be finite, got {offset!r}")
    invert = raw.get("invert", False)
    if not isinstance(invert, bool):
        raise ValueError(f"glyph_ramp invert must be a boolean, got {invert!r}")
    return GlyphRampOptions(
        ramp=ramp,
        font=font,
        fg=_colour_option(raw, "fg", DEFAULT_FG),
        bg=_colour_option(raw, "bg", DEFAULT_BG),
        mode=mode,
        offset=float(offset),
        invert=invert,
    )


def _colour_option(raw: dict, key: str, default: str) -> str:
    """Return one colour option as text, validating it before any drawing happens."""
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"glyph_ramp {key} must be a colour string, got {value!r}")
    _parse_colour(value)
    return value


def _parse_colour(value: str) -> tuple[float, float, float, float]:
    """Parse "#rrggbb", "#rrggbbaa" or "transparent" into RGBA floats in [0, 1]."""
    text = str(value).strip().lower()
    if text == TRANSPARENT:
        return (0.0, 0.0, 0.0, 0.0)
    digits = text.lstrip("#")
    if len(digits) not in (6, 8) or not _HEX_DIGITS.issuperset(digits):
        raise ValueError(
            f"glyph_ramp colour must be #rrggbb, #rrggbbaa or 'transparent', got {value!r}"
        )
    red, green, blue = (int(digits[at : at + 2], 16) / 255.0 for at in (0, 2, 4))
    alpha = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
    return (red, green, blue, alpha)


def _hex(rgba: np.ndarray) -> str:
    """Format one RGBA float row as "#rrggbb", "#rrggbbaa" or "transparent"."""
    alpha = int(round(float(rgba[3]) * 255.0))
    if alpha <= 0:
        return TRANSPARENT
    red, green, blue = (int(round(float(value) * 255.0)) for value in rgba[:3])
    if alpha >= 255:
        return f"#{red:02x}{green:02x}{blue:02x}"
    return f"#{red:02x}{green:02x}{blue:02x}{alpha:02x}"


def _font_key(path: str | None) -> tuple[str | None, int, int]:
    """Return the cache key of a font: its path plus the file's mtime and size.

    The mtime and size make a font replaced at the same path a different key, so a cached
    mask can never outlive the file it was drawn from (§3 invariant 2). A path that is not
    an existing file raises ValueError naming it, before anything is drawn or laid out.
    """
    if path is None:
        return (None, 0, 0)
    target = Path(path)
    if not target.is_file():
        raise ValueError(f"glyph_ramp font file not found: {path}")
    info = target.stat()
    return (path, info.st_mtime_ns, info.st_size)


def _load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Load the font at path at size, or Pillow's bundled default when path is None."""
    if path is None:
        return ImageFont.load_default(size=size)
    try:
        return ImageFont.truetype(path, size)
    except OSError as exc:
        raise ValueError(f"glyph_ramp font file is not a usable font: {path}") from exc


@lru_cache(maxsize=_MASK_CACHE_SIZE)
def _metrics(font_key: tuple[str | None, int, int]) -> tuple[float, float]:
    """Return the (line height, advance width) per point of the font, cached per font."""
    font = _load_font(font_key[0], _PROBE_SIZE)
    ascent, descent = font.getmetrics()
    return ((ascent + descent) / _PROBE_SIZE, float(font.getlength("M")) / _PROBE_SIZE)


def _font_size(cell_w: int, cell_h: int, path: str | None) -> int:
    """Return the point size whose advance and line height both fit one cell."""
    height_ratio, advance_ratio = _metrics(_font_key(path))
    by_height = cell_h / height_ratio if height_ratio > 0.0 else float(cell_h)
    by_width = cell_w / advance_ratio if advance_ratio > 0.0 else float(cell_w)
    return max(1, int(round(min(by_height, by_width))))


def _glyph_mask(char: str, path: str | None, cell_w: int, cell_h: int) -> np.ndarray:
    """Return the read-only (cell_h, cell_w) float32 ink mask of one centred glyph."""
    return _cached_mask(_font_key(path), char, cell_w, cell_h)


@lru_cache(maxsize=_MASK_CACHE_SIZE)
def _cached_mask(
    font_key: tuple[str | None, int, int], char: str, cell_w: int, cell_h: int
) -> np.ndarray:
    """Return the read-only ink mask of one glyph, cached per font identity and cell.

    Every input is part of the key, the cache is bounded, and the returned array is not
    writable, so no caller can observe or cause a change of the rendered output.
    """
    font = _load_font(font_key[0], _font_size(cell_w, cell_h, font_key[0]))
    canvas = PILImage.new("L", (cell_w, cell_h), 0)
    ImageDraw.Draw(canvas).text(
        (cell_w / 2.0, cell_h / 2.0), char, font=font, fill=255, anchor="mm"
    )
    mask = np.asarray(canvas, dtype=np.float32) / 255.0
    mask.setflags(write=False)
    return mask


def _ramp_indices(luma: np.ndarray, count: int, offset: float, invert: bool) -> np.ndarray:
    """Return the ramp index of every cell: darkest first, shifted by offset, inverted.

    ``luma`` is linear light (S2) and indexes the ramp through its sRGB-perceptual encoding
    (AMD-010): the re-encoding is monotonic, so darkest-first order is preserved and the
    ordered ramp stays perceptually spaced — a black-to-white source gradient walks the whole
    ramp instead of collapsing into its dark third. One unit of ``offset`` moves one glyph.
    """
    position = color.linear_to_srgb(np.asarray(luma, dtype=np.float32))
    scaled = (position + np.float32(offset)) * np.float32(count)
    index = np.clip(np.floor(scaled + np.float32(_EPSILON)).astype(np.intp), 0, count - 1)
    return (count - 1 - index) if invert else index


def _palette_colours(grid: CellGrid, palette: Palette) -> np.ndarray:
    """Return the (rows, cols, 4) opaque palette colour of every cell."""
    rgb = np.asarray(palette, dtype=np.float32)[np.asarray(grid.index, dtype=np.intp), :3]
    alpha = np.ones(rgb.shape[:2] + (1,), dtype=np.float32)
    return np.concatenate([rgb, alpha], axis=-1)


def _darkest(palette: Palette) -> np.ndarray:
    """Return the RGBA colour of the palette entry with the lowest linear luminance."""
    linear = color.srgb_to_linear(np.asarray(palette, dtype=np.float32)[:, :3])
    luma = np.float32(0.2126) * linear[:, 0] + np.float32(0.7152) * linear[:, 1]
    luma = luma + np.float32(0.0722) * linear[:, 2]
    row = np.asarray(palette, dtype=np.float32)[int(np.argmin(luma)), :3]
    return np.concatenate([row, np.ones(1, dtype=np.float32)])


def _cell_colours(
    options: GlyphRampOptions, grid: CellGrid, palette: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    """Return the (rows, cols, 4) ink and paper colours of every cell for the chosen mode.

    ``mono`` uses fg on bg; ``fg_colour`` puts the cell palette colour in the ink and bg in
    the paper; ``bg_colour`` the reverse; ``palette`` takes the ink from the cell and the
    paper from the palette's darkest entry, so both come from the palette.
    """
    shape = (grid.rows, grid.cols, 4)
    ink = np.broadcast_to(np.asarray(_parse_colour(options.fg), np.float32), shape).copy()
    paper = np.broadcast_to(np.asarray(_parse_colour(options.bg), np.float32), shape).copy()
    if options.mode == "mono" or palette is None:
        return ink, paper
    cells = _palette_colours(grid, palette)
    if options.mode == "fg_colour":
        return cells, paper
    if options.mode == "bg_colour":
        return ink, cells
    return cells, np.broadcast_to(_darkest(palette), shape).copy()


def _blend(paper: np.ndarray, ink: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Composite glyph ink over paper with straight alpha; mask is (cell_h, cell_w)."""
    weight = mask[None, :, :, None]
    ink_weight = ink[:, None, None, 3:4] * weight
    paper_weight = paper[:, None, None, 3:4] * (1.0 - weight)
    alpha = ink_weight + paper_weight
    rgb = ink[:, None, None, :3] * ink_weight + paper[:, None, None, :3] * paper_weight
    return np.concatenate([rgb / np.maximum(alpha, np.float32(_EPSILON)), alpha], axis=-1)


def _groups(indices: np.ndarray, count: int) -> list[np.ndarray]:
    """Return, per ramp value, the flat cell positions that carry it (one stable sort)."""
    flat = np.asarray(indices, dtype=np.intp).ravel()
    order = np.argsort(flat, kind="stable")
    bounds = np.searchsorted(flat[order], np.arange(count + 1))
    return [order[bounds[value] : bounds[value + 1]] for value in range(count)]


def _frame(grid: CellGrid, palette: Palette, options: GlyphRampOptions) -> np.ndarray:
    """Return the (rows*cell_h, cols*cell_w, C) float32 frame of one glyph_ramp render."""
    count = len(options.ramp)
    indices = _ramp_indices(grid.luma, count, options.offset, options.invert)
    ink, paper = _cell_colours(options, grid, palette)
    alpha = bool(ink[:, :, 3].min() < 1.0 or paper[:, :, 3].min() < 1.0)
    frame = np.empty((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 4), dtype=np.float32)
    view = frame.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w, 4)
    view[...] = paper[:, None, :, None, :]
    for value, cells in enumerate(_groups(indices, count)):
        if cells.size == 0:
            continue
        rows, cols = np.divmod(cells, grid.cols)
        mask = _glyph_mask(options.ramp[value], options.font, grid.cell_w, grid.cell_h)
        view[rows, :, cols, :, :] = _blend(paper[rows, cols], ink[rows, cols], mask)
    if alpha:
        return frame
    return np.ascontiguousarray(frame[:, :, :3])


def register_glyph_ramp_renderer() -> CellRenderer:
    """Register the GlyphRampRenderer under "glyph_ramp" and return it."""
    return register_renderer(GlyphRampRenderer())


register_glyph_ramp_renderer()
