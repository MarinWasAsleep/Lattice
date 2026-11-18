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



TASK CARD

### L12 · Lattice Glyph application shell
- wave: 1 · deps: L6, L8, L9, L11 · executor: OMH deep-work · review: full · size: L
- owns: `lattice_glyph/**`, `tests/test_glyph_app.py`
- context: §1 §2 §7 §8 §9 §10 §11
- spec: the `lattice-glyph` distribution. PySide6 window with a renderer selector, a live preview, a
  palette panel, a preset browser, and the four CLI verbs of §8. Bridge to PhotoCraft and
  DesignCraft. Works standalone on a dropped file. No new dependency.
- accept:
  - the app launches, opens an image, renders, and saves.
  - the CLI `render` and the GUI produce identical bytes for the same preset (G9).
  - `bridge status` reports the host state without crashing when no host runs.
  - the app runs with `lattice-core` installed without the `[ui]` extra only for the CLI path.
  - every renderer in the registry is selectable in the UI.



CURRENT CONTENT OF THE FILES CONCERNED BY THE FINDINGS

--- lattice_glyph/window.py ---
"""Main window of Lattice Glyph: selector, live preview, palette, presets and bridge.

The window owns the only ``PipelineSpec`` and hands every job to a controller:

- previews go to the shared ``RenderWorker`` on a helper thread;
- exports go to ``ExportController``, which calls the same functions the CLI calls, so the
  CLI and the GUI cannot produce different bytes for the same preset (G9);
- host work goes to ``BridgeController``, and an absent host is a status-bar message.

The shared widgets of ``lattice_core.ui`` are consumed, never reimplemented: canvas, worker,
export dialog, preset indicator, empty state, bridge dot and the glyph browser.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTabWidget,
    QWidget,
)

import lattice_core.dither  # noqa: F401  (registers every algorithm)
import lattice_core.effects  # noqa: F401  (registers every effect)
import lattice_core.renderers  # noqa: F401  (registers every renderer)
from lattice_core.pipeline import PipelineSpec
from lattice_core.types import Image
from lattice_core.ui import (
    BridgeStatusDot,
    EmptyState,
    PresetIndicator,
    PreviewCanvas,
    RenderWorker,
    oversize_message,
    preview_proxy,
)
from lattice_core.ui.glyph_browser import GlyphBrowser
from lattice_glyph import APP_NAME
from lattice_glyph import presets as preset_tools
from lattice_glyph.actions import build_actions, build_toolbar, dropped_images
from lattice_glyph.bridge_actions import DEFAULT_HOST
from lattice_glyph.bridge_controller import BridgeController
from lattice_glyph.document import DocumentError, load_image
from lattice_glyph.export_actions import ExportController
from lattice_glyph.palette_panel import PalettePanel
from lattice_glyph.preset_panel import PresetPanel
from lattice_glyph.renderer_panel import RendererPanel

LOGGER = logging.getLogger(__name__)

SETTINGS_NAME = "LatticeGlyph"
GEOMETRY_KEY = "geometry"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
PANEL_TABS = ("Renderer", "Palette", "Presets", "Ramps")
STATUS_MS = 5000
STOP_MS = 5000
EMPTY_TEXT = "Open an image, or drop one here, to start rendering glyphs."
NO_SOURCE = "Load an image before rendering."


class MainWindow(QMainWindow):
    """Application window owning the pipeline spec, the render worker and the bridge."""

    preview_requested = Signal(object)
    source_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None, *,
                 preset_dirs: tuple[Path, ...] | None = None) -> None:
        """Build the canvas, the docks, the status bar and the helper threads."""
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.spec: PipelineSpec = preset_tools.default_spec()
        self.source: Image | None = None
        self.source_path: Path | None = None
        self.worker: RenderWorker | None = None
        self.render_thread: QThread | None = None
        self._settings = QSettings(SETTINGS_NAME, SETTINGS_NAME)
        self.exporter = ExportController(self)
        self.bridge = BridgeController(self)
        self.canvas = PreviewCanvas(self)
        self.empty = EmptyState(EMPTY_TEXT)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.canvas)
        self.stack.setCurrentWidget(self.empty)
        self.setCentralWidget(self.stack)
        self.setAcceptDrops(True)
        self.action_map = build_actions(self)
        self.toolbar = build_toolbar(self, self.action_map)
        self._build_dock(preset_dirs)
        self._build_status_bar()
        geometry = self._settings.value(GEOMETRY_KEY)
        if geometry:
            self.restoreGeometry(geometry)
        self._start_worker()
        self.bridge.pulled.connect(self._on_pulled)
        self.bridge.pushed.connect(self._on_pushed)
        self.bridge.failed.connect(self.report)
        self.bridge.progress.connect(self.status)
        self.apply_spec(preset_tools.default_spec(), announce=False)

    # --- construction ------------------------------------------------------------

    def _build_dock(self, preset_dirs: tuple[Path, ...] | None) -> None:
        """Create the right dock with the renderer, palette, preset and ramp panels."""
        self.dock = QDockWidget("Panels", self)
        self.dock.setObjectName("panel_dock")
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.tabs = QTabWidget(self.dock)
        self.tabs.setObjectName("panel_tabs")
        self.renderer_panel = RendererPanel(self.tabs)
        self.palette_panel = PalettePanel(self.tabs)
        self.preset_panel = PresetPanel(preset_dirs, self.tabs)
        self.glyph_browser = GlyphBrowser(self.tabs)
        self.panels: dict[str, QWidget] = dict(zip(
            PANEL_TABS,
            (self.renderer_panel, self.palette_panel, self.preset_panel, self.glyph_browser),
            strict=True,
        ))
        for name, panel in self.panels.items():
            self.tabs.addTab(panel, name)
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumWidth(340)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.renderer_panel.changed.connect(self.on_panels_changed)
        self.palette_panel.changed.connect(self.on_panels_changed)
        self.preset_panel.loaded.connect(self.load_spec)
        self.preset_panel.save_requested.connect(self.save_preset_to)
        self.preset_panel.failed.connect(self.report)
        self.glyph_browser.ramp_chosen.connect(self.on_ramp_chosen)

    def _build_status_bar(self) -> None:
        """Create the status bar with the bridge dot, the preset indicator and times."""
        bar = self.statusBar()
        self.bridge_dot = BridgeStatusDot(DEFAULT_HOST, self)
        self.connection_label = QLabel(f"{DEFAULT_HOST}: unknown", self)
        self.connection_label.setObjectName("connection_label")
        self.render_time_label = QLabel("Render: -", self)
        self.render_time_label.setObjectName("render_time_label")
        self.indicator = PresetIndicator(self)
        for widget in (self.bridge_dot, self.connection_label, self.render_time_label,
                       self.indicator):
            bar.addPermanentWidget(widget)
        bar.showMessage("Ready")
        self.bridge_dot.state_changed.connect(self._on_state)

    def _start_worker(self) -> None:
        """Create the render worker in its own thread and connect its signals."""
        thread = QThread(self)
        worker = RenderWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        thread.finished.connect(worker.deleteLater)
        self.preview_requested.connect(worker.request_preview)
        self.source_changed.connect(worker.set_source)
        worker.preview_ready.connect(self._on_preview)
        worker.failed.connect(self.report)
        self.render_thread, self.worker = thread, worker
        thread.start()

    # --- lifecycle ---------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop the helper threads and the bridge probe; safe to call more than once.

        The worker reference is released only once its thread has actually stopped: PySide
        deletes the C++ object with the last Python reference, and dropping it earlier frees
        a worker a running thread is still executing (a hard crash, not an exception).
        """
        self.bridge_dot.stop()
        self.bridge.stop()
        thread = self.render_thread
        if thread is None:
            return
        thread.quit()
        if not thread.wait(STOP_MS):
            LOGGER.warning("the render thread did not stop within %d ms", STOP_MS)
            thread.wait()
        self.render_thread = self.worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """Remember the window geometry and stop the helper threads."""
        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        self.shutdown()
        super().closeEvent(event)

    # --- spec, panels and preview ------------------------------------------------

    def settings(self) -> QSettings:
        """Return the settings object the export dialog remembers its directory in."""
        return self._settings

    def spec_from_panels(self) -> PipelineSpec:
        """Return the spec the panels describe, keeping the pipeline settings not shown."""
        current = self.spec
        spec = PipelineSpec(algorithm_id=current.algorithm_id or "floyd_steinberg",
                            pixel_size=current.pixel_size,
                            renderer=self.renderer_panel.current())
        spec.algorithm_params = dict(current.algorithm_params)
        spec.renderer_style = self.renderer_panel.style_options()
        spec.palette = self.palette_panel.spec()
        spec.color_metric = current.color_metric
        spec.seed = current.seed
        spec.pre_effects = list(current.pre_effects)
        spec.post_effects = list(current.post_effects)
        return spec

    def on_panels_changed(self) -> None:
        """Adopt the panels' spec, mark the preset modified and request a preview."""
        self.spec = self.spec_from_panels()
        self.indicator.pipeline_changed()
        self._request_preview()

    def on_ramp_chosen(self, ramp_id: str) -> None:
        """Copy the ramp chosen in the glyph browser into the glyph_ramp option."""
        ramp = self.glyph_browser.catalogue().get(ramp_id).ramp
        style = dict(self.spec.renderer_style)
        style["ramp"] = ramp
        self.renderer_panel.set_renderer("glyph_ramp", style)
        self.status(f"Ramp {ramp_id}")
        self.on_panels_changed()

    def apply_spec(self, spec: PipelineSpec, announce: bool = True) -> None:
        """Adopt spec, load the panels from it and request a preview."""
        self.spec = spec
        self.renderer_panel.set_renderer(spec.renderer, dict(spec.renderer_style))
        if spec.palette is not None:
            self.palette_panel.set_palette(spec.palette)
        if announce:
            self.indicator.pipeline_changed()
        self._request_preview()

    def load_spec(self, spec: PipelineSpec) -> None:
        """Load a preset spec; the indicator names the preset as freshly applied."""
        self.apply_spec(spec, announce=False)
        path = self.preset_panel.selected_path()
        self.indicator.set_preset(None if path is None else path.name)
        self.indicator.set_image_loaded(self.source is not None)

    def _request_preview(self) -> None:
        """Ask the worker for a preview of the current spec, when an image is loaded."""
        if self.source is not None:
            self.preview_requested.emit(self.spec)

    def set_source(self, image: Image | None, path: Path | None = None) -> None:
        """Adopt image as the document source, refusing an oversized one honestly."""
        if image is not None:
            message = oversize_message(np.shape(image))
            if message is not None:
                self.report(message)
                return
            image = np.ascontiguousarray(image, dtype=np.float32)
        self.source = image
        self.source_path = path if image is not None else None
        self.canvas.set_original(None if image is None else preview_proxy(image))
        self.stack.setCurrentWidget(self.empty if image is None else self.canvas)
        self.indicator.set_image_loaded(image is not None)
        self.source_changed.emit(image)
        self._request_preview()

    def open_dialog(self) -> None:
        """Ask for an image file and open it."""
        path, _ = QFileDialog.getOpenFileName(self, "Open image", str(Path.home()), IMAGE_FILTER)
        if path:
            self.open_path(Path(path))

    def open_path(self, path: str | Path) -> bool:
        """Load path into the document; return True when it became the source."""
        try:
            image = load_image(Path(path))
        except DocumentError as exc:
            self.report(str(exc))
            return False
        self.set_source(image, Path(path))
        self.status(f"Opened {Path(path).name}")
        return True

    def _on_preview(self, result) -> None:
        """Show one finished preview and its duration."""
        self.canvas.set_image(result.image)
        self.stack.setCurrentWidget(self.canvas)
        self.render_time_label.setText(f"Render: {result.seconds * 1000:.0f} ms")

    def set_mode(self, mode: str) -> None:
        """Switch the preview canvas between before, after and split."""
        self.canvas.set_mode(mode)  # type: ignore[arg-type]
        action = self.action_map.get(f"mode_{mode}")
        if action is not None:
            action.setChecked(True)

    # --- actions the toolbar and tests call by name -------------------------------

    def export_dialog(self) -> None:
        """Open the shared full-resolution export dialog."""
        self.exporter.dialog()

    def export_to(self, path: str | Path) -> dict:
        """Write the current render to path in the format the path names."""
        return self.exporter.to(path)

    def export_text(self) -> None:
        """Ask for a text-export path and write txt, ansi or html."""
        self.exporter.text()

    def save_preset_to(self, path: str | Path) -> None:
        """Write the current spec as a v3 preset and remember it as the applied one."""
        self.exporter.save_preset(str(path))

    def render_full(self, image: Image, spec: PipelineSpec):
        """Render spec on image through the function the CLI calls (G9)."""
        return self.exporter.render_full(image, spec)

    # --- bridge ------------------------------------------------------------------

    def get_from_host(self) -> None:
        """Read the active document of the bridge host into this application."""
        self.bridge.pull()

    def send_to_host(self) -> None:
        """Place the current full-resolution render in the bridge host."""
        if self.source is None:
            self.report(NO_SOURCE)
            return
        try:
            rgb8 = self.render_full(self.source, self.spec)
        except DocumentError as exc:
            self.report(str(exc))
            return
        self.bridge.push(np.ascontiguousarray(rgb8, dtype=np.uint8))

    def _on_pulled(self, image: object, host: str) -> None:
        """Adopt a document pulled from a host, which has no source path."""
        if image is None:
            self.report(f"{host}: no document")
            return
        self.set_source(np.ascontiguousarray(np.asarray(image), dtype=np.float32))
        self.status(f"Read the {host} document")

    def _on_pushed(self, object_id: int) -> None:
        """Report a successful placement in the host."""
        self.status(f"Placed object {object_id}")

    def _on_state(self, state: str) -> None:
        """Show the host reachability in the status bar label."""
        self.connection_label.setText(f"{DEFAULT_HOST}: {state}")

    def check_bridge(self) -> None:
        """Ask the bridge status dot to probe the host now."""
        self.bridge_dot.check()

    # --- misc --------------------------------------------------------------------

    def status(self, message: str) -> None:
        """Show one transient message in the status bar."""
        self.statusBar().showMessage(message, STATUS_MS)

    def report(self, message: str) -> None:
        """Show a failure in the status bar and a dialog, never a traceback."""
        LOGGER.info("reported: %s", message)
        self.status(message)
        QMessageBox.critical(self, APP_NAME, message)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept a drag carrying at least one local image file."""
        if dropped_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Open the first image of a drop, or report that the drop was ignored."""
        images = dropped_images(event.mimeData())
        if not images:
            self.status("Ignored: no image in the drop")
            event.ignore()
            return
        event.acceptProposedAction()
        self.open_path(images[0])


