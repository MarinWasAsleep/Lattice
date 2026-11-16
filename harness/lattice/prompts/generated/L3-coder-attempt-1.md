# Coder prompt — L3 · attempt 1 (généré par l'orchestrateur, 2026-11-16, contrat 0.1.0 gelé)

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

## §12 Colour matching

Amends §5. `nearest_index` gains a metric.

```python
Metric = Literal["srgb", "linear", "oklab", "lab2000"]

def nearest_index(img: Image, palette: Palette, metric: Metric = "srgb") -> Indices
def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray, metric: int) -> int
```

- `metric` is an int code in the numba kernel: 0 srgb, 1 linear, 2 oklab, 3 lab2000.
- **srgb** is the 1.0 behaviour, unchanged, and stays the default. Presets written before 1.1 must
  produce byte-identical output.
- **linear**: sRGB decoded to linear light (the exact piecewise transfer function, not a 2.2 power),
  then squared Euclidean distance.
- **oklab**: sRGB → linear → Oklab (Björn Ottosson's matrices), squared Euclidean distance in
  (L, a, b). No scaling of the axes.
- **lab2000**: sRGB → linear → XYZ (D65) → CIELAB, then the CIEDE2000 difference.
- Palette conversion happens **once per call**, not per pixel. The kernel receives the palette
  already converted to the working space.
- Budget: 1024×1024, K=16, any metric, under 150 ms after warm-up. If lab2000 cannot meet it, a
  precomputed 3D lookup table (33³, trilinear) is allowed; the result must stay within ΔE 0.5 of
  the exact computation on a 1000-pixel sample.

## §13 Pre-dither conditioning

Amends §7. `PipelineSpec` gains three fields, and the normative render order changes.

```python
saturation: float = 0.0      # -1.0 .. 1.0, 0 = unchanged
pre_blur: float = 0.0        # 0.0 .. 20.0 pixels, 0 = off
auto_levels: bool = False    # stretch each channel to its 0.5th/99.5th percentile
color_metric: str = "srgb"   # §12
```

New normative order (replaces §7 steps 1 to 9):

1. If `max_side`: area-downscale so that max(H, W) <= max_side. Call this shape S.
2. Enabled pre-effects in order; effect i gets `default_rng(seed + i)`.
3. `auto_levels` if enabled.
4. `adjust(brightness, contrast, gamma, saturation)`.
5. `pre_blur` if > 0 (separable Gaussian, sigma = pre_blur / 3).
6. `downscale(pixel_size)`.
7. `resolve_palette` on the image from step 6.
8. Algorithm (params through `resolve_params`) → indices → `apply_palette`.
9. `upscale_nearest` back to S.
10. Enabled post-effects in order; effect j gets `default_rng(seed + 1000 + j)`.
11. `to_rgb8`. Output shape = S.

`adjust` signature becomes `adjust(img, brightness, contrast, gamma, saturation=0.0)`. Saturation is
applied in linear light around the luminance, `out = lum + (c - lum) * (1 + saturation)` over the
whole range [-1, 1]. The same multiplicative form is used on both sides: at `saturation = 1` the
distance to the luminance doubles, at `-1` it cancels. A lerp toward the fully saturated colour was
rejected for [0, 1] because it normalises the chroma vector, so a nearly grey pixel reaches full
saturation at a tiny `saturation` and the control jumps. Clipped to [0, 1].

`auto_levels` computes percentiles on the **downscaled proxy** when `max_side` is set, so that the
preview and the full render agree.

## §14 Dither strength

Every algorithm accepts a `strength` parameter, float 0..1, default 1.0. It is added to the
`params` tuple of every registered algorithm that does not already have it.

Semantics, by family:

- **error_diffusion**: the propagated error is multiplied by `strength`.
- **ordered**: the threshold amplitude is multiplied by `strength`.
- **halftone, yliluoma, dbs**: the result is blended in colour space toward the nearest-colour map,
  `out = palette[algo] * s + palette[nearest] * (1 - s)`, then re-quantised. The per-family wording
  of the first draft (spot threshold pulled toward 0.5, candidate search scaled, search radius
  scaled) describes what `strength = 1` looks like, not the interpolation. It was dropped because
  none of the three degenerates to `nearest_index` at 0 under the literal reading, which would break
  the invariant below.
- **other**: the result is blended toward `nearest_index` by `strength` (index-wise: where the
  blend crosses 0.5, take the nearest index).

**Invariant, tested for every registered algorithm**: `strength = 0` produces exactly the output of
`nearest_index(img, palette, metric)`. This is the contract's strongest guarantee and the reason the
parameter is uniform. It is also why the three families above use the blend rather than their own
degenerate form.

## §15 Halftone v2

### §15.1 Palette halftone (algorithms, family `halftone`)

Amends §4 for `halftone_dots`, `halftone_squares`, `halftone_lines`. New parameters:

```python
cell_size: int = 8          # 3 .. 64
angle: float = 45.0         # 0 .. 180 degrees
dot_shape: str = "round"    # round | square | diamond | line | cross | ellipse
oversample: int = 1         # 1 .. 4, anti-aliasing factor on the spot function
per_channel: bool = False   # screen each RGB channel independently, then recombine
strength: float = 1.0       # §14
```

`per_channel = True` applies the screen to R, G and B separately with angles offset by 0°, 30° and
60° from `angle`, then recombines. This is the colour-halftone look without leaving the palette
model.

`dot_shape` defaults to the shape the algorithm's name promises: `round` for `halftone_dots`,
`square` for `halftone_squares`, `line` for `halftone_lines`. A single shared default would make
`squares` and `lines` render exactly what `dots` renders, and would move the 1.0 output of two
algorithms. All six shapes stay reachable from every algorithm through the parameter.

### §15.2 CMYK halftone (effect, not algorithm)

A CMYK screen produces ink coverage, not palette indices, so it cannot be an algorithm under §4.
It is registered as a **post-effect**:

```python
@register_effect("halftone_cmyk", "CMYK Halftone", _CMYK_PARAMS)
def halftone_cmyk(img: Image, params: dict, rng: np.random.Generator) -> Image
```

Parameters: `lpi` (int 20..200, 60), `dot_shape` (round | square | diamond | ellipse),
`black_pullout` (float 0..1, 0.5), `oversample` (int 1..4, 2), `ink_colors` (bool, False).

Screen angles are fixed at the print standard: C 15°, M 75°, Y 0°, K 45°. `lpi` is converted to a
cell size in pixels using 300 DPI as the reference resolution, so that the visual result is stable
across image sizes. `black_pullout` removes the grey component from C, M and Y before screening.
`ink_colors = True` renders the four plates in cyan, magenta, yellow and black on white instead of
greyscale.

## §16 Palette authoring

Amends §6 and §7. `PaletteSpec` gains:

```python
locked: list[str] = field(default_factory=list)   # colours preserved by extraction
order: list[int] = field(default_factory=list)    # display order, empty = natural
```

- `locked` holds `#RRGGBB` colours, not indices: at extraction time no palette exists yet, so an
  index would have nothing to point into. The locked colours are seeded at the front of the
  extraction result and never merged or dropped. `extract_k - len(locked)` colours are extracted,
  never fewer than `MIN_K`; when `len(locked) == extract_k` no extraction runs at all. Duplicate
  locked colours collapse to one slot. If more than `extract_k` distinct colours are locked, or an
  entry is not a colour, extraction raises `ValueError`.
- `order` is a permutation of `range(K)`; an invalid permutation raises `ValueError` at
  `resolve_palette` time. It affects display and export order only, never the rendered image.
- New module `dithercraft/palettes/library.py`:
  ```python
  def library_names() -> list[str]
  def get_library(name: str) -> Palette
  ```
  Backed by `dithercraft/palettes/data/*.hex`, one file per palette, `R G B<tab>name` per line.
  Only palettes whose licence permits redistribution are shipped; each file carries a `# source:`
  and `# licence:` comment line.
- `palettes/io.py` gains `from_hex_text(text) -> Palette`, which accepts a pasted list of
  `#RRGGBB` codes separated by any whitespace, commas or newlines, and ignores other text. This is
  the supported way to import a palette from a web page without network access.
- **No network access in the core.** `tools/fetch_palettes.py` is a separate, manually run script
  that may use `urllib` to populate `palettes/data/`; it is never imported by the application.

## §17 CLI and batch

New module `dithercraft/cli.py`, entry point `python -m dithercraft.cli`.

```
dithercraft.cli render --preset P.json --in A.png --out B.png [--max-side N] [--json]
dithercraft.cli batch  --preset P.json --in-dir SRC --out-dir DST [--jobs N] [--ext png,jpg]
dithercraft.cli info   --preset P.json [--json]
```

- `render` and `batch` call `core.pipeline.render` with the same arguments as the GUI. **Byte
  identical output is required** (gate G6).
- `batch` processes files in sorted order, skips files whose output already exists and is newer
  unless `--force`, and prints one line per file to stderr.
- Exit codes: 0 success, 1 usage error, 2 input error (missing file, unreadable preset), 3 render
  error. Never a traceback on stderr; a one-line message instead.
- `--json` prints a machine-readable summary on stdout: `{"ok": bool, "files": [...], "errors": [...]}`.
- `--jobs` defaults to 1. Parallelism uses `concurrent.futures.ProcessPoolExecutor`; results must be
  identical to `--jobs 1`.

## §18 Preset format v2

Amends §7. `version` becomes 2. A v1 preset loads with the new fields at their defaults and must
render identically (gate G5).

New top-level fields: `color_metric`, `saturation`, `pre_blur`, `auto_levels`, and a `meta` object:

```python
@dataclass
class PresetMeta:
    name: str = ""
    author: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    thumbnail: str = ""      # relative path to a PNG, optional
```

`to_json` writes `version: 2` and `meta`. `from_json` accepts version 1 and 2; any other version
raises `ValueError` naming it. Unknown keys are still ignored, as in 1.0.

Preset search order for the GUI: `presets/` (shipped, read-only) then
`%APPDATA%/LatticeDither/presets/` (user). Saving always targets the user directory. The application
directory is `LatticeDither`, not the pre-rename `DitherCraft`; the bridge keeps a legacy fallback
for its exchange directory only.

## §19 Vector export

New module `dithercraft/export/svg.py`.

```python
def export_svg(rgb8: RGB8, path: Path, *, cell: int = 1, background: str | None = None) -> None
```

- One `<path>` element per distinct colour, `fill` set to the hex code, `shape-rendering="crispEdges"`.
- Cells of the same colour are merged into horizontal runs before being emitted. The file size
  follows the number of runs, not the number of colours: flat artwork produces few runs, a dithered
  render produces about one run per pixel.
- `cell` multiplies the coordinate system (a 1-pixel cell becomes `cell` units), so the SVG scales
  cleanly.
- The document has `width`/`height` in pixels and a `viewBox` in cell units.
- Budget: 2048×2048, 16 colours, **on a dithered render**, under 50 MB and under 5 s. The reference
  content is the worst case, a Floyd-Steinberg render, because that is what the tool produces by
  default and a budget measured on flat artwork would not protect the real output. Measured: 46.45 MB
  in 2.66 s. Flat artwork stays far below (0.49 MB in 0.30 s) and is not the reference.

## §20 Print export

New module `dithercraft/export/print.py`.

```python
def export_print(
    rgb8: RGB8,
    path: Path,
    *,
    dpi: int = 300,
    bleed_mm: float = 0.0,
    crop_marks: bool = False,
    separations: bool = False,
) -> list[Path]
```

- Writes a PNG at `dpi` (metadata only; pixel dimensions unchanged) with an optional bleed border
  filled with the edge colour, and optional crop marks drawn outside the trim area.
- `separations = True` additionally writes one greyscale PNG per ink (`<stem>_C.png`, `_M`, `_Y`,
  `_K`) computed from the CMYK conversion, and returns every path written. The plates cover the trim
  only: the bleed is a replication of the edge and the margin holds marks, so neither carries ink.
  A plate is 255 where its ink is at full strength, so an ink the image does not use is an all-zero
  plate, which reads as black in a greyscale viewer.
- Returns the list of files created, in write order.

## §21 Animation and video

New module `dithercraft/core/animation.py` and `dithercraft/export/video.py`.

```python
def render_sequence(frames: list[Image], spec: PipelineSpec, *, stable: bool = True) -> list[RGB8]
def export_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None
def export_video(frames: list[RGB8], path: Path, *, fps: int = 12) -> bool
```

- `stable = True` is the temporal-stability mode: ordered matrices are anchored to the canvas (not
  to the frame), the palette is resolved once on the first frame and reused, and the error of frame
  n is not carried into frame n+1 (carrying is explicitly out of scope for 1.1).
- `export_gif` uses Pillow only.
- `export_video` returns `False` and writes nothing when no ffmpeg binary can be found; it never
  raises for a missing ffmpeg. It returns `True` on success.
- The ffmpeg binary comes from the `imageio-ffmpeg` dependency, which ships one inside the wheel, so
  `pip install -r requirements.txt` is enough and no system step is needed. A system ffmpeg is the
  fallback when the dependency is absent. This is the one dependency 1.1 adds; the 1.0 rule "no new
  dependency" is amended here, by human decision, and the PyInstaller bundle ships the binary too.
- No other new dependency. ffmpeg is still invoked as a subprocess, never linked.

## §22 Ergonomics

### §22.1 Algorithm gallery

New module `dithercraft/ui/gallery.py`. A grid of thumbnails, one per registered algorithm,
rendered at 96×96 from a fixed test image (the same synthetic image as `tools/contact_sheet.py`),
with the algorithm name underneath and a search box filtering by name and family. Thumbnails are
cached in `%LOCALAPPDATA%/LatticeDither/thumbs/` keyed by `(algorithm_id, params_hash, palette_hash)`
and regenerated when the key changes.

### §22.2 Undo, shortcuts, drag and drop, recent files

New module `dithercraft/ui/commands.py`: an undo stack over `PipelineSpec` (immutable snapshots,
depth 50). `MainWindow` gains:

- `Ctrl+Z` / `Ctrl+Shift+Z` (and `Ctrl+Y`) for undo/redo.
- Drag and drop of image files onto the window opens the first one.
- A `File > Recent` menu with the last 10 images, persisted in `QSettings`.
- `Ctrl+O`, `Ctrl+S`, `Ctrl+E` (export), `Ctrl+Shift+S` (send to PhotoCraft), `F5` (re-render),
  `Space` (toggle before/after), `Left`/`Right` (previous/next preset, already present).

### §22.3 Localisation

New package `dithercraft/i18n/` with `en.json` and `fr.json`, and:

```python
def tr(key: str, **kwargs) -> str
def set_language(code: str) -> None   # "en" | "fr"
def current_language() -> str
```

- Every user-visible string in `ui/` goes through `tr()`. No literal UI string outside the JSON
  files. Tests assert on `tr()` output, never on a literal.
- The French file uses **tramage** for dithering, **palette** unchanged, **algorithme**,
  **avant/après**, **force**, **densité**.
- Language is chosen from `QSettings`, defaulting to the system locale, falling back to `en`.

## §23 Pre-processing: Pixel Snapper and descreen

New package `dithercraft/preprocess/`.

```python
def detect_grid(img: Image) -> tuple[int, int, int, int, float]
    # (cell_w, cell_h, offset_x, offset_y, confidence) — confidence in 0..1
def snap_to_grid(img: Image, grid: tuple[int, int, int, int]) -> Image
def descreen(img: Image, *, strength: float = 1.0) -> Image
```

- `detect_grid` uses autocorrelation of the edge magnitude along both axes. It returns
  `confidence < 0.5` when no convincing grid is found; callers must then leave the image untouched.
  **A pre-pass that damages a photo is worse than no pre-pass.**
- `snap_to_grid` resamples with nearest neighbour onto the detected grid, removing anti-aliasing.
- `descreen` suppresses a periodic halftone screen: FFT, notch the dominant off-centre peaks,
  inverse FFT, then a light median. `strength` blends between the original and the result.
- Both are exposed in the UI as an optional "Prepare source" step, off by default, with the detected
  grid and confidence shown before applying.

## §24 Bridge v2

Amends §8. Additions only; every 1.0 behaviour is preserved.

- `place_as_layer` gains `name: str | None = None` so the created layer can be named after the
  preset.
- New `preview_layer(rgb8, name) -> int`: places a layer, returns its index, and remembers it so a
  subsequent `update_preview_layer(rgb8)` replaces its content instead of stacking new layers.
  `commit_preview_layer()` renames it and forgets the handle.
- New `documents() -> list[dict]` returning the `ui.inspect` document list, and
  `render_document(index: int)` to pull a specific document rather than the active one.
- Every call keeps the 1.0 guarantees: relative `/` paths, `auth` first on each connection, the
  document left untouched, cleanup in a `finally`.
- Timeouts: 5 s for control calls, 60 s for `app.save` on documents above 4000 px.

---

## §25 Gates

| Gate | Command | Passes when |
|---|---|---|
| G1 | `ruff check .` | no finding |
| G2 | `pytest -q` | all tests pass, no new skip |
| G3 | `python tools/check_contract.py` | exit 0 |
| G4 | ownership check | every changed file is in the card's `owns` |
| G5 | `pytest -q tests/test_preset_compat.py` | the three witness presets render byte-identically to the 1.0 baseline |
| G6 | `pytest -q tests/test_cli_parity.py` | CLI and GUI renders are byte-identical |

G5 and G6 are new in 1.1 and are gates, not informative tests. A task that breaks either is not done.

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
--- lattice_core/color.py ---
def to_floatimg: PILImage.Image  # Convert any Pillow image to float32 RGB in [0, 1], compositing alpha over white.
def to_rgb8img: Image  # Convert a float32 image in [0, 1] to uint8, rounding half up and clipping.
def to_pilrgb8: RGB8  # Wrap a uint8 RGB array in a Pillow image.
def luminanceimg: Image  # Return the sRGB luminance of every pixel as a float32 (H, W) array.
def nearest_indeximg: Image, palette: Palette, metric: str='srgb'  # Return the index of the closest palette colour for every pixel, under metric.
def metric_codemetric: str | int  # Return the kernel code of a colour metric name, or pass an int code through.
def to_working_spaceimg: Image, metric: str | int  # Convert an sRGB image or palette to the space the metric compares in.
def srgb_to_oklabimg: Image  # Convert sRGB values in [0, 1] to Oklab (Ottosson's matrices, no axis scaling).
def srgb_to_labimg: Image  # Convert sRGB values in [0, 1] to CIELAB under the D65 white point.
def apply_paletteidx: Indices, palette: Palette  # Map palette indices back to float32 colours.
def adjustimg: Image, brightness: float, contrast: float, gamma: float, saturation: float=0.0  # Apply gamma, contrast around 0.5, brightness and saturation, clipping to [0, 1].
def srgb_to_linearimg: Image  # Decode sRGB-encoded values in [0, 1] to linear light with the exact transfer function.
def linear_to_srgbimg: Image  # Encode linear-light values in [0, 1] back to sRGB with the exact transfer function.
def auto_levelsimg: Image, low: float=0.5, high: float=99.5  # Stretch each channel between its low and high percentiles, clipping to [0, 1].
def gaussian_blurimg: Image, sigma: float  # Blur img with a separable Gaussian of the given sigma; sigma <= 0 is a no-op.
def downscaleimg: Image, factor: int  # Average factor x factor blocks, replicating the edge when the size is not divisible.
def upscale_nearestimg: Image, factor: int, shape: tuple[int, int]  # Repeat every pixel factor times, then crop to shape.
def nearest_index_pxr: float, g: float, b: float, palette: np.ndarray, metric: int=0  # Return the index of the palette colour closest to (r, g, b); numba kernel.
--- lattice_core/types.py ---
class ParamSpec:
--- lattice_core/presets.py ---
def shipped_preset_dir  # Return the read-only shipped preset directory that sits next to the package.
def user_preset_dir  # Return the user preset directory under %APPDATA%, without creating it.
def preset_search_dirs  # Return the preset search order: the shipped directory first, then the user one.
def list_presetsdirectories: Sequence[Path] | None=None  # List the presets of the search directories, shipped first, a user file winning a tie.
def resolve_presetname: str, directories: Sequence[Path] | None=None  # Return the file a preset name resolves to, the user tier winning over the shipped one.
def is_withinpath: str | Path, directory: str | Path  # Return True when path is directory itself or lies inside it.
def to_jsonspec: PipelineSpec  # Serialise spec to indented JSON at the current preset version, keys in field order.
def from_jsontext: str  # Parse JSON into a PipelineSpec, validating the version, ids and metric.
def save_presetpath: str | Path, spec: PipelineSpec  # Write spec as UTF-8 JSON to path, creating parent directories.
def load_presetpath: str | Path  # Read a UTF-8 JSON preset file and parse it into a PipelineSpec.

TASK CARD
### L3 · Colour metrics and palette model
- wave: 0 · deps: L1 · executor: OMH deep · review: full · size: M
- owns: `lattice_core/color.py`, `lattice_core/palette.py`, `tests/test_color.py`,
  `tests/test_palette.py`
- context: §4, 1.1 §12, 1.1 §16
- spec: port the 1.1 colour metrics (`srgb`, `linear`, `oklab`, `lab2000`) into `lattice_core`.
  Add `Palette.lum_min` / `lum_max` computed once at construction in linear light. Palette import
  accepts hex lists, GPL files, PNG images and Lospec-style text; no network. `Palette.order` is a
  permutation or `None`.
- accept:
  - `srgb` output is byte-identical to the 1.0 implementation on 20 random images and 5 palettes.
  - `oklab` and `lab2000` disagree with `srgb` on at least 5 % of pixels of a saturated test image.
  - `lum_min`/`lum_max` are correct on a two-colour palette within 1e-6.
  - a GPL file, a PNG and a hex list of the same palette produce equal `Palette` objects.
  - a non-permutation `order` raises `ValueError` naming the offending index.
  - no import of `urllib`, `requests` or `socket` anywhere in `palette.py`.

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/color.py` existe (déplacé par L1 — lisez-le, ses signatures sont ci-dessus) ; les
métriques `srgb`/`linear`/`oklab`/`lab2000` y sont déjà présentes (1.1 §12 porté par L1).
`lattice_core/palette.py` n'existe PAS (à créer). `tests/test_color.py` et
`tests/test_palette.py` n'existent pas (à créer). Les palettes vivent aujourd'hui dans le
package `lattice_core/palettes/` (builtin, extract, io, library, data) — le modèle `Palette`
de `lattice_core/types.py` est déjà utilisé par `color`/`pipeline` ; ne changez pas leur contrat
d'usage. Le module `importer` vient de `lattice_core/palettes/io.py` (from_hex_text etc.).