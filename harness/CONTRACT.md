# DitherCraft technical contract

Version: **1.2.0-draft** (becomes 1.2.0 when frozen at checkpoint H1, after T01). 1.1: §8 rewritten for the desktop control server (DEV-001). 1.2: §8.6 version check and smoke test (DEV-002).
Any change after freeze goes through `DEVIATIONS.md`. Sections are referenced as §N in task cards.
Versioning: PATCH = clarification, no code impact. MINOR = additive, backward compatible.
MAJOR = breaking; forbidden after wave 1 starts without human approval.

## §1 Environment

- Windows 11. Project root: `C:\Users\marin\DitherCraft`. Virtual env: `.venv` at root.
- Interpreter version decided by T00 and recorded in `STATE.md` (system Python is 3.15.2; fallback 3.13).
- Dependencies, pinned by T00 in `requirements.txt`: numpy, numba, Pillow, PySide6, pytest, ruff.
  **No other dependency** (no scipy, no opencv, no scikit-learn). Adding one is a deviation E5.
- All text IO uses `encoding="utf-8"` explicitly. Code, identifiers, comments, UI strings: English.
- Git repository at root. One commit per task that passes review: `T<id>: <title>`.

## §2 File tree (fixed; T01 creates every file, as stub when owned by a later task)

```
DitherCraft/
  pyproject.toml                 T01  (ruff: line-length 100; pytest markers: perf, manual)
  requirements.txt               T00
  DitherCraft.pyw                T15
  dithercraft/
    __init__.py                  T01  (__version__ = "0.1.0")
    __main__.py                  T01  (calls dithercraft.ui.app.main)
    core/types.py                T01  §3
    core/registry.py             T01  §4
    core/color.py                T01  §5
    core/pipeline.py             T09  §7
    core/presets.py              T09  §7
    algorithms/__init__.py       T01  (imports the 4 modules below; never edited later)
    algorithms/error_diffusion.py T02
    algorithms/ordered.py        T03
    algorithms/misc.py           T04
    algorithms/halftone.py       T04
    palettes/builtin.py          T05
    palettes/io.py               T05
    palettes/extract.py          T06
    effects/__init__.py          T01  (imports tone, glitch; never edited later)
    effects/tone.py              T07A
    effects/glitch.py            T07B
    bridge/photocraft.py         T08  §8
    ui/app.py                    T10
    ui/main_window.py            T10 (shell), T14 (wiring)
    ui/canvas.py                 T10
    ui/param_form.py             T10
    ui/algorithm_panel.py        T11
    ui/effects_panel.py          T12
    ui/palette_panel.py          T13
    ui/worker.py                 T14
  data/blue_noise_64.npy         T03 (generated, committed)
  tools/check_contract.py        T01  §11
  tools/smoke_photocraft.py      T08  §8.6
  tools/gen_blue_noise.py        T03
  tools/make_icon.py             T15
  scripts/install_shortcuts.ps1  T15
  tests/conftest.py              T01
  tests/test_<module>.py         owner of <module>
  tests/manual/                  T16 (never run by gates)
```

Every `__init__.py` of a sub-package not listed is empty and created by T01.

## §3 Types (`core/types.py`)

```python
Image = np.ndarray    # float32, shape (H, W, 3), values in [0, 1], sRGB-encoded, C-contiguous
Indices = np.ndarray  # int32, shape (H, W), values in [0, K)
Palette = np.ndarray  # float32, shape (K, 3), 2 <= K <= 256, values in [0, 1]
RGB8 = np.ndarray     # uint8, shape (H, W, 3)

@dataclass(frozen=True)
class ParamSpec:
    id: str                                   # snake_case, unique within its owner
    label: str                                # UI label, English
    kind: Literal["float", "int", "bool", "choice"]
    default: float | int | bool | str
    min: float | None = None                  # required for float/int
    max: float | None = None                  # required for float/int
    step: float | None = None
    choices: tuple[str, ...] = ()             # required for choice
```

Rules: alpha is never processed (loaders composite over white). Functions never mutate their inputs.
No global mutable state except the two registries.

## §4 Registry (`core/registry.py`)

