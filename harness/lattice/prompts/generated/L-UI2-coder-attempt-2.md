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


CONTRACT EXCERPTS (version 1.1 — Lattice Dither, toujours en vigueur)


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


REVUE-PRODUIT (extraits verbatim — les bloquants à traiter, cf. motivation de la carte)
- **Désormais 3 bloquants** (les deux premiers sont des défauts de résultat
  silencieux, confirmés par le code ; le troisième est venu des captures) :
  1) export avancé (SVG/impression/GIF/vidéo) sur l'aperçu plafonné à 1024 px
  au lieu d'un rendu pleine résolution — nuance visuelle : la barre n'expose
  que « Exporter en PNG » (le bon chemin) ; 2) « GIF animé »/« Vidéo »
  produisent un fichier d'une seule image dans la GUI ; 3) l'indicateur
  « Préréglage 1/12 : 01_gameboy.json » **ment dans les cinq états** (affiché
  sans image, sur un rendu Floyd-Steinberg N&B, et figé après changement
  d'algorithme et de palette) — c'est le piège le plus visible pour H12.
- **Aggravations visuelles** : la galerie occupe ~500 px de large (pas 240) —
  le canevas n'a que ~35 % de la fenêtre, vide au démarrage ; la barre
  d'outils déborde à 1280 px (« Préparer la source » et « Retirer la trame »
  hors champ : piège pour le scan) ; la galerie est figée (vignettes
  identiques, jamais sur l'image/palette courante, aucun surlignage de
  l'algorithme actif) ; le bouton « Ajouter ▾ » des effets est placé sous la
  liste « Après tramage » alors qu'il vise « Avant » — l'écran contredit le
  comportement ; les boutons PhotoCraft restent actifs malgré
  « PhotoCraft : déconnecté » ; zone « Couleurs » vide pour une palette EGA
  de 16 couleurs.
- **Corrections apportées par les captures** : le groupe « Extraire de
  l'image » est bien grisé quand la source est « Intégrée » (moins confus que
  le code ne le laissait croire) ; les pièges d'export restent établis par le
  code seul (non visibles sur les captures, le menu Fichier n'étant pas
  ouvert).
- **8 majeurs**, tous d'interface : état vide sans consigne, presets ◀/▶ à
  l'aveugle avec noms de fichiers techniques, barre de 19 actions plates,
  panneau Algorithme surchargé (la force noyée), galerie en doublon, bouton
  « Ajouter » d'effet visant la liste *avant* tramage, noms de palettes bruts
  (`cga_0_high`, `kmeans`), incohérence « Préréglage 1/12 » au démarrage.
