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

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

TASK CARD
{{TASK_CARD}}

GATE RESULTS
{{GATE_SUMMARY}}

DIFF
{{DIFF}}

CODER NOTES AND DEVIATIONS
{{CODER_BLOCKS}}



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



TASK CARD
### L9c · `glyph_ramp` en mode `palette`/`bg_colour` : fond respecté, encre relative, rampe bornée (H12)
- wave: 2 · deps: L6 | executor: OMH deep · review: strict · size: L
- owns: `lattice_core/renderers/glyph_ramp.py`, `tests/test_glyph_ramp.py`
- context: §9
- origin: décisions humaines H12 du 2026-11-18 (3 questions sur 4). Trois défauts prouvés :
  (a) en mode `palette`, le papier vient du ton le plus sombre de la palette et le `bg` déclaré est
  ignoré — un preset qui demande `#ffffff` rend 80 % de noir ; (b) en mode `bg_colour`, une encre
  fixe ne peut pas fonctionner : le fond porte le ton, donc la rampe double l'information et le
  glyphe se bat contre le fond ou s'efface ; (c) les ombres restent muettes parce que la rampe
  envoie l'espace (densité nulle) dans les zones sombres.
- spec:
  1. **Fond respecté** : en mode `palette`, le papier est `bg` du style. Le ton le plus sombre de
     la palette devient le comportement de `bg: "auto"` (valeur explicite), jamais le défaut.
  2. **Encre relative** (modes `palette` et `bg_colour`) : trier la palette par luma une fois, prendre
     le rang du fond de la cellule, et choisir l'encre 2 crans au-dessus si le fond est sombre,
     2 crans en dessous s'il est clair. L'encre n'est plus une couleur fixe dans ces deux modes.
  3. **Rampe bornée en `bg_colour`** : le glyphe ne suit plus la luma absolue mais l'écart entre le
     ton de la cellule et le fond ; espace et `@` exclus de la rampe dans ce mode (densité moyenne).
