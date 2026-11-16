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

### L2 · `CellRenderer` contract and `PixelRenderer`
- wave: 0 · deps: L1 · executor: OMH architect · review: strict · size: M
- owns: `lattice_core/cell.py`, `lattice_core/renderers/__init__.py`,
  `lattice_core/renderers/pixel.py`, `tests/test_cell.py` + `lattice_core/pipeline.py`
  (ajout DEV-203 : l'étape 11 de §5 et la dérivation coverage/luma/samples de §3 vivent
  dans `pipeline.render` — la carte ne peut pas les implémenter sans ce fichier)
- context: §3 §5
- spec: implement §3 exactly: `CellGrid`, `RenderStyle`, the `CellRenderer` protocol, the registry
  (`register_renderer`, `get_renderer`, `list_renderers`), and the `coverage` derivation. Implement
  `PixelRenderer` so that it reproduces the 1.0 `apply_palette` + `upscale_nearest` pair exactly.
  Wire step 11 of §5 into `pipeline.render` behind the registry, with `pixel` as the default so
  every existing caller keeps working.
- accept:
  - the six invariants of §3 are each a test.
  - `PixelRenderer` output is byte-identical to the 1.0 path on 20 random images and 5 palettes.
  - `list_renderers()` returns `["pixel"]` at this point.
  - `get_renderer("nope")` raises `KeyError` naming the missing renderer.
  - `coverage` is 0.0 on a single-colour palette and monotonic in palette luminance otherwise.
  - registering a duplicate name raises `ValueError`.

GATE RESULTS (attempt 2 — retry après verdict FIX du pass 1)
- G1 ruff: clean. G2 pytest: **1257 passed** (1216 baseline + 41 tests test_cell.py). G3
  check_contract: OK. G4: seuls les fichiers `owns` sont modifiés. G7: témoins bit-à-bit couverts
  par la suite. G8: registre = ["pixel"], aspect 1.0, subgrid (1,1), consumes {"index"}.
- **Vérification indépendante de l'orchestrateur (le blocker du pass 1)**: 25 essais
  `pipeline.render_with_palette` (tailles aléatoires, palettes flottantes non alignées 1/255,
  moitié avec post-effect gaussian_blur) comparés au pipeline HEAD (1.0) chargé en module isolé —
  **0 octet de différence**. Reproduction pré-fix du pass 1 : 57/240 octets.
- E8 vérifié par grep: aucun import d'application dans lattice_core.

HISTORIQUE DES FINDINGS DU PASS 1 (tous traités dans ce diff — à re-vérifier)
- blocker pipeline.py:186 — frame passée par uint8 avant les post-effets → fix: `_render_frame`
  + protocole optionnel `FloatFrameRenderer.render_frame` (float32) ; `PixelRenderer.render_frame`
  = apply_palette + np.repeat par axe, sans arrondi 8 bits.
- major test:143 — byte-identity qui restate l'implémentation → fix: passage par
  `pipeline.render_with_palette` sur 20 images aléatoires × 5 palettes (dont non alignées),
  avec/sans post-effects, pixel_size 1–3, max_side, + 2 cas palettes extraites (k-means,
  median-cut) vs _finish 1.0 rejoué inline ; le cas k-means affirme que la sortie DIFFERE du
  chemin défectueux.
- major invariant 4 — pipeline ne consultait pas cell_aspect → fix: renderer résolu avant
  l'étape 6, `_cell_geometry` dérive cell_w/cell_h de cell_aspect ; testé avec un stub temporaire
  (aspect 0.5 → cell 1×2).
- major invariant 6 — RenderStyle non enforce → fix: `RenderStyle.__post_init__` rejette
  non-sérialisable et perte de type (tuple→list) ; 3 tests.
- minors: code mort supprimé ; `render`/`render_with_palette` acceptent `renderer="pixel"` et
  `style=None` en keyword-only ; PixelRenderer répète lignes/colonnes par cell_h/cell_w
  séparément (test cellule non carrée) ; imports en tête + docstring _style.

