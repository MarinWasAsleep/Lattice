# Coder prompt — L8 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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

## §4 Colour and palette

Inherits Lattice Dither §12 (colour metrics: `srgb`, `linear`, `oklab`, `lab2000`) and §16 (palette
authoring: extraction, locking, ordering, import/export).

Additions:

- `Palette` gains `lum_min` and `lum_max`, computed once at construction in linear light.
- Palette import accepts hex lists, GPL files, PNG images and Lospec-style text. No network.
- `Palette.order` is a permutation or `None`. A non-permutation raises `ValueError` at
  `resolve_palette`, naming the offending index.

## §5 Pipeline

Inherits Lattice Dither §13 (pre-dither conditioning) and its render order, with step 8 replaced by
the renderer call. The normative order becomes:

1. If `max_side`: area-downscale so `max(H, W) <= max_side`. Call this shape S.
2. Enabled pre-effects in order; effect i gets `default_rng(seed + i)`.
3. `auto_levels` if enabled.
4. `adjust(brightness, contrast, gamma, saturation)`.
5. `pre_blur` if > 0 (separable Gaussian, sigma = `pre_blur / 3`).
6. Compute grid geometry from `renderer.cell_aspect()` and `pixel_size`, with the normative
   rule (H11, decided 2026-11-16): let `a = cell_aspect()`; if `a >= 1`, `cell_w = pixel_size`
   and `cell_h = max(1, floor(pixel_size / a + 0.5))`; else `cell_h = pixel_size` and
   `cell_w = max(1, floor(pixel_size * a + 0.5))`. The grid holds as many whole cells as fit in
   the step-5 image. Glyph font sizes derive from `cell_h` (no `size` option in §9).
7. Downscale to the grid.
8. `resolve_palette` on the image from step 7.
9. Algorithm (params through `resolve_params`) → `index`.
10. Derive `coverage` and `samples` per §3.
11. `renderer.render(grid, palette, style)`.
12. Enabled post-effects in order; effect j gets `default_rng(seed + 1000 + j)`.

Steps 3, 4 and 5 must be no-ops at their defaults. Step 11 replaces the 1.0 `apply_palette` +
`upscale_nearest` pair; `PixelRenderer` reproduces that pair exactly.

**Continuous mode (S1, amended at H11, decided 2026-11-16).** The pipeline may run without
quantisation: `algorithm: null` and `palette: null` are legal. In that mode **steps 6 to 11 are
skipped outright**: the step-5 image goes straight to step 12 (post-effects); no `CellGrid` is
built and no renderer is called. Lattice Glitch is an effect-graph app that consumes the core
(seed, masks, presets, bridge, CLI) without depending on the CellRenderer quantisation chain.

## §6 Preset format v3

One format for the whole suite. Human-readable, diffable, portable.

```json
{
  "version": 3,
  "app": "glyph",
  "meta": {"name": "", "author": "", "created": ""},
  "renderer": {"name": "glyph_ramp", "style": {}},
  "palette": {"colors": ["#000000", "#ffffff"], "locked": false, "order": null,
              "source": "integrated",
              "extract": {"from": "image", "n_colors": 16, "rows": null}},
  "pipeline": {
    "algorithm": "floyd_steinberg", "params": {}, "color_metric": "srgb",
    "pixel_size": 1, "max_side": null, "brightness": 0.0, "contrast": 0.0,
    "gamma": 1.0, "saturation": 0.0, "pre_blur": 0.0, "auto_levels": false
  },
  "effects": [{"name": "scanlines", "params": {}, "enabled": true, "stage": "post", "mask": null}],
  "masks": {"flip": {"kind": "v_flip"}},
  "fonts": {"ramp": {"family": "DejaVu Sans Mono", "style": "", "fallback": ["mono"]}},
  "output": {"scale": 1, "width": null, "dpi": null},
  "seed": 0
}
```

**v3 completeness (S4, decided 2026-11-16).** The v3 format keeps every capability the v1/v2
formats had: `effects[].stage: "pre" | "post"` (default `post`), `palette.source` +
`palette.extract` (how the palette of a preset was obtained — integrated, extracted from the
image, or imported), `masks: {id: {...}}` referenced by `effects[].mask`, `fonts: {id: {family,
style, fallback[]}}` resolved by family name then shipped fallbacks (no absolute paths), and
`output: {scale, width?, dpi?}` feeding §17. Unknown keys remain preserved on round-trip.

