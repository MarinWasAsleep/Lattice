# Coder prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

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

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
{{SIGNATURES}}

TASK CARD
{{TASK_CARD}}

CURRENT CONTENT OF YOUR FILES (stubs on first attempt)
{{OWNED_FILES}}

{{RETRY_BLOCK}}
<!-- RETRY_BLOCK, only on retries:
RETRY attempt {{N}}. Fix exactly what is reported below, change nothing else, keep passing tests passing.
{{GATE_LOG_OR_REVIEW_FINDINGS}}
-->



CONTRACT EXCERPTS (version 0.1.0)


## §1 Scope

Lattice is a family of free, open-source desktop applications that transform images, each of which
runs standalone and also plugs into the ArtCraft suite over its local control server.

Three applications are in scope:

| App | Package | Transform family |
|---|---|---|
| Lattice Dither | `lattice-dither` | palette dithering |
| Lattice Glyph | `lattice-glyph` | glyph, bitmask and text rendering |
| Lattice Glitch | `lattice-glitch` | feedback, displacement, sorting, signal degradation |

All three share one engine, `lattice-core`. All three target **fixed images only**. Video is out of
scope for this contract.

All packages run on **Windows and Linux** (the dither application already does; ArtCraft hosts exist
on both, so the bridge is testable on both). Card L23 covers packaging and install per platform.

Licence: MIT OR Apache-2.0, dual, for every package. No dependency may be added that is not compatible with both.


## §2 Packages and repositories

Four repositories, four distributions:

```
lattice-core      import lattice_core      no UI dependency in the base install
lattice-dither    import lattice_dither    depends on lattice-core>=0.1,<0.2
lattice-glyph     import lattice_glyph     depends on lattice-core>=0.1,<0.2
lattice-glitch    import lattice_glitch    depends on lattice-core>=0.1,<0.2
```

**What L1 actually moves** (current tree at HEAD `b4b0aea`, portage Linux approuvé): `core/{color,pipeline,presets,types,registry}.py`,
the `palettes/` package, `dither/` (from `algorithms/`), `effects/`, `bridge/`. The application keeps
`ui/`, `export/`, `preprocess/`, `i18n/` and its own `cli.py` (the 1.1 verbs are app-specific; the shared CLI
frame is created with the application shells). `core/animation.py` is moved into `lattice_core` by
card L-LOOP (N-image loop, decided 2026-11-16); full video is out of scope for the suite (H11
coherence pass). There is no `core/palette.py` in the current tree:
palettes are a package. `image.py`, `cell.py` and `renderers/` are created by the cards (L2+).

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
  effects/        the 10 Lattice Dither effects plus the glitch effects
  pipeline.py     PipelineSpec, render
  preset.py       preset v3 read/write
  bridge/         ArtCraftClient, photocraft.py, designcraft.py
  cli.py          shared argument parsing and exit codes   (frame built with the app shells, L12/L20)
  ui/             shared widgets, imported only under the [ui] extra.
                  Owned by card L-UI (after L5, before L12/L20, decided 2026-11-16): preview
                  canvas + worker with before/after split, Looks grid (thumbnails on the
                  current image), one full-resolution export dialog, bridge status dot, empty
                  state. L-UI fixes the two blocker findings of the Dither product review
                  (export resolution, preset indicator) first.