__all__ = ["MainWindow", "PANEL_TABS"]


--- lattice_glyph/renderer_panel.py ---
"""Renderer panel: every registered renderer, with the option form of the selected one.

The selector's list is ``lattice_core.cell.list_renderers()``, never a table, so a renderer
added to the core becomes selectable here without touching this module (L12 accept). The
option form is built from ``lattice_glyph.options``: one widget per declared option, at its
default; a renderer this table does not name shows an honest "no option" line.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lattice_core.cell import list_renderers
from lattice_glyph import options as option_tools


class RendererPanel(QWidget):
    """Renderer selector plus the option widgets of the selected renderer."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the selector and the option host, then show the first renderer."""
        super().__init__(parent)
        self.setObjectName("renderer_panel")
        self._loading = False
        self._renderer = ""
        self._widgets: dict[str, QWidget] = {}
        self.selector = QComboBox(self)
        self.selector.setObjectName("renderer_selector")
        for name in list_renderers():
            self.selector.addItem(name, name)
        self.host = QWidget(self)
        self.host.setObjectName("renderer_options")
        self.form = QFormLayout(self.host)
        self.form.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel("Renderer", self))
        layout.addWidget(self.selector)
        layout.addWidget(self.host)
        layout.addStretch(1)
        self.selector.currentIndexChanged.connect(self._on_renderer_chosen)
        self._show(str(self.selector.currentData() or ""))

    def renderers(self) -> list[str]:
        """Return every renderer name the selector offers, in display order."""
        return [str(self.selector.itemData(index)) for index in range(self.selector.count())]

    def current(self) -> str:
        """Return the renderer currently selected."""
        return str(self.selector.currentData())

    def option_widget(self, key: str) -> QWidget | None:
        """Return the widget of one option key, or None for a renderer that lacks it."""
        return self._widgets.get(key)

    def style_options(self) -> dict:
        """Return the style options the widgets hold, defaults already dropped."""
        values: dict = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QLineEdit):
                values[key] = widget.text()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[key] = widget.value()
        return option_tools.clean(self._renderer, values)

    def set_renderer(self, name: str, style: dict | None = None) -> None:
        """Select name without emitting, then load style into its widgets."""
        index = self.selector.findData(name)
        if index < 0:
            raise ValueError(f"unknown renderer {name!r}")
        self._loading = True
        try:
            self.selector.setCurrentIndex(index)
            self._show(name)
            self._load(style or {})
        finally:
            self._loading = False

    def _on_renderer_chosen(self) -> None:
        """Show the option widgets of the chosen renderer and announce the change."""
        if self._loading:
            return
        self._show(str(self.selector.currentData()))
        self.changed.emit()

    def _show(self, name: str) -> None:
        """Rebuild the option form for name, every widget at its default."""
        self._renderer = name
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._widgets = {}
        for spec in option_tools.specs_for(name):
            widget = _widget_for(spec, self.host)
            self._widgets[spec.key] = widget
            label = QLabel(spec.label, self.host)
            if spec.hint:
                label.setToolTip(spec.hint)
            self.form.addRow(label, widget)
        for widget in self._widgets.values():
            _connect(widget, self._emit_changed)
        if not self._widgets:
            self.form.addRow(QLabel("This renderer has no option.", self.host))

    def _emit_changed(self) -> None:
        """Announce one user edit of an option, unless the panel is being loaded."""
        if not self._loading:
            self.changed.emit()

    def _load(self, style: dict) -> None:
        """Write style into the widgets, leaving every absent key at its default."""
        for spec in option_tools.specs_for(self._renderer):
            widget = self._widgets.get(spec.key)
            if widget is None:
                continue
            value = style.get(spec.key, spec.default)
            if isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value) if value is not None else int(spec.minimum or 0))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value) if value is not None else float(spec.minimum or 0.0))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))