Rules:

- `from_json` accepts versions 1, 2 and 3. Versions 1 and 2 are Lattice Dither formats and map to
  `app: "dither"`, `renderer: "pixel"`. Any other version raises `ValueError` naming it.
- Unknown top-level keys and unknown `style` keys are **preserved** on round-trip. A preset written
  by a newer app must survive a load/save by an older one.
- An `app` mismatch is not an error. Any app may load any preset. If the named renderer is absent,
  the app falls back to its default renderer and records a warning in the result.
- `to_json` writes sorted keys, two-space indent, one trailing newline.
- `seed` is part of the preset. Two runs of the same preset produce identical output.

## §7 Bridge

One client, one adapter per host. The bridge is never fatal: every application works standalone.

```python
class ArtCraftClient:
    @staticmethod
    def discover(host: Literal["photocraft", "designcraft"], port: int | None = None) -> ArtCraftClient | None
    def ping(self) -> bool
    def render_document(self) -> Image.Image
    def place_as_layer(self, img: Image.Image, name: str) -> int
```

- **PhotoCraft** (port 47600, token file): `document.inspect`, `app.save`, `app.open`,
  `layer.copyToDocument`, `file.close`. This is the existing Lattice Dither implementation, moved.
- **DesignCraft**: `file.place` with `{path, frame?}` when a frame is selected, otherwise
  `{path, x, y, width}` to create one. `place_as_layer` returns the placed object id.
- Discovery reads the token file, opens one authenticated connection, and calls `engine.commands`
  as the liveness probe. A missing token, a refused connection or a failed probe returns `None`.
- Every call is bounded by a timeout. A bridge failure surfaces as a typed error, never a crash.
- The exchange directory is per-application, under the platform app-data directory
  (QStandardPaths: `%LOCALAPPDATA%/<App>` on Windows, `~/.local/share/<App>` on Linux), and files
  older than one hour are discarded on each call.

## §8 CLI

Every application exposes the same four verbs:

```
<app> render  --preset P --in IMG --out IMG
<app> batch   --preset P --in DIR --out DIR [--recursive]
<app> presets list|show|validate
<app> bridge  status|pull|push
```

- `render` and the GUI must produce **byte-identical** output for the same preset and image (G9).
- Exit codes: 0 success, 1 usage error, 2 render error, 3 bridge error.
- `--json` on any verb prints a machine-readable result on stdout and nothing else.
- No verb may require a display. `import lattice_core.ui` must not happen on the CLI path.

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

## §11 Vector export

Every renderer can emit SVG.

- `pixel` → one `<rect>` per cell, merged into runs where adjacent cells share a colour.
- `glyph_ramp`, `glyph_shape`, `bitmask`, `text` → export driven by the renderer's `layout()`
  when it is available (H11): one `<text>` element per glyph, with `font-family`,
  `font-size` and `fill` set. The output is **editable typography**, not traced paths.
- Budget: 2048×2048 source, 16 colours, output under 8 MB. Beyond that, merge cells into rectangles
  and record a warning.
- SVG output must open in Inkscape, Illustrator and a browser without repair.

**Text export (P3, decided 2026-11-16).** `glyph_ramp`, `glyph_shape` and `bitmask` also emit
text — from `layout()` when available (H11): `.txt` (UTF-8, space-separated cells, `\n` line
breaks), `.ansi` (24-bit colour, SGR escapes; terminal-safe ordering), `.html` (a coloured `<pre>`
block in a standalone page). Shared CLI verb: `render --format png|svg|txt|ansi|html`. The ANSI
exporter must not leak escape codes into the text path; HTML output escapes text content.

## §12 Feedback buffer

The mechanism that makes a glitch tool an instrument rather than a filter.

```
f(n) = decay * T(f(n-1)) + input
```

- `decay` in `[0, 0.99]`. Values at or above 1 are rejected at validation.
- `T` is one of: `translate`, `rotate`, `scale`, `displace`, `identity`. Composable.
- The buffer is normalised per frame so it cannot diverge.
- Stability test: 200 iterations on a fixed input, no NaN, no value outside `[0, 1]`, and the mean
  converges.
