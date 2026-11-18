"""The text renderer: a flowing paragraph in a real font, modulated by luma (§10).

Glyphs are laid out with the font's own advances, pair kerning and line distance, wrapped
word by word to the canvas width, so the output reads as a paragraph and not a grid. The
linear luma of the cell under a glyph (S2, re-encoded to sRGB per AMD-010) drives its size
(0.5x to 1.5x, §10), stroke weight and opacity, so ink never collapses on a neutral palette.
The paper paints every pixel, ink is clipped to the canvas, and an overflowing paragraph is
re-flowed smaller rather than clipped. Fonts, metrics and masks are bounded input-keyed
caches that never change the output (§3 invariant 2, H11); randomness is a seed-keyed jitter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple, cast

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from lattice_core import color
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
from lattice_core.renderers.glyph_ramp import _font_key, _layout_arguments
from lattice_core.types import Palette

_FontKey = tuple[str | None, int, int]
_Metrics = tuple[float, float, float, float, float]
NAME = "text"
CELL_ASPECT = 0.5
DEFAULT_TEXT = "Lattice renders a paragraph in a real font, one glyph at a time."
DEFAULT_FG = "#000000"
DEFAULT_BG = "#ffffff"
SIZE_MODES = ("fixed", "variable")
WEIGHT_MODES = ("fixed", "variable")
MIN_FACTOR, MAX_FACTOR = 0.5, 1.5
MIN_OPACITY = 0.12
MAX_SIZE, JITTER = 512, 0.08
_PROBE_SIZE, _FIT_PASSES, _CACHE = 100, 8, 1024
_EPSILON = 1e-6
_HEX_DIGITS = frozenset("0123456789abcdef")
_EMPTY_MASK = np.zeros((1, 1), np.float32)  # read-only: an inkless glyph's mask
_EMPTY_MASK.setflags(write=False)


@dataclass(frozen=True)
class TextOptions:
    """Validated options of one text render (§10)."""

    text: str = DEFAULT_TEXT
    font: str | None = None
    size: int | None = None
    line_distance: float = 1.2
    kerning: float = 1.0
    size_mode: str = "variable"
    weight_mode: str = "variable"
    fg: str = DEFAULT_FG
    bg: str = DEFAULT_BG
    seed: int = 0


class TextGlyph(NamedTuple):
    """One placed glyph: §3's layout fields plus its point size, stroke width and opacity."""

    character: str
    x: float
    y: float
    width: float
    height: float
    fill: str
    paper: str
    size: int
    stroke: int
    opacity: float


class _Placed(NamedTuple):
    """One glyph at its pen and baseline, before modulation becomes a placed box."""

    character: str
    pen: float
    baseline: float
    size: int
    slot: int