```python
AlgorithmFn = Callable[[Image, Palette, dict], Indices]
EffectFn = Callable[[Image, dict, np.random.Generator], Image]

@dataclass(frozen=True)
class AlgorithmInfo:
    id: str; name: str
    family: Literal["error_diffusion", "ordered", "halftone", "other"]
    params: tuple[ParamSpec, ...]; fn: AlgorithmFn

@dataclass(frozen=True)
class EffectInfo:
    id: str; name: str; params: tuple[ParamSpec, ...]; fn: EffectFn

def register_algorithm(id: str, name: str, family: str, params: tuple[ParamSpec, ...] = ()): ...  # decorator
def register_effect(id: str, name: str, params: tuple[ParamSpec, ...] = ()): ...                  # decorator
def get_algorithm(id: str) -> AlgorithmInfo        # KeyError if unknown
def list_algorithms() -> list[AlgorithmInfo]       # sorted by family, then name
def get_effect(id: str) -> EffectInfo
def list_effects() -> list[EffectInfo]             # sorted by name
def resolve_params(specs: tuple[ParamSpec, ...], given: dict) -> dict
    # fills defaults, clamps numbers to [min, max], casts int, ValueError on unknown key or bad choice
```

Duplicate id registration raises `ValueError`.

**Algorithm contract.** Input image is already adjusted and downscaled by the pipeline; params are
already resolved. Output: `Indices` with the input's H, W. Never returns colors. Randomized algorithms
take a `seed: int` param (default 0) and are deterministic. Performance target: 1024x1024, K=16,
< 0.5 s after JIT warm-up (test marked `perf`, informative, not a gate).

**Effect contract.** Returns a new `Image` of the same shape, float32, clipped to [0, 1].
Deterministic for a given `rng`. Never raises on valid input of any size >= 1x1.

## §5 Color utilities (`core/color.py`, T01)

```python
def to_float(img: PIL.Image.Image) -> Image          # any mode → RGB float; RGBA/LA/P composited over white
def to_rgb8(img: Image) -> RGB8                      # round half up, clip
def to_pil(rgb8: RGB8) -> PIL.Image.Image
def luminance(img: Image) -> np.ndarray              # (H, W) float32, 0.2126R + 0.7152G + 0.0722B on sRGB values
def nearest_index(img: Image, palette: Palette) -> Indices   # squared euclidean RGB, vectorized, chunked ≤ 256 MB
def apply_palette(idx: Indices, palette: Palette) -> Image
def adjust(img: Image, brightness: float, contrast: float, gamma: float) -> Image
    # brightness, contrast in [-1, 1]; gamma in [0.1, 5]; order: gamma, contrast around 0.5, brightness add; clip
def downscale(img: Image, factor: int) -> Image      # area average; pads edge by replication when not divisible
def upscale_nearest(img: Image, factor: int, shape: tuple[int, int]) -> Image  # repeat then crop to shape
@njit(cache=True)
def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray) -> int  # for numba kernels
```

Only `color.py`, `error_diffusion.py` and `misc.py` (Riemersma) may import numba. UI code never does.

## §6 Palettes

- `palettes/builtin.py`: `BUILTIN: dict[str, Palette]`, `def get_builtin(name) -> Palette`,
  `def builtin_names() -> list[str]`. Keys snake_case. Exact contents are given in task T05.
- `palettes/io.py`: `load_palette(path: Path) -> Palette`, `save_palette(path: Path, p: Palette, name: str = "DitherCraft")`.
  Format by extension. `.hex`: one `RRGGBB` per line, leading `#` optional, blank lines and lines
  starting with `;` ignored. `.gpl`: GIMP format (`GIMP Palette`, `Name:`, optional `Columns:`, `#` comments,
  `R G B<tab>name`). Also `hex_list(p) -> list[str]` and `from_hex_list(list[str]) -> Palette` (`"#RRGGBB"` uppercase).
  Errors: `ValueError` with line number.
- `palettes/extract.py`: `extract_palette(img: Image, k: int, method: Literal["kmeans", "median_cut"], seed: int = 0) -> Palette`.
  k in [2, 32]. Result sorted by luminance ascending. If the image has fewer unique colors than k,
  return those colors; if only one, append black or white (whichever is farther).
  kmeans: numpy only, subsample ≤ 65536 pixels with `default_rng(seed)`, k-means++ init, ≤ 30 iterations.

## §7 Pipeline (`core/pipeline.py`, `core/presets.py`, T09)

```python
@dataclass
class EffectInstance:
    effect_id: str
    params: dict = field(default_factory=dict)
    enabled: bool = True

@dataclass
class PaletteSpec:
    source: Literal["builtin", "extracted", "custom"] = "builtin"
    name: str = "bw"                      # builtin key when source == "builtin"
    colors: list[str] = field(default_factory=list)   # "#RRGGBB", when source == "custom"
    extract_k: int = 8
    extract_method: str = "kmeans"

@dataclass
class PipelineSpec:
    version: int = 1
    pre_effects: list[EffectInstance] = field(default_factory=list)
    brightness: float = 0.0
    contrast: float = 0.0
    gamma: float = 1.0
    pixel_size: int = 1                    # 1..32
    algorithm_id: str = "floyd_steinberg"
    algorithm_params: dict = field(default_factory=dict)
    palette: PaletteSpec = field(default_factory=PaletteSpec)
    post_effects: list[EffectInstance] = field(default_factory=list)
    seed: int = 0

def resolve_palette(spec: PaletteSpec, img: Image) -> Palette
def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8
```