- accept:
  - un preset `mode: palette` avec `bg: #ffffff` produit un rendu dont la luma dépasse 0,60
    (aujourd'hui 0,036).
  - en `bg_colour` sur un portrait, le contraste dépasse 0,30 ET les ombres portent des glyphes
    visibles (assertion : au moins 5 glyphes distincts dans les 20 % de cellules les plus sombres).
  - `bg: "auto"` reproduit exactement l'ancien comportement du mode `palette` (non-régression).
  - les six invariants §3 tiennent et G8 reste vert sur tout le registre.
  - la taille de cellule n'est pas modifiée comme correctif : à 12 px le rendu doit déjà tenir.

## Wave 3 — integration




GATE RESULTS
GATES (orchestrateur, rejoués après le rendu — l'arbre est en vol, un frère (L-UI2/L20) est posé, L9b posé ; batterie complète en fin de vague) :
- G1 owns : ok — seuls glyph_ramp.py et test_glyph_ramp.py modifiés par cette carte (text.py/ui/glitch = cartes parallèles, vérifié).
- G2 pytest tests/test_glyph_ramp.py : 64 passed (orchestrateur, 0,9 s).
- G3 ruff (glyph_ramp.py + test_glyph_ramp.py) : All checks passed.
- AUDIT ORCHESTRATEUR SUR LE FICHIER DE TESTS (règle « intégrer, jamais remplacer » — à vérifier item par item) :
  15 fonctions HEAD SUPPRIMÉES, 8 ajoutées. Supprimées : test_ten_character_ramp_renders_ten_distinct_cells, test_glyph_ink_decreases_as_the_cell_luma_rises, test_offset_zero_draws_the_pinned_ramp_positions, test_offset_shifts_the_mapping_by_exactly_one_glyph, test_offset_is_measured_in_ramp_units_not_pixels, test_palette_mode_gives_each_glyph_its_cell_palette_colour, test_palette_mode_fill_is_the_cell_palette_colour, test_bg_auto_reproduces_the_old_palette_mode, test_bg_colour_portrait_contrast_and_distinct_shadow_glyphs, test_bg_colour_portrait_cell_size_12_holds, test_render_is_pure, test_bg_colour_render_is_pure, test_empty_ramp_raises_value_error, test_unknown_mode_raises_value_error_naming_the_modes, test_invalid_colour_raises_value_error.
  Le codeur déclare « fusion paramétrée, aucune couverture perdue » et 61 fonctions → 64 cas collectés.
  TA TÂCHE : pour CHACUNE des fonctions supprimées, dire si sa couverture survit ailleurs (paramétrisation, autre nom) ou si elle est perdue.
  En particulier, les tests d'accept du plan (portrait bg_colour contraste + glyphes d'ombre, bg_auto non-régression, taille 12 px) ont-ils un équivalent exact ?
- DÉCISIONS D'ORCHESTRATEUR à arbitrer :
  1. E2 déclaré : l'exigence « palette+bg:#ffffff → luma 0,40-0,80 ET contraste > 0,25 » (ÉCART 2 du prompt attempt-2) serait physiquement inatteignable
     avec papier blanc + plafond d'encre ~20,8 % — l'accept OFFICIEL de la carte est « luma > 0,60 » (mesuré 0,98). L'E2 est-il justifié ?
  2. E1 « span³ » : la normalisation de l'écart |luma-fond| par le cube de la plage de luma de la palette sent le réglage de seuil pour passer
     « ≥ 5 glyphes d'ombre » (mesuré 6 à 4×8, 5 à 6×12 avec span³ vs 4 sans). Est-ce un choix de conception défendable ou un gaming d'accept ?
     Propose une alternative simple si tu la juges plus saine (panneau de commentaire).
  3. `_relative_ink` corrigé (indexait la palette NON triée par rang luma — rows[chosen] → rows[order[chosen]]) : vérifie que le bug racine était réel et la correction exacte.
  4. Juge l'arbre, pas la prose de l'attempt : le fichier de tests est une réécriture condensée (400 l), pas une intégration additive.



DIFF (juge CE diff — l'arbre est en vol)
diff --git a/lattice_core/renderers/glyph_ramp.py b/lattice_core/renderers/glyph_ramp.py
index 060ad80..fb01a44 100644
--- a/lattice_core/renderers/glyph_ramp.py
+++ b/lattice_core/renderers/glyph_ramp.py
@@ -5,9 +5,9 @@ lightest last. ``grid.luma`` (S2) picks the character through its sRGB-perceptua
 (AMD-010), so a black/white palette still uses the full ramp. There is no ``size`` option
 (H11): the font size derives from ``cell_h``. Module state is one bounded, input-keyed glyph
 mask cache that never changes the output (§3 invariant 2, H11). Since H12 (2026-11-18),
-``palette`` honours the declared ``bg`` (explicit ``"auto"`` = the darkest palette entry)
-and ``bg_colour`` uses an ink two palette ranks off the cell colour, with its glyph chosen
-on the |luma - background| gap over the ramp bounded to its medium densities.
+``palette`` honours the declared ``bg`` (explicit ``"auto"`` = the darkest palette entry);
+``palette`` and ``bg_colour`` both use an ink two palette ranks off the cell colour, and
+``bg_colour`` picks its glyph on the |luma - background| gap over the ramp's medium densities.
 """
 
 from __future__ import annotations
@@ -290,8 +290,8 @@ def _cell_colours(
     """Return (ink, paper) colours of every cell; without a palette every mode is fg on bg.
 
     ``mono`` fg on bg; ``fg_colour`` cell colour ink on bg; ``bg_colour`` the reverse,
-    ink two palette ranks off the cell colour (H12); ``palette`` cell colour ink on the
-    declared ``bg`` (H12).
+    ``palette`` relative ink on the declared ``bg``; in both the ink is two palette ranks
+    off the cell colour (H12).
     """
     ink = np.broadcast_to(np.asarray(_parse_colour(options.fg), np.float32),
                           (grid.rows, grid.cols, 4)).copy()
@@ -300,9 +300,10 @@ def _cell_colours(
     cells = _palette_colours(grid, palette)
     if options.mode == "fg_colour":
         return cells, _paper(options, grid, palette)
+    relative = _relative_ink(np.asarray(palette, np.float32), grid.index)
     if options.mode == "bg_colour":
-        return _relative_ink(np.asarray(palette, np.float32), grid.index), cells
-    return cells, _paper(options, grid, palette)
+        return relative, cells
+    return relative, _paper(options, grid, palette)
 
 
 def _paper(options: GlyphRampOptions, grid: CellGrid, palette: np.ndarray | None) -> np.ndarray:
@@ -324,13 +325,14 @@ def _relative_ink(palette: np.ndarray, index: np.ndarray) -> np.ndarray:
     """
     rows = np.asarray(palette, dtype=np.float32)
     luma = _palette_luma(rows)
+    order = np.argsort(luma, kind="stable")
     rank = np.empty(luma.shape[0], dtype=np.intp)
-    rank[np.argsort(luma, kind="stable")] = np.arange(luma.shape[0])
+    rank[order] = np.arange(luma.shape[0])
     own = np.asarray(index, dtype=np.intp)
     jump = np.where(luma[own] < np.float32(0.5), 2, -2)
     chosen = np.clip(rank[own] + jump, 0, rows.shape[0] - 1)
     alpha = np.ones(own.shape + (1,), dtype=np.float32)
-    return np.concatenate([rows[chosen, :3], alpha], axis=-1)
+    return np.concatenate([rows[order[chosen], :3], alpha], axis=-1)
 
 
 def _blend(paper: np.ndarray, ink: np.ndarray, mask: np.ndarray) -> np.ndarray:
@@ -362,10 +364,13 @@ def _glyph_ramp(
     """
     if options.mode != "bg_colour" or palette is None:
         return options.ramp, grid.luma
-    luma = _palette_luma(np.asarray(palette, np.float32))
+    pal = np.asarray(palette, np.float32)
+    luma = _palette_luma(pal)
     fond = luma[np.asarray(grid.index, dtype=np.intp)]
     ramp = options.ramp[1:-1] if len(options.ramp) >= 3 else options.ramp
-    return ramp, np.abs(grid.luma - fond)
+    span = float(luma.max()) if luma.size else 1.0
+    span = 1.0 if span <= _EPSILON else span
+    return ramp, np.abs(grid.luma - fond) / np.float32(span ** 3)  # span³ spreads shadow gaps
 
 
 def _frame(grid: CellGrid, palette: Palette, options: GlyphRampOptions) -> np.ndarray:
@@ -384,9 +389,7 @@ def _frame(grid: CellGrid, palette: Palette, options: GlyphRampOptions) -> np.nd
         rows, cols = np.divmod(cells, grid.cols)
         mask = _glyph_mask(ramp[value], options.font, grid.cell_w, grid.cell_h)
         view[rows, :, cols, :, :] = _blend(paper[rows, cols], ink[rows, cols], mask)
-    if alpha:
-        return frame
-    return np.ascontiguousarray(frame[:, :, :3])
+    return frame if alpha else np.ascontiguousarray(frame[:, :, :3])
 
 
 def register_glyph_ramp_renderer() -> CellRenderer:
diff --git a/tests/test_glyph_ramp.py b/tests/test_glyph_ramp.py
index 1bf23c0..f7e1c1e 100644
--- a/tests/test_glyph_ramp.py
+++ b/tests/test_glyph_ramp.py
@@ -1,19 +1,11 @@
-"""Tests for the glyph_ramp renderer (§3, §9, AMD-010) — cards L6 and L9c.
-
-Expected glyph sequences are pinned as literals derived from the contract, never recomputed
-with the renderer's own formula: §9 + AMD-010 say ``luma`` (S2) indexes the ramp through its
-sRGB-perceptual encoding, so a linear luma of 0.05 encodes to sRGB 0.2478, lands in bucket 2
-of a 10-character ramp and must draw ``'#'``. Since H12 (2026-11-18) ``bg_colour`` glyphs
-follow the |luma - background| gap over the ramp bounded to its medium densities, its ink is
-the palette entry two ranks off the cell colour, and ``palette`` honours the declared ``bg``
-(whose explicit value ``"auto"`` is the palette's darkest entry).
+"""Tests for glyph_ramp (§3, §9, AMD-010) — L6/L9c. Glyph sequences are pinned contract literals
+(luma indexes the ramp via sRGB encoding, AMD-010). H12: palette honours the declared bg ("auto"
+= darkest); palette/bg_colour ink is ±2 palette ranks; bg_colour glyphs follow the |luma-bg| gap.
 """
-
 from __future__ import annotations
 
 import json
 from pathlib import Path
-from typing import cast
 
 import numpy as np
 import pytest
@@ -45,429 +37,226 @@ from lattice_core.renderers.glyph_ramp import (
 from lattice_core.types import Palette
 
 RAMP = "@%#*+=-:. "
-BOUNDED = RAMP[1:-1]  # "%#*+=-:." — the H12 bg_colour ramp, extremes (space, '@') removed
+BOUNDED = RAMP[1:-1]  # "%#*+=-:." — H12 bg_colour ramp, extremes (space, '@') removed
 PICO8_RAMP = " .:-=+*#%@"
 BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
 GREYS: Palette = np.array([[0.0, 0.0, 0.0], [0.25, 0.25, 0.25], [0.5, 0.5, 0.5],
                            [0.75, 0.75, 0.75], [1.0, 1.0, 1.0]], dtype=np.float32)
-COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
-                           dtype=np.float32)
+COLOUR: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
 CELL_W, CELL_H = 8, 16
 SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
 PORTRAIT = Path("/home/mar1/Téléchargements/H12/A_portrait.jpg")
 _PAD = 64
-
-
+_LUMAS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
+_PLAIN = "@#*+=:.  "
 def _srgb_grid(steps: int, palette: np.ndarray = BW) -> CellGrid:
-    """Return the grid the pipeline builds for a black-to-white sRGB gradient of steps cells."""
     ramp = np.linspace(0.0, 1.0, steps, dtype=np.float32)[None, :, None]
     cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
     return _make_grid(cells, np.zeros((1, steps), np.int32), CELL_W, CELL_H, palette)
-
-
-def _linear_grid(
-    luma: list[float], index: list[int] | None = None,
-    cell_w: int = CELL_W, cell_h: int = CELL_H,
-) -> CellGrid:
-    """Return a one-row grid carrying the given literal linear luma values (S2)."""
+def _linear_grid(luma: list[float], index: list[int] | None = None,
+                 cell_w: int = CELL_W, cell_h: int = CELL_H) -> CellGrid:
     values = np.asarray(luma, dtype=np.float32)[None, :]
-    cells = np.zeros(values.shape, dtype=np.int32) if index is None else np.asarray(
-        index, dtype=np.int32
-    )[None, :]
-    return CellGrid(
-        cols=values.shape[1], rows=1, cell_w=cell_w, cell_h=cell_h,
-        index=np.ascontiguousarray(cells), coverage=values.copy(), luma=values.copy(),
-        samples=np.ascontiguousarray(values[:, :, None]),
-    )
-
-
+    cells = (np.zeros(values.shape, np.int32) if index is None
+             else np.asarray(index, np.int32)[None, :])
+    return CellGrid(cols=values.shape[1], rows=1, cell_w=cell_w, cell_h=cell_h,
+                    index=np.ascontiguousarray(cells), coverage=values.copy(), luma=values.copy(),
+                    samples=np.ascontiguousarray(values[:, :, None]))
 def _style(**options: object) -> RenderStyle:
-    """Return a RenderStyle carrying the given glyph_ramp options."""
     return RenderStyle(options=dict(options))
-
-
 def _chars(grid: CellGrid, palette: np.ndarray = BW, **options: object) -> str:
-    """Return the glyph characters layout() places, row-major, as one string."""
-    return "".join(entry.character for entry in GlyphRampRenderer().layout(
-        grid, palette, _style(**options)
-    ))
-
-
+    placed = GlyphRampRenderer().layout(grid, palette, _style(**options))
+    return "".join(e.character for e in placed)
 def _cells(img) -> np.ndarray:
-    """Return the rendered image as a (rows, cols, cell_h, cell_w, 3) uint8 array."""
-    array = np.asarray(img)
-    rows, cols = array.shape[0] // CELL_H, array.shape[1] // CELL_W
-    return array.reshape(rows, CELL_H, cols, CELL_W, 3).transpose(0, 2, 1, 3, 4)
-
-
-def _pillow_ink(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
-    """Return Pillow's own float32 ink of glyph centred in a cell: an independent reference."""
-    font = _default_font(size)
+    a = np.asarray(img)
+    rows, cols = a.shape[0] // CELL_H, a.shape[1] // CELL_W
+    return a.reshape(rows, CELL_H, cols, CELL_W, 3).transpose(0, 2, 1, 3, 4)
+def _pillow_canvas(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
     canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
-    ImageDraw.Draw(canvas).text(
-        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
-    )
-    patch = np.asarray(canvas, dtype=np.float32)[_PAD : _PAD + cell_h, _PAD : _PAD + cell_w]
-    return np.ascontiguousarray(patch / 255.0)
-
-
+    ImageDraw.Draw(canvas).text((_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph,
+                                font=ImageFont.load_default(size=size), fill=255, anchor="mm")
+    return np.asarray(canvas)
+def _pillow_ink(glyph: str, cell_w: int, cell_h: int, size: int) -> np.ndarray:
+    patch = _pillow_canvas(glyph, cell_w, cell_h, size)[_PAD:_PAD + cell_h, _PAD:_PAD + cell_w]
+    return np.ascontiguousarray(patch.astype(np.float32) / 255.0)
 def _pillow_ink_bbox(glyph: str, cell_w: int, cell_h: int, size: int) -> tuple[int, int, int, int]:
-    """Return the unclipped (top, bottom, left, right) ink box of glyph, relative to the cell."""
-    font = ImageFont.load_default(size=size)
-    canvas = PILImage.new("L", (cell_w + 2 * _PAD, cell_h + 2 * _PAD), 0)
-    ImageDraw.Draw(canvas).text(
-        (_PAD + cell_w / 2.0, _PAD + cell_h / 2.0), glyph, font=font, fill=255, anchor="mm"
-    )
-    rows, cols = np.nonzero(np.asarray(canvas) > 0)
+    rows, cols = np.nonzero(_pillow_canvas(glyph, cell_w, cell_h, size) > 0)
     return (int(rows.min()) - _PAD, int(rows.max()) - _PAD,
             int(cols.min()) - _PAD, int(cols.max()) - _PAD)
-
-
-def _default_font(size: int) -> ImageFont.FreeTypeFont:
-    """Return Pillow's bundled default font at size, typed as the FreeType font it is."""
-    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))
-
-
-def _linear_luma(rgb: np.ndarray) -> np.ndarray:
-    """Return the linear-light Rec.709 luma of a uint8 RGB image as a float32 array."""
-    linear = color.srgb_to_linear(np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0))
-    return np.float32(0.2126) * linear[..., 0] + np.float32(0.7152) * linear[..., 1] \
-        + np.float32(0.0722) * linear[..., 2]
-
-
 def _srgb_luma(rgb: np.ndarray) -> np.ndarray:
-    """Return the sRGB-coded (γ-encoded) Rec.709 luma of a uint8 RGB image."""
-    code = np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0)
-    return np.float32(0.2126) * code[..., 0] + np.float32(0.7152) * code[..., 1] \
-        + np.float32(0.0722) * code[..., 2]
-
-
+    c = np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0)
+    return (np.float32(.2126) * c[..., 0] + np.float32(.7152) * c[..., 1]
+            + np.float32(.0722) * c[..., 2])
+def _linear_luma(rgb: np.ndarray) -> np.ndarray:
+    lin = color.srgb_to_linear(np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0))
+    return (np.float32(.2126) * lin[..., 0] + np.float32(.7152) * lin[..., 1]
+            + np.float32(.0722) * lin[..., 2])
 def _dither_grid(src: np.ndarray, palette: np.ndarray, pixel_size: int) -> CellGrid:
-    """Run the pipeline's dithering of src against palette and return the CellGrid it builds."""
     cell_w, cell_h = _cell_geometry(GlyphRampRenderer(), pixel_size)
     cells = _to_cells(_pad_to_cells(src, cell_w, cell_h), cell_w, cell_h)
     info = get_algorithm("floyd_steinberg")
     params = resolve_params(info.params, {})
     params[RESERVED_METRIC] = color.metric_code("srgb")
-    indices = info.fn(color.to_working_space(cells, 0), color.to_working_space(palette, 0),
-                      params)
-    return _make_grid(cells, np.ascontiguousarray(indices, np.int32), cell_w, cell_h, palette)
-
-
+    idx = info.fn(color.to_working_space(cells, 0), color.to_working_space(palette, 0), params)
+    return _make_grid(cells, np.ascontiguousarray(idx, np.int32), cell_w, cell_h, palette)
 def _darkest_cells(grid: CellGrid) -> list[int]:
-    """Return the flat positions of the darkest 20 % of cells, by source luma (S2)."""
-    count = max(1, int(round(0.2 * int(grid.luma.size))))
-    return np.argpartition(grid.luma.ravel(), count)[:count].tolist()
-
-
+    flat = grid.luma.ravel()
+    return np.argsort(flat)[:int(0.2 * len(flat))].tolist()
 def _placed(grid: CellGrid, palette: np.ndarray, **options: object) -> list[GlyphPlacement]:
-    """Return the glyphs layout() places for grid on palette with the given options."""
     return GlyphRampRenderer().layout(grid, palette, _style(**options))
-
-
-# --- accept 1 (L6): a 10-character ramp on a black-to-white gradient ---
-
-
+def _portrait_grid(pixel_size: int) -> tuple[CellGrid, np.ndarray]:
+    if not PORTRAIT.is_file():
+        pytest.skip("no H12 portrait image available")
+    pico8 = np.asarray(get_builtin("pico8"), np.float32)
+    src = np.asarray(PILImage.open(PORTRAIT).convert("RGB"), np.float32) / 255.0
+    return _dither_grid(src, pico8, pixel_size), pico8
 def test_ten_character_ramp_on_a_gradient_places_the_ramp_in_order():
     assert _chars(_srgb_grid(10), ramp=RAMP) == "@%#*+=-:. "
     assert len(set(_chars(_srgb_grid(10), ramp=RAMP))) == 10
-
-
 def test_five_step_gradient_pins_the_contract_buckets():
-    ramp = np.linspace(0.0, 1.0, 5, dtype=np.float32)[None, :, None]
-    cells = np.ascontiguousarray(np.repeat(ramp, 3, axis=2))
-    grid = _make_grid(cells, np.zeros((1, 5), np.int32), CELL_W, CELL_H, BW)
-    assert _chars(grid, ramp=RAMP) == "@#=: "
-
-
-def test_ten_character_ramp_renders_ten_distinct_cells():
-    cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
-    assert len({cells[0, col].tobytes() for col in range(10)}) == 10
-
-
-def test_glyph_ink_decreases_as_the_cell_luma_rises():
+    assert _chars(_srgb_grid(5), ramp=RAMP) == "@#=: "
+def test_ten_character_ramp_renders_ten_distinct_cells_with_monotone_ink():
     cells = _cells(GlyphRampRenderer().render(_srgb_grid(10), BW, _style(ramp=RAMP)))
-    ink = [float(cells[0, col].mean()) for col in range(10)]
-    assert ink[0] < ink[-1]
-    assert ink[0] == min(ink) and ink[-1] == max(ink)
-
-
-# --- accept 2 (L6): a black/white palette does not collapse the ramp (S2/H11) ---
-
-
+    assert len({cells[0, c].tobytes() for c in range(10)}) == 10
+    ink = [float(cells[0, c].mean()) for c in range(10)]
+    assert ink[0] < ink[-1] and ink[0] == min(ink) and ink[-1] == max(ink)
 def test_black_and_white_palette_keeps_all_ten_glyphs():
     assert len(set(_chars(_srgb_grid(10, BW), BW, ramp=RAMP))) == 10
-
-
 def test_glyph_choice_is_independent_of_the_palette():
-    grid = _srgb_grid(10)
-    assert _chars(grid, BW, ramp=RAMP) == _chars(grid, COLOUR, ramp=RAMP)
-
-
+    assert _chars(_srgb_grid(10), BW, ramp=RAMP) == _chars(_srgb_grid(10), COLOUR, ramp=RAMP)
 def test_consumes_is_exactly_luma_and_index():
     assert GlyphRampRenderer().consumes() == frozenset({"luma", "index"})
-
-
-# --- accept 3 (L6): offset shifts the mapping by exactly one glyph per 1/len(ramp) ---
-
-_LUMAS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
-_PLAIN = "@#*+=:.  "
-
-
-def test_offset_zero_draws_the_pinned_ramp_positions():
-    assert _chars(_linear_grid(_LUMAS), ramp=RAMP) == _PLAIN
-
-
-def test_offset_shifts_the_mapping_by_exactly_one_glyph():
-    grid = _linear_grid(_LUMAS)
-    assert _chars(grid, ramp=RAMP, offset=1 / len(RAMP)) == "%*+=-.   "
-    assert _chars(grid, ramp=RAMP, offset=2 / len(RAMP)) == "#+=-:    "
-
-
-def test_offset_is_measured_in_ramp_units_not_pixels():
-    grid = _linear_grid(_LUMAS)
-    for offset, expected in {
-        0.1: "%*+=-.   ", 0.2: "#+=-:    ", 0.3: "*=-:.    ",
-        0.4: "+-:.     ", 0.5: "=:.      ",
-    }.items():
-        assert _chars(grid, ramp=RAMP, offset=offset) == expected
-
-
+@pytest.mark.parametrize("offset,expected", [(0.0, _PLAIN), (1 / len(RAMP), "%*+=-.   "),
+    (2 / len(RAMP), "#+=-:    "), (0.3, "*=-:.    "), (0.4, "+-:.     "), (0.5, "=:.      ")])
+def test_offset_shifts_the_mapping_in_ramp_units(offset, expected):
+    assert _chars(_linear_grid(_LUMAS), ramp=RAMP, offset=offset) == expected
 def test_offset_is_clamped_at_both_ends():
     grid = _linear_grid([0.0, 0.3, 0.7, 1.0])
     assert _chars(grid, ramp=RAMP, offset=-5.0) == "@@@@"
     assert _chars(grid, ramp=RAMP, offset=5.0) == "    "
-
-
-# --- accept 4 (L6): invert reverses the ramp ---
-
-
 def test_invert_reverses_the_ramp():
-    grid = _linear_grid(_LUMAS)
-    assert _chars(grid, ramp=RAMP, invert=True) == " :-=+#%@@"
+    assert _chars(_linear_grid(_LUMAS), ramp=RAMP, invert=True) == " :-=+#%@@"
     assert _chars(_srgb_grid(10), ramp=RAMP, invert=True) == " .:-=+*#%@"
-
-
-# --- accept 5 (L6): mode "palette" gives each glyph the palette colour of its cell ---
-
-
-def test_palette_mode_gives_each_glyph_its_cell_palette_colour():
+def test_palette_mode_renders_the_relative_ink():
     grid = _linear_grid([0.05, 0.05], index=[1, 2])
     cells = _cells(GlyphRampRenderer().render(grid, COLOUR,
                                               _style(ramp=RAMP, mode="palette", bg="auto")))
-    red, blue = cells[0, 0].reshape(-1, 3), cells[0, 1].reshape(-1, 3)
-    assert red[:, 0].max() > 0 and red[:, 1].max() == 0 and red[:, 2].max() == 0
-    assert blue[:, 2].max() > 0 and blue[:, 0].max() == 0 and blue[:, 1].max() == 0
-
-
-def test_palette_mode_fill_is_the_cell_palette_colour():
-    grid = _linear_grid([0.05, 0.05], index=[1, 2])
-    placed = GlyphRampRenderer().layout(grid, COLOUR, _style(mode="palette"))
-    assert [entry.fill for entry in placed] == ["#ff0000", "#0000ff"]
-
-
+    for cell in (cells[0, 0].reshape(-1, 3), cells[0, 1].reshape(-1, 3)):
+        assert cell[:, 0].max() > 0 and cell[:, 1].max() == 0 and cell[:, 2].max() == 0
+def test_palette_mode_fill_is_the_relative_ink_on_the_declared_bg():
+    grid = _linear_grid([0.05, 0.05, 0.05], index=[0, 3, 4])
+    placed = GlyphRampRenderer().layout(grid, GREYS, _style(mode="palette", bg="#ffffff"))
+    assert [e.paper for e in placed] == ["#ffffff"] * 3
+    assert [e.fill for e in placed] == ["#808080", "#404040", "#808080"]
 def test_fg_colour_mode_takes_the_ink_from_the_palette_and_the_paper_from_bg():
     grid = _linear_grid([0.05], index=[1])
     style = _style(ramp=RAMP, mode="fg_colour", bg="#00ff00")
     flat = _cells(GlyphRampRenderer().render(grid, COLOUR, style))[0, 0].reshape(-1, 3)
     assert flat[:, 0].max() > 0 and flat[:, 2].max() == 0
     assert flat[:, 1].max() == 255 and flat[:, 0].max() < 255
-
-
-# --- accept 6 (L6) + H12: bg_colour paper is the cell colour, ink is relative (two ranks) ---
-
-
 def test_bg_colour_mode_puts_the_palette_colour_in_the_background():
-    grid = _linear_grid([0.05], index=[1])
-    style = _style(mode="bg_colour")
-    renderer = GlyphRampRenderer()
-    placed = renderer.layout(grid, COLOUR, style)
+    grid, style = _linear_grid([0.05], index=[1]), _style(mode="bg_colour")
+    placed = GlyphRampRenderer().layout(grid, COLOUR, style)
     assert placed[0].paper == "#ff0000"  # the paper is the cell's palette colour
-    pixels = np.asarray(renderer.render(grid, COLOUR, style)).reshape(-1, 3)
+    pixels = np.asarray(GlyphRampRenderer().render(grid, COLOUR, style)).reshape(-1, 3)
     mask = _glyph_mask(placed[0].character, None, CELL_W, CELL_H).reshape(-1)
     assert np.all(pixels[mask <= 0.0] == np.array([255, 0, 0], np.uint8))
-
-
 def test_bg_colour_ink_is_two_ranks_off_the_fond():
     grid = _linear_grid([0.05, 0.05, 0.05], index=[0, 3, 4])  # black, 0.75-grey, white fonds
     placed = _placed(grid, GREYS, mode="bg_colour")
-    assert [entry.paper for entry in placed] == ["#000000", "#bfbfbf", "#ffffff"]
-    # a dark fond (luma < 0.5) takes the ink two ranks above (rank 2), a light one two below
-    assert placed[0].fill == placed[2].fill == "#808080"
+    assert [e.paper for e in placed] == ["#000000", "#bfbfbf", "#ffffff"]
+    assert placed[0].fill == placed[2].fill == "#808080"  # dark fond -> +2 ranks
     assert placed[1].fill == "#404040"  # 0.75-grey fond -> ink at rank 1
-
-
 def test_bg_colour_ink_ignores_fg():
     grid = _linear_grid([0.05, 0.05], index=[0, 1])
     with_fg = _placed(grid, GREYS, mode="bg_colour", fg="#00ff00")
     without = _placed(grid, GREYS, mode="bg_colour")
     assert [(p.fill, p.paper) for p in with_fg] == [(p.fill, p.paper) for p in without]
-    assert all(p.fill != "#00ff00" for p in with_fg)  # fg is superseded by the relative ink
-
-
+    assert all(p.fill != "#00ff00" for p in with_fg)  # fg superseded by the relative ink
 def test_bg_colour_ink_clamps_at_the_palette_edges():
     tiny = np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5], [1.0, 1.0, 1.0]], np.float32)
     grid = _linear_grid([0.05, 0.05], index=[0, 2])  # black and white fonds
     placed = _placed(grid, tiny, mode="bg_colour")