```


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


PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
# --- lattice_core/pipeline ---
  class PresetMeta:
      """Human-readable description of a preset, carried through the JSON format."""
  class EffectInstance:
      """One configured effect in a pipeline, with its parameters and enabled flag."""
  class PaletteSpec:
      """Description of the palette a pipeline renders with."""
  class PipelineSpec:
      """Complete, serialisable description of one render."""
  def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
      """Return the float32 palette described by spec, extracting from img when needed."""
  def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
  def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
  def render_with_palette(src: Image, spec: PipelineSpec, palette: Palette,
# --- lattice_core/registry ---
  class AlgorithmInfo:
      """Registration record of one dithering algorithm."""
  class EffectInfo:
      """Registration record of one image effect."""
  def register_algorithm(
      def decorator(fn: AlgorithmFn) -> AlgorithmFn:
  def register_effect(
      def decorator(fn: EffectFn) -> EffectFn:
  def get_algorithm(id: str) -> AlgorithmInfo:
      """Return the algorithm registered under id, or raise KeyError."""
  def list_algorithms() -> list[AlgorithmInfo]:
      """Return every registered algorithm, sorted by family then name."""
  def get_effect(id: str) -> EffectInfo:
      """Return the effect registered under id, or raise KeyError."""
  def list_effects() -> list[EffectInfo]:
      """Return every registered effect, sorted by name."""
  def resolve_params(specs: tuple[ParamSpec, ...], given: dict) -> dict:
      """Fill defaults, clamp numbers to their bounds, cast ints and validate choices."""
# --- lattice_core/seed ---
  def module_seed(seed: int, module: int) -> int:
      """Return the deterministic per-module stream seed derived from the global seed."""
  class SeedController:
      """One global seed plus per-module streams, with optional per-module locks.
      def seed(self) -> int:
      """The global seed driving the whole render."""
      def module_seed_for(self, module: int) -> int:
      """Return the stream seed of one module, fixed when the module is locked."""
      def rng(self, module: int) -> np.random.Generator:
      """Return the deterministic random generator of one module."""
      def lock(self, module: int) -> None:
      """Freeze the current stream of module so a reroll does not change it."""
      def unlock(self, module: int) -> None:
      """Let module follow the global seed again on the next reroll."""
      def locked(self) -> frozenset[int]:
      """Return the set of module indices whose streams are frozen."""
      def reroll(self, seed: int | None = None) -> int:
      """Reroll the global seed; locked modules keep their prior streams."""
  def render_effects(img: Image, effects: list[str], controller: SeedController,
# --- lattice_core/mask ---
  class MaskRef:
      """Serialisable reference to one greyscale mask: a path or embedded base64 data.
      def from_mask(cls, mask: Image, ref_id: str, *, path: str | None = None) -> MaskRef:
      """Build a reference for mask, embedding when possible and requiring a path otherwise."""
      def from_path(cls, path: str | Path, ref_id: str) -> MaskRef:
      """Reference an existing PNG mask by path, decoding it once to read its dimensions."""
      def embedded(self) -> bool:
      """True when the mask is embedded as base64 data rather than referenced by path."""
      def to_dict(self) -> dict[str, str | int | None]:
      """Return the JSON dict of the reference; exactly one of path/data is present."""
      def from_dict(cls, item: dict) -> MaskRef:
      """Rebuild a reference from its JSON dict, rejecting an entry with both keys."""
  def to_png(mask: Image) -> bytes:
      """Encode a greyscale mask as 8-bit PNG bytes with exact rounding."""
  def from_png(data: bytes) -> Image:
      """Decode PNG bytes (8 or 16 bit, grey or alpha) to a float32 mask in [0, 1]."""
  def from_base64(text: str) -> Image:
      """Decode a base64 PNG payload back to a float32 greyscale mask."""
  def export_png(mask: Image, path: str | Path) -> Path:
      """Write a mask as an 8-bit greyscale PNG, creating parent directories."""
  def import_png(path: str | Path) -> Image:
      """Read a greyscale PNG mask from disk into [0, 1]."""
  def load_ref(ref: MaskRef | dict) -> Image:
      """Resolve a MaskRef (or its dict) into the greyscale mask it references."""
  def resolve_masks(section: dict[str, object] | None) -> dict[str, Image]:
      """Resolve the `masks` section of a v3 preset into its greyscale mask planes.
  def apply(source: Image, effect: Image, *, mask: Image) -> Image:
      """Compose a localised effect over source: 0 keeps source, 1 keeps the effect.
# --- lattice_core/preset ---
  class Preset:
      """A v3 preset: typed sections, preserved unknown keys and load warnings."""
  def to_json(preset: Preset) -> str:
      """Serialise preset as sorted, two-space-indented v3 JSON with one trailing newline."""
  def from_json(
  def save_preset(path: str | Path, preset: Preset) -> None:
      """Write preset as UTF-8 v3 JSON, creating parent directories."""
  def load_preset(
  def to_pipeline_spec(preset: Preset) -> PipelineSpec:
      """Return PipelineSpec carrying renderer/style and continuous-mode nulls (§5 S1)."""
  def from_pipeline_spec(spec: PipelineSpec) -> Preset:
      """Build a v3 preset from a PipelineSpec, keeping renderer and renderer_style."""
# --- lattice_core/ui/worker ---
  class RenderResult:
      """One finished full-resolution render: its job, the image and its duration."""
  class PreviewResult:
      """One finished preview stage: its job, the render, the source proxy and its duration."""
  def proxy_factor(image: Image, max_side: int) -> int:
      """Return the integer area-downscale factor that brings image under max_side."""
  def preview_proxy(image: Image, max_side: int = PREVIEW_MAX_SIDE) -> RGB8:
      """Return the uint8 proxy of image, shaped like the preview render at max_side."""
  def oversize_message(shape: tuple[int, ...]) -> str | None:
      """Return the refusal message for a source of this (height, width), or None."""
  class RenderWorker(QObject):
      """Renders debounced, staged previews and full-resolution exports of one source."""
      def start(self) -> None:
      """Create the debounce timer inside whatever thread owns this worker."""
      def set_source(self, image: Image | None) -> None:
      """Adopt image as the pipeline source, refusing sources above MAX_SOURCE_SIDE."""
      def source(self) -> Image | None:
      """Return the adopted source image, or None when none is loaded."""
      def request_preview(self, spec: PipelineSpec) -> None:
      """Store spec and restart the debounce timer; only the last spec is rendered."""
      def request_export(self, spec: PipelineSpec) -> None:
      """Render spec at full resolution and emit the result for saving."""
# --- lattice_core/ui/export_dialog ---
  class ExportError(Exception):
      """An export that could not be written: no output path, or a render failure."""
  class ExportDialog(QDialog):
      """Dialog that renders the pipeline at full resolution and writes it as PNG, SVG or GIF."""
      def format(self) -> str:
      """Return the selected format key: png, svg or gif."""
      def export_directory(self) -> Path:
      """Return the remembered export directory, or the home directory."""
      def target_path(self) -> Path:
      """Return the output path typed in the dialog, with the format's suffix."""
      def background(self) -> str | None:
      """Return the SVG background colour, or None when the field is empty."""
      def export_now(self) -> list[Path]:
      """Render at full resolution, write the file and return the paths written."""
  def run_export_dialog(
# --- lattice_core/ui/canvas ---
  class PreviewCanvas(QGraphicsView):
      """Zoomable, pannable preview of the rendered image with a split view."""
      def set_image(self, rgb8: RGB8) -> None:
      """Set the rendered (after) image and refresh the display."""
      def set_original(self, rgb8: RGB8 | None) -> None:
      """Set the source (before) image, or None to clear it."""
      def set_mode(self, mode: Mode) -> None:
      """Switch the preview between the after, before and split views."""
      def mode(self) -> Mode:
      """Return the active preview mode."""
      def qimage(self) -> QImage | None:
      """Return the QImage buffer the canvas displays, or None when it is empty."""
      def zoom(self) -> float:
      """Return the current zoom factor (1.0 is one image pixel per screen pixel)."""
      def set_zoom(self, f: float) -> None:
      """Set the zoom factor, clamped to the supported range."""
      def zoom_fit(self) -> None:
      """Scale the image so that it fits entirely inside the viewport."""
      def wheelEvent(self, event: QWheelEvent) -> None:
      """Zoom around the cursor with the mouse wheel."""
      def zoom_around(self, position: QPointF, f: float) -> None:
      """Set the zoom factor while keeping the scene point under position fixed."""
      def mousePressEvent(self, event: QMouseEvent) -> None:
      """Start panning on a left or middle button press."""
      def mouseMoveEvent(self, event: QMouseEvent) -> None:
      """Scroll the view while a pan drag is active."""
      def mouseReleaseEvent(self, event: QMouseEvent) -> None:
      """Finish panning when the drag button is released."""
      def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
      """Draw the divider line of the split view."""
# --- lattice_core/ui/glyph_browser ---
  class GlyphRamp:
      """One named ramp of the catalogue, darkest glyph first."""
  class GlyphCategory:
      """One catalogue category: its documented ladder and the ramps cut from it."""
  class Catalogue:
      """The whole ramps catalogue, in display order, with its ids indexed once."""
      def ramps(self) -> tuple[GlyphRamp, ...]:
      """Return every ramp of the catalogue, category by category."""
      def ramp_index(self) -> dict[str, GlyphRamp]:
      """Return every ramp indexed by id, built on first lookup and then reused."""
      def category_index(self) -> dict[str, GlyphCategory]:
      """Return every category indexed by id, built on first lookup and then reused."""
      def get(self, ramp_id: str) -> GlyphRamp:
      """Return the ramp registered under ramp_id, or raise KeyError naming it."""
      def category(self, category_id: str) -> GlyphCategory:
      """Return the category registered under category_id, or raise KeyError naming it."""
  def validate_catalogue(data: object) -> Catalogue:
      """Validate a ramps document into typed objects; ramps must be ordered subsequences."""
  def load_catalogue(path: Path | str | None = None) -> Catalogue:
      """Return the shipped catalogue, or the one at path, validated once per path."""
  def render_ramp_preview(
  class GlyphBrowser(QWidget):
      """Category list, set list and a live preview of every ramp in the current font."""
      def catalogue(self) -> Catalogue:
      """Return the catalogue this browser displays."""
      def current_ramp(self) -> GlyphRamp | None:
      """Return the ramp currently previewed, or None before the first selection."""
      def preview_rgb8(self) -> RGB8 | None:
      """Return the pixels of the current preview, or None before the first selection."""
      def select_ramp(self, ramp_id: str) -> None:
      """Show ramp_id by moving both lists silently, then repainting and announcing once.
      def set_font(self, font: str | None) -> None:
      """Preview every ramp in font, or in the bundled font when font is None."""
# --- lattice_core/bridge/__init__ ---
      def ping(self) -> bool: ...
      def call(self, method: str, params: dict | None = None) -> object: ...
      def render_document(self) -> Image.Image: ...
      def place_as_layer(self, img: Image.Image, name: str) -> int: ...
      def disconnect(self) -> None: ...
  class ArtCraftClient:
      """One ArtCraft host, reached through the adapter that speaks to it."""
      def host(self) -> HostName:
      """Return the host name this client talks to."""
      def client(self) -> _Adapter:
      """Return the host adapter underneath, for host-specific calls."""
      def discover(host: HostName, port: int | None = None) -> ArtCraftClient | None:
      """Return a live client for `host`, or None when that host is not reachable."""
      def ping(self) -> bool:
      """Return True when the host answers its liveness probe."""
      def render_document(self) -> Image.Image:
      """Return the active document of the host as an image."""
      def place_as_layer(self, img: Image.Image, name: str = DEFAULT_LAYER_NAME) -> int:
      """Place the image in the host as a layer or placed object and return its id."""
      def call(self, method: str, params: dict | None = None) -> object:
      """Send one raw request to the host and return its result."""
      def disconnect(self) -> None:
      """Drop whatever the adapter holds; connections are per call."""
# --- lattice_glyph/cli ---
  class UsageError(Exception):
      """A command line the application cannot honour: a missing or unreadable preset."""
      def error(self, message: str) -> NoReturn:
      """Print the usage line and exit with the §8 usage code.
  def host_report(hosts: tuple[str, ...] | list[str]) -> list[dict]:
      """Probe every host and return one {host, connected} record per host."""
  def main(argv: list[str] | None = None) -> int:
      """Run the command line and return its exit code; no traceback ever escapes."""
# --- lattice_glyph/app ---
  def dark_palette() -> QPalette:
      """Return the dark palette applied on top of the Fusion style."""
  def create_application(argv: list[str] | None = None) -> QApplication:
      """Return the QApplication, creating it with the Fusion dark theme when needed."""
  def main(argv: list[str] | None = None) -> int:
      """Start the Lattice Glyph GUI and return the Qt exit code."""
# lattice_glyph/ui/panels: (fichier absent)

TASK CARD
### L20 · Lattice Glitch application shell
- wave: 2 · deps: L13, L14, L15, L16, L17, L18, L19 · executor: OMH deep-work · review: full · size: L
- owns: `lattice_glitch/**`, `tests/test_glitch_app.py`
- context: §1 §2 §7 §8 §12 §13 §14 §15 §16 §17 §18
- spec: the `lattice-glitch` distribution. PySide6 window with an effect stack, a live preview, a
  seed control with reroll and per-module lock, a mask painter, a preset browser, and the four CLI
  verbs of §8. Bridge to PhotoCraft and DesignCraft. Works standalone.
- accept:
  - the app launches, opens an image, stacks two effects, reorders them, and saves.
  - the CLI `render` and the GUI produce identical bytes for the same preset (G9).
  - reroll changes the output; locking a module keeps that module's contribution.
  - the mask painter produces a mask that the renderer honours.
  - the app runs with `lattice-core` without the `[ui]` extra only for the CLI path.


CURRENT CONTENT OF YOUR FILES (state on disk — integrate, never replace)
# lattice_glitch/**: (à créer — n'existe pas encore sur disque)

# tests/test_glitch_app.py: (à créer — n'existe pas encore sur disque)

RETRY attempt 2. Fix exactly what is reported below, change nothing else, keep passing tests passing.
Rejoue TES gates (ruff + pytest sur tes owns) TOI-MÊME et donne les chiffres réels. Ne touche JAMAIS à un fichier hors owns.
Interdictions inchangées : ni commit/push, ni harness/**, ni probes à la racine du dépôt ; ne lance JAMAIS la batterie complète
(des cartes voisines écrivent en parallèle — les échecs venant d'elles ne te concernent pas).

VERDICT DU RE LECTEUR (JSON verbatim) :
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "blocker",
      "file": "lattice_glitch/export_actions.py",
      "line": 54,
      "what": "Le rappel render_full donné à ExportDialog lève DocumentError, que ExportDialog._on_export n'attrape pas (il ne catche que ExportError, OSError, ValueError) : l'exception s'échappe dans un slot Qt — traceback, et abort (qFatal) avec PySide6 ≥ 6.5.2.",
      "why": "Chemin de crash accessible : assigner un masque à un effet, supprimer le masque (delete_active laisse mask_id pendant), puis Exporter → DocumentError « mask is not in the document » non catchée. Perte du travail non sauvegardé.",
      "fix": "Dans render_full, convertir DocumentError en ExportError ; purger les mask_id des slots à la suppression d'un masque ; test : masque supprimé → export via dialogue → rapport, aucune exception."
    },
    {
      "severity": "major",
      "file": "lattice_glitch/pyproject.toml",
      "line": 0,
      "what": "La distribution lattice-glitch n'existe pas : aucun pyproject.toml, alors que le spec est « the lattice-glitch distribution » (L12 livre lattice_glyph/pyproject.toml).",
      "why": "§2 exige quatre distributions ; sans métadonnées pas d'installation pip, pas de scripts, presets hors wheel, L23 bloqué.",
      "fix": "Ajouter lattice_glitch/pyproject.toml calqué sur lattice_glyph/pyproject.toml : name lattice-glitch, version 0.1.0, license MIT OR Apache-2.0, dependencies lattice-core>=0.1,<0.2 + numpy/numba/Pillow, extra ui = lattice-core[ui], scripts lattice-glitch = lattice_glitch.__main__:main et lattice-glitch-cli = lattice_glitch.cli:main, package-data presets/*.json."
    },
    {
      "severity": "major",
      "file": "lattice_glitch/effects_panel.py",
      "line": 180,
      "what": "§16 non honoré : le formulaire expose les 14 paramètres de ntsc sans mode simple ni bascule avancé, les six presets nommés nulle part.",
      "why": "lattice_core/effects/ntsc.py expose params_for_mode('simple'|'advanced'), SIMPLE_PARAMS (4), MODES et PRESETS (6 noms) ; le shell est le seul endroit où le mode simple existe ; les labels du catalogue sont trompeurs.",
      "fix": "Pour ntsc, formulaire depuis params_for_mode avec bascule simple/avancé (simple par défaut, 4 sliders) + sélecteur des six PRESETS ; tooltips honnêtes via LABEL_NOTES ; test : le mode simple expose exactement 4 éditeurs."
    },
    {
      "severity": "major",
      "file": "lattice_glitch/presets.py",
      "line": 115,
      "what": "G9 casse dès qu'un module est verrouillé : to_preset ne sérialise que la seed globale ; les streams verrouillés (session-only) ne voyagent pas → CLI et GUI octets différents pour le même preset sauvegardé.",
      "why": "Verrou + reroll → stream 0 figé en mémoire ; l'export GUI utilise le stream figé, le CLI reconstruit SeedController(seed).rng(0) → octets différents. §8 exige l'identité octet à octet ; §18 promet un accident reproductible.",
      "fix": "Sérialiser le stream de chaque slot verrouillé dans son entrée d'effet (p. ex. « seed »: controller.module_seed_for(i)) et le relire vers RenderContext.streams ; test verrou → reroll → sauvegarde → parité CLI/GUI."
    },
    {
      "severity": "major",
      "file": "lattice_glitch/window.py",
      "line": 215,
      "what": "render_context() promet un snapshot immuable mais ne copie que le dict des masques : les plans numpy restent partagés, mutés en place pendant que le thread de rendu les lit.",
      "why": "Course de données réelle pendant un push bridge ou un preview pendant la peinture → calque poussé avec masque incohérent.",
      "fix": "Copier les plans : masks={k: v.copy() for k, v in self.mask_panel.planes().items()}."
    },
    {
      "severity": "major",
      "file": "lattice_glitch/window_bridge.py",
      "line": 46,
      "what": "check_bridge() n'est appelé par rien : BridgeStatusDot reste « unknown » toute la session.",
      "why": "Statut trompeur (E7), contraire au « nothing is half-wired » de actions.py.",
      "fix": "Prober au démarrage et après chaque pull/push (ou QTimer périodique) ; test : après check_bridge, l'état quitte « unknown »."
    },
    {
      "severity": "minor",
      "file": "tests/test_glitch_app.py",
      "line": 301,
      "what": "Assertions quasi tautologiques : export.size == stat().st_size ; post_effects[-1].effect_id == effect_id.",
      "why": "Ne prouvent presque rien ; la valeur vient des assertions voisines.",
      "fix": "Remplacer par des assertions discriminantes (octets PNG relus == png_bytes(render_preset), ordre du stack après move)."
    },
    {
      "severity": "minor",
      "file": "tests/test_glitch_app.py",
      "line": 235,
      "what": "Le test de verrou désactive le module 1 : le cas « verrouillé inchangé ET déverrouillé changé » (les deux actifs) jamais asserté.",
      "why": "Un bug qui figerait tout le rendu après verrou passerait le test.",
      "fix": "Garder les deux effets actifs, verrouiller 0, reroll, assert module 0 identique et module 1 différent."
    },
    {
      "severity": "minor",
      "file": "lattice_glitch/actions.py",
      "line": 90,
      "what": "Paramètres non typés : dropped_images(mime), handle_drag_enter/handle_drop(event), window._on_preview(result), MaskPainter.paintEvent(event).",
      "why": "Hygiène : le reste du paquet est typé.",
      "fix": "Typer QMimeData, QDragEnterEvent, QDropEvent, PreviewResult, QPaintEvent."
    }
  ],
  "regression": "none — paquet neuf ; le chemin glitch assume sa propre seeding §18 (streams par module)",
  "renderer_invariants": "mode continu appliqué et vérifié ; masque 0=source/1=effet vérifié pixel à pixel ; pas de mutation de l'entrée",
  "tests_that_cannot_fail": [
    "test_presets_document_stack_and_masks (export.size == stat().st_size)",
    "test_cli_and_gui_write_identical_bytes (post_effects[-1].effect_id == effect_id)"
  ],
  "notes": "G9 prouvé avec du NON trivial (8 presets, stack édité, masque peint) ; CLI sans Qt prouvé par sous-processus bloqueur ; les 7 tests couvrent les 5 accepts. FIX pour : crash dialogue export, distribution absente, §16 sans mode simple, G9 en session verrouillée, plans de masque partagés, bridge jamais probé."
}

DISPOSITION ORCHESTRATEUR (réponds finding par finding, dans l'ordre du JSON) :
1. [BLOCKER — DocumentError non catchée dans le slot export] ACCEPTE : dans render_full, convertir DocumentError en ExportError ;
   purger les mask_id orphelins à la suppression d'un masque ; test : masque supprimé → export → rapport, pas d'exception.
2. [major — distribution absente] ACCEPTE : la consigne « ne touche pas pyproject.toml » visait le pyproject RACINE du dépôt.
   Un NOUVEAU fichier lattice_glitch/pyproject.toml EST dans tes owns (lattice_glitch/**) : crée-le calqué sur
   lattice_glyph/pyproject.toml (name lattice-glitch, version 0.1.0, licence MIT OR Apache-2.0, dependencies
   lattice-core>=0.1,<0.2 + numpy/numba/Pillow, extra ui = lattice-core[ui], scripts lattice-glitch/_cli, package-data presets/*.json).
   Ne touche PAS au pyproject racine ni à ceux des autres paquets.
3. [major — §16 ntsc sans mode simple] ACCEPTE : formulaire ntsc depuis params_for_mode avec bascule simple/avancé (simple par
   défaut = exactement 4 sliders) + sélecteur des six PRESETS nommés ; tooltips via LABEL_NOTES ; test du compte d'éditeurs.
4. [major — G9 cassé en session verrouillée] ACCEPTE la sérialisation : chaque slot verrouillé écrit son stream
   (module_seed_for(i)) dans son entrée d'effet, relu au chargement vers RenderContext.streams. Enregistre la nuance en E1 :
   le core §18 reste verrouillé session-only (DEV-216) ; c'est le FORMAT DE PRESET du shell Glitch qui étend la sérialisation
   pour tenir G9 — pas un changement du contrat core. Test : verrou → reroll → sauvegarde → parité CLI/GUI.
5. [major — plans de masque partagés] ACCEPTE : copie les plans dans render_context (v.copy()) ; le snapshot devient réellement immuable.
6. [major — statut bridge mort] ACCEPTE : prober au démarrage et après chaque pull/push (ou QTimer) ; test : l'état quitte « unknown ».
7-9. [minors] ACCEPTE tous : assertions discriminantes (octets PNG relus, ordre du stack), test de verrou avec les DEUX effets
   actifs (module 0 identique, module 1 différent après reroll), types des paramètres (QMimeData, QDragEnterEvent, QDropEvent,
   PreviewResult, QPaintEvent).
Rappels : 21 modules ≤ 400 l, fonctions ≤ 60 l ; ne touche ni lattice_core ni lattice_glyph ; aucun import d'une autre app ;
hôte absent = état normal (E9).