"""The text renderer: a flowing paragraph modulated by luma (§10).

Glyphs use the font's advances, pair kerning and line distance, wrapped word by word; an
overlong word is cut character by character. Luma (S2, sRGB per AMD-010) drives each glyph's
size, stroke and opacity. Wrapping and fit use the real rasterised ink box — the blit's own
source of truth — so no ink leaves the canvas; a too-tall paragraph re-flows smaller. Caches
are bounded and input-keyed (§3, H11).
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
NAME, CELL_ASPECT = "text", 0.5
DEFAULT_TEXT = "Lattice renders a paragraph in a real font, one glyph at a time."
DEFAULT_FG, DEFAULT_BG = "#000000", "#ffffff"
SIZE_MODES = WEIGHT_MODES = ("fixed", "variable")
MIN_FACTOR, MAX_FACTOR, MIN_OPACITY, MAX_SIZE, JITTER = 0.5, 1.5, 0.12, 512, 0.08
_PROBE_SIZE, _FIT_PASSES, _CACHE = 100, 8, 1024
_EPSILON, _HEX_DIGITS = 1e-6, frozenset("0123456789abcdef")
_EMPTY_MASK = np.zeros((1, 1), np.float32)  # read-only: an inkless glyph's mask
_EMPTY_MASK.setflags(write=False)


@dataclass(frozen=True)
class TextOptions:
    """Validated options of one render (§10); fixed size forces fixed weight (opacity only)."""

    text: str = DEFAULT_TEXT
    font: str | None = None
    size: int | None = None
    line_distance: float = 1.2
    kerning: float = 1.0
    size_mode: str = "variable"
    weight_mode: str = "variable"  # ignored when size_mode="fixed" (§10: opacity only)
    fg: str = DEFAULT_FG
    bg: str = DEFAULT_BG
    seed: int = 0  # deterministic jitter; §10 omits the option but reproducibility needs it


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
        opt = _read_options(style)
        fg, key = _parse_colour(opt.fg), _font_key(opt.font)
        shape = (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
        frame = np.full(shape, _parse_colour(opt.bg), np.float32)
        for glyph in _Paragraph(grid, opt).glyphs():
            _blit(frame, glyph, fg, key)
        return np.ascontiguousarray(frame, dtype=np.float32)

    def layout(
        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
    ) -> list[TextGlyph]:
        """Return every laid-out glyph at its real position (both §3 call forms accepted)."""
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
    _font_key(font)  # a missing path raises naming it; an unreadable font is rejected in _font()
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
        fg=cast(str, fg), bg=cast(str, bg), seed=seed)


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


@lru_cache(maxsize=_CACHE)
def _ink_box(font_key: _FontKey, char: str, size: int, stroke: int) -> tuple[int, ...]:
    """Return the glyph's real rasterised ink box (x0, y0, x1, y1), stroke included (§10)."""
    mask, left, top = _mask(font_key, char, size, stroke)
    cols, rows = np.flatnonzero(mask.any(axis=0)), np.flatnonzero(mask.any(axis=1))
    if not len(cols) or not len(rows):
        return (0, 0, 0, 0)
    return (left + cols[0], top + rows[0], left + cols[-1] + 1, top + rows[-1] + 1)


