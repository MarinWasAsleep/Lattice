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

CONTRACT EXCERPTS (version 0.1.0-draft)

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
    def consumes(self) -> frozenset[str]: ...  # subset of {"index", "luma", "samples"} (S2)
    def render(self, grid: CellGrid, palette: np.ndarray, style: RenderStyle) -> Image.Image: ...
```

Registry: `register_renderer`, `get_renderer(name)`, `list_renderers()`.

Normative invariants, each one a test:

1. `render` returns an image of exactly `(cols * cell_w, rows * cell_h)` pixels.
2. `render` is pure: identical inputs produce identical output, no module-level state.
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

## §5 Pipeline

Inherits Lattice Dither §13 (pre-dither conditioning) and its render order, with step 8 replaced by
the renderer call. The normative order becomes:

1. If `max_side`: area-downscale so `max(H, W) <= max_side`. Call this shape S.
2. Enabled pre-effects in order; effect i gets `default_rng(seed + i)`.
3. `auto_levels` if enabled.
4. `adjust(brightness, contrast, gamma, saturation)`.
5. `pre_blur` if > 0 (separable Gaussian, sigma = `pre_blur / 3`).
6. Compute grid geometry from `renderer.cell_aspect()` and `pixel_size`.
7. Downscale to the grid.
8. `resolve_palette` on the image from step 7.
9. Algorithm (params through `resolve_params`) → `index`.
10. Derive `coverage` and `samples` per §3.
11. `renderer.render(grid, palette, style)`.
12. Enabled post-effects in order; effect j gets `default_rng(seed + 1000 + j)`.

Steps 3, 4 and 5 must be no-ops at their defaults. Step 11 replaces the 1.0 `apply_palette` +
`upscale_nearest` pair; `PixelRenderer` reproduces that pair exactly.

**Continuous mode (S1, decided 2026-11-16).** The pipeline may run without quantisation:
`algorithm: null` and `palette: null` are legal. In that mode steps 8 and 9 are skipped,
`grid.luma`/`samples` are derived from the step-7 cells, the renderer must be `pixel` at
cell 1×1, and `grid.index` carries nearest-source pixels (a pass-through). Lattice Glitch is an
effect-graph app that consumes the core (seed, masks, presets, bridge, CLI) without depending on
the CellRenderer quantisation chain.

TASK CARD

### L6 · Glyph ramp renderer
- wave: 1 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/renderers/glyph_ramp.py`, `tests/test_glyph_ramp.py` +
  `lattice_core/renderers/__init__.py` (enregistrement : ajout DEV-208 — append atomique d'une
  ligne d'import via terminal, JAMAIS write_file sur ce fichier, ne toucher qu'à VOTRE ligne)