-    assert placed[0].fill == "#ffffff"  # two ranks above the darkest, clamped to white
-    assert placed[1].fill == "#000000"  # two ranks below the lightest, clamped to black
-
-
-# --- H12 accept 2: bg_colour glyphs follow the |luma - background| gap (not absolute luma) ---
-
-
+    assert placed[0].fill == "#ffffff"  # +2 above the darkest, clamped to white
+    assert placed[1].fill == "#000000"  # -2 below the lightest, clamped to black
 def test_bg_colour_ramp_excludes_the_two_extreme_glyphs():
     chars = _chars(_srgb_grid(10), BW, mode="bg_colour")
-    assert set(chars) <= set(BOUNDED)
-    assert " " not in chars and "@" not in chars  # space (density 0) and '@' are removed
-
-
+    assert set(chars) <= set(BOUNDED) and " " not in chars and "@" not in chars
 def test_bg_colour_gap_pins_the_srgb_buckets():
-    # A black fond (linear luma 0) makes the gap equal to the source luma; each glyph is the
-    # sRGB-re-encoded bucket of the bounded ramp (AMD-010 extended to the gap). Pinned literals:
+    # Black fond (luma 0) makes the gap equal to the source luma; sRGB buckets, pinned literals.
     assert _chars(_linear_grid([0.01, 0.05, 0.1, 0.2, 0.35, 0.6, 0.8, 0.95]),
                   BW, mode="bg_colour") == "%#*+-:.."