def _widget_for(spec: option_tools.OptionSpec, parent: QWidget) -> QWidget:
    """Return the input widget a spec kind calls for, at its default value."""
    default = spec.default
    if spec.kind == "bool":
        box = QCheckBox(parent)
        box.setChecked(bool(default))
        return box
    if spec.kind == "choice":
        combo = QComboBox(parent)
        for choice in spec.choices:
            combo.addItem(choice, choice)
        combo.setCurrentIndex(max(0, combo.findData(default)))
        return combo
    if spec.kind == "float":
        spin = QDoubleSpinBox(parent)
        spin.setDecimals(2)
        spin.setSingleStep(float(spec.step))
        spin.setRange(-1e6, 1e6)
        if spec.minimum is not None and spec.maximum is not None:
            spin.setRange(float(spec.minimum), float(spec.maximum))
        spin.setValue(float(default))  # type: ignore[arg-type]
        return spin
    if spec.kind == "int":
        spin = QSpinBox(parent)
        spin.setRange(0, 1_000_000)
        if spec.minimum is not None and spec.maximum is not None:
            spin.setRange(int(spec.minimum), int(spec.maximum))
        spin.setValue(int(default))  # type: ignore[arg-type]
        return spin
    edit = QLineEdit(parent)
    edit.setText("" if default is None else str(default))
    return edit


def _connect(widget: QWidget, slot: Callable[[], None]) -> None:
    """Connect the change signal the widget actually has to slot."""
    if isinstance(widget, QLineEdit):
        widget.textChanged.connect(lambda _text: slot())
    elif isinstance(widget, QCheckBox):
        widget.toggled.connect(lambda _state: slot())
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(lambda _index: slot())
    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.valueChanged.connect(lambda _value: slot())