- Options: `decay`, `transform`, `amount`, `iterations` (1..8), `blend` (`add` | `max` | `screen`).

## §13 Displacement

- Map source: a still image, an image sequence, a noise field, or the feedback buffer.
- Map modes: `luma`, `r`, `g`, `b`, `hue`.
- `dst(x, y) = src(x + k * (mapR - 0.5), y + k * (mapG - 0.5))`, with `k` in pixels.
- `iterations` repeats the displacement with decay, producing a smear without a feedback loop.
- `mask` restricts the effect spatially (§18).
- Sampling is bilinear; edges clamp.

## §14 Pixel sort

- Three thresholds: `black`, `brightness`, `white`. A run starts when a pixel passes `brightness`
  and continues while it stays inside the `black`..`white` band.
- Direction: `rows`, `columns`, `diagonal`.
- Sort key: `luma`, `hue`, `saturation`, `r`, `g`, `b`.
- `mask` acts as an interval map: white pixels are sorted, black pixels are not.
- Runs are sorted with a stable sort so the result is deterministic.

## §15 Channel shift

- Per-channel translate, scale and radial offset. R and B are pushed in opposite directions by
  default, which is what reads as chromatic aberration.
- **Per-channel effect assignment**: any effect may be applied to a subset of channels. This is a
  one-line change in the compositor and produces looks nothing else ships.
- Options: `amount`, `mode` (`translate` | `scale` | `radial`), `channels` (bitmask).

## §16 NTSC / VHS

Signal emulation, not overlay. Artefacts must emerge from the chain.

- Chain: RGB → YIQ → chroma low-pass → chroma subsample → noise injection → demodulate → RGB.
- Parameters: `chroma_lowpass`, `chroma_phase_noise`, `luma_smear`, `luma_noise`, `composite_noise`,
  `bandwidth`, `ringing` (`butterworth` | `constant_k`).
- VHS additions: `head_switching` (displaces the bottom edge), `tracking_noise`, `snow`,
  `sharpening`, `tape_speed` (`sp` | `lp` | `ep`).
- **Usability constraint**: six named presets plus a simple mode with four sliders. The full
  parameter set is behind an advanced toggle. A tool with 14 sliders and no presets is a tool
  nobody opens twice.

## §17 CRT / scanlines

The finishing layer. Static by nature, and that is fine.

- Scanline beam profile, phosphor mask (`slot` | `aperture_grille` | `shadow_mask`), bloom,
  curvature, vignette.
- **The mask scales in device pixels, not image pixels.** A CRT effect that does not know its
  output resolution is a lie.
- Options: `scanline_intensity`, `mask`, `mask_scale`, `bloom`, `curvature`, `vignette`.

## §18 Seed and masks

**Seed.** One seed drives every random operator in a render. Reroll is a single button. Each module
can be locked so a reroll changes the noise without losing the block layout. The seed is serialised
into the preset, so a good accident is reproducible.

**Masks.** A greyscale image, same size as the source, where 0 means no effect and 1 means full
effect. Masks are:
- paintable in the app (brush, gradient, luminance range),
- importable and exportable as PNG,
- referenced by path in the preset, or embedded as base64 when under 64 KB.

A global effect is a filter. A localised effect is a composition. Every glitch effect accepts a
mask.

## §19 Gates

G1 to G4 are inherited from the DitherCraft harness: ruff clean, pytest green, `check_contract`
passes, a task writes only the files it owns.

The dithering application already owns **G5 (v1 preset compatibility)** and **G6 (CLI/GUI parity)**
from the 1.1 harness — those two numbers mean something different there. To keep every gate number
unique across the project's history, this harness numbers its own gates from **G7** (gate registry
in `harness/README.md`; the next new gate is G10):

- **G7 core regression.** After L1, Lattice Dither renders its three witness presets byte-identically
  to the baselines committed at HEAD (`tests/data/baseline/`).
- **G8 renderer contract.** Every registered `CellRenderer` satisfies §3, verified by iterating
  `list_renderers()` so any future renderer is covered automatically.
- **G9 CLI/GUI parity.** For the same preset and image, the CLI and the GUI produce identical
  bytes, in every application (generalises the 1.1 G6).

## §20 Non-goals

Explicitly out of scope for this contract. Adding any of these requires a new contract version.