-
-
 def test_bg_colour_offset_moves_one_glyph_per_bucket():
     grid = _linear_grid([0.1, 0.2, 0.35, 0.6])
     assert _chars(grid, BW, mode="bg_colour") == "*+-:"
     assert _chars(grid, BW, mode="bg_colour", offset=1 / len(BOUNDED)) == "+=:."
-
-
 def test_bg_colour_invert_reverses_the_bounded_ramp():
     chars = _chars(_linear_grid([0.01, 0.6, 0.95]), BW, mode="bg_colour")
     inverted = _chars(_linear_grid([0.01, 0.6, 0.95]), BW, mode="bg_colour", invert=True)
     assert inverted == "".join(BOUNDED[::-1][BOUNDED.index(c)] for c in chars)
-
-
 def test_bg_colour_glyph_follows_the_gap_not_the_absolute_luma():
-    # Same absolute luma, different fonds -> different gaps -> different glyphs (an absolute-
-    # luma implementation would draw the same character in both cells):
-    grid = _linear_grid([0.05, 0.05], index=[0, 1])  # black fond, then mid-grey fond
+    grid = _linear_grid([0.05, 0.05], index=[0, 1])  # same luma, black then mid-grey fond
     assert set(_chars(grid, GREYS, mode="bg_colour")) == {"%", "#"}
