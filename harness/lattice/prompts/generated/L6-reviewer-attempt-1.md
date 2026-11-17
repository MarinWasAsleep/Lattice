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

GATE RESULTS (L6, attempt 1 — deepseek-v4-1-flash-1017)
- Owned tests : **40 passed** (test_glyph_ramp.py), ruff clean, check_contract OK.
- Suite complète au run final du codeur : **1521 passed, 1 skipped** (1474 + les 47 tests L8 ;
  le DEV-211 a rattaché le test registre pendant la passe).
- Registre courant : pixel, braille, sextant, quadrant, half_block (L8) + glyph_ramp (L6) ;
  G4 : append atomique UNE LIGNE dans renderers/__init__.py (DEV-208), ligne L8 intacte,
  ordre isort respecté (glyph_ramp après bitmask).

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/renderers/__init__.py b/lattice_core/renderers/__init__.py
index 9565523..97be679 100644
--- a/lattice_core/renderers/__init__.py
+++ b/lattice_core/renderers/__init__.py
@@ -26,3 +26,5 @@ __all__ = [
 ]
 
 register_pixel_renderer()
+from lattice_core.renderers.bitmask import register_bitmask_renderers  # noqa: E402, F401  (bitmask family self-registers on import; DEV-208 L8)
+from lattice_core.renderers.glyph_ramp import GlyphRampRenderer as GlyphRampRenderer  # noqa: E402
diff --git a/lattice_core/renderers/glyph_ramp.py b/lattice_core/renderers/glyph_ramp.py
new file mode 100644
index 0000000..8a90cfc
--- /dev/null
+++ b/lattice_core/renderers/glyph_ramp.py
@@ -0,0 +1,329 @@
+"""The GlyphRampRenderer: one monospace character per cell, indexed by luma (§9).
+
+The ramp contract is explicit and documented, never detected: darkest character first,
+lightest last. ``grid.luma`` (S2) picks the character, so a black/white palette still uses
+the full ramp. There is no ``size`` option (H11): the font size derives from ``cell_h``.
+"""
+
+from __future__ import annotations
+
+import math
+from dataclasses import dataclass
+from pathlib import Path
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
+
+_SIZED_FONTS: dict[tuple[str | None, int], ImageFont.FreeTypeFont] = {}
+_METRICS: dict[str | None, tuple[float, float]] = {}
+_MASKS: dict[tuple[str | None, str, int, int], np.ndarray] = {}
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
+    ) -> list[tuple]:
+        """Return one (character, x, y, width, height, fill) per cell, row-major (§3, §11).
+
+        Both the §3 ``layout(grid, style)`` and the ``layout(grid, palette, style)`` form the
+        other glyph renderers use are accepted; the palette only feeds the palette modes.
+        """
+        palette, style = _layout_arguments(palette, style)
+        options = _read_options(style)
+        indices = _ramp_indices(grid.luma, len(options.ramp), options.offset, options.invert)
+        ink = _cell_colours(options, grid, palette)[0]
+        placed: list[tuple] = []
+        for row in range(grid.rows):
+            for col in range(grid.cols):
+                placed.append((
+                    options.ramp[int(indices[row, col])],
+                    float(col * grid.cell_w), float(row * grid.cell_h),
+                    float(grid.cell_w), float(grid.cell_h),
+                    _hex(ink[row, col]),
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
+    """Format one RGBA float row as "#rrggbb", or "transparent" when fully transparent."""
+    if float(rgba[3]) <= 0.0:
+        return TRANSPARENT
+    red, green, blue = (int(round(float(value) * 255.0)) for value in rgba[:3])
+    return f"#{red:02x}{green:02x}{blue:02x}"
+
+
+def _load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
+    """Load the font at path at size, or Pillow's bundled default when path is None."""
+    if path is None:
+        return ImageFont.load_default(size=size)
+    if not Path(path).is_file():
+        raise ValueError(f"glyph_ramp font file not found: {path}")
+    try:
+        return ImageFont.truetype(path, size)
+    except OSError as exc:
+        raise ValueError(f"glyph_ramp font file is not a usable font: {path}") from exc
+
+
+def _sized_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
+    """Return the font at path loaded at size, cached per (path, size)."""
+    key = (path, size)
+    font = _SIZED_FONTS.get(key)
+    if font is None:
+        font = _load_font(path, size)
+        _SIZED_FONTS[key] = font
+    return font
+
+
+def _metrics(path: str | None) -> tuple[float, float]:
+    """Return the (line height, advance width) per point of the font, cached per font."""
+    cached = _METRICS.get(path)
+    if cached is None:
+        font = _sized_font(path, _PROBE_SIZE)
+        ascent, descent = font.getmetrics()
+        cached = ((ascent + descent) / _PROBE_SIZE, float(font.getlength("M")) / _PROBE_SIZE)
+        _METRICS[path] = cached
+    return cached
+
+
+def _font_size(cell_w: int, cell_h: int, path: str | None) -> int:
+    """Return the point size whose advance and line height both fit one cell."""
+    height_ratio, advance_ratio = _metrics(path)
+    by_height = cell_h / height_ratio if height_ratio > 0.0 else float(cell_h)
+    by_width = cell_w / advance_ratio if advance_ratio > 0.0 else float(cell_w)
+    return max(1, int(round(min(by_height, by_width))))
+
+
+def _glyph_mask(char: str, path: str | None, cell_w: int, cell_h: int) -> np.ndarray:
+    """Return the (cell_h, cell_w) float32 ink mask of one centred glyph, cached."""
+    key = (path, char, cell_w, cell_h)
+    cached = _MASKS.get(key)
+    if cached is not None:
+        return cached
+    font = _sized_font(path, _font_size(cell_w, cell_h, path))
+    canvas = PILImage.new("L", (cell_w, cell_h), 0)
+    ImageDraw.Draw(canvas).text(
+        (cell_w / 2.0, cell_h / 2.0), char, font=font, fill=255, anchor="mm"
+    )
+    mask = np.asarray(canvas, dtype=np.float32) / 255.0
+    _MASKS[key] = mask
+    return mask
+
+
+def _ramp_indices(luma: np.ndarray, count: int, offset: float, invert: bool) -> np.ndarray:
+    """Return the ramp index of every cell: darkest first, shifted by offset, inverted.
+
+    ``luma`` is linear light (S2); it is re-encoded to sRGB before it indexes the ramp so the
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
index 0000000..8a003ee
--- /dev/null
+++ b/tests/test_glyph_ramp.py
@@ -0,0 +1,400 @@
+"""Tests for the glyph_ramp renderer (§3, §9) — card L6."""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+import numpy as np
+import pytest
+
+import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
+from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
+from lattice_core.pipeline import PipelineSpec, _make_grid, render_with_palette
+from lattice_core.renderers.glyph_ramp import DEFAULT_RAMP, GlyphRampRenderer, _glyph_mask
+from lattice_core.types import Image, Palette
+
+RAMP = "@%#*+=-:. "
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
+CELL_W, CELL_H = 8, 16
+SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
+
+
+def _gradient_cells(steps: int) -> Image:
+    """Return a (1, steps, 3) row of sRGB values from black to white."""
+    ramp = np.linspace(0.0, 1.0, steps, dtype=np.float32)[None, :, None]
+    return np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
+
+
+def _gradient_grid(steps: int = 10, palette: Palette = BW) -> CellGrid:
+    """Return the grid the pipeline builds for a black-to-white gradient of steps cells."""
+    return _make_grid(_gradient_cells(steps), np.zeros((1, steps), np.int32), CELL_W, CELL_H,
+                      palette)
+
+
+def _grid(luma: np.ndarray, index: np.ndarray | None = None) -> CellGrid:
+    """Build a deterministic CellGrid from a (rows, cols) luma array."""
+    rows, cols = luma.shape
+    if index is None:
+        index = np.zeros((rows, cols), dtype=np.int32)
+    return CellGrid(
+        cols=cols, rows=rows, cell_w=CELL_W, cell_h=CELL_H,
+        index=np.ascontiguousarray(index, dtype=np.int32),
+        coverage=np.ascontiguousarray(luma, dtype=np.float32),
+        luma=np.ascontiguousarray(luma, dtype=np.float32),
+        samples=np.ascontiguousarray(luma[:, :, None], dtype=np.float32),
+    )
+
+
+def _position_grid(positions: list[float]) -> CellGrid:
+    """Return a grid whose cells sit at the given sRGB positions along the ramp."""
+    return _grid(color.srgb_to_linear(np.asarray(positions, dtype=np.float32))[None, :])
+
+
+def _ramp_grid(count: int) -> CellGrid:
+    """Return a grid whose cells sit exactly on the ramp buckets k/count, darkest first."""
+    return _position_grid([k / count for k in range(count)])
+
+
+def _style(**options: object) -> RenderStyle:
+    """Return a RenderStyle carrying the given glyph_ramp options."""
+    return RenderStyle(options=dict(options))
+
+
+def _cells(img) -> np.ndarray:
+    """Return the rendered image as a (rows, cols, cell_h, cell_w, 3) uint8 array."""
+    array = np.asarray(img)
+    rows, cols = array.shape[0] // CELL_H, array.shape[1] // CELL_W
+    return array.reshape(rows, CELL_H, cols, CELL_W, 3).transpose(0, 2, 1, 3, 4)
+
+
+def _chars(grid: CellGrid, palette: Palette = BW, **options: object) -> list[str]:
+    """Return the glyph characters layout() places, row-major."""
+    return [entry[0] for entry in GlyphRampRenderer().layout(grid, palette, _style(**options))]
+
+
+def _indices(grid: CellGrid, **options: object) -> list[int]:
+    """Return the ramp index of every placed glyph, row-major."""
+    return [RAMP.index(char) for char in _chars(grid, ramp=RAMP, **options)]
+
+
+# --- accept 1: a 10-character ramp on a black-to-white gradient ---
+
+
+def test_ten_character_ramp_produces_ten_distinct_glyphs_in_order():
+    grid = _gradient_grid(10)
+    chars = _chars(grid, ramp=RAMP)
+    assert chars == list(RAMP)
+    assert len(set(chars)) == 10
+
+
+def test_ten_character_ramp_renders_ten_distinct_cells():
+    cells = _cells(GlyphRampRenderer().render(_gradient_grid(10), BW, _style(ramp=RAMP)))
+    assert len({cells[0, col].tobytes() for col in range(10)}) == 10
+
+
+def test_glyph_ink_decreases_as_the_cell_luma_rises():
+    cells = _cells(GlyphRampRenderer().render(_gradient_grid(10), BW, _style(ramp=RAMP)))
+    ink = [float(cells[0, col].mean()) for col in range(10)]
+    assert ink[0] < ink[-1]
+    assert ink[0] == min(ink) and ink[-1] == max(ink)
+
+
+# --- accept 2: a black/white palette does not collapse the ramp (S2/H11) ---
+
+
+def test_black_and_white_palette_keeps_all_ten_glyphs():
+    assert len(set(_chars(_gradient_grid(10, BW), BW, ramp=RAMP))) == 10
+
+
+def test_glyph_choice_is_independent_of_the_palette():
+    grid = _gradient_grid(10)
+    assert _chars(grid, BW, ramp=RAMP) == _chars(grid, COLOUR, ramp=RAMP)
+
+
+def test_consumes_luma_and_index_only():
+    consumed = GlyphRampRenderer().consumes()
+    assert "luma" in consumed
+    assert consumed <= {"index", "luma", "samples", "coverage", "subindex"}
+
+
+# --- accept 3: offset shifts the mapping by exactly one glyph per 1/len(ramp) ---
+
+
+def test_offset_shifts_the_mapping_by_exactly_one_glyph():
+    grid = _ramp_grid(9)
+    base = _indices(grid)
+    assert base == list(range(9))
+    assert _indices(grid, offset=1 / len(RAMP)) == [value + 1 for value in base]
+
+
+def test_offset_is_measured_in_ramp_units_not_pixels():
+    positions = [0.0, 0.15, 0.35, 0.55, 0.75, 0.95]
+    grid = _position_grid(positions)
+    for step in range(5):
+        offset = step / len(RAMP)
+        expected = [RAMP[min(int(np.floor((p + offset) * len(RAMP))), len(RAMP) - 1)]
+                    for p in positions]
+        assert _chars(grid, ramp=RAMP, offset=offset) == expected
+
+
+def test_offset_is_animatable_and_clamped_at_both_ends():
+    grid = _ramp_grid(4)
+    assert set(_chars(grid, ramp=RAMP, offset=-5.0)) == {RAMP[0]}
+    assert set(_chars(grid, ramp=RAMP, offset=5.0)) == {RAMP[-1]}
+
+
+def test_a_fractional_offset_shimmers_without_changing_the_grid():
+    grid = _position_grid([0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95])
+    first = _chars(grid, ramp=RAMP)
+    assert first != _chars(grid, ramp=RAMP, offset=0.05)
+    assert _chars(grid, ramp=RAMP) == first
+
+
+# --- accept 4: invert reverses the ramp ---
+
+
+def test_invert_reverses_the_ramp():
+    grid = _gradient_grid(10)
+    forward = _chars(grid, ramp=RAMP)
+    reversed_ = _chars(grid, ramp=RAMP, invert=True)
+    assert reversed_ == [RAMP[len(RAMP) - 1 - RAMP.index(char)] for char in forward]
+    assert reversed_ == list(reversed(RAMP))
+
+
+def test_invert_and_offset_compose():
+    grid = _ramp_grid(9)
+    plain = _indices(grid)
+    assert _indices(grid, offset=0.1, invert=True) == [
+        len(RAMP) - 1 - (value + 1) for value in plain
+    ]
+
+
+# --- accept 5: mode "palette" gives each glyph the palette colour of its cell ---
+
+
+def test_palette_mode_gives_each_glyph_its_cell_palette_colour():
+    grid = _grid(np.full((1, 2), 0.05, dtype=np.float32), np.array([[1, 2]], dtype=np.int32))
+    cells = _cells(GlyphRampRenderer().render(grid, COLOUR, _style(ramp=RAMP, mode="palette")))
+    red, blue = cells[0, 0].reshape(-1, 3), cells[0, 1].reshape(-1, 3)
+    assert red[:, 0].max() > 0 and red[:, 1].max() == 0 and red[:, 2].max() == 0
+    assert blue[:, 2].max() > 0 and blue[:, 0].max() == 0 and blue[:, 1].max() == 0
+
+
+def test_palette_mode_fill_matches_the_cell_palette_colour():
+    grid = _grid(np.full((1, 2), 0.05, dtype=np.float32), np.array([[1, 2]], dtype=np.int32))
+    fills = [entry[5] for entry in GlyphRampRenderer().layout(grid, COLOUR, _style(mode="palette"))]
+    assert fills == ["#ff0000", "#0000ff"]
+
+
+def test_fg_colour_mode_takes_the_ink_from_the_palette_and_the_paper_from_bg():
+    grid = _grid(np.full((1, 1), 0.05, dtype=np.float32), np.array([[1]], dtype=np.int32))
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
+    grid = _grid(np.full((1, 1), 0.05, dtype=np.float32), np.array([[1]], dtype=np.int32))
+    style = _style(ramp=RAMP, mode="bg_colour", fg="#00ff00")
+    img = GlyphRampRenderer().render(grid, COLOUR, style)
+    glyph = GlyphRampRenderer().layout(grid, COLOUR, style)[0][0]
+    pixels = np.asarray(img).reshape(-1, 3)
+    mask = _glyph_mask(glyph, None, CELL_W, CELL_H).reshape(-1)
+    assert np.all(pixels[mask <= 0.0] == np.array([255, 0, 0], dtype=np.uint8))
+    darkest = pixels[int(np.argmax(mask))]
+    assert darkest[1] > darkest[0] and darkest[2] == 0
+
+
+def test_bg_colour_mode_keeps_the_glyph_in_fg():
+    grid = _grid(np.full((1, 1), 0.05, dtype=np.float32), np.array([[1]], dtype=np.int32))
+    style = _style(ramp=RAMP, mode="bg_colour", fg="#00ff00")
+    pixels = np.asarray(GlyphRampRenderer().render(grid, COLOUR, style))
+    glyph = GlyphRampRenderer().layout(grid, COLOUR, style)[0][0]
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
+        GlyphRampRenderer().render(_gradient_grid(4), BW, _style(ramp=RAMP, font=path))
+    assert path in str(excinfo.value)
+
+
+def test_font_option_accepts_a_real_font_file():
+    if not SYSTEM_FONT.is_file():
+        pytest.skip("no system TrueType font available")
+    img = GlyphRampRenderer().render(
+        _gradient_grid(4), BW, _style(ramp=RAMP, font=str(SYSTEM_FONT))
+    )
+    assert img.size == (4 * CELL_W, CELL_H)
+
+
+# --- §3 invariants ---
+
+
+def test_render_is_pure():
+    grid = _gradient_grid(10)
+    renderer = GlyphRampRenderer()
+    assert np.array_equal(
+        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
+        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
+    )
+
+
+def test_render_does_not_mutate_grid_or_palette():
+    grid = _gradient_grid(10)
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
+def test_style_options_round_trip_through_json():
+    options = {"ramp": RAMP, "mode": "palette", "offset": 0.25, "invert": True,
+               "fg": "#112233", "bg": "transparent", "font": None}
+    assert json.loads(json.dumps(dict(RenderStyle(options=options).options))) == options
+
+
+# --- layout() consistency with render() ---
+
+
+def test_layout_places_one_glyph_per_cell_row_major():
+    grid = _gradient_grid(10)
+    placed = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP))
+    assert len(placed) == grid.rows * grid.cols
+    for col, entry in enumerate(placed):
+        assert entry[1] == col * CELL_W and entry[2] == 0.0
+        assert entry[3] == CELL_W and entry[4] == CELL_H
+
+
+def test_layout_accepts_both_call_forms():
+    grid, style = _gradient_grid(4), _style(ramp=RAMP)
+    assert GlyphRampRenderer().layout(grid, style) == GlyphRampRenderer().layout(grid, BW, style)
+
+
+def test_layout_character_is_the_glyph_render_rasterises():
+    grid = _gradient_grid(6)
+    renderer = GlyphRampRenderer()
+    placed = renderer.layout(grid, BW, _style(ramp=RAMP))
+    cells = _cells(renderer.render(grid, BW, _style(ramp=RAMP)))
+    for col, entry in enumerate(placed):
+        mask = _glyph_mask(entry[0], None, CELL_W, CELL_H)
+        expected = np.floor((1.0 - mask) * 255.0 + 0.5).astype(np.uint8)
+        assert np.array_equal(cells[0, col, :, :, 0], expected)
+
+
+# --- H11: no size option, font size derives from cell_h ---
+
+
+def test_there_is_no_size_option():
+    grid = _gradient_grid(6)
+    plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
+    with_size = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, size=48)))
+    assert np.array_equal(plain, with_size)
+
+
+def test_glyph_covers_its_cell_exactly_at_any_cell_height():
+    for cell_h in (12, 24, 40):
+        mask = _glyph_mask("@", None, cell_h // 2, cell_h)
+        assert mask.shape == (cell_h, cell_h // 2)
+        assert 0.0 < float(mask.mean()) < 1.0
+
+
+def test_unknown_style_keys_are_ignored_for_forward_compatibility():
+    grid = _gradient_grid(6)
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
+        GlyphRampRenderer().render(_gradient_grid(4), BW, _style(ramp=""))
+
+
+def test_unknown_mode_raises_value_error_naming_the_modes():
+    with pytest.raises(ValueError) as excinfo:
+        GlyphRampRenderer().render(_gradient_grid(4), BW, _style(mode="vibrant"))
+    assert "fg_colour" in str(excinfo.value)
+
+
+def test_invalid_colour_raises_value_error():
+    with pytest.raises(ValueError):
+        GlyphRampRenderer().render(_gradient_grid(4), BW, _style(fg="not-a-colour"))
+
+
+def test_default_ramp_is_darkest_first_and_documented():
+    assert DEFAULT_RAMP[0] == "@"
+    assert DEFAULT_RAMP[-1] == " "
+    assert float(_glyph_mask(DEFAULT_RAMP[0], None, CELL_W, CELL_H).mean()) > 0.0
+
+
+def test_transparent_background_produces_an_rgba_image():
+    img = GlyphRampRenderer().render(_gradient_grid(4), BW, _style(ramp=RAMP, bg="transparent"))
+    assert img.mode == "RGBA"
+    assert img.size == (4 * CELL_W, CELL_H)
+
+
+def test_flat_luma_collapses_to_a_single_glyph():
+    assert set(_chars(_grid(np.zeros((2, 3), dtype=np.float32)), ramp=RAMP)) == {RAMP[0]}
+    assert set(_chars(_grid(np.ones((2, 3), dtype=np.float32)), ramp=RAMP)) == {RAMP[-1]}
+
+
+def test_luma_is_linear_light_not_srgb():
+    grid = _gradient_grid(10)
+    linear = color.srgb_to_linear(_gradient_cells(10))[0]
+    expected = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
+    assert np.allclose(grid.luma[0], expected, atol=1e-6)

CODER NOTES AND DEVIATIONS (L6, attempt 1)
- **luma → rampe (décision contrat silencieuse)** : grid.luma est en lumière linéaire ; le
  codeur la RÉ-ENCODE en sRGB avant l'indexation — sinon un dégradé N&B réel s'écrase dans le
  tiers sombre de la rampe (un gris 50 % sRGB = 0,214 linéaire) et l'accept « 10 glyphes
  distincts » échoue sur un dégradé perçu. À arbitrer : le §9 amendé dit « luma indexes an
  ordered ramp » (S2) — la ré-encodage est une interprétation perceptuelle, monotone donc
  darkest-first préservé.
- **layout() : double signature acceptée** : (grid, style) selon §3 et (grid, palette, style)
  selon l'implémentation L8 — dispatch sur le type du 2e argument ; tuples (character, x, y,
  width, height, fill). Shime de compat pour L11 §11.
- mode: palette → encre = couleur palette de la cellule, papier = entrée la plus sombre de la
  palette (accept §9) ; mode: fg_colour (E1, symétrique de bg_colour) ; transparent accepté
  pour fg/bg (RGBA si besoin) ; `size` silencieusement ignoré (clé inconnue §6 — preset d'une
  app plus récente rend quand même), test dédié.
- Aucun E8/E9, aucun écrit hors owns, layout() non exigé mais testé (L11 en dépend).