class TextRenderer:
    """Draw a flowing paragraph whose every glyph is sized, weighted and faded by luma."""

    name = NAME

    def cell_aspect(self) -> float:
        """Return 0.5: the nominal monospace cell ratio, width over height (§10)."""
        return CELL_ASPECT

    def subgrid(self) -> tuple[int, int]:
        """Return (1, 1): a glyph carries the whole cell, with no sub-points."""
        return (1, 1)

    def consumes(self) -> frozenset[str]:
        """Return {"luma"}: luma modulates the glyphs, fg/bg colour them (§10, S2)."""
        return frozenset({"luma"})

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
        """Rasterise the paragraph of grid into an image of the exact grid geometry."""
        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))

    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
        """Return the unrounded frame: ink over a fully painted paper, float32 in [0, 1]."""
        options = _read_options(style)
        fg = _parse_colour(options.fg)
        shape = (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
        frame = np.full(shape, _parse_colour(options.bg), np.float32)
        font_key = _font_key(options.font)
        for glyph in _Paragraph(grid, options).glyphs():
            _blit(frame, glyph, fg, font_key)
        return np.ascontiguousarray(frame, dtype=np.float32)

    def layout(
        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
    ) -> list[TextGlyph]:
        """Return every visible glyph inside the canvas, in reading order (§3, §11).

        Both the §3 ``layout(grid, style)`` and ``layout(grid, palette, style)`` forms are
        accepted; only fg/bg and luma change the output, never the palette.
        """
        _, style = _layout_arguments(palette, style)
        return _Paragraph(grid, _read_options(style)).glyphs()


def _read_options(style: RenderStyle) -> TextOptions:
    """Validate style.options into TextOptions; unknown keys are ignored (§6)."""
    raw = dict(style.options)
    text = raw.get("text", DEFAULT_TEXT)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"text renderer option 'text' must be a non-empty string, got {text!r}")
    font = raw.get("font")
    if font is not None and not isinstance(font, str):
        raise ValueError(f"text renderer option 'font' must be a path string or null: {font!r}")
    try:
        _font_key(font)  # ValueError naming the path, before anything is drawn
    except ValueError as exc:
        raise ValueError(f"text renderer font file not found: {font}") from exc
    size = raw.get("size")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int)
                             or not 1 <= size <= MAX_SIZE):
        raise ValueError(f"text renderer option 'size' must be in [1, {MAX_SIZE}]: {size!r}")
    line_distance = _number(raw, "line_distance", 1.2)
    if line_distance <= 0.0:
        raise ValueError(f"text renderer 'line_distance' must be positive: {line_distance!r}")
    kerning = _number(raw, "kerning", 1.0)
    if not 0.0 <= kerning <= 2.0:
        raise ValueError(f"text renderer 'kerning' must be in [0, 2]: {kerning!r}")
    seed = raw.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"text renderer option 'seed' must be a non-negative integer: {seed!r}")
    fg, bg = raw.get("fg", DEFAULT_FG), raw.get("bg", DEFAULT_BG)
    _parse_colour(fg, "fg")
    _parse_colour(bg, "bg")
    return TextOptions(
        text=text, font=font, size=size, line_distance=line_distance, kerning=kerning,
        size_mode=_choice(raw, "size_mode", "variable", SIZE_MODES),
        weight_mode=_choice(raw, "weight_mode", "variable", WEIGHT_MODES),
        fg=cast(str, fg), bg=cast(str, bg), seed=seed,
    )


def _number(raw: dict, key: str, default: float) -> float:
    """Return one finite numeric option, naming it when the value is not a number."""
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"text renderer option {key!r} must be a finite number: {value!r}")
    return float(value)


def _choice(raw: dict, key: str, default: str, allowed: tuple[str, ...]) -> str:
    """Return one enumerated option, naming it and its allowed values when unknown."""
    value = raw.get(key, default)
    if value not in allowed:
        raise ValueError(f"text renderer option {key!r} must be one of {allowed}: {value!r}")
    return str(value)


def _parse_colour(value: object, key: str = "colour") -> np.ndarray:
    """Parse one #rrggbb option into a float32 (3,) sRGB row in [0, 1], or name it."""
    digits = str(value).strip().lower().lstrip("#")
    if not isinstance(value, str) or len(digits) != 6 or not _HEX_DIGITS.issuperset(digits):
        raise ValueError(f"text renderer option {key!r} must be a #rrggbb colour: {value!r}")
    return np.asarray([int(digits[at : at + 2], 16) / 255.0 for at in (0, 2, 4)], np.float32)


@lru_cache(maxsize=_CACHE)
def _font(font_key: _FontKey, size: int) -> ImageFont.FreeTypeFont:
    """Load the font of one cache key at size, or Pillow's bundled default when pathless."""
    if font_key[0] is None:
        return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))
    try:
        return ImageFont.truetype(font_key[0], size)
    except OSError as exc:
        raise ValueError(f"text renderer font is not a usable font: {font_key[0]}") from exc


@lru_cache(maxsize=_CACHE)
def _glyph_metrics(font_key: _FontKey, size: int, char: str) -> _Metrics:
    """Return (advance, x0, y0, x1, y1) of one glyph, relative to its pen on the baseline."""
    font = _font(font_key, size)
    x0, y0, x1, y1 = font.getbbox(char, anchor="ls")
    return float(font.getlength(char)), float(x0), float(y0), float(x1), float(y1)


@lru_cache(maxsize=_CACHE)
def _kern(font_key: _FontKey, size: int, left: str, right: str) -> float:
    """Return the font's own pair kerning between two characters, in pixels."""
    font = _font(font_key, size)
    return float(font.getlength(left + right) - font.getlength(left) - font.getlength(right))