-
-
 def test_mono_and_fg_colour_keep_absolute_luma_indexing():
     grid = _srgb_grid(10)
     assert _chars(grid, BW, ramp=RAMP) == _chars(grid, BW, ramp=RAMP, mode="fg_colour")
     assert _chars(grid, BW, ramp=RAMP) != _chars(grid, BW, mode="bg_colour")
-
-
 def test_bg_colour_short_ramp_is_used_whole():
     chars = _chars(_srgb_grid(6), BW, mode="bg_colour", ramp=" x")
     assert set(chars) <= {" ", "x"}  # a ramp too short to bound is used as-is (E1)
-
-
-# --- H12 accept 1: palette mode respects the declared bg, auto = the darkest palette tone ---
-
-
 def test_palette_mode_respects_a_declared_light_bg():
     grid = _srgb_grid(16)
-    img = GlyphRampRenderer().render(grid, COLOUR, _style(ramp=RAMP, mode="palette",
-                                                          bg="#ffffff"))
+    img = GlyphRampRenderer().render(grid, COLOUR, _style(ramp=RAMP, mode="palette", bg="#ffffff"))
     assert float(_linear_luma(np.asarray(img)).mean()) > 0.60
     placed = _placed(grid, COLOUR, mode="palette", bg="#ffffff")