- **Aucun constat ne touche le moteur** : 2-3 cartes d'ergonomie suffisent
  (priorités 1-9 du fichier visio-verdict.json — la n°1 est désormais
  l'indicateur de preset ; la passe visuelle exécute 10 tours, 0,71 $).


PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
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
# --- lattice_core/ui/looks ---
  class Look:
      """One named pipeline variant shown in the Looks grid."""
  def render_look_thumbnail(look: Look, source: Image, size: int = THUMB_SIZE) -> RGB8:
      """Render look on the source proxy and return a size×size thumbnail."""
  class LookThumbnailWorker(QObject):
      """Renders look thumbnails on a helper thread and reports them by signal."""
      def build(self, look_id: str, spec: PipelineSpec, source: Image) -> None:
      """Render one thumbnail and emit it; this slot never touches a widget."""
  class LookCell(QWidget):
      """One gallery cell: a thumbnail above the look name."""
      def has_thumbnail(self) -> bool:
      """Return True once a rendered thumbnail has replaced the placeholder."""
      def show_placeholder(self) -> None:
      """Show the neutral placeholder instead of a thumbnail."""
      def set_thumbnail(self, rgb8: RGB8) -> None:
      """Show rgb8 as this cell's thumbnail; call it from the GUI thread only."""
      def mousePressEvent(self, event: QMouseEvent) -> None:
      """Report the look of the cell when it is clicked."""
  class LookGallery(QWidget):
      """Grid of look thumbnails rendered on the current image."""
      def cells(self) -> list[LookCell]:
      """Return every cell of the gallery, in the order the looks were set."""
      def looks(self) -> list[Look]:
      """Return the looks of the gallery, in display order."""
      def set_looks(self, looks: Sequence[Look]) -> None:
      """Replace the gallery with looks, in order, and re-queue every thumbnail."""
      def set_source(self, image: Image | None) -> None:
      """Set the current image; every thumbnail is re-rendered on it."""
      def shutdown(self) -> None:
      """Stop the helper thread and release its worker; safe to call more than once."""
      def closeEvent(self, event: QCloseEvent) -> None:
      """Stop the helper thread before the widget goes away."""
# --- lattice_core/ui/bridge ---
  class ConnectionProbe(QObject):
      """Runs one discover() on a helper thread so a slow probe never blocks the GUI."""
      def check(self) -> None:
      """Start one discover() probe unless the previous one is still running."""
      def stop(self) -> None:
      """Stop emitting probe results and wait briefly for the running probe."""
      def set_host(self, host: HostName, port: int | None = None) -> None:
      """Set the host probed by the next check() call."""
  class BridgeStatusDot(QWidget):
      """A coloured dot showing the reachability of one ArtCraft host."""
      def host(self) -> str:
      """Return the host this dot probes."""
      def set_host(self, host: HostName, port: int | None = None) -> None:
      """Retarget the dot at another host; the next check() probes it."""
      def state(self) -> str:
      """Return the current state: connected, disconnected or unknown."""
      def set_state(self, state: str) -> None:
      """Set the displayed state and repaint the dot."""
      def check(self) -> None:
      """Start one asynchronous probe; the dot updates when the probe answers."""
      def start(self) -> None:
      """Probe now; scheduling belongs to the owning application."""
      def stop(self) -> None:
      """Stop the probe thread; safe to call more than once."""
      def paintEvent(self, event: QPaintEvent) -> None:
      """Draw the state colour as a filled circle."""
# --- lattice_core/ui/__init__ ---
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

TASK CARD
### L-UI2 · Recâblage de Lattice Dither sur `lattice_core/ui` (doublons supprimés)
- wave: 2 · deps: L-UI, L11 · executor: OMH deep-work · review: strict · size: L
- owns: `lattice_dither/ui/**`, `tests/test_ui_*.py`, `lattice_core/ui/**`
- context: §2 (`ui/`), 1.1 §19-§22 (fenêtre, export, raccourcis), REVUE-PRODUIT (bloquants 1-2)
- motivation (décision humaine du 2026-11-18) : `lattice_dither/ui/` fait 4026 lignes et n'importe
  AUCUN widget de `lattice_core/ui`. Le canvas a été dupliqué à l'identique lors de L-UI, mais le
  worker et le dialogue d'export ont divergé : le core n'a ni `request_send`/`request_get`/
  `check_version` (pont PhotoCraft interactif), ni `PaletteExtraction` (extraction de palette sur
  thread), ni les pages d'export impression/GIF/vidéo. Tant que Dither garde sa copie, la suite
  n'a pas UNE ui partagée mais deux, et chaque correctif doit être fait deux fois — c'est
  exactement le défaut structurel S5 relevé par la revue produit.
- spec: recâbler Dither sur les widgets du core sans changer un pixel de rendu ni un raccourci.
  1. Ce qui manque au core d'abord : généraliser `RenderWorker` pour couvrir les verbes pont
     (`request_send`, `request_get`, `check_version`) et extraire `PaletteExtraction` dans
     `lattice_core/ui/worker.py` — le bridge du core (`lattice_core/ui/bridge.py`) porte déjà le
     `ConnectionProbe`, ne pas le redupliquer.
  2. Le dialogue d'export du core doit couvrir les quatre formats de Dither (PNG, SVG, impression,
     GIF/vidéo séquence) ; les pages spécifiques restent dans l'app SEULEMENT si elles dépendent
     d'un format que le core n'a pas à connaître.
  3. Ensuite seulement : `lattice_dither/ui/` réimporte les widgets du core ; les fichiers devenus
     vides sont SUPPRIMÉS (pas de coquilles de ré-export qui laisseraient deux chemins d'import).
  4. Aucune régression de comportement : G6 (parité CLI/GUI de Dither) et G7 (témoins bit-à-bit)
     doivent rester verts, et la batterie 1.1 de Dither (raccourcis §22.2, undo, récents, drag & drop)
     doit passer sans qu'un seul test soit modifié — sauf import.
- accept:
  - `lattice_dither/ui/` n'importe plus aucun widget propre : `PreviewCanvas`, `RenderWorker`,
    `PaletteExtraction`, `ExportDialog`, `LookGallery` et `PresetIndicator` viennent du core.
  - pas un seul fichier de `lattice_dither/ui/` ne duplique un widget existant dans
    `lattice_core/ui/` (vérifié par un test qui compare les `__all__` et les noms de classes).
  - les 11 fichiers `tests/test_ui_*.py` passent ; `tests/test_ui_shared.py` reste vert ; le compte
    total de tests ne baisse pas.
  - G6 et G7 verts : un même preset rend des octets identiques en CLI et GUI, et les trois témoins
    sont bit-à-bit.
  - le worker du core expose `request_send`, `request_get`, `check_version` et `PaletteExtraction`,
    couverts par des tests, et `lattice_core` n'importe toujours aucune application (E8).
  - `lattice_core/ui` s'installe et s'importe sans Dither : `pip install -e .[ui]` seul suffit.


CURRENT CONTENT OF YOUR FILES (state on disk — integrate, never replace)
# lattice_dither/ui/**: (à créer — n'existe pas encore sur disque)

# tests/test_ui_*.py: (à créer — n'existe pas encore sur disque)

# lattice_core/ui/**: (à créer — n'existe pas encore sur disque)

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
      "file": "lattice_dither/ui/export_dialog.py",
      "line": 69,
      "what": "Le dialogue d'export de l'app subsiste (ExportDialog/ExportError/run_export_dialog, 4 formats) et reste branché sur Ctrl+E ; le ExportDialog du core n'est pas utilisé par Dither. Spec point 2 et accept 1-2 non tenus ; l'E3 déclaré est une impasse de scope, pas un blocage technique.",
      "why": "La carte exige UN dialogue partagé (défaut S5) ; l'argument « hors owns » ne tient pas : le core dialog.injecte déjà render_full ; le même pattern (writers + tr injectés) couvre les 4 formats sans que le core importe l'app ; seule l'écriture vidéo (imageio-ffmpeg) peut rester injectée. Conséquence : commands.py passe window._last_image (preview ≤1024 px) → les exports SVG/impression/GIF/vidéo sortent à la résolution preview ; le bloquant 1 de REVUE-PRODUIT n'est pas livré.",
      "fix": "Généraliser lattice_core/ui/export_dialog.py : 4 formats (PNG, SVG, impression, GIF/vidéo séquence) avec frames, writers génériques côté core (Pillow only), writer vidéo et tr() injectables ; recâbler commands.py sur le core ; SUPPRIMER lattice_dither/ui/export_dialog.py ; adapter tests/test_ui_export.py. Attention : test_ui_commands.py:554 épingle le handoff preview de Ctrl+E — déviation E1 « test périmé par la carte » à déclarer par l'orchestrateur."
    },
    {
      "severity": "major",
      "file": "tests/test_ui_no_duplicates.py",
      "line": 39,
      "what": "DECLARED_APP_EXPORT = {\"ExportDialog\", \"ExportError\"} exempte le doublon ; ExportDialog absent de SHARED_WIDGETS.",
      "why": "Le test exigé par l'accept 2 ne peut pas échouer sur le doublon que la carte interdit.",
      "fix": "Dialogue déplacé dans le core : retirer DECLARED_APP_EXPORT, ajouter ExportDialog (+ ExportError) à SHARED_WIDGETS."
    },
    {
      "severity": "minor",
      "file": "lattice_core/ui/worker.py",
      "line": 103,
      "what": "oversize_message du core sans « in Lattice Dither » (delta de message utilisateur).",
      "why": "Aucun test n'épingle le texte exact ; G6/G7 non affectés.",
      "fix": "Assumer et documenter la normalisation app-agnostique, ou paramétrer le nom d'application."
    },
    {
      "severity": "minor",
      "file": "lattice_core/ui/worker.py",
      "line": 46,
      "what": "NO_CLIENT_MESSAGE code en dur « Start it from the PhotoCraft (Lattice Dither) shortcut. » dans le widget partagé.",
      "why": "Chaîne spécifique à une application dans un widget core ; trompeuse pour Glyph/Glitch.",
      "fix": "Injecter le libellé du raccourci au constructeur, comme layer_name ; défaut app-agnostique."
    }
  ],
  "regression": "aucune régression pixel/raccourci — seul delta : message oversize tronqué ; export Ctrl+E à la résolution preview préexistant non corrigé (voir blocker)",
  "renderer_invariants": "all six hold (aucun renderer modifié)",
  "tests_that_cannot_fail": [
    "tests/test_ui_no_duplicates.py::test_the_app_does_not_redefine_core_widgets",
    "tests/test_ui_no_duplicates.py::test_no_app_module_defines_a_core___all__widget",
    "tests/test_ui_no_duplicates.py::test_shared_widgets_are_defined_in_core_and_not_in_the_app"
  ],
  "notes": "E3 rejeté : missing accept, pas un blocage. worker/canvas/PaletteExtraction fidèlement recâblés. G2 279 ≥ 266, test_ui_shared vert. Le diff embarqué omettait les tests ajoutés/modifiés et la section CODER NOTES était vide — E3 retrouvé dans le docstring du test."
}

