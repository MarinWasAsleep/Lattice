# Coder prompt — L2 · attempt 1 (généré par l'orchestrateur, 2026-11-16)

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

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT

--- lattice_core/pipeline.py ---
class PresetMeta:
class EffectInstance:
class PaletteSpec:
class PipelineSpec:
def resolve_palette(spec: PaletteSpec, img: Image)  # Return the float32 palette described by spec, extracting from img when needed.
def render(src: Image, spec: PipelineSpec, *, max_side: int | None=None)  # Render src through the eleven normative pipeline steps and return uint8 RGB.
def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None=None)  # Return src after steps 1 to 5, the image palette resolution reads.
def render_with_palette(src: Image, spec: PipelineSpec, palette: Palette, *, max_side: int | None=None)  # Render src with an already resolved palette, skipping step 5's resolution.

--- lattice_core/registry.py ---
class AlgorithmInfo:
class EffectInfo:
def register_algorithm(id: str, name: str, family: str, params: tuple[ParamSpec, ...]=())  # Return a decorator that registers an algorithm under id.
def register_effect(id: str, name: str, params: tuple[ParamSpec, ...]=())  # Return a decorator that registers an effect under id.
def get_algorithm(id: str)  # Return the algorithm registered under id, or raise KeyError.
def list_algorithms()  # Return every registered algorithm, sorted by family then name.
def get_effect(id: str)  # Return the effect registered under id, or raise KeyError.
def list_effects()  # Return every registered effect, sorted by name.
def resolve_params(specs: tuple[ParamSpec, ...], given: dict)  # Fill defaults, clamp numbers to their bounds, cast ints and validate choices.

--- lattice_core/types.py ---
class ParamSpec:

--- lattice_core/color.py ---
def to_float(img: PILImage.Image)  # Convert any Pillow image to float32 RGB in [0, 1], compositing alpha over white.
def to_rgb8(img: Image)  # Convert a float32 image in [0, 1] to uint8, rounding half up and clipping.
def to_pil_rgb8(rgb8: RGB8)  # Wrap a uint8 RGB array in a Pillow image.
def luminance(img: Image)  # Return the sRGB luminance of every pixel as a float32 (H, W) array.
def nearest_index(img: Image, palette: Palette, metric: str='srgb')  # Return the index of the closest palette colour for every pixel, under metric.
def metric_code(metric: str | int)  # Return the kernel code of a colour metric name, or pass an int code through.
def to_working_space(img: Image, metric: str | int)  # Convert an sRGB image or palette to the space the metric compares in.
def srgb_to_oklab(img: Image)  # Convert sRGB values in [0, 1] to Oklab (Ottosson's matrices, no axis scaling).
def srgb_to_lab(img: Image)  # Convert sRGB values in [0, 1] to CIELAB under the D65 white point.
def apply_palette(idx: Indices, palette: Palette)  # Map palette indices back to float32 colours.
def adjust(img: Image, brightness: float, contrast: float, gamma: float, saturation: float=0.0)  # Apply gamma, contrast around 0.5, brightness and saturation, clipping to [0, 1].
def srgb_to_linear(img: Image)  # Decode sRGB-encoded values in [0, 1] to linear light with the exact transfer function.
def linear_to_srgb(img: Image)  # Encode linear-light values in [0, 1] back to sRGB with the exact transfer function.
def auto_levels(img: Image, low: float=0.5, high: float=99.5)  # Stretch each channel between its low and high percentiles, clipping to [0, 1].
def gaussian_blur(img: Image, sigma: float)  # Blur img with a separable Gaussian of the given sigma; sigma <= 0 is a no-op.
def downscale(img: Image, factor: int)  # Average factor x factor blocks, replicating the edge when the size is not divisible.
def upscale_nearest(img: Image, factor: int, shape: tuple[int, int])  # Repeat every pixel factor times, then crop to shape.
def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray, metric: int=0)  # Return the index of the palette colour closest to (r, g, b); numba kernel.

--- lattice_core/presets.py ---
def shipped_preset_dir()  # Return the read-only shipped preset directory that sits next to the package.
def user_preset_dir()  # Return the user preset directory under %APPDATA%, without creating it.
def preset_search_dirs()  # Return the preset search order: the shipped directory first, then the user one.
def list_presets(directories: Sequence[Path] | None=None)  # List the presets of the search directories, shipped first, a user file winning a tie.
def resolve_preset(name: str, directories: Sequence[Path] | None=None)  # Return the file a preset name resolves to, the user tier winning over the shipped one.
def is_within(path: str | Path, directory: str | Path)  # Return True when path is directory itself or lies inside it.
def to_json(spec: PipelineSpec)  # Serialise spec to indented JSON at the current preset version, keys in field order.
def from_json(text: str)  # Parse JSON into a PipelineSpec, validating the version, ids and metric.
def save_preset(path: str | Path, spec: PipelineSpec)  # Write spec as UTF-8 JSON to path, creating parent directories.
def load_preset(path: str | Path)  # Read a UTF-8 JSON preset file and parse it into a PipelineSpec.

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

CURRENT CONTENT OF YOUR FILES (stubs on first attempt)

Aucun des fichiers `owns` n'existe encore au premier essai : `lattice_core/cell.py` absent,
`lattice_core/renderers/` absent, `tests/test_cell.py` absent. `lattice_core/pipeline.py` existe
déjà (déplacé par L1 sans changement de comportement) : lisez-le avant de le modifier — son
interface publique est donnée ci-dessus dans SIGNATURES, son implémentation complète est dans le
repo. `pipeline.render` implémente aujourd'hui les onze étapes avec la paire 1.0
`apply_palette` + `upscale_nearest` (ces fonctions vivent dans `lattice_core/color.py`).
