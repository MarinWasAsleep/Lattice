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

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
{{SIGNATURES}}

TASK CARD
{{TASK_CARD}}

CURRENT CONTENT OF YOUR FILES (stubs on first attempt)
{{OWNED_FILES}}

{{RETRY_BLOCK}}
<!-- RETRY_BLOCK, only on retries:
RETRY attempt {{N}}. Fix exactly what is reported below, change nothing else, keep passing tests passing.
{{GATE_LOG_OR_REVIEW_FINDINGS}}
-->



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


PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
# --- lattice_core/color ---
  def to_float(img: PILImage.Image) -> Image:
      """Convert any Pillow image to float32 RGB in [0, 1], compositing alpha over white."""
  def to_rgb8(img: Image) -> RGB8:
      """Convert a float32 image in [0, 1] to uint8, rounding half up and clipping."""
  def to_pil(rgb8: RGB8) -> PILImage.Image:
      """Wrap a uint8 RGB array in a Pillow image."""
  def luminance(img: Image) -> np.ndarray:
      """Return the sRGB luminance of every pixel as a float32 (H, W) array."""
  def nearest_index(img: Image, palette: Palette, metric: str = "srgb") -> Indices:
      """Return the index of the closest palette colour for every pixel, under metric."""
  def metric_code(metric: str | int) -> int:
      """Return the kernel code of a colour metric name, or pass an int code through."""
  def to_working_space(img: Image, metric: str | int) -> Image:
      """Convert an sRGB image or palette to the space the metric compares in."""
  def srgb_to_oklab(img: Image) -> Image:
      """Convert sRGB values in [0, 1] to Oklab (Ottosson's matrices, no axis scaling)."""
  def srgb_to_lab(img: Image) -> Image:
      """Convert sRGB values in [0, 1] to CIELAB under the D65 white point."""
  def apply_palette(idx: Indices, palette: Palette) -> Image:
      """Map palette indices back to float32 colours."""
  def adjust(
  def srgb_to_linear(img: Image) -> Image:
      """Decode sRGB-encoded values in [0, 1] to linear light with the exact transfer function."""
  def linear_to_srgb(img: Image) -> Image:
      """Encode linear-light values in [0, 1] back to sRGB with the exact transfer function."""
  def auto_levels(img: Image, low: float = 0.5, high: float = 99.5) -> Image:
      """Stretch each channel between its low and high percentiles, clipping to [0, 1]."""
  def gaussian_blur(img: Image, sigma: float) -> Image:
      """Blur img with a separable Gaussian of the given sigma; sigma <= 0 is a no-op."""
  def downscale(img: Image, factor: int) -> Image:
      """Average factor x factor blocks, replicating the edge when the size is not divisible."""
  def upscale_nearest(img: Image, factor: int, shape: tuple[int, int]) -> Image:
      """Repeat every pixel factor times, then crop to shape."""
  def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray, metric: int = 0) -> int:
      """Return the index of the palette colour closest to (r, g, b); numba kernel.
# --- lattice_core/cell ---
  class CellGrid:
      """One quantised image expressed as a grid of cells for a CellRenderer."""
  class RenderStyle:
      """Renderer-specific options, JSON-serialisable."""
  class CellRenderer(Protocol):
      """How a quantised CellGrid is drawn; the pipeline decides which palette entry.
      def cell_aspect(self) -> float:
      """Return width / height of one cell."""
      def subgrid(self) -> tuple[int, int]:
      """Return the (sx, sy) sub-point grid; (1, 1) means no sub-points."""
      def consumes(self) -> frozenset[str]:
      """Return the subset of {"index", "luma", "samples", "coverage",
      def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
      """Draw grid with palette and style into a Pillow image."""
  class FloatFrameRenderer(Protocol):
      """Optional capability: hand the pipeline a float32 frame instead of a Pillow image."""
      def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
      """Return the same frame as render, as float32 (rows*cell_h, cols*cell_w, 3) in [0, 1]."""
  def register_renderer(renderer: CellRenderer) -> CellRenderer:
      """Register renderer under its name, raising ValueError on a duplicate name."""
  def get_renderer(name: str) -> CellRenderer:
      """Return the renderer registered under name, or raise KeyError naming it."""
  def list_renderers() -> list[str]:
      """Return every registered renderer name, sorted."""
# --- lattice_core/renderers/glyph_ramp ---
  class GlyphRampOptions:
      """Validated options of one glyph_ramp render (§9); there is no size option (H11)."""
  class GlyphPlacement(NamedTuple):
      """One placed glyph: §3's six fields, plus the paper colour the cell was drawn on."""
  class GlyphRampRenderer:
      """Draw one monospace character per cell; the H12 modes tie ink and glyph to the cell."""
      def cell_aspect(self) -> float:
      """Return 0.5: the default monospace font ratio, width over height (§9)."""
      def subgrid(self) -> tuple[int, int]:
      """Return (1, 1): one glyph covers the whole cell, with no sub-points."""
      def consumes(self) -> frozenset[str]:
      """Return {"luma", "index"}: luma picks the glyph, index the palette colour."""
      def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
      """Rasterise the glyph ramp of grid into an image of the exact grid geometry."""
      def layout(
  def register_glyph_ramp_renderer() -> CellRenderer:
      """Register the GlyphRampRenderer under "glyph_ramp" and return it."""
# --- lattice_core/renderers/text ---
  class TextOptions:
      """Validated options of one render (§10); fixed size forces fixed weight (opacity only)."""
  class TextGlyph(NamedTuple):
      """One placed glyph: §3's layout fields plus its point size, stroke width and opacity."""
  class TextRenderer:
      """Draw a flowing paragraph whose every glyph is sized, weighted and faded by luma."""
      def cell_aspect(self) -> float:
      """Return 0.5: the nominal monospace cell ratio, width over height (§10)."""
      def subgrid(self) -> tuple[int, int]:
      """Return (1, 1): a glyph carries the whole cell, with no sub-points."""
      def consumes(self) -> frozenset[str]:
      """Return {"luma"}: luma modulates the glyphs, fg/bg colour them (§10, S2)."""
      def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
      """Rasterise the paragraph of grid into an image of the exact grid geometry."""
      def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
      """Return the unrounded frame: ink over a fully painted paper, float32 in [0, 1]."""
      def layout(
      def glyphs(self) -> list[TextGlyph]:
      """Lay the paragraph out and return every glyph at its real, unclamped position."""
  def register_text_renderer() -> CellRenderer:
      """Register the TextRenderer under "text" and return it."""

TASK CARD
### L9b · Renderer `text` : répétition du paragraphe pour remplir la toile (H12)
- wave: 2 · deps: L9 | executor: OMH capable · review: strict · size: M
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §10
- origin: décision humaine H12 du 2026-11-18 (DEV-218). Le renderer pose son paragraphe UNE fois
  (`_flow` boucle sur `while idx < len(chars)`) : mesuré 496 caractères sur 12 960 cellules
  disponibles, soit 3 % de la hauteur de la toile à `pixel_size 10`. §10 exige que les cellules
  « must still fill the output rectangle exactly ».
- spec: boucler le texte jusqu'à ce que toutes les cellules soient couvertes. Option `repeat`
  (`fill` | `once`), défaut `fill` ; `once` conserve le comportement actuel pour qui veut un
  paragraphe unique. Ne change pas la modulation par `luma`, ni la césure, ni `size_mode`.
- accept:
  - sur un paragraphe court (une phrase) et un canevas large, la fraction de cellules portant de
    l'encre dépasse 90 % en mode `fill`.
  - `repeat: once` reproduit exactement le comportement d'avant (test de non-régression).
  - le texte bouclé respecte la césure et ne produit aucun glyphe hors du canevas (les tests de L9
    restent verts).
  - la luma du rendu d'un portrait sur fond neutre passe sous 0,90 et son contraste dépasse 0,20
    (aujourd'hui : 0,995 / 0,011).


CURRENT CONTENT OF YOUR FILES (state on disk — integrate, never replace)
# === lattice_core/renderers/text.py (396 l) — état actuel sur disque ===
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


# === tests/test_text.py (398 l) — état actuel sur disque ===
"""Tests for the text renderer (§3, §10) — card L9.

Metrics are pinned against Pillow's own; renders compare across palettes (S2).
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
_WORDS = ("lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
          "canvas grid luma ink paper palette neutral source image renderer").split()
PARAGRAPH = " ".join(_WORDS[(i * 7) % len(_WORDS)] for i in range(200))
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
    options = {"text": word, "size_mode": "fixed", "size": 8}
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
    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
    assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
    assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
    assert len(_line_tops(glyphs)) >= 10
    for glyph in glyphs:  # real positions from layout(), including the stroke margin
        _assert_ink_inside(glyph, width, height)
    frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
    assert frame.shape == (height, width, 3) and frame.min() >= 0.0 and frame.max() <= 1.0


def test_layout_reports_real_unclamped_positions():
    text, kern = "unclamped", 1.0
    glyphs = _layout(_canvas(80, 4, 1, 60), text=text, size=12, kerning=kern, size_mode="fixed")
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
