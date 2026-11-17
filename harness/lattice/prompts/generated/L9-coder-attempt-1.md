# Coder prompt — L9 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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

--- lattice_core/renderers/glyph_shape.py ---
class GlyphShapeOptions:
class ShapeTable:
class GlyphShapeRenderer:
    def cell_aspectself  # Return 0.5: the default monospace font ratio, width over height (§9).
    def subgridself  # Return (1, 1): one glyph covers the whole cell, with no sub-points.
    def consumesself  # Return {"samples"}: the six circle samples pick the glyph, nothing else is read.
    def sample_pointsself  # Return the (6, 2) stencil: circle centres, top/middle/bottom x left/right (§3).
    def renderself, grid: CellGrid, palette: Palette, style: RenderStyle  # Rasterise the shape-matched glyphs of grid into an image of the grid geometry.
    def render_frameself, grid: CellGrid, palette: Palette, style: RenderStyle  # Return the unrounded frame: glyph ink over paper, float32 (H, W, 3) in [0, 1].
    def layoutself, grid: CellGrid, palette: Palette | None=None, style: RenderStyle | None=None  # Return one placed glyph per cell, row-major (§3, §11).
def register_glyph_shape_renderer  # Register the GlyphShapeRenderer under "glyph_shape" and return it.

--- lattice_core/renderers/pixel.py ---
class PixelRenderer:
    def cell_aspectself  # Return 1.0: one cell is one pixel wide and one pixel tall.
    def subgridself  # Return (1, 1): pixels carry no sub-points.
    def consumesself  # Return {"index"}: only the palette index per cell is drawn.
    def renderself, grid: CellGrid, palette: Palette, style: RenderStyle  # Reproduce the 1.0 apply_palette + upscale_nearest pair exactly.
    def render_frameself, grid: CellGrid, palette: Palette, style: RenderStyle  # Return the unrounded frame: palette colours repeated by cell_w and cell_h.
def register_pixel_renderer  # Register the PixelRenderer under "pixel" and return it.

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

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/renderers/text.py` n'existe PAS (à créer). Lisez glyph_ramp.py, glyph_shape.py et
pixel.py AVANT de coder : le motif renderer est établi (auto-enregistrement register_renderer en
bout de module ; geometry/subgrid/cell_aspect/consumes/render_frame/render/layout). Le renderer
`text` (§10) : paragraphe courant avec métriques de police réelles (kerning, interligne, retour
à la ligne par mots), poids/taille/opacité par glyphe modulés par la luma (S2/H11 — l'encre ne
doit pas s'effondrer sur une palette neutre), cellules ±50 % de taille qui doivent TOUJOURS
remplir exactement le rectangle. Options : text, font, size, line_distance, kerning,
size_mode (fixed|variable), weight_mode (fixed|variable), fg, bg.
CONVENTION : libellés ParamSpec = clés i18n existantes (test_i18n / DEV-212) ; cache module
borné/déterministe (invariant 2) ; ne pas importer d'app ; samples/k selon le stencil.

CONTRAT DE RÉCEPTION (tests déterministes) : size_mode=fixed → glyphes de taille identique /
variable → ≥ 5 tailles distinctes sur un dégradé ; rectangle de sortie rempli exactement (aucun
trou, aucun débordement) dans les deux modes ; un paragraphe de 200 mots se replie sans
clipping (aucun glyphe hors canevas) ; même texte + même graine → sortie identique entre deux
appels ; texte vide → ValueError nommant l'option.