--- lattice_glyph/document.py ---
"""The single render path of Lattice Glyph: load, render, export bytes (G9, §8, §11).

Every entry point of the application goes through this module. ``render_rgb8`` is
``lattice_core.pipeline.render`` and nothing else, so the CLI and the GUI cannot drift:
the GUI export dialog is handed this exact function. SVG and text export need the
``CellGrid`` the pipeline builds internally (§3); ``grid_bundle`` re-runs the same core
steps in the same order and never re-implements their maths, and a test pins its frame
to ``render`` byte for byte.

Promoted effects are raster: they are applied to PNG and not to vector or text output,
which is reported as a warning instead of being silently dropped.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image as PILImage

import lattice_core.dither  # noqa: F401  (registers every algorithm this path can run)
import lattice_core.effects  # noqa: F401  (registers every effect a preset may name)
from lattice_core import color
from lattice_core import pipeline as _pipeline
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer
from lattice_core.pipeline import PipelineSpec, resolve_palette
from lattice_core.registry import get_algorithm, resolve_params
from lattice_core.svg import render_svg
from lattice_core.textout import render_text
from lattice_core.types import RGB8, Image, Palette

FORMATS: tuple[str, ...] = ("png", "svg", "txt", "ansi", "html")
TEXT_FORMATS: tuple[str, ...] = ("txt", "ansi", "html")
SUFFIXES: dict[str, str] = {
    "png": ".png",
    "svg": ".svg",
    "txt": ".txt",
    "ansi": ".ansi",
    "html": ".html",
}
RASTER_ONLY = "post effects are raster: they are not applied to {fmt} export"


class DocumentError(Exception):
    """A typed failure of the document path: unreadable source, or an impossible export."""


class GridError(DocumentError):
    """An export format that needs a CellGrid, asked for a render that has none."""


@dataclass(frozen=True)
class GridBundle:
    """The §3 grid of one spec, with the palette, renderer and style that produced it."""

    grid: CellGrid
    palette: Palette
    renderer: CellRenderer
    style: RenderStyle


@dataclass(frozen=True)
class Export:
    """One written file: where it went, in which format, its size and its warnings."""

    path: Path
    fmt: str
    size: int
    warnings: list[str] = field(default_factory=list)


def load_image(path: str | Path) -> Image:
    """Load path as a float32 RGB image, raising DocumentError when it is unusable."""
    target = Path(path)
    if not target.is_file():
        raise DocumentError(f"image not found: {target}")
    try:
        with PILImage.open(target) as handle:
            return color.to_float(handle)
    except (OSError, ValueError) as exc:
        raise DocumentError(f"cannot read image {target}: {exc}") from None


def render_rgb8(image: Image, spec: PipelineSpec) -> RGB8:
    """Render image through the core pipeline, raising DocumentError on any failure."""
    try:
        return _pipeline.render(image, spec)
    except Exception as exc:  # noqa: BLE001 - every pipeline failure is a render error (§8)
        raise DocumentError(f"render failed: {exc}") from None


def grid_bundle(image: Image, spec: PipelineSpec) -> GridBundle:
    """Return the §3 grid of spec, built with the core steps in the normative order.

    Steps 1 to 5 come from ``pipeline._prepare``, the geometry from step 6, the cell
    averages, palette, dither, sub-points and samples from the helpers the pipeline
    itself calls; nothing is re-implemented here.
    """
    if spec.algorithm_id is None or spec.palette is None:
        raise GridError(
            "continuous mode has no cell grid: export png instead of svg, txt, ansi or html"
        )
    try:
        return _grid_bundle(image, spec)
    except (KeyError, ValueError) as exc:
        raise DocumentError(f"cannot build the cell grid: {exc}") from None


def _grid_bundle(image: Image, spec: PipelineSpec) -> GridBundle:
    """Build the §3 grid of spec; the caller turns a lookup failure into a DocumentError."""
    work, _ = _pipeline._prepare(image, spec, None)
    renderer = get_renderer(spec.renderer)
    style = RenderStyle(options=dict(spec.renderer_style))
    cell_w, cell_h = _pipeline._cell_geometry(renderer, spec.pixel_size)
    padded = _pipeline._pad_to_cells(work, cell_w, cell_h)
    cells = _pipeline._to_cells(padded, cell_w, cell_h)
    palette = resolve_palette(spec.palette, cells)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    params[_pipeline.RESERVED_METRIC] = color.metric_code(spec.color_metric)
    subgrid = (int(renderer.subgrid()[0]), int(renderer.subgrid()[1]))
    subindex = None
    if subgrid != (1, 1):
        subindex = _pipeline._subindex(
            padded, palette, info.fn, params, (cell_w, cell_h), subgrid
        )
    grid = _pipeline._make_grid(
        cells,
        _pipeline._run(info.fn, params, cells, palette),
        cell_w,
        cell_h,
        palette,
        samples=_pipeline._derive_samples(renderer, padded, cells, (cell_w, cell_h), subgrid),
        subindex=subindex,
    )
    return GridBundle(grid=grid, palette=palette, renderer=renderer, style=style)


def png_bytes(rgb8: RGB8) -> bytes:
    """Return rgb8 encoded as a PNG file byte for byte as the GUI export writes it."""
    buffer = io.BytesIO()
    color.to_pil(rgb8).save(buffer, format="PNG")
    return buffer.getvalue()


def export_bytes(image: Image, spec: PipelineSpec, fmt: str = "png") -> tuple[bytes, list[str]]:
    """Return the encoded output of spec in fmt, with the warnings of that export."""
    if fmt not in FORMATS:
        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    if fmt == "png":
        return png_bytes(render_rgb8(image, spec)), []
    bundle = grid_bundle(image, spec)
    warnings: list[str] = []
    if spec.post_effects:
        warnings.append(RASTER_ONLY.format(fmt=fmt))
    if fmt == "svg":
        document, svg_warnings = render_svg(
            bundle.grid, bundle.palette, bundle.renderer, bundle.style
        )
        return document.encode("utf-8"), warnings + list(svg_warnings)
    text = render_text(bundle.grid, bundle.palette, bundle.renderer, bundle.style, fmt=fmt)
    return text.encode("utf-8"), warnings


def target_path(path: str | Path, fmt: str) -> Path:
    """Return path with fmt's suffix appended when it carries none of its own."""
    target = Path(path)
    if target.suffix:
        return target
    if fmt not in SUFFIXES:
        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    return target.with_name(target.name + SUFFIXES[fmt])


def write_render(image: Image, spec: PipelineSpec, path: str | Path, fmt: str = "png") -> Export:
    """Render spec and write it to path in fmt, creating the parent directories."""
    payload, warnings = export_bytes(image, spec, fmt)
    target = target_path(path, fmt)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    except OSError as exc:
        raise DocumentError(f"cannot write {target}: {exc}") from None
    return Export(path=target, fmt=fmt, size=len(payload), warnings=warnings)


def format_of(path: str | Path) -> str:
    """Return the export format named by path's suffix, png when the suffix is unknown."""
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix if suffix in FORMATS else "png"


__all__ = [
    "DocumentError",
    "Export",
    "FORMATS",
    "GridBundle",
    "GridError",
    "SUFFIXES",
    "TEXT_FORMATS",
    "export_bytes",
    "format_of",
    "grid_bundle",
    "load_image",
    "png_bytes",
    "render_rgb8",
    "target_path",
    "write_render",
]


