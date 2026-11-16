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

GATE RESULTS
- G1 ruff: clean. (5 erreurs UP035/F401 corrigées par `ruff check --fix`, 1 E501 reflowé —
  format-only, appliqués par l'orchestrateur côté gate, pas de changement de logique.)
- G2 pytest: 1231 passed = 1216 baseline + 15 nouveaux (test_cell.py), deux runs successives.
- G3 check_contract: OK.
- G4 propriété des fichiers: seul `lattice_core/pipeline.py` modifié + 3 nouveaux fichiers
  `owns` (cell.py, renderers/, test_cell.py); rien hors owns (pipeline.py ajouté par DEV-203).
- G7 régression core: couvert par la suite — les baselines témoins (01_gameboy, 05_ega_riemersma,
  07_grey16_stucki) sont re-rendus bit-à-bit dans les tests G2.
- G8 contrat renderers: registre = ["pixel"], aspect 1.0, subgrid (1,1), consumes {"index"},
  KeyError "unknown renderer: 'nope'" vérifié en dur.
- G9 parité CLI/GUI: non applicable — aucune coquille d'app dans cette carte ; la parité dither
  existante est couverte par la suite 1.1 (G6).

DIFF
diff --git a/lattice_core/cell.py b/lattice_core/cell.py
new file mode 100644
index 0000000..e6aba69
--- /dev/null
+++ b/lattice_core/cell.py
@@ -0,0 +1,82 @@
+"""CellRenderer contract: CellGrid, RenderStyle, the renderer protocol and its registry."""
+
+from __future__ import annotations
+
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
index c2e8480..fdfd54d 100644
--- a/lattice_core/pipeline.py
+++ b/lattice_core/pipeline.py
@@ -8,7 +8,9 @@ from typing import Literal
 import numpy as np
 
 from lattice_core import color
+from lattice_core.cell import CellGrid, RenderStyle
 from lattice_core.registry import get_algorithm, get_effect, resolve_params
+from lattice_core.renderers import get_renderer, list_renderers
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
@@ -175,12 +178,54 @@ def _finish(
     indices = info.fn(
         color.to_working_space(work, code), color.to_working_space(palette, code), params
     )
-    work = color.apply_palette(indices, palette)
-    work = color.upscale_nearest(work, factor, target)
+    renderer = get_renderer(DEFAULT_RENDERER)
+    if renderer.name not in list_renderers():
+        raise KeyError(f"unknown renderer: {renderer.name!r}")
+    grid = _make_grid(work, indices, factor, palette)
+    image = renderer.render(grid, palette, RenderStyle(options={}))
+    work = color.to_float(image)[: target[0], : target[1]]
     work = _apply_effects(work, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
     return color.to_rgb8(work)
 
 
+def _make_grid(work: Image, indices: np.ndarray, factor: int, palette: Palette) -> CellGrid:
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
+        cell_w=factor,
+        cell_h=factor,
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
+    )
+    lum_min = float(lum.min())
+    lum_max = float(lum.max())
+    if lum_max == lum_min:
+        return np.zeros(palette.shape[0], dtype=np.float32)
+    return np.ascontiguousarray(((lum - lum_min) / (lum_max - lum_min)).astype(np.float32))
+
+
 def _as_image(src: Image) -> Image:
     """Validate the source shape and return it as a contiguous float32 image."""
     array = np.asarray(src)
diff --git a/lattice_core/renderers/__init__.py b/lattice_core/renderers/__init__.py
new file mode 100644
index 0000000..d47aa82
--- /dev/null
+++ b/lattice_core/renderers/__init__.py
@@ -0,0 +1,26 @@
+"""Built-in CellRenderer implementations."""
+
+from __future__ import annotations
+
+from lattice_core.cell import (  # noqa: F401  (re-exported for callers)
+    CellGrid,
+    CellRenderer,
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
index 0000000..c984149
--- /dev/null
+++ b/lattice_core/renderers/pixel.py
@@ -0,0 +1,43 @@
+"""The PixelRenderer: the 1.0 apply_palette + upscale_nearest pair as a CellRenderer."""
+
+from __future__ import annotations
+
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
+        work = color.apply_palette(grid.index, palette)
+        work = color.upscale_nearest(
+            work, grid.cell_h, (grid.rows * grid.cell_h, grid.cols * grid.cell_w)
+        )
+        rgb8 = color.to_rgb8(work)
+        return color.to_pil(rgb8)
+
+
+def register_pixel_renderer() -> CellRenderer:
+    """Register the PixelRenderer under "pixel" and return it."""
+    return register_renderer(PixelRenderer())
diff --git a/tests/test_cell.py b/tests/test_cell.py
new file mode 100644
index 0000000..bbc7019
--- /dev/null
+++ b/tests/test_cell.py
@@ -0,0 +1,207 @@
+"""Tests for the CellRenderer contract (§3) and the PixelRenderer."""
+
+from __future__ import annotations
+
+import json
+
+import numpy as np
+import pytest
+
+from lattice_core import color
+from lattice_core.cell import (
+    CellGrid,
+    CellRenderer,
+    RenderStyle,
+    get_renderer,
+    list_renderers,
+    register_renderer,
+)
+from lattice_core.renderers.pixel import PixelRenderer
+from lattice_core.types import Palette
+
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+GREY_PALETTE: Palette = np.array(
+    [[v / 255.0] * 3 for v in (0, 85, 170, 255)], dtype=np.float32
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
+    return RenderStyle(options=options or {"scale": 1})
+
+
+# --- Invariant 1: output size is exactly (cols*cell_w, rows*cell_h) ---
+
+
+def test_invariant_output_size_matches_grid_geometry():
+    grid = _grid(rows=3, cols=4, cell=2)
+    image = PixelRenderer().render(grid, BW, _style())
+    assert image.size == (4 * 2, 3 * 2)
+
+
+def test_invariant_output_size_factor_one():
+    grid = _grid(rows=5, cols=7, cell=1)
+    image = PixelRenderer().render(grid, BW, _style())
+    assert image.size == (7, 5)
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
+# --- Invariant 4: cell_aspect is width / height ---
+
+
+def test_invariant_cell_aspect_is_width_over_height():
+    assert PixelRenderer().cell_aspect() == 1.0
+
+
+# --- Invariant 5: unique, stable name ---
+
+
+def test_invariant_renderer_name_is_stable():
+    assert PixelRenderer().name == "pixel"
+    assert get_renderer("pixel").name == "pixel"
+
+
+# --- Invariant 6: style.options round-trips through JSON ---
+
+
+def test_invariant_style_options_round_trip_json():
+    options = {"scale": 2, "label": "demo", "flags": [True, False], "ratio": 0.25}
+    style = RenderStyle(options=options)
+    assert json.loads(json.dumps(dict(style.options))) == options
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
+# --- PixelRenderer reproduces the 1.0 apply_palette + upscale_nearest pair ---
+
+
+def test_pixel_renderer_matches_legacy_pair_on_random_images():
+    rng = np.random.default_rng(20261116)
+    palettes = [
+        BW,
+        GREY_PALETTE,
+        rng.random((5, 3)).astype(np.float32),
+        np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32),
+        np.array([[0.2, 0.4, 0.6], [0.9, 0.1, 0.3]], dtype=np.float32),
+    ]
+    for trial in range(20):
+        rows = int(rng.integers(1, 9))
+        cols = int(rng.integers(1, 9))
+        cell = int(rng.integers(1, 5))
+        palette = palettes[trial % len(palettes)]
+        index = rng.integers(0, palette.shape[0], size=(rows, cols)).astype(np.int32)
+        grid = _grid(rows=rows, cols=cols, cell=cell, index=index)
+        rendered = np.asarray(PixelRenderer().render(grid, palette, _style()))
+        legacy = color.upscale_nearest(
+            color.apply_palette(index, palette), cell, (rows * cell, cols * cell)
+        )
+        legacy8 = color.to_rgb8(legacy)
+        assert np.array_equal(rendered, legacy8), f"mismatch on trial {trial}"
+
+
+# --- Coverage derivation ---
+
+
+def test_coverage_zero_on_single_colour_palette():
+    palette = np.array([[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]], dtype=np.float32)
+    from lattice_core.pipeline import _coverage_table
+
+    coverage = _coverage_table(palette)
+    assert np.all(coverage == 0.0)
+    assert coverage.shape == (2,)
+
+
+def test_coverage_monotone_in_palette_luminance():
+    from lattice_core.pipeline import _coverage_table
+
+    palette = np.array(
+        [[v / 255.0] * 3 for v in (0, 64, 128, 192, 255)], dtype=np.float32
+    )
+    linear = color.srgb_to_linear(palette)
+    lum = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
+    coverage = _coverage_table(palette)
+    order = np.argsort(lum)
+    sorted_cov = coverage[order]
+    assert np.all(np.diff(sorted_cov) >= 0)
+
+
+def test_luma_is_continuous_and_palette_independent():
+    from lattice_core.pipeline import _make_grid
+
+    rng = np.random.default_rng(7)
+    work = rng.random((4, 6, 3)).astype(np.float32)
+    index = np.zeros((4, 6), dtype=np.int32)
+    grid_bw = _make_grid(work, index, 1, BW)
+    grid_grey = _make_grid(work, index, 1, GREY_PALETTE)
+    assert np.array_equal(grid_bw.luma, grid_grey.luma)
+    linear = color.srgb_to_linear(work)
+    expected = (
+        0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1] + 0.0722 * linear[:, :, 2]
+    ).astype(np.float32)
+    assert np.allclose(grid_bw.luma, expected, atol=1e-6)

CODER NOTES AND DEVIATIONS
- Notes du codeur (rapport final, attempt 1) : 15 tests nouveaux couverts par item `accept` ;
  suite complète 1231 passed (deux exécutions) ; auto-vérification E8 « no app imports in core »
  (grep lattice_dither/lattice_glyph/lattice_glitch vide) ; registre et KeyError vérifiés en dur.
- DEVIATIONS: none déclarées par le codeur.
- Contexte de routage (transparence) : le codeur de l'attempt 1 a tourné sur mistral-large-4
  (routage d'avant la décision humaine du 2026-11-16 ; le codage passe désormais sur les modèles
  standard — deepseek-v4.1-flash — et les gros modèles sont réservés à la relecture/décision).