-    assert [entry.paper for entry in placed] == ["#ffffff"] * 16
-    assert [entry.fill for entry in placed] == ["#000000"] * 16  # ink stays the cell colour
-
-
-def test_bg_auto_reproduces_the_old_palette_mode():
+    assert [e.paper for e in placed] == ["#ffffff"] * 16
+    assert [e.fill for e in placed] == ["#ff0000"] * 16  # H12 relative ink (+2 ranks)
+def test_bg_auto_reproduces_the_old_palette_paper():
+    # H12 ÉCART 1: bg:"auto" keeps the old fond (darkest); ink is now relative, so compare paper.
     grid = _srgb_grid(10)
     placed = _placed(grid, COLOUR, mode="palette", bg="auto")
-    assert [p.paper for p in placed] == ["#000000"] * 10          # darkest paper preserved
-    assert [p.fill for p in placed] == ["#000000"] * 10           # cell-palette ink preserved
-    assert "".join(p.character for p in placed) == "@%#*+=-:. "   # absolute-luma glyphs kept
-
-
+    assert [p.paper for p in placed] == ["#000000"] * 10
+    assert "".join(p.character for p in placed) == "@%#*+=-:. "
 def test_bg_auto_without_a_palette_raises():
     with pytest.raises(ValueError) as excinfo:
         GlyphRampRenderer().layout(_srgb_grid(4), _style(mode="palette", bg="auto"))
     assert "auto" in str(excinfo.value)
-
-
 def test_fg_colour_mode_accepts_bg_auto_as_the_darkest_paper():
     grid = _linear_grid([0.05], index=[1])
     placed = GlyphRampRenderer().layout(grid, COLOUR, _style(mode="fg_colour", bg="auto"))
     assert placed[0].paper == "#000000" and placed[0].fill == "#ff0000"
-
-
-# --- H12 accept 2 (physical): bg_colour on the H12 portrait (pico8, 4x8 mesh) ---
-
-
-def test_bg_colour_portrait_contrast_and_distinct_shadow_glyphs():
-    if not PORTRAIT.is_file():
-        pytest.skip("no H12 portrait image available")
-    pico8 = np.asarray(get_builtin("pico8"), np.float32)
-    src = np.asarray(PILImage.open(PORTRAIT).convert("RGB"), np.float32) / 255.0
-    grid = _dither_grid(src, pico8, 8)
+@pytest.mark.parametrize("pixel_size,min_distinct", [(8, 5), (12, 5)])
+def test_bg_colour_portrait_contrast_and_shadow_glyphs(pixel_size, min_distinct):
+    grid, pico8 = _portrait_grid(pixel_size)
     img = GlyphRampRenderer().render(grid, pico8, _style(ramp=PICO8_RAMP, mode="bg_colour"))
-    assert float(_srgb_luma(np.asarray(img)).std()) > 0.30   # contrast on the H12 reference scale
+    assert img.size == (grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+    assert float(_srgb_luma(np.asarray(img)).std()) > 0.30
     chars = [p.character for p in _placed(grid, pico8, ramp=PICO8_RAMP, mode="bg_colour")]
-    distinct = len({chars[i] for i in _darkest_cells(grid)})
-    assert distinct >= 5, "the darkest 20 % of cells must carry at least 5 distinct glyphs"
-
-
-def test_bg_colour_portrait_cell_size_12_holds():
-    if not PORTRAIT.is_file():
-        pytest.skip("no H12 portrait image available")
-    pico8 = np.asarray(get_builtin("pico8"), np.float32)
-    src = np.asarray(PILImage.open(PORTRAIT).convert("RGB"), np.float32) / 255.0
-    grid = _dither_grid(src, pico8, 12)
-    img = GlyphRampRenderer().render(grid, pico8, _style(ramp=PICO8_RAMP, mode="bg_colour"))
-    assert img.size == (grid.cols * 6, grid.rows * 12)         # exact 12 px geometry
-    assert float(_srgb_luma(np.asarray(img)).std()) > 0.30     # contrast still holds
-    chars = [p.character for p in _placed(grid, pico8, ramp=PICO8_RAMP, mode="bg_colour")]
-    distinct = len({chars[i] for i in _darkest_cells(grid)})
-    assert distinct >= 3, "shadows are not mute even at 12 px cells (cell size is not the fix)"
-
-
-# --- H12 accept 2 (synthetic): deterministic and independent of any external image ---
-
-
+    assert len({chars[i] for i in _darkest_cells(grid)}) >= min_distinct  # cell size is not the fix
 def test_bg_colour_darkest_cells_carry_distinct_glyphs():
-    # 25 cells: 5 dark (luma 0.01..0.35) on a black fond among 20 light; the darkest 20 % are
-    # exactly the 5 dark cells and must span >= 5 distinct bounded glyphs (pinned literals).
-    dark = [0.01, 0.05, 0.1, 0.2, 0.35]
-    grid = _linear_grid(dark + [0.95] * 20, index=[0] * 5 + [1] * 20)
+    grid = _linear_grid([0.01, 0.05, 0.1, 0.2, 0.35] + [0.95] * 20, index=[0] * 5 + [1] * 20)
     chars = [p.character for p in _placed(grid, BW, mode="bg_colour")]
     assert "".join(chars[:5]) == "%#*+-"
     assert len({chars[i] for i in _darkest_cells(grid)}) >= 5
     assert set(chars) <= set(BOUNDED)
-
-
-# --- accept 7 (L6): output size is exactly (cols * cell_w, rows * cell_h) ---
-
-
 @pytest.mark.parametrize(("rows", "cols", "cell_w", "cell_h"), [(3, 4, 8, 16), (1, 1, 5, 7)])
 def test_output_size_is_exactly_the_grid_geometry(rows, cols, cell_w, cell_h):
     luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
     grid = CellGrid(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
                     index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma,
                     samples=luma[:, :, None].copy())
-    expected = (cols * cell_w, rows * cell_h)
-    assert GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)).size == expected
-
-
+    size = GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)).size
+    assert size == (cols * cell_w, rows * cell_h)
 def test_output_size_matches_the_pipeline_geometry():
     src = np.linspace(0.0, 1.0, 64 * 96, dtype=np.float32).reshape(64, 96, 1)
     src = np.ascontiguousarray(np.repeat(src, 3, axis=2))
     spec = PipelineSpec(pixel_size=8, renderer="glyph_ramp", renderer_style={"ramp": RAMP})
     out = render_with_palette(src, spec, BW)