--- lattice_glyph/cli.py ---
"""Command line of Lattice Glyph: the four verbs of §8 and their exit codes.

``render`` and ``batch`` go through :mod:`lattice_glyph.document`, the module the GUI
export uses, so their PNG bytes are identical by construction (G9). ``presets`` reads the
v3 preset tiers and ``bridge`` talks to PhotoCraft or DesignCraft; an absent host is a
normal answer reported as text, not a traceback (§7). No verb needs a display and this
module never imports Qt: it only imports the core, whose base install has no PySide6.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

import lattice_core.dither  # noqa: F401  (importing the package registers every algorithm)
import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
import lattice_core.renderers  # noqa: F401  (importing the package registers every renderer)
from lattice_core import color
from lattice_core.bridge import HOSTS, ArtCraftClient, BridgeError
from lattice_core.pipeline import PipelineSpec
from lattice_glyph import presets as preset_tools
from lattice_glyph.document import (
    FORMATS,
    DocumentError,
    Export,
    format_of,
    load_image,
    render_rgb8,
    target_path,
    write_render,
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RENDER = 2
EXIT_BRIDGE = 3
DEFAULT_EXTENSIONS = "png,jpg,jpeg,bmp,tif,tiff,webp"
PROG = "lattice-glyph"
IMAGE_EXTENSIONS = frozenset(DEFAULT_EXTENSIONS.split(","))


class UsageError(Exception):
    """A command line the application cannot honour: a missing or unreadable preset."""


class _Parser(argparse.ArgumentParser):
    """Argument parser reporting usage errors with exit code 1, not argparse's 2."""

    def error(self, message: str) -> NoReturn:
        """Print the usage line and exit with the §8 usage code."""
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _note(message: str) -> None:
    """Print one human-readable line on stderr, leaving stdout to the machine result."""
    print(message, file=sys.stderr)


def _emit(args: argparse.Namespace, payload: dict) -> None:
    """Print payload as JSON on stdout when --json is set; stdout stays empty otherwise."""
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _spec(preset: str) -> PipelineSpec:
    """Load a preset file in this app's context, mapping any failure to a usage error."""
    path = Path(preset)
    if not path.is_file():
        raise UsageError(f"preset not found: {path}")
    try:
        return preset_tools.spec_of(preset_tools.read_preset(path))
    except (OSError, ValueError, KeyError) as exc:
        raise UsageError(f"cannot read preset {path}: {exc}") from None


def _failure(args: argparse.Namespace, message: str, code: int) -> int:
    """Report one failure on stderr and in JSON and return the exit code of its class."""
    _note(message)
    _emit(args, {"ok": False, "errors": [message]})
    return code


def _cmd_render(args: argparse.Namespace) -> int:
    """Render one image with one preset into one file, in the format it names."""
    try:
        spec = _spec(args.preset)
        image = load_image(Path(args.source))
        fmt = args.format or format_of(args.output)
        export = write_render(image, spec, args.output, fmt)
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    for warning in export.warnings:
        _note(f"warning: {warning}")
    _note(f"wrote {export.path} ({export.fmt}, {export.size} bytes)")
    _emit(args, _export_payload(export))
    return EXIT_OK


def _export_payload(export: Export) -> dict:
    """Return the machine-readable description of one written file."""
    return {"ok": True, "file": str(export.path), "format": export.fmt,
            "bytes": export.size, "warnings": list(export.warnings), "errors": []}


def _extensions(text: str) -> set[str]:
    """Return the lower-case extensions listed in a comma-separated string."""
    return {part.strip().lower().lstrip(".") for part in text.split(",") if part.strip()}


def _batch_inputs(source: Path, extensions: set[str], recursive: bool) -> list[Path]:
    """Return the image files of a directory, sorted, filtered by extension."""
    if not source.is_dir():
        raise UsageError(f"input directory not found: {source}")
    found = source.rglob("*") if recursive else source.iterdir()
    return sorted(
        path for path in found
        if path.is_file() and path.suffix.lower().lstrip(".") in extensions
    )


def _destination(target_dir: Path, item: Path, source: Path, fmt: str, recursive: bool) -> Path:
    """Return where one batch item is written, mirroring the tree when recursive."""
    relative = item.relative_to(source) if recursive else Path(item.name)
    suffix = target_path(relative.name, fmt).suffix
    return target_dir / relative.with_name(relative.stem + suffix)


def _cmd_batch(args: argparse.Namespace) -> int:
    """Render every image of a directory with one preset, keeping the file names."""
    try:
        spec = _spec(args.preset)
        source = Path(args.source)
        files = _batch_inputs(source, _extensions(args.ext), args.recursive)
    except UsageError as exc:
        _note(str(exc))
        _emit(args, {"ok": False, "files": [], "errors": [str(exc)]})
        return EXIT_USAGE
    fmt = args.format or "png"
    written: list[str] = []
    errors: list[str] = []
    for item in files:
        destination = _destination(Path(args.output), item, source, fmt, args.recursive)
        try:
            export = write_render(load_image(item), spec, destination, fmt)
        except DocumentError as exc:
            _note(f"{item}: {exc}")
            errors.append(f"{item}: {exc}")
            continue
        _note(f"wrote {export.path}")
        written.append(str(export.path))
    _emit(args, {"ok": not errors, "files": written, "errors": errors})
    return EXIT_OK if not errors else EXIT_RENDER


def _cmd_presets_list(args: argparse.Namespace) -> int:
    """List the presets of the shipped tier and of the user tier."""
    directories = [Path(entry) for entry in args.directory] or None
    entries = preset_tools.available(directories)
    payload = {"presets": [
        {"name": entry.name, "path": str(entry.path), "read_only": entry.read_only}
        for entry in entries
    ]}
    _emit(args, payload)
    if not args.json:
        for entry in entries:
            tier = "shipped" if entry.read_only else "user"
            print(f"{entry.name}\t{tier}\t{entry.path}")
    return EXIT_OK


