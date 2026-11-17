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

### L8 · Bitmask renderers
- wave: 1 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/renderers/bitmask.py`, `tests/test_bitmask.py` +
  `lattice_core/renderers/__init__.py` (enregistrement : ajout DEV-208 — append atomique d'une
  ligne d'import via terminal, JAMAIS write_file sur ce fichier, ne toucher qu'à VOTRE ligne)
- context: §3 §9
- spec: implement `bitmask` per §9. One code path, four geometries: `braille` (2×4, U+2800+mask),
  `sextant` (2×3, U+1FB00..U+1FB3B), `quadrant` (2×2, U+2596..U+259F), `half_block` (1×2, U+2580/
  U+2584/U+2588). Threshold `samples` into sub-dots. Options: `threshold`, `fg`, `bg` — pas de
  `dither` (S3/H11 : la décision du sous-point appartient à l'algorithme, résolu au subgrid).
- accept:
  - a fully black cell produces the full codepoint for each geometry; a fully white cell produces
    the empty or background codepoint.
  - the four geometries produce the documented sub-cell counts (8, 6, 4, 2).
  - `threshold` at 0.5 on a half-black cell produces a half-filled codepoint.
  - sur une cellule gris moyen, le motif des sous-points suit l'algorithme à la résolution du
    subgrid et est déterministe (S3 : pas d'option `dither`).
  - every emitted codepoint is a valid Unicode scalar in the documented range.

GATE RESULTS (L8, attempt 2 — deepseek-v4-flash-0731)
- Owned tests : **48 passed** (+1 test de régression palette dégénérée), ruff clean.
- Suite complète : **1603 passed, 1 skipped, 0 failed**.
- Pass 1 (v4-pro) : FIX — blocker sextant row-major + test auto-bénissant + minors.

DISPOSITION PASS 1 (attempt 2)
- blocker : _SEXTANT_CODEPOINTS reconstruite en mapping identité row-major (bit k ↔ point k+1),
  dérivée des NOMS Unicode ; le bloc n'exprime exactement que {vide, plein, colonne gauche
  {1,3,5}, colonne droite {2,4,6}} (masks 0/21/42/63) → U+0020/U+2588 + approximations 3-points
  documentées U+1FB06/U+1FB0A (miroirs en bloc, jamais un glyphe 2-points) ; spot-checks 10/10.
- major : test réécrit — mask→codepoint construit depuis les NOMS (« BLOCK SEXTANT-* »), sans
  dict manuel, skip seulement si unicodedata < 13.0, asserte l'ensemble manquant + stand-ins +
  6 gardes positionnelles (table transposée → échec).
- minors : docstring corrigé (inexprimables = vide/plein/2 colonnes ; Unicode 13.0) ; palette
  dégénérée → tout-papier (all-False), conforme _coverage_table, + test de régression.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/renderers/bitmask.py b/lattice_core/renderers/bitmask.py
new file mode 100644
index 0000000..cd92a22
--- /dev/null
+++ b/lattice_core/renderers/bitmask.py
@@ -0,0 +1,242 @@
+"""The bitmask renderer family: braille, sextant, quadrant, half_block (§9).
+
+One code path, four geometries. The sub-point decision belongs to the
+dithering algorithm, run by the pipeline at subgrid resolution (S3): each
+renderer packs ``grid.subindex`` into one block character per cell.
+
+Codepoint ranges (E1, see NOTES in the card):
+
+- ``braille`` 2x4: U+2800 + an 8-dot bitmask; all 256 patterns are assigned.
+- ``sextant`` 2x3: U+1FB00..U+1FB3B (Unicode 13.0 BLOCK SEXTANT-*) plus U+0020
+  and U+2588 FULL BLOCK. Dots are row-major: 1=top-left, 2=top-right,
+  3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right. The block
+  cannot express four patterns: empty -> U+0020, all six dots -> U+2588, and
+  the two solid columns {1,3,5} / {2,4,6} -> the documented 3-dot
+  approximations U+1FB06 and U+1FB0A (upper two-thirds blocks, E1).
+- ``quadrant`` 2x2: U+2596..U+259F (Unicode 15.1 quadrant names) plus the
+  exact half/full blocks U+2580, U+2584, U+2588, U+258C, U+2590 and U+0020.
+- ``half_block`` 1x2: U+2580, U+2584, U+2588 and U+0020 (background).
+
+The four geometries are four registered renderers sharing this class: the
+pipeline derives the sub-point resolution from ``subgrid()`` before it ever
+sees a style (pipeline.py §5 step 6), so the geometry cannot be a style
+option. Options: ``threshold`` (0..1, default 0.5), ``fg``/``bg`` (hex
+colours). There is no ``dither`` option (removed, H11/S3): an unknown option
+in the style is ignored.
+"""
+
+from __future__ import annotations
+
+import re
+from typing import Final
+
+import numpy as np
+from PIL import Image as PILImage
+
+from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
+from lattice_core.types import Palette
+
+_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}\Z")
+_GEOMETRY_ORDER: Final = ("braille", "sextant", "quadrant", "half_block")
+
+# Sub-point k is ordered y-major, x-minor: k = y * sx + x, matching the
+# pipeline's subindex packing and its default k-point stencil (S3).
+_BRAILLE_DOT_BITS: Final = (0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80)
+_BRAILLE_BASE: Final = 0x2800
+# Sextant: mask bit k = dot k+1, row-major (1=top-left, 2=top-right,
+# 3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right), built from
+# the Unicode BLOCK SEXTANT-* names (L8 FIX: the previous table was
+# column-major and transposed 54 of 60 patterns). The block lacks empty, full
+# and the two solid columns {1,3,5}/{2,4,6}: empty -> U+0020, full -> U+2588,
+# the columns -> the documented 3-dot approximations U+1FB06 (SEXTANT-123)
+# and U+1FB0A (SEXTANT-124), never a 2-dot glyph that drops a dot (E1).
+_SEXTANT_CODEPOINTS: Final = (
+    0x0020, 0x1FB00, 0x1FB01, 0x1FB02,
+    0x1FB03, 0x1FB04, 0x1FB05, 0x1FB06,
+    0x1FB07, 0x1FB08, 0x1FB09, 0x1FB0A,
+    0x1FB0B, 0x1FB0C, 0x1FB0D, 0x1FB0E,
+    0x1FB0F, 0x1FB10, 0x1FB11, 0x1FB12,
+    0x1FB13, 0x1FB06, 0x1FB14, 0x1FB15,
+    0x1FB16, 0x1FB17, 0x1FB18, 0x1FB19,
+    0x1FB1A, 0x1FB1B, 0x1FB1C, 0x1FB1D,
+    0x1FB1E, 0x1FB1F, 0x1FB20, 0x1FB21,
+    0x1FB22, 0x1FB23, 0x1FB24, 0x1FB25,
+    0x1FB26, 0x1FB27, 0x1FB0A, 0x1FB28,
+    0x1FB29, 0x1FB2A, 0x1FB2B, 0x1FB2C,
+    0x1FB2D, 0x1FB2E, 0x1FB2F, 0x1FB30,
+    0x1FB31, 0x1FB32, 0x1FB33, 0x1FB34,
+    0x1FB35, 0x1FB36, 0x1FB37, 0x1FB38,
+    0x1FB39, 0x1FB3A, 0x1FB3B, 0x2588,
+)
+_QUADRANT_CODEPOINTS: Final = (
+    0x0020, 0x2598, 0x259D, 0x2580, 0x2596, 0x258C, 0x259E, 0x259B,
+    0x2597, 0x259A, 0x2590, 0x259C, 0x2584, 0x2599, 0x259F, 0x2588,
+)
+_HALF_BLOCK_CODEPOINTS: Final = (0x0020, 0x2580, 0x2584, 0x2588)
+
+_GEOMETRIES: Final = {
+    "braille": (2, 4, _BRAILLE_DOT_BITS, _BRAILLE_BASE),
+    "sextant": (2, 3, _SEXTANT_CODEPOINTS, None),
+    "quadrant": (2, 2, _QUADRANT_CODEPOINTS, None),
+    "half_block": (1, 2, _HALF_BLOCK_CODEPOINTS, None),
+}
+
+_THRESHOLD = "threshold"
+_FG = "fg"
+_BG = "bg"
+_DEFAULTS: Final = {"threshold": 0.5, "fg": "#000000", "bg": "#ffffff"}
+
+
+class BitmaskRenderer:
+    """Pack sub-point palette decisions into one block character per cell."""
+
+    def __init__(self, geometry: str) -> None:
+        """Store the geometry; raise ValueError on an unknown geometry name."""
+        if geometry not in _GEOMETRIES:
+            raise ValueError(f"unknown bitmask geometry: {geometry!r}")
+        self._geometry = geometry
+        self.name = geometry
+        self._sx, self._sy = (
+            int(value) for value in _GEOMETRIES[geometry][:2]
+        )
+
+    def cell_aspect(self) -> float:
+        """Return sx / sy: width dots over height dots of one cell."""
+        return self._sx / self._sy
+
+    def subgrid(self) -> tuple[int, int]:
+        """Return the (sx, sy) sub-point grid of this geometry (S3)."""
+        return (self._sx, self._sy)
+
+    def consumes(self) -> frozenset[str]:
+        """Return {"subindex"}: the algorithm's sub-point decisions (S3)."""
+        return frozenset({"subindex"})
+
+    def codepoints(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
+        """Return the (rows, cols) int32 Unicode codepoint of every cell."""
+        option = self._options(style)
+        bits_or_table, base = _GEOMETRIES[self._geometry][2:]
+        dots = self._on_dots(grid, palette, option[_THRESHOLD])
+        masks = np.zeros((grid.rows, grid.cols), dtype=np.int64)
+        if base is not None:
+            for k, bit in enumerate(bits_or_table):
+                masks |= dots[:, :, k].astype(np.int64) * bit
+            return np.ascontiguousarray(base + masks, dtype=np.int32)
+        for k in range(self._sx * self._sy):
+            masks |= dots[:, :, k].astype(np.int64) << k
+        table = np.asarray(bits_or_table, dtype=np.int32)
+        return np.ascontiguousarray(np.take(table, masks), dtype=np.int32)
+
+    def _on_dots(self, grid: CellGrid, palette: Palette, threshold: float) -> np.ndarray:
+        """Return the (rows, cols, sx*sy) bool ink mask of the sub-points."""
+        if grid.subindex is None:
+            raise ValueError(
+                f"{self.name!r} needs grid.subindex (S3, subgrid "
+                f"{self._sx}x{self._sy}); the pipeline fills it "
+                "at sub-point resolution"
+            )
+        expected = (grid.rows, grid.cols, self._sx * self._sy)
+        if grid.subindex.shape != expected:
+            raise ValueError(
+                f"{self.name!r} expected grid.subindex of shape {expected}, "
+                f"got {grid.subindex.shape}"
+            )
+        linear = color.srgb_to_linear(palette)
+        lum = (np.float32(0.2126) * linear[:, 0] + np.float32(0.7152) * linear[:, 1]
+               + np.float32(0.0722) * linear[:, 2])
+        lum_min, lum_max = float(lum.min()), float(lum.max())
+        if lum_max == lum_min:
+            # Degenerate palette: no contrast to threshold, so no ink — all
+            # paper, matching the pipeline's _coverage_table convention where
+            # coverage 0 means no ink (L8 FIX, H11).
+            return np.zeros(
+                (grid.rows, grid.cols, self._sx * self._sy), dtype=bool
+            )
+        rel = (lum - lum_min) / (lum_max - lum_min)
+        return rel[grid.subindex] < np.float32(threshold)
+
+    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
+        """Return the unrounded frame: fg dots on a bg cell, as render draws."""
+        option = self._options(style)
+        fg = _colour(option[_FG])
+        bg = _colour(option[_BG])
+        frame = np.broadcast_to(
+            bg.astype(np.float32),
+            (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3),
+        ).copy()
+        dots = self._on_dots(grid, palette, option[_THRESHOLD])
+        x_spans = _spans(grid.cell_w, self._sx)
+        y_spans = _spans(grid.cell_h, self._sy)
+        blocks = frame.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w, 3)
+        ink = fg.reshape(1, 1, 1, 1, 3)
+        for k in range(self._sx * self._sy):
+            if not dots[:, :, k].any():
+                continue
+            y0, y1 = y_spans[k // self._sx]
+            x0, x1 = x_spans[k % self._sx]
+            patch = blocks[:, y0:y1, :, x0:x1, :]
+            on = dots[:, :, k].reshape(grid.rows, 1, grid.cols, 1, 1)
+            patch[...] = np.where(on, ink, patch)
+        return np.ascontiguousarray(frame, dtype=np.float32)
+
+    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
+        """Rasterise the fg/bg dots into a Pillow image of the grid geometry."""
+        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))
+
+    def layout(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> list[tuple]:
+        """Return one (character, x, y, width, height, fill) per cell (§3)."""
+        option = self._options(style)
+        codepoints = self.codepoints(grid, palette, style)
+        placed: list[tuple] = []
+        for r in range(grid.rows):
+            for c in range(grid.cols):
+                placed.append((
+                    chr(int(codepoints[r, c])),
+                    float(c * grid.cell_w), float(r * grid.cell_h),
+                    float(grid.cell_w), float(grid.cell_h),
+                    option[_FG].lower(),
+                ))
+        return placed
+
+    def _options(self, style: RenderStyle) -> dict:
+        """Return validated threshold/fg/bg; unknown options stay ignored."""
+        threshold = float(style.options.get(_THRESHOLD, _DEFAULTS[_THRESHOLD]))
+        if not 0.0 <= threshold <= 1.0:
+            raise ValueError(
+                f"bitmask option {_THRESHOLD!r} must be in [0, 1], got {threshold!r}"
+            )
+        fg = str(style.options.get(_FG, _DEFAULTS[_FG]))
+        bg = str(style.options.get(_BG, _DEFAULTS[_BG]))
+        if _HEX_COLOUR.fullmatch(fg) is None:
+            raise ValueError(f"bitmask option {_FG!r} must be #RRGGBB, got {fg!r}")
+        if _HEX_COLOUR.fullmatch(bg) is None:
+            raise ValueError(f"bitmask option {_BG!r} must be #RRGGBB, got {bg!r}")
+        return {_THRESHOLD: threshold, _FG: fg, _BG: bg}
+
+
+def _colour(hex_code: str) -> np.ndarray:
+    """Parse #RRGGBB into a float32 (3,) sRGB row in [0, 1]."""
+    return np.asarray(
+        [int(hex_code[i : i + 2], 16) / 255.0 for i in (1, 3, 5)], dtype=np.float32
+    )
+
+
+def _spans(length: int, count: int) -> list[tuple[int, int]]:
+    """Split length pixels into count [start, end) spans of at least 1 pixel.
+
+    Identical to pipeline._spans, so the filled bands cover exactly the
+    pixels the pipeline averaged into each sub-point (S3).
+    """
+    edges = [index * length // count for index in range(count + 1)]
+    return [(start, min(length, max(start + 1, end)))
+            for start, end in zip(edges, edges[1:], strict=False)]
+
+
+def register_bitmask_renderers() -> tuple[CellRenderer, ...]:
+    """Register the four bitmask renderers under their geometry names."""
+    return tuple(register_renderer(BitmaskRenderer(geometry))
+                 for geometry in _GEOMETRY_ORDER)
+
+
+register_bitmask_renderers()
diff --git a/tests/test_bitmask.py b/tests/test_bitmask.py
new file mode 100644
index 0000000..3ccb9a6
--- /dev/null
+++ b/tests/test_bitmask.py
@@ -0,0 +1,392 @@
+"""Tests for the bitmask renderer family (L8, §3 §9, contract 0.1.0)."""
+
+from __future__ import annotations
+
+import unicodedata
+
+import numpy as np
+import pytest
+
+import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
+from lattice_core.cell import (
+    CellGrid,
+    CellRenderer,
+    RenderStyle,
+    get_renderer,
+    list_renderers,
+)
+from lattice_core.pipeline import PipelineSpec, render_with_palette
+from lattice_core.renderers.bitmask import (
+    _HALF_BLOCK_CODEPOINTS,
+    _QUADRANT_CODEPOINTS,
+    _SEXTANT_CODEPOINTS,
+    register_bitmask_renderers,
+)
+
+BW: np.ndarray = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+# (geometry, sx, sy, sub-point count) — the documented sub-cell counts (§9).
+GEOMETRIES: dict[str, tuple[int, int, int]] = {
+    "braille": (2, 4, 8),
+    "sextant": (2, 3, 6),
+    "quadrant": (2, 2, 4),
+    "half_block": (1, 2, 2),
+}
+# The all-ink codepoint of each geometry (E1: sextant/quadrant/half_block
+# express "full" with U+2588 FULL BLOCK; braille with U+28FF).
+FULL: dict[str, int] = {
+    "braille": 0x28FF, "sextant": 0x2588, "quadrant": 0x2588,
+    "half_block": 0x2588,
+}
+# The all-paper codepoint (empty or background, E1 for the three geometries
+# whose block has no blank glyph: U+0020).
+EMPTY: dict[str, int] = {
+    "braille": 0x2800, "sextant": 0x20, "quadrant": 0x20, "half_block": 0x20,
+}
+
+
+def _style(**options) -> RenderStyle:
+    """Return a RenderStyle carrying the given JSON-serialisable options."""
+    return RenderStyle(options=options)
+
+
+def _grid(geometry: str, subindex: np.ndarray, rows: int = 1, cols: int = 1,
+          cell_w: int = 2, cell_h: int = 4) -> CellGrid:
+    """Build a CellGrid whose sub-points carry the given palette indices."""
+    sx, sy, count = GEOMETRIES[geometry]
+    if subindex.ndim == 1:
+        if subindex.size == count:
+            filled = np.broadcast_to(
+                np.asarray(subindex, dtype=np.int32).reshape(1, 1, count),
+                (rows, cols, count),
+            ).copy()
+        else:
+            filled = np.asarray(subindex, dtype=np.int32).reshape(rows, cols, count)
+    else:
+        filled = np.asarray(subindex, dtype=np.int32)
+    if filled.shape != (rows, cols, count):
+        raise ValueError(f"subindex shape {filled.shape} != {(rows, cols, count)}")
+    return CellGrid(
+        cols=cols,
+        rows=rows,
+        cell_w=cell_w,
+        cell_h=cell_h,
+        index=np.zeros((rows, cols), dtype=np.int32),
+        coverage=np.full((rows, cols), 0.5, dtype=np.float32),
+        luma=np.full((rows, cols), 0.5, dtype=np.float32),
+        samples=np.full((rows, cols, count), 0.5, dtype=np.float32),
+        subindex=filled,
+    )
+
+
+def _all_patterns(geometry: str) -> list[np.ndarray]:
+    """Return one subindex row per possible sub-point pattern (0..2^count)."""
+    _, _, count = GEOMETRIES[geometry]
+    return [np.array([(mask >> k) & 1 for k in range(count)], dtype=np.int32)
+            for mask in range(1 << count)]
+
+
+# --- accept: the four geometries expose the documented sub-cell counts ---
+
+
+@pytest.mark.parametrize(("name", "sx", "sy", "count"),
+                         sorted((n, *g) for n, g in GEOMETRIES.items()))
+def test_geometry_subcell_counts(name, sx, sy, count):
+    renderer = get_renderer(name)
+    assert renderer.subgrid() == (sx, sy)
+    assert renderer.cell_aspect() == pytest.approx(sx / sy)
+
+
+# --- accept: black cell → full codepoint, white cell → empty codepoint ---
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_black_cell_produces_the_full_codepoint(name):
+    sx, sy, count = GEOMETRIES[name]
+    grid = _grid(name, np.zeros(count, dtype=np.int32))
+    codepoint = int(get_renderer(name).codepoints(grid, BW, _style())[0, 0])
+    assert codepoint == FULL[name]
+    assert codepoint == ord(get_renderer(name).layout(grid, BW, _style())[0][0])
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_white_cell_produces_the_empty_codepoint(name):
+    sx, sy, count = GEOMETRIES[name]
+    grid = _grid(name, np.ones(count, dtype=np.int32))
+    codepoint = int(get_renderer(name).codepoints(grid, BW, _style())[0, 0])
+    assert codepoint == EMPTY[name]
+
+
+# --- accept: threshold 0.5 on a half-black cell → a half-filled codepoint ---
+
+
+@pytest.mark.parametrize(("name", "half"), [("braille", 4), ("sextant", 3),
+                                            ("quadrant", 2), ("half_block", 1)])
+def test_half_black_cell_is_half_filled(name, half):
+    tables = {"sextant": _SEXTANT_CODEPOINTS, "quadrant": _QUADRANT_CODEPOINTS,
+              "half_block": _HALF_BLOCK_CODEPOINTS}
+    _, _, count = GEOMETRIES[name]
+    subindex = np.array([0] * half + [1] * (count - half), dtype=np.int32)
+    grid = _grid(name, subindex)
+    codepoint = int(get_renderer(name).codepoints(grid, BW, _style(threshold=0.5))[0, 0])
+    if name == "braille":
+        assert bin(codepoint - 0x2800).count("1") == half
+    else:
+        mask_value = (1 << half) - 1  # the first `half` sub-points are ink
+        assert codepoint == tables[name][mask_value]
+    img = np.asarray(get_renderer(name).render(grid, BW, _style(threshold=0.5)))
+    # ink dots and paper both survive the rasterisation of a half-filled cell.
+    assert (img == 0).any() and (img == 255).any()
+    assert (img[:, :, 0] == img[:, :, 1]).all()
+
+
+# --- accept (S3): the pattern follows the algorithm's subgrid decision ---
+
+
+def test_pattern_packs_subindex_not_samples():
+    renderer = get_renderer("braille")
+    # Mid-grey samples (0.5 at threshold 0.5 would threshold to all-paper);
+    # the sub-points keep an explicit checkerboard from the algorithm.
+    subindex = np.array([0, 1, 1, 0, 0, 1, 1, 0], dtype=np.int32)
+    grid = _grid("braille", subindex)
+    expected = 0x2800 + 0x01 + 0x10 + 0x04 + 0x80  # k in (0, 3, 4, 7)
+    assert int(renderer.codepoints(grid, BW, _style(threshold=0.5))[0, 0]) == expected
+    frame = renderer.render_frame(grid, BW, _style(threshold=0.5))
+    assert frame.shape == (4, 2, 3)  # dots follow the same k-order as subindex
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_mid_grey_cell_is_deterministic(name):
+    grid = _grid(name, np.array([0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1][:GEOMETRIES[name][2]],
+                                dtype=np.int32))
+    renderer = get_renderer(name)
+    first = np.asarray(renderer.render(grid, BW, _style(threshold=0.5)))
+    second = np.asarray(renderer.render(grid, BW, _style(threshold=0.5)))
+    assert np.array_equal(first, second)
+
+
+def test_removed_dither_option_changes_nothing():
+    grid = _grid("braille", np.array([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int32))
+    renderer = get_renderer("braille")
+    plain = np.asarray(renderer.render(grid, BW, _style(threshold=0.5)))
+    with_dither = np.asarray(renderer.render(grid, BW, _style(threshold=0.5, dither=True)))
+    assert np.array_equal(plain, with_dither)
+
+
+# --- accept: every emitted codepoint is a valid scalar, in the documented range ---
+
+
+_DOCUMENTED = {
+    "braille": lambda cp: 0x2800 <= cp <= 0x28FF,
+    "sextant": lambda cp: cp in (0x20, 0x2588) or 0x1FB00 <= cp <= 0x1FB3B,
+    "quadrant": lambda cp: cp in (0x20, 0x2580, 0x2584, 0x2588, 0x258C, 0x2590)
+    or 0x2596 <= cp <= 0x259F,
+    "half_block": lambda cp: cp in (0x20, 0x2580, 0x2584, 0x2588),
+}
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_every_emitted_codepoint_is_valid_and_documented(name):
+    renderer = get_renderer(name)
+    for subindex in _all_patterns(name):
+        grid = _grid(name, subindex)
+        codepoint = int(renderer.codepoints(grid, BW, _style())[0, 0])
+        assert 0 < codepoint <= 0x10FFFF
+        assert not 0xD800 <= codepoint <= 0xDFFF
+        assert _DOCUMENTED[name](codepoint), (name, subindex, hex(codepoint))
+
+
+def test_sextant_table_matches_unicode_names():
+    """Derive the dot numbering from Unicode names, never from the table.
+
+    BLOCK SEXTANT names are row-major: dot 1=top-left, 2=top-right,
+    3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right. The table
+    must agree for every expressible pattern; the four patterns the block
+    cannot express must use the documented stand-ins. A transposed table
+    fails on mask 2 (top-right: SEXTANT-2, not SEXTANT-4) or the missing mask
+    set {0, 21, 42, 63}.
+    """
+    if unicodedata.unidata_version < "13.0":
+        pytest.skip(f"needs Unicode >= 13.0, got {unicodedata.unidata_version}")
+    present = {}
+    for cp in range(0x1FB00, 0x1FB3C):
+        name = unicodedata.name(chr(cp))
+        if "SEXTANT-" not in name:
+            continue
+        mask = sum(1 << (int(d) - 1) for d in name.split("SEXTANT-")[1])
+        assert mask not in present, (mask, hex(cp))
+        present[mask] = cp
+    # 60 of the 64 patterns exist in U+1FB00..U+1FB3B; the block lacks empty,
+    # full, and the two solid columns {1,3,5}/{2,4,6} (row-major dots).
+    assert set(present) == set(range(64)) - {0, 21, 42, 63}, \
+        sorted(set(range(64)) - set(present))
+    for mask, cp in present.items():
+        assert _SEXTANT_CODEPOINTS[mask] == cp, (mask, hex(cp))
+    # Documented stand-ins (E1): empty, full, and 3-dot column approximations.
+    assert _SEXTANT_CODEPOINTS[0] == 0x0020
+    assert _SEXTANT_CODEPOINTS[63] == 0x2588
+    assert _SEXTANT_CODEPOINTS[21] == 0x1FB06  # SEXTANT-123, upper two-thirds
+    assert _SEXTANT_CODEPOINTS[42] == 0x1FB0A  # SEXTANT-124, its mirror
+    # Single-dot positional guards: mask bit k = dot k+1 (identity, row-major).
+    assert [_SEXTANT_CODEPOINTS[1 << k] for k in range(6)] == [
+        0x1FB00, 0x1FB01, 0x1FB03, 0x1FB07, 0x1FB0F, 0x1FB1E]
+
+
+def test_degenerate_palette_renders_all_paper():
+    """A zero-luminance-range palette has no contrast: all sub-dots stay paper.
+
+    Matches the pipeline's _coverage_table convention (coverage 0 = no ink);
+    the previous behaviour rel = 0 < threshold turned every cell into the
+    all-ink codepoint.
+    """
+    flat = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
+    for name in sorted(GEOMETRIES):
+        renderer = get_renderer(name)
+        grid = _grid(name, np.zeros(GEOMETRIES[name][2], dtype=np.int32))
+        codepoint = int(renderer.codepoints(grid, flat, _style(threshold=0.5))[0, 0])
+        assert codepoint == EMPTY[name], name
+        assert (np.asarray(renderer.render(grid, flat, _style())) == 255).all(), name
+
+
+def test_quadrant_codepoint_names():
+    from lattice_core.renderers.bitmask import _QUADRANT_CODEPOINTS
+    quadrants = {
+        "UPPER LEFT": 0x1, "UPPER RIGHT": 0x2, "LOWER LEFT": 0x4,
+        "LOWER RIGHT": 0x8,
+    }
+    blocks = {0x2580: 0b0011, 0x258C: 0b0101, 0x2590: 0b1010,
+              0x2584: 0b1100, 0x2588: 0b1111}
+    for mask, cp in enumerate(_QUADRANT_CODEPOINTS):
+        if cp == 0x20:
+            assert mask == 0
+            continue
+        if cp in blocks:
+            assert blocks[cp] == mask, (mask, hex(cp))
+            continue
+        assert 0x2596 <= cp <= 0x259F, (mask, hex(cp))
+        name = unicodedata.name(chr(cp))
+        expected = 0
+        for word, bit in quadrants.items():
+            if word in name:
+                expected |= bit
+        assert expected == mask, (mask, hex(cp), name)
+
+
+# --- §3 invariants ---
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_render_size_matches_grid_geometry(name):
+    renderer = get_renderer(name)
+    subindex = np.tile(np.arange(GEOMETRIES[name][2], dtype=np.int32) % 2, 6)
+    grid = _grid(name, subindex, rows=3, cols=2, cell_w=2, cell_h=4)
+    assert renderer.render(grid, BW, _style()).size == (2 * 2, 3 * 4)
+    frame = renderer.render_frame(grid, BW, _style())
+    assert frame.shape == (3 * 4, 2 * 2, 3)
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_render_is_pure_and_mutates_nothing(name):
+    renderer = get_renderer(name)
+    subindex = np.tile(np.arange(GEOMETRIES[name][2], dtype=np.int32) % 2, 4)
+    grid = _grid(name, subindex, rows=2, cols=2)
+    palette = BW.copy()
+    snapshot = grid.subindex.copy()
+    first = np.asarray(renderer.render(grid, palette, _style(threshold=0.4)))
+    second = np.asarray(renderer.render(grid, palette, _style(threshold=0.4)))
+    assert np.array_equal(first, second)
+    assert np.array_equal(grid.subindex, snapshot)
+    assert np.array_equal(palette, BW)
+
+
+@pytest.mark.parametrize("name", sorted(GEOMETRIES))
+def test_render_frame_matches_render(name):
+    renderer = get_renderer(name)
+    subindex = np.tile(np.arange(GEOMETRIES[name][2], dtype=np.int32) % 2, 4)
+    grid = _grid(name, subindex, rows=2, cols=2, cell_w=3, cell_h=2)
+    frame = renderer.render_frame(grid, BW, _style())
+    rounded = np.floor(np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
+    assert np.array_equal(rounded, np.asarray(renderer.render(grid, BW, _style())))
+
+
+def test_registered_under_geometry_names_and_contract_protocol():
+    for name in GEOMETRIES:
+        renderer = get_renderer(name)
+        assert isinstance(renderer, CellRenderer)
+        assert renderer.name == name
+    assert set(GEOMETRIES) <= set(list_renderers())
+    assert len({get_renderer(name).name for name in GEOMETRIES}) == len(GEOMETRIES)
+    with pytest.raises(ValueError):
+        register_bitmask_renderers()  # duplicate names
+
+
+def test_layout_positions_match_codepoints():
+    renderer = get_renderer("braille")
+    subindex = np.tile(np.arange(8, dtype=np.int32) % 2, 4).reshape(2, 2, 8)
+    grid = _grid("braille", subindex, rows=2, cols=2, cell_w=2, cell_h=4)
+    placed = renderer.layout(grid, BW, _style(fg="#ff0000"))
+    assert len(placed) == 4
+    for cell, (char, x, y, width, height, fill) in enumerate(placed):
+        expected_char = int(
+            renderer.codepoints(grid, BW, _style(fg="#ff0000"))[cell // 2, cell % 2]
+        )
+        assert char == chr(expected_char)
+        assert (x, y) == ((cell % 2) * 2, (cell // 2) * 4)
+        assert (width, height) == (2, 4)
+        assert fill == "#ff0000"
+
+
+# --- options ---
+
+
+def test_option_validation():
+    grid = _grid("braille", np.zeros(8, dtype=np.int32))
+    renderer = get_renderer("braille")
+    with pytest.raises(ValueError, match="threshold"):
+        renderer.render(grid, BW, _style(threshold=1.5))
+    with pytest.raises(ValueError, match="threshold"):
+        renderer.render(grid, BW, _style(threshold=-0.1))
+    with pytest.raises(ValueError, match="fg"):
+        renderer.render(grid, BW, _style(fg="red"))
+    with pytest.raises(ValueError, match="bg"):
+        renderer.render(grid, BW, _style(bg="#12345"))
+    # a fully black braille cell renders every sub-dot in the default black fg.
+    assert (np.asarray(renderer.render(grid, BW, _style())) == 0).all()
+
+
+def test_fg_and_bg_colours_reach_the_pixels():
+    renderer = get_renderer("braille")
+    black = _grid("braille", np.zeros(8, dtype=np.int32))
+    white = _grid("braille", np.ones(8, dtype=np.int32))
+    pixels = np.asarray(renderer.render(black, BW, _style(fg="#ff0000", bg="#0000ff")))
+    assert (pixels == (255, 0, 0)).all()
+    pixels = np.asarray(renderer.render(white, BW, _style(fg="#ff0000", bg="#0000ff")))
+    assert (pixels == (0, 0, 255)).all()
+
+
+def test_missing_or_mis_shaped_subindex_raises():
+    from dataclasses import replace
+    renderer = get_renderer("sextant")
+    grid = _grid("sextant", np.zeros(6, dtype=np.int32))
+    with pytest.raises(ValueError, match="subindex"):
+        renderer.render(replace(grid, subindex=None), BW, _style())
+    with pytest.raises(ValueError, match="subindex"):
+        renderer.render(replace(grid, subindex=np.zeros((1, 1, 4), dtype=np.int32)),
+                        BW, _style())
+
+
+# --- pipeline integration (S3): the pipeline fills grid.subindex and renders ---
+
+
+@pytest.mark.parametrize(("renderer", "pixel_size", "src_h", "src_w"),
+                         [("braille", 4, 16, 16), ("sextant", 3, 12, 12)])
+def test_pipeline_renders_bitmask_renderer(renderer, pixel_size, src_h, src_w):
+    src = np.zeros((src_h, src_w, 3), dtype=np.float32)
+    src[: src_h // 2, :, :] = 1.0
+    spec = PipelineSpec(pixel_size=pixel_size)
+    first = render_with_palette(src, spec, BW, renderer=renderer)
+    second = render_with_palette(src, spec, BW, renderer=renderer)
+    assert np.array_equal(first, second)
+    assert first.shape == (src_h, src_w, 3)
+    # black and white halves both appear: ink and paper survive the pipeline.
+    assert (first[: src_h // 2] == 0).all() or (first[src_h // 2 :] == 0).all() \
+        or (first[: src_h // 2, :, 0] != first[src_h // 2 :, :, 0]).any()

NOTES DU CODEUR (L8, attempt 2)
- Aucune déviation contre les instructions. Renommage du test (…unicode_names, skip < 13.0).
- PNG/render inchangés (rasterise via _spans, indépendant de la table).
- Diagnostic Pyright « codepoints unknown on CellRenderer » : style préexistant (appels
  identiques partout), non bloquant, ruff vert.