DIFF (arbre de travail vs HEAD — le diff complet de la carte)
diff --git a/lattice_core/cell.py b/lattice_core/cell.py
new file mode 100644
index 0000000..436dd7b
--- /dev/null
+++ b/lattice_core/cell.py
@@ -0,0 +1,101 @@
+"""CellRenderer contract: CellGrid, RenderStyle, the renderer protocol and its registry."""
+
+from __future__ import annotations
+
+import json
+from collections.abc import Mapping
+from dataclasses import dataclass
+from typing import TYPE_CHECKING, Protocol, runtime_checkable
+
+import numpy as np
+from PIL import Image as PILImage
+
+if TYPE_CHECKING:
+    from lattice_core.types import Palette
+
+
+@dataclass(frozen=True)
+class CellGrid:
+    """One quantised image expressed as a grid of cells for a CellRenderer."""
+
+    cols: int
+    rows: int
+    cell_w: int
+    cell_h: int
+    index: np.ndarray  # (rows, cols) int32, palette index per cell
+    coverage: np.ndarray  # (rows, cols) float32 in [0, 1], ink coverage per cell
+    luma: np.ndarray  # (rows, cols) float32, linear luminance of the SOURCE cell
+    samples: np.ndarray  # (rows, cols, k) float32 in [0, 1], sub-cell luminance
+    subindex: np.ndarray | None = None  # (rows, cols, sx*sy) int32 per sub-point
+
+
+@dataclass(frozen=True)
+class RenderStyle:
+    """Renderer-specific options, JSON-serialisable."""
+
+    options: Mapping[str, object]
+
+    def __post_init__(self) -> None:
+        """Reject options that are not serialisable or do not round-trip through JSON."""
+        try:
+            encoded = json.dumps(dict(self.options))
+        except (TypeError, ValueError) as exc:
+            raise ValueError(f"render style options are not JSON-serialisable: {exc}") from exc
+        if json.loads(encoded) != dict(self.options):
+            raise ValueError("render style options do not round-trip through JSON without loss")
+
+
+@runtime_checkable
+class CellRenderer(Protocol):
+    """How a quantised CellGrid is drawn; the pipeline decides which palette entry."""
+
+    name: str
+
+    def cell_aspect(self) -> float:
+        """Return width / height of one cell."""
+        ...
+
+    def subgrid(self) -> tuple[int, int]:
+        """Return the (sx, sy) sub-point grid; (1, 1) means no sub-points."""
+        ...
+
+    def consumes(self) -> frozenset[str]:
+        """Return the subset of {"index", "luma", "samples"} this renderer reads."""
+        ...
+
+    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
+        """Draw grid with palette and style into a Pillow image."""
+        ...
+
+
+@runtime_checkable
+class FloatFrameRenderer(Protocol):
+    """Optional capability: hand the pipeline a float32 frame instead of a Pillow image."""
+
+    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
+        """Return the same frame as render, as float32 (rows*cell_h, cols*cell_w, 3) in [0, 1]."""
+        ...
+
+
+_RENDERERS: dict[str, CellRenderer] = {}
+
+
+def register_renderer(renderer: CellRenderer) -> CellRenderer:
+    """Register renderer under its name, raising ValueError on a duplicate name."""
+    if renderer.name in _RENDERERS:
+        raise ValueError(f"duplicate renderer name: {renderer.name!r}")
+    _RENDERERS[renderer.name] = renderer
+    return renderer
+
+
+def get_renderer(name: str) -> CellRenderer:
+    """Return the renderer registered under name, or raise KeyError naming it."""
+    try:
+        return _RENDERERS[name]
+    except KeyError:
+        raise KeyError(f"unknown renderer: {name!r}") from None
+
+
+def list_renderers() -> list[str]:
+    """Return every registered renderer name, sorted."""
+    return sorted(_RENDERERS)
diff --git a/lattice_core/pipeline.py b/lattice_core/pipeline.py
index c2e8480..db7f4e9 100644
--- a/lattice_core/pipeline.py
+++ b/lattice_core/pipeline.py
@@ -8,7 +8,9 @@ from typing import Literal
 import numpy as np
 
 from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle
 from lattice_core.registry import get_algorithm, get_effect, resolve_params
+from lattice_core.renderers import get_renderer
 from lattice_core.types import RGB8, Image, Palette
 
 MIN_PALETTE_SIZE = 2
@@ -16,6 +18,7 @@ MAX_PALETTE_SIZE = 256
 MIN_PIXEL_SIZE = 1
 MAX_PIXEL_SIZE = 32
 POST_EFFECT_SEED_OFFSET = 1000
+DEFAULT_RENDERER = "pixel"
 COLOR_METRICS = ("srgb", "linear", "oklab", "lab2000")
 PRESET_VERSION = 2
 RESERVED_METRIC = "_color_metric"
@@ -127,29 +130,44 @@ def _validate_order(order: list[int], size: int) -> None:
         raise ValueError(f"palette order is missing index {missing}")
 
 
-def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8:
+def render(
+    src: Image,
+    spec: PipelineSpec,
+    *,
+    max_side: int | None = None,
+    renderer: str = DEFAULT_RENDERER,
+    style: RenderStyle | None = None,
+) -> RGB8:
     """Render src through the eleven normative pipeline steps and return uint8 RGB."""
