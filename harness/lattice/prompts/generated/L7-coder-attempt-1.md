# Coder prompt — L7 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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

PUBLIC SIGNATURES (lecture seule — ne pas écrire)
--- lattice_core/renderers/glyph_ramp.py ---
class GlyphRampOptions:
class GlyphPlacement:
class GlyphRampRenderer:
    def cell_aspectself  # Return 0.5: the default monospace font ratio, width over height (§9).
    def subgridself  # Return (1, 1): one glyph covers the whole cell, with no sub-points.
    def consumesself  # Return {"luma", "index"}: luma picks the glyph, index the palette colour.
    def renderself, grid: CellGrid, palette: Palette, style: RenderStyle  # Rasterise the glyph ramp of grid into an image of the exact grid geometry.
    def layoutself, grid: CellGrid, palette: Palette | None=None, style: RenderStyle | None=None  # Return one placed glyph per cell, row-major (§3, §11).
def register_glyph_ramp_renderer  # Register the GlyphRampRenderer under "glyph_ramp" and return it.

--- lattice_core/renderers/pixel.py ---
class PixelRenderer:
    def cell_aspectself  # Return 1.0: one cell is one pixel wide and one pixel tall.
    def subgridself  # Return (1, 1): pixels carry no sub-points.
    def consumesself  # Return {"index"}: only the palette index per cell is drawn.
    def renderself, grid: CellGrid, palette: Palette, style: RenderStyle  # Reproduce the 1.0 apply_palette + upscale_nearest pair exactly.
    def render_frameself, grid: CellGrid, palette: Palette, style: RenderStyle  # Return the unrounded frame: palette colours repeated by cell_w and cell_h.
def register_pixel_renderer  # Register the PixelRenderer under "pixel" and return it.

--- lattice_core/renderers/__init__.py ---

--- lattice_core/cell.py ---
class CellGrid:
class RenderStyle:
class CellRenderer:
    def cell_aspectself  # Return width / height of one cell.
    def subgridself  # Return the (sx, sy) sub-point grid; (1, 1) means no sub-points.
    def consumesself  # Return the subset of {"index", "luma", "samples", "coverage",
    def renderself, grid: CellGrid, palette: Palette, style: RenderStyle  # Draw grid with palette and style into a Pillow image.
class FloatFrameRenderer:
    def render_frameself, grid: CellGrid, palette: Palette, style: RenderStyle  # Return the same frame as render, as float32 (rows*cell_h, cols*cell_w, 3) in [0, 1].
def register_rendererrenderer: CellRenderer  # Register renderer under its name, raising ValueError on a duplicate name.
def get_renderername: str  # Return the renderer registered under name, or raise KeyError naming it.
def list_renderers  # Return every registered renderer name, sorted.

TASK CARD
### L7 · Shape-matched glyph renderer
- wave: 1 · deps: L6 · executor: OMH ultrabrain · review: strict · size: L
- owns: `lattice_core/renderers/glyph_shape.py`, `tests/test_glyph_shape.py`
- context: §3 §9
- spec: implement `glyph_shape` per §9. Six sampling circles per cell (top/middle/bottom ×
  left/right). For each glyph, compute the fraction of sampled points inside its ink. **Normalise
  each component by the maximum across the alphabet** — without this every vector clusters and
  every cell maps to the same few characters. Per cell, compute the same vector from `samples` and
  take the nearest neighbour. Cache shape vectors per (font, size) at module level.
- accept:
  - on a synthetic image of a diagonal edge, `glyph_shape` picks different glyphs on either side of
    the edge, and the chosen glyphs differ from `glyph_ramp` on at least 20 % of cells.
  - normalisation is verified: without it, a test asserts that more than 80 % of cells collapse to
    fewer than 3 distinct glyphs; with it, at least 8 distinct glyphs appear on a gradient.
  - the cache is hit on the second call (asserted by a counter).
  - budget: 1024×1024, 64 glyphs, under 200 ms after warm-up.
  - `p` and `q` are distinguished on a test image that differs only by vertical ink position.

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/renderers/glyph_shape.py` n'existe PAS (à créer). Lisez glyph_ramp.py et pixel.py
(lire aussi cell.py) AVANT de coder : le motif renderer est établi (auto-enregistrement en bout
de module via register_renderer ; geometry/subgrid/cell_aspect/consumes/render_frame/render/
layout optionnel — cf. registre). `tests/test_glyph_shape.py` n'existe pas. Module-level cache
des shape vectors : CONFORME à l'invariant 2 amendé (H11) s'il est déterministe, clé = entrées
pures (font, size) et borné. `samples` (§9/§3/S3) : le pipeline fournit k points par cellule —
consumez `samples` ; attention à la géométrie (cell shapes 2×1 par défaut pour des glyphes
monospace).

CONTRAT DE RÉCEPTION (à couvrir en tests déterministes) : synthèse d'un bord diagonal →
glyph_shape choisit des glyphes différents de part et d'autre ET diffère de glyph_ramp sur ≥ 20 %
des cellules ; normalisation vérifiée (sans elle > 80 % des cellules < 3 glyphes distincts ;
avec elle ≥ 8 glyphes distincts sur un dégradé) ; cache touché au 2e appel (compteur) ; budget
1024×1024/64 glyphes < 200 ms à chaud ; `p` et `q` distingués sur une image qui ne diffère que
par la position verticale de l'encre.