class _Paragraph:
    """One paragraph laid out over a fixed canvas: modulation, wrapping and fit."""

    def __init__(self, grid: CellGrid, options: TextOptions) -> None:
        """Measure the canvas, the font and the nominal point size of the paragraph."""
        if np.shape(grid.luma) != (grid.rows, grid.cols):
            raise ValueError(
                f"text renderer needs grid.luma of shape {(grid.rows, grid.cols)}, "
                f"got {np.shape(grid.luma)}")
        self.grid = grid
        self.options = options
        self.width, self.height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
        self.chars = list(" ".join(options.text.split()))
        self.font_key = _font_key(options.font)
        ratio = sum(_font(self.font_key, _PROBE_SIZE).getmetrics()) / float(_PROBE_SIZE)
        nominal = int(round(grid.cell_h / ratio)) if ratio > 0.0 else grid.cell_h
        self.base = max(1, min(options.size or nominal, max(self.width, self.height)))
        self.count = len(self.chars)
        self.factors = np.ones(self.count, dtype=np.float32)
        self.inks = np.zeros(self.count, dtype=np.float32)

    def glyphs(self) -> list[TextGlyph]:
        """Lay the paragraph out and return every glyph at its real, unclamped position."""
        if not self.chars or self.width <= 0 or self.height <= 0:
            return []
        self._modulate()
        placed, dx, dy = self._fit()
        return self._place(placed, dx, dy)

    def _modulate(self) -> None:
        """Fill each character's ink and size factor from the cells under the nominal layout."""
        key = self.font_key
        jitter = np.random.default_rng(self.options.seed).uniform(-JITTER, JITTER, self.count)
        table = np.ascontiguousarray(1.0 - color.linear_to_srgb(self.grid.luma), np.float32)
        for glyph in self._flow([self.base] * self.count):
            advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
            x = glyph.pen + 0.5 * advance
            y = glyph.baseline - 0.5 * _font(key, glyph.size).getmetrics()[0]
            col = min(self.grid.cols - 1, max(0, int(x // self.grid.cell_w)))
            row = min(self.grid.rows - 1, max(0, int(y // self.grid.cell_h)))
            ink = float(table[row, col])
            self.inks[glyph.slot] = ink
            if self.options.size_mode == "variable":
                self.factors[glyph.slot] = np.clip(
                    MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR)

    def _stroke(self, slot: int, size: int) -> int:
        """Return one glyph's §10 stroke from its ink and size (fixed mode never strokes)."""
        if self.options.size_mode == "fixed" or self.options.weight_mode == "fixed":
            return 0
        return int(round(self.inks[slot] * max(1, size // 8)))

    def _flow(self, sizes: list[int]) -> list[_Placed]:
        """Lay characters out word by word, cutting any word too long for an empty line."""
        key, opt, chars = self.font_key, self.options, self.chars
        asc, desc = _font(key, max(sizes) if sizes else self.base).getmetrics()
        lead = opt.line_distance * float(asc + desc)
        space = _glyph_metrics(key, self.base, " ")[0]
        placed: list[_Placed] = []
        pen, line, idx = 0.0, 0, 0
        while idx < len(chars):
            stop = idx
            while stop < len(chars) and chars[stop] != " ":
                stop += 1
            if stop == idx:  # a separator: nothing to draw
                idx += 1
                continue
            runs, begin, used = [], idx, 0.0
            for o in range(idx, stop):  # a word too long for one line is cut here
                box = _ink_box(key, chars[o], sizes[o], self._stroke(o, sizes[o]))
                step = max(_glyph_metrics(key, sizes[o], chars[o])[0], box[2] - box[0])
                if used + step + 1.0 > self.width and o > begin:
                    runs.append((begin, o))
                    begin, used = o, 0.0
                used += step
            runs.append((begin, stop))
            for begin, end in runs:
                word, cursor = [], 0.0
                left = right = 0.0
                for o in range(begin, end):
                    word.append((o, chars[o], cursor))
                    box = _ink_box(key, chars[o], sizes[o], self._stroke(o, sizes[o]))
                    left, right = min(left, cursor + box[0]), max(right, cursor + box[2])
                    cursor += _glyph_metrics(key, sizes[o], chars[o])[0]
                    if o + 1 < end:
                        cursor += opt.kerning * _kern(key, sizes[o], chars[o], chars[o + 1])
                shift = -left if left < 0.0 else 0.0
                if pen > 0.0 and pen + shift + max(cursor, right) + 1.0 > self.width:
                    pen, line = 0.0, line + 1
                for o, ch, rel in word:
                    placed.append(_Placed(ch, pen + shift + rel, asc + line * lead, sizes[o], o))
                pen += cursor + space
            idx = stop + 1
        return placed

    def _fit(self) -> tuple[list[_Placed], float, float]:
        """Return placed glyphs and the shift that brings their real ink inside the canvas."""
        placed: list[_Placed] = []
        dx = dy = 0.0
        key = self.font_key
        for _ in range(_FIT_PASSES):
            if self.options.size_mode == "fixed":
                sizes = [self.base] * self.count
            else:
                sizes = [max(1, int(round(self.base * float(f)))) for f in self.factors]
            placed = self._flow(sizes)
            left = top = math.inf
            right = bottom = -math.inf
            for glyph in placed:
                stroke = self._stroke(glyph.slot, glyph.size)
                box = _ink_box(key, glyph.character, glyph.size, stroke)
                left, right = min(left, glyph.pen + box[0]), max(right, glyph.pen + box[2])
                top = min(top, glyph.baseline + box[1])
                bottom = max(bottom, glyph.baseline + box[3])
            if left is math.inf:
                left = right = top = bottom = 0.0
            dx, dy = max(0.0, -left), max(0.0, -top)
            if right + dx <= self.width and bottom + dy <= self.height:
                break
            scale = min(self.width / max(right + dx, _EPSILON),
                        self.height / max(bottom + dy, _EPSILON)) * 0.98
            nxt = max(1, min(self.base - 1, int(self.base * scale)))
            if nxt == self.base:
                break
            self.base = nxt
        return placed, dx, dy

    def _place(self, placed: list[_Placed], dx: float, dy: float) -> list[TextGlyph]:
        """Return glyphs at their real positions with size, stroke and opacity (§10)."""
        out: list[TextGlyph] = []
        opt, key = self.options, self.font_key
        for glyph in placed:
            asc, desc = _font(key, glyph.size).getmetrics()
            box_w = _glyph_metrics(key, glyph.size, glyph.character)[0]
            x, y = glyph.pen + dx, glyph.baseline + dy - asc
            ink = float(self.inks[glyph.slot])
            out.append(TextGlyph(
                glyph.character, x, y, box_w, float(asc + desc), opt.fg.lower(), opt.bg.lower(),
                glyph.size, self._stroke(glyph.slot, glyph.size),
                MIN_OPACITY + (1.0 - MIN_OPACITY) * ink))
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
        (-left, -top), char, font=font, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
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