class _Paragraph:
    """One paragraph laid out over a fixed canvas: modulation, wrapping and fit."""

    def __init__(self, grid: CellGrid, options: TextOptions) -> None:
        """Measure the canvas, the font and the nominal point size of the paragraph."""
        if np.shape(grid.luma) != (grid.rows, grid.cols):
            raise ValueError(
                f"text renderer needs grid.luma of shape {(grid.rows, grid.cols)}, "
                f"got {np.shape(grid.luma)}"
            )
        self.grid = grid
        self.options = options
        self.width = grid.cols * grid.cell_w
        self.height = grid.rows * grid.cell_h
        self.chars = list(" ".join(options.text.split()))
        self.font_key = _font_key(options.font)
        ratio = sum(_font(self.font_key, _PROBE_SIZE).getmetrics()) / float(_PROBE_SIZE)
        nominal = int(round(grid.cell_h / ratio)) if ratio > 0.0 else grid.cell_h
        self.base = max(1, min(options.size or nominal, max(self.width, self.height)))
        self.count = len(self.chars)
        self.factors = np.ones(self.count, dtype=np.float32)
        self.inks = np.zeros(self.count, dtype=np.float32)

    def glyphs(self) -> list[TextGlyph]:
        """Lay the paragraph out and return every visible glyph, clamped to the canvas."""
        if not self.chars or self.width <= 0 or self.height <= 0:
            return []
        self._modulate()
        placed, dx, dy = self._fit()
        return self._place(placed, dx, dy)

    def _modulate(self) -> None:
        """Fill each character's ink and size factor from the cells under the nominal layout."""
        options, key = self.options, self.font_key
        jitter = np.random.default_rng(options.seed).uniform(-JITTER, JITTER, self.count)
        table = np.ascontiguousarray(1.0 - color.linear_to_srgb(self.grid.luma), np.float32)
        for glyph in self._flow([self.base] * self.count):
            advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
            x = glyph.pen + 0.5 * advance
            y = glyph.baseline - 0.5 * _font(key, glyph.size).getmetrics()[0]
            col = min(self.grid.cols - 1, max(0, int(x // self.grid.cell_w)))
            row = min(self.grid.rows - 1, max(0, int(y // self.grid.cell_h)))
            ink = float(table[row, col])
            self.inks[glyph.slot] = ink
            if options.size_mode == "variable":
                self.factors[glyph.slot] = np.clip(
                    MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR
                )

    def _flow(self, sizes: list[int]) -> list[_Placed]:
        """Lay the characters out word by word and wrap each line at the canvas width."""
        key, options, chars = self.font_key, self.options, self.chars
        lead_size = max(sizes) if sizes else self.base
        ascent, descent = _font(key, lead_size).getmetrics()
        lead = options.line_distance * float(ascent + descent)
        placed: list[_Placed] = []
        pen, line, index = 0.0, 0, 0
        while index < len(chars):
            stop = index
            while stop < len(chars) and chars[stop] != " ":
                stop += 1
            if stop == index:  # a separator: nothing to draw, its advance is added below
                index += 1
                continue
            word: list[tuple[int, str, float]] = []
            cursor = right = left = 0.0
            for offset in range(index, stop):
                step, x0, _, x1, _ = _glyph_metrics(key, sizes[offset], chars[offset])
                word.append((offset, chars[offset], cursor))
                left = min(left, cursor + x0)
                right = max(right, cursor + x1)
                cursor += step
                if offset + 1 < stop:
                    cursor += options.kerning * _kern(
                        key, sizes[offset], chars[offset], chars[offset + 1]
                    )
            if pen > 0.0 and pen + max(cursor, right) + 1.0 > self.width:
                pen, line = 0.0, line + 1
            shift = -left if left < 0.0 else 0.0
            for offset, char, relative in word:
                placed.append(_Placed(char, pen + shift + relative, ascent + line * lead,
                                      sizes[offset], offset))
            pen += cursor + _glyph_metrics(key, self.base, " ")[0]
            index = stop + 1
        return placed

    def _fit(self) -> tuple[list[_Placed], float, float]:
        """Return the placed glyphs and the shift that brings their ink inside the canvas."""
        placed: list[_Placed] = []
        dx = dy = 0.0
        for _ in range(_FIT_PASSES):
            if self.options.size_mode == "fixed":
                sizes = [self.base] * self.count
            else:
                sizes = [max(1, int(round(self.base * float(f)))) for f in self.factors]
            placed = self._flow(sizes)
            left = top = math.inf
            right = bottom = -math.inf
            for glyph in placed:
                x0, y0, x1, y1 = _glyph_metrics(self.font_key, glyph.size, glyph.character)[1:]
                left = min(left, glyph.pen + x0)
                right = max(right, glyph.pen + x1)
                top = min(top, glyph.baseline + y0)
                bottom = max(bottom, glyph.baseline + y1)
            if left is math.inf:
                left = right = top = bottom = 0.0
            dx, dy = max(0.0, -left), max(0.0, -top)
            if right + dx + 1.0 <= self.width and bottom + dy + 1.0 <= self.height:
                break
            scale = min(self.width / max(right + dx, _EPSILON),
                        self.height / max(bottom + dy, _EPSILON)) * 0.98
            nxt = max(1, min(self.base - 1, int(self.base * scale)))
            if nxt == self.base:
                break
            self.base = nxt
        return placed, dx, dy

    def _place(self, placed: list[_Placed], dx: float, dy: float) -> list[TextGlyph]:
        """Return the glyphs as boxes clamped inside the canvas, with size, stroke, opacity."""
        out: list[TextGlyph] = []
        options, key = self.options, self.font_key
        weight_mode = options.weight_mode if options.size_mode == "variable" else "fixed"
        for glyph in placed:
            advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
            ascent, descent = _font(key, glyph.size).getmetrics()
            box_w = min(advance, float(self.width))
            box_h = min(float(ascent + descent), float(self.height))
            x = min(max(glyph.pen + dx, 0.0), max(0.0, self.width - box_w))
            y = min(max(glyph.baseline + dy - ascent, 0.0), max(0.0, self.height - box_h))
            ink = float(self.inks[glyph.slot])
            stroke = 0 if weight_mode == "fixed" else int(round(ink * max(1, glyph.size // 8)))
            out.append(TextGlyph(
                glyph.character, x, y, box_w, box_h, options.fg.lower(), options.bg.lower(),
                glyph.size, stroke, MIN_OPACITY + (1.0 - MIN_OPACITY) * ink,
            ))
        return out


@lru_cache(maxsize=_CACHE)
def _mask(font_key: _FontKey, char: str, size: int, stroke: int) -> tuple[np.ndarray, int, int]:
    """Return the read-only ink mask of one glyph and the offset of its patch's origin."""
    font = _font(font_key, size)
    x0, y0, x1, y1 = font.getbbox(char, anchor="ls")
    pad = stroke + 1
    left, top = math.floor(x0) - pad, math.floor(y0) - pad
    right, bottom = math.ceil(x1) + pad, math.ceil(y1) + pad
    if right <= left or bottom <= top:
        return _EMPTY_MASK, 0, 0
    canvas = PILImage.new("L", (right - left, bottom - top), 0)
    ImageDraw.Draw(canvas).text(
        (-left, -top), char, font=font, fill=255, anchor="ls",
        stroke_width=stroke, stroke_fill=255,
    )
    mask = np.asarray(canvas, np.float32) / 255.0
    mask.setflags(write=False)
    return mask, left, top


def _blit(frame: np.ndarray, glyph: TextGlyph, fg: np.ndarray, font_key: _FontKey) -> None:
    """Composite one glyph's ink into frame with its opacity, clipped to the canvas."""
    if glyph.opacity <= 0.0:
        return
    mask, offset_x, offset_y = _mask(font_key, glyph.character, glyph.size, glyph.stroke)
    if mask.size <= 1 and not mask.any():
        return
    x = int(round(glyph.x)) + offset_x
    y = int(round(glyph.y + _font(font_key, glyph.size).getmetrics()[0])) + offset_y
    x0, y0 = max(0, -x), max(0, -y)
    x1, y1 = min(mask.shape[1], frame.shape[1] - x), min(mask.shape[0], frame.shape[0] - y)
    if x0 >= x1 or y0 >= y1:
        return
    alpha = (mask[y0:y1, x0:x1] * glyph.opacity)[..., None]
    region = frame[y + y0 : y + y1, x + x0 : x + x1]
    region[:] = region * (1.0 - alpha) + fg * alpha


def register_text_renderer() -> CellRenderer:
    """Register the TextRenderer under "text" and return it."""
    return register_renderer(TextRenderer())


register_text_renderer()