Normative render order:
1. If `max_side`: area-downscale `src` so that max(H, W) <= max_side (preview proxy). Call this shape S.
2. Enabled pre-effects in order; effect i gets `np.random.default_rng(spec.seed + i)`.
3. `adjust(brightness, contrast, gamma)`.
4. `downscale(pixel_size)`.
5. `resolve_palette` on the image from step 4.
6. Algorithm (params through `resolve_params`) → indices → `apply_palette`.
7. `upscale_nearest` back to S.
8. Enabled post-effects in order; effect j gets `default_rng(spec.seed + 1000 + j)`.
9. `to_rgb8`. Output shape = S.

`presets.py`: `to_json(spec) -> str` (indent 2, keys = field names), `from_json(text) -> PipelineSpec`
(validates algorithm and effect ids against the registry, `ValueError` naming the bad id; unknown
top-level keys ignored; missing keys take defaults), `save_preset(path, spec)`, `load_preset(path)`.

## §8 PhotoCraft bridge (`bridge/photocraft.py`, T08)

Target: the **desktop app** control server (not `photocraft-cli serve`, whose method set differs).
Status tags: [V] verified by T00 on a separate desktop instance; [V user instance] verified by P00 on the
user's own instance (2026-11-10, PhotoCraft 0.22.0, started from the shortcut described in §8.2).

### §8.1 Transport [V, V user instance]
- The control server listens on **fixed port 47600** (`--control 47600`; same value as
  `integrations.controlPort` in preferences.json). The token is the content of
  `%LOCALAPPDATA%\DitherCraft\control.token` (64 hex digits, strip whitespace). [V user instance]
- `%APPDATA%\Photocraft\instance.json` (`{"pid","port","token"}`) is the app's single-instance IPC, NOT the
  control server: its port answers `{"ok":false,"error":"not taken"}` to every request and its token is refused
  on 47600. **Never use it.** [V user instance]
- TCP `127.0.0.1:47600`, one JSON object per line, UTF-8. Request `{"id", "method", "params"}`,
  response `{"id", "ok", "result" | "error"}`.
- First request on EACH connection: `{"id":0,"method":"auth","params":{"token":"<64 hex>"}}` →
  `{"ok":true,"result":{"authenticated":true}}`. Without it: error `"authentication required"`.
  Wrong token: the server answers `{"ok":false,"error":"authentication required"}` and then closes the
  connection (map to BridgeError "authentication failed"). [V user instance]
- Desktop methods: `engine.execute {"command": "<id>", "params": {...}}` (params optional), `engine.commands`
  (list of 1005 entries `{id, label, params (doc string), enabled, disabledReason, ...}`),
  `app.open {"path"}`, `app.save {"path"}`, `ui.inspect`, `jobs.list`, `jobs.cancel`. **Not available**:
  `methods`, `doc.*`, `session.list`, `batch`. Never call `app.quit`.
- Document list: `ui.inspect` → `result.session` = `{"active": index, "documents": [{"index","name","path",
  "dirty","revision","width","height"}, ...]}`. `document.inspect` has no `dirty` flag; use this one.
  [V user instance]

### §8.2 File access [V, V user instance]
- Automation roots are set only at app start. Env vars `PHOTOCRAFT_AUTOMATION_READ_ROOT`,
  `PHOTOCRAFT_AUTOMATION_WRITE_ROOT` and `PHOTOCRAFT_CONTROL_TOKEN_FILE` were not honoured or were not
  verified: **not relied upon**. The mechanism is launch flags, via the Desktop shortcut
  "PhotoCraft (DitherCraft)":
  `photocraft.exe --control 47600 --control-token-file "%LOCALAPPDATA%\DitherCraft\control.token"
  --automation-read-root <EXCHANGE_DIR> --automation-write-root <EXCHANGE_DIR>`.
  Both roots must equal `EXCHANGE_DIR`; both directions are required (read for `app.open`, write for `app.save`).
- Paths sent to the app are **relative to the root**, with `/` separators (backslashes are refused).
- [V user instance] On an instance started with these flags, `app.open {"path":"x.png"}` and
  `app.save {"path":"y.png"}` (relative names inside the root) work; `app.open` returns
  `{"name","path","warnings"}` and the opened document's `path` is the relative name.

