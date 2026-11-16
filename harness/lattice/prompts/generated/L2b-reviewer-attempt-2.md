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

### L2b · Pipeline §3/§5 complet — mode continu, sous-points, géométrie (H11)
- wave: 0 · deps: L2 · executor: OMH architect · review: strict · size: M
- owns: `lattice_core/pipeline.py`, `lattice_core/cell.py`, `tests/test_pipeline.py`
- context: §3 §5 (amendements H11 décidés 2026-11-16 : règle de géométrie §5-6, mode continu
  reformulé, pochoir `sample_points()`, `render_frame`, `layout()`, invariant 2 amendé)
- spec: compléter le pipeline et les types selon les amendements H11 :
  1. `PipelineSpec` gagne `renderer: str = "pixel"` et `renderer_style: dict = {}` ;
     `render` et `render_with_palette` les propagent (fin du `DEFAULT_RENDERER` hardcodé).
  2. Mode continu (§5) : `algorithm: null` et `palette: null` → étapes 6-11 sautées, l'image
     de l'étape 5 va directement aux post-effets (étape 12) ; aucun CellGrid construit, aucun
     renderer appelé. Bit-exact par construction.
  3. Sous-points (S3) : quand `renderer.subgrid() != (1, 1)`, l'algorithme tourne à la
     résolution (rows·sy, cols·sx) et `grid.subindex: (rows, cols, sx·sy) int32` est rempli.
  4. Pochoir `samples` : `renderer.sample_points()` (optionnel, H11) ; défaut = grille uniforme
     de k points, position appliquée dans la dérivation de `samples`.
  5. Règle de géométrie §5-6 (H11/Q4) : `a = cell_aspect()` ; si a >= 1 : cell_w = pixel_size
     et cell_h = max(1, floor(pixel_size / a + 0.5)) ; sinon l'inverse. L'aspect > 1 ne
     s'effondre plus en 1×1 (remplace l'arrondi half-to-even).
  6. `_render_frame` : si `render_frame` est implémenté, vérifier la forme
     (rows·cell_h, cols·cell_w, 3) — erreur typée sinon. `prepare_image` reçoit le renderer
     (géométrie correcte pour autre chose que pixel).
  7. `RenderStyle.__post_init__` stocke une copie des options (le mapping mutable du caller
     ne doit pas pouvoir contourner l'invariant 6).
  8. Docstrings §5 : « twelve normative pipeline steps ».
- accept:
  - en mode continu, `render` == étape 5 → étape 12 (bit-à-bit, avec et sans post-effect) ;
    aucun appel de renderer (vérifié par un spy) et aucun CellGrid construit.
  - `pixel` reste bit-identique 1.0 : 20 images aléatoires × 5 palettes flottantes, la suite
    existante (1257) reste verte, témoins bit-à-bit.
  - `subgrid (2, 3)` (stub) : `subindex` a la forme (rows, cols, 6) et la couverture des
    sous-points est monotone à la résolution du sous-point.
  - `sample_points()` : le nombre de points demandé est respecté ; sans la méthode, grille
    uniforme de k points.
  - renderer inconnu dans la spec → `KeyError` nommant le renderer ; style non JSON → `ValueError`.
  - stubs d'aspect 0.5 et 2.0 : la grille préserve l'aspect de la source, cell_w/cell_h
    conformes à la règle §5-6.
  - `render_frame` qui renvoie une mauvaise forme → erreur typée, pas de crash.
  - muter le dict du caller après construction de `RenderStyle` ne change pas le style.

GATE RESULTS (L2b, attempt 2 — batterie complète rejouée par l'orchestrateur, 2026-11-16)
- G1 ruff: clean (repo entier). G2 pytest: **1336 passed, 1 skipped** (1287 + 49 nouveaux ;
  le skip est le smoke manuel). G3 check_contract: OK. G4 : seuls les owns de la carte
  (pipeline.py, cell.py, tests/test_pipeline.py) + l'alignement orchestrateur de
  tests/test_cell.py (DEV-205). G7 témoins bit-à-bit : verts dans la suite. G8 : ["pixel"].
- Vérification orchestrateur : les 30 tests du HEAD (tests/test_pipeline.py) sont tous
  présents (0 manquant), ruff/check_contract verts.

PASS 1 FINDINGS — DISPOSITION (attempt 2)
- blocker « stencil sans origine de cellule » → corrigé : `xi = floor((col + px)·cell_w)`
  clampé sur `[col·cell_w, (col+1)·cell_w − 1]`, idem en y ; l'origine de la cellule est
  multipliée par la taille de cellule. Vérifié : cellule (1,2) échantillonne `lum[2,4]`/`lum[3,5]`
  (l'ancienne formule donnait `lum[1,2]`/`lum[3,3]` = 0).
- blocker « sous-points sur upsample des moyennes » → corrigé : `_to_subpoints` moyenne par
  blocs (cell_w/sx × cell_h/sy) l'image de l'étape 5-7 déjà paddée, puis l'algorithme tourne à
  `(rows·sy, cols·sx)`. Plus d'upsample nearest des moyennes quantifiées.
- major « ~20 tests 1.0 supprimés » → les 30 tests du HEAD sont restaurés à l'identique
  (corps byte-identiques ; seul changement : `@pytest.fixture` → `@pytest.fixture(autouse=True)`),
  et les tests L2b s'y ajoutent (78 cas collectés au total).
- major « stencil défaut = point central k=1 » → défaut = grille uniforme aux centres des
  sous-points `((c+0.5)/sx, (r+0.5)/sy)` quand `subgrid != (1,1)` ; pour `(1,1)` la luma
  moyenne de cellule est conservée (cas ouvert par la revue, documenté).
- major « test de monotonie complaisant » → réécrit : rampe horizontale 256 niveaux, `subindex`
  reaplati en `(rows·sy, cols·sx)`, monotonie le long de x ET assertion que les deux
  sous-points d'une cellule résolvent la rampe.
- major « parité pixel 1×1 » → 20 images seedées × 5 palettes flottantes × pixel_size {1,3},
  attendu calculé indépendamment (`downscale → nearest_index → apply_palette →
  upscale_nearest` sur la source brute), tailles non divisibles.
- minors : docstrings restaurées (vérifié par AST : aucune fonction/classe sans docstring) ;
  `_quantise`/`_subindex`/`_to_subpoints`/`_spans`/`_stencil_points`/`_derive_samples`/
  `_pad_to_cells` extraits de `_finish` ; aucune fonction > 60 lignes (AST) ;
  `_check_continuous` appelé par `prepare_image` ET `_finish` (même ValueError).
- Preuve de non-complaisance (codeur) : sous les maths de l'attempt 1 (monkeypatch), les trois
  tests concernés échouent ; sous le correctif ils passent.

DIFF (arbre de travail vs HEAD — état complet de la carte, attempts 1+2)
diff --git a/lattice_core/cell.py b/lattice_core/cell.py
index 436dd7b..3b8cb8b 100644
--- a/lattice_core/cell.py
+++ b/lattice_core/cell.py
@@ -36,18 +36,25 @@ class RenderStyle:
     options: Mapping[str, object]
 
     def __post_init__(self) -> None:
-        """Reject options that are not serialisable or do not round-trip through JSON."""
+        """Reject options that do not round-trip through JSON, then store a copy."""
         try:
             encoded = json.dumps(dict(self.options))
         except (TypeError, ValueError) as exc:
             raise ValueError(f"render style options are not JSON-serialisable: {exc}") from exc
-        if json.loads(encoded) != dict(self.options):
+        decoded = json.loads(encoded)
+        if decoded != dict(self.options):
             raise ValueError("render style options do not round-trip through JSON without loss")
+        object.__setattr__(self, "options", decoded)
 
 
 @runtime_checkable
 class CellRenderer(Protocol):
-    """How a quantised CellGrid is drawn; the pipeline decides which palette entry."""
+    """How a quantised CellGrid is drawn; the pipeline decides which palette entry.
+
+    Optional capabilities the pipeline probes with getattr (H11): sample_points()
+    returning a (k, 2) stencil of positions in [0, 1] x [0, 1], render_frame()
+    for exact float frames, and layout() for structured export.
+    """
 
     name: str
 
@@ -60,7 +67,8 @@ class CellRenderer(Protocol):
         ...
 
     def consumes(self) -> frozenset[str]:
-        """Return the subset of {"index", "luma", "samples"} this renderer reads."""
+        """Return the subset of {"index", "luma", "samples", "coverage",
+        "subindex"} that this renderer reads."""
         ...
 
     def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
diff --git a/lattice_core/pipeline.py b/lattice_core/pipeline.py
index db7f4e9..5c85f0d 100644
--- a/lattice_core/pipeline.py
+++ b/lattice_core/pipeline.py
@@ -2,6 +2,7 @@
 
 from __future__ import annotations
 
+import math
 from dataclasses import dataclass, field
 from typing import Literal
 
@@ -72,12 +73,14 @@ class PipelineSpec:
     auto_levels: bool = False
     color_metric: str = "srgb"
     pixel_size: int = 1
-    algorithm_id: str = "floyd_steinberg"
+    algorithm_id: str | None = "floyd_steinberg"
     algorithm_params: dict = field(default_factory=dict)
-    palette: PaletteSpec = field(default_factory=PaletteSpec)
+    palette: PaletteSpec | None = field(default_factory=PaletteSpec)
     post_effects: list[EffectInstance] = field(default_factory=list)
     seed: int = 0
     meta: PresetMeta = field(default_factory=PresetMeta)
+    renderer: str = DEFAULT_RENDERER
+    renderer_style: dict = field(default_factory=dict)
 
 
 def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
@@ -89,87 +92,78 @@ def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
 
 def _palette_for(spec: PaletteSpec, img: Image) -> Palette:
     """Build the palette of spec without validating its display order."""
+    if spec.source == "custom":
+        return _rows_to_palette([_hex_row(entry) for entry in spec.colors])
     if spec.source == "builtin":
         from lattice_core.palettes.builtin import get_builtin
 
-        return np.ascontiguousarray(get_builtin(spec.name), dtype=np.float32)
-    if spec.source == "custom":
-        return _palette_from_hex(spec.colors)
-    if spec.source == "extracted":
-        from lattice_core.palettes.extract import MAX_K, MIN_K, extract_palette
-
-        k = int(spec.extract_k)
-        if not MIN_K <= k <= MAX_K:
-            raise ValueError(f"extract_k must be in [{MIN_K}, {MAX_K}], got {k}")
-        locked = _locked_colors(spec.locked)
-        if len(locked) > k:
-            raise ValueError(f"{len(locked)} locked colours exceed extract_k={k}")
-        if len(locked) == k:
-            return _palette_from_hex(locked)
-        wanted = max(MIN_K, k - len(locked))
-        palette = extract_palette(img, wanted, spec.extract_method)
-        rows = [_hex_row(entry) for entry in locked]
-        rows.extend(np.asarray(palette, dtype=np.float32)[: k - len(locked)].tolist())
-        return np.ascontiguousarray(np.array(rows, dtype=np.float32))
-    raise ValueError(f"unknown palette source: {spec.source!r}")
+        return np.ascontiguousarray(get_builtin(spec.name), np.float32)
+    if spec.source != "extracted":
+        raise ValueError(f"unknown palette source: {spec.source!r}")
+    from lattice_core.palettes.extract import MAX_K, MIN_K, extract_palette
+    k = int(spec.extract_k)
+    locked = list(dict.fromkeys(tuple(_hex_row(entry)) for entry in spec.locked))
+    if not MIN_K <= k <= MAX_K:
+        raise ValueError(f"extract_k must be in [{MIN_K}, {MAX_K}], got {k}")
+    if len(locked) > k:
+        raise ValueError(f"{len(locked)} locked colours exceed extract_k={k}")
+    if len(locked) == k:
+        return _rows_to_palette(locked)
+    found = np.asarray(extract_palette(img, max(MIN_K, k - len(locked)), spec.extract_method),
+                       np.float32)
+    return _rows_to_palette(locked + found[: k - len(locked)].tolist())
 
 
 def _validate_order(order: list[int], size: int) -> None:
     """Raise ValueError naming the offending index when order is not a permutation."""
     if not order:
         return
-    seen: set[int] = set()
     for index in order:
         if not 0 <= index < size:
             raise ValueError(f"palette order index {index} is outside [0, {size})")
-        if index in seen:
-            raise ValueError(f"palette order index {index} is repeated")
-        seen.add(index)
+    if len(set(order)) != len(order):
+        raise ValueError(f"palette order index {next(i for i in order if order.count(i) > 1)}"
+                         " is repeated")
     if len(order) != size:
-        missing = sorted(set(range(size)) - seen)[0]
+        missing = sorted(set(range(size)) - set(order))[0]
         raise ValueError(f"palette order is missing index {missing}")
 
 
-def render(
-    src: Image,
-    spec: PipelineSpec,
-    *,
-    max_side: int | None = None,
-    renderer: str = DEFAULT_RENDERER,
-    style: RenderStyle | None = None,
-) -> RGB8:
-    """Render src through the eleven normative pipeline steps and return uint8 RGB."""
+def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
+           renderer: str | None = None, style: RenderStyle | None = None) -> RGB8:
+    """Render src through the twelve normative pipeline steps and return uint8 RGB."""
     work, target = _prepare(src, spec, max_side)
     return _finish(work, target, spec, None, renderer, style)
 
 
-def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> Image:
+def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
+                  renderer: str | None = None) -> Image:
     """Return src after steps 1 to 5, the image palette resolution reads."""
     work, _ = _prepare(src, spec, max_side)
-    cell_w, cell_h = _cell_geometry(get_renderer(DEFAULT_RENDERER), spec.pixel_size)
-    return _to_cells(work, cell_w, cell_h)
-
-
-def render_with_palette(
-    src: Image,
-    spec: PipelineSpec,
-    palette: Palette,
-    *,
-    max_side: int | None = None,
-    renderer: str = DEFAULT_RENDERER,
-    style: RenderStyle | None = None,
-) -> RGB8:
-    """Render src with an already resolved palette, skipping step 5's resolution."""
+    if spec.algorithm_id is None:
+        return np.ascontiguousarray(work, np.float32)
+    name = spec.renderer if renderer is None else renderer
+    return _to_cells(work, *_cell_geometry(get_renderer(name), spec.pixel_size))
+
+
+def render_with_palette(src: Image, spec: PipelineSpec, palette: Palette,
+                        *, max_side: int | None = None, renderer: str | None = None,
+                        style: RenderStyle | None = None) -> RGB8:
+    """Render src with an already resolved palette through the twelve pipeline steps."""
     work, target = _prepare(src, spec, max_side)
     return _finish(work, target, spec, palette, renderer, style)
 
 
-def _prepare(
-    src: Image, spec: PipelineSpec, max_side: int | None
-) -> tuple[Image, tuple[int, int]]:
+def _check_continuous(spec: PipelineSpec) -> None:
+    """Reject a half-null spec: continuous mode needs algorithm_id and palette both None."""
+    if (spec.algorithm_id is None) != (spec.palette is None):
+        raise ValueError("continuous mode needs algorithm_id and palette both None")
+
+
+def _prepare(src: Image, spec: PipelineSpec, max_side: int | None) -> tuple[Image, tuple[int, int]]:
     """Run steps 1 to 5 and return the working image with the target shape of step 1."""
-    work = _as_image(src)
-    work = _proxy(work, max_side)
+    _check_continuous(spec)
+    work = _proxy(_as_image(src), max_side)
     target = work.shape[:2]
     work = _apply_effects(work, spec.pre_effects, spec.seed, 0)
     if spec.auto_levels:
@@ -180,138 +174,205 @@ def _prepare(
     return work, target
 
 
-def _finish(
-    work: Image,
-    target: tuple[int, int],
-    spec: PipelineSpec,
-    palette: Palette | None,
-    renderer_name: str = DEFAULT_RENDERER,
-    style: RenderStyle | None = None,
-) -> RGB8:
-    """Run steps 6 to 12: choose the grid, quantise, render, then the post-effects."""
-    renderer = get_renderer(renderer_name)
+def _as_image(src: Image) -> Image:
+    """Validate the source shape and return it as a contiguous float32 image."""
+    array = np.asarray(src)
+    if array.ndim != 3 or array.shape[2] != 3:
+        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
+    return np.ascontiguousarray(array, np.float32)
+
+
+def _proxy(img: Image, max_side: int | None) -> Image:
+    """Area-downscale img by an integer factor so its longest side is at most max_side."""
+    if max_side is None:
+        return img
+    if max_side < 1:
+        raise ValueError(f"max_side must be >= 1, got {max_side}")
+    longest = max(img.shape[:2])
+    return img if longest <= max_side else color.downscale(img, -(-longest // max_side))
+
+
+def _finish(work: Image, target: tuple[int, int], spec: PipelineSpec, palette: Palette | None,
+            renderer_name: str | None = None, style: RenderStyle | None = None) -> RGB8:
+    """Run steps 6 to 12; in continuous mode (algorithm and palette null) skip 6 to 11."""
+    _check_continuous(spec)
+    frame = work if spec.algorithm_id is None else _quantise(
+        work, spec, palette, renderer_name, style)
+    frame = _apply_effects(frame[: target[0], : target[1]], spec.post_effects, spec.seed,
+                           POST_EFFECT_SEED_OFFSET)
+    return color.to_rgb8(frame)
+
+
+def _quantise(work: Image, spec: PipelineSpec, palette: Palette | None,
+              renderer_name: str | None, style: RenderStyle | None) -> Image:
+    """Run steps 6 to 11: build the grid, dither it and rasterise the renderer frame."""
+    renderer = get_renderer(spec.renderer if renderer_name is None else renderer_name)
+    style = RenderStyle(options=spec.renderer_style) if style is None else style
     cell_w, cell_h = _cell_geometry(renderer, spec.pixel_size)
+    work = _pad_to_cells(work, cell_w, cell_h)
     cells = _to_cells(work, cell_w, cell_h)
     if palette is None:
         palette = resolve_palette(spec.palette, cells)
     info = get_algorithm(spec.algorithm_id)
     params = resolve_params(info.params, spec.algorithm_params)
-    code = color.metric_code(spec.color_metric)
-    params[RESERVED_METRIC] = code
-    indices = info.fn(
-        color.to_working_space(cells, code), color.to_working_space(palette, code), params
+    params[RESERVED_METRIC] = color.metric_code(spec.color_metric)
+    sx, sy = (int(value) for value in renderer.subgrid())
+    if sx < 1 or sy < 1:
+        raise ValueError(f"renderer {renderer.name!r} returned an invalid subgrid {(sx, sy)!r}")
+    size, subgrid = (cell_w, cell_h), (sx, sy)
+    sub = None if subgrid == (1, 1) else _subindex(work, palette, info.fn, params, size, subgrid)
+    grid = _make_grid(cells, _run(info.fn, params, cells, palette), cell_w, cell_h, palette,
+                      samples=_derive_samples(renderer, work, cells, size, subgrid), subindex=sub)
+    return _render_frame(renderer, grid, palette, style)
+
+
+def _run(fn, params: dict, img: Image, palette: Palette) -> np.ndarray:
+    """Run one algorithm function over img in the working space of the colour metric."""
+    code = params[RESERVED_METRIC]
+    out = fn(color.to_working_space(img, code), color.to_working_space(palette, code), params)
+    return np.ascontiguousarray(out, np.int32)
+
+
+def _subindex(work: Image, palette: Palette, fn, params: dict, size: tuple[int, int],
+              subgrid: tuple[int, int]) -> np.ndarray:
+    """Dither the step-5 image at (rows*sy, cols*sx) sub-point resolution (§3, S3)."""
+    sx, sy = subgrid
+    rows, cols = work.shape[0] // size[1], work.shape[1] // size[0]
+    sub = _run(fn, params, _to_subpoints(work, size, subgrid), palette)
+    packed = sub.reshape(rows, sy, cols, sx).transpose(0, 2, 1, 3)
+    return np.ascontiguousarray(packed.reshape(rows, cols, sx * sy), dtype=np.int32)
+
+
+def _to_subpoints(work: Image, size: tuple[int, int], subgrid: tuple[int, int]) -> Image:
+    """Area-average the padded step-5 image onto the (rows*sy, cols*sx) sub-point grid."""
+    (cell_w, cell_h), (sx, sy) = size, subgrid
+    rows, cols = work.shape[0] // cell_h, work.shape[1] // cell_w
+    blocks = work.reshape(rows, cell_h, cols, cell_w, 3)
+    out = np.empty((rows * sy, cols * sx, 3), dtype=np.float32)
+    for i, (y0, y1) in enumerate(_spans(cell_h, sy)):
+        for j, (x0, x1) in enumerate(_spans(cell_w, sx)):
+            out[i::sy, j::sx] = blocks[:, y0:y1, :, x0:x1].mean(axis=(1, 3), dtype=np.float32)
+    return np.ascontiguousarray(out, dtype=np.float32)
+
+
+def _spans(length: int, count: int) -> list[tuple[int, int]]:
+    """Split length pixels into count contiguous [start, end) spans of at least one pixel."""
+    edges = [index * length // count for index in range(count + 1)]
+    return [(start, min(length, max(start + 1, end))) for start, end in zip(edges, edges[1:],
+                                                                           strict=False)]
+
+
+def _derive_samples(renderer: CellRenderer, work: Image, cells: Image, size: tuple[int, int],
+                    subgrid: tuple[int, int]) -> Image:
+    """Return the (rows, cols, k) sub-cell luminance of the SOURCE cell (§3 step 10)."""
+    (cell_w, cell_h) = size
+    points = _stencil_points(renderer, subgrid)
+    if points is None:
+        return np.ascontiguousarray(_linear_luma(cells)[:, :, None], dtype=np.float32)
+    lum = _linear_luma(work)
+    col, row = np.arange(cells.shape[1])[None, :, None], np.arange(cells.shape[0])[:, None, None]
+    x = np.clip(np.floor((col + points[None, :, 0]) * cell_w).astype(np.int64), col * cell_w,
+                (col + 1) * cell_w - 1)
+    y = np.clip(np.floor((row + points[None, :, 1]) * cell_h).astype(np.int64), row * cell_h,
+                (row + 1) * cell_h - 1)
+    return np.ascontiguousarray(lum[y, x], dtype=np.float32)
+
+
+def _stencil_points(renderer: CellRenderer, subgrid: tuple[int, int]) -> np.ndarray | None:
+    """Return the renderer's (k, 2) stencil, or None for the default cell-mean stencil."""
+    stencil = getattr(renderer, "sample_points", None)
+    if callable(stencil):
+        points = np.asarray(stencil(), dtype=np.float32)
+        if points.ndim != 2 or points.shape[1] != 2 or points.shape[0] == 0:
+            raise ValueError(f"renderer {renderer.name!r} sample_points() must be a (k, 2) array")
+        return points
+    if subgrid == (1, 1):
+        return None
+    xs, ys = ((np.arange(n, dtype=np.float32) + 0.5) / n for n in subgrid)
+    return np.ascontiguousarray(
+        np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2), dtype=np.float32
     )
-    grid = _make_grid(cells, indices, cell_w, cell_h, palette)
-    style = RenderStyle(options={}) if style is None else style
-    frame = _render_frame(renderer, grid, palette, style)
-    frame = frame[: target[0], : target[1]]
-    frame = _apply_effects(frame, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
-    return color.to_rgb8(frame)
+
+
+def _linear_luma(img: Image) -> np.ndarray:
+    """Return the linear-light luminance of img as a float32 (H, W) array."""
+    linear = color.srgb_to_linear(img)
+    return np.ascontiguousarray(np.float32(0.2126) * linear[:, :, 0]
+                                + np.float32(0.7152) * linear[:, :, 1]
+                                + np.float32(0.0722) * linear[:, :, 2], dtype=np.float32)
+
+
+def _pad_to_cells(work: Image, cell_w: int, cell_h: int) -> Image:
+    """Replicate the bottom and right edges so the image holds a whole number of cells."""
+    pad_y, pad_x = (-work.shape[0]) % cell_h, (-work.shape[1]) % cell_w
+    if not (pad_y or pad_x):
+        return work
+    return np.pad(work, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")
 
 
 def _cell_geometry(renderer: CellRenderer, pixel_size: int) -> tuple[int, int]:
-    """Return (cell_w, cell_h) from the renderer's cell aspect and the clamped pixel size."""
-    size = _pixel_size(pixel_size)
+    """Return the (cell_w, cell_h) that the §5 step-6 geometry rule gives this renderer."""
+    size = max(MIN_PIXEL_SIZE, min(MAX_PIXEL_SIZE, int(pixel_size)))
     aspect = float(renderer.cell_aspect())
     if not aspect > 0.0:
         raise ValueError(f"renderer {renderer.name!r} returned cell_aspect {aspect!r}")
-    return size, max(1, int(round(size / aspect)))
+    if aspect >= 1.0:
+        return size, max(1, math.floor(size / aspect + 0.5))
+    return max(1, math.floor(size * aspect + 0.5)), size
 
 
 def _to_cells(work: Image, cell_w: int, cell_h: int) -> Image:
-    """Step 7: downscale the prepared image to the grid of cell_w x cell_h blocks."""
+    """Average every cell_w x cell_h block of work into one cell colour."""
     if cell_w == cell_h:
         return color.downscale(work, cell_w)
-    pad_y = (-work.shape[0]) % cell_h
-    pad_x = (-work.shape[1]) % cell_w
-    if pad_y or pad_x:
-        work = np.pad(work, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")
-    rows = work.shape[0] // cell_h
-    cols = work.shape[1] // cell_w
-    blocks = work.reshape(rows, cell_h, cols, cell_w, 3)
+    work = _pad_to_cells(work, cell_w, cell_h)
+    blocks = work.reshape(work.shape[0] // cell_h, cell_h, work.shape[1] // cell_w, cell_w, 3)
     return np.ascontiguousarray(blocks.mean(axis=(1, 3), dtype=np.float32))
 
 
-def _render_frame(
-    renderer: CellRenderer, grid: CellGrid, palette: Palette, style: RenderStyle
-) -> Image:
-    """Return the step-11 frame as float32, skipping the uint8 round-trip when exact."""
+def _render_frame(renderer: CellRenderer, grid: CellGrid, palette: Palette,
+                  style: RenderStyle) -> Image:
+    """Return the renderer's frame, using render_frame when the renderer implements it."""
     exact = getattr(renderer, "render_frame", None)
-    if callable(exact):
-        return np.ascontiguousarray(np.asarray(exact(grid, palette, style), dtype=np.float32))
-    return color.to_float(renderer.render(grid, palette, style))
-
-
-def _make_grid(
-    work: Image, indices: np.ndarray, cell_w: int, cell_h: int, palette: Palette
-) -> CellGrid:
-    """Build the CellGrid of step 10: index, coverage, luma and samples per cell."""
-    rows, cols = indices.shape
-    linear = color.srgb_to_linear(work)
-    luma = (
-        np.float32(0.2126) * linear[:, :, 0]
-        + np.float32(0.7152) * linear[:, :, 1]
-        + np.float32(0.0722) * linear[:, :, 2]
-    ).astype(np.float32)
-    samples = luma[:, :, None].copy()
-    coverage = _coverage_table(palette)[np.ascontiguousarray(indices, dtype=np.int32)]
+    if not callable(exact):
+        return color.to_float(renderer.render(grid, palette, style))
+    frame = np.ascontiguousarray(np.asarray(exact(grid, palette, style), dtype=np.float32))
+    expected = (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
+    if frame.shape != expected:
+        raise ValueError(f"render_frame returned shape {frame.shape}, expected {expected}")
+    return frame
+
+
+def _make_grid(work: Image, indices: np.ndarray, cell_w: int, cell_h: int, palette: Palette,
+               *, samples: Image | None = None, subindex: np.ndarray | None = None) -> CellGrid:
+    """Assemble the CellGrid handed to the renderer from the dithered cell image."""
+    luma = _linear_luma(work)
+    if samples is None:
+        samples = luma[:, :, None]
     return CellGrid(
-        cols=cols,
-        rows=rows,
-        cell_w=cell_w,
-        cell_h=cell_h,
+        cols=indices.shape[1], rows=indices.shape[0], cell_w=cell_w, cell_h=cell_h,
         index=np.ascontiguousarray(indices, dtype=np.int32),
-        coverage=np.ascontiguousarray(coverage, dtype=np.float32),
+        coverage=np.ascontiguousarray(_coverage_table(palette)[indices], dtype=np.float32),
         luma=np.ascontiguousarray(luma, dtype=np.float32),
-        samples=np.ascontiguousarray(samples, dtype=np.float32),
+        samples=np.ascontiguousarray(samples, np.float32),
+        subindex=np.ascontiguousarray(subindex, dtype=np.int32) if subindex is not None else None,
     )
 
 
 def _coverage_table(palette: Palette) -> np.ndarray:
-    """Derive ink coverage per palette entry, 0.0 on a single-luminance palette."""
+    """Return the ink coverage of every palette entry, from linear-light luminance."""
     linear = color.srgb_to_linear(palette)
-    lum = (
-        np.float32(0.2126) * linear[:, 0]
-        + np.float32(0.7152) * linear[:, 1]
-        + np.float32(0.0722) * linear[:, 2]
-    )
-    lum_min = float(lum.min())
-    lum_max = float(lum.max())
+    lum = (np.float32(0.2126) * linear[:, 0] + np.float32(0.7152) * linear[:, 1]
+           + np.float32(0.0722) * linear[:, 2])
+    lum_min, lum_max = float(lum.min()), float(lum.max())
     if lum_max == lum_min:
         return np.zeros(palette.shape[0], dtype=np.float32)
     return np.ascontiguousarray(((lum - lum_min) / (lum_max - lum_min)).astype(np.float32))
 
 
-def _as_image(src: Image) -> Image:
-    """Validate the source shape and return it as a contiguous float32 image."""
-    array = np.asarray(src)
-    if array.ndim != 3 or array.shape[2] != 3:
-        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
-    return np.ascontiguousarray(array, dtype=np.float32)
-
-
-def _proxy(img: Image, max_side: int | None) -> Image:
-    """Area-downscale img by an integer factor so its longest side is at most max_side."""
-    if max_side is None:
-        return img
-    if max_side < 1:
-        raise ValueError(f"max_side must be >= 1, got {max_side}")
-    longest = max(img.shape[:2])
-    if longest <= max_side:
-        return img
-    factor = -(-longest // max_side)
-    return color.downscale(img, factor)
-
-
-def _pixel_size(value: int) -> int:
-    """Clamp pixel_size to the contract range 1..32."""
-    return max(MIN_PIXEL_SIZE, min(MAX_PIXEL_SIZE, int(value)))
-
-
 def _apply_effects(img: Image, instances: list[EffectInstance], seed: int, offset: int) -> Image:
     """Run the enabled effects in order, seeding the i-th enabled one with seed + offset + i."""
-    out = img
-    index = 0
+    out, index = img, 0
     for instance in instances:
         if not instance.enabled:
             continue
@@ -323,35 +384,17 @@ def _apply_effects(img: Image, instances: list[EffectInstance], seed: int, offse
     return out
 
 
-def _hex_text(entry: object) -> str:
-    """Return entry as an uppercase "#RRGGBB" string, or raise ValueError."""
+def _hex_row(entry: object) -> list[float]:
+    """Parse one "#RRGGBB" colour into a float32 RGB row, or raise ValueError."""
     text = str(entry).strip().lstrip("#")
     if len(text) != 6 or not _HEX_DIGITS.issuperset(text):
         raise ValueError(f"invalid palette colour: {entry!r}")
-    return "#" + text.upper()
-
-
-def _hex_row(entry: object) -> list[float]:
-    """Parse one colour into a float32 RGB row."""
-    text = _hex_text(entry)[1:]
     return [int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
 
 
-def _locked_colors(values: list[str]) -> list[str]:
-    """Return the locked colours as unique uppercase "#RRGGBB" strings, in order."""
-    unique: list[str] = []
-    for entry in values:
-        text = _hex_text(entry)
-        if text not in unique:
-            unique.append(text)
-    return unique
-
-
-def _palette_from_hex(colors: list[str]) -> Palette:
-    """Parse "#RRGGBB" strings into a float32 palette, validating count and syntax."""
-    if not MIN_PALETTE_SIZE <= len(colors) <= MAX_PALETTE_SIZE:
-        raise ValueError(
-            f"a palette needs {MIN_PALETTE_SIZE} to {MAX_PALETTE_SIZE} colours, got {len(colors)}"
-        )
-    rows = [_hex_row(entry) for entry in colors]
+def _rows_to_palette(rows: list) -> Palette:
+    """Build a float32 (K, 3) palette from parsed RGB rows, validating the count."""
+    if not MIN_PALETTE_SIZE <= len(rows) <= MAX_PALETTE_SIZE:
+        raise ValueError(f"a palette needs {MIN_PALETTE_SIZE}-{MAX_PALETTE_SIZE} colours, "
+                         f"got {len(rows)}")
     return np.ascontiguousarray(np.array(rows, dtype=np.float32))
diff --git a/tests/test_pipeline.py b/tests/test_pipeline.py
index 7879373..a9700ff 100644
--- a/tests/test_pipeline.py
+++ b/tests/test_pipeline.py
@@ -1,19 +1,28 @@
-"""Tests for the render pipeline (T09), using test-only registry entries."""
+"""Tests for the render pipeline (T09 and §3/§5 L2b), using test-only registry entries."""
 
 from __future__ import annotations
 
+import json
 import sys
 import types
+from contextlib import contextmanager
 
 import numpy as np
 import pytest
 
-from lattice_core import color, pipeline, registry
+import lattice_core.cell as cell_module
+import lattice_core.pipeline as pipeline
+from lattice_core import color, registry
+from lattice_core.cell import RenderStyle, register_renderer
 from lattice_core.pipeline import (
+    POST_EFFECT_SEED_OFFSET,
     EffectInstance,
     PaletteSpec,
     PipelineSpec,
+    _coverage_table,
+    prepare_image,
     render,
+    render_with_palette,
     resolve_palette,
 )
 from lattice_core.registry import AlgorithmInfo, EffectInfo
@@ -68,7 +77,7 @@ def _constant(value: float):
     return effect
 
 
-@pytest.fixture
+@pytest.fixture(autouse=True)
 def test_registry(monkeypatch):
     """Register test-only algorithms and effects by patching the registry dicts."""
     algorithms = {
@@ -363,3 +372,312 @@ def test_disabled_effect_does_not_shift_the_seed(test_registry, field):
     alone = render(src, _spec(**{field: [noise]}))
     shifted = render(src, _spec(**{field: [disabled, noise]}))
     assert np.array_equal(alone, shifted)
+
+
+# ---------------------------------------------------------------------------
+# L2b (§3/§5 H11): continuous mode, sub-points, geometry, stencil, render_frame
+# ---------------------------------------------------------------------------
+
+BW_FLOAT = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+
+
+def _bw_palette() -> np.ndarray:
+    """The BW palette as the float32 array the renderer receives."""
+    return BW_FLOAT.copy()
+
+
+class _Stub:
+    """Configurable stub renderer for the pipeline tests, recording every grid."""
+
+    def __init__(self, name, aspect=1.0, subgrid=(1, 1), points=None,
+                 forbid=False, bad_frame=False):
+        self.name = name
+        self._aspect, self._subgrid = aspect, subgrid
+        self._points, self._forbid = points, forbid
+        self._bad_frame = bad_frame
+        self.calls, self.grid, self.style = 0, None, None
+        if points is not None:
+            self.sample_points = self._sample_points
+        if forbid or bad_frame:
+            self.render_frame = self._render_frame
+
+    def _sample_points(self):
+        return list(self._points)
+
+    def _render_frame(self, grid, palette, style):
+        if self._forbid:
+            raise AssertionError(f"{self.name}.render_frame called")
+        return np.zeros((1, 1, 3), dtype=np.float32)
+
+    def cell_aspect(self):
+        return self._aspect
+
+    def subgrid(self):
+        return self._subgrid
+
+    def consumes(self):
+        return frozenset({"index"})
+
+    def render(self, grid, palette, style):
+        if self._forbid:
+            raise AssertionError(f"{self.name}.render called")
+        self.calls += 1
+        self.grid = grid
+        self.style = style
+        blank = np.zeros((grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3), dtype=np.uint8)
+        return color.to_pil(blank)
+
+
+@contextmanager
+def _registered(renderer):
+    """Register a stub renderer for the block, then unregister it."""
+    register_renderer(renderer)
+    try:
+        yield
+    finally:
+        cell_module._RENDERERS.pop(renderer.name, None)
+
+
+def _luma(img: np.ndarray) -> np.ndarray:
+    """Linear-light luminance of a float32 image, as the pipeline computes it."""
+    linear = color.srgb_to_linear(img)
+    return (0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1]
+            + 0.0722 * linear[:, :, 2]).astype(np.float32)
+
+
+def _render_grid(aspect, src, pixel_size, subgrid=(1, 1), points=None):
+    """Render src through a stub renderer of the given aspect and return its grid."""
+    spy = _Stub(f"geom_{aspect}_{subgrid}_{pixel_size}", aspect=aspect, subgrid=subgrid,
+                points=points)
+    with _registered(spy):
+        render_with_palette(src, _spec(pixel_size=pixel_size), _bw_palette(), renderer=spy.name)
+    return spy.grid
+
+
+def test_continuous_mode_matches_step5_to_post():
+    """Continuous mode sends the step-5 image straight to the post-effects, bit for bit."""
+    src = _image(24, 20)
+    spec = PipelineSpec(algorithm_id=None, palette=None)
+    work = prepare_image(src, spec)
+    assert np.array_equal(render(src, spec), color.to_rgb8(work))
+    noisy = PipelineSpec(
+        algorithm_id=None, palette=None,
+        post_effects=[EffectInstance("test_noise", {"amount": 1.0})],
+    )
+    rng = np.random.default_rng(POST_EFFECT_SEED_OFFSET)
+    field = rng.random(work.shape[:2], dtype=np.float32)[:, :, None]
+    expected = color.to_rgb8(np.clip(work + field, 0.0, 1.0))
+    assert np.array_equal(render(src, noisy), expected)
+
+
+def test_continuous_mode_calls_no_renderer_and_builds_no_grid(monkeypatch):
+    """No CellGrid is built and no renderer is called when algorithm and palette are null."""
+    built = []
+    monkeypatch.setattr(pipeline, "CellGrid", lambda *a, **k: built.append(k))
+    with _registered(_Stub("never", forbid=True)):
+        out = render(_image(16, 16),
+                     PipelineSpec(algorithm_id=None, palette=None, renderer="never"))
+    assert built == []
+    assert out.shape == (16, 16, 3)
+
+
+@pytest.mark.parametrize("kw", [{"algorithm_id": None}, {"palette": None}])
+def test_half_null_spec_is_rejected_by_both_entry_points(kw):
+    """prepare_image and render both reject a half-null spec with the same ValueError."""
+    spec = PipelineSpec(**kw)
+    with pytest.raises(ValueError, match="continuous mode"):
+        render(_image(), spec)
+    with pytest.raises(ValueError, match="continuous mode"):
+        prepare_image(_image(), spec)
+
+
+def test_spec_renderer_and_style_reach_the_pipeline():
+    """PipelineSpec.renderer and renderer_style are propagated to the renderer."""
+    spy = _Stub("spec_renderer")
+    with _registered(spy):
+        out = render(_image(16, 16),
+                     _spec(pixel_size=2, renderer="spec_renderer", renderer_style={"scale": 2}))
+    assert out.shape == (16, 16, 3)
+    assert spy.calls == 1 and (spy.grid.cell_w, spy.grid.cell_h) == (2, 2)
+    assert spy.style.options == {"scale": 2}
+
+
+def test_explicit_renderer_argument_overrides_the_spec():
+    """The renderer keyword argument wins over PipelineSpec.renderer."""
+    spy = _Stub("explicit_renderer")
+    with _registered(spy):
+        render(_image(12, 12), _spec(renderer="pixel"), renderer="explicit_renderer")
+    assert spy.calls == 1
+
+
+@pytest.mark.parametrize(
+    "overrides,exc_type,match",
+    [({"renderer": "nope"}, KeyError, "nope"),
+     ({"renderer_style": {"x": object()}}, ValueError, "render style")],
+)
+def test_invalid_renderer_spec_raises(overrides, exc_type, match):
+    """An unknown renderer name is a KeyError; a non-JSON style is a ValueError."""
+    with pytest.raises(exc_type) as exc:
+        render(_image(), _spec(**overrides))
+    assert match in str(exc.value)
+
+
+def test_subindices_have_the_subgrid_shape_and_dtype():
+    """A (2, 3) subgrid fills subindex with (rows, cols, 6) int32."""
+    grid = _render_grid(1.0, _image(16, 20), 2, subgrid=(2, 3))
+    assert grid.subindex is not None
+    assert grid.subindex.shape == (grid.rows, grid.cols, 6)
+    assert grid.subindex.dtype == np.int32
+
+
+def test_subindices_carry_detail_from_inside_the_cell():
+    """A horizontal edge inside one cell gives different sub-indices on its two rows."""
+    src = np.zeros((8, 8, 3), dtype=np.float32)
+    src[2:] = 1.0
+    grid = _render_grid(1.0, src, 4, subgrid=(1, 2))
+    assert grid.subindex.shape == (2, 2, 2)
+    top, bottom = grid.subindex[0, 0]
+    assert top != bottom, "sub-points of one cell must not all share one index"
+
+
+def test_subpoint_coverage_is_monotone_along_a_source_ramp():
+    """Sub-point coverage rises along x on a ramp, including inside a single cell."""
+    palette = np.array([[v / 255.0] * 3 for v in range(256)], dtype=np.float32)
+    ramp = np.repeat(np.linspace(0.0, 1.0, 20, dtype=np.float32)[None, :, None], 8, axis=0)
+    src = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
+    spy = _Stub("sub_mono", subgrid=(2, 3))
+    with _registered(spy):
+        render_with_palette(src, _spec(pixel_size=2), palette, renderer="sub_mono")
+    grid = spy.grid
+    flat = grid.subindex.reshape(grid.rows, grid.cols, 3, 2).transpose(0, 2, 1, 3)
+    covers = _coverage_table(palette)[flat.reshape(grid.rows * 3, grid.cols * 2)]
+    assert np.all(np.diff(covers, axis=1) >= 0), "coverage must not fall along the ramp"
+    inside = np.diff(covers.reshape(grid.rows * 3, grid.cols, 2), axis=2)
+    assert np.any(inside > 0), "the two sub-points of a cell must resolve the ramp"
+
+
+def test_no_subindex_when_subgrid_is_one():
+    """A (1, 1) renderer receives subindex None."""
+    spy = _Stub("no_sub")
+    with _registered(spy):
+        render_with_palette(_image(16, 16), _spec(pixel_size=2), _bw_palette(), renderer="no_sub")
+    assert spy.grid.subindex is None
+
+
+def test_sample_points_count_and_positions_are_respected():
+    """An explicit sample_points() stencil sets k and the sampled source positions."""
+    points = [(0.25, 0.25), (0.75, 0.75)]
+    src = np.zeros((8, 8, 3), dtype=np.float32)
+    src[0, 0] = 1.0
+    src[1, 1] = 0.5
+    spy = _Stub("stencil_pos", points=points)
+    with _registered(spy):
+        render_with_palette(src, _spec(pixel_size=2), _bw_palette(), renderer="stencil_pos")
+    lum = _luma(src)
+    assert spy.grid.samples.shape == (4, 4, 2)
+    assert spy.grid.samples[0, 0, 0] == pytest.approx(lum[0, 0], abs=1e-6)
+    assert spy.grid.samples[0, 0, 1] == pytest.approx(lum[1, 1], abs=1e-6)
+
+
+def test_stencil_positions_include_the_cell_origin():
+    """Cell (1, 2) samples inside its own cell, not at the top-left of the image."""
+    src = np.zeros((8, 8, 3), dtype=np.float32)
+    src[2, 4] = 1.0
+    spy = _Stub("stencil_origin", points=[(0.25, 0.25)])
+    with _registered(spy):
+        render_with_palette(src, _spec(pixel_size=2), _bw_palette(), renderer="stencil_origin")
+    lum = _luma(src)
+    samples = spy.grid.samples
+    assert samples.shape == (4, 4, 1)
+    assert samples[1, 2, 0] == pytest.approx(lum[2, 4], abs=1e-6)
+    assert samples[1, 2, 0] > 0.0
+    assert samples[0, 0, 0] == pytest.approx(0.0, abs=1e-6)
+
+
+def test_default_stencil_is_the_cell_mean_luma_for_a_pixel_renderer():
+    """Without sample_points() and subgrid (1, 1), samples hold the source cell mean luma."""
+    src = np.zeros((9, 9, 3), dtype=np.float32)
+    src[1, 1] = 1.0
+    spy = _Stub("stencil_default")
+    with _registered(spy):
+        render_with_palette(src, _spec(pixel_size=3), _bw_palette(), renderer="stencil_default")
+    cells = prepare_image(src, _spec(pixel_size=3))
+    assert spy.grid.samples.shape == (3, 3, 1)
+    assert spy.grid.samples[0, 0, 0] == pytest.approx(_luma(cells)[0, 0], abs=1e-6)
+
+
+def test_default_stencil_for_a_subgrid_renderer_is_the_uniform_sx_by_sy_grid():
+    """Without sample_points(), a (2, 3) renderer gets k = 6 points at the sub-point centres."""
+    src = np.zeros((12, 12, 3), dtype=np.float32)
+    src[:, 0] = 1.0
+    spy = _Stub("stencil_uniform", subgrid=(2, 3))
+    with _registered(spy):
+        render_with_palette(src, _spec(pixel_size=2), _bw_palette(), renderer="stencil_uniform")
+    samples = spy.grid.samples
+    assert samples.shape == (spy.grid.rows, spy.grid.cols, 6)
+    left, right = samples[0, 0, ::2], samples[0, 0, 1::2]
+    assert np.allclose(left, 1.0, atol=1e-6), "the left sub-points sit on the white column"
+    assert np.allclose(right, 0.0, atol=1e-6), "the right sub-points sit on the black columns"
+
+
+@pytest.mark.parametrize(
+    "aspect,pixel_size,expected",
+    [(0.5, 4, (2, 4)), (2.0, 4, (4, 2)), (0.5, 1, (1, 1)), (2.0, 1, (1, 1)), (1.0, 3, (3, 3))],
+)
+def test_geometry_follows_the_h11_rule(aspect, pixel_size, expected):
+    """cell_w/cell_h follow the §5 step-6 rule and the grid preserves the source aspect."""
+    src = np.full((20, 30, 3), 0.5, dtype=np.float32)
+    grid = _render_grid(aspect, src, pixel_size)
+    assert (grid.cell_w, grid.cell_h) == expected
+    ratio = (grid.cols * grid.cell_w) / (grid.rows * grid.cell_h)
+    assert ratio == pytest.approx(30 / 20, rel=0.1)
+
+
+def test_render_frame_wrong_shape_is_a_typed_error():
+    """A render_frame of the wrong shape raises ValueError, not an IndexError."""
+    with _registered(_Stub("bad_frame", bad_frame=True)):
+        with pytest.raises(ValueError, match="render_frame returned shape"):
+            render_with_palette(_image(16, 16), _spec(pixel_size=2), _bw_palette(),
+                                renderer="bad_frame")
+
+
+def test_style_stores_a_copy_of_the_caller_options():
+    """Mutating the caller dict after construction does not change the style."""
+    options = {"scale": 1, "fg": "#ffffff"}
+    style = RenderStyle(options=options)
+    options["scale"] = 99
+    assert style.options == {"scale": 1, "fg": "#ffffff"}
+    assert json.loads(json.dumps(dict(style.options))) == style.options
+
+
+@pytest.mark.parametrize("pixel_size", [1, 2, 3, 5])
+@pytest.mark.parametrize("palette_id", range(5))
+def test_pixel_renderer_matches_the_frozen_1_0_path(pixel_size, palette_id):
+    """pixel reproduces downscale → nearest_index → apply_palette → upscale_nearest exactly."""
+    rng = np.random.default_rng(1000 + palette_id)
+    src = np.ascontiguousarray(rng.random((37, 23, 3), dtype=np.float32))
+    palette = np.ascontiguousarray(rng.random((4 + palette_id, 3), dtype=np.float32))
+    cells = color.downscale(src, pixel_size)
+    idx = color.nearest_index(cells, palette)
+    want = color.upscale_nearest(color.apply_palette(idx, palette), pixel_size, (37, 23))
+    spec = _spec(pixel_size=pixel_size, palette=PaletteSpec(source="custom", colors=GREYS[:4]))
+    assert np.array_equal(render_with_palette(src, spec, palette), color.to_rgb8(want))
+
+
+def test_pixel_renderer_matches_twenty_random_images_and_five_palettes():
+    """20 seeded images x 5 float palettes stay bit-identical to the 1.0 render path."""
+    rng = np.random.default_rng(4242)
+    palettes = [np.ascontiguousarray(rng.random((k, 3), dtype=np.float32))
+                for k in (2, 3, 5, 8, 16)]
+    for index in range(20):
+        height, width = 11 + index, 7 + index * 2
+        src = np.ascontiguousarray(rng.random((height, width, 3), dtype=np.float32))
+        for pixel_size in (1, 3):
+            cells = color.downscale(src, pixel_size)
+            for palette in palettes:
+                idx = color.nearest_index(cells, palette)
+                want = color.upscale_nearest(color.apply_palette(idx, palette), pixel_size,
+                                             (height, width))
+                spec = _spec(pixel_size=pixel_size)
+                got = render_with_palette(src, spec, palette)
+                assert np.array_equal(got, color.to_rgb8(want))

CODER NOTES AND DEVIATIONS (L2b, attempt 2, deepseek-v4-1-flash-1017)
- cell.py inchangé cette passe (RenderStyle.__post_init__ copiant les options = fermeture de
  l'invariant 6, déjà en place à l'attempt 1).
- Aucune déviation E1–E9 déclarée à l'attempt 2. `_palette_from_hex` supprimé (inliné dans
  `_rows_to_palette`) pour tenir la limite 400 lignes — privé, aucune signature publique
  touchée, pipeline.py à 400 lignes pile.
- Hors périmètre, non traité (non possédé) : `presets.py` `from_json` ignore encore
  `renderer`/`renderer_style` — à la carte L4 (deps L2b).
- `ruff format --check` n'est pas une gate (le HEAD lui-même ne le passe pas) ; `ruff check`
  est clean.
- Puces DEV : DEV-205 = alignement tests/test_cell.py sur la règle H11 (test géométrie
  pixel_size 1→2), DEV-203/204 inchangés.