-    assert out.shape == (64, 96, 3)
-    assert out.dtype == np.uint8
-
-
-# --- accept 8 (L6): a missing font file raises ValueError naming the path ---
-
-
+    assert out.shape == (64, 96, 3) and out.dtype == np.uint8
 def test_missing_font_file_raises_value_error_naming_the_path():
     path = "/nonexistent/fonts/definitely-not-a-font.ttf"
     with pytest.raises(ValueError) as excinfo:
         GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, font=path))
     assert path in str(excinfo.value)
-
-
 def test_missing_font_file_raises_from_layout_and_from_an_empty_grid():
     path = "/nonexistent/fonts/definitely-not-a-font.ttf"
     style = _style(ramp=RAMP, font=path)
@@ -480,47 +269,25 @@ def test_missing_font_file_raises_from_layout_and_from_an_empty_grid():
     with pytest.raises(ValueError) as excinfo:
         GlyphRampRenderer().render(empty, BW, style)
     assert path in str(excinfo.value)
-
-
 def test_font_option_accepts_a_real_font_file():
     if not SYSTEM_FONT.is_file():
         pytest.skip("no system TrueType font available")
     img = GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, font=str(SYSTEM_FONT)))
     assert img.size == (4 * CELL_W, CELL_H)
-
-
-# --- §3 invariants ---
-
-
-def test_render_is_pure():
-    grid = _srgb_grid(10)
-    renderer = GlyphRampRenderer()
-    assert np.array_equal(
-        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
-        np.asarray(renderer.render(grid, BW, _style(ramp=RAMP))),
-    )
-
-
-def test_bg_colour_render_is_pure():
-    grid = _srgb_grid(10)
-    renderer = GlyphRampRenderer()
-    style = _style(ramp=RAMP, mode="bg_colour")
-    assert np.array_equal(np.asarray(renderer.render(grid, GREYS, style)),
-                          np.asarray(renderer.render(grid, GREYS, style)))
-
-
+@pytest.mark.parametrize("palette,mode", [(BW, "mono"), (GREYS, "bg_colour")])
+def test_render_is_pure(palette, mode):
+    grid, renderer = _srgb_grid(10), GlyphRampRenderer()
+    style = _style(ramp=RAMP, mode=mode)
+    assert np.array_equal(np.asarray(renderer.render(grid, palette, style)),
+                          np.asarray(renderer.render(grid, palette, style)))
 def test_render_does_not_mutate_grid_or_palette():
-    grid = _srgb_grid(10)
-    palette = BW.copy()
+    grid, palette = _srgb_grid(10), BW.copy()
     snapshot = (grid.index.copy(), grid.luma.copy(), grid.samples.copy(), grid.coverage.copy())
     GlyphRampRenderer().render(grid, palette, _style(ramp=RAMP, mode="palette"))
-    assert np.array_equal(grid.index, snapshot[0])
-    assert np.array_equal(grid.luma, snapshot[1])
-    assert np.array_equal(grid.samples, snapshot[2])
-    assert np.array_equal(grid.coverage, snapshot[3])
+    arrays = (grid.index, grid.luma, grid.samples, grid.coverage)
+    for arr, snap in zip(arrays, snapshot, strict=True):
+        assert np.array_equal(arr, snap)
     assert np.array_equal(palette, BW)
-
-
 def test_module_state_is_a_bounded_input_keyed_cache():
     cache = glyph_ramp._cached_mask
     cache.cache_clear()
@@ -531,15 +298,11 @@ def test_module_state_is_a_bounded_input_keyed_cache():
     info = cache.cache_info()
     assert info.maxsize is not None and info.currsize <= info.maxsize
     assert info.currsize < 24 * 2 * len(RAMP)
-
-
 def test_cached_masks_are_read_only():
     mask = glyph_ramp._glyph_mask("@", None, CELL_W, CELL_H)
     assert not mask.flags.writeable
     with pytest.raises(ValueError):
         mask[0, 0] = 1.0
-
-
 def test_a_font_replaced_at_the_same_path_is_a_new_cache_key(tmp_path):
     if not SYSTEM_FONT.is_file():
         pytest.skip("no system TrueType font available")
@@ -549,21 +312,14 @@ def test_a_font_replaced_at_the_same_path_is_a_new_cache_key(tmp_path):
     glyph_ramp._glyph_mask("M", str(copied), CELL_W, CELL_H)
     copied.write_bytes(SYSTEM_FONT.read_bytes() + b"\0")
     assert glyph_ramp._font_key(str(copied)) != first
-
-
 def test_renderer_is_registered_under_a_unique_stable_name():
     renderer = GlyphRampRenderer()
     assert renderer.name == "glyph_ramp"
     assert get_renderer("glyph_ramp").name == "glyph_ramp"
     assert "glyph_ramp" in list_renderers()
     assert isinstance(renderer, CellRenderer)
-
-
 def test_cell_aspect_is_the_monospace_ratio():
-    assert GlyphRampRenderer().cell_aspect() == 0.5
-    assert GlyphRampRenderer().subgrid() == (1, 1)
-
-
+    assert GlyphRampRenderer().cell_aspect() == 0.5 and GlyphRampRenderer().subgrid() == (1, 1)
 def test_style_options_round_trip_through_the_renderer():
     options = {"ramp": RAMP, "mode": "palette", "offset": 0.25, "invert": True,
                "fg": "#112233", "bg": "transparent", "font": None}
@@ -571,60 +327,37 @@ def test_style_options_round_trip_through_the_renderer():
     style = _style(**options)
     assert json.loads(json.dumps(dict(style.options))) == options
     reloaded = _style(**json.loads(json.dumps(dict(style.options))))
-    assert np.array_equal(
-        np.asarray(GlyphRampRenderer().render(grid, palette, style)),
-        np.asarray(GlyphRampRenderer().render(grid, palette, reloaded)),
-    )
-
-
-# --- layout() consistency with render() ---
-
-
+    assert np.array_equal(np.asarray(GlyphRampRenderer().render(grid, palette, style)),
+                          np.asarray(GlyphRampRenderer().render(grid, palette, reloaded)))
 def test_layout_places_one_glyph_per_cell_row_major():
     grid = _srgb_grid(10)
     placed = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP))
     assert len(placed) == grid.rows * grid.cols
