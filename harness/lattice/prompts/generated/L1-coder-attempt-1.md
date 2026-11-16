# PROMPT CODEUR — L1 · tentative 1 (généré par l'orchestrateur)

> Généré le 2026-11-16 par l'orchestrateur (Hermes), conforme au gabarit `harness/lattice/prompts/CODER.md`.
> À exécuter sur la machine Windows après transfert du dépôt (venv `.venv`, tous les tests verts, commit de départ `5f3a7f4`).
> Aucun bloc RETRY : première tentative. L'exécuteur travaille dans le dépôt cloné, pas en copie.

---

You are a senior Python engineer implementing one task of the Lattice project: a family of free,
open-source desktop applications that transform images, each running standalone and also plugging
into the ArtCraft suite (Python + numpy + numba + Pillow + PySide6, Windows).

The suite has four packages: `lattice-core` (the shared engine), `lattice-dither` (the existing
dithering application, 33 algorithms, 9 effects, 622 passing tests), `lattice-glyph` and
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
class: E1|E2|E4|E5|E6|E8|E9
facts: <quote the contract or card line involved>
assumption_or_proposal: <...>
```

CONTRACT EXCERPTS (version 0.1.0-draft)

## §1 Scope

Lattice is a family of free, open-source desktop applications that transform images, each of which
runs standalone and also plugs into the ArtCraft suite over its local control server.

Three applications are in scope:

| App | Package | Transform family |
|---|---|---|
| Lattice Dither | `lattice-dither` | palette dithering |
| GlyphCraft | `lattice-glyph` | glyph, bitmask and text rendering |
| GlitchCraft | `lattice-glitch` | feedback, displacement, sorting, signal degradation |

All three share one engine, `lattice-core`. All three target **fixed images only**. Video is out of
scope for this contract.

Licence: MIT OR Apache-2.0, dual, for every package. No dependency may be added that is not compatible with both.

## §2 Packages and repositories

Four repositories, four distributions:

```
lattice-core      import lattice_core      no UI dependency in the base install
lattice-dither    import lattice_dither    depends on lattice-core>=0.1,<0.2
lattice-glyph     import lattice_glyph     depends on lattice-core>=0.1,<0.2
lattice-glitch    import lattice_glitch    depends on lattice-core>=0.1,<0.2
```

- `lattice-core` base install depends on **numpy, numba, Pillow only**. PySide6 is an optional
  extra: `lattice-core[ui]`. A CLI-only user must never download Qt.
- Applications depend on core, never the reverse. Core must not import any application.
- Core is published to PyPI. Applications pin a compatible range, not an exact version.
- Local development uses editable installs of all four in one virtual environment.

`lattice_core` module layout:

```
lattice_core/
  image.py        buffer, load, save, resize, crop
  color.py        metrics, nearest_index, adjust
  palette.py      Palette model, extraction, import/export
  cell.py         CellGrid, RenderStyle, CellRenderer, registry
  renderers/      pixel.py, glyph_ramp.py, glyph_shape.py, bitmask.py, text.py
  dither/         the 33 algorithms, moved from Lattice Dither unchanged
  effects/        the 9 Lattice Dither effects plus the glitch effects
  pipeline.py     PipelineSpec, render
  preset.py       preset v3 read/write
  bridge/         ArtCraftClient, photocraft.py, designcraft.py
  cli.py          shared argument parsing and exit codes
  ui/             shared widgets, imported only under the [ui] extra