### §8.3 Get the visible image [V, V user instance]
1. `engine.execute {"command":"document.inspect"}` → if no document, BridgeError("no document open").
2. `app.save {"path":"get_<uuid>.png"}` saves a flattened PNG of the active document into the root.
   It overwrites silently and returns warnings such as "N layer(s) flattened; layers, masks and blend modes
   are not kept".
3. Read the PNG from `EXCHANGE_DIR`, delete it, return a `PIL.Image` (RGB, or RGBA when the document has
   transparency; `to_float` composites).
- [V user instance] On a 3-layer document (one layer hidden, document dirty), `app.save` leaves the document
  unchanged: same layers and ids, same name, same `path` (it does NOT become the saved file), same
  `revision`, same history, `dirty` flag unchanged (true before and after). The PNG is pixel-identical to the
  expected flattened render; hidden layers are excluded. The save does not clear `dirty`.

### §8.4 Send as a new layer [V, V user instance]
1. `engine.execute {"command":"document.activate","params":{"offset":0}}` → `{"document": T}` (target index).
2. Write the PNG to `EXCHANGE_DIR/send_<uuid>.png`; `app.open {"path":"send_<uuid>.png"}` → opens a helper
   document that becomes active. Its index H is appended at the end (`H = number of documents - 1`, also when T
   is not the last document); T and every other index stay valid. Find H by name in `ui.inspect`
   `session.documents`.
3. `engine.execute {"command":"layer.copyToDocument","params":{"document":T,"center":true,"name":<layer_name>}}`
   → `{"document":T,"layers":[<new id>],"offset":[dx,dy]}`. Side effect: T becomes the active document again.
4. `engine.execute {"command":"file.close","params":{"document":H,"save":"discard"}}` closes exactly the
   helper and leaves T active; no reactivation needed. (Variant also verified: `document.activate {"document":H}`,
   `file.close {"save":"discard"}` with no `document` closes the ACTIVE document, then `document.activate
   {"document":T}`. Never call `file.close` without `document` while T is active.) Delete the PNG.
5. `engine.execute {"command":"document.inspect"}` → return `activeLayer` id.
- The copied layer is already a Pixel layer: do not rasterize. It is named by the `name` of step 3 (the
  `layer.renameLayer {"name": ...}` fallback was not needed), lands directly above the layer that was active
  in T, and becomes T's active layer. Layer ids are not consecutive (10, 14, 20, 24 observed): read the id,
  never predict it. [V user instance]
- [V user instance] Sequence run 4 times on a test target (T = 1, once with another document after T): identical
  results each time. The user's own document was never the target.

### §8.5 Python API
```python
EXCHANGE_DIR = Path(os.environ["LOCALAPPDATA"]) / "DitherCraft" / "exchange"   # = both automation roots
TOKEN_PATH = Path(os.environ["LOCALAPPDATA"]) / "DitherCraft" / "control.token"
CONTROL_PORT = 47600

class BridgeError(Exception): ...

class PhotoCraftClient:
    def __init__(self, port: int, token: str, timeout: float = 10.0): ...
    @staticmethod
    def discover(token_path: Path | None = None, port: int = CONTROL_PORT) -> "PhotoCraftClient | None"
        # reads the token file (strip), connects to 127.0.0.1:port, authenticates;
        # None if the file is missing or empty, the port is closed, or auth fails. instance.json is never read.
    def ping(self) -> bool                                  # auth + engine.commands
    def render_document(self) -> PIL.Image.Image            # §8.3; BridgeError on any error
    def place_as_layer(self, img: PIL.Image.Image, layer_name: str = "DitherCraft") -> int   # §8.4
```
- The app's roots cannot be read from outside, so there is no `roots_configured()`: a missing or wrong root
  surfaces as an error of `app.open`/`app.save` (message not observed), mapped to BridgeError.
- One TCP connection per public call (auth first), guarded by a `threading.Lock`.
- Files in `EXCHANGE_DIR` older than 1 hour are deleted at each call. Never write elsewhere
  (`control.token` lives outside `EXCHANGE_DIR` and is only read).
- Any partial failure in §8.4 after step 2 must still try to close the helper document (`file.close
  {"document":H,"save":"discard"}`), then raise BridgeError.
- Tests use an in-process fake desktop server (socket thread, auth + canned responses). No automated test
  touches the real app.