DISPOSITION ORCHESTRATEUR (réponds finding par finding, dans l'ordre du JSON) :
1. [BLOCKER — dialogue d'export non dédupliqué : E3 REJETÉ] Le relecteur a raison : l'exemption de la carte ne vise que le
   writer vidéo (imageio-ffmpeg), pas le dialogue. À faire DANS CE CYCLE :
   a. Généraliser lattice_core/ui/export_dialog.py aux 4 formats (PNG, SVG, impression, GIF/vidéo séquence) : writers
      génériques côté core (Pillow/numpy uniquement, pas de dépendance nouvelle), writer vidéo INJECTABLE depuis l'app (pattern
      render_full déjà présent), tr() injectable pour l'i18n. SVG est déjà dans lattice_core/ui/svg.py.
   b. Recâbler lattice_dither/ui/commands.py sur le dialogue du core (Ctrl+E exporte désormais PLEINE résolution — c'est le
      point de la carte, REVUE bloquant 1).
   c. SUPPRIMER lattice_dither/ui/export_dialog.py (pas de coquille de ré-export).
   d. Adapter tests/test_ui_export.py (dans tes owns) + le handoff preview de test_ui_commands.py (le test épinglait l'ancien
      comportement preview — l'orchestrateur enregistre la déviation E1 DEV « test périmé par la carte », précédent DEV-209 ;
      ne contourne pas le test en silence : adapte-le à la pleine résolution).
2. [major — test anti-doublon whitelisté] ACCEPTE : retirer DECLARED_APP_EXPORT, ajouter ExportDialog (+ ExportError) à
   SHARED_WIDGETS dès que le dialogue est dans le core.
3. [minor — oversize_message] ACCEPTE : documente la normalisation app-agnostique (pas de réintroduction du nom d'app dans le core).
4. [minor — NO_CLIENT_MESSAGE en dur] ACCEPTE : injecter le libellé du raccourci au constructeur du worker (comme layer_name),
   défaut app-agnostique ; garde le texte actuel pour Dither.
Rappels : zéro régression pixel/raccourci (G6/G7 : ne touche ni pipeline ni CLI) ; lattice_core n'importe jamais d'app (E8) ;
le compte total de tests ne baisse pas.