- Full video and timeline editing. A shared **N-image loop** (GIF/APNG, card L-LOOP) is in
  scope: variation of seed, offset or feedback iterations across N frames; no timeline, no video.
- Physical-media output (LEGO, beads, cross-stitch, embroidery).
- Print separations (CMYK plates, riso, spot inks, trapping, dot gain). **Assumed bet,
  documented, no promise** (P2, decided 2026-11-16): separations and full animation are
  explicitly out and not foreshadowed in any contract version yet.
- Network access in the core. Palette import is file-based or pasted hex.
- Any dependency beyond numpy, numba, Pillow, and PySide6 under the `[ui]` extra.

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
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
--- lattice_core/pipeline.py ---
class PresetMeta:
class EffectInstance:
class PaletteSpec:
class PipelineSpec:
def resolve_palettespec: PaletteSpec, img: Image  # Return the float32 palette described by spec, extracting from img when needed.
def rendersrc: Image, spec: PipelineSpec, *, max_side: int | None=None, renderer: str | None=None, style: RenderStyle | None=None  # Render src through the twelve normative pipeline steps and return uint8 RGB.
def prepare_imagesrc: Image, spec: PipelineSpec, *, max_side: int | None=None, renderer: str | None=None  # Return src after steps 1 to 5, the image palette resolution reads.
def render_with_palettesrc: Image, spec: PipelineSpec, palette: Palette, *, max_side: int | None=None, renderer: str | None=None, style: RenderStyle | None=None  # Render src with an already resolved palette through the twelve pipeline steps.
--- lattice_core/renderers/__init__.py ---

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

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/renderers/bitmask.py` n'existe PAS (à créer). Modèle à suivre :
`lattice_core/renderers/pixel.py` (classe + auto-enregistrement). DEV-208 : ajoutez VOTRE ligne
d'import dans `lattice_core/renderers/__init__.py` par APPEND ATOMIQUE via terminal
(`cat >>`), jamais write_file sur ce fichier, jamais les lignes des autres cartes (L6 ajoute
la sienne) ; votre module s'auto-enregistre à l'import (register_renderer en bout de module).
Le contrat est AMENDÉ (H11) : PAS d'option `dither` (S3 — la décision du sous-point appartient
à l'algorithme au subgrid) ; la géométrie des sous-points vient de `renderer.subgrid()` (S3)
et le pipeline remplit `grid.subindex` (L2b). `layout()` optionnel possible (§3).--- RETRY attempt 2 ---

Les fichiers owns existent (état attempt 1 : 47 tests, suite 1521 verte). Fix exactly what is
reported below, change nothing else, keep passing tests passing.

```json
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "blocker",
      "file": "lattice_core/renderers/bitmask.py",
      "line": 44,
      "what": "_SEXTANT_CODEPOINTS is built with column-major (braille-style) dot numbering, but Unicode BLOCK SEXTANT is row-major.",
      "why": "Unicode NamesList annotates BLOCK SEXTANT-12 as 'upper one third block' and SEXTANT-34 as 'middle one third block', so dot 1=top-left, 2=top-right, 3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right (row-major). The table instead assumes 1/2/3 down the left column and 4/5/6 down the right, so 54 of the 60 present patterns map to the wrong glyph. render()/PNG is unaffected (it rasterises dots via _spans), but codepoints()/layout() emits transposed/misordered sextant glyphs. The E1 premise (4 of 64 patterns have no glyph in U+1FB00..U+1FB3B) is TRUE, but the implementation of the deviation is unsound.",
      "fix": "Rebuild _SEXTANT_CODEPOINTS with the identity mapping k->dot k+1 (row-major, y-major x-minor). The genuinely un-expressible patterns are then the left column {1,3,5} (mask 21) and right column {2,4,6} (mask 42) plus full/empty; map those four to U+0020/U+2588 and a documented 3-dot approximation (not a 2-dot glyph that silently drops a dot)."
    },
    {
      "severity": "major",
      "file": "tests/test_bitmask.py",
      "line": 202,
      "what": "test_sextant_table_matches_unicode_15_1_names hardcodes the same wrong sub_dot={0:1,1:4,2:2,3:5,4:3,5:6} and a special dict {(1,3,5):0x1FB04,(2,4,6):0x1FB09}, then reconstructs the expected table from it.",
      "why": "The test restates the implementation: it rebuilds the table from the coder's own (wrong) dot numbering and therefore cannot fail when the numbering is wrong. It also skips entirely on Unicode < 15.1. This is the one test that should have caught the blocker but blesses it instead.",
      "fix": "Derive the dot-to-position mapping from Unicode names (SEXTANT-12 = upper one third, SEXTANT-34 = middle one third) instead of a hand-written dict, and assert the table against it; keep the skip only when unicodedata < 13.0 (the block exists since 13.0)."
    },
    {
      "severity": "minor",
      "file": "lattice_core/renderers/bitmask.py",
      "line": 10,
      "what": "Module docstring says the four un-expressible sextant patterns are 'the two alternating diagonals' U+1FB04/U+1FB09.",
      "why": "U+1FB04 (SEXTANT-13) and U+1FB09 (SEXTANT-24) are in-block 2-dot sextants — the block CAN express them. The actually un-expressible patterns are the full block, the empty block, and the two full columns {1,3,5}/{2,4,6}. A docstring that lies about the deviation's own mapping.",
      "fix": "Rewrite the sextant bullet to state the true missing set (full, empty, left column, right column) and the chosen approximation for each."
    },
    {
      "severity": "minor",
      "file": "lattice_core/renderers/bitmask.py",
      "line": 135,
      "what": "threshold thresholds palette relative luminance (rel[subindex] < threshold), not `samples` as §9 states.",
      "why": "Documented E1 and coherent under S3 (decision lives in subindex), and the BW accept items are honored. But on a degenerate palette (lum_max==lum_min) rel=0 everywhere, so every cell renders all-ink (full blocks) at the default threshold — the opposite of the pipeline's own _coverage_table degenerate convention (coverage=0 = no ink).",
      "fix": "Either document the palette-relative threshold and its degenerate behaviour explicitly, or map a zero-range palette to all-paper to match _coverage_table."
    }
  ],
  "regression": "none",
  "renderer_invariants": "all six hold (size, purity, no mutation, cell_aspect, unique names, JSON round-trip). The sextant bug is in glyph spatial mapping, not the §3 invariants; braille/quadrant/half_block tables are correct.",
  "tests_that_cannot_fail": [
    "test_sextant_table_matches_unicode_15_1_names (rebuilds the table from the same wrong sub_dot; passes despite 54/60 wrong codepoints)",
    "test_half_black_cell_is_half_filled (sextant/quadrant/half_block branch asserts codepoint == the table under test, restating it; only the braille dot-count branch is a real check)"
  ],
  "notes": "E1 premise verified against Unicode 16.0 NamesList: 4 of 64 sextant patterns (empty, full, left column {1,3,5}, right column {2,4,6}) have no glyph in U+1FB00..U+1FB3B. The deviation is sound in principle; the table that implements it is not. Braille dot bits, quadrant and half_block tables are all correct; only sextant is broken. PNG render path is unaffected. FIX, not ESCALATE — the correct mapping needs no contract change, only a corrected table and a test that derives the numbering from Unicode rather than restating it."
}
```

INSTRUCTIONS DE L'ORCHESTRATEUR :
1. **Blocker sextant** : l'E1 (4 motifs inexprimables) RESTE approuvé, mais implémentez-le
   proprement : _SEXTANT_CODEPOINTS en row-major (dot 1=top-left, 2=top-right, 3=middle-left,
   4=middle-right, 5=bottom-left, 6=bottom-right). Les 4 motifs réellement inexprimables
   (vide, plein, colonne gauche {1,3,5}, colonne droite {2,4,6}) → U+0020, U+2588, et une
   approximation 3-points DOCUMENTÉE (jamais un glyphe 2-points qui perd un point).
2. **Test** : dérivez la numérotation des NOMS Unicode (SEXTANT-12 = « upper one third »,
   SEXTANT-34 = « middle one third ») au lieu d'un dict écrit à la main ; skip seulement si
   unicodedata < 13.0. Le test doit pouvoir échouer si la table est transposée.
3. **Minor docstring** : les inexprimables sont plein/vide/2 colonnes, pas les diagonales.
4. **Minor threshold** : palette dégénérée (lum_max==lum_min) → tout-PAPIER (vide), conforme
   à la convention _coverage_table (coverage 0 = pas d'encre) — le codeur pointait le mauvais côté.