- context: §3 §9
- spec: implement `glyph_ramp` per §9. Options: `ramp`, `font`, `fg`, `bg`, `mode`
  (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset`, `invert` — **pas de `size`** :
  la taille de police est dérivée de `cell_h` (H11/Q4, §5-6). La rampe est indexée par `luma`
  (S2, indépendante de la palette). The ramp contract is darkest-first and is documented, not
  detected. `offset` shifts the luma-to-glyph mapping and is animatable. Aspect correction uses
  `cell_aspect()`; default font ratio 1/2.
- accept:
  - a 10-character ramp on a black-to-white gradient produces 10 distinct glyphs in order.
  - une palette N&B ne réduit pas la rampe : les 10 caractères restent distincts (S2/H11).
  - `offset` shifts the mapping by exactly one glyph per 1/len(ramp) of coverage.
  - `invert` reverses the ramp.
  - `mode: "palette"` gives each glyph the palette colour of its cell.
  - `mode: "bg_colour"` puts the colour in the background and the glyph in `fg`.
  - output size is exactly `(cols * cell_w, rows * cell_h)`.
  - a missing font file raises `ValueError` naming the path.

GATE RESULTS (L6, attempt 2 — deepseek-v4-1-flash-1017)
- Owned tests : **49 passed** (40 → 49), ruff clean. Suite complète : **1603 passed,
  1 skipped, 0 failed**.
- Mutation testing du codeur : 16 mutations injectées, **15 tuées** ; UNE survivante :
  `font_size_from_cell_w_only` (la dérivation de la taille de police ne dépend que de cell_w —
  aucun test ne la fige). À juger : réel trou de test ou non-significatif (§9 : font size ?
  cell_aspect 0.5 ; cell larges de 1×2 — la dérivation hauteur vs largeur a-t-elle un effet
  observable ?).
- Pass 1 (Sonnet) : FIX — caches module-level vs invariant 2, tests auto-référents, minors.

DISPOSITION PASS 1 (attempt 2)
- majeurs : 3 dicts module-level supprimés → lru_cache(maxsize=256) clé (chemin, mtime_ns,
  taille) ; masques write=False ; cache froid == chaud vérifié, currsize plafonne à 256 après
  780 entrées. Indexation sRGB CONSERVÉE (AMD-010, docstring _ramp_indices réécrite citant
  l'amendement : monotone, darkest-first préservé, indépendant de la palette).
- majeurs de test : _ramp_grid/_position_grid supprimés → séquences en littéraux
  (« @%#*+=-:. », tables d'offset 0.0→0.5) ; consumes == frozenset({"luma","index"}) ;
  layout testé contre une référence Pillow indépendante (canvas paddé).
- mineurs : layout() → GlyphPlacement (NamedTuple) avec fill ET paper (#rrggbbaa si
  translucide, transparent si nul) ; _font_key valide le chemin dans _read_options
  (ValueError précoce, y compris grille 0 cellule et layout()) ; test cover-cell durci
  (bbox d'encre indépendante + centrage horizontal ≤ 1 px).

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/renderers/glyph_ramp.py b/lattice_core/renderers/glyph_ramp.py
new file mode 100644
index 0000000..bf502b3
--- /dev/null
+++ b/lattice_core/renderers/glyph_ramp.py
@@ -0,0 +1,359 @@
+"""The GlyphRampRenderer: one monospace character per cell, indexed by luma (§9).
+
+The ramp contract is explicit and documented, never detected: darkest character first,
+lightest last. ``grid.luma`` (S2) picks the character through its sRGB-perceptual encoding
+(AMD-010), so a black/white palette still uses the full ramp. There is no ``size`` option
+(H11): the font size derives from ``cell_h``. Module state is one bounded, input-keyed glyph
+mask cache that never changes the output (§3 invariant 2, H11).
+"""
+
+from __future__ import annotations
+
+import math
+from dataclasses import dataclass
+from functools import lru_cache
+from pathlib import Path
+from typing import NamedTuple
+
+import numpy as np
+from PIL import Image as PILImage
+from PIL import ImageDraw, ImageFont
+
+from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
+from lattice_core.types import Palette
+
+NAME = "glyph_ramp"
+DEFAULT_RAMP = "@%#*+=-:. "
+CELL_ASPECT = 0.5
+MODES = ("mono", "fg_colour", "bg_colour", "palette")
+DEFAULT_FG = "#000000"
+DEFAULT_BG = "#ffffff"
+TRANSPARENT = "transparent"
+_EPSILON = 1e-6
+_PROBE_SIZE = 100
+_HEX_DIGITS = frozenset("0123456789abcdef")
+_MASK_CACHE_SIZE = 256
+
+
+@dataclass(frozen=True)
+class GlyphRampOptions:
+    """Validated options of one glyph_ramp render (§9); there is no size option (H11)."""
+
+    ramp: str = DEFAULT_RAMP
+    font: str | None = None
+    fg: str = DEFAULT_FG
+    bg: str = DEFAULT_BG
+    mode: str = "mono"
+    offset: float = 0.0
+    invert: bool = False
+
+
+class GlyphPlacement(NamedTuple):
+    """One placed glyph: §3's six fields, plus the paper colour the cell was drawn on."""
+
+    character: str
+    x: float
+    y: float
+    width: float
+    height: float
+    fill: str
+    paper: str
+
+
+class GlyphRampRenderer:
+    """Draw one monospace character per cell, its ink density chosen by the cell luma."""
+
+    name = NAME
+
+    def cell_aspect(self) -> float:
+        """Return 0.5: the default monospace font ratio, width over height (§9)."""
+        return CELL_ASPECT
+
+    def subgrid(self) -> tuple[int, int]:
+        """Return (1, 1): one glyph covers the whole cell, with no sub-points."""
+        return (1, 1)
+
+    def consumes(self) -> frozenset[str]:
+        """Return {"luma", "index"}: luma picks the glyph, index the palette colour."""
+        return frozenset({"luma", "index"})
+
+    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
+        """Rasterise the glyph ramp of grid into an image of the exact grid geometry.
+
+        The image is RGBA when a colour option is ``transparent``, RGB otherwise.
+        """
+        frame = _frame(grid, palette, _read_options(style))
+        pixels = color.to_rgb8(frame)
+        return PILImage.fromarray(pixels, "RGBA" if frame.shape[2] == 4 else "RGB")
+
+    def layout(
+        self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
+    ) -> list[GlyphPlacement]:
+        """Return one placed glyph per cell, row-major (§3, §11).
+
+        ``fill`` is the ink colour and ``paper`` the background colour of the cell; either is
+        ``#rrggbbaa`` when translucent and ``transparent`` when fully clear, so an export can
+        reproduce a ``bg_colour`` or transparent render. Both the §3 ``layout(grid, style)``
+        form and the ``layout(grid, palette, style)`` form the other glyph renderers use are
+        accepted; the palette only feeds the palette modes.
+        """
+        palette, style = _layout_arguments(palette, style)
+        options = _read_options(style)
+        indices = _ramp_indices(grid.luma, len(options.ramp), options.offset, options.invert)
+        ink, paper = _cell_colours(options, grid, palette)
+        placed: list[GlyphPlacement] = []
+        for row in range(grid.rows):
+            for col in range(grid.cols):
+                placed.append(GlyphPlacement(
+                    options.ramp[int(indices[row, col])],
+                    float(col * grid.cell_w), float(row * grid.cell_h),
+                    float(grid.cell_w), float(grid.cell_h),
+                    _hex(ink[row, col]), _hex(paper[row, col]),
+                ))
+        return placed
+
+
+def _layout_arguments(
+    palette: Palette | None, style: RenderStyle | None
+) -> tuple[Palette | None, RenderStyle]:
+    """Disambiguate layout()'s two call forms: (grid, style) and (grid, palette, style)."""
+    if isinstance(palette, RenderStyle):
+        return None, palette
+    if style is None:
+        raise TypeError("layout() needs a RenderStyle: layout(grid, style)")
+    return palette, style
+
+
+def _read_options(style: RenderStyle) -> GlyphRampOptions:
+    """Validate style.options and return the typed options of one glyph_ramp render.
+
+    Unknown keys are ignored, so a preset written by a newer app still renders (§6).
+    """
+    raw = dict(style.options)
+    ramp = raw.get("ramp", DEFAULT_RAMP)
+    if not isinstance(ramp, str) or not ramp:
+        raise ValueError(f"glyph_ramp ramp must be a non-empty string, got {ramp!r}")
+    mode = raw.get("mode", "mono")
+    if mode not in MODES:
+        raise ValueError(f"glyph_ramp mode must be one of {MODES}, got {mode!r}")
+    font = raw.get("font")
+    if font is not None and not isinstance(font, str):
+        raise ValueError(f"glyph_ramp font must be a path string or null, got {font!r}")
+    _font_key(font)  # ValueError naming the path, before anything is drawn or laid out
+    offset = raw.get("offset", 0.0)
+    if isinstance(offset, bool) or not isinstance(offset, (int, float)):
+        raise ValueError(f"glyph_ramp offset must be a number, got {offset!r}")
+    if not math.isfinite(float(offset)):
+        raise ValueError(f"glyph_ramp offset must be finite, got {offset!r}")
+    invert = raw.get("invert", False)
+    if not isinstance(invert, bool):
+        raise ValueError(f"glyph_ramp invert must be a boolean, got {invert!r}")
+    return GlyphRampOptions(
+        ramp=ramp,
+        font=font,
+        fg=_colour_option(raw, "fg", DEFAULT_FG),
+        bg=_colour_option(raw, "bg", DEFAULT_BG),
+        mode=mode,
+        offset=float(offset),
+        invert=invert,
+    )
+
+
+def _colour_option(raw: dict, key: str, default: str) -> str:
+    """Return one colour option as text, validating it before any drawing happens."""
+    value = raw.get(key, default)
+    if not isinstance(value, str):
+        raise ValueError(f"glyph_ramp {key} must be a colour string, got {value!r}")
+    _parse_colour(value)
+    return value
+
+
+def _parse_colour(value: str) -> tuple[float, float, float, float]:
+    """Parse "#rrggbb", "#rrggbbaa" or "transparent" into RGBA floats in [0, 1]."""
+    text = str(value).strip().lower()
+    if text == TRANSPARENT:
+        return (0.0, 0.0, 0.0, 0.0)
+    digits = text.lstrip("#")
+    if len(digits) not in (6, 8) or not _HEX_DIGITS.issuperset(digits):
+        raise ValueError(
+            f"glyph_ramp colour must be #rrggbb, #rrggbbaa or 'transparent', got {value!r}"
+        )
+    red, green, blue = (int(digits[at : at + 2], 16) / 255.0 for at in (0, 2, 4))
+    alpha = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
+    return (red, green, blue, alpha)
+
+
+def _hex(rgba: np.ndarray) -> str:
+    """Format one RGBA float row as "#rrggbb", "#rrggbbaa" or "transparent"."""
+    alpha = int(round(float(rgba[3]) * 255.0))
+    if alpha <= 0:
+        return TRANSPARENT
+    red, green, blue = (int(round(float(value) * 255.0)) for value in rgba[:3])
+    if alpha >= 255:
+        return f"#{red:02x}{green:02x}{blue:02x}"
+    return f"#{red:02x}{green:02x}{blue:02x}{alpha:02x}"
+
+
+def _font_key(path: str | None) -> tuple[str | None, int, int]:
+    """Return the cache key of a font: its path plus the file's mtime and size.
+
+    The mtime and size make a font replaced at the same path a different key, so a cached
+    mask can never outlive the file it was drawn from (§3 invariant 2). A path that is not
+    an existing file raises ValueError naming it, before anything is drawn or laid out.
+    """
+    if path is None:
+        return (None, 0, 0)
+    target = Path(path)
+    if not target.is_file():
+        raise ValueError(f"glyph_ramp font file not found: {path}")
+    info = target.stat()
+    return (path, info.st_mtime_ns, info.st_size)
+
+
+def _load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
+    """Load the font at path at size, or Pillow's bundled default when path is None."""
+    if path is None:
+        return ImageFont.load_default(size=size)
+    try:
+        return ImageFont.truetype(path, size)
+    except OSError as exc:
+        raise ValueError(f"glyph_ramp font file is not a usable font: {path}") from exc
+
+
+@lru_cache(maxsize=_MASK_CACHE_SIZE)
+def _metrics(font_key: tuple[str | None, int, int]) -> tuple[float, float]:
+    """Return the (line height, advance width) per point of the font, cached per font."""
+    font = _load_font(font_key[0], _PROBE_SIZE)
+    ascent, descent = font.getmetrics()
+    return ((ascent + descent) / _PROBE_SIZE, float(font.getlength("M")) / _PROBE_SIZE)
+
+
+def _font_size(cell_w: int, cell_h: int, path: str | None) -> int:
+    """Return the point size whose advance and line height both fit one cell."""
+    height_ratio, advance_ratio = _metrics(_font_key(path))
+    by_height = cell_h / height_ratio if height_ratio > 0.0 else float(cell_h)
+    by_width = cell_w / advance_ratio if advance_ratio > 0.0 else float(cell_w)
+    return max(1, int(round(min(by_height, by_width))))
+
+
+def _glyph_mask(char: str, path: str | None, cell_w: int, cell_h: int) -> np.ndarray:
+    """Return the read-only (cell_h, cell_w) float32 ink mask of one centred glyph."""
+    return _cached_mask(_font_key(path), char, cell_w, cell_h)
+
+
+@lru_cache(maxsize=_MASK_CACHE_SIZE)
+def _cached_mask(
+    font_key: tuple[str | None, int, int], char: str, cell_w: int, cell_h: int
+) -> np.ndarray:
+    """Return the read-only ink mask of one glyph, cached per font identity and cell.
+
+    Every input is part of the key, the cache is bounded, and the returned array is not
+    writable, so no caller can observe or cause a change of the rendered output.
+    """
+    font = _load_font(font_key[0], _font_size(cell_w, cell_h, font_key[0]))
+    canvas = PILImage.new("L", (cell_w, cell_h), 0)
+    ImageDraw.Draw(canvas).text(
+        (cell_w / 2.0, cell_h / 2.0), char, font=font, fill=255, anchor="mm"
+    )
+    mask = np.asarray(canvas, dtype=np.float32) / 255.0
+    mask.setflags(write=False)
+    return mask
+
+
+def _ramp_indices(luma: np.ndarray, count: int, offset: float, invert: bool) -> np.ndarray:
+    """Return the ramp index of every cell: darkest first, shifted by offset, inverted.
+
+    ``luma`` is linear light (S2) and indexes the ramp through its sRGB-perceptual encoding
+    (AMD-010): the re-encoding is monotonic, so darkest-first order is preserved and the
+    ordered ramp stays perceptually spaced — a black-to-white source gradient walks the whole
+    ramp instead of collapsing into its dark third. One unit of ``offset`` moves one glyph.
+    """
+    position = color.linear_to_srgb(np.asarray(luma, dtype=np.float32))
+    scaled = (position + np.float32(offset)) * np.float32(count)
+    index = np.clip(np.floor(scaled + np.float32(_EPSILON)).astype(np.intp), 0, count - 1)
+    return (count - 1 - index) if invert else index
+
+
+def _palette_colours(grid: CellGrid, palette: Palette) -> np.ndarray:
+    """Return the (rows, cols, 4) opaque palette colour of every cell."""
+    rgb = np.asarray(palette, dtype=np.float32)[np.asarray(grid.index, dtype=np.intp), :3]
+    alpha = np.ones(rgb.shape[:2] + (1,), dtype=np.float32)
+    return np.concatenate([rgb, alpha], axis=-1)
+
+
+def _darkest(palette: Palette) -> np.ndarray:
+    """Return the RGBA colour of the palette entry with the lowest linear luminance."""
+    linear = color.srgb_to_linear(np.asarray(palette, dtype=np.float32)[:, :3])
+    luma = np.float32(0.2126) * linear[:, 0] + np.float32(0.7152) * linear[:, 1]
+    luma = luma + np.float32(0.0722) * linear[:, 2]
+    row = np.asarray(palette, dtype=np.float32)[int(np.argmin(luma)), :3]
+    return np.concatenate([row, np.ones(1, dtype=np.float32)])
+
+
+def _cell_colours(
+    options: GlyphRampOptions, grid: CellGrid, palette: np.ndarray | None
+) -> tuple[np.ndarray, np.ndarray]:
+    """Return the (rows, cols, 4) ink and paper colours of every cell for the chosen mode.
+
+    ``mono`` uses fg on bg; ``fg_colour`` puts the cell palette colour in the ink and bg in
+    the paper; ``bg_colour`` the reverse; ``palette`` takes the ink from the cell and the
+    paper from the palette's darkest entry, so both come from the palette.
+    """
+    shape = (grid.rows, grid.cols, 4)
+    ink = np.broadcast_to(np.asarray(_parse_colour(options.fg), np.float32), shape).copy()
+    paper = np.broadcast_to(np.asarray(_parse_colour(options.bg), np.float32), shape).copy()
+    if options.mode == "mono" or palette is None:
+        return ink, paper
+    cells = _palette_colours(grid, palette)
+    if options.mode == "fg_colour":
+        return cells, paper
+    if options.mode == "bg_colour":
+        return ink, cells
+    return cells, np.broadcast_to(_darkest(palette), shape).copy()
+
+
+def _blend(paper: np.ndarray, ink: np.ndarray, mask: np.ndarray) -> np.ndarray:
+    """Composite glyph ink over paper with straight alpha; mask is (cell_h, cell_w)."""
+    weight = mask[None, :, :, None]
+    ink_weight = ink[:, None, None, 3:4] * weight
+    paper_weight = paper[:, None, None, 3:4] * (1.0 - weight)
+    alpha = ink_weight + paper_weight
+    rgb = ink[:, None, None, :3] * ink_weight + paper[:, None, None, :3] * paper_weight
+    return np.concatenate([rgb / np.maximum(alpha, np.float32(_EPSILON)), alpha], axis=-1)
+
+
+def _groups(indices: np.ndarray, count: int) -> list[np.ndarray]:
+    """Return, per ramp value, the flat cell positions that carry it (one stable sort)."""
+    flat = np.asarray(indices, dtype=np.intp).ravel()
+    order = np.argsort(flat, kind="stable")
+    bounds = np.searchsorted(flat[order], np.arange(count + 1))
+    return [order[bounds[value] : bounds[value + 1]] for value in range(count)]
+
+
+def _frame(grid: CellGrid, palette: Palette, options: GlyphRampOptions) -> np.ndarray:
+    """Return the (rows*cell_h, cols*cell_w, C) float32 frame of one glyph_ramp render."""
+    count = len(options.ramp)
+    indices = _ramp_indices(grid.luma, count, options.offset, options.invert)
+    ink, paper = _cell_colours(options, grid, palette)
+    alpha = bool(ink[:, :, 3].min() < 1.0 or paper[:, :, 3].min() < 1.0)
+    frame = np.empty((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 4), dtype=np.float32)
+    view = frame.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w, 4)
+    view[...] = paper[:, None, :, None, :]
+    for value, cells in enumerate(_groups(indices, count)):
+        if cells.size == 0:
+            continue
+        rows, cols = np.divmod(cells, grid.cols)
+        mask = _glyph_mask(options.ramp[value], options.font, grid.cell_w, grid.cell_h)
+        view[rows, :, cols, :, :] = _blend(paper[rows, cols], ink[rows, cols], mask)
+    if alpha:
+        return frame
+    return np.ascontiguousarray(frame[:, :, :3])
+
+
+def register_glyph_ramp_renderer() -> CellRenderer:
+    """Register the GlyphRampRenderer under "glyph_ramp" and return it."""
+    return register_renderer(GlyphRampRenderer())
+
+
+register_glyph_ramp_renderer()
diff --git a/tests/test_glyph_ramp.py b/tests/test_glyph_ramp.py
new file mode 100644
index 0000000..30859bb
--- /dev/null
+++ b/tests/test_glyph_ramp.py
@@ -0,0 +1,547 @@
+"""Tests for the glyph_ramp renderer (§3, §9, AMD-010) — card L6.
+
+Expected glyph sequences are pinned as literals derived from the contract, never recomputed
+with the renderer's own formula: §9 + AMD-010 say ``luma`` indexes the ramp through its
+sRGB-perceptual encoding, so a linear luma of 0.05 encodes to sRGB 0.2478, lands in bucket 2
+of a 10-character ramp and must draw ``'#'``.
+"""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+from typing import cast
+
+import numpy as np
+import pytest
+from PIL import Image as PILImage
+from PIL import ImageDraw, ImageFont
+
+import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
+from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
+from lattice_core.pipeline import PipelineSpec, _make_grid, render_with_palette
+from lattice_core.renderers import glyph_ramp
+from lattice_core.renderers.glyph_ramp import (
+    DEFAULT_RAMP,
+    GlyphPlacement,
+    GlyphRampRenderer,
+    _font_size,
+    _glyph_mask,
+)
+from lattice_core.types import Palette
+
+RAMP = "@%#*+=-:. "
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
+CELL_W, CELL_H = 8, 16
+SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
+_PAD = 64
+
+
+def _srgb_grid(steps: int, palette: np.ndarray = BW) -> CellGrid:
+    """Return the grid the pipeline builds for a black-to-white sRGB gradient of steps cells."""
+    ramp = np.linspace(0.0, 1.0, steps, dtype=np.float32)[None, :, None]
+    cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
+    return _make_grid(cells, np.zeros((1, steps), np.int32), CELL_W, CELL_H, palette)
+
+
+def _linear_grid(
+    luma: list[float], index: list[int] | None = None,
+    cell_w: int = CELL_W, cell_h: int = CELL_H,
+) -> CellGrid:
+    """Return a one-row grid carrying the given literal linear luma values (S2)."""
+    values = np.asarray(luma, dtype=np.float32)[None, :]
+    cells = np.zeros(values.shape, dtype=np.int32) if index is None else np.asarray(
+        index, dtype=np.int32
+    )[None, :]
+    return CellGrid(
+        cols=values.shape[1], rows=1, cell_w=cell_w, cell_h=cell_h,
+        index=np.ascontiguousarray(cells), coverage=values.copy(), luma=values.copy(),
+        samples=np.ascontiguousarray(values[:, :, None]),
+    )
+
+
+def _style(**options: object) -> RenderStyle:
+    """Return a RenderStyle carrying the given glyph_ramp options."""
+    return RenderStyle(options=dict(options))
+
+
+def _chars(grid: CellGrid, palette: np.ndarray = BW, **options: object) -> str:
+    """Return the glyph characters layout() places, row-major, as one string."""
+    return "".join(entry.character for entry in GlyphRampRenderer().layout(
+        grid, palette, _style(**options)
+    ))
+
+
+def _cells(img) -> np.ndarray:
+    """Return the rendered image as a (rows, cols, cell_h, cell_w, 3) uint8 array."""
+    array = np.asarray(img)
+    rows, cols = array.shape[0] // CELL_H, array.shape[1] // CELL_W
+    return array.reshape(rows, CELL_H, cols, CELL_W, 3).transpose(0, 2, 1, 3, 4)
+
+
+def _pillow_ink(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
+    """Draw glyph with Pillow alone, centred in a cell, and return its float32 ink in [0, 1].
+
+    This is an independent reference: it shares no code with the renderer, so a change that
+    moves both the renderer and its own mask helper still fails here.
+    """
+    font = _default_font(size)
+    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
+    ImageDraw.Draw(canvas).text(
+        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
+    )
+    patch = np.asarray(canvas, dtype=np.float32)[_PAD : _PAD + cell_h, _PAD : _PAD + cell_w]
+    return np.ascontiguousarray(patch / 255.0)
+
+
+def _pillow_cell(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
+    """Return the uint8 grey cell Pillow draws for glyph: ink on white paper."""
+    return np.floor((1.0 - _pillow_ink(glyph, cell_w, cell_h, size)) * 255.0 + 0.5).astype(
+        np.uint8
+    )
+
+
+def _matching_pillow_sizes(glyph: str, cell_w: int, cell_h: int, target: np.ndarray) -> list[int]:
+    """Return every Pillow font size whose independently drawn cell equals target."""
+    return [size for size in range(1, 4 * max(cell_w, cell_h))
+            if np.array_equal(_pillow_cell(glyph, cell_w, cell_h, size), target)]
+
+
+def _pillow_ink_bbox(glyph: str, cell_w: int, cell_h: int, size: int) -> tuple[int, int, int, int]:
+    """Return the unclipped (top, bottom, left, right) ink box of glyph, relative to the cell."""
+    font = ImageFont.load_default(size=size)
+    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
+    ImageDraw.Draw(canvas).text(
+        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
+    )
+    rows, cols = np.nonzero(np.asarray(canvas) > 0)
+    return (int(rows.min()) - _PAD, int(rows.max()) - _PAD,
+            int(cols.min()) - _PAD, int(cols.max()) - _PAD)
+
+
+def _default_font(size: int) -> ImageFont.FreeTypeFont:
+    """Return Pillow's bundled default font at size, typed as the FreeType font it is."""
+    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))
+
+
+# --- accept 1: a 10-character ramp on a black-to-white gradient ---
+
+
+def test_ten_character_ramp_on_a_gradient_places_the_ramp_in_order():
+    assert _chars(_srgb_grid(10), ramp=RAMP) == "@%#*+=-:. "
+    assert len(set(_chars(_srgb_grid(10), ramp=RAMP))) == 10
+
+
+def test_five_step_gradient_pins_the_contract_buckets():
+    ramp = np.linspace(0.0, 1.0, 5, dtype=np.float32)[None, :, None]
+    cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
+    grid = _make_grid(cells, np.zeros((1, 5), np.int32), CELL_W, CELL_H, BW)
+    assert _chars(grid, ramp=RAMP) == "@#=: "
+
+
+def test_ten_character_ramp_renders_ten_distinct_cells():
+    cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
+    assert len({cells[0, col].tobytes() for col in range(10)}) == 10
+
+
+def test_glyph_ink_decreases_as_the_cell_luma_rises():
+    cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
+    ink = [float(cells[0, col].mean()) for col in range(10)]
+    assert ink[0] < ink[-1]
+    assert ink[0] == min(ink) and ink[-1] == max(ink)
+
+
+# --- accept 2: a black/white palette does not collapse the ramp (S2/H11) ---
+
+
+def test_black_and_white_palette_keeps_all_ten_glyphs():
+    assert len(set(_chars(_srgb_grid(10, BW), BW, ramp=RAMP))) == 10
+
+
+def test_glyph_choice_is_independent_of_the_palette():
+    grid = _srgb_grid(10)
+    assert _chars(grid, BW, ramp=RAMP) == _chars(grid, COLOUR, ramp=RAMP)
+
+
+def test_consumes_is_exactly_luma_and_index():
+    assert GlyphRampRenderer().consumes() == frozenset({"luma", "index"})
+
+
+# --- accept 3: offset shifts the mapping by exactly one glyph per 1/len(ramp) ---
+
+# Literal linear luma values, darkest to lightest; the glyphs they must draw are pinned in
+# the tests below rather than derived from the renderer's own arithmetic.
+_LUMAS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
+_PLAIN = "@#*+=:.  "
+
+
+def test_offset_zero_draws_the_pinned_ramp_positions():
+    assert _chars(_linear_grid(_LUMAS), ramp=RAMP) == _PLAIN
+
+
+def test_offset_shifts_the_mapping_by_exactly_one_glyph():
+    grid = _linear_grid(_LUMAS)
+    assert _chars(grid, ramp=RAMP, offset=1 / len(RAMP)) == "%*+=-.   "
+    assert _chars(grid, ramp=RAMP, offset=2 / len(RAMP)) == "#+=-:    "
+
+
+def test_offset_is_measured_in_ramp_units_not_pixels():
+    grid = _linear_grid(_LUMAS)
+    pinned = {
+        0.0: "@#*+=:.  ",
+        0.1: "%*+=-.   ",
+        0.2: "#+=-:    ",
+        0.3: "*=-:.    ",
+        0.4: "+-:.     ",
+        0.5: "=:.      ",
+    }
+    for offset, expected in pinned.items():
+        assert _chars(grid, ramp=RAMP, offset=offset) == expected
+
+
+def test_offset_is_clamped_at_both_ends():
+    grid = _linear_grid([0.0, 0.3, 0.7, 1.0])
+    assert _chars(grid, ramp=RAMP, offset=-5.0) == "@@@@"
+    assert _chars(grid, ramp=RAMP, offset=5.0) == "    "
+
+
+def test_a_fractional_offset_shimmers_without_changing_the_grid():
+    grid = _linear_grid([0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95])
+    first = _chars(grid, ramp=RAMP)
+    assert first != _chars(grid, ramp=RAMP, offset=0.05)
+    assert _chars(grid, ramp=RAMP) == first
+
+
+# --- accept 4: invert reverses the ramp ---
+
+
+def test_invert_reverses_the_ramp():
+    grid = _linear_grid(_LUMAS)
+    assert _chars(grid, ramp=RAMP, invert=True) == " :-=+#%@@"
+    assert _chars(_srgb_grid(10), ramp=RAMP, invert=True) == " .:-=+*#%@"
+
+
+def test_invert_and_offset_compose():
+    grid = _linear_grid(_LUMAS)
+    assert _chars(grid, ramp=RAMP, offset=0.1, invert=True) == ".-=+*%@@@"
+
+
+# --- accept 5: mode "palette" gives each glyph the palette colour of its cell ---
+
+
+def test_palette_mode_gives_each_glyph_its_cell_palette_colour():
+    grid = _linear_grid([0.05, 0.05], index=[1, 2])
+    cells = _cells(GlyphRampRenderer().render(grid, COLOUR, _style(ramp=RAMP, mode="palette")))
+    red, blue = cells[0, 0].reshape(-1, 3), cells[0, 1].reshape(-1, 3)
+    assert red[:, 0].max() > 0 and red[:, 1].max() == 0 and red[:, 2].max() == 0
+    assert blue[:, 2].max() > 0 and blue[:, 0].max() == 0 and blue[:, 1].max() == 0
+
+
+def test_palette_mode_fill_is_the_cell_palette_colour():
+    grid = _linear_grid([0.05, 0.05], index=[1, 2])
+    placed = GlyphRampRenderer().layout(grid, COLOUR, _style(mode="palette"))
+    assert [entry.fill for entry in placed] == ["#ff0000", "#0000ff"]
+
+
+def test_fg_colour_mode_takes_the_ink_from_the_palette_and_the_paper_from_bg():
+    grid = _linear_grid([0.05], index=[1])
+    style = _style(ramp=RAMP, mode="fg_colour", bg="#00ff00")
+    flat = _cells(GlyphRampRenderer().render(grid, COLOUR, style))[0, 0].reshape(-1, 3)
+    assert flat[:, 0].max() > 0 and flat[:, 2].max() == 0
+    assert flat[:, 1].max() == 255 and flat[:, 0].max() < 255
+
+
+# --- accept 6: mode "bg_colour" puts the colour in the background ---
+
+
+def test_bg_colour_mode_puts_the_palette_colour_in_the_background():
+    grid = _linear_grid([0.05], index=[1])
+    style = _style(ramp=RAMP, mode="bg_colour", fg="#00ff00")
+    img = GlyphRampRenderer().render(grid, COLOUR, style)
+    glyph = GlyphRampRenderer().layout(grid, COLOUR, style)[0].character
+    pixels = np.asarray(img).reshape(-1, 3)
+    mask = _glyph_mask(glyph, None, CELL_W, CELL_H).reshape(-1)
+    assert np.all(pixels[mask <= 0.0] == np.array([255, 0, 0], dtype=np.uint8))
+    darkest = pixels[int(np.argmax(mask))]
+    assert darkest[1] > darkest[0] and darkest[2] == 0
+
+
+def test_bg_colour_mode_keeps_the_glyph_in_fg():
+    grid = _linear_grid([0.05], index=[1])
+    style = _style(ramp=RAMP, mode="bg_colour", fg="#00ff00")
+    pixels = np.asarray(GlyphRampRenderer().render(grid, COLOUR, style))
+    glyph = GlyphRampRenderer().layout(grid, COLOUR, style)[0].character
+    mask = _glyph_mask(glyph, None, CELL_W, CELL_H)
+    assert np.allclose(pixels[mask > 0.99], np.array([0, 255, 0]), atol=1)
+
+
+# --- accept 7: output size is exactly (cols * cell_w, rows * cell_h) ---
+
+
+@pytest.mark.parametrize(("rows", "cols", "cell_w", "cell_h"), [(3, 4, 8, 16), (1, 1, 5, 7)])
+def test_output_size_is_exactly_the_grid_geometry(rows, cols, cell_w, cell_h):
+    luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
+    grid = CellGrid(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
+                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma,
+                    samples=luma[:, :, None].copy())
+    expected = (cols * cell_w, rows * cell_h)
+    assert GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)).size == expected
+
+
+def test_output_size_matches_the_pipeline_geometry():
+    src = np.linspace(0.0, 1.0, 64 * 96, dtype=np.float32).reshape(64, 96, 1)
+    src = np.ascontiguousarray(np.repeat(src, 3, axis=2))
+    spec = PipelineSpec(pixel_size=8, renderer="glyph_ramp", renderer_style={"ramp": RAMP})
+    out = render_with_palette(src, spec, BW)
+    assert out.shape == (64, 96, 3)
+    assert out.dtype == np.uint8
+
+
+# --- accept 8: a missing font file raises ValueError naming the path ---
+
+
+def test_missing_font_file_raises_value_error_naming_the_path():
+    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
+    with pytest.raises(ValueError) as excinfo:
+        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, font=path))
+    assert path in str(excinfo.value)
+
+
+def test_missing_font_file_raises_from_layout_and_from_an_empty_grid():
+    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
+    style = _style(ramp=RAMP, font=path)
+    with pytest.raises(ValueError) as excinfo:
+        GlyphRampRenderer().layout(_srgb_grid(4), BW, style)
+    assert path in str(excinfo.value)
+    empty = CellGrid(cols=0, rows=0, cell_w=CELL_W, cell_h=CELL_H,
+                     index=np.zeros((0, 0), np.int32), coverage=np.zeros((0, 0), np.float32),
+                     luma=np.zeros((0, 0), np.float32), samples=np.zeros((0, 0, 1), np.float32))
+    with pytest.raises(ValueError) as excinfo:
+        GlyphRampRenderer().render(empty, BW, style)
+    assert path in str(excinfo.value)
+
+
+def test_font_option_accepts_a_real_font_file():
+    if not SYSTEM_FONT.is_file():
+        pytest.skip("no system TrueType font available")
+    img = GlyphRampRenderer().render(
+        _srgb_grid(4), BW, _style(ramp=RAMP, font=str(SYSTEM_FONT))
+    )
+    assert img.size == (4 * CELL_W, CELL_H)
+
+
+# --- §3 invariants ---
+
+
+def test_render_is_pure():
+    grid = _srgb_grid(10)
+    renderer = GlyphRampRenderer()
+    assert np.array_equal(
+        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
+        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
+    )
+
+
+def test_render_does_not_mutate_grid_or_palette():
+    grid = _srgb_grid(10)
+    palette = BW.copy()
+    snapshot = (grid.index.copy(), grid.luma.copy(), grid.samples.copy(), grid.coverage.copy())
+    GlyphRampRenderer().render(grid, palette, _style(ramp=RAMP, mode="palette"))
+    assert np.array_equal(grid.index, snapshot[0])
+    assert np.array_equal(grid.luma, snapshot[1])
+    assert np.array_equal(grid.samples, snapshot[2])
+    assert np.array_equal(grid.coverage, snapshot[3])
+    assert np.array_equal(palette, BW)
+
+
+def test_module_state_is_a_bounded_input_keyed_cache():
+    cache = glyph_ramp._cached_mask
+    cache.cache_clear()
+    for cell_w in range(1, 24):
+        for cell_h in (cell_w * 2, cell_w * 2 + 1):
+            for glyph in RAMP:
+                glyph_ramp._glyph_mask(glyph, None, cell_w, cell_h)
+    info = cache.cache_info()
+    assert info.maxsize is not None and info.currsize <= info.maxsize
+    assert info.currsize < 24 * 2 * len(RAMP)
+
+
+def test_cached_masks_are_read_only():
+    mask = glyph_ramp._glyph_mask("@", None, CELL_W, CELL_H)
+    assert not mask.flags.writeable
+    with pytest.raises(ValueError):
+        mask[0, 0] = 1.0
+
+
+def test_a_font_replaced_at_the_same_path_is_a_new_cache_key(tmp_path):
+    if not SYSTEM_FONT.is_file():
+        pytest.skip("no system TrueType font available")
+    copied = tmp_path / "font.ttf"
+    copied.write_bytes(SYSTEM_FONT.read_bytes())
+    first = glyph_ramp._font_key(str(copied))
+    glyph_ramp._glyph_mask("M", str(copied), CELL_W, CELL_H)
+    copied.write_bytes(SYSTEM_FONT.read_bytes() + b"\0")
+    assert glyph_ramp._font_key(str(copied)) != first
+
+
+def test_renderer_is_registered_under_a_unique_stable_name():
+    renderer = GlyphRampRenderer()
+    assert renderer.name == "glyph_ramp"
+    assert get_renderer("glyph_ramp").name == "glyph_ramp"
+    assert "glyph_ramp" in list_renderers()
+    assert isinstance(renderer, CellRenderer)
+
+
+def test_cell_aspect_is_the_monospace_ratio():
+    assert GlyphRampRenderer().cell_aspect() == 0.5
+    assert GlyphRampRenderer().subgrid() == (1, 1)
+
+
+def test_style_options_round_trip_through_the_renderer():
+    options = {"ramp": RAMP, "mode": "palette", "offset": 0.25, "invert": True,
+               "fg": "#112233", "bg": "transparent", "font": None}
+    grid, palette = _srgb_grid(6), COLOUR
+    style = _style(**options)
+    assert json.loads(json.dumps(dict(style.options))) == options
+    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
+    assert np.array_equal(
+        np.asarray(GlyphRampRenderer().render(grid, palette, style)),
+        np.asarray(GlyphRampRenderer().render(grid, palette, reloaded)),
+    )
+
+
+# --- layout() consistency with render() ---
+
+
+def test_layout_places_one_glyph_per_cell_row_major():
+    grid = _srgb_grid(10)
+    placed = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP))
+    assert len(placed) == grid.rows * grid.cols
+    assert all(isinstance(entry, GlyphPlacement) for entry in placed)
+    for col, entry in enumerate(placed):
+        assert entry.x == col * CELL_W and entry.y == 0.0
+        assert entry.width == CELL_W and entry.height == CELL_H
+
+
+def test_layout_accepts_both_call_forms():
+    grid, style = _srgb_grid(4), _style(ramp=RAMP)
+    assert GlyphRampRenderer().layout(grid, style) == GlyphRampRenderer().layout(grid, BW, style)
+
+
+def test_layout_character_is_the_glyph_pillow_rasterises():
+    grid = _srgb_grid(6)
+    renderer = GlyphRampRenderer()
+    placed = renderer.layout(grid, BW, _style(ramp=RAMP))
+    cells = _cells(renderer.render(grid, BW, _style(ramp=RAMP)))
+    sizes = set()
+    for col, entry in enumerate(placed):
+        if entry.character == " ":
+            continue
+        matches = _matching_pillow_sizes(entry.character, CELL_W, CELL_H, cells[0, col, :, :, 0])
+        assert matches, f"no Pillow size redraws {entry.character!r} as rendered"
+        sizes.update(matches)
+    assert len(sizes) == 1, f"the ramp is not drawn at one font size: {sorted(sizes)}"
+
+
+def test_layout_paper_matches_the_rendered_background():
+    grid = _linear_grid([0.05], index=[1])
+    style = _style(ramp=RAMP, mode="bg_colour", fg="#00ff00")
+    entry = GlyphRampRenderer().layout(grid, COLOUR, style)[0]
+    pixels = np.asarray(GlyphRampRenderer().render(grid, COLOUR, style)).reshape(-1, 3)
+    assert entry.fill == "#00ff00" and entry.paper == "#ff0000"
+    assert np.any(pixels == np.array([255, 0, 0], dtype=np.uint8))
+
+
+def test_layout_reports_alpha_and_transparent_paper():
+    grid = _linear_grid([0.05])
+    clear = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="transparent"))[0]
+    assert clear.paper == "transparent"
+    half = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="#ff000080"))[0]
+    assert half.paper == "#ff000080"
+
+
+# --- H11: no size option, font size derives from cell_h ---
+
+
+def test_there_is_no_size_option():
+    grid = _srgb_grid(6)
+    plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
+    with_size = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, size=48)))
+    assert np.array_equal(plain, with_size)
+
+
+def test_glyph_font_size_derives_from_the_cell():
+    pinned = {(8, 16): 9, (6, 12): 7, (12, 24): 14, (20, 40): 23, (10, 20): 11, (4, 8): 5}
+    for (cell_w, cell_h), size in pinned.items():
+        assert _font_size(cell_w, cell_h, None) == size
+        assert np.array_equal(
+            _glyph_mask("@", None, cell_w, cell_h), _pillow_ink("@", cell_w, cell_h, size)
+        )
+
+
+def test_glyph_ink_stays_inside_the_cell_and_is_horizontally_centred():
+    for cell_h in (12, 24, 40):
+        cell_w = cell_h // 2
+        mask = _glyph_mask("@", None, cell_w, cell_h)
+        assert mask.shape == (cell_h, cell_w)
+        size = _font_size(cell_w, cell_h, None)
+        top, bottom, left, right = _pillow_ink_bbox("@", cell_w, cell_h, size)
+        assert 0 <= top and bottom <= cell_h - 1 and 0 <= left and right <= cell_w - 1
+        assert abs((left + right) / 2.0 - (cell_w - 1) / 2.0) <= 1.0
+        rows, cols = np.nonzero(mask > 0.0)
+        assert rows.min() >= 0 and rows.max() <= cell_h - 1
+        assert cols.min() >= 0 and cols.max() <= cell_w - 1
+        assert 0.0 < float(mask.mean()) < 1.0
+
+
+def test_unknown_style_keys_are_ignored_for_forward_compatibility():
+    grid = _srgb_grid(6)
+    plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
+    future = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, glow=0.7)))
+    assert np.array_equal(plain, future)
+
+
+# --- option validation and edge cases ---
+
+
+def test_empty_ramp_raises_value_error():
+    with pytest.raises(ValueError):
+        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=""))
+
+
+def test_unknown_mode_raises_value_error_naming_the_modes():
+    with pytest.raises(ValueError) as excinfo:
+        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(mode="vibrant"))
+    assert "fg_colour" in str(excinfo.value)
+
+
+def test_invalid_colour_raises_value_error():
+    with pytest.raises(ValueError):
+        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(fg="not-a-colour"))
+
+
+def test_default_ramp_is_darkest_first_and_documented():
+    assert DEFAULT_RAMP[0] == "@"
+    assert DEFAULT_RAMP[-1] == " "
+    assert float(_glyph_mask(DEFAULT_RAMP[0], None, CELL_W, CELL_H).mean()) > 0.0
+
+
+def test_transparent_background_produces_an_rgba_image():
+    img = GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, bg="transparent"))
+    assert img.mode == "RGBA"
+    assert img.size == (4 * CELL_W, CELL_H)
+
+
+def test_flat_luma_collapses_to_a_single_glyph():
+    assert set(_chars(_linear_grid([0.0, 0.0, 0.0]), ramp=RAMP)) == {RAMP[0]}
+    assert set(_chars(_linear_grid([1.0, 1.0, 1.0]), ramp=RAMP)) == {RAMP[-1]}
+
+
+def test_luma_is_linear_light_not_srgb():
+    grid = _srgb_grid(10)
+    ramp = np.linspace(0.0, 1.0, 10, dtype=np.float32)[None, :, None]
+    linear = color.srgb_to_linear(np.ascontiguousarray(np.repeat(ramp, 3, axis=2)))[0]
+    expected = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
+    assert np.allclose(grid.luma[0], expected, atol=1e-6)

NOTES DU CODEUR (L6, attempt 2)
- Un run intermédiaire a échoué sur test_bitmask.py (édition concurrente L8 retry, en vol) ;
  les runs finaux sont verts, le fichier passe seul. Non causé par ce changement.
- Aucun écart E-déclaré ; contrat 0.1.0 + AMD-010 respectés à la lettre.
- test_style_options_round_trip_through_json (faible : json sur un dict) laissé tel quel,
  hors périmètre des findings.
