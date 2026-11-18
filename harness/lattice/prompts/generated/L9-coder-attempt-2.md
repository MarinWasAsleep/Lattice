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

## §3 The CellRenderer contract

This is the architectural bet of the project. Everything else is an implementation detail.

```python
@dataclass(frozen=True)
class CellGrid:
    cols: int
    rows: int
    cell_w: int
    cell_h: int
    index: np.ndarray      # (rows, cols) int32, palette index per cell
    coverage: np.ndarray   # (rows, cols) float32 in [0, 1], ink coverage per cell
    luma: np.ndarray       # (rows, cols) float32, linear luminance of the SOURCE cell
                           # computed before quantisation (S2, decided 2026-11-16)
    samples: np.ndarray    # (rows, cols, k) float32 in [0, 1], sub-cell luminance
    subindex: np.ndarray | None = None  # (rows, cols, sx*sy) int32, palette index per
                                        # sub-point, present when subgrid != (1, 1) (S3)

@dataclass(frozen=True)
class RenderStyle:
    options: Mapping[str, object]   # renderer-specific, JSON-serialisable

class CellRenderer(Protocol):
    name: str
    def cell_aspect(self) -> float: ...
    def subgrid(self) -> tuple[int, int]: ...  # default (1, 1); braille (2, 4), sextant (2, 3) (S3)
    def consumes(self) -> frozenset[str]: ...  # subset of {"index", "luma", "samples",
                                               # "coverage", "subindex"} (H11)
    def render(self, grid: CellGrid, palette: np.ndarray, style: RenderStyle) -> Image.Image: ...
```

Registry: `register_renderer`, `get_renderer(name)`, `list_renderers()`.

Normative invariants, each one a test:

1. `render` returns an image of exactly `(cols * cell_w, rows * cell_h)` pixels.
2. `render` is pure: identical inputs produce identical output. Module-level state is restricted
   to deterministic, input-keyed caches (e.g. glyph shape vectors, §9); a cache never changes the
   output (H11, decided 2026-11-16).
3. `render` does not mutate `grid` or `palette`.
4. `cell_aspect()` returns width/height of one cell. The pipeline uses it to choose the grid so the
   output preserves the source aspect ratio.
5. `name` is unique across the registry and stable across versions.
6. `style.options` round-trips through JSON without loss.

**Why the split.** The dithering stage decides *which palette entry* each cell receives. The
renderer decides *how to draw that entry*: a solid square, a glyph whose density matches the
entry's luminance, a braille bitmask, a paragraph of text. This is what lets 33 dithering
algorithms serve three applications without being rewritten.

`coverage` is derived once, in the pipeline, not by the renderer:

```
lum(c)      = 0.2126 R + 0.7152 G + 0.0722 B, computed in linear light
coverage    = (lum(palette[index]) - lum_min) / (lum_max - lum_min)
coverage    = 0.0 where lum_max == lum_min
```

`samples` is produced by supersampling the source cell on a `k`-point stencil. `k` is a renderer
property: 1 for `pixel`, 6 for `glyph_shape`, 8 for braille, 6 for sextant, 4 for quadrant.
The stencil geometry is renderer-specific and declared by the optional `sample_points()` method
when it matters (glyph_shape: six circles at top/middle/bottom × left/right); the default is a
uniform grid of `k` points over the cell, sampled by the pipeline (H11, decided 2026-11-16).

**Luma — independent of the palette (S2, decided 2026-11-16).** `grid.luma` is the linear
luminance of the source cell (step-7 pixels, computed in linear light) taken BEFORE quantisation.
Each renderer declares what it consumes via `consumes()`; `glyph_ramp` and `glyph_shape` consume
`luma` for ink-density ramps, so a black/white palette still uses the full glyph ramp. The L2
"coverage is monotone" test stays; a new L2 test asserts "luma is continuous and independent of
the palette".

**Sub-point dithering (S3, decided 2026-11-16).** A renderer may declare `subgrid = (sx, sy)`
(braille 2×4, sextant 2×3). The pipeline then runs the chosen algorithm at resolution
`(rows·sy, cols·sx)` and hands the renderer `grid.subindex: (rows, cols, sx·sy) int32`. The
bitmask and text renderers only pack sub-points into codepoints; the single boolean `dither`
option is removed. New L2 test: sub-point coverage is monotone at the subgrid resolution.

