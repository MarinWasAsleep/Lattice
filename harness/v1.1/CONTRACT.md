# DitherCraft technical contract — version 1.1.0-draft

**Delta over 1.0.0.** Sections §1 to §11 of `harness/v1.0/CONTRACT.md` (version 1.0.0) remain in force
and are not repeated here. This document adds §12 to §24 and amends §3 and §7 as stated below.

Versioning: PATCH = clarification, no code impact. MINOR = additive, backward compatible.
MAJOR = breaking; forbidden without human approval.

Freeze at checkpoint H5, after T17.

---

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
applied in linear light around the luminance, `out = lum + (c - lum) * (1 + saturation)` for
saturation in [-1, 0], and a lerp toward the fully saturated colour for [0, 1]. Clipped to [0, 1].

`auto_levels` computes percentiles on the **downscaled proxy** when `max_side` is set, so that the
preview and the full render agree.

## §14 Dither strength

Every algorithm accepts a `strength` parameter, float 0..1, default 1.0. It is added to the
`params` tuple of every registered algorithm that does not already have it.

Semantics, by family:

- **error_diffusion**: the propagated error is multiplied by `strength`.
- **ordered**: the threshold amplitude is multiplied by `strength`.
- **halftone**: the spot threshold is pulled toward 0.5 by `strength`.
- **other**: the result is blended toward `nearest_index` by `strength` (index-wise: where the
  blend crosses 0.5, take the nearest index).

**Invariant, tested for every registered algorithm**: `strength = 0` produces exactly the output of
`nearest_index(img, palette, metric)`. This is the contract's strongest guarantee and the reason the
parameter is uniform.

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
locked: list[int] = field(default_factory=list)   # indices preserved by extraction
order: list[int] = field(default_factory=list)    # display order, empty = natural
```

- `locked` indices are seeded into the extraction result and never merged or dropped. If more than
  `extract_k` indices are locked, extraction raises `ValueError`.
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
`%APPDATA%/DitherCraft/presets/` (user). Saving always targets the user directory.

## §19 Vector export

New module `dithercraft/export/svg.py`.

```python
def export_svg(rgb8: RGB8, path: Path, *, cell: int = 1, background: str | None = None) -> None
```

- One `<path>` element per distinct colour, `fill` set to the hex code, `shape-rendering="crispEdges"`.
- Cells of the same colour are merged into horizontal runs before being emitted, so a 1024×1024
  image with 16 colours stays well under 8 MB.
- `cell` multiplies the coordinate system (a 1-pixel cell becomes `cell` units), so the SVG scales
  cleanly.
- The document has `width`/`height` in pixels and a `viewBox` in cell units.
- Budget: 2048×2048, 16 colours, under 8 MB and under 5 s.

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
  `_K`) computed from the CMYK conversion, and returns every path written.
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
- `export_video` returns `False` and writes nothing when ffmpeg is not on `PATH`; it never raises
  for a missing ffmpeg. It returns `True` on success.
- No new dependency. ffmpeg is invoked as a subprocess if present.

## §22 Ergonomics

### §22.1 Algorithm gallery

New module `dithercraft/ui/gallery.py`. A grid of thumbnails, one per registered algorithm,
rendered at 96×96 from a fixed test image (the same synthetic image as `tools/contact_sheet.py`),
with the algorithm name underneath and a search box filtering by name and family. Thumbnails are
cached in `%LOCALAPPDATA%/DitherCraft/thumbs/` keyed by `(algorithm_id, params_hash, palette_hash)`
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