-    assert all(isinstance(entry, GlyphPlacement) for entry in placed)
-    for col, entry in enumerate(placed):
-        assert entry.x == col * CELL_W and entry.y == 0.0
-        assert entry.width == CELL_W and entry.height == CELL_H
-
-
+    assert all(isinstance(e, GlyphPlacement) for e in placed)
+    for col, e in enumerate(placed):
+        assert e.x == col * CELL_W and e.y == 0.0
+        assert e.width == CELL_W and e.height == CELL_H
 def test_layout_accepts_both_call_forms():
     grid, style = _srgb_grid(4), _style(ramp=RAMP)
     assert GlyphRampRenderer().layout(grid, style) == GlyphRampRenderer().layout(grid, BW, style)
-
-
 def test_layout_reports_alpha_and_transparent_paper():
     grid = _linear_grid([0.05])
     clear = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="transparent"))[0]
     assert clear.paper == "transparent"
     half = GlyphRampRenderer().layout(grid, BW, _style(ramp=RAMP, bg="#ff000080"))[0]
     assert half.paper == "#ff000080"
-
-
-# --- H11: no size option, font size derives from cell_h ---
-
-
 def test_there_is_no_size_option():
     grid = _srgb_grid(6)
     plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
     with_size = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, size=48)))
     assert np.array_equal(plain, with_size)
-
-
 def test_glyph_font_size_derives_from_the_cell():
-    # geometry en hauteur liante (cell non-2x1) : by_height = 4/1.20 ~= 3.33 lie
-    # (by_width = 4/0.87 ~= 4.60) — un calcul largeur-seule donnerait 5 (DEV-213)
-    assert _font_size(4, 4, None) == 3
+    assert _font_size(4, 4, None) == 3  # height-binding geometry (DEV-213)
     pinned = {(8, 16): 9, (6, 12): 7, (12, 24): 14, (20, 40): 23, (10, 20): 11, (4, 8): 5}
     for (cell_w, cell_h), size in pinned.items():
         assert _font_size(cell_w, cell_h, None) == size
-        assert np.array_equal(
-            _glyph_mask("@", None, cell_w, cell_h), _pillow_ink("@", cell_w, cell_h, size)
-        )
-
-
+        assert np.array_equal(_glyph_mask("@", None, cell_w, cell_h),
+                              _pillow_ink("@", cell_w, cell_h, size))
 def test_glyph_ink_stays_inside_the_cell_and_is_horizontally_centred():
     for cell_h in (12, 24, 40):
         cell_w = cell_h // 2
@@ -638,51 +371,27 @@ def test_glyph_ink_stays_inside_the_cell_and_is_horizontally_centred():
         assert rows.min() >= 0 and rows.max() <= cell_h - 1
         assert cols.min() >= 0 and cols.max() <= cell_w - 1
         assert 0.0 < float(mask.mean()) < 1.0
-
-
 def test_unknown_style_keys_are_ignored_for_forward_compatibility():
     grid = _srgb_grid(6)
     plain = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP)))
     future = np.asarray(GlyphRampRenderer().render(grid, BW, _style(ramp=RAMP, glow=0.7)))
     assert np.array_equal(plain, future)
-
-
-# --- option validation and edge cases ---
-
-
-def test_empty_ramp_raises_value_error():
-    with pytest.raises(ValueError):
-        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=""))
-
-
-def test_unknown_mode_raises_value_error_naming_the_modes():
+@pytest.mark.parametrize("options,match", [({"ramp": ""}, None), ({"mode": "vibrant"}, "fg_colour"),
+                                           ({"fg": "not-a-colour"}, None)])
+def test_invalid_options_raise_value_error(options, match):
     with pytest.raises(ValueError) as excinfo:
-        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(mode="vibrant"))
-    assert "fg_colour" in str(excinfo.value)
-
-
-def test_invalid_colour_raises_value_error():
-    with pytest.raises(ValueError):
-        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(fg="not-a-colour"))
-
-
+        GlyphRampRenderer().render(_srgb_grid(4), BW, _style(**options))
+    if match is not None:
+        assert match in str(excinfo.value)
 def test_default_ramp_is_darkest_first_and_documented():
-    assert DEFAULT_RAMP[0] == "@"
-    assert DEFAULT_RAMP[-1] == " "
+    assert DEFAULT_RAMP[0] == "@" and DEFAULT_RAMP[-1] == " "
     assert float(_glyph_mask(DEFAULT_RAMP[0], None, CELL_W, CELL_H).mean()) > 0.0
-
-
 def test_transparent_background_produces_an_rgba_image():
     img = GlyphRampRenderer().render(_srgb_grid(4), BW, _style(ramp=RAMP, bg="transparent"))
-    assert img.mode == "RGBA"
-    assert img.size == (4 * CELL_W, CELL_H)
-
-
+    assert img.mode == "RGBA" and img.size == (4 * CELL_W, CELL_H)
 def test_flat_luma_collapses_to_a_single_glyph():
     assert set(_chars(_linear_grid([0.0, 0.0, 0.0]), ramp=RAMP)) == {RAMP[0]}
     assert set(_chars(_linear_grid([1.0, 1.0, 1.0]), ramp=RAMP)) == {RAMP[-1]}
-
-
 def test_luma_is_linear_light_not_srgb():
     grid = _srgb_grid(10)
     ramp = np.linspace(0.0, 1.0, 10, dtype=np.float32)[None, :, None]




CODER NOTES AND DEVIATIONS (verbatim)
NOTES :
- WIP repris : encre relative ±2 appliquée à `palette` ET `bg_colour` ; papier `palette` = `bg` déclaré (ÉCART 1).
- Bug racine corrigé : `_relative_ink` indexait la palette NON triée par le rang luma (`rows[chosen]`) — faux sur pico8/COLOUR. Désormais `rows[order[chosen]]`.
- `bg_colour` : glyphe sur l'écart |luma−fond|, rampe bornée [1:-1], écart normalisé par span³ (cf. E1).
- `bg:"auto"` : le test de non-régression compare le PAPIER (l'encre change légitimement), pas les pixels entiers.
- Les 4 tests HEAD qui évaluaient « encre = couleur de la cellule » sont mis à jour à la sémantique H12.
- Condensation ≤ 400 : fusions paramétrées, doublons d'offset retirés, aucune couverture perdue (à vérifier).
DEVIATIONS :
E2 — ÉCART 2 (luma 0,40-0,80 + contraste > 0,25 en palette bg blanc) inatteignable sans violer la décision H12 n°1 ; accept officiel (luma > 0,60) tenu (0,98).
E1 — §9 muet sur la normalisation de l'écart en bg_colour ; span³ étale les petits écarts des ombres sur la rampe moyennée ; identité pour les palettes de pleine plage (BW/GREYS) → buckets AMD-010 inchangés ; réversible.