**Float frames (H11, decided 2026-11-16).** A renderer may implement the optional
`render_frame(grid, palette, style) -> np.ndarray float32 (H, W, 3)` in [0, 1]. When available,
step 11 uses it and the pipeline passes that unrounded frame to step 12: post-effects must never
receive an 8-bit-rounded frame when the palette mapping is exact (L2 blocker, resolved). `pixel`
implements `render_frame` as `apply_palette` + per-axis repeat; `render()` remains its
rasterisation and every renderer must keep the two consistent.

**Structured output (H11, decided 2026-11-16).** Glyph renderers may implement the optional
`layout(grid, style)` returning the placed glyphs (character, x, y, width, height, fill) that
`render()` rasterises. When available, §11 export consumes solely `layout()`, so PNG, SVG and
text exports cannot diverge. Without it, a renderer renders pixels only.

## §9 Glyph renderers

Four renderers, one per mechanism.

**`glyph_ramp`** — one monospace character per cell. `luma` (S2, decided 2026-11-16) indexes an
ordered ramp, darkest first, independently of the palette: a black/white palette still uses the
full ramp. Options: `ramp` (string), `font` (path), `fg`/`bg` (colour or `transparent`),
`mode` (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset` (float, shifts the
luma-to-glyph mapping), `invert` (bool). There is no `size` option (H11, decided 2026-11-16):
the glyph font size is derived from `cell_h` (§5 step 6), so each glyph covers its cell exactly.

- The ramp contract is explicit: **darkest character first, lightest last**. A ramp that violates
  it is not detected, it is documented.
- `offset` is animatable and is the cheapest way to make a still image shimmer.
- Aspect correction uses `cell_aspect()`; the default font ratio is 1/2 (width/height).

**`glyph_shape`** — one monospace character per cell, chosen by shape rather than by density.

- For each glyph, place `k = 6` sampling circles inside the cell (top/middle/bottom × left/right).
  For each circle, sample many points and compute the fraction inside the glyph's ink. That is the
  glyph's shape vector.
- **Normalise each component by the maximum across the alphabet.** Without this every vector
  clusters in the bottom-left and every cell maps to the same few characters.
- Per cell, compute the same vector from `samples` and take the nearest neighbour.
- Shape vectors are precomputed per (font, size) and cached at module level.
- Budget: 1024×1024, 64 glyphs, under 200 ms after warm-up. If missed, a precomputed lookup table
  over quantised vectors is allowed.

**`bitmask`** — sub-cell dots. One code path, four geometries:

| Geometry | Sub-grid | Codepoints |
|---|---|---|
| `braille` | 2×4 | U+2800 + bitmask |
| `sextant` | 2×3 | U+1FB00..U+1FB3B |
| `quadrant` | 2×2 | U+2596..U+259F |
| `half_block` | 1×2 | U+2580, U+2584, U+2588 |

Threshold `samples` into on/off sub-dots. Options: `threshold` (0..1), `fg`/`bg`. The sub-dot
decision belongs to the algorithm, run at subgrid resolution (S3): there is no `dither` option
(removed; H11 coherence pass).

**`pixel`** — one solid square per cell. This is Lattice Dither's current behaviour, expressed through
the abstraction. It must reproduce the 1.0 output byte for byte.

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

cell.py: class CellGrid:
cell.py: class RenderStyle:
cell.py: class CellRenderer(Protocol):
cell.py:     def cell_aspect(self) -> float:
cell.py:     def subgrid(self) -> tuple[int, int]:
cell.py:     def consumes(self) -> frozenset[str]:
cell.py:     def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
cell.py: class FloatFrameRenderer(Protocol):
cell.py:     def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
cell.py: def register_renderer(renderer: CellRenderer) -> CellRenderer:
cell.py: def get_renderer(name: str) -> CellRenderer:
cell.py: def list_renderers() -> list[str]:
palette.py: class Palette(np.ndarray):
palette.py:     def lum_min(self) -> float:
palette.py:     def lum_max(self) -> float:
palette.py:     def order(self) -> list[int] | None:
palette.py: def from_hex_list(values: list[str]) -> Palette:
palette.py: def from_hex_text(text: str) -> Palette:
palette.py: def from_gpl(path: str | Path) -> Palette:
palette.py: def from_png(source: str | Path | PILImage.Image) -> Palette:
palette.py: def load(path: str | Path) -> Palette:
color.py: def to_float(img: PILImage.Image) -> Image:
color.py: def to_rgb8(img: Image) -> RGB8:
color.py: def to_pil(rgb8: RGB8) -> PILImage.Image:
color.py: def luminance(img: Image) -> np.ndarray:
color.py: def nearest_index(img: Image, palette: Palette, metric: str = "srgb") -> Indices:
color.py: def metric_code(metric: str | int) -> int:
color.py: def to_working_space(img: Image, metric: str | int) -> Image:
color.py: def srgb_to_oklab(img: Image) -> Image:
color.py: def srgb_to_lab(img: Image) -> Image:
color.py: def apply_palette(idx: Indices, palette: Palette) -> Image:
color.py: def adjust(
color.py: def srgb_to_linear(img: Image) -> Image:
color.py: def linear_to_srgb(img: Image) -> Image:
color.py: def auto_levels(img: Image, low: float = 0.5, high: float = 99.5) -> Image:
color.py: def gaussian_blur(img: Image, sigma: float) -> Image:
color.py: def downscale(img: Image, factor: int) -> Image:
color.py: def upscale_nearest(img: Image, factor: int, shape: tuple[int, int]) -> Image:
color.py: def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray, metric: int = 0) -> int:

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

SITUATION — attempt 1 de cette carte, mais le fichier existe déjà
`lattice_core/renderers/text.py` a été écrit par une session précédente interrompue et n'a JAMAIS été
revu ni testé : il n'existe aucun `tests/test_text.py`. Ton travail : **livrer les deux fichiers**,
c'est-à-dire reprendre, corriger si nécessaire et compléter l'implémentation, puis écrire les tests
d'accept. Le fichier n'est pas enregistré dans `renderers/__init__.py` (l'orchestrateur s'en charge,
ce n'est pas dans tes `owns`).

Deux contraintes vérifiées par l'orchestrateur sur l'état actuel, à respecter :
- le module doit continuer à s'auto-enregistrer à l'import (`register_renderer(...)` en fin de module),
  comme les autres renderers de la vague 1 ;
- le module doit rester ≤ 400 lignes par fichier et ≤ 60 lignes par fonction (règle 6 du prompt) —
  l'état actuel fait 534 lignes : découpe (helpers privés dans le même fichier, ou décorations de
  police mises en cache) sans perdre de comportement.

CURRENT CONTENT OF YOUR FILE `lattice_core/renderers/text.py`

"""The TextRenderer: a flowing paragraph in a real font, modulated by luma (§10).

Glyphs are laid out with the font's own metrics -- advances, pair kerning and line
distance -- and wrapped word by word to the output width, so the result reads as a
paragraph rather than a character grid. Each glyph is modulated by the linear luma of
the cell under it (S2), re-encoded to sRGB before use (AMD-010): the resulting ink
amount drives its size (0.5x to 1.5x, §10), its stroke weight and its opacity, so ink
never collapses on a neutral or degenerate palette. The background paints every pixel
of the output rectangle and glyph ink is clamped inside it, whatever the canvas. Fonts,
metrics, boxes and masks live in bounded input-keyed caches that never change the
output (§3 invariant 2, H11); the only randomness is a seed-keyed per-glyph jitter.
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

NAME = "text"
CELL_ASPECT = 0.5
DEFAULT_TEXT = "Lattice renders a paragraph in a real font, one glyph at a time."
DEFAULT_FG = "#000000"
DEFAULT_BG = "#ffffff"
SIZE_MODES = ("fixed", "variable")
WEIGHT_MODES = ("fixed", "variable")
MIN_FACTOR = 0.5
MAX_FACTOR = 1.5
MIN_OPACITY = 0.12
MAX_SIZE = 512
JITTER = 0.08
_PROBE_SIZE = 100
_FIT_PASSES = 8
_FONT_CACHE = 64
_METRIC_CACHE = 4096
_MASK_CACHE = 1024
_EPSILON = 1e-6
_HEX_DIGITS = frozenset("0123456789abcdef")


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
    """One placed glyph: the §3 fields, plus its point size, stroke width and opacity."""

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
    """One glyph before modulation is turned into a placed box."""

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
        return _frame(grid, _read_options(style))

    def layout(
        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
    ) -> list[TextGlyph]:
        """Return every visible glyph placed inside the canvas, in reading order (§3, §11).

        Whitespace carries no ink and is not placed. Both the §3 ``layout(grid, style)``
        form and the ``layout(grid, palette, style)`` form are accepted; the palette never
        changes the output, because ``fg``/``bg`` and ``luma`` are the whole input.
        """
        palette, style = _layout_arguments(palette, style)
        return _glyphs(grid, _read_options(style))


def _read_options(style: RenderStyle) -> TextOptions:
    """Validate style.options and return the typed options of one text render.

    Unknown keys are ignored, so a preset written by a newer app still renders (§6).
    """
    raw = dict(style.options)
    text = raw.get("text", DEFAULT_TEXT)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            f"text renderer option 'text' must be a non-empty string, got {text!r}"
        )
    font = raw.get("font")
    if font is not None and not isinstance(font, str):
        raise ValueError(
            f"text renderer option 'font' must be a path string or null, got {font!r}"
        )
    _font_identity(font)  # ValueError naming the path, before anything is drawn
    size = raw.get("size")
    if size is not None and (
        isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_SIZE
    ):
        raise ValueError(
            f"text renderer option 'size' must be an integer in [1, {MAX_SIZE}] or null, "
            f"got {size!r}"
        )
    line_distance = _number(raw, "line_distance", 1.2)
    if line_distance <= 0.0:
        raise ValueError(
            f"text renderer option 'line_distance' must be positive, got {line_distance!r}"
        )
    kerning = _number(raw, "kerning", 1.0)
    if not 0.0 <= kerning <= 2.0:
        raise ValueError(f"text renderer option 'kerning' must be in [0, 2], got {kerning!r}")
    seed = raw.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(
            f"text renderer option 'seed' must be a non-negative integer, got {seed!r}"
        )
    return TextOptions(
        text=text,
        font=font,
        size=size,
        line_distance=line_distance,
        kerning=kerning,
        size_mode=_choice(raw, "size_mode", "variable", SIZE_MODES),
        weight_mode=_choice(raw, "weight_mode", "variable", WEIGHT_MODES),
        fg=_colour_option(raw, "fg", DEFAULT_FG),
        bg=_colour_option(raw, "bg", DEFAULT_BG),
        seed=seed,
    )


def _number(raw: dict, key: str, default: float) -> float:
    """Return one finite numeric option, naming it when the value is not a number."""
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"text renderer option {key!r} must be a number, got {value!r}")
    if not math.isfinite(float(value)):
        raise ValueError(f"text renderer option {key!r} must be finite, got {value!r}")
    return float(value)


def _choice(raw: dict, key: str, default: str, allowed: tuple[str, ...]) -> str:
    """Return one enumerated option, naming it and its allowed values when unknown."""
    value = raw.get(key, default)
    if value not in allowed:
        raise ValueError(
            f"text renderer option {key!r} must be one of {allowed}, got {value!r}"
        )
    return str(value)


def _colour_option(raw: dict, key: str, default: str) -> str:
    """Return one #rrggbb option as text, validating it before any drawing happens."""
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"text renderer option {key!r} must be a colour string, got {value!r}")
    digits = value.strip().lower().lstrip("#")
    if len(digits) != 6 or not _HEX_DIGITS.issuperset(digits):
        raise ValueError(f"text renderer option {key!r} must be #rrggbb, got {value!r}")
    return value


def _parse_colour(value: str) -> np.ndarray:
    """Parse #rrggbb into a float32 (3,) sRGB row in [0, 1]."""
    digits = value.strip().lower().lstrip("#")
    return np.asarray(
        [int(digits[at : at + 2], 16) / 255.0 for at in (0, 2, 4)], dtype=np.float32
    )


def _font_identity(path: str | None) -> tuple[str | None, int, int]:
    """Return glyph_ramp's font cache key, re-raising its error under this renderer's name."""
    try:
        return _font_key(path)
    except ValueError as exc:
        raise ValueError(f"text renderer font file not found: {path}") from exc


@lru_cache(maxsize=_FONT_CACHE)
def _font(font_key: tuple[str | None, int, int], size: int) -> ImageFont.FreeTypeFont:
    """Load the font of one cache key at size, or Pillow's bundled default when pathless."""
    if font_key[0] is None:
        return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))
    try:
        return ImageFont.truetype(font_key[0], size)
    except OSError as exc:
        raise ValueError(f"text renderer font file is not a usable font: {font_key[0]}") from exc


@lru_cache(maxsize=_METRIC_CACHE)
def _vmetrics(font_key: tuple[str | None, int, int], size: int) -> tuple[int, int]:
    """Return the (ascent, descent) in pixels of one font at one size."""
    return _font(font_key, size).getmetrics()


@lru_cache(maxsize=_METRIC_CACHE)
def _advance(font_key: tuple[str | None, int, int], size: int, char: str) -> float:
    """Return the advance width of char at size, in pixels."""
    return float(_font(font_key, size).getlength(char))


@lru_cache(maxsize=_METRIC_CACHE)
def _kern(font_key: tuple[str | None, int, int], size: int, left: str, right: str) -> float:
    """Return the font's own pair kerning between two characters, in pixels."""
    font = _font(font_key, size)
    return float(font.getlength(left + right) - font.getlength(left) - font.getlength(right))


@lru_cache(maxsize=_METRIC_CACHE)
def _glyph_box(font_key: tuple[str | None, int, int], size: int, char: str) -> tuple[float, ...]:
    """Return the (x0, y0, x1, y1) ink box of char, relative to its pen on the baseline."""
    return tuple(float(value) for value in _font(font_key, size).getbbox(char, anchor="ls"))


@lru_cache(maxsize=_FONT_CACHE)
def _height_ratio(font_key: tuple[str | None, int, int]) -> float:
    """Return the (ascent + descent) per point of one font, cached per font identity."""
    ascent, descent = _font(font_key, _PROBE_SIZE).getmetrics()
    return (ascent + descent) / float(_PROBE_SIZE)


def _base_size(cell_h: int, font_key: tuple[str | None, int, int]) -> int:
    """Return the point size that makes one line of text fit a cell's height."""
    ratio = _height_ratio(font_key)
    return max(1, int(round(cell_h / ratio)) if ratio > 0.0 else int(cell_h))


def _word_extents(
    chars: list[str], sizes: list[int], start: int, stop: int, options: TextOptions,
    font_key: tuple[str | None, int, int],
) -> tuple[float, float, float]:
    """Return (advance, ink right, ink left) of one word, relative to its starting pen."""
    cursor, right, left = 0.0, 0.0, 0.0
    for offset in range(start, stop):
        box = _glyph_box(font_key, sizes[offset], chars[offset])
        left = min(left, cursor + box[0])
        right = max(right, cursor + box[2])
        cursor += _advance(font_key, sizes[offset], chars[offset])
        if offset + 1 < stop:
            cursor += options.kerning * _kern(
                font_key, sizes[offset], chars[offset], chars[offset + 1]
            )
    return cursor, right, left


def _flow(
    chars: list[str], sizes: list[int], base: int, width: int, options: TextOptions,
    font_key: tuple[str | None, int, int],
) -> list[_Placed]:
    """Lay the characters out word by word, wrapping at width with real font metrics.

    The line box is the largest glyph's: its ascent places the first baseline and its
    height, times ``line_distance``, sets the leading, so a 1.5x glyph never collides
    with the next line.
    """
    lead_size = max(sizes) if sizes else base
    ascent = _vmetrics(font_key, lead_size)[0]
    lead = options.line_distance * float(sum(_vmetrics(font_key, lead_size)))
    placed: list[_Placed] = []
    pen, line, index = 0.0, 0, 0
    while index < len(chars):
        stop = index
        while stop < len(chars) and chars[stop] != " ":
            stop += 1
        if stop == index:  # a separator: nothing to draw, the space advance is added below
            index += 1
            continue
        advance, right, left = _word_extents(chars, sizes, index, stop, options, font_key)
        if pen > 0.0 and pen + max(advance, right) + 1.0 > width:
            pen, line = 0.0, line + 1
        shift = -left if left < 0.0 else 0.0
        cursor = 0.0
        for offset in range(index, stop):
            placed.append(
                _Placed(chars[offset], pen + shift + cursor, ascent + line * lead,
                        sizes[offset], offset)
            )
            cursor += _advance(font_key, sizes[offset], chars[offset])
            if offset + 1 < stop:
                cursor += options.kerning * _kern(
                    font_key, sizes[offset], chars[offset], chars[offset + 1]
                )
        pen += cursor + _advance(font_key, base, " ")
        index = stop + 1
    return placed


def _cell_ink(
    table: np.ndarray, grid: CellGrid, glyph: _Placed, font_key: tuple[str | None, int, int]
) -> float:
    """Return the ink (1 - perceptual luma) of the cell under one nominal glyph."""
    x = glyph.pen + 0.5 * _advance(font_key, glyph.size, glyph.character)
    y = glyph.baseline - 0.5 * _vmetrics(font_key, glyph.size)[0]
    col = min(grid.cols - 1, max(0, int(x // grid.cell_w)))
    row = min(grid.rows - 1, max(0, int(y // grid.cell_h)))
    return float(table[row, col])


def _modulation(
    grid: CellGrid, chars: list[str], base: int, width: int, options: TextOptions,
    font_key: tuple[str | None, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Return the per-character size factor and ink amount, read at the nominal layout."""
    count = len(chars)
    jitter = np.random.default_rng(options.seed).uniform(-JITTER, JITTER, count)
    table = np.ascontiguousarray(1.0 - color.linear_to_srgb(grid.luma), dtype=np.float32)
    factors = np.ones(count, dtype=np.float32)
    inks = np.zeros(count, dtype=np.float32)
    for glyph in _flow(chars, [base] * count, base, width, options, font_key):
        ink = _cell_ink(table, grid, glyph, font_key)
        inks[glyph.slot] = ink
        if options.size_mode == "variable":
            factors[glyph.slot] = np.clip(
                MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR
            )
    return factors, inks


def _sizes(base: int, factors: np.ndarray, size_mode: str) -> list[int]:
    """Return the point size of every character: one size when fixed, else base x factor."""
    if size_mode == "fixed":
        return [base] * int(factors.size)
    return [max(1, int(round(base * float(factor)))) for factor in factors]


def _ink_extents(
    placed: list[_Placed], font_key: tuple[str | None, int, int]
) -> tuple[float, float, float, float]:
    """Return the (left, right, top, bottom) ink extents of a placed paragraph, in pixels."""
    left = top = math.inf
    right = bottom = -math.inf
    for glyph in placed:
        box = _glyph_box(font_key, glyph.size, glyph.character)
        left = min(left, glyph.pen + box[0])
        right = max(right, glyph.pen + box[2])
        top = min(top, glyph.baseline + box[1])
        bottom = max(bottom, glyph.baseline + box[3])
    if left is math.inf:
        return 0.0, 0.0, 0.0, 0.0
    return left, right, top, bottom


def _stroke(size: int, ink: float, weight_mode: str) -> int:
    """Return the stroke width of one glyph: 0 when fixed, else ink x a size-keyed budget."""
    if weight_mode == "fixed":
        return 0
    return int(round(ink * max(1, size // 8)))


def _opacity(ink: float) -> float:
    """Return the glyph opacity: paper stays faintly traced, dense ink is opaque."""
    return MIN_OPACITY + (1.0 - MIN_OPACITY) * ink


def _place(
    placed: list[_Placed], inks: np.ndarray, dx: float, dy: float, width: int, height: int,
    options: TextOptions, font_key: tuple[str | None, int, int],
) -> list[TextGlyph]:
    """Return the glyphs as boxes clamped inside the canvas, with size, stroke and opacity.

    §10: ``size_mode: fixed`` keeps every glyph the same size and modulates only opacity,
    so it also pins the weight; ``weight_mode`` shapes the weight in variable size mode.
    """
    out: list[TextGlyph] = []
    weight_mode = options.weight_mode if options.size_mode == "variable" else "fixed"
    for glyph in placed:
        ascent, descent = _vmetrics(font_key, glyph.size)
        box_w = min(_advance(font_key, glyph.size, glyph.character), float(width))
        box_h = min(float(ascent + descent), float(height))
        x = min(max(glyph.pen + dx, 0.0), max(0.0, width - box_w))
        y = min(max(glyph.baseline + dy - ascent, 0.0), max(0.0, height - box_h))
        ink = float(inks[glyph.slot])
        out.append(
            TextGlyph(
                glyph.character, x, y, box_w, box_h, options.fg.lower(), options.bg.lower(),
                glyph.size, _stroke(glyph.size, ink, weight_mode), _opacity(ink),
            )
        )
    return out


def _glyphs(grid: CellGrid, options: TextOptions) -> list[TextGlyph]:
    """Lay the paragraph out over the whole canvas and return every visible glyph."""
    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
    if np.shape(grid.luma) != (grid.rows, grid.cols):
        raise ValueError(
            f"text renderer needs grid.luma of shape {(grid.rows, grid.cols)}, "
            f"got {np.shape(grid.luma)}"
        )
    chars = list(" ".join(options.text.split()))
    if not chars or width <= 0 or height <= 0:
        return []
    font_key = _font_key(options.font)
    base = options.size if options.size is not None else _base_size(grid.cell_h, font_key)
    base = max(1, min(base, max(width, height)))
    factors, inks = _modulation(grid, chars, base, width, options, font_key)
    placed: list[_Placed] = []
    dx = dy = 0.0
    for _ in range(_FIT_PASSES):
        placed = _flow(chars, _sizes(base, factors, options.size_mode), base, width,
                       options, font_key)
        left, right, top, bottom = _ink_extents(placed, font_key)
        dx, dy = max(0.0, -left), max(0.0, -top)
        if right + dx + 1.0 <= width and bottom + dy + 1.0 <= height:
            break
        scale = min(width / max(right + dx, _EPSILON),
                    height / max(bottom + dy, _EPSILON)) * 0.98
        nxt = max(1, min(base - 1, int(base * scale)))
        if nxt == base:
            break
        base = nxt
    return _place(placed, inks, dx, dy, width, height, options, font_key)


@lru_cache(maxsize=_MASK_CACHE)
def _mask(
    font_key: tuple[str | None, int, int], char: str, size: int, stroke: int
) -> tuple[np.ndarray, int, int]:
    """Return the read-only ink mask of one glyph, its patch offset and its top offset.

    The mask is drawn once per (font, character, size, stroke) and cached; every input is
    part of the key, the cache is bounded and the array is not writable, so no caller can
    observe or cause a change of the rendered output (§3 invariant 2, H11).
    """
    font = _font(font_key, size)
    box = font.getbbox(char, anchor="ls")
    pad = stroke + 1
    x0, y0 = math.floor(box[0]) - pad, math.floor(box[1]) - pad
    x1, y1 = math.ceil(box[2]) + pad, math.ceil(box[3]) + pad
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        empty = np.zeros((1, 1), dtype=np.float32)
        empty.setflags(write=False)
        return empty, 0, 0
    canvas = PILImage.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(canvas).text(
        (-x0, -y0), char, font=font, fill=255, anchor="ls",
        stroke_width=stroke, stroke_fill=255,
    )
    ink = np.asarray(canvas, dtype=np.float32) / 255.0
    ink.setflags(write=False)
    return ink, x0, y0


def _blit(
    frame: np.ndarray, glyph: TextGlyph, fg: np.ndarray,
    font_key: tuple[str | None, int, int],
) -> None:
    """Composite one glyph's ink into frame with its opacity, clipped to the canvas."""
    if glyph.opacity <= 0.0:
        return
    mask, offset_x, offset_y = _mask(font_key, glyph.character, glyph.size, glyph.stroke)
    if mask.size <= 1 and not mask.any():
        return
    x = int(round(glyph.x)) + offset_x
    y = int(round(glyph.y + _vmetrics(font_key, glyph.size)[0])) + offset_y
    x0, y0 = max(0, -x), max(0, -y)
    x1 = min(mask.shape[1], frame.shape[1] - x)
    y1 = min(mask.shape[0], frame.shape[0] - y)
    if x0 >= x1 or y0 >= y1:
        return
    alpha = (mask[y0:y1, x0:x1] * glyph.opacity)[..., None]
    region = frame[y + y0 : y + y1, x + x0 : x + x1]
    region[:] = region * (1.0 - alpha) + fg * alpha


def _frame(grid: CellGrid, options: TextOptions) -> np.ndarray:
    """Return the (rows*cell_h, cols*cell_w, 3) float32 frame of one text render."""
    fg = _parse_colour(options.fg)
    frame = np.empty(
        (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3), dtype=np.float32
    )
    frame[...] = _parse_colour(options.bg)
    font_key = _font_key(options.font)
    for glyph in _glyphs(grid, options):
        _blit(frame, glyph, fg, font_key)
    return np.ascontiguousarray(frame, dtype=np.float32)


def register_text_renderer() -> CellRenderer:
    """Register the TextRenderer under "text" and return it."""
    return register_renderer(TextRenderer())


register_text_renderer()