### §8.6 Version compatibility and smoke test (DEV-002)
```python
TESTED_PHOTOCRAFT_VERSION = "0.22.0"
PHOTOCRAFT_CLI = Path(r"C:\Program Files\ArtCraft\PhotoCraft\photocraft-cli.exe")

def installed_photocraft_version(cli: Path = PHOTOCRAFT_CLI) -> str | None
    # runs `<cli> --version` (timeout 10 s, no window: CREATE_NO_WINDOW), parses "photocraft-cli X.Y.Z (...)"
    # → "X.Y.Z"; None if the file is missing, the call fails or the output does not parse. Never raises.
def version_status() -> Literal["tested", "untested", "unknown"]
    # "tested" if installed == TESTED_PHOTOCRAFT_VERSION, "unknown" if None, else "untested"
```
- Assumption [not verified]: the CLI and the desktop app installed side by side share the same version.
- `tools/smoke_photocraft.py` (manual tool, never run by gates): requires the app launched from the
  "PhotoCraft (DitherCraft)" shortcut. Steps: discover → print installed version and version_status →
  create a 64x48 test PNG in EXCHANGE_DIR → `app.open` it (test document, index H) → `render_document` on it
  → `place_as_layer` of an inverted copy onto it → `document.inspect` checks one new Pixel layer named
  "DitherCraft smoke" → `file.close {"document":H,"save":"discard"}` → verify the user's document count and
  active index are restored. Prints `OK` or `FAIL at step <n>: <message>`; exit code 0/1. Closes its test
  document even on failure. Never touches documents it did not open.
- UI rule (T14): when version_status() is "untested", show a non-blocking status-bar warning
  "PhotoCraft <v> not tested with DitherCraft (tested: 0.22.0). Run tools/smoke_photocraft.py." once per launch.
  "unknown" shows nothing. Bridge errors keep their own messages.

## §9 UI (PySide6)

Layout: central `PreviewCanvas`; right dock with tabs Algorithm (T11), Palette (T13), Effects (T12).
Toolbar: Open image, Get from PhotoCraft, Send to PhotoCraft, Export PNG, Load preset, Save preset,
Before/After/Split, Zoom Fit / 100 / 200 / 400 %. Status bar: PhotoCraft connection state, render time.

Panel interface (all three panels implement it):
```python
class <Panel>(QWidget):
    changed = Signal()                       # emitted on any user edit, never during load_from
    def load_from(self, spec: PipelineSpec) -> None
    def apply_to(self, spec: PipelineSpec) -> None   # writes its fields into spec
```
`ParamForm(QWidget)`: `__init__(specs: tuple[ParamSpec, ...])`, `values() -> dict`,
`set_values(d: dict)`, `changed = Signal()`. float → slider + spinbox, int → spinbox, bool → checkbox,
choice → combobox.

`PreviewCanvas(QGraphicsView)`: `set_image(rgb8)`, `set_original(rgb8)`,
`set_mode(Literal["after", "before", "split"])`, `zoom_fit()`, `set_zoom(f: float)`. Nearest-neighbour
display (no smoothing). Wheel zooms around cursor; middle or left drag pans.

Threading: rendering runs in a worker (`QThread` + `QObject`), debounce 120 ms, latest-wins (stale
results dropped by job counter). Preview uses `max_side=1024`; Export and Send use full resolution.
**Never touch a widget outside the GUI thread.**

## §10 Code rules

- Type annotations on all public functions; 1 to 3 line docstring on each public function.
- File ≤ 400 lines, function ≤ 60 lines. No commented-out code. No `print` in library code (use `logging`).
- Edit only the files listed in your task's `owns`. Need anything else → declare a deviation, do not edit.
- No new dependency, no network access, no file writes outside the project, `EXCHANGE_DIR` and user-chosen paths.
- Tests: pytest, deterministic seeds, each test module < 5 s (excluding `perf` and `manual`).

## §11 Gates (run by the harness, in order)

- G1 `ruff check <owned .py files>`
- G2 `pytest <owned test files> -q -m "not perf and not manual"`
- G3 `python tools/check_contract.py`
- G4 `git status --porcelain` paths ⊆ task `owns`
- G5 Sonnet review (only if G1 to G4 pass)

`tools/check_contract.py` (T01) imports `dithercraft.algorithms` and `dithercraft.effects`, then for every
registered item: run with default params on seeded random images of shapes 37x23, 64x64, 1x5 and a
constant image; palettes K = 2 and K = 5. Algorithms: dtype int32, shape, range [0, K). Effects: shape,
float32, range [0, 1]. Also: ids snake_case and unique, defaults within [min, max], choices non-empty.
Exit code 0 on success; prints one line per failure. Registries may be empty (stubs) without failing.
