# Reviewer prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are reviewing one task of the Lattice project: a family of free, open-source image-transformation
applications sharing one engine, each running standalone and also plugging into the ArtCraft suite.
You see the task card, the contract sections it must satisfy, the git diff, the gate results and the
coder's notes. You do not see the rest of the repository, and you do not need to.

The dithering application is frozen and shipped (harness 1.1 feature-complete: 18 cards T17-T34,
~1212 test cases at wave-7 close; its human checkpoints H6-H9 are the 1.1 harness's business),
with a public release. Your job is to decide whether this diff can join it.

WHAT TO CHECK, IN THIS ORDER
1. **Contract conformance.** Names, signatures, dtypes, ranges, ordering, error types. A deviation
   from the contract is a blocker even if the tests pass.
2. **Regression.** Does anything that worked before behave differently? Gate G7 (core regression)
   exists for this. A regression is an E6 deviation and a blocker unless the card explicitly asks
   for the change.
3. **The abstraction holds.** Gate G8 checks that every registered `CellRenderer` satisfies §3. Read
   the invariant list and check the diff against each one, not just the gate result. A renderer that
   mutates its input, or whose output size is off by one, is a blocker.
4. **No abstraction leak.** Does `lattice_core` reference an application? Does an application import
   from another application? That is an E8 deviation and a blocker.
5. **No host coupling.** Does the application still work with no ArtCraft running? A missing token
   file, a refused connection or an absent host must be a normal state. That is an E9 deviation and a
   blocker.
6. **Test quality.** Do the tests actually fail on the old code? A test that passes before and after
   the change proves nothing. Look for assertions that restate the implementation, tests that would
   pass with the feature removed, and missing edge cases named in `accept`.
7. **Correctness of the maths.** For renderer and effect cards, check the formulas against the
   contract, not against intuition. Off-by-one in a kernel, a missing normalisation, a wrong colour
   space, a mask applied in the wrong order.
8. **Product quality** (cards L10, L12, L20, L21 only). Is the control discoverable? Does the default
   surprise? Does the message say what to do next? A task can pass every test and still be an E7.
9. **Hygiene.** File length, function length, typing, docstrings, no dead code, no commented-out
   blocks, no debug prints.

SEVERITY
- **blocker**: wrong result, contract violation, regression, crash, data loss, abstraction leak,
  host coupling.
- **major**: missing acceptance item, test that cannot fail, wrong default, misleading message.
- **minor**: style, naming, a docstring that lies.

VERDICT
- `PASS` — no blocker, no major. Minors are listed but do not block.
- `FIX` — at least one blocker or major. The coder gets one more cycle with your findings.
- `ESCALATE` — the task cannot be done as specified, or the fix needs a contract change. Name the
  deviation class (E2, E4, E6, E7, E8, E9).

OUTPUT FORMAT, nothing else:
```json
{
  "verdict": "PASS | FIX | ESCALATE",
  "findings": [
    {"severity": "blocker|major|minor", "file": "...", "line": 0,
     "what": "...", "why": "...", "fix": "..."}
  ],
  "regression": "none | <what changed vs the frozen behaviour>",
  "renderer_invariants": "all six hold | <which one fails and how>",
  "tests_that_cannot_fail": ["..."],
  "notes": "<≤ 5 lines>"
}
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



GATE RESULTS (L9, attempt 2 — codeur opencode-go deepseek-v4.1-flash, TUÉ PAR TIMEOUT à 1500 s)
- ATTENTION, CIRCONSTANCE PARTICULIÈRE : le codeur n'a jamais rendu son rapport (exit 124,
  sortie vide). Les fichiers ont été écrits sur disque avant qu'il ne se bloque. Je les prends tels
  quels et je te les soumets — mais cela signifie qu'aucun NOTES ni DEVIATIONS ne les accompagne :
  ce que tu vois est le code nu, sans justification. Sois plus dur que d'habitude sur ce point.
- Owned tests : 60 passed (tests/test_text.py). `text.py` 400 l exactement, `test_text.py` 397 l.
- Suite complète : 2004 passed, 1 skipped (2005 collectés). G1 ruff : all checks passed.
  G3 check_contract : OK. G8 : `list_renderers()` contient désormais `text` (8 renderers) ; les six
  invariants §3 sont couverts par test_cell.py, qui reste vert.
- Enregistrement : le module s'auto-enregistre via `register_text_renderer()` en fin de fichier ;
  l'orchestrateur a ajouté UNE ligne d'import dans `lattice_core/renderers/__init__.py` (fichier hors
  owns de la carte, règle DEV-208) — la première tentative appelait aussi la fonction, ce qui levait
  « duplicate renderer name: 'text' » puisque le module s'enregistre déjà à l'import.

CE QUE JE TE DEMANDE DE VÉRIFIER EN PRIORITÉ (les cinq items d'accept de la carte)
1. `size_mode: "fixed"` → glyphes de taille identique ; `"variable"` → au moins 5 tailles distinctes
   sur un dégradé.
2. Le rectangle de sortie est rempli EXACTEMENT, sans trou ni débordement, dans les deux modes.
3. Un paragraphe de 200 mots se replie sans coupure et sans un seul glyphe hors du canevas.
4. Même texte + même graine → même sortie sur deux appels.
5. `text` vide → `ValueError` nommant l'option.
Plus, spécifiquement pour cette carte : §10 exige une modulation du POIDS, de la TAILLE et de
l'OPACITÉ par `luma` (S2) — vérifie que l'encre ne s'effondre pas sur une palette neutre
(`[[0.5, 0.5, 0.5]]`), et que `size_mode: fixed` ne fait pas taire la modulation de taille.

DIFF (les deux fichiers de la carte + la ligne d'enregistrement, créés de zéro)

diff --git a/lattice_core/renderers/__init__.py b/lattice_core/renderers/__init__.py
index 83cf5f9..a742aca 100644
--- a/lattice_core/renderers/__init__.py
+++ b/lattice_core/renderers/__init__.py
@@ -30,3 +30,4 @@ register_pixel_renderer()
 from lattice_core.renderers.bitmask import register_bitmask_renderers  # noqa: E402, F401  (bitmask family self-registers on import; DEV-208 L8)
 from lattice_core.renderers.glyph_ramp import GlyphRampRenderer as GlyphRampRenderer  # noqa: E402
 from lattice_core.renderers.glyph_shape import GlyphShapeRenderer  # noqa: E402  (L7 glyph_shape self-registers on import)
+from lattice_core.renderers.text import TextRenderer as TextRenderer  # noqa: E402  (L9 text self-registers on import)
diff --git a/lattice_core/renderers/text.py b/lattice_core/renderers/text.py
new file mode 100644
index 0000000..6bf0be0
--- /dev/null
+++ b/lattice_core/renderers/text.py
@@ -0,0 +1,400 @@
+"""The text renderer: a flowing paragraph in a real font, modulated by luma (§10).
+
+Glyphs are laid out with the font's own advances, pair kerning and line distance, wrapped
+word by word to the canvas width, so the output reads as a paragraph and not a grid. The
+linear luma of the cell under a glyph (S2, re-encoded to sRGB per AMD-010) drives its size
+(0.5x to 1.5x, §10), stroke weight and opacity, so ink never collapses on a neutral palette.
+The paper paints every pixel, ink is clipped to the canvas, and an overflowing paragraph is
+re-flowed smaller rather than clipped. Fonts, metrics and masks are bounded input-keyed
+caches that never change the output (§3 invariant 2, H11); randomness is a seed-keyed jitter.
+"""
+
+from __future__ import annotations
+
+import math
+from dataclasses import dataclass
+from functools import lru_cache
+from typing import NamedTuple, cast
+
+import numpy as np
+from PIL import Image as PILImage
+from PIL import ImageDraw, ImageFont
+
+from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
+from lattice_core.renderers.glyph_ramp import _font_key, _layout_arguments
+from lattice_core.types import Palette
+
+_FontKey = tuple[str | None, int, int]
+_Metrics = tuple[float, float, float, float, float]
+NAME = "text"
+CELL_ASPECT = 0.5
+DEFAULT_TEXT = "Lattice renders a paragraph in a real font, one glyph at a time."
+DEFAULT_FG = "#000000"
+DEFAULT_BG = "#ffffff"
+SIZE_MODES = ("fixed", "variable")
+WEIGHT_MODES = ("fixed", "variable")
+MIN_FACTOR, MAX_FACTOR = 0.5, 1.5
+MIN_OPACITY = 0.12
+MAX_SIZE, JITTER = 512, 0.08
+_PROBE_SIZE, _FIT_PASSES, _CACHE = 100, 8, 1024
+_EPSILON = 1e-6
+_HEX_DIGITS = frozenset("0123456789abcdef")
+_EMPTY_MASK = np.zeros((1, 1), np.float32)  # read-only: an inkless glyph's mask
+_EMPTY_MASK.setflags(write=False)
+
+
+@dataclass(frozen=True)
+class TextOptions:
+    """Validated options of one text render (§10)."""
+
+    text: str = DEFAULT_TEXT
+    font: str | None = None
+    size: int | None = None
+    line_distance: float = 1.2
+    kerning: float = 1.0
+    size_mode: str = "variable"
+    weight_mode: str = "variable"
+    fg: str = DEFAULT_FG
+    bg: str = DEFAULT_BG
+    seed: int = 0
+
+
+class TextGlyph(NamedTuple):
+    """One placed glyph: §3's layout fields plus its point size, stroke width and opacity."""
+
+    character: str
+    x: float
+    y: float
+    width: float
+    height: float
+    fill: str
+    paper: str
+    size: int
+    stroke: int
+    opacity: float
+
+
+class _Placed(NamedTuple):
+    """One glyph at its pen and baseline, before modulation becomes a placed box."""
+
+    character: str
+    pen: float
+    baseline: float
+    size: int
+    slot: int
+
+
+class TextRenderer:
+    """Draw a flowing paragraph whose every glyph is sized, weighted and faded by luma."""
+
+    name = NAME
+
+    def cell_aspect(self) -> float:
+        """Return 0.5: the nominal monospace cell ratio, width over height (§10)."""
+        return CELL_ASPECT
+
+    def subgrid(self) -> tuple[int, int]:
+        """Return (1, 1): a glyph carries the whole cell, with no sub-points."""
+        return (1, 1)
+
+    def consumes(self) -> frozenset[str]:
+        """Return {"luma"}: luma modulates the glyphs, fg/bg colour them (§10, S2)."""
+        return frozenset({"luma"})
+
+    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
+        """Rasterise the paragraph of grid into an image of the exact grid geometry."""
+        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))
+
+    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
+        """Return the unrounded frame: ink over a fully painted paper, float32 in [0, 1]."""
+        options = _read_options(style)
+        fg = _parse_colour(options.fg)
+        shape = (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
+        frame = np.full(shape, _parse_colour(options.bg), np.float32)
+        font_key = _font_key(options.font)
+        for glyph in _Paragraph(grid, options).glyphs():
+            _blit(frame, glyph, fg, font_key)
+        return np.ascontiguousarray(frame, dtype=np.float32)
+
+    def layout(
+        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
+    ) -> list[TextGlyph]:
+        """Return every visible glyph inside the canvas, in reading order (§3, §11).
+
+        Both the §3 ``layout(grid, style)`` and ``layout(grid, palette, style)`` forms are
+        accepted; only fg/bg and luma change the output, never the palette.
+        """
+        _, style = _layout_arguments(palette, style)
+        return _Paragraph(grid, _read_options(style)).glyphs()
+
+
+def _read_options(style: RenderStyle) -> TextOptions:
+    """Validate style.options into TextOptions; unknown keys are ignored (§6)."""
+    raw = dict(style.options)
+    text = raw.get("text", DEFAULT_TEXT)
+    if not isinstance(text, str) or not text.strip():
+        raise ValueError(f"text renderer option 'text' must be a non-empty string, got {text!r}")
+    font = raw.get("font")
+    if font is not None and not isinstance(font, str):
+        raise ValueError(f"text renderer option 'font' must be a path string or null: {font!r}")
+    try:
+        _font_key(font)  # ValueError naming the path, before anything is drawn
+    except ValueError as exc:
+        raise ValueError(f"text renderer font file not found: {font}") from exc
+    size = raw.get("size")
+    if size is not None and (isinstance(size, bool) or not isinstance(size, int)
+                             or not 1 <= size <= MAX_SIZE):
+        raise ValueError(f"text renderer option 'size' must be in [1, {MAX_SIZE}]: {size!r}")
+    line_distance = _number(raw, "line_distance", 1.2)
+    if line_distance <= 0.0:
+        raise ValueError(f"text renderer 'line_distance' must be positive: {line_distance!r}")
+    kerning = _number(raw, "kerning", 1.0)
+    if not 0.0 <= kerning <= 2.0:
+        raise ValueError(f"text renderer 'kerning' must be in [0, 2]: {kerning!r}")
+    seed = raw.get("seed", 0)
+    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
+        raise ValueError(f"text renderer option 'seed' must be a non-negative integer: {seed!r}")
+    fg, bg = raw.get("fg", DEFAULT_FG), raw.get("bg", DEFAULT_BG)
+    _parse_colour(fg, "fg")
+    _parse_colour(bg, "bg")
+    return TextOptions(
+        text=text, font=font, size=size, line_distance=line_distance, kerning=kerning,
+        size_mode=_choice(raw, "size_mode", "variable", SIZE_MODES),
+        weight_mode=_choice(raw, "weight_mode", "variable", WEIGHT_MODES),
+        fg=cast(str, fg), bg=cast(str, bg), seed=seed,
+    )
+
+
+def _number(raw: dict, key: str, default: float) -> float:
+    """Return one finite numeric option, naming it when the value is not a number."""
+    value = raw.get(key, default)
+    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
+        raise ValueError(f"text renderer option {key!r} must be a finite number: {value!r}")
+    return float(value)
+
+
+def _choice(raw: dict, key: str, default: str, allowed: tuple[str, ...]) -> str:
+    """Return one enumerated option, naming it and its allowed values when unknown."""
+    value = raw.get(key, default)
+    if value not in allowed:
+        raise ValueError(f"text renderer option {key!r} must be one of {allowed}: {value!r}")
+    return str(value)
+
+
+def _parse_colour(value: object, key: str = "colour") -> np.ndarray:
+    """Parse one #rrggbb option into a float32 (3,) sRGB row in [0, 1], or name it."""
+    digits = str(value).strip().lower().lstrip("#")
+    if not isinstance(value, str) or len(digits) != 6 or not _HEX_DIGITS.issuperset(digits):
+        raise ValueError(f"text renderer option {key!r} must be a #rrggbb colour: {value!r}")
+    return np.asarray([int(digits[at : at + 2], 16) / 255.0 for at in (0, 2, 4)], np.float32)
+
+
+@lru_cache(maxsize=_CACHE)
+def _font(font_key: _FontKey, size: int) -> ImageFont.FreeTypeFont:
+    """Load the font of one cache key at size, or Pillow's bundled default when pathless."""
+    if font_key[0] is None:
+        return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))
+    try:
+        return ImageFont.truetype(font_key[0], size)
+    except OSError as exc:
+        raise ValueError(f"text renderer font is not a usable font: {font_key[0]}") from exc
+
+
+@lru_cache(maxsize=_CACHE)
+def _glyph_metrics(font_key: _FontKey, size: int, char: str) -> _Metrics:
+    """Return (advance, x0, y0, x1, y1) of one glyph, relative to its pen on the baseline."""
+    font = _font(font_key, size)
+    x0, y0, x1, y1 = font.getbbox(char, anchor="ls")
+    return float(font.getlength(char)), float(x0), float(y0), float(x1), float(y1)
+
+
+@lru_cache(maxsize=_CACHE)
+def _kern(font_key: _FontKey, size: int, left: str, right: str) -> float:
+    """Return the font's own pair kerning between two characters, in pixels."""
+    font = _font(font_key, size)
+    return float(font.getlength(left + right) - font.getlength(left) - font.getlength(right))
+
+
+class _Paragraph:
+    """One paragraph laid out over a fixed canvas: modulation, wrapping and fit."""
+
+    def __init__(self, grid: CellGrid, options: TextOptions) -> None:
+        """Measure the canvas, the font and the nominal point size of the paragraph."""
+        if np.shape(grid.luma) != (grid.rows, grid.cols):
+            raise ValueError(
+                f"text renderer needs grid.luma of shape {(grid.rows, grid.cols)}, "
+                f"got {np.shape(grid.luma)}"
+            )
+        self.grid = grid
+        self.options = options
+        self.width = grid.cols * grid.cell_w
+        self.height = grid.rows * grid.cell_h
+        self.chars = list(" ".join(options.text.split()))
+        self.font_key = _font_key(options.font)
+        ratio = sum(_font(self.font_key, _PROBE_SIZE).getmetrics()) / float(_PROBE_SIZE)
+        nominal = int(round(grid.cell_h / ratio)) if ratio > 0.0 else grid.cell_h
+        self.base = max(1, min(options.size or nominal, max(self.width, self.height)))
+        self.count = len(self.chars)
+        self.factors = np.ones(self.count, dtype=np.float32)
+        self.inks = np.zeros(self.count, dtype=np.float32)
+
+    def glyphs(self) -> list[TextGlyph]:
+        """Lay the paragraph out and return every visible glyph, clamped to the canvas."""
+        if not self.chars or self.width <= 0 or self.height <= 0:
+            return []
+        self._modulate()
+        placed, dx, dy = self._fit()
+        return self._place(placed, dx, dy)
+
+    def _modulate(self) -> None:
+        """Fill each character's ink and size factor from the cells under the nominal layout."""
+        options, key = self.options, self.font_key
+        jitter = np.random.default_rng(options.seed).uniform(-JITTER, JITTER, self.count)
+        table = np.ascontiguousarray(1.0 - color.linear_to_srgb(self.grid.luma), np.float32)
+        for glyph in self._flow([self.base] * self.count):
+            advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
+            x = glyph.pen + 0.5 * advance
+            y = glyph.baseline - 0.5 * _font(key, glyph.size).getmetrics()[0]
+            col = min(self.grid.cols - 1, max(0, int(x // self.grid.cell_w)))
+            row = min(self.grid.rows - 1, max(0, int(y // self.grid.cell_h)))
+            ink = float(table[row, col])
+            self.inks[glyph.slot] = ink
+            if options.size_mode == "variable":
+                self.factors[glyph.slot] = np.clip(
+                    MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR
+                )
+
+    def _flow(self, sizes: list[int]) -> list[_Placed]:
+        """Lay the characters out word by word and wrap each line at the canvas width."""
+        key, options, chars = self.font_key, self.options, self.chars
+        lead_size = max(sizes) if sizes else self.base
+        ascent, descent = _font(key, lead_size).getmetrics()
+        lead = options.line_distance * float(ascent + descent)
+        placed: list[_Placed] = []
+        pen, line, index = 0.0, 0, 0
+        while index < len(chars):
+            stop = index
+            while stop < len(chars) and chars[stop] != " ":
+                stop += 1
+            if stop == index:  # a separator: nothing to draw, its advance is added below
+                index += 1
+                continue
+            word: list[tuple[int, str, float]] = []
+            cursor = right = left = 0.0
+            for offset in range(index, stop):
+                step, x0, _, x1, _ = _glyph_metrics(key, sizes[offset], chars[offset])
+                word.append((offset, chars[offset], cursor))
+                left = min(left, cursor + x0)
+                right = max(right, cursor + x1)
+                cursor += step
+                if offset + 1 < stop:
+                    cursor += options.kerning * _kern(
+                        key, sizes[offset], chars[offset], chars[offset + 1]
+                    )
+            if pen > 0.0 and pen + max(cursor, right) + 1.0 > self.width:
+                pen, line = 0.0, line + 1
+            shift = -left if left < 0.0 else 0.0
+            for offset, char, relative in word:
+                placed.append(_Placed(char, pen + shift + relative, ascent + line * lead,
+                                      sizes[offset], offset))
+            pen += cursor + _glyph_metrics(key, self.base, " ")[0]
+            index = stop + 1
+        return placed
+
+    def _fit(self) -> tuple[list[_Placed], float, float]:
+        """Return the placed glyphs and the shift that brings their ink inside the canvas."""
+        placed: list[_Placed] = []
+        dx = dy = 0.0
+        for _ in range(_FIT_PASSES):
+            if self.options.size_mode == "fixed":
+                sizes = [self.base] * self.count
+            else:
+                sizes = [max(1, int(round(self.base * float(f)))) for f in self.factors]
+            placed = self._flow(sizes)
+            left = top = math.inf
+            right = bottom = -math.inf
+            for glyph in placed:
+                x0, y0, x1, y1 = _glyph_metrics(self.font_key, glyph.size, glyph.character)[1:]
+                left = min(left, glyph.pen + x0)
+                right = max(right, glyph.pen + x1)
+                top = min(top, glyph.baseline + y0)
+                bottom = max(bottom, glyph.baseline + y1)
+            if left is math.inf:
+                left = right = top = bottom = 0.0
+            dx, dy = max(0.0, -left), max(0.0, -top)
+            if right + dx + 1.0 <= self.width and bottom + dy + 1.0 <= self.height:
+                break
+            scale = min(self.width / max(right + dx, _EPSILON),
+                        self.height / max(bottom + dy, _EPSILON)) * 0.98
+            nxt = max(1, min(self.base - 1, int(self.base * scale)))
+            if nxt == self.base:
+                break
+            self.base = nxt
+        return placed, dx, dy
+
+    def _place(self, placed: list[_Placed], dx: float, dy: float) -> list[TextGlyph]:
+        """Return the glyphs as boxes clamped inside the canvas, with size, stroke, opacity."""
+        out: list[TextGlyph] = []
+        options, key = self.options, self.font_key
+        weight_mode = options.weight_mode if options.size_mode == "variable" else "fixed"
+        for glyph in placed:
+            advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
+            ascent, descent = _font(key, glyph.size).getmetrics()
+            box_w = min(advance, float(self.width))
+            box_h = min(float(ascent + descent), float(self.height))
+            x = min(max(glyph.pen + dx, 0.0), max(0.0, self.width - box_w))
+            y = min(max(glyph.baseline + dy - ascent, 0.0), max(0.0, self.height - box_h))
+            ink = float(self.inks[glyph.slot])
+            stroke = 0 if weight_mode == "fixed" else int(round(ink * max(1, glyph.size // 8)))
+            out.append(TextGlyph(
+                glyph.character, x, y, box_w, box_h, options.fg.lower(), options.bg.lower(),
+                glyph.size, stroke, MIN_OPACITY + (1.0 - MIN_OPACITY) * ink,
+            ))
+        return out
+
+
+@lru_cache(maxsize=_CACHE)
+def _mask(font_key: _FontKey, char: str, size: int, stroke: int) -> tuple[np.ndarray, int, int]:
+    """Return the read-only ink mask of one glyph and the offset of its patch's origin."""
+    font = _font(font_key, size)
+    x0, y0, x1, y1 = font.getbbox(char, anchor="ls")
+    pad = stroke + 1
+    left, top = math.floor(x0) - pad, math.floor(y0) - pad
+    right, bottom = math.ceil(x1) + pad, math.ceil(y1) + pad
+    if right <= left or bottom <= top:
+        return _EMPTY_MASK, 0, 0
+    canvas = PILImage.new("L", (right - left, bottom - top), 0)
+    ImageDraw.Draw(canvas).text(
+        (-left, -top), char, font=font, fill=255, anchor="ls",
+        stroke_width=stroke, stroke_fill=255,
+    )
+    mask = np.asarray(canvas, np.float32) / 255.0
+    mask.setflags(write=False)
+    return mask, left, top
+
+
+def _blit(frame: np.ndarray, glyph: TextGlyph, fg: np.ndarray, font_key: _FontKey) -> None:
+    """Composite one glyph's ink into frame with its opacity, clipped to the canvas."""
+    if glyph.opacity <= 0.0:
+        return
+    mask, offset_x, offset_y = _mask(font_key, glyph.character, glyph.size, glyph.stroke)
+    if mask.size <= 1 and not mask.any():
+        return
+    x = int(round(glyph.x)) + offset_x
+    y = int(round(glyph.y + _font(font_key, glyph.size).getmetrics()[0])) + offset_y
+    x0, y0 = max(0, -x), max(0, -y)
+    x1, y1 = min(mask.shape[1], frame.shape[1] - x), min(mask.shape[0], frame.shape[0] - y)
+    if x0 >= x1 or y0 >= y1:
+        return
+    alpha = (mask[y0:y1, x0:x1] * glyph.opacity)[..., None]
+    region = frame[y + y0 : y + y1, x + x0 : x + x1]
+    region[:] = region * (1.0 - alpha) + fg * alpha
+
+
+def register_text_renderer() -> CellRenderer:
+    """Register the TextRenderer under "text" and return it."""
+    return register_renderer(TextRenderer())
+
+
+register_text_renderer()
diff --git a/tests/test_text.py b/tests/test_text.py
new file mode 100644
index 0000000..aba1e3b
--- /dev/null
+++ b/tests/test_text.py
@@ -0,0 +1,397 @@
+"""Tests for the text renderer (§3, §10) — card L9.
+
+Wrap points, leading and kerning are pinned against Pillow's own font metrics, computed
+independently here: a change that moves both the renderer and its arithmetic still fails.
+The renderer is palette-independent by contract (S2), so renders are compared across very
+different palettes.
+"""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+import numpy as np
+import pytest
+from PIL import ImageFont
+
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
+from lattice_core.renderers import text as text_module
+from lattice_core.renderers.text import DEFAULT_BG, MIN_OPACITY, TextGlyph, TextRenderer
+from lattice_core.types import Palette
+
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+COLOUR: Palette = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
+NEUTRAL: Palette = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
+CELL_W, CELL_H = 8, 16
+SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
+_WORDS = (
+    "lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
+    "canvas grid luma ink paper palette neutral source image renderer"
+).split()
+PARAGRAPH = " ".join(_WORDS[(index * 7) % len(_WORDS)] for index in range(200))
+RENDERER = TextRenderer()
+
+
+def _canvas(
+    cols: int = 12, rows: int = 6, cell_w: int = CELL_W, cell_h: int = CELL_H,
+    flat: float | None = None,
+) -> CellGrid:
+    """Return a grid over a black-to-white gradient, or over one flat linear luma."""
+    cols = int(cols)
+    rows = int(rows)
+    if flat is None:
+        luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
+    else:
+        luma = np.full((rows, cols), flat, np.float32)
+    return CellGrid(
+        cols=cols, rows=rows, cell_w=int(cell_w), cell_h=int(cell_h),
+        index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma.copy(),
+        samples=luma[:, :, None].copy(),
+    )
+
+
+def _style(**options: object) -> RenderStyle:
+    """Return a RenderStyle carrying the given text options."""
+    return RenderStyle(options=dict(options))
+
+
+def _layout(grid: CellGrid, palette: Palette = BW, **options: object) -> list[TextGlyph]:
+    """Return the glyphs layout() places for these options."""
+    return RENDERER.layout(grid, palette, _style(**options))
+
+
+def _frame(grid: CellGrid, palette: Palette = BW, **options: object) -> np.ndarray:
+    """Return the float frame render_frame() draws for these options."""
+    return RENDERER.render_frame(grid, palette, _style(**options))
+
+
+def _image(grid: CellGrid, palette: Palette = BW, **options: object) -> np.ndarray:
+    """Return the rendered image as a uint8 array."""
+    return np.asarray(RENDERER.render(grid, palette, _style(**options)))
+
+
+def _line_tops(glyphs: list[TextGlyph]) -> list[float]:
+    """Return the distinct top edges of the placed glyph boxes, in reading order."""
+    return sorted({round(glyph.y, 6) for glyph in glyphs})
+
+
+def _default_font(size: int) -> ImageFont.FreeTypeFont:
+    """Return Pillow's bundled default font at size, as the FreeType font it is."""
+    return ImageFont.load_default(size=size)  # type: ignore[return-value]
+
+
+# --- accept 1: fixed keeps one size; variable gives at least five on a gradient ---
+
+
+def test_fixed_size_mode_gives_every_glyph_the_same_size():
+    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="fixed keeps glyphs identical")
+    assert len(glyphs) > 20
+    assert {glyph.size for glyph in glyphs} == {glyphs[0].size}
+
+
+def test_variable_size_mode_gives_at_least_five_distinct_sizes_on_a_gradient():
+    glyphs = _layout(_canvas(18, 6), text="variable size spreads ink across the canvas")
+    assert len({glyph.size for glyph in glyphs}) >= 5
+
+
+def test_fixed_size_mode_modulates_opacity_instead_of_size():
+    glyphs = _layout(_canvas(18, 6), size_mode="fixed", text="opacity carries the modulation")
+    assert len({round(glyph.opacity, 6) for glyph in glyphs}) >= 5
+
+
+# --- accept 2: the rectangle is filled exactly, with no gap and no overflow ---
+
+
+@pytest.mark.parametrize("mode", ["fixed", "variable"])
+def test_the_output_rectangle_is_exactly_the_grid_geometry(mode):
+    grid = _canvas(12, 5, 6, 18)
+    img = RENDERER.render(grid, BW, _style(size_mode=mode, text="exact geometry"))
+    assert img.size == (grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+    assert img.mode == "RGB"
+    frame = _frame(grid, size_mode=mode)
+    assert frame.shape == (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
+    assert frame.dtype == np.float32 and np.isfinite(frame).all()
+
+
+@pytest.mark.parametrize("mode", ["fixed", "variable"])
+def test_every_pixel_is_paper_or_ink_blended_over_paper(mode):
+    frame = _frame(_canvas(10, 4), size_mode=mode, text="no gap and no overflow",
+                   fg="#ff0000", bg="#0000ff")
+    assert frame.min() >= 0.0 and frame.max() <= 1.0
+    assert np.all(frame[:, :, 1] == 0.0), "a colour outside fg/bg reached the canvas"
+    ink, paper = frame[:, :, 0], 1.0 - frame[:, :, 2]
+    assert np.allclose(ink, paper, atol=2e-6), "pixels are not blends of the two colours"
+    assert ink.max() > 0.5 and ink.min() == 0.0
+
+
+@pytest.mark.parametrize("mode", ["fixed", "variable"])
+def test_every_glyph_box_lies_inside_the_canvas(mode):
+    grid = _canvas(10, 4)
+    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
+    for glyph in _layout(grid, size_mode=mode, text="boxes stay inside the canvas"):
+        assert 0.0 <= glyph.x and glyph.x + glyph.width <= width
+        assert 0.0 <= glyph.y and glyph.y + glyph.height <= height
+
+
+def test_the_paper_paints_the_whole_rectangle():
+    frame = _frame(_canvas(30, 4), text="short")
+    assert np.all(frame[-1, -1] == np.float32(1.0)), DEFAULT_BG
+    assert np.all(frame == np.float32(1.0), axis=-1).mean() > 0.3
+
+
+# --- accept 3: a 200-word paragraph wraps, unclipped ---
+
+
+@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"), [(40, 20, 8, 16), (20, 40, 6, 12)])
+def test_a_200_word_paragraph_wraps_over_many_lines(cols, rows, cell_w, cell_h):
+    tops = _line_tops(_layout(_canvas(cols, rows, cell_w, cell_h), text=PARAGRAPH))
+    assert len(tops) >= 20
+
+
+@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
+                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16)])
+def test_a_200_word_paragraph_never_places_a_glyph_outside_the_canvas(cols, rows, cell_w, cell_h):
+    grid = _canvas(cols, rows, cell_w, cell_h)
+    width, height = cols * cell_w, rows * cell_h
+    glyphs = _layout(grid, text=PARAGRAPH)
+    assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
+    assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
+    for glyph in glyphs:
+        assert 0.0 <= glyph.x and glyph.x + glyph.width <= width
+        assert 0.0 <= glyph.y and glyph.y + glyph.height <= height
+    frame = _frame(grid, text=PARAGRAPH)
+    assert frame.shape == (height, width, 3)
+    assert frame.min() >= 0.0 and frame.max() <= 1.0
+
+
+# --- accept 4: the same text and seed render identically ---
+
+
+def test_the_same_text_and_seed_render_and_lay_out_identically():
+    grid, options = _canvas(14, 6), {"text": "seed me", "seed": 3}
+    assert np.array_equal(_frame(grid, **options), _frame(grid, **options))
+    assert _layout(grid, **options) == _layout(grid, **options)
+    assert np.array_equal(_frame(grid, **options),
+                          TextRenderer().render_frame(grid, BW, _style(**options)))
+    assert not np.array_equal(_frame(grid, **options), _frame(grid, text="seed me", seed=4))
+
+
+# --- accept 5: empty text raises ValueError naming the option ---
+
+
+@pytest.mark.parametrize("value", ["", "   ", "\n\t ", " \r\n "])
+def test_empty_text_raises_value_error_naming_the_option(value):
+    with pytest.raises(ValueError) as excinfo:
+        RENDERER.render(_canvas(6, 4), BW, _style(text=value))
+    assert "text" in str(excinfo.value) and "option" in str(excinfo.value)
+
+
+# --- §10: real font metrics — kerning, leading, wrapping ---
+
+
+@pytest.mark.parametrize("kerning", [0.0, 0.5, 1.0, 2.0])
+def test_pair_kerning_moves_the_second_glyph_by_the_font_pair(kerning):
+    if not SYSTEM_FONT.is_file():
+        pytest.skip("no system TrueType font available")
+    first, second = _layout(_canvas(30, 14), font=str(SYSTEM_FONT), size=12, kerning=kerning,
+                            size_mode="fixed", text="AV")
+    reference = ImageFont.truetype(str(SYSTEM_FONT), 12)
+    pair = reference.getlength("AV") - reference.getlength("A") - reference.getlength("V")
+    assert pair != 0.0, "the pinned font must kern AV for this test to mean anything"
+    assert second.x - first.x == pytest.approx(
+        float(reference.getlength("A")) + kerning * float(pair), abs=1e-6
+    )
+
+
+def test_line_distance_scales_the_leading():
+    grid = _canvas(12, 30)
+    options = {"text": "one two three four five six seven eight nine ten",
+               "size": 8, "size_mode": "fixed"}
+    tight = _line_tops(_layout(grid, line_distance=1.0, **options))
+    loose = _line_tops(_layout(grid, line_distance=2.0, **options))
+    ascent, descent = _default_font(8).getmetrics()
+    assert len(tight) == 2 and len(loose) == 2
+    assert loose[1] - tight[1] == pytest.approx(float(ascent + descent), abs=1e-6)
+
+
+def test_words_wrap_when_they_no_longer_fit_the_width():
+    font = _default_font(10)
+    word, space = float(font.getlength("ab")), float(font.getlength(" "))
+    wide, narrow = int(3 * word + 3 * space), int(2 * word + space)
+    options = {"text": "ab ab ab", "size": 10, "size_mode": "fixed"}
+    assert _line_tops(_layout(_canvas(wide, 8, 1, 16), **options)) == [0.0]
+    assert len(_line_tops(_layout(_canvas(narrow, 8, 1, 16), **options))) == 3
+
+
+def test_default_text_is_a_usable_paragraph():
+    glyphs = _layout(_canvas(20, 6))
+    assert len(glyphs) > 10
+    assert {glyph.character for glyph in glyphs} <= set(text_module.DEFAULT_TEXT)
+
+
+# --- §10: luma modulation, independent of the palette (S2) ---
+
+
+def test_dark_cells_get_larger_heavier_and_darker_glyphs_than_light_cells():
+    dark = _layout(_canvas(8, 4, flat=0.0), text="ink")[0]
+    light = _layout(_canvas(8, 4, flat=1.0), text="ink")[0]
+    assert dark.size > light.size
+    assert dark.stroke > light.stroke
+    assert dark.opacity == pytest.approx(1.0)
+    assert light.opacity == pytest.approx(MIN_OPACITY, abs=1e-6)
+
+
+def test_ink_never_collapses_on_a_neutral_palette():
+    grid = _canvas(18, 6)
+    glyphs = _layout(grid, NEUTRAL, text="neutral ink must survive the palette")
+    assert len({glyph.size for glyph in glyphs}) >= 5
+    assert all(glyph.opacity >= MIN_OPACITY for glyph in glyphs)
+
+
+@pytest.mark.parametrize("palette", [BW, COLOUR, NEUTRAL])
+def test_the_choice_of_palette_never_changes_the_output(palette):
+    grid = _canvas(14, 5)
+    assert np.array_equal(_frame(grid, BW, text="palette free"),
+                          _frame(grid, palette, text="palette free"))
+
+
+# --- options ---
+
+
+def test_size_option_sets_the_base_point_size_in_fixed_mode():
+    glyphs = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
+    assert {glyph.size for glyph in glyphs} == {9}
+
+
+def test_layout_reports_the_ink_and_paper_colours():
+    glyph = _layout(_canvas(6, 3), text="colours", fg="#AABBCC", bg="#FFEEDD")[0]
+    assert glyph.fill == "#aabbcc" and glyph.paper == "#ffeedd"
+
+
+def test_missing_font_file_raises_value_error_naming_the_path():
+    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
+    with pytest.raises(ValueError) as excinfo:
+        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=path))
+    assert path in str(excinfo.value)
+
+
+def test_a_real_font_file_is_used():
+    if not SYSTEM_FONT.is_file():
+        pytest.skip("no system TrueType font available")
+    img = RENDERER.render(_canvas(10, 4), BW, _style(text="DejaVu", font=str(SYSTEM_FONT)))
+    assert img.size == (10 * CELL_W, 4 * CELL_H)
+
+
+@pytest.mark.parametrize("size", [0, -3, True, 10_000])
+def test_invalid_size_raises_value_error(size):
+    with pytest.raises(ValueError):
+        RENDERER.render(_canvas(6, 3), BW, _style(text="size", size=size))
+
+
+@pytest.mark.parametrize(("key", "value"), [("size_mode", "huge"), ("weight_mode", "bold")])
+def test_unknown_modes_raise_value_error_naming_the_choices(key, value):
+    with pytest.raises(ValueError) as excinfo:
+        RENDERER.render(_canvas(6, 3), BW, _style(text="mode", **{key: value}))
+    assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)
+
+
+@pytest.mark.parametrize(("key", "value"), [("kerning", -0.5), ("kerning", 2.5),
+                                            ("line_distance", 0.0), ("line_distance", -1.0)])
+def test_out_of_range_numbers_raise_value_error(key, value):
+    with pytest.raises(ValueError):
+        RENDERER.render(_canvas(6, 3), BW, _style(text="numbers", **{key: value}))
+
+
+@pytest.mark.parametrize("colour", ["not-a-colour", "#12345", "#gggggg", 12])
+def test_invalid_colours_raise_value_error(colour):
+    with pytest.raises(ValueError):
+        RENDERER.render(_canvas(6, 3), BW, _style(text="colours", fg=colour))
+
+
+def test_unknown_style_keys_are_ignored_for_forward_compatibility():
+    grid = _canvas(8, 4)
+    assert np.array_equal(_frame(grid, text="future"),
+                          _frame(grid, text="future", glow=0.7, shimmer=True))
+
+
+# --- §3 invariants ---
+
+
+def test_render_is_pure_and_does_not_mutate_grid_or_palette():
+    grid, palette = _canvas(12, 5), BW.copy()
+    style = _style(text="pure")
+    snapshot = [array.copy() for array in (grid.index, grid.coverage, grid.luma, grid.samples)]
+    first = np.asarray(RENDERER.render(grid, palette, style))
+    assert np.array_equal(first, np.asarray(RENDERER.render(grid, palette, style)))
+    for array, before in zip((grid.index, grid.coverage, grid.luma, grid.samples), snapshot,
+                             strict=True):
+        assert np.array_equal(array, before)
+    assert np.array_equal(palette, BW)
+
+
+def test_render_frame_matches_render():
+    grid = _canvas(12, 5)
+    frame = _frame(grid, text="consistent rasterisation")
+    expected = np.floor(np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
+    assert np.array_equal(_image(grid, text="consistent rasterisation"), expected)
+
+
+def test_the_renderer_is_registered_under_a_unique_stable_name():
+    renderer = TextRenderer()
+    assert renderer.name == "text"
+    assert get_renderer("text").name == "text"
+    assert list_renderers().count("text") == 1
+    assert isinstance(renderer, CellRenderer)
+
+
+def test_cell_aspect_subgrid_and_consumes():
+    assert RENDERER.cell_aspect() == 0.5
+    assert RENDERER.subgrid() == (1, 1)
+    assert RENDERER.consumes() == frozenset({"luma"})
+
+
+def test_style_options_round_trip_through_json():
+    options = {"text": "round trip", "font": None, "size": 12, "line_distance": 1.4,
+               "kerning": 0.5, "size_mode": "fixed", "weight_mode": "variable",
+               "fg": "#112233", "bg": "#ffeedd", "seed": 5}
+    style = _style(**options)
+    assert json.loads(json.dumps(dict(style.options))) == options
+    grid = _canvas(10, 4)
+    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
+    assert np.array_equal(np.asarray(RENDERER.render(grid, BW, style)),
+                          np.asarray(RENDERER.render(grid, BW, reloaded)))
+
+
+def test_layout_accepts_both_call_forms():
+    grid, style = _canvas(8, 4), _style(text="both forms")
+    assert RENDERER.layout(grid, style) == RENDERER.layout(grid, BW, style)
+
+
+def test_cached_masks_are_read_only_and_the_cache_is_bounded():
+    text_module._mask.cache_clear()
+    mask, _, _ = text_module._mask((None, 0, 0), "M", 12, 0)
+    assert not mask.flags.writeable
+    with pytest.raises(ValueError):
+        mask[0, 0] = 1.0
+    for size in range(4, 20):
+        text_module._mask((None, 0, 0), "M", size, 0)
+    info = text_module._mask.cache_info()
+    assert info.maxsize is not None and info.currsize <= info.maxsize
+
+
+def test_a_grid_whose_luma_shape_does_not_match_raises_value_error():
+    grid = _canvas(6, 3)
+    broken = CellGrid(cols=6, rows=3, cell_w=CELL_W, cell_h=CELL_H, index=grid.index,
+                      coverage=grid.coverage, luma=grid.luma[:, :4], samples=grid.samples)
+    with pytest.raises(ValueError) as excinfo:
+        RENDERER.layout(broken, _style(text="shape"))
+    assert "luma" in str(excinfo.value)
+
+
+def test_an_empty_canvas_renders_nothing():
+    empty = CellGrid(cols=0, rows=0, cell_w=CELL_W, cell_h=CELL_H,
+                     index=np.zeros((0, 0), np.int32), coverage=np.zeros((0, 0), np.float32),
+                     luma=np.zeros((0, 0), np.float32), samples=np.zeros((0, 0, 1), np.float32))
+    assert RENDERER.layout(empty, _style(text="nothing")) == []
+    assert RENDERER.render(empty, BW, _style(text="nothing")).size == (0, 0)


CODER NOTES AND DEVIATIONS
- AUCUN. Le codeur a été tué par son timeout sans rendre de NOTES ni de DEVIATIONS. Les deux
  fichiers sont sur disque, verts, et n'ont jamais été relus. Traite l'absence de justification comme
  un risque en soi : si un choix est ambigu, dis-le plutôt que de le présumer voulu.