def _cmd_presets_show(args: argparse.Namespace) -> int:
    """Describe one preset: its renderer, its options, its palette and its pipeline."""
    try:
        preset = preset_tools.read_preset(Path(args.name))
    except (OSError, ValueError, KeyError) as exc:
        return _failure(args, f"cannot read preset {args.name}: {exc}", EXIT_USAGE)
    description = preset_tools.describe(preset)
    _emit(args, description)
    if not args.json:
        print(json.dumps(description, indent=2, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


def _cmd_presets_validate(args: argparse.Namespace) -> int:
    """Validate one preset file, or every preset of the tiers when no path is given."""
    reports = [preset_tools.validate(Path(args.path))] if args.path \
        else preset_tools.validate_all()
    payload = {
        "ok": all(report.ok for report in reports),
        "presets": [
            {"name": report.name, "ok": report.ok, "renderer": report.renderer,
             "errors": report.errors, "warnings": report.warnings}
            for report in reports
        ],
    }
    _emit(args, payload)
    if not args.json:
        for report in reports:
            print(f"{report.name}\t{'ok' if report.ok else 'invalid'}\t{report.renderer}")
            for prose in report.errors + report.warnings:
                print(f"  {prose}")
    return EXIT_OK if payload["ok"] else EXIT_USAGE


def discover_host(host: str) -> ArtCraftClient | None:
    """Return a live client for host, or None for any host that is not running (§7)."""
    try:
        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
    except (BridgeError, OSError, ValueError):
        return None


def host_report(hosts: tuple[str, ...] | list[str]) -> list[dict]:
    """Probe every host and return one {host, connected} record per host."""
    report: list[dict] = []
    for host in hosts:
        client = discover_host(host)
        if client is not None:
            client.disconnect()
        report.append({"host": host, "connected": client is not None})
    return report


def _cmd_bridge_status(args: argparse.Namespace) -> int:
    """Report the reachability of the ArtCraft hosts, with no host running being normal."""
    hosts: list[str] = [args.host] if args.host else list(HOSTS)
    report = host_report(hosts)
    _emit(args, {"ok": True, "hosts": report})
    if not args.json:
        for entry in report:
            print(f"{entry['host']}: {'connected' if entry['connected'] else 'not running'}")
    return EXIT_OK


def _cmd_bridge_pull(args: argparse.Namespace) -> int:
    """Render the active document of a host with a preset and write the result."""
    client = discover_host(args.host)
    if client is None:
        return _failure(args, f"{args.host}: host not running", EXIT_BRIDGE)
    try:
        image = color.to_float(client.render_document())
        export = write_render(image, _spec(args.preset), args.output,
                              args.format or format_of(args.output))
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    except (BridgeError, OSError) as exc:
        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
    _note(f"wrote {export.path} ({export.size} bytes)")
    _emit(args, _export_payload(export))
    return EXIT_OK


def _cmd_bridge_push(args: argparse.Namespace) -> int:
    """Render one image with a preset and place it in a host as a layer."""
    client = discover_host(args.host)
    if client is None:
        return _failure(args, f"{args.host}: host not running", EXIT_BRIDGE)
    try:
        rgb8 = render_rgb8(load_image(Path(args.source)), _spec(args.preset))
        object_id = client.place_as_layer(color.to_pil(rgb8), args.name)
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    except (BridgeError, OSError) as exc:
        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
    _note(f"placed object {object_id} in {args.host}")
    _emit(args, {"ok": True, "host": args.host, "object_id": object_id, "errors": []})
    return EXIT_OK


def _add_render_options(parser: argparse.ArgumentParser, *, output_help: str) -> None:
    """Add the preset, the output and the JSON flag shared by the render verbs."""
    parser.add_argument("--preset", required=True, help="preset JSON file")
    parser.add_argument("--out", dest="output", required=True, help=output_help)
    parser.add_argument("--format", choices=FORMATS, default=None,
                        help="png, svg, txt, ansi or html (default: from --out)")
    parser.add_argument("--json", action="store_true", help="print a JSON result")


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser carrying the four verbs of §8."""
    parser = _Parser(prog=PROG, description="Lattice Glyph command line.")
    verbs = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    render = verbs.add_parser("render", help="render one image with one preset")
    _add_render_options(render, output_help="output file")
    render.add_argument("--in", dest="source", required=True, help="input image")
    render.set_defaults(handler=_cmd_render)

    batch = verbs.add_parser("batch", help="render a directory with one preset")
    _add_render_options(batch, output_help="output directory")
    batch.add_argument("--in", dest="source", required=True, help="input directory")
    batch.add_argument("--recursive", action="store_true", help="walk subdirectories")
    batch.add_argument("--ext", default=DEFAULT_EXTENSIONS, help="input extensions")
    batch.set_defaults(handler=_cmd_batch)

    presets = verbs.add_parser("presets", help="list, show and validate presets")
    preset_verbs = presets.add_subparsers(dest="preset_command", required=True,
                                          parser_class=_Parser)
    listing = preset_verbs.add_parser("list", help="list the presets of both tiers")
    listing.add_argument("--dir", dest="directory", action="append", default=[],
                         help="search directory, repeatable")
    listing.add_argument("--json", action="store_true", help="print a JSON result")
    listing.set_defaults(handler=_cmd_presets_list)
    show = preset_verbs.add_parser("show", help="describe one preset")
    show.add_argument("name", help="preset file to describe")
    show.add_argument("--json", action="store_true", help="print a JSON result")
    show.set_defaults(handler=_cmd_presets_show)
    check = preset_verbs.add_parser("validate", help="validate one preset or the tiers")
    check.add_argument("path", nargs="?", default=None, help="preset file to validate")
    check.add_argument("--json", action="store_true", help="print a JSON result")
    check.set_defaults(handler=_cmd_presets_validate)

    bridge = verbs.add_parser("bridge", help="talk to PhotoCraft or DesignCraft")
    bridge_verbs = bridge.add_subparsers(dest="bridge_command", required=True,
                                         parser_class=_Parser)
    status = bridge_verbs.add_parser("status", help="report the host state")
    status.add_argument("host", nargs="?", default=None, choices=HOSTS,
                        help="host to probe (default: both)")
    status.add_argument("--json", action="store_true", help="print a JSON result")
    status.set_defaults(handler=_cmd_bridge_status)
    pull = bridge_verbs.add_parser("pull", help="render the host document into a file")
    _add_render_options(pull, output_help="output file")
    pull.add_argument("--host", dest="host", default="photocraft", choices=HOSTS)
    pull.set_defaults(handler=_cmd_bridge_pull)
    push = bridge_verbs.add_parser("push", help="place a render in the host as a layer")
    push.add_argument("--host", dest="host", default="photocraft", choices=HOSTS)
    push.add_argument("--preset", required=True, help="preset JSON file")
    push.add_argument("--in", dest="source", required=True, help="input image")
    push.add_argument("--name", default="Lattice Glyph", help="layer or object name")
    push.add_argument("--json", action="store_true", help="print a JSON result")
    push.set_defaults(handler=_cmd_bridge_push)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return its exit code; no traceback ever escapes."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or EXIT_OK)
    try:
        return int(args.handler(args))
    except UsageError as exc:
        _note(str(exc))
        return EXIT_USAGE
    except DocumentError as exc:
        _note(str(exc))
        return EXIT_RENDER
    except (BridgeError, OSError) as exc:
        _note(f"{args.command} failed: {exc}")
        return EXIT_BRIDGE
    except Exception as exc:  # noqa: BLE001 - §8 forbids a traceback on stderr
        _note(f"{args.command} failed: {exc}")
        return EXIT_RENDER


if __name__ == "__main__":
    sys.exit(main())


--- lattice_glyph/bridge_actions.py ---
"""Bridge work of the Glyph shell, run on a helper thread (§7).

The window never talks to a host on the GUI thread: a slow connection would freeze the
preview. ``BridgeWorker`` does exactly three things — pull the active document, place a
render as a layer, or report why neither was possible — and a missing host is the normal
``failed`` case, reported in the status bar, never an exception.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from lattice_core import color
from lattice_core.bridge import ArtCraftClient, BridgeError
from lattice_core.types import RGB8, Image

LOGGER = logging.getLogger(__name__)

HOSTS = ("photocraft", "designcraft")
DEFAULT_HOST = "photocraft"
DEFAULT_NAME = "Lattice Glyph"
NOT_RUNNING = "{host} is not running: Lattice Glyph works standalone"


class BridgeWorker(QObject):
    """Pulls documents from a host and pushes renders to it, off the GUI thread."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    progress = Signal(str)

    @Slot(str)
    def pull(self, host: str) -> None:
        """Read the active document of host and emit it as a float32 image."""
        self.progress.emit(f"Reading the {host} document…")
        client = _discover(host)
        if client is None:
            self.failed.emit(NOT_RUNNING.format(host=host))
            return
        try:
            image = color.to_float(client.render_document())
        except (BridgeError, OSError, ValueError) as exc:
            LOGGER.debug("bridge pull failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pulled.emit(image, host)

    @Slot(str, object, str)
    def push(self, host: str, rgb8: RGB8, name: str) -> None:
        """Place one rendered image in host as a layer and emit the object id."""
        self.progress.emit(f"Placing the render in {host}…")
        client = _discover(host)
        if client is None:
            self.failed.emit(NOT_RUNNING.format(host=host))
            return
        try:
            object_id = client.place_as_layer(color.to_pil(rgb8), name or DEFAULT_NAME)
        except (BridgeError, OSError, ValueError) as exc:
            LOGGER.debug("bridge push failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pushed.emit(int(object_id))


def _discover(host: str) -> ArtCraftClient | None:
    """Return a live client for host, or None for every way a host can be absent."""
    if host not in HOSTS:
        return None
    try:
        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
    except (BridgeError, OSError, ValueError):
        LOGGER.debug("host discovery failed", exc_info=True)
        return None


def pull_image(host: str = DEFAULT_HOST) -> Image | None:
    """Synchronously read a host document, returning None when the host is absent."""
    client = _discover(host)
    if client is None:
        return None
    try:
        return color.to_float(client.render_document())
    except (BridgeError, OSError, ValueError):
        return None
    finally:
        client.disconnect()


__all__ = ["BridgeWorker", "DEFAULT_HOST", "HOSTS", "NOT_RUNNING", "pull_image"]


--- lattice_glyph/pyproject.toml ---
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "lattice-glyph"
version = "0.1.0"
description = "Lattice Glyph: glyph, bitmask and text rendering for PhotoCraft and DesignCraft"
requires-python = ">=3.13"
license = "MIT OR Apache-2.0"
dependencies = [
    "lattice-core>=0.1,<0.2",
    "numpy",
    "numba",
    "Pillow",
]

[project.optional-dependencies]
ui = ["lattice-core[ui]"]

[project.scripts]
lattice-glyph-cli = "lattice_glyph.cli:main"

# The distribution lives beside the application directory, as lattice-dither does. The
# mapping below makes a build started from this directory ship the package itself and its
# presets, instead of a wheel that carries only metadata.
[tool.setuptools]
packages = ["lattice_glyph"]
package-dir = { "lattice_glyph" = "." }

[tool.setuptools.package-data]
lattice_glyph = ["presets/*.json"]


RETRY attempt 2 (cycle 2 de revue). Fix exactly what is reported below, change nothing else,
keep passing tests passing. Le codeur de l'attempt 1 a été TUÉ par timeout sans rendre de rapport :
personne n'a jamais relu ce code. Le relecteur a trouvé 4 majors réels ; j'en ai confirmé deux par
exécution, chiffres à l'appui.

CONFIRMÉ PAR EXÉCUTION PAR L'ORCHESTRATEUR (ne discute pas, corrige)

A. `spec_from_panels` (window.py:175) — perte de réglages à l'édition. J'ai chargé un preset v3 portant
   brightness=0.15, contrast=0.30, gamma=2.2, saturation=0.40, pre_blur=1.5, auto_levels=True, puis
   simulé une édition de panneau : **les six champs retombent aux valeurs par défaut**
   (0.0 / 0.0 / 1.0 / 0.0 / 0.0 / False). Corrige en partant du spec COURANT (`dataclasses.replace`
   ou `copy.deepcopy` du spec existant) et en ne surchargeant QUE les champs que les panneaux
   possèdent réellement. Un champ non affiché doit survivre intact.

B. `format_of` (document.py:196) — `format_of('a.jpg')` renvoie `'png'` (vérifié), donc
   `render --out photo.jpg` écrit des octets PNG dans un fichier `.jpg`. Deux corrections possibles,
   choisis-en une et assume-la en NOTES : (1) `format_of` déduit le format du suffixe et lève
   `DocumentError` nommant le suffixe quand il n'est pas dans `FORMATS` (png, svg, txt, ansi, html) —
   jamais de repli silencieux ; (2) accepter le repli mais ÉCRIRE le fichier avec l'extension réelle
   (`photo.jpg` → `photo.png`) et l'annoncer dans l'`Export` retourné. Je recommande (1) : un
   utilisateur qui tape `.jpg` doit apprendre tout de suite que ce n'est pas supporté, pas recevoir
   un PNG déguisé. Même règle pour `export_text`.

C. Tests G9 complaisants (tests/test_glyph_app.py) — les deux tests signalés passent par
   `render_rgb8` des deux côtés ET sur des presets aux valeurs par défaut, donc ils ne peuvent pas
   détecter la perte de A. À renforcer : le test de parité CLI/GUI doit partir d'un **preset non
   trivial** (brightness/contrast/gamma/pre_blur/auto_levels non nuls, un effet pré et un effet post,
   une graine ≠ 0), et comparer les octets. Le test des panneaux doit asserter que les champs non
   affichés SURVIVENT à `spec_from_panels` — c'est le test qui aurait dû exister.

D. major renderer_panel.py:150 — chaque frappe dans un champ texte (fg, bg, ramp, alphabet, font)
   déclenche `changed` et un rendu ; `#f` ou une rampe vide fait échouer le rendu. À corriger :
   valider avant d'émettre, ou ne rendre qu'à la fin de la frappe (débounce), et ne jamais laisser
   un état invalide atteindre le worker. Dis en NOTES quelle stratégie tu as prise.

E. minors à traiter : code mort et dupliqué du pont (`pull_image` / `fetch_image` / `_discover` /
   `cli.discover_host` — garde UN chemin) ; point d'entrée GUI manquant dans `[project.scripts]`
   (il n'y a que `lattice-glyph-cli`, ajoute `lattice-glyph = "lattice_glyph.app:main"` ou
   l'équivalent réel) ; `send_to_host` qui rend en pleine résolution sur le thread GUI et ouvre un
   dialogue modal quand l'hôte est absent (le cas « pas d'hôte » doit être un état normal, E9 : un
   message dans la barre d'état, pas une modale).

CONTRAINTES : `window.py` 394 l et `cli.py` 369 l — reste sous 400 chacun ; si tu dois dépasser,
extrais dans un nouveau module de `lattice_glyph/` (tes owns). ruff clean, suite complète verte
(2068 au départ), `tests/test_glyph_app.py` ≤ 400 l. Livre les fichiers modifiés + NOTES + DEVIATIONS.

FINDINGS DU REVIEWER (verbatim)
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "lattice_glyph/window.py",
      "line": 175,
      "what": "spec_from_panels builds a fresh PipelineSpec and copies only algorithm, pixel_size, params, metric, seed and effects. Everything else the loaded preset carried is dropped on the first panel edit: pre-processing fields (brightness, contrast, gamma, saturation, pre_blur, auto_levels, max_side) and output scale/width. The docstring claims it keeps the settings not shown.",
      "why": "Load a preset with brightness != 0, edit a ramp option, then save or export: the render and the saved preset have silently lost those settings. A continuous preset (algorithm null, palette null) also becomes floyd_steinberg plus the panel palette. Shipped presets all have default pipeline fields, so no test sees it. I did not verify the PipelineSpec field names against the core.",
      "fix": "Start from a copy of self.spec (dataclasses.replace or deepcopy) and overwrite only renderer, renderer_style and palette. Keep algorithm_id, and keep a null palette when the spec is continuous. Add a test that loads a preset with non-default pre-processing fields, edits an option, and compares the exported PNG with the CLI render of the saved preset."
    },
    {
      "severity": "major",
      "file": "lattice_glyph/renderer_panel.py",
      "line": 150,
      "what": "Every keystroke in a text option (fg, bg, ramp, alphabet, font) emits changed and triggers a preview. A half-typed colour such as '#f', or an empty ramp, makes the render fail. RenderWorker.failed is wired to MainWindow.report, which opens a modal QMessageBox.critical.",
      "why": "Typing a foreground colour pops an error dialog on the first keystrokes. The palette panel has valid_colours(), but nothing validates the renderer options. Inferred from the design: I did not confirm that the renderers reject these values.",
      "fix": "Validate before emitting (colour regex or 'transparent', non-empty ramp). Keep the previous spec on invalid input and show an inline hint. Make a render failure a status-bar message, or debounce, instead of a modal dialog. Add a test that types '#f' into fg and asserts no QMessageBox."
    },
    {
      "severity": "major",
      "file": "lattice_glyph/document.py",
      "line": 196,
      "what": "format_of falls back to png for any unknown suffix, so `render --out x.jpg` (or .webp, .tif) writes PNG bytes into a file named .jpg. export_text does the same: a typed 'a.xyz' becomes a PNG written through the text-export action.",
      "why": "The file extension lies about the content and nothing warns. The user asked for a JPEG and got a PNG with a .jpg name.",
      "fix": "Reject a suffix outside FORMATS with a usage error (exit 1) unless --format is given. Alternatively, append .png and warn. Cover it with a test."
    },
    {
      "severity": "major",
      "file": "tests/test_glyph_app.py",
      "line": 0,
      "what": "The G9 tests compare CLI and GUI output, but both call document.render_rgb8, and every preset used has default pipeline fields and no effects. The risky path, panels to spec to render, is never compared against a preset file that has non-default values. The 9 tests would not fail on a lossy panel-to-spec path. Nor do they cover continuous mode (algorithm null), the --json-only-stdout guarantee on failure, or the bridge push success path.",
      "why": "They are partly decorative on the points the card cares about. The CLI-without-Qt, registry-selector and bridge-without-host tests are real and would fail on an empty app.",
      "fix": "Add a round-trip test: a preset with brightness, pre_blur and a post effect, loaded in the GUI, edited, then compared with the CLI. Add a continuous-preset test that asserts the app's chosen behaviour. Add a failure-path --json test that checks stdout."
    },
    {
      "severity": "minor",
      "file": "lattice_glyph/cli.py",
      "line": 0,
      "what": "Continuous mode (algorithm null): the CLI renders it as png but svg/txt/ansi/html raise GridError, which becomes exit 2 (acceptable). The GUI renders it until the first panel edit, then converts it to quantised silently (see the spec_from_panels finding). validate accepts both-null and rejects a mixed pair, so the app has no stated position on what it supports. Also: --json prints nothing on stdout for argparse errors and for the generic Exception fallback, and bridge pull/push never disconnect the client (no finally).",
      "why": "§8 says --json prints a machine-readable result, and an absent result is not one. A leaked client leaves a live connection.",
      "fix": "Decide explicitly: either refuse algorithm null with a clear usage message, or support it end to end. Emit {ok:false,errors} on every exit path when --json is set. Wrap the bridge verbs' client use in try/finally disconnect()."
    },
    {
      "severity": "minor",
      "file": "lattice_glyph/bridge_actions.py",
      "line": 86,
      "what": "Dead and duplicated code: pull_image (bridge_actions) and fetch_image (bridge_controller) are two unused synchronous pulls. _discover, cli.discover_host and fetch_image's inline discover are three copies of the same try/except. Also unused: presets.read_text, spec_from_text, default_preset, actions.Action, and the one-line wrappers ExportController.render_full and MainWindow.render_full. bridge_actions and bridge_controller could be one module.",
      "why": "Hygiene: dead code, and three places to fix when the discovery semantics change.",
      "fix": "Keep one discover helper (in a Qt-free module) and delete the unused functions."
    },
    {
      "severity": "minor",
      "file": "lattice_glyph/pyproject.toml",
      "line": 19,
      "what": "The only script is `lattice-glyph-cli`, so no `lattice-glyph` GUI entry point exists. The pyproject sits inside the package directory with package-dir '.'. cli.PROG is 'lattice-glyph' while the installed command has another name.",
      "why": "The app launches only through `python -m lattice_glyph`. A packaged install has no launcher, and the usage text names a command that does not exist.",
      "fix": "Add [project.gui-scripts] lattice-glyph = lattice_glyph.__main__:main (or app:main), and align PROG. Packaging is L23's business, but the entry point belongs to L12."
    },
    {
      "severity": "minor",
      "file": "lattice_glyph/window.py",
      "line": 330,
      "what": "send_to_host renders the full-resolution image on the GUI thread, and the host-absent case (bridge.failed to report) opens a modal error dialog. window.py is 394 lines and cli.py 369. document.grid_bundle re-runs private core steps (_prepare, _cell_geometry, _pad_to_cells, ...), which can drift from the pipeline; one test pins it for 8 renderers on one spec without effects.",
      "why": "A large render freezes the UI. A missing host is a normal state (E9) and deserves a status-bar line, not a dialog. Calling private core functions couples the app to the core's internals.",
      "fix": "Render in the worker thread. Show host-absent as a status message. Ask the core for a public grid-building function."
    }
  ],
  "regression": "none — a new package; lattice_core and lattice_dither are untouched in this diff.",
  "renderer_invariants": "all six hold — no renderer was added or changed. The shell does not mutate inputs: render goes through the core pipeline, and the image passed to the worker is made contiguous without being modified.",
  "tests_that_cannot_fail": [
    "test_cli_render_matches_the_gui_bytes: both sides call render_rgb8, so the byte equality holds by construction. It would not catch a panel-to-spec loss because every preset used has default pipeline fields.",
    "test_the_panels_list_load_save_and_feed_the_spec: only the default pipeline fields are exercised, so it passes with spec_from_panels dropping the other settings."
  ],
  "notes": "Your 3 checks hold on the diff (shared render path, Qt-free CLI, reuse of core/ui). The selector is built from list_renderers(), so a future renderer is visible; its options show 'no option' until OPTIONS names it, which is honest. discover() returning None is handled as a normal state in the CLI and the worker, so there is no E9 issue. Continuous mode: validate accepts both-null; the CLI renders it as png only; the GUI converts it silently on the first edit (see findings). Not run: this review is from the diff only."
}