-    work, target, factor = _prepare(src, spec, max_side)
-    return _finish(work, target, factor, spec, resolve_palette(spec.palette, work))
+    work, target = _prepare(src, spec, max_side)
+    return _finish(work, target, spec, None, renderer, style)
 
 
 def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> Image:
     """Return src after steps 1 to 5, the image palette resolution reads."""
-    return _prepare(src, spec, max_side)[0]
+    work, _ = _prepare(src, spec, max_side)
+    cell_w, cell_h = _cell_geometry(get_renderer(DEFAULT_RENDERER), spec.pixel_size)
+    return _to_cells(work, cell_w, cell_h)
 
 
 def render_with_palette(
-    src: Image, spec: PipelineSpec, palette: Palette, *, max_side: int | None = None
+    src: Image,
+    spec: PipelineSpec,
+    palette: Palette,
+    *,
+    max_side: int | None = None,
+    renderer: str = DEFAULT_RENDERER,
+    style: RenderStyle | None = None,
 ) -> RGB8:
     """Render src with an already resolved palette, skipping step 5's resolution."""
-    work, target, factor = _prepare(src, spec, max_side)
-    return _finish(work, target, factor, spec, palette)
+    work, target = _prepare(src, spec, max_side)
+    return _finish(work, target, spec, palette, renderer, style)
 
 
 def _prepare(
     src: Image, spec: PipelineSpec, max_side: int | None
-) -> tuple[Image, tuple[int, int], int]:
-    """Run steps 1 to 5 and return the working image, the target shape and the pixel factor."""
+) -> tuple[Image, tuple[int, int]]:
+    """Run steps 1 to 5 and return the working image with the target shape of step 1."""
     work = _as_image(src)
     work = _proxy(work, max_side)
     target = work.shape[:2]
@@ -159,26 +177,109 @@ def _prepare(
     work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma, spec.saturation)
     if spec.pre_blur > 0.0:
         work = color.gaussian_blur(work, spec.pre_blur / 3.0)
-    factor = _pixel_size(spec.pixel_size)
-    work = color.downscale(work, factor)
-    return work, target, factor
+    return work, target
 
 
 def _finish(
-    work: Image, target: tuple[int, int], factor: int, spec: PipelineSpec, palette: Palette
+    work: Image,
+    target: tuple[int, int],
+    spec: PipelineSpec,
+    palette: Palette | None,
+    renderer_name: str = DEFAULT_RENDERER,
+    style: RenderStyle | None = None,
 ) -> RGB8:
-    """Run steps 6 to 11 on the prepared image with a resolved palette."""
+    """Run steps 6 to 12: choose the grid, quantise, render, then the post-effects."""
+    renderer = get_renderer(renderer_name)
+    cell_w, cell_h = _cell_geometry(renderer, spec.pixel_size)
+    cells = _to_cells(work, cell_w, cell_h)
+    if palette is None:
+        palette = resolve_palette(spec.palette, cells)
     info = get_algorithm(spec.algorithm_id)
     params = resolve_params(info.params, spec.algorithm_params)
     code = color.metric_code(spec.color_metric)
     params[RESERVED_METRIC] = code
     indices = info.fn(
-        color.to_working_space(work, code), color.to_working_space(palette, code), params
+        color.to_working_space(cells, code), color.to_working_space(palette, code), params
+    )
+    grid = _make_grid(cells, indices, cell_w, cell_h, palette)
+    style = RenderStyle(options={}) if style is None else style
+    frame = _render_frame(renderer, grid, palette, style)
+    frame = frame[: target[0], : target[1]]
+    frame = _apply_effects(frame, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
+    return color.to_rgb8(frame)
+
+
+def _cell_geometry(renderer: CellRenderer, pixel_size: int) -> tuple[int, int]:
+    """Return (cell_w, cell_h) from the renderer's cell aspect and the clamped pixel size."""
+    size = _pixel_size(pixel_size)
+    aspect = float(renderer.cell_aspect())
+    if not aspect > 0.0:
+        raise ValueError(f"renderer {renderer.name!r} returned cell_aspect {aspect!r}")
+    return size, max(1, int(round(size / aspect)))
+
+
+def _to_cells(work: Image, cell_w: int, cell_h: int) -> Image:
+    """Step 7: downscale the prepared image to the grid of cell_w x cell_h blocks."""
+    if cell_w == cell_h:
+        return color.downscale(work, cell_w)
+    pad_y = (-work.shape[0]) % cell_h
+    pad_x = (-work.shape[1]) % cell_w
+    if pad_y or pad_x:
+        work = np.pad(work, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")
+    rows = work.shape[0] // cell_h
+    cols = work.shape[1] // cell_w
+    blocks = work.reshape(rows, cell_h, cols, cell_w, 3)
+    return np.ascontiguousarray(blocks.mean(axis=(1, 3), dtype=np.float32))
+
+
+def _render_frame(
+    renderer: CellRenderer, grid: CellGrid, palette: Palette, style: RenderStyle
+) -> Image:
+    """Return the step-11 frame as float32, skipping the uint8 round-trip when exact."""
+    exact = getattr(renderer, "render_frame", None)
+    if callable(exact):
+        return np.ascontiguousarray(np.asarray(exact(grid, palette, style), dtype=np.float32))
+    return color.to_float(renderer.render(grid, palette, style))
+
+
+def _make_grid(
+    work: Image, indices: np.ndarray, cell_w: int, cell_h: int, palette: Palette
+) -> CellGrid:
+    """Build the CellGrid of step 10: index, coverage, luma and samples per cell."""
+    rows, cols = indices.shape
+    linear = color.srgb_to_linear(work)
+    luma = (
+        np.float32(0.2126) * linear[:, :, 0]
+        + np.float32(0.7152) * linear[:, :, 1]
+        + np.float32(0.0722) * linear[:, :, 2]
+    ).astype(np.float32)
+    samples = luma[:, :, None].copy()
+    coverage = _coverage_table(palette)[np.ascontiguousarray(indices, dtype=np.int32)]
+    return CellGrid(
+        cols=cols,
+        rows=rows,
+        cell_w=cell_w,
+        cell_h=cell_h,
+        index=np.ascontiguousarray(indices, dtype=np.int32),
+        coverage=np.ascontiguousarray(coverage, dtype=np.float32),
+        luma=np.ascontiguousarray(luma, dtype=np.float32),
+        samples=np.ascontiguousarray(samples, dtype=np.float32),
+    )
+
+
+def _coverage_table(palette: Palette) -> np.ndarray:
+    """Derive ink coverage per palette entry, 0.0 on a single-luminance palette."""
+    linear = color.srgb_to_linear(palette)
+    lum = (
+        np.float32(0.2126) * linear[:, 0]
+        + np.float32(0.7152) * linear[:, 1]
+        + np.float32(0.0722) * linear[:, 2]
     )
-    work = color.apply_palette(indices, palette)
-    work = color.upscale_nearest(work, factor, target)
-    work = _apply_effects(work, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
-    return color.to_rgb8(work)
+    lum_min = float(lum.min())
+    lum_max = float(lum.max())
+    if lum_max == lum_min:
+        return np.zeros(palette.shape[0], dtype=np.float32)
+    return np.ascontiguousarray(((lum - lum_min) / (lum_max - lum_min)).astype(np.float32))
 
 
 def _as_image(src: Image) -> Image:
diff --git a/lattice_core/renderers/__init__.py b/lattice_core/renderers/__init__.py
new file mode 100644
index 0000000..9565523
--- /dev/null
+++ b/lattice_core/renderers/__init__.py
@@ -0,0 +1,28 @@
+"""Built-in CellRenderer implementations."""
+
+from __future__ import annotations
+
+from lattice_core.cell import (  # noqa: F401  (re-exported for callers)
+    CellGrid,
+    CellRenderer,
+    FloatFrameRenderer,
+    RenderStyle,
+    get_renderer,
+    list_renderers,
+    register_renderer,
+)
+from lattice_core.renderers.pixel import PixelRenderer, register_pixel_renderer
+
+__all__ = [
+    "CellGrid",
+    "CellRenderer",
+    "FloatFrameRenderer",
+    "PixelRenderer",
+    "RenderStyle",
+    "get_renderer",
+    "list_renderers",
+    "register_pixel_renderer",
+    "register_renderer",
+]
+
+register_pixel_renderer()
diff --git a/lattice_core/renderers/pixel.py b/lattice_core/renderers/pixel.py
new file mode 100644
index 0000000..ae46f1d
--- /dev/null
+++ b/lattice_core/renderers/pixel.py
@@ -0,0 +1,48 @@
+"""The PixelRenderer: the 1.0 apply_palette + upscale_nearest pair as a CellRenderer."""
+
+from __future__ import annotations
+
+import numpy as np
+from PIL import Image as PILImage
+
+from lattice_core import color
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
+from lattice_core.types import Palette
+
+_PIXEL = "pixel"
+
+
+class PixelRenderer:
+    """Draw each cell as a solid square of its palette colour (name "pixel")."""
+
+    name = _PIXEL
+
+    def cell_aspect(self) -> float:
+        """Return 1.0: one cell is one pixel wide and one pixel tall."""
+        return 1.0
+
+    def subgrid(self) -> tuple[int, int]:
+        """Return (1, 1): pixels carry no sub-points."""
+        return (1, 1)
+
+    def consumes(self) -> frozenset[str]:
+        """Return {"index"}: only the palette index per cell is drawn."""
+        return frozenset({"index"})
+
+    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
+        """Reproduce the 1.0 apply_palette + upscale_nearest pair exactly."""
+        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))
+
+    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
+        """Return the unrounded frame: palette colours repeated by cell_w and cell_h."""
+        work = color.apply_palette(grid.index, palette)
+        if grid.cell_h > 1:
+            work = np.repeat(work, grid.cell_h, axis=0)
+        if grid.cell_w > 1:
+            work = np.repeat(work, grid.cell_w, axis=1)
+        return np.ascontiguousarray(work, dtype=np.float32)
+
+
+def register_pixel_renderer() -> CellRenderer:
+    """Register the PixelRenderer under "pixel" and return it."""
+    return register_renderer(PixelRenderer())
diff --git a/tests/test_cell.py b/tests/test_cell.py
new file mode 100644
index 0000000..03a79b9
--- /dev/null
+++ b/tests/test_cell.py
@@ -0,0 +1,400 @@
+"""Tests for the CellRenderer contract (§3) and the PixelRenderer."""
+
+from __future__ import annotations
+
+import json
+
+import numpy as np
+import pytest
+
+import lattice_core.cell as cell_module
+import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
+import lattice_core.effects  # noqa: F401  (registers the effects the pipeline resolves)
+from lattice_core import color
+from lattice_core.cell import (
+    CellGrid,
+    CellRenderer,
+    RenderStyle,
+    get_renderer,
+    list_renderers,
+    register_renderer,
+)
+from lattice_core.palettes.extract import extract_palette
+from lattice_core.pipeline import (
+    MAX_PIXEL_SIZE,
+    MIN_PIXEL_SIZE,
+    POST_EFFECT_SEED_OFFSET,
+    EffectInstance,
+    PipelineSpec,
+    _coverage_table,
+    _make_grid,
+    render_with_palette,
+)
+from lattice_core.registry import get_algorithm, get_effect, resolve_params
+from lattice_core.renderers.pixel import PixelRenderer
+from lattice_core.types import Image, Palette
+
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+GREY_PALETTE: Palette = np.array([[v / 255.0] * 3 for v in (0, 85, 170, 255)], dtype=np.float32)
+PRIMARY: Palette = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
+FLOAT_PALETTE: Palette = np.array(
+    [[0.2, 0.4, 0.6], [0.9, 0.1, 0.3], [0.05, 0.77, 0.13]], dtype=np.float32
+)
+
+
+def _grid(rows: int = 3, cols: int = 4, cell: int = 2, index: np.ndarray | None = None) -> CellGrid:
+    """Build a deterministic CellGrid with the given geometry."""
+    if index is None:
+        index = np.arange(rows * cols, dtype=np.int32).reshape(rows, cols) % 2
+    luma = np.full((rows, cols), 0.5, dtype=np.float32)
+    return CellGrid(
+        cols=cols,
+        rows=rows,
+        cell_w=cell,
+        cell_h=cell,
+        index=index,
+        coverage=np.full((rows, cols), 0.5, dtype=np.float32),
+        luma=luma,
+        samples=luma[:, :, None].copy(),
+    )
+
+
+def _style(options: dict | None = None) -> RenderStyle:
+    """Return a RenderStyle carrying options, defaulting to {"scale": 1}."""
+    return RenderStyle(options=options or {"scale": 1})
+
+
+# --- The frozen 1.0 reference: apply_palette + upscale_nearest + effects + to_rgb8 ---
+
+
+def _legacy_effects(img: Image, instances: list, seed: int, offset: int) -> Image:
+    """Replay the 1.0 post/pre-effect loop: seed + offset + i per enabled effect."""
+    out = img
+    index = 0
+    for instance in instances:
+        if not instance.enabled:
+            continue
+        info = get_effect(instance.effect_id)
+        params = resolve_params(info.params, instance.params)
+        rng = np.random.default_rng(seed + offset + index)
+        out = np.ascontiguousarray(np.clip(info.fn(out, params, rng), 0.0, 1.0), dtype=np.float32)
+        index += 1
+    return out
+
+
+def _legacy_steps_1_to_7(src: Image, spec: PipelineSpec, max_side: int | None) -> tuple:
+    """Replay 1.0 steps 1 to 7 inline and return the grid image, the target and the factor."""
+    work = np.ascontiguousarray(np.asarray(src, dtype=np.float32))
+    if max_side is not None and max(work.shape[:2]) > max_side:
+        work = color.downscale(work, -(-max(work.shape[:2]) // max_side))
+    target = work.shape[:2]
+    work = _legacy_effects(work, spec.pre_effects, spec.seed, 0)
+    if spec.auto_levels:
+        work = color.auto_levels(work)
+    work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma, spec.saturation)
+    if spec.pre_blur > 0.0:
+        work = color.gaussian_blur(work, spec.pre_blur / 3.0)
+    factor = max(MIN_PIXEL_SIZE, min(MAX_PIXEL_SIZE, int(spec.pixel_size)))
+    return color.downscale(work, factor), target, factor
+
+
+def _legacy_render(
+    src: Image,
+    spec: PipelineSpec,
+    palette: Palette,
+    max_side: int | None = None,
+    *,
+    round_frame: bool = False,
+) -> np.ndarray:
+    """Replay the whole 1.0 render path inline, as the frozen reference output.
+
+    With round_frame, replay the reviewed defect instead: the frame is rounded to 8 bits
+    before the post-effects, which is what the L2 wiring did before this fix.
+    """
+    work, target, factor = _legacy_steps_1_to_7(src, spec, max_side)
+    info = get_algorithm(spec.algorithm_id)
+    params = resolve_params(info.params, spec.algorithm_params)
+    code = color.metric_code(spec.color_metric)
+    params["_color_metric"] = code
+    indices = info.fn(
+        color.to_working_space(work, code), color.to_working_space(palette, code), params
+    )
+    work = color.apply_palette(indices, palette)
+    work = color.upscale_nearest(work, factor, target)
+    if round_frame:
+        work = color.to_float(color.to_pil(color.to_rgb8(work)))[: target[0], : target[1]]
+    work = _legacy_effects(work, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
+    return color.to_rgb8(work)
+
+
+# --- Invariant 1: output size is exactly (cols*cell_w, rows*cell_h) ---
+
+
+def test_invariant_output_size_matches_grid_geometry():
+    assert PixelRenderer().render(_grid(rows=3, cols=4, cell=2), BW, _style()).size == (8, 6)
+    assert PixelRenderer().render(_grid(rows=5, cols=7, cell=1), BW, _style()).size == (7, 5)
+
+
+def test_invariant_output_size_with_non_square_cells():
+    grid = CellGrid(
+        cols=4,
+        rows=3,
+        cell_w=2,
+        cell_h=3,
+        index=np.zeros((3, 4), dtype=np.int32),
+        coverage=np.zeros((3, 4), dtype=np.float32),
+        luma=np.zeros((3, 4), dtype=np.float32),
+        samples=np.zeros((3, 4, 1), dtype=np.float32),
+    )
+    assert PixelRenderer().render(grid, BW, _style()).size == (4 * 2, 3 * 3)
+
+
+# --- Invariant 2: purity ---
+
+
+def test_invariant_render_is_pure():
+    grid = _grid()
+    renderer = PixelRenderer()
+    first = np.asarray(renderer.render(grid, BW, _style()))
+    second = np.asarray(renderer.render(grid, BW, _style()))
+    assert np.array_equal(first, second)
+
+
+# --- Invariant 3: no mutation of grid or palette ---
+
+
+def test_invariant_render_does_not_mutate_inputs():
+    grid = _grid()
+    palette = BW.copy()
+    snapshot = (
+        grid.index.copy(),
+        grid.coverage.copy(),
+        grid.luma.copy(),
+        grid.samples.copy(),
+    )
+    PixelRenderer().render(grid, palette, _style())
+    assert np.array_equal(grid.index, snapshot[0])
+    assert np.array_equal(grid.coverage, snapshot[1])
+    assert np.array_equal(grid.luma, snapshot[2])
+    assert np.array_equal(grid.samples, snapshot[3])
+    assert np.array_equal(palette, BW)
+
+
+# --- Invariant 4: the pipeline chooses the grid from cell_aspect() ---
+
+
+class _RecordingRenderer:
+    """Stub renderer with a configurable cell aspect that records the grid it is given."""
+
+    def __init__(self, aspect: float) -> None:
+        self.name = f"recording_stub_{aspect!s}"
+        self.aspect = aspect
+        self.grid: CellGrid | None = None
+
+    def cell_aspect(self) -> float:
+        """Return the configured width / height of one cell."""
+        return self.aspect
+
+    def subgrid(self) -> tuple[int, int]:
+        """Return (1, 1): the stub packs no sub-points."""
+        return (1, 1)
+
+    def consumes(self) -> frozenset[str]:
+        """Return {"index"}: the stub draws palette indices only."""
+        return frozenset({"index"})
+
+    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle):
+        """Record the grid and return a blank image of the exact grid geometry."""
+        self.grid = grid
+        blank = np.zeros((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3), dtype=np.uint8)
+        return color.to_pil(blank)
+
+
+def _render_with_stub(aspect: float, src: Image, pixel_size: int) -> CellGrid:
+    """Register a stub renderer at aspect, render src through the pipeline, then unregister."""
+    stub = _RecordingRenderer(aspect)
+    register_renderer(stub)
+    try:
+        spec = PipelineSpec(pixel_size=pixel_size)
+        render_with_palette(src, spec, BW, renderer=stub.name)
+    finally:
+        cell_module._RENDERERS.pop(stub.name, None)
+    assert stub.grid is not None
+    return stub.grid
+
+
+def test_invariant_cell_aspect_is_width_over_height():
+    assert PixelRenderer().cell_aspect() == 1.0
+
+
+def test_pipeline_derives_grid_geometry_from_cell_aspect():
+    src = np.full((20, 30, 3), 0.5, dtype=np.float32)
+    grid = _render_with_stub(0.5, src, pixel_size=1)
+    assert (grid.cell_w, grid.cell_h) == (1, 2)
+    out_aspect = (grid.cols * grid.cell_w) / (grid.rows * grid.cell_h)
+    assert out_aspect == pytest.approx(30 / 20)
+
+
+def test_pipeline_preserves_source_aspect_with_square_cells():
+    src = np.full((15, 40, 3), 0.5, dtype=np.float32)
+    grid = _render_with_stub(1.0, src, pixel_size=3)
+    assert (grid.cell_w, grid.cell_h) == (3, 3)
+    out_aspect = (grid.cols * grid.cell_w) / (grid.rows * grid.cell_h)
+    assert out_aspect == pytest.approx(40 / 15, rel=0.1)
+
+
+# --- Invariant 5: unique, stable name ---
+
+
+def test_invariant_renderer_name_is_stable():
+    assert PixelRenderer().name == "pixel"
+    assert get_renderer("pixel").name == "pixel"
+    names = [get_renderer(name).name for name in list_renderers()]
+    assert len(names) == len(set(names))
+
+
+# --- Invariant 6: style.options round-trips through JSON ---
+
+
+def test_invariant_style_options_round_trip_json():
+    options = {"scale": 2, "label": "demo", "flags": [True, False], "ratio": 0.25}
+    style = RenderStyle(options=options)
+    assert json.loads(json.dumps(dict(style.options))) == options
+    default = RenderStyle(options={})
+    assert json.loads(json.dumps(dict(default.options))) == dict(default.options)
+
+
+def test_style_rejects_non_serialisable_options():
+    with pytest.raises(ValueError):
+        RenderStyle(options={"x": object()})
+
+
+def test_style_rejects_options_that_lose_their_type():
+    with pytest.raises(ValueError):
+        RenderStyle(options={"flags": (True, False)})
+
+
+# --- Registry behaviour ---
+
+
+def test_list_renderers_returns_pixel():
+    assert list_renderers() == ["pixel"]
+
+
+def test_get_renderer_unknown_raises_key_error_naming_it():
+    with pytest.raises(KeyError) as excinfo:
+        get_renderer("nope")
+    assert "nope" in str(excinfo.value)
+
+
+def test_register_duplicate_name_raises_value_error():
+    with pytest.raises(ValueError):
+        register_renderer(PixelRenderer())
+
+
+def test_protocol_conformance():
+    assert isinstance(PixelRenderer(), CellRenderer)
+
+
+# --- The pipeline reproduces the 1.0 path byte for byte ---
+
+
+def _random_case(trial: int) -> tuple[Image, PipelineSpec, Palette]:
+    """Return one deterministic (source, spec, palette) case for the parity sweep."""
+    rng = np.random.default_rng(20261116 + trial)
+    height = int(rng.integers(9, 25))
+    width = int(rng.integers(9, 25))
+    src = rng.random((height, width, 3), dtype=np.float32)
+    palettes = [BW, GREY_PALETTE, PRIMARY, FLOAT_PALETTE, rng.random((5, 3)).astype(np.float32)]
+    pixel_size = int(rng.integers(1, 4))
+    if trial % 3 == 0:
+        post = [EffectInstance("gaussian_blur", {"radius": 1.0})]
+    elif trial % 3 == 1:
+        post = [EffectInstance("noise", {"amount": 0.2, "monochrome": True})]
+    else:
+        post = []
+    spec = PipelineSpec(pixel_size=pixel_size, post_effects=post, seed=trial)
+    return src, spec, palettes[trial % len(palettes)]
+
+
+@pytest.mark.parametrize("trial", range(20))
+def test_pipeline_matches_legacy_finish_on_random_images(trial: int) -> None:
+    src, spec, palette = _random_case(trial)
+    got = render_with_palette(src, spec, palette)
+    want = _legacy_render(src, spec, palette)
+    assert got.shape == want.shape
+    assert np.array_equal(got, want), f"mismatch on trial {trial}"
+
+
+def test_pipeline_matches_legacy_finish_with_max_side_and_effects():
+    rng = np.random.default_rng(99)
+    src = rng.random((40, 57, 3), dtype=np.float32)
+    spec = PipelineSpec(
+        pixel_size=2,
+        post_effects=[EffectInstance("gaussian_blur", {"radius": 1.0})],
+        pre_effects=[EffectInstance("noise", {"amount": 0.1})],
+        seed=5,
+    )
+    got = render_with_palette(src, spec, FLOAT_PALETTE, max_side=20)
+    want = _legacy_render(src, spec, FLOAT_PALETTE, max_side=20)
+    assert np.array_equal(got, want)
+
+
+def test_extracted_palette_with_post_effect_matches_legacy_finish():
+    rng = np.random.default_rng(424242)
+    src = rng.random((37, 53, 3), dtype=np.float32)
+    palette = extract_palette(src, 5, "kmeans")
+    assert not np.allclose(palette * 255.0, np.round(palette * 255.0)), "palette is 8-bit aligned"
+    spec = PipelineSpec(
+        pixel_size=2,
+        post_effects=[EffectInstance("gaussian_blur", {"radius": 1.0})],
+        seed=3,
+    )
+    got = render_with_palette(src, spec, palette)
+    assert np.array_equal(got, _legacy_render(src, spec, palette))
+    assert not np.array_equal(got, _legacy_render(src, spec, palette, round_frame=True))
+
+
+def test_median_cut_palette_with_noise_matches_legacy_finish():
+    rng = np.random.default_rng(8181)
+    src = rng.random((24, 31, 3), dtype=np.float32)
+    palette = extract_palette(src, 6, "median_cut")
+    spec = PipelineSpec(
+        pixel_size=3,
+        post_effects=[EffectInstance("noise", {"amount": 0.3, "monochrome": False})],
+        seed=11,
+    )
+    got = render_with_palette(src, spec, palette)
+    assert np.array_equal(got, _legacy_render(src, spec, palette))
+
+
+# --- Coverage derivation ---
+
+
+def test_coverage_zero_on_single_colour_palette():
+    palette = np.array([[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]], dtype=np.float32)
+    coverage = _coverage_table(palette)
+    assert np.all(coverage == 0.0)
+    assert coverage.shape == (2,)
+
+
+def test_coverage_monotone_in_palette_luminance():
+    palette = np.array([[v / 255.0] * 3 for v in (0, 64, 128, 192, 255)], dtype=np.float32)
+    linear = color.srgb_to_linear(palette)
+    lum = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
+    coverage = _coverage_table(palette)
+    assert np.all(np.diff(coverage[np.argsort(lum)]) >= 0)
+
+
+def test_luma_is_continuous_and_palette_independent():
+    rng = np.random.default_rng(7)
+    work = rng.random((4, 6, 3)).astype(np.float32)
+    index = np.zeros((4, 6), dtype=np.int32)
+    grid_bw = _make_grid(work, index, 1, 1, BW)
+    grid_grey = _make_grid(work, index, 1, 1, GREY_PALETTE)
+    assert np.array_equal(grid_bw.luma, grid_grey.luma)
+    linear = color.srgb_to_linear(work)
+    expected = (
+        0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1] + 0.0722 * linear[:, :, 2]
+    ).astype(np.float32)
+    assert np.allclose(grid_bw.luma, expected, atol=1e-6)

CODER NOTES AND DEVIATIONS (attempt 2, deepseek-v4-1-flash-1017)
- `FloatFrameRenderer` (protocole optionnel, `render_frame`) ajouté dans cell.py — l'option
  « cleaner » du relecteur ; §3 inchangé (CellRenderer.render rend toujours une image Pillow),
  pas d'E6 nécessaire.
- `_prepare` ne fait plus la descente en grille ; `_to_cells` s'en charge. `prepare_image`
  renvoie toujours l'image de l'étape 7 (byte-identique, vérifié par le codeur).
- Chemin `cell_w == cell_h` délègue à `color.downscale` pour rester bit-à-bit identique.
- `tests/test_cell.py` importe `lattice_core.dither` et `lattice_core.effects` pour enregistrer
  algorithmes/effets (le test n'accède plus via l'app).
- Le stub de test nettoie le registre via `cell_module._RENDERERS.pop` — accès privé confiné au
  test, faute d'API de désenregistrement publique.
- DEVIATIONS: none déclarées à l'attempt 2 (les E1 de l'attempt 1 restent consignés DEV-204 ;
  le point 2 — renderer hardcodé — est résolu par le champ `renderer=`).