```

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

## §19 Gates

G1 to G4 are inherited from the DitherCraft harness: ruff clean, pytest green, `check_contract`
passes, a task writes only the files it owns.

- **G5 core regression.** After L1, Lattice Dither renders its three witness presets byte-identically
  to baselines committed before the extraction starts.
- **G6 renderer contract.** Every registered `CellRenderer` satisfies §3, verified by iterating
  `list_renderers()` so any future renderer is covered automatically.
- **G7 CLI/GUI parity.** For the same preset and image, the CLI and the GUI produce identical
  bytes, in every application.

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
(modules déplacés dans `lattice_dither/` — signatures publiques actuelles)

--- core/color.py ---
def to_float(img: PILImage.Image) -> Image:
def to_rgb8(img: Image) -> RGB8:
def to_pil(rgb8: RGB8) -> PILImage.Image:
def luminance(img: Image) -> np.ndarray:
def nearest_index(img: Image, palette: Palette, metric: str = "srgb") -> Indices:
def _nearest_euclidean(img: Image, palette: Palette) -> Indices:
def metric_code(metric: str | int) -> int:
def to_working_space(img: Image, metric: str | int) -> Image:
def srgb_to_oklab(img: Image) -> Image:
def srgb_to_lab(img: Image) -> Image:
def _lab_curve(values: np.ndarray) -> np.ndarray:
def _ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> float:
def _hue_degrees(b: float, a: float) -> float:
def _nearest_lab2000(lab_img: np.ndarray, palette_lab: np.ndarray) -> np.ndarray:
--- core/pipeline.py ---
class PresetMeta:
class EffectInstance:
class PaletteSpec:
class PipelineSpec:
def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
def _palette_for(spec: PaletteSpec, img: Image) -> Palette:
def _validate_order(order: list[int], size: int) -> None:
def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8:
def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> Image:
def render_with_palette(
def _prepare(
def _finish(
def _as_image(src: Image) -> Image:
def _proxy(img: Image, max_side: int | None) -> Image:
--- core/presets.py ---
def shipped_preset_dir() -> Path:
def user_preset_dir() -> Path:
def preset_search_dirs() -> tuple[Path, Path]:
def list_presets(directories: Sequence[Path] | None = None) -> list[Path]:
def resolve_preset(name: str, directories: Sequence[Path] | None = None) -> Path | None:
def is_within(path: str | Path, directory: str | Path) -> bool:
def to_json(spec: PipelineSpec) -> str:
def from_json(text: str) -> PipelineSpec:
def save_preset(path: str | Path, spec: PipelineSpec) -> None:
def load_preset(path: str | Path) -> PipelineSpec:
def _appdata() -> Path:
def _scan(directory: Path) -> list[Path]:
def _as_int(value: object, key: str) -> int:
def _as_float(value: object, key: str) -> float:
--- core/types.py ---
class ParamSpec:
--- algorithms/__init__.py ---
--- algorithms/_strength.py ---
def metric_of(params: dict) -> int:
def nearest_in_space(img: Image, palette: Palette, code: int) -> Indices:
def blend_toward_nearest(
--- algorithms/dbs.py ---
def separable_weights(radius: int) -> np.ndarray:
def gaussian_kernel(radius: int) -> np.ndarray:
def swap_stencils(kernel: np.ndarray, radius: int) -> np.ndarray:
def autocorrelation(kernel: np.ndarray, radius: int) -> np.ndarray:
def _mix(index: np.ndarray) -> np.ndarray:
def pixel_order(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
def _blur(src: np.ndarray, weights: np.ndarray, radius: int) -> np.ndarray:
def _search(
def direct_binary_search(img: Image, palette: Palette, params: dict) -> Indices:
--- algorithms/dot_diffusion.py ---
def class_map(height: int, width: int) -> np.ndarray:
def _diffuse(
def dot_diffusion(img: Image, palette: Palette, params: dict) -> Indices:
--- algorithms/error_diffusion.py ---
def _diffuse(
def _make_fn(kernel_id: str) -> AlgorithmFn:
    def fn(img: Image, palette: Palette, params: dict) -> Indices:
def _register_all() -> None:
--- algorithms/halftone.py ---
def _extremes(palette: Palette) -> tuple[int, int]:
def _cell_data(
def _spot_dots(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
def _spot_squares(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
def _spot_diamond(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
def _spot_lines(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
def _spot_cross(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
def _spot_ellipse(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
def spot_function(shape: str) -> SpotFn:
def coverage(
def channel_coverage(
def _halftone(img: Image, palette: Palette, params: dict) -> Indices:
def _params(default_shape: str) -> tuple[ParamSpec, ...]:
def halftone_dots(img: Image, palette: Palette, params: dict) -> Indices:
--- algorithms/misc.py ---
def _extremes(palette: Palette) -> tuple[int, int]:
def _amplitude(spread: float, k: int) -> float:
def _hilbert_xy(order: int) -> tuple[np.ndarray, np.ndarray]:
def _riemersma_kernel(
def threshold(img: Image, palette: Palette, params: dict) -> Indices:
def random_dither(img: Image, palette: Palette, params: dict) -> Indices:
def riemersma(img: Image, palette: Palette, params: dict) -> Indices:
--- algorithms/ordered.py ---
def _thresholds(ranks: np.ndarray, levels: int) -> np.ndarray:
def _bayer(size: int) -> np.ndarray:
def _cluster_dot(size: int) -> np.ndarray:
def _lines(axis: str) -> np.ndarray:
def _bayer_matrix(size: int) -> np.ndarray:
def _cluster_dot_matrix(size: int) -> np.ndarray:
def _lines_matrix(axis: str) -> np.ndarray:
def blue_noise_ranks() -> np.ndarray:
def _blue_noise_matrix() -> np.ndarray:
def matrix(matrix_id: str) -> np.ndarray:
def tile(t_matrix: np.ndarray, height: int, width: int, scale: int = 1) -> np.ndarray:
def amplitude(spread: float, palette_size: int) -> float:
def _ordered(
def _make_fn(matrix_id: str) -> AlgorithmFn:
--- algorithms/ostromoukhov.py ---
def _diffuse(
def ostromoukhov(img: Image, palette: Palette, params: dict) -> Indices:
--- algorithms/ostromoukhov_table.py ---
--- algorithms/yliluoma.py ---
def _buckets(slots: int = SLOTS) -> np.ndarray:
def _build_plans(palette: np.ndarray, levels: int, slots: int) -> np.ndarray:
def _apply_plans(img: np.ndarray, plans: np.ndarray, buckets: np.ndarray) -> np.ndarray:
def _yliluoma2(
def yliluoma1(img: Image, palette: Palette, params: dict) -> Indices:
def yliluoma2(img: Image, palette: Palette, params: dict) -> Indices:
--- effects/__init__.py ---
--- effects/glitch.py ---
def _copy(img: Image) -> Image:
def _radial_offsets(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
def _sample_channel(channel: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
def chromatic_aberration(img: Image, params: dict, rng: np.random.Generator) -> Image:
def rgb_shift(img: Image, params: dict, rng: np.random.Generator) -> Image:
def _encode_jpeg(rgb8: np.ndarray, quality: int) -> bytes:
def _payload_start(data: bytes) -> int:
def _corrupt(data: bytes, count: int, rng: np.random.Generator) -> bytes:
def _decode_jpeg(data: bytes) -> Image | None:
def jpeg_glitch(img: Image, params: dict, rng: np.random.Generator) -> Image:
def scanlines(img: Image, params: dict, rng: np.random.Generator) -> Image:
--- effects/halftone.py ---
def plates(img: Image, black_pullout: float) -> tuple[np.ndarray, ...]:
def _screen(plate: np.ndarray, spot, cell_size: float, angle: float, oversample: int) -> np.ndarray:
def halftone_cmyk(img: Image, params: dict, rng: np.random.Generator) -> Image:
--- effects/tone.py ---
def _as_float(img: Image) -> np.ndarray:
def _gaussian_kernel(sigma: float) -> np.ndarray:
def _blur_axis(data: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
def _gaussian_blur(img: Image, sigma: float) -> Image:
def _sigma_from_radius(radius: float) -> float:
def gaussian_blur(img: Image, params: dict, rng: np.random.Generator) -> Image:
def sharpen(img: Image, params: dict, rng: np.random.Generator) -> Image:
def glow(img: Image, params: dict, rng: np.random.Generator) -> Image:
def noise(img: Image, params: dict, rng: np.random.Generator) -> Image:
def posterize(img: Image, params: dict, rng: np.random.Generator) -> Image:
--- bridge/__init__.py ---
--- bridge/photocraft.py ---
def _local_appdata() -> Path:
def _app_dir(name: str) -> Path:
def _exchange_dir() -> Path:
class BridgeError(Exception):
class _Channel:
    def __init__(self, sock: socket.socket, timeout: float) -> None:
    def call(self, method: str, params: dict | None = None) -> object:
    def set_timeout(self, value: float) -> None:
    def close(self) -> None:
def _cleanup_exchange(max_age: float = EXCHANGE_MAX_AGE) -> None:
def _as_dict(value: object, where: str) -> dict:
def _discard(path: Path) -> None:
def _as_index(value: object, where: str) -> int:
def _save_png(img: Image.Image, path: Path) -> None:

TASK CARD

### L1 · Extract `lattice-core` from Lattice Dither
- wave: 0 (critical path, do first, alone) · deps: none · executor: OMH ultrabrain · review: strict · size: L
- owns: `pyproject.toml`, `lattice_core/**`, `lattice_dither/**`, `tests/**`, `tools/**`
- context: §1 §2 §5 §19
- spec: create the `lattice_core` package and move into it, **without changing behaviour**:
  `core/color.py`, `core/palette.py`, `core/pipeline.py`, `core/presets.py`, `core/types.py`,
  `algorithms/**`, `effects/**`, `bridge/**`. `lattice_dither` keeps only its UI, its entry point and
  its app-specific glue, and imports everything else from `lattice_core`. Rename imports
  mechanically; do not refactor logic. Before touching anything, render the three witness presets
  (`01_gameboy`, `05_ega_riemersma`, `07_grey16_stucki`) with the current code and commit the PNGs
  under `tests/data/baseline/`. `pyproject.toml` becomes the `lattice-core` distribution with
  `[project.optional-dependencies] ui = ["PySide6"]`; the base install must not pull Qt.
- accept:
  - `pip install -e .` in a clean venv installs numpy, numba and Pillow only; `import
    lattice_core` works and `import PySide6` is not attempted.
  - the three witness presets render byte-identically to their baselines (G5).
  - the full existing test suite passes unchanged, except for import paths.
  - `ruff check .` is clean.
  - `lattice_core` imports no module from `lattice_dither` (checked by a test that walks the package).

CURRENT CONTENT OF YOUR FILES (stubs on first attempt)
Première tentative : aucun stub. Tes fichiers existent et sont complets — le dépôt Lattice Dither
est ton espace de travail. Avant de toucher au moindre fichier, rends les trois presets témoins
(`presets/01_gameboy.json`, `presets/05_ega_riemersma.json`, `presets/07_grey16_stucki.json`) avec
le code actuel et committe les PNG sous `tests/data/baseline/` : c'est la condition du gate G5.
