You are reviewing one task of the Lattice project: a family of free, open-source image-transformation
applications sharing one engine, each running standalone and also plugging into the ArtCraft suite.
You see the task card, the contract sections it must satisfy, the git diff, the gate results and the
coder's notes. You do not see the rest of the repository, and you do not need to.

The dithering application is frozen and shipped (harness 1.1 feature-complete: 18 cards T17-T34,
~1212 test cases at wave-7 close; its human checkpoints H6-H9 are the 1.1 harness's business),
with a public release. Your job is to decide whether this diff can join it.

WHAT TO CHECK, IN THIS ORDER
1. **Contract conformance.** Names, signatures, dtypes, ranges, ordering, error types. A deviation
   from the contract is a blocker even if the tests pass.
2. **Regression.** Does anything that worked before behave differently? Gate G7 (core regression)
   exists for this. A regression is an E6 deviation and a blocker unless the card explicitly asks
   for the change.
3. **The abstraction holds.** Gate G8 checks that every registered `CellRenderer` satisfies §3. Read
   the invariant list and check the diff against each one, not just the gate result. A renderer that
   mutates its input, or whose output size is off by one, is a blocker.
4. **No abstraction leak.** Does `lattice_core` reference an application? Does an application import
   from another application? That is an E8 deviation and a blocker.
5. **No host coupling.** Does the application still work with no ArtCraft running? A missing token
   file, a refused connection or an absent host must be a normal state. That is an E9 deviation and a
   blocker.
6. **Test quality.** Do the tests actually fail on the old code? A test that passes before and after
   the change proves nothing. Look for assertions that restate the implementation, tests that would
   pass with the feature removed, and missing edge cases named in `accept`.
7. **Correctness of the maths.** For renderer and effect cards, check the formulas against the
   contract, not against intuition. Off-by-one in a kernel, a missing normalisation, a wrong colour
   space, a mask applied in the wrong order.
8. **Product quality** (cards L10, L12, L20, L21 only). Is the control discoverable? Does the default
   surprise? Does the message say what to do next? A task can pass every test and still be an E7.
9. **Hygiene.** File length, function length, typing, docstrings, no dead code, no commented-out
   blocks, no debug prints.

SEVERITY
- **blocker**: wrong result, contract violation, regression, crash, data loss, abstraction leak,
  host coupling.
- **major**: missing acceptance item, test that cannot fail, wrong default, misleading message.
- **minor**: style, naming, a docstring that lies.

VERDICT
- `PASS` — no blocker, no major. Minors are listed but do not block.
- `FIX` — at least one blocker or major. The coder gets one more cycle with your findings.
- `ESCALATE` — the task cannot be done as specified, or the fix needs a contract change. Name the
  deviation class (E2, E4, E6, E7, E8, E9).

OUTPUT FORMAT, nothing else:
```json
{
  "verdict": "PASS | FIX | ESCALATE",
  "findings": [
    {"severity": "blocker|major|minor", "file": "...", "line": 0,
     "what": "...", "why": "...", "fix": "..."}
  ],
  "regression": "none | <what changed vs the frozen behaviour>",
  "renderer_invariants": "all six hold | <which one fails and how>",
  "tests_that_cannot_fail": ["..."],
  "notes": "<≤ 5 lines>"
}
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

TASK CARD

### L-UI · Shared widgets, extracted from Lattice Dither (S5)
- wave: 0 · deps: L1 · executor: OMH capable · review: full · size: L
- owns: `lattice_core/ui/**`, `tests/test_ui_shared.py`, moves from `lattice_dither/ui/**`
- context: §2 (`lattice_core/ui/`), REVUE-PRODUIT (bloquants 1-2 de l'analyse Dither, S5)
- spec: implement §2 `ui/` as code, decided 2026-11-16. Extract from Lattice Dither the shared
  widgets into `lattice_core/ui/`: preview canvas + progress worker + before/after split,
  Looks grid (thumbnails rendered on the current image), one full-resolution export dialog
  (PNG/SVG/GIF — never the 1024 px preview proxy), bridge status dot, empty state. Fix first
  the two blocker findings of the Dither product review: (a) exported images must render at
  full resolution, (b) the preset indicator must be honest (applies the real preset, updates
  on change, absent when no image is loaded). Both apps (L12/L20) consume these widgets;
  they must not reimplement a canvas or an export dialog.
- accept:
  - `lattice_core/ui` imports no application module; apps import it under the `[ui]` extra.
  - the export dialog renders the pipeline at full resolution (not the preview proxy) and
    the resulting file matches the pipeline output size.
  - the preset indicator shows the actually-applied preset, updates after any pipeline
    change, and is hidden without an image.
  - canvas + worker + split, Looks grid, bridge status dot and empty state exist as widgets
    with tests (offscreen), each consumed by a smoke test.
  - no test regression: the full suite still passes (1216 baseline).

---

## Wave 1 — glyphs

GATE RESULTS (L-UI, attempt 1 — deepseek-v4-flash-0731)
- Owned tests : **27/27 verts** (offscreen, ruff clean). Tests UI de l'app : **101/101** —
  zéro régression app. test_core_packaging (aligné DEV-209) : vert.
- Suite complète : 1474 passed, 1 skipped, **1 failed** : test_cell.py::test_list_renderers_returns_pixel
  — attend ["pixel"], reçoit les renderers de L6/L8 encore en vol (modifié-non-committé par
  eux) ; preuve d'indépendance fournie par le codeur (même échec sans ses fichiers) — sera
  aligné par l'orchestrateur quand L6/L8 atterrissent (test L2 périmé, DEV-211 en cours).
- G9 : l'export utilise le même `render(source, spec)` que le CLI → octets identiques par
  construction. G7/G8 : inchangés (aucun renderer/témoin modifié ; la suite UI de l'app verte
  le confirme).

REVUE PRODUIT — les 2 bloquants Dither à corriger (cité dans la carte) :
1) export avancé (SVG/impression/GIF/vidéo) sur l'aperçu plafonné à 1024 px au lieu d'un rendu
   pleine résolution ; 2) l'indicateur « Préréglage 1/12 : 01_gameboy.json » ment dans les cinq
   états (affiché sans image, figé après changement). Le 3e (GIF/vidéo mono-image) = L-LOOP.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/ui/__init__.py b/lattice_core/ui/__init__.py
new file mode 100644
index 0000000..8fc76bc
--- /dev/null
+++ b/lattice_core/ui/__init__.py
@@ -0,0 +1,53 @@
+"""Shared Qt widgets of the Lattice suite (imported only under the ``[ui]`` extra).
+
+This package is owned by card L-UI and hosts the widgets every application
+reuses instead of reimplementing: the preview canvas with its render worker,
+the Looks grid, the full-resolution export dialog, the bridge status dot, the
+preset indicator and the empty state. It never imports an application module;
+applications import it under ``lattice-core[ui]``.
+"""
+
+from __future__ import annotations
+
+from lattice_core.ui.bridge import BridgeStatusDot, ConnectionProbe
+from lattice_core.ui.canvas import MODES, Mode, PreviewCanvas
+from lattice_core.ui.empty import EmptyState
+from lattice_core.ui.export_dialog import ExportDialog, ExportError, run_export_dialog
+from lattice_core.ui.looks import Look, LookCell, LookGallery
+from lattice_core.ui.preset_indicator import PresetIndicator
+from lattice_core.ui.worker import (
+    MAX_SOURCE_SIDE,
+    PREVIEW_MAX_SIDE,
+    PREVIEW_STAGES,
+    PreviewResult,
+    RenderResult,
+    RenderWorker,
+    oversize_message,
+    preview_proxy,
+    proxy_factor,
+)
+
+__all__ = [
+    "BridgeStatusDot",
+    "ConnectionProbe",
+    "EmptyState",
+    "ExportDialog",
+    "ExportError",
+    "Look",
+    "LookCell",
+    "LookGallery",
+    "MAX_SOURCE_SIDE",
+    "MODES",
+    "Mode",
+    "PREVIEW_MAX_SIDE",
+    "PREVIEW_STAGES",
+    "PresetIndicator",
+    "PreviewCanvas",
+    "PreviewResult",
+    "RenderResult",
+    "RenderWorker",
+    "oversize_message",
+    "preview_proxy",
+    "proxy_factor",
+    "run_export_dialog",
+]
diff --git a/lattice_core/ui/bridge.py b/lattice_core/ui/bridge.py
new file mode 100644
index 0000000..94b34eb
--- /dev/null
+++ b/lattice_core/ui/bridge.py
@@ -0,0 +1,179 @@
+"""Shared bridge status dot: live ArtCraft reachability as a small widget.
+
+The dot probes ``ArtCraftClient.discover`` on a helper thread so a slow or
+refused connection never blocks the GUI. A missing host is a normal state:
+every application must work standalone, and the dot simply shows orange.
+"""
+
+from __future__ import annotations
+
+import logging
+import threading
+from collections.abc import Callable
+from typing import Literal
+
+from PySide6.QtCore import QObject, Qt, Signal, Slot
+from PySide6.QtGui import QColor, QPainter, QPaintEvent
+from PySide6.QtWidgets import QWidget
+
+from lattice_core.bridge import ArtCraftClient
+from lattice_core.bridge.designcraft import CONTROL_PORT as DESIGNCRAFT_PORT
+from lattice_core.bridge.photocraft import CONTROL_PORT as PHOTOCRAFT_PORT
+
+LOGGER = logging.getLogger(__name__)
+
+CONNECTED = "connected"
+DISCONNECTED = "disconnected"
+UNKNOWN = "unknown"
+STATES: tuple[str, ...] = (CONNECTED, DISCONNECTED, UNKNOWN)
+PROBE_JOIN_MS = 250
+HOSTS = ("photocraft", "designcraft")
+DEFAULT_PORT: dict[str, int | None] = {
+    "photocraft": PHOTOCRAFT_PORT,
+    "designcraft": DESIGNCRAFT_PORT,
+}
+_STATE_COLOURS = {
+    CONNECTED: QColor(70, 190, 90),
+    DISCONNECTED: QColor(210, 70, 70),
+    UNKNOWN: QColor(220, 160, 50),
+}
+_STATE_TIPS = {
+    CONNECTED: "Connected",
+    DISCONNECTED: "Disconnected",
+    UNKNOWN: "Unknown",
+}
+HostName = Literal["photocraft", "designcraft"]
+Discover = Callable[[HostName, int | None], ArtCraftClient | None]
+
+
+class ConnectionProbe(QObject):
+    """Runs one discover() on a helper thread so a slow probe never blocks the GUI."""
+
+    state_changed = Signal(str)
+
+    def __init__(
+        self,
+        discover: Discover = ArtCraftClient.discover,
+        parent: QObject | None = None,
+    ) -> None:
+        super().__init__(parent)
+        self._discover = discover
+        self._host: HostName = "photocraft"
+        self._port: int | None = None
+        self._lock = threading.Lock()
+        self._thread: threading.Thread | None = None
+        self._stopped = False
+
+    def check(self) -> None:
+        """Start one discover() probe unless the previous one is still running."""
+        with self._lock:
+            if self._stopped or (self._thread is not None and self._thread.is_alive()):
+                return
+            self._thread = threading.Thread(
+                target=self._run, name="artcraft-probe", daemon=True
+            )
+            self._thread.start()
+
+    def stop(self) -> None:
+        """Stop emitting probe results and wait briefly for the running probe."""
+        with self._lock:
+            self._stopped = True
+            thread = self._thread
+        if thread is not None:
+            thread.join(PROBE_JOIN_MS / 1000.0)
+
+    def _run(self) -> None:
+        """Probe the host and emit the resulting connection state."""
+        try:
+            client = self._discover(self._host, self._port)
+        except Exception:  # noqa: BLE001 - a probe must never raise
+            LOGGER.exception("ArtCraft discovery failed")
+            client = None
+        if not self._stopped:
+            self.state_changed.emit(CONNECTED if client is not None else DISCONNECTED)
+
+    def set_host(self, host: HostName, port: int | None = None) -> None:
+        """Set the host probed by the next check() call."""
+        if host not in HOSTS:
+            raise ValueError(f"unknown ArtCraft host {host!r}; expected one of {HOSTS}")
+        self._host = host
+        self._port = DEFAULT_PORT[host] if port is None else port
+
+
+class BridgeStatusDot(QWidget):
+    """A coloured dot showing the reachability of one ArtCraft host."""
+
+    state_changed = Signal(str)
+
+    def __init__(
+        self,
+        host: HostName = "photocraft",
+        parent: QWidget | None = None,
+        *,
+        port: int | None = None,
+        discover: Discover = ArtCraftClient.discover,
+        diameter: int = 12,
+    ) -> None:
+        super().__init__(parent)
+        self.setObjectName("bridge_status_dot")
+        self._diameter = int(diameter)
+        self.setFixedSize(self._diameter, self._diameter)
+        self._state = UNKNOWN
+        self.probe = ConnectionProbe(discover, self)
+        self.probe.set_host(host, port)
+        self.probe.state_changed.connect(self.set_state)
+        self.probe.state_changed.connect(self.state_changed)
+        self._update_tip()
+
+    def host(self) -> str:
+        """Return the host this dot probes."""
+        return self.probe._host
+
+    def set_host(self, host: HostName, port: int | None = None) -> None:
+        """Retarget the dot at another host; the next check() probes it."""
+        self.probe.set_host(host, port)
+        self.set_state(UNKNOWN)
+        self.check()
+
+    def state(self) -> str:
+        """Return the current state: connected, disconnected or unknown."""
+        return self._state
+
+    def set_state(self, state: str) -> None:
+        """Set the displayed state and repaint the dot."""
+        if state not in STATES:
+            raise ValueError(f"unknown bridge state {state!r}")
+        self._state = state
+        self._update_tip()
+        self.update()
+
+    @Slot()
+    def check(self) -> None:
+        """Start one asynchronous probe; the dot updates when the probe answers."""
+        self.probe.check()
+
+    def start(self) -> None:
+        """Probe now; scheduling belongs to the owning application."""
+        self.check()
+
+    def stop(self) -> None:
+        """Stop the probe thread; safe to call more than once."""
+        self.probe.stop()
+
+    def _update_tip(self) -> None:
+        """Refresh the tooltip with the state and the probed host."""
+        self.setToolTip(f"{_STATE_TIPS[self._state]} ({self.probe._host})")
+
+    def paintEvent(self, event: QPaintEvent) -> None:
+        """Draw the state colour as a filled circle."""
+        painter = QPainter(self)
+        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
+        radius = self._diameter / 2.0
+        painter.setBrush(_STATE_COLOURS[self._state])
+        painter.setPen(Qt.PenStyle.NoPen)
+        painter.drawEllipse(0.0, 0.0, radius * 2.0, radius * 2.0)
+        painter.end()
+        super().paintEvent(event)
+
+
+__all__ = ["BridgeStatusDot", "ConnectionProbe", "CONNECTED", "DISCONNECTED", "UNKNOWN"]
diff --git a/lattice_core/ui/canvas.py b/lattice_core/ui/canvas.py
new file mode 100644
index 0000000..0c5cb01
--- /dev/null
+++ b/lattice_core/ui/canvas.py
@@ -0,0 +1,244 @@
+"""Shared preview canvas with nearest-neighbour display and before/after/split modes."""
+
+from __future__ import annotations
+
+from typing import Literal
+
+import numpy as np
+from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
+from PySide6.QtGui import (
+    QColor,
+    QImage,
+    QMouseEvent,
+    QPainter,
+    QPen,
+    QPixmap,
+    QTransform,
+    QWheelEvent,
+)
+from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget
+
+from lattice_core.types import RGB8
+
+Mode = Literal["after", "before", "split"]
+
+MODES: tuple[str, ...] = ("after", "before", "split")
+MIN_ZOOM = 0.01
+MAX_ZOOM = 32.0
+WHEEL_STEP = 1.25
+FIT_MARGIN = 2.0
+
+
+def _as_rgb8(rgb8: RGB8) -> RGB8:
+    """Validate an RGB8 array and return it as a contiguous uint8 (H, W, 3) array."""
+    array = np.asarray(rgb8)
+    if array.ndim != 3 or array.shape[2] != 3:
+        raise ValueError(f"expected an (H, W, 3) array, got shape {array.shape}")
+    if array.dtype != np.uint8:
+        if array.dtype.kind not in "iu":
+            raise ValueError(f"expected a uint8 array, got dtype {array.dtype}")
+        array = np.clip(array, 0, 255).astype(np.uint8)
+    return np.ascontiguousarray(array)
+
+
+def _pixels(image: QImage) -> np.ndarray:
+    """Return a writable (height, bytesPerLine) uint8 view of the image pixels."""
+    height = image.height()
+    return np.frombuffer(image.bits(), dtype=np.uint8).reshape(height, image.bytesPerLine())
+
+
+class PreviewCanvas(QGraphicsView):
+    """Zoomable, pannable preview of the rendered image with a split view."""
+
+    zoom_changed = Signal(float)
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        super().__init__(parent)
+        self._scene = QGraphicsScene(self)
+        self.setScene(self._scene)
+        self._item = QGraphicsPixmapItem()
+        self._item.setTransformationMode(Qt.TransformationMode.FastTransformation)
+        self._scene.addItem(self._item)
+        self._after: RGB8 | None = None
+        self._before: RGB8 | None = None
+        self._buffer: QImage | None = None
+        self._mode: Mode = "after"
+        self._zoom = 1.0
+        self._fitted = True
+        self._panning = False
+        self._pan_origin = QPoint()
+        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
+        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
+        self.setDragMode(QGraphicsView.DragMode.NoDrag)
+        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
+        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
+        self.setBackgroundBrush(QColor(32, 32, 34))
+        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.setFrameShape(QGraphicsView.Shape.NoFrame)
+
+    def set_image(self, rgb8: RGB8) -> None:
+        """Set the rendered (after) image and refresh the display."""
+        previous = None if self._after is None else self._after.shape
+        self._after = _as_rgb8(rgb8)
+        self._refresh()
+        if previous is None or (self._fitted and self._after.shape != previous):
+            self.zoom_fit()
+
+    def set_original(self, rgb8: RGB8 | None) -> None:
+        """Set the source (before) image, or None to clear it."""
+        self._before = None if rgb8 is None else _as_rgb8(rgb8)
+        self._refresh()
+
+    def set_mode(self, mode: Mode) -> None:
+        """Switch the preview between the after, before and split views."""
+        if mode not in MODES:
+            raise ValueError(f"unknown mode {mode!r}")
+        self._mode = mode
+        self._refresh()
+        self.viewport().update()
+
+    def mode(self) -> Mode:
+        """Return the active preview mode."""
+        return self._mode
+
+    def qimage(self) -> QImage | None:
+        """Return the QImage buffer the canvas displays, or None when it is empty."""
+        return self._buffer
+
+    def zoom(self) -> float:
+        """Return the current zoom factor (1.0 is one image pixel per screen pixel)."""
+        return self._zoom
+
+    def set_zoom(self, f: float) -> None:
+        """Set the zoom factor, clamped to the supported range."""
+        factor = float(min(max(float(f), MIN_ZOOM), MAX_ZOOM))
+        self._zoom = factor
+        self._fitted = False
+        self.setTransform(QTransform().scale(factor, factor))
+        self.zoom_changed.emit(factor)
+
+    def zoom_fit(self) -> None:
+        """Scale the image so that it fits entirely inside the viewport."""
+        rect = self._scene.sceneRect()
+        if rect.isEmpty():
+            return
+        viewport = self.viewport().size()
+        scale_x = (viewport.width() - FIT_MARGIN) / rect.width()
+        scale_y = (viewport.height() - FIT_MARGIN) / rect.height()
+        self.set_zoom(min(scale_x, scale_y))
+        self._fitted = True
+
+    def _refresh(self) -> None:
+        """Rebuild the displayed pixmap from the current images and mode."""
+        after = self._after
+        if after is None:
+            self._item.setPixmap(QPixmap())
+            self._scene.setSceneRect(QRectF())
+            return
+        self._compose(after)
+        pixmap = QPixmap.fromImage(self._buffer)
+        self._item.setPixmap(pixmap)
+        self._scene.setSceneRect(QRectF(pixmap.rect()))
+
+    def _compose(self, after: RGB8) -> None:
+        """Write the image matching the current mode into the display buffer."""
+        before = self._before
+        paired = before is not None and before.shape == after.shape
+        if paired and self._mode == "before":
+            self._blit(before)
+            return
+        self._blit(after)
+        if paired and self._mode == "split":
+            self._blit_left(before)
+
+    def _blit(self, rgb8: RGB8) -> None:
+        """Copy rgb8 into the display buffer, reallocating it only when the shape changes."""
+        height, width = rgb8.shape[:2]
+        buffer = self._buffer
+        if buffer is None or buffer.width() != width or buffer.height() != height:
+            buffer = QImage(width, height, QImage.Format.Format_RGB888)
+            self._buffer = buffer
+        view = _pixels(buffer)
+        view[:, : width * 3] = rgb8.reshape(height, width * 3)
+        if view.shape[1] > width * 3:
+            view[:, width * 3 :] = 0
+
+    def _blit_left(self, rgb8: RGB8) -> None:
+        """Copy the left half of rgb8 into the display buffer."""
+        buffer = self._buffer
+        if buffer is None:
+            return
+        height, width = rgb8.shape[:2]
+        half = (width // 2) * 3
+        _pixels(buffer)[:, :half] = rgb8.reshape(height, width * 3)[:, :half]
+
+    def wheelEvent(self, event: QWheelEvent) -> None:
+        """Zoom around the cursor with the mouse wheel."""
+        delta = event.angleDelta().y()
+        if delta == 0:
+            event.ignore()
+            return
+        factor = WHEEL_STEP if delta > 0 else 1.0 / WHEEL_STEP
+        self.zoom_around(event.position(), self._zoom * factor)
+        event.accept()
+
+    def zoom_around(self, position: QPointF, f: float) -> None:
+        """Set the zoom factor while keeping the scene point under position fixed."""
+        anchor = self.mapToScene(position.toPoint())
+        self.set_zoom(f)
+        offset = self.mapFromScene(anchor) - position.toPoint()
+        horizontal = self.horizontalScrollBar()
+        vertical = self.verticalScrollBar()
+        horizontal.setValue(horizontal.value() + offset.x())
+        vertical.setValue(vertical.value() + offset.y())
+
+    def mousePressEvent(self, event: QMouseEvent) -> None:
+        """Start panning on a left or middle button press."""
+        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
+            self._panning = True
+            self._pan_origin = event.position().toPoint()
+            self.setCursor(Qt.CursorShape.ClosedHandCursor)
+            event.accept()
+            return
+        super().mousePressEvent(event)
+
+    def mouseMoveEvent(self, event: QMouseEvent) -> None:
+        """Scroll the view while a pan drag is active."""
+        if self._panning:
+            position = event.position().toPoint()
+            delta = position - self._pan_origin
+            self._pan_origin = position
+            horizontal = self.horizontalScrollBar()
+            vertical = self.verticalScrollBar()
+            horizontal.setValue(horizontal.value() - delta.x())
+            vertical.setValue(vertical.value() - delta.y())
+            event.accept()
+            return
+        super().mouseMoveEvent(event)
+
+    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
+        """Finish panning when the drag button is released."""
+        if self._panning and event.button() in (
+            Qt.MouseButton.LeftButton,
+            Qt.MouseButton.MiddleButton,
+        ):
+            self._panning = False
+            self.unsetCursor()
+            event.accept()
+            return
+        super().mouseReleaseEvent(event)
+
+    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
+        """Draw the divider line of the split view."""
+        super().drawForeground(painter, rect)
+        after = self._after
+        before = self._before
+        if self._mode != "split" or after is None or before is None:
+            return
+        if before.shape != after.shape:
+            return
+        x = float(after.shape[1] // 2)
+        painter.save()
+        painter.setPen(QPen(QColor(255, 255, 255, 180), 0))
+        painter.drawLine(QPointF(x, 0.0), QPointF(x, float(after.shape[0])))
+        painter.restore()
diff --git a/lattice_core/ui/empty.py b/lattice_core/ui/empty.py
new file mode 100644
index 0000000..bc36fa6
--- /dev/null
+++ b/lattice_core/ui/empty.py
@@ -0,0 +1,35 @@
+"""Shared empty state: the guidance shown while no image is loaded."""
+
+from __future__ import annotations
+
+from PySide6.QtCore import Qt
+from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
+
+DEFAULT_TEXT = "Open an image to start."
+
+
+class EmptyState(QWidget):
+    """A centred placeholder telling the user what to do with an empty workspace."""
+
+    def __init__(self, text: str | None = None, parent: QWidget | None = None) -> None:
+        super().__init__(parent)
+        self.setObjectName("empty_state")
+        self.label = QLabel(text if text is not None else DEFAULT_TEXT, self)
+        self.label.setObjectName("empty_state_text")
+        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.label.setWordWrap(True)
+        layout = QVBoxLayout(self)
+        layout.addStretch(1)
+        layout.addWidget(self.label)
+        layout.addStretch(1)
+
+    def set_message(self, text: str) -> None:
+        """Replace the guidance text."""
+        self.label.setText(text)
+
+    def message(self) -> str:
+        """Return the current guidance text."""
+        return self.label.text()
+
+
+__all__ = ["DEFAULT_TEXT", "EmptyState"]
diff --git a/lattice_core/ui/export_dialog.py b/lattice_core/ui/export_dialog.py
new file mode 100644
index 0000000..0556682
--- /dev/null
+++ b/lattice_core/ui/export_dialog.py
@@ -0,0 +1,207 @@
+"""Shared full-resolution export dialog (PNG/SVG/GIF).
+
+The Dither product review blocker was that the advanced export ran on the
+1024 px preview proxy. This dialog fixes that contract: it owns the render. It
+is handed the source image and the pipeline spec, renders the pipeline at FULL
+resolution (no ``max_side``) on export, and only then writes the file, so the
+file always matches the pipeline output size. The render callable can be
+injected for worker-thread rendering in an application shell.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+from pathlib import Path
+
+import numpy as np
+from PySide6.QtCore import QSettings
+from PySide6.QtWidgets import (
+    QComboBox,
+    QDialog,
+    QDialogButtonBox,
+    QFileDialog,
+    QFormLayout,
+    QHBoxLayout,
+    QLabel,
+    QLineEdit,
+    QPushButton,
+    QSpinBox,
+    QVBoxLayout,
+    QWidget,
+)
+
+from lattice_core import color
+from lattice_core.pipeline import PipelineSpec, render
+from lattice_core.types import RGB8, Image
+from lattice_core.ui.svg import write_svg
+
+EXPORT_DIR_KEY = "export_dir"
+REPORT_SEPARATOR = "\n"
+FORMATS: tuple[str, ...] = ("png", "svg", "gif")
+FORMAT_LABELS = {"png": "PNG", "svg": "SVG", "gif": "GIF"}
+FORMAT_SUFFIX = {"png": ".png", "svg": ".svg", "gif": ".gif"}
+FORMAT_FILTER = {
+    "png": "PNG images (*.png);;All files (*)",
+    "svg": "SVG images (*.svg);;All files (*)",
+    "gif": "GIF images (*.gif);;All files (*)",
+}
+DEFAULT_CELL = 1
+MAX_CELL = 64
+DEFAULT_PATH_NAME = "export"
+RENDER = Callable[[PipelineSpec], RGB8]
+
+
+class ExportError(Exception):
+    """An export that could not be written: no output path, or a render failure."""
+
+
+class ExportDialog(QDialog):
+    """Dialog that renders the pipeline at full resolution and writes it as PNG, SVG or GIF."""
+
+    def __init__(
+        self,
+        source: Image,
+        spec: PipelineSpec,
+        parent: QWidget | None = None,
+        *,
+        render_full: RENDER | None = None,
+        settings: QSettings | None = None,
+    ) -> None:
+        super().__init__(parent)
+        self.setWindowTitle("Export")
+        self.source = np.ascontiguousarray(source, dtype=np.float32)
+        self.spec = spec
+        self._render_full = render_full if render_full is not None else self._default_render
+        self.written: list[Path] = []
+        self._settings = settings or QSettings()
+        self._build()
+        self._load_defaults()
+
+    def _build(self) -> None:
+        """Create the format selector, the option pages, the path row and the buttons."""
+        self.format_box = QComboBox(self)
+        self.format_box.setObjectName("export_format")
+        for key in FORMATS:
+            self.format_box.addItem(FORMAT_LABELS[key], key)
+        self.stack = QWidget(self)
+        self._build_svg_page(self.stack)
+        self.path_edit = QLineEdit(self)
+        self.path_edit.setObjectName("export_path")
+        browse = QPushButton("Browse…", self)
+        browse.setObjectName("export_browse")
+        browse.clicked.connect(self._on_browse)
+        row = QHBoxLayout()
+        row.addWidget(self.path_edit)
+        row.addWidget(browse)
+        self.report = QLabel(self)
+        self.report.setObjectName("export_report")
+        self.report.setWordWrap(True)
+        self.buttons = QDialogButtonBox(
+            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close, self
+        )
+        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Export")
+        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Close")
+        self.buttons.accepted.connect(self._on_export)
+        self.buttons.rejected.connect(self.reject)
+        layout = QVBoxLayout(self)
+        layout.addWidget(self.format_box)
+        layout.addWidget(self.stack)
+        layout.addLayout(row)
+        layout.addWidget(self.report)
+        layout.addWidget(self.buttons)
+
+    def _build_svg_page(self, page: QWidget) -> None:
+        """Create the SVG page: cell size and background colour."""
+        self.cell = QSpinBox(page)
+        self.cell.setObjectName("export_cell")
+        self.cell.setRange(1, MAX_CELL)
+        self.cell.setValue(DEFAULT_CELL)
+        self.background_edit = QLineEdit(page)
+        self.background_edit.setObjectName("export_background")
+        self.background_edit.setPlaceholderText("#RRGGBB, empty for transparent")
+        form = QFormLayout(page)
+        form.addRow("Cell size", self.cell)
+        form.addRow("Background", self.background_edit)
+
+    def format(self) -> str:
+        """Return the selected format key: png, svg or gif."""
+        return str(self.format_box.currentData())
+
+    def export_directory(self) -> Path:
+        """Return the remembered export directory, or the home directory."""
+        stored = self._settings.value(EXPORT_DIR_KEY)
+        return Path(stored) if stored else Path.home()
+
+    def target_path(self) -> Path:
+        """Return the output path typed in the dialog, with the format's suffix."""
+        text = self.path_edit.text().strip()
+        if not text:
+            raise ExportError("Choose an output file first.")
+        path = Path(text)
+        return path if path.suffix else path.with_suffix(FORMAT_SUFFIX[self.format()])
+
+    def background(self) -> str | None:
+        """Return the SVG background colour, or None when the field is empty."""
+        return self.background_edit.text().strip() or None
+
+    def _default_render(self, spec: PipelineSpec) -> RGB8:
+        """Render spec at full resolution; the preview proxy is never used here."""
+        return render(self.source, spec)
+
+    def export_now(self) -> list[Path]:
+        """Render at full resolution, write the file and return the paths written."""
+        target = self.target_path()
+        target.parent.mkdir(parents=True, exist_ok=True)
+        self.report.setText("Rendering at full resolution…")
+        image = self._render_full(self.spec)
+        written = self._write(image, target)
+        self.written = written
+        self._settings.setValue(EXPORT_DIR_KEY, str(target.parent))
+        self.report.setText(REPORT_SEPARATOR.join(f"Exported {path.name}" for path in written))
+        return written
+
+    def _write(self, image: RGB8, target: Path) -> list[Path]:
+        """Write the selected format to target and return every file created."""
+        kind = self.format()
+        if kind == "svg":
+            write_svg(image, target, cell=self.cell.value(), background=self.background())
+        else:
+            color.to_pil(image).save(target, format="PNG" if kind == "png" else "GIF")
+        return [target]
+
+    def _on_export(self) -> None:
+        """Export with the current options and report the outcome in the dialog."""
+        try:
+            self.export_now()
+        except (ExportError, OSError, ValueError) as exc:
+            self.report.setText(str(exc))
+
+    def _on_browse(self) -> None:
+        """Ask for an output path with the selected format's filter."""
+        current = self.path_edit.text().strip() or str(self.export_directory())
+        path, _ = QFileDialog.getSaveFileName(
+            self, "Export", current, FORMAT_FILTER[self.format()]
+        )
+        if path:
+            self.path_edit.setText(path)
+
+    def _load_defaults(self) -> None:
+        """Point the path field at the remembered directory and the format's suffix."""
+        suffix = FORMAT_SUFFIX[self.format()]
+        self.path_edit.setText(str(self.export_directory() / f"{DEFAULT_PATH_NAME}{suffix}"))
+
+
+def run_export_dialog(
+    source: Image,
+    spec: PipelineSpec,
+    parent: QWidget | None = None,
+    *,
+    render_full: RENDER | None = None,
+) -> list[Path]:
+    """Show the export dialog for source and spec and return every file written."""
+    dialog = ExportDialog(source, spec, parent, render_full=render_full)
+    dialog.exec()
+    return dialog.written
+
+
+__all__ = ["ExportDialog", "ExportError", "FORMATS", "run_export_dialog"]
diff --git a/lattice_core/ui/looks.py b/lattice_core/ui/looks.py
new file mode 100644
index 0000000..f85a2f2
--- /dev/null
+++ b/lattice_core/ui/looks.py
@@ -0,0 +1,297 @@
+"""Shared Looks grid: one thumbnail per look, rendered on the current image.
+
+A "look" is a named pipeline variant. Thumbnails are rendered on a helper
+thread from the current source, so every thumbnail shows what that look does to
+the image that is actually loaded. The gallery keeps an in-memory cache keyed
+by look id, cleared whenever the source changes.
+"""
+
+from __future__ import annotations
+
+import logging
+from collections.abc import Sequence
+from dataclasses import dataclass
+
+import numpy as np
+from PIL import Image as PILImage
+from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
+from PySide6.QtGui import QCloseEvent, QColor, QImage, QMouseEvent, QPixmap
+from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget
+
+from lattice_core import color
+from lattice_core.pipeline import PipelineSpec, render
+from lattice_core.types import RGB8, Image
+from lattice_core.ui.worker import _downscale_strips, proxy_factor
+
+LOGGER = logging.getLogger(__name__)
+
+THUMB_SIZE = 96
+THUMB_COLUMNS = 4
+THUMB_SOURCE_SIDE = 512
+PLACEHOLDER_COLOR = "#2a2a30"
+JOIN_MS = 2000
+FAILED_TIP = "{name}: {message}"
+
+
+@dataclass(frozen=True)
+class Look:
+    """One named pipeline variant shown in the Looks grid."""
+
+    id: str
+    name: str
+    spec: PipelineSpec
+
+
+def _resize(rgb8: RGB8, size: int) -> RGB8:
+    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
+    if rgb8.shape[:2] == (size, size):
+        return np.ascontiguousarray(rgb8, dtype=np.uint8)
+    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
+    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
+
+
+def render_look_thumbnail(look: Look, source: Image, size: int = THUMB_SIZE) -> RGB8:
+    """Render look on the source proxy and return a size×size thumbnail."""
+    proxy = color.to_rgb8(_downscale_strips(source, proxy_factor(source, THUMB_SOURCE_SIDE)))
+    return _resize(color.to_rgb8(render(proxy, look.spec)), size)
+
+
+def _pixmap(rgb8: RGB8) -> QPixmap:
+    """Return a QPixmap copy of a uint8 RGB array."""
+    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
+    # QImage wraps the buffer instead of copying it, so the bytes must outlive the image.
+    buffer = data.tobytes()
+    image = QImage(buffer, data.shape[1], data.shape[0], QImage.Format.Format_RGB888)
+    return QPixmap.fromImage(image)
+
+
+class LookThumbnailWorker(QObject):
+    """Renders look thumbnails on a helper thread and reports them by signal."""
+
+    thumbnail_ready = Signal(str, object)
+    failed = Signal(str, str)
+
+    def __init__(self, size: int = THUMB_SIZE) -> None:
+        super().__init__()
+        self._size = int(size)
+
+    @Slot(str, object, object)
+    def build(self, look_id: str, spec: PipelineSpec, source: Image) -> None:
+        """Render one thumbnail and emit it; this slot never touches a widget."""
+        try:
+            rgb8 = render_look_thumbnail(Look(look_id, "", spec), source, self._size)
+        except Exception as exc:  # noqa: BLE001 - one broken look must not stop the rest
+            LOGGER.exception("look %s failed", look_id)
+            self.failed.emit(look_id, str(exc))
+            return
+        self.thumbnail_ready.emit(look_id, rgb8)
+
+
+_ACTIVE_WORKERS: set[LookThumbnailWorker] = set()
+# A QThread that outlived its join timeout must not be destroyed while it still runs.
+_ORPHAN_THREADS: set[QThread] = set()
+
+
+def _release_worker(gallery: LookGallery, worker: LookThumbnailWorker) -> None:
+    """Drop every reference the gallery and this module keep to a stopped worker.
+
+    Without this the worker stays in ``_ACTIVE_WORKERS`` and its signal
+    connections keep the gallery, and through it the whole window, alive.
+    """
+    worker.thumbnail_ready.disconnect(gallery._on_thumbnail_ready)
+    worker.failed.disconnect(gallery._on_thumbnail_failed)
+    gallery._request.disconnect(worker.build)
+    _ACTIVE_WORKERS.discard(worker)
+
+
+class LookCell(QWidget):
+    """One gallery cell: a thumbnail above the look name."""
+
+    clicked = Signal(str)
+
+    def __init__(self, look: Look, size: int = THUMB_SIZE, parent: QWidget | None = None) -> None:
+        super().__init__(parent)
+        self.look_id = look.id
+        self.setObjectName(f"look_cell_{look.id}")
+        self.setToolTip(look.name)
+        self.image_label = QLabel(self)
+        self.image_label.setObjectName("look_thumb")
+        self.image_label.setFixedSize(size, size)
+        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.name_label = QLabel(look.name, self)
+        self.name_label.setObjectName("look_name")
+        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.name_label.setWordWrap(True)
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(4, 4, 4, 4)
+        layout.setSpacing(2)
+        layout.addWidget(self.image_label)
+        layout.addWidget(self.name_label)
+        self._placeholder = QPixmap(size, size)
+        self._placeholder.fill(QColor(PLACEHOLDER_COLOR))
+        self._ready = False
+        self.show_placeholder()
+
+    def has_thumbnail(self) -> bool:
+        """Return True once a rendered thumbnail has replaced the placeholder."""
+        return self._ready
+
+    def show_placeholder(self) -> None:
+        """Show the neutral placeholder instead of a thumbnail."""
+        self.image_label.setPixmap(self._placeholder)
+        self._ready = False
+
+    def set_thumbnail(self, rgb8: RGB8) -> None:
+        """Show rgb8 as this cell's thumbnail; call it from the GUI thread only."""
+        self.image_label.setPixmap(_pixmap(rgb8))
+        self._ready = True
+
+    def mousePressEvent(self, event: QMouseEvent) -> None:
+        """Report the look of the cell when it is clicked."""
+        self.clicked.emit(self.look_id)
+        super().mousePressEvent(event)
+
+
+class LookGallery(QWidget):
+    """Grid of look thumbnails rendered on the current image."""
+
+    look_chosen = Signal(str)
+    _request = Signal(str, object, object)
+
+    def __init__(
+        self,
+        parent: QWidget | None = None,
+        *,
+        size: int = THUMB_SIZE,
+        columns: int = THUMB_COLUMNS,
+    ) -> None:
+        super().__init__(parent)
+        self.setObjectName("look_gallery")
+        self._size = int(size)
+        self._columns = max(1, int(columns))
+        self._looks: dict[str, Look] = {}
+        self._cells: list[LookCell] = []
+        self._cache: dict[str, RGB8] = {}
+        self._source: Image | None = None
+        self._thread: QThread | None = None
+        self._worker: LookThumbnailWorker | None = None
+        self.grid = QGridLayout()
+        self.grid.setContentsMargins(0, 0, 0, 0)
+        self.grid.setSpacing(6)
+        outer = QVBoxLayout(self)
+        outer.setContentsMargins(6, 6, 6, 6)
+        outer.addLayout(self.grid)
+        outer.addStretch(1)
+        self._apply_layout("")
+
+    def cells(self) -> list[LookCell]:
+        """Return every cell of the gallery, in the order the looks were set."""
+        return list(self._cells)
+
+    def looks(self) -> list[Look]:
+        """Return the looks of the gallery, in display order."""
+        return [self._looks[cell.look_id] for cell in self._cells]
+
+    def set_looks(self, looks: Sequence[Look]) -> None:
+        """Replace the gallery with looks, in order, and re-queue every thumbnail."""
+        self._clear_cells()
+        for look in looks:
+            self._looks[look.id] = look
+            cell = LookCell(look, self._size, self)
+            cell.clicked.connect(self.look_chosen)
+            self._cells.append(cell)
+        self._apply_layout("")
+        self._queue_thumbnails()
+
+    def set_source(self, image: Image | None) -> None:
+        """Set the current image; every thumbnail is re-rendered on it."""
+        self._source = None if image is None else np.ascontiguousarray(image, dtype=np.float32)
+        self._cache.clear()
+        for cell in self._cells:
+            cell.show_placeholder()
+        self._queue_thumbnails()
+
+    def shutdown(self) -> None:
+        """Stop the helper thread and release its worker; safe to call more than once."""
+        thread, worker = self._thread, self._worker
+        self._thread = self._worker = None
+        if thread is None:
+            return
+        if worker is not None:
+            _release_worker(self, worker)
+        thread.quit()
+        if not thread.wait(JOIN_MS):
+            LOGGER.warning("the look thread did not stop within %d ms", JOIN_MS)
+            _ORPHAN_THREADS.add(thread)
+
+    def closeEvent(self, event: QCloseEvent) -> None:
+        """Stop the helper thread before the widget goes away."""
+        self.shutdown()
+        super().closeEvent(event)
+
+    def _clear_cells(self) -> None:
+        """Delete every cell and empty the grid."""
+        while self.grid.count():
+            widget = self.grid.takeAt(0).widget()
+            if widget is not None:
+                widget.hide()
+                widget.deleteLater()
+        self._cells.clear()
+        self._looks.clear()
+        self._cache.clear()
+
+    def _apply_layout(self, _filter: str) -> None:
+        """Place the cells in the grid, columns per row."""
+        while self.grid.count():
+            self.grid.takeAt(0)
+        for index, cell in enumerate(self._cells):
+            self.grid.addWidget(cell, index // self._columns, index % self._columns)
+
+    def _ensure_worker(self) -> LookThumbnailWorker:
+        """Create the helper thread and its worker on first use."""
+        if self._worker is not None:
+            return self._worker
+        thread = QThread()
+        worker = LookThumbnailWorker(self._size)
+        worker.moveToThread(thread)
+        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
+        worker.failed.connect(self._on_thumbnail_failed)
+        self._request.connect(worker.build)
+        _ACTIVE_WORKERS.add(worker)
+        thread.finished.connect(worker.deleteLater)
+        thread.finished.connect(lambda: _ACTIVE_WORKERS.discard(worker))
+        thread.start()
+        self._thread, self._worker = thread, worker
+        return worker
+
+    def _queue_thumbnails(self) -> None:
+        """Ask the worker for every cell's thumbnail, cache hits included."""
+        source = self._source
+        if not self._cells or source is None:
+            return
+        self._ensure_worker()
+        for cell in self._cells:
+            if cell.look_id in self._cache:
+                cell.set_thumbnail(self._cache[cell.look_id])
+                continue
+            self._request.emit(cell.look_id, self._looks[cell.look_id].spec, source)
+
+    @Slot(str, object)
+    def _on_thumbnail_ready(self, look_id: str, rgb8: object) -> None:
+        """Show a finished thumbnail; this slot runs on the GUI thread."""
+        cell = next((cell for cell in self._cells if cell.look_id == look_id), None)
+        if cell is None:
+            return
+        image = np.ascontiguousarray(np.asarray(rgb8, dtype=np.uint8))
+        self._cache[look_id] = image
+        cell.set_thumbnail(image)
+
+    @Slot(str, str)
+    def _on_thumbnail_failed(self, look_id: str, message: str) -> None:
+        """Keep the placeholder of a cell whose thumbnail could not be rendered."""
+        cell = next((cell for cell in self._cells if cell.look_id == look_id), None)
+        if cell is not None:
+            cell.setToolTip(FAILED_TIP.format(name=cell.look_id, message=message))
+
+
+__all__ = ["Look", "LookCell", "LookGallery", "render_look_thumbnail", "THUMB_SIZE"]
diff --git a/lattice_core/ui/preset_indicator.py b/lattice_core/ui/preset_indicator.py
new file mode 100644
index 0000000..903794c
--- /dev/null
+++ b/lattice_core/ui/preset_indicator.py
@@ -0,0 +1,73 @@
+"""Shared preset indicator: shows the preset that is actually applied.
+
+The Dither product review found the old indicator dishonest: it kept showing
+"Preset 1/12: …" while no image was loaded and after the user changed the
+algorithm or the palette. This widget fixes that contract: the owner tells it
+which preset is applied, marks it modified on every pipeline change, and hides
+it entirely while no image is loaded.
+"""
+
+from __future__ import annotations
+
+from PySide6.QtWidgets import QLabel, QWidget
+
+CUSTOM_TEXT = "Custom"
+MODIFIED_SUFFIX = " (modified)"
+NO_IMAGE_HIDDEN = True
+
+
+class PresetIndicator(QLabel):
+    """Status label for the applied preset: honest, live-updating, image-gated."""
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        super().__init__(parent)
+        self.setObjectName("preset_indicator")
+        self._preset: str | None = None
+        self._modified = False
+        self._image_loaded = False
+        self._refresh()
+
+    def preset_name(self) -> str | None:
+        """Return the name of the applied preset, or None for a custom pipeline."""
+        return self._preset
+
+    def is_modified(self) -> bool:
+        """Return True once the pipeline drifted from the applied preset."""
+        return self._modified
+
+    def is_visible_without_image(self) -> bool:
+        """Return whether the label stays visible while no image is loaded."""
+        return not NO_IMAGE_HIDDEN
+
+    def set_preset(self, name: str | None) -> None:
+        """Record the applied preset (None = custom) and clear the modified flag."""
+        self._preset = None if name is None or not str(name) else str(name)
+        self._modified = False
+        self._refresh()
+
+    def set_modified(self, modified: bool) -> None:
+        """Mark the pipeline as drifted from the applied preset."""
+        self._modified = bool(modified)
+        self._refresh()
+
+    def pipeline_changed(self) -> None:
+        """Record one pipeline change: the applied preset is now modified."""
+        self.set_modified(True)
+
+    def set_image_loaded(self, loaded: bool) -> None:
+        """Show the label only when an image is loaded."""
+        self._image_loaded = bool(loaded)
+        self._refresh()
+
+    def indicator_text(self) -> str:
+        """Return the text the label shows: the applied preset, honestly qualified."""
+        base = self._preset if self._preset is not None else CUSTOM_TEXT
+        return base + (MODIFIED_SUFFIX if self._modified else "")
+
+    def _refresh(self) -> None:
+        """Update the text and the visibility from the current state."""
+        self.setText(self.indicator_text())
+        self.setVisible(self._image_loaded)
+
+
+__all__ = ["CUSTOM_TEXT", "MODIFIED_SUFFIX", "PresetIndicator"]
diff --git a/lattice_core/ui/svg.py b/lattice_core/ui/svg.py
new file mode 100644
index 0000000..bc96b55
--- /dev/null
+++ b/lattice_core/ui/svg.py
@@ -0,0 +1,96 @@
+"""Minimal SVG writer for the shared export dialog (CONTRACT §11, pixel fallback).
+
+Writes one ``<path>`` per distinct colour, each made of horizontal runs, so the
+document stays small and vector. One image pixel becomes ``cell`` units; the
+document size is ``width * cell`` by ``height * cell``, matching the pipeline
+output size exactly at the chosen cell scale. Glyph renderers with ``layout()``
+will drive richer SVG later (card L11); this writer is the always-available
+pixel fallback and never touches an application module.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import numpy as np
+
+from lattice_core.types import RGB8
+
+SVG_NS = "http://www.w3.org/2000/svg"
+_CRISP = 'shape-rendering="crispEdges"'
+_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
+
+
+def _packed_codes(rgb8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
+    """Return the packed 0xRRGGBB codes and the (H, W) index map of rgb8."""
+    array = np.asarray(rgb8)
+    packed = (
+        (array[:, :, 0].astype(np.int32) << 16)
+        | (array[:, :, 1].astype(np.int32) << 8)
+        | array[:, :, 2].astype(np.int32)
+    )
+    codes, inverse = np.unique(packed, return_inverse=True)
+    return codes, inverse.reshape(array.shape[:2])
+
+
+def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Return the (y, x, length) of every horizontal run of True in mask."""
+    height, width = mask.shape
+    padded = np.zeros((height, width + 2), dtype=np.int8)
+    padded[:, 1 : width + 1] = mask
+    ys, xs = np.nonzero(padded[:, 1:] != padded[:, :-1])
+    starts = xs[0::2]
+    return ys[0::2], starts, xs[1::2] - starts
+
+
+def _path_data(ys: np.ndarray, xs: np.ndarray, lengths: np.ndarray, cell: int) -> str:
+    """Return the path data of the runs, one subpath per run."""
+    return "".join(
+        f"M{x * cell} {y * cell}h{length * cell}v{cell}"
+        for x, y, length in zip(xs.tolist(), ys.tolist(), lengths.tolist(), strict=True)
+    )
+
+
+def _check_background(value: str) -> str:
+    """Return value as an uppercase ``#RRGGBB`` string, or raise ValueError."""
+    text = str(value).strip().lstrip("#")
+    if len(text) != 6 or not _HEX_DIGITS.issuperset(text):
+        raise ValueError(f"invalid colour: {value!r}")
+    return "#" + text.upper()
+
+
+def write_svg(
+    rgb8: RGB8, path: Path, *, cell: int = 1, background: str | None = None
+) -> None:
+    """Write rgb8 to path as an SVG with one path element per distinct colour."""
+    array = np.asarray(rgb8)
+    if array.ndim != 3 or array.shape[2] != 3:
+        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
+    if int(cell) < 1:
+        raise ValueError(f"cell must be >= 1, got {cell}")
+    height, width = array.shape[:2]
+    if height == 0 or width == 0:
+        raise ValueError("cannot export an empty image")
+    cell = int(cell)
+    if background is not None:
+        background = _check_background(background)
+    codes, indices = _packed_codes(array)
+    parts = [
+        f'<svg xmlns="{SVG_NS}" width="{width * cell}" height="{height * cell}" '
+        f'viewBox="0 0 {width * cell} {height * cell}">'
+    ]
+    if background is not None:
+        parts.append(f'<rect width="100%" height="100%" fill="{background}"/>')
+    for code in codes:
+        mask = indices == code
+        ys, xs, lengths = _runs(mask)
+        if len(ys) == 0:
+            continue
+        parts.append(
+            f'<path fill="#{int(code):06X}" {_CRISP} d="{_path_data(ys, xs, lengths, cell)}"/>'
+        )
+    parts.append("</svg>")
+    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")
+
+
+__all__ = ["SVG_NS", "write_svg"]
diff --git a/lattice_core/ui/worker.py b/lattice_core/ui/worker.py
new file mode 100644
index 0000000..e545948
--- /dev/null
+++ b/lattice_core/ui/worker.py
@@ -0,0 +1,195 @@
+"""Shared render worker: progressive previews and full-resolution renders.
+
+Previews are rendered from cached proxies, coarse first (``PREVIEW_STAGES``), so
+a large source never reaches the pipeline at full resolution. The full render
+happens only on export. Sources above ``MAX_SOURCE_SIDE`` are refused instead of
+exhausting memory. The worker is app-agnostic: it renders pipeline specs and
+emits signals; it never talks to a host.
+"""
+
+from __future__ import annotations
+
+import logging
+import time
+from dataclasses import dataclass
+
+import numpy as np
+from PySide6.QtCore import QObject, QTimer, Signal, Slot
+
+from lattice_core import color
+from lattice_core.pipeline import PipelineSpec, render
+from lattice_core.types import RGB8, Image
+
+LOGGER = logging.getLogger(__name__)
+
+DEBOUNCE_MS = 120
+PREVIEW_STAGES: tuple[int, ...] = (256, 1024)
+PREVIEW_MAX_SIDE = PREVIEW_STAGES[-1]
+MAX_SOURCE_SIDE = 8000
+PROXY_STRIP_ROWS = 256
+
+
+@dataclass(frozen=True)
+class RenderResult:
+    """One finished full-resolution render: its job, the image and its duration."""
+
+    job: int
+    image: RGB8
+    seconds: float
+
+
+@dataclass(frozen=True)
+class PreviewResult:
+    """One finished preview stage: its job, the render, the source proxy and its duration."""
+
+    job: int
+    image: RGB8
+    original: RGB8
+    seconds: float
+    max_side: int = PREVIEW_MAX_SIDE
+
+
+def proxy_factor(image: Image, max_side: int) -> int:
+    """Return the integer area-downscale factor that brings image under max_side."""
+    longest = max(image.shape[:2])
+    return max(1, -(-longest // max(1, int(max_side))))
+
+
+def _downscale_strips(image: Image, factor: int) -> Image:
+    """Area-downscale image by factor in row strips, so peak memory stays near the output."""
+    if factor <= 1:
+        return np.ascontiguousarray(image, dtype=np.float32)
+    rows = max(factor, (PROXY_STRIP_ROWS // factor) * factor)
+    parts = [
+        color.downscale(image[start : start + rows], factor)
+        for start in range(0, image.shape[0], rows)
+    ]
+    return np.ascontiguousarray(np.concatenate(parts, axis=0))
+
+
+def preview_proxy(image: Image, max_side: int = PREVIEW_MAX_SIDE) -> RGB8:
+    """Return the uint8 proxy of image, shaped like the preview render at max_side."""
+    return color.to_rgb8(_downscale_strips(image, proxy_factor(image, max_side)))
+
+
+def oversize_message(shape: tuple[int, ...]) -> str | None:
+    """Return the refusal message for a source of this (height, width), or None."""
+    if len(shape) < 2:
+        return None
+    height, width = int(shape[0]), int(shape[1])
+    if max(height, width) <= MAX_SOURCE_SIDE:
+        return None
+    return (
+        f"Image is {width}×{height} px, above the {MAX_SOURCE_SIDE} px limit; "
+        "downscale it before opening it."
+    )
+
+
+class RenderWorker(QObject):
+    """Renders debounced, staged previews and full-resolution exports of one source."""
+
+    preview_ready = Signal(object)
+    export_ready = Signal(object)
+    failed = Signal(str)
+    progress = Signal(str)
+
+    def __init__(self, parent: QObject | None = None) -> None:
+        super().__init__(parent)
+        self._source: Image | None = None
+        self._proxies: dict[int, tuple[Image, RGB8]] = {}
+        self._spec: PipelineSpec | None = None
+        self._job = 0
+        self._pending_job = 0
+        self._debounce: QTimer | None = None
+
+    @Slot()
+    def start(self) -> None:
+        """Create the debounce timer inside whatever thread owns this worker."""
+        self._debounce = QTimer(self)
+        self._debounce.setSingleShot(True)
+        self._debounce.setInterval(DEBOUNCE_MS)
+        self._debounce.timeout.connect(self._render_preview)
+
+    @Slot(object)
+    def set_source(self, image: Image | None) -> None:
+        """Adopt image as the pipeline source, refusing sources above MAX_SOURCE_SIDE."""
+        if image is not None:
+            message = oversize_message(np.shape(image))
+            if message is not None:
+                self.failed.emit(message)
+                return
+        self._proxies.clear()
+        self._source = None if image is None else np.ascontiguousarray(image, dtype=np.float32)
+
+    def source(self) -> Image | None:
+        """Return the adopted source image, or None when none is loaded."""
+        return self._source
+
+    @Slot(object)
+    def request_preview(self, spec: PipelineSpec) -> None:
+        """Store spec and restart the debounce timer; only the last spec is rendered."""
+        self._spec = spec
+        self._job += 1
+        self._pending_job = self._job
+        if self._debounce is not None:
+            self._debounce.start()
+
+    @Slot(object)
+    def request_export(self, spec: PipelineSpec) -> None:
+        """Render spec at full resolution and emit the result for saving."""
+        result = self._render_full(spec)
+        if result is not None:
+            self.export_ready.emit(result)
+
+    def _proxy_for(self, max_side: int) -> tuple[Image, RGB8]:
+        """Return the cached (float32 proxy, uint8 proxy) of the source at max_side."""
+        cached = self._proxies.get(max_side)
+        if cached is None:
+            source = self._source
+            if source is None:
+                raise ValueError("no source image")
+            proxy = _downscale_strips(source, proxy_factor(source, max_side))
+            cached = (proxy, color.to_rgb8(proxy))
+            self._proxies[max_side] = cached
+        return cached
+
+    def _render_preview(self) -> None:
+        """Render the latest spec through the preview stages, dropping superseded jobs."""
+        spec, source = self._spec, self._source
+        if spec is None or source is None:
+            return
+        job = self._pending_job
+        if job != self._job:
+            LOGGER.debug("dropping superseded preview job %d", job)
+            return
+        previous: tuple[int, int] | None = None
+        for max_side in PREVIEW_STAGES:
+            if job != self._job:
+                LOGGER.debug("dropping superseded preview job %d", job)
+                return
+            started = time.perf_counter()
+            try:
+                proxy, original = self._proxy_for(max_side)
+                rgb8 = render(proxy, spec)
+            except Exception as exc:  # noqa: BLE001 - report any render failure to the user
+                self.failed.emit(f"Render failed: {exc}")
+                return
+            if rgb8.shape == previous:
+                continue
+            previous = rgb8.shape
+            seconds = time.perf_counter() - started
+            self.preview_ready.emit(PreviewResult(job, rgb8, original, seconds, max_side))
+
+    def _render_full(self, spec: PipelineSpec) -> RenderResult | None:
+        """Render spec at full resolution, emitting failed and returning None on error."""
+        source = self._source
+        if source is None:
+            self.failed.emit("Load an image before rendering.")
+            return None
+        started = time.perf_counter()
+        try:
+            rgb8 = render(source, spec)
+        except Exception as exc:  # noqa: BLE001 - report any render failure to the user
+            self.failed.emit(f"Render failed: {exc}")
+            return None
+        return RenderResult(self._job, rgb8, time.perf_counter() - started)
diff --git a/tests/test_ui_shared.py b/tests/test_ui_shared.py
new file mode 100644
index 0000000..2ac76a2
--- /dev/null
+++ b/tests/test_ui_shared.py
@@ -0,0 +1,561 @@
+"""Tests for the shared widgets of lattice_core/ui (card L-UI).
+
+Covers every accept item of the card: no application import in lattice_core/ui
+(E8), full-resolution export matching the pipeline output size, honest preset
+indicator, and each widget (canvas + worker + split, Looks grid, bridge status
+dot, empty state) with an offscreen smoke test.
+"""
+
+from __future__ import annotations
+
+import ast
+import os
+import subprocess
+import sys
+import time
+from pathlib import Path
+
+os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
+
+import numpy as np  # noqa: E402
+import pytest  # noqa: E402
+from PySide6.QtCore import QSettings, Qt  # noqa: E402
+from PySide6.QtGui import QImage  # noqa: E402
+from PySide6.QtTest import QTest  # noqa: E402
+from PySide6.QtWidgets import QApplication  # noqa: E402
+
+import lattice_core.dither  # noqa: E402,F401  (registers every algorithm)
+import lattice_core.effects  # noqa: E402,F401  (registers every effect)
+from lattice_core import color  # noqa: E402
+from lattice_core.pipeline import PipelineSpec, render  # noqa: E402
+from lattice_core.types import RGB8, Image  # noqa: E402
+from lattice_core.ui import (  # noqa: E402
+    MAX_SOURCE_SIDE,
+    PREVIEW_MAX_SIDE,
+    PREVIEW_STAGES,
+    BridgeStatusDot,
+    EmptyState,
+    ExportDialog,
+    ExportError,
+    Look,
+    LookGallery,
+    PresetIndicator,
+    PreviewCanvas,
+    PreviewResult,
+    RenderWorker,
+    oversize_message,
+    preview_proxy,
+    proxy_factor,
+)
+from lattice_core.ui import export_dialog as export_module  # noqa: E402
+from lattice_core.ui import looks as looks_module  # noqa: E402
+from lattice_core.ui import worker as worker_module  # noqa: E402
+
+UI_PACKAGE = Path(lattice_core.ui.__file__).resolve().parent
+REPO_ROOT = UI_PACKAGE.parents[1]
+RED = (255, 0, 0)
+BLUE = (0, 0, 255)
+
+
+@pytest.fixture(scope="module")
+def qapp() -> QApplication:
+    """Return the shared offscreen QApplication."""
+    app = QApplication.instance()
+    if not isinstance(app, QApplication):
+        app = QApplication([])
+    return app
+
+
+def _ramp(height: int, width: int) -> Image:
+    """Return a deterministic float32 grey ramp of the given shape."""
+    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)
+    image = np.empty((height, width, 3), dtype=np.float32)
+    image[:, :, :] = ramp[None, :, None]
+    return image
+
+
+def _solid(height: int, width: int, rgb: tuple[int, int, int]) -> RGB8:
+    """Return a uint8 RGB image filled with one colour."""
+    image = np.zeros((height, width, 3), dtype=np.uint8)
+    image[:, :] = rgb
+    return image
+
+
+def _pump(cond, timeout_ms: int = 8000) -> None:
+    """Process Qt events until cond() is true or the deadline passes."""
+    deadline = time.monotonic() + timeout_ms / 1000.0
+    while not cond() and time.monotonic() < deadline:
+        QApplication.processEvents()
+        time.sleep(0.01)
+    assert cond(), "the asynchronous widget never reached the expected state"
+
+
+@pytest.fixture
+def looks() -> list[Look]:
+    """Two named pipeline variants for the gallery tests."""
+    return [
+        Look("bw", "Black & white", PipelineSpec(algorithm_id="floyd_steinberg", pixel_size=6)),
+        Look("pixel", "Pixel", PipelineSpec(algorithm_id="bayer_4", pixel_size=8)),
+    ]
+
+
+@pytest.fixture
+def gallery(qapp: QApplication) -> LookGallery:
+    """Return a gallery whose helper thread is stopped even when a test fails."""
+    view = LookGallery()
+    view.show()
+    QApplication.processEvents()
+    yield view
+    view.shutdown()
+    view.close()
+    QApplication.processEvents()
+
+
+# --- accept: lattice_core/ui imports no application module (E8) --------------------
+
+
+def test_ui_package_imports_no_application_module() -> None:
+    """No module of lattice_core/ui may reference an application in an import."""
+    files = [path for path in UI_PACKAGE.rglob("*.py") if "__pycache__" not in str(path)]
+    for path in sorted(files):
+        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
+        for node in ast.walk(tree):
+            if isinstance(node, ast.Import):
+                names = [alias.name for alias in node.names]
+            elif isinstance(node, ast.ImportFrom):
+                names = [node.module] if node.module else []
+            else:
+                continue
+            for name in names:
+                root = name.split(".")[0]
+                assert root not in ("lattice_dither", "lattice_glyph", "lattice_glitch"), (
+                    f"{path.name} imports {name!r} from an application package"
+                )
+
+
+def test_base_core_import_never_pulls_ui_or_pyside6() -> None:
+    """A fresh interpreter importing lattice_core must not import the ui package."""
+    code = (
+        "import lattice_core, sys\n"
+        "assert 'lattice_core.ui' not in sys.modules, 'lattice_core.ui was imported'\n"
+        "assert 'PySide6' not in sys.modules, 'PySide6 was imported'\n"
+    )
+    env = dict(os.environ)
+    env.pop("PYTHONPATH", None)
+    result = subprocess.run(
+        [sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True
+    )
+    assert result.returncode == 0, result.stderr
+
+
+# --- accept: canvas + worker + split -----------------------------------------------
+
+
+def test_preview_emits_the_coarse_proxy_before_the_fine_proxy(qapp: QApplication) -> None:
+    """The 256 proxy is emitted first, then the 1024 proxy."""
+    worker = RenderWorker()
+    source = _ramp(600, 1100)
+    results: list[PreviewResult] = []
+    worker.preview_ready.connect(results.append)
+    worker.set_source(source)
+    worker.request_preview(PipelineSpec())
+    worker._render_preview()
+    assert [result.max_side for result in results] == list(PREVIEW_STAGES)
+    assert [max(result.image.shape[:2]) for result in results] == [220, 550]
+    assert all(result.original.shape == result.image.shape for result in results)
+    assert np.array_equal(results[0].image, render(source, PipelineSpec(), max_side=256))
+    assert np.array_equal(results[-1].image, render(source, PipelineSpec(), max_side=1024))
+
+
+def test_source_below_the_first_stage_emits_one_preview(qapp: QApplication) -> None:
+    """A source smaller than the coarse proxy renders once, not twice."""
+    worker = RenderWorker()
+    results: list[PreviewResult] = []
+    worker.preview_ready.connect(results.append)
+    worker.set_source(_ramp(48, 64))
+    worker.request_preview(PipelineSpec())
+    worker._render_preview()
+    assert [result.max_side for result in results] == [PREVIEW_STAGES[0]]
+    assert results[0].image.shape == (48, 64, 3)
+
+
+def test_previews_render_proxies_and_only_export_renders_full(
+    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """Preview stages render proxies; the export path renders the full source."""
+    shapes: list[tuple[int, ...]] = []
+    real = worker_module.render
+
+    def spy(src, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8:
+        shapes.append(src.shape)
+        return real(src, spec, max_side=max_side)
+
+    monkeypatch.setattr(worker_module, "render", spy)
+    worker = RenderWorker()
+    source = _ramp(600, 1100)
+    worker.set_source(source)
+    worker.request_preview(PipelineSpec())
+    worker._render_preview()
+    assert len(shapes) == len(PREVIEW_STAGES)
+    assert all(max(shape[:2]) <= PREVIEW_MAX_SIDE for shape in shapes)
+    shapes.clear()
+    exported: list[object] = []
+    worker.export_ready.connect(exported.append)
+    worker.request_export(PipelineSpec())
+    assert shapes == [source.shape]
+    assert exported[0].image.shape == source.shape
+
+
+def test_oversized_source_is_refused(qapp: QApplication) -> None:
+    """A source above MAX_SOURCE_SIDE is refused and never reaches the pipeline."""
+    worker = RenderWorker()
+    messages: list[str] = []
+    results: list[PreviewResult] = []
+    worker.failed.connect(messages.append)
+    worker.preview_ready.connect(results.append)
+    worker.set_source(_ramp(9000, 40))
+    assert len(messages) == 1
+    assert "9000" in messages[0] and str(MAX_SOURCE_SIDE) in messages[0]
+    worker.request_preview(PipelineSpec())
+    worker._render_preview()
+    assert results == []
+    assert oversize_message((MAX_SOURCE_SIDE, 10)) is None
+    assert oversize_message((MAX_SOURCE_SIDE + 1, 10)) is not None
+
+
+@pytest.mark.parametrize("shape", [(5, 7), (601, 1101), (1000, 999)])
+def test_preview_proxy_matches_the_core_downscale(shape: tuple[int, int]) -> None:
+    """The strip-wise proxy is bit-identical to color.downscale on the whole image."""
+    image = np.random.default_rng(0).random((*shape, 3), dtype=np.float32)
+    for max_side in PREVIEW_STAGES:
+        factor = proxy_factor(image, max_side)
+        expected = color.to_rgb8(color.downscale(image, factor))
+        assert np.array_equal(preview_proxy(image, max_side), expected)
+
+
+def test_canvas_buffer_reuse_and_modes(qapp: QApplication) -> None:
+    """Split and before modes compose into the reused display buffer."""
+    canvas = PreviewCanvas()
+    canvas.set_original(_solid(20, 40, BLUE))
+    canvas.set_image(_solid(20, 40, RED))
+    buffer = canvas.qimage()
+    assert isinstance(buffer, QImage)
+    canvas.set_image(_solid(20, 40, RED))
+    assert canvas.qimage() is buffer
+    canvas.set_mode("split")
+    assert buffer.pixelColor(0, 0).getRgb()[:3] == BLUE
+    assert buffer.pixelColor(39, 0).getRgb()[:3] == RED
+    canvas.set_mode("before")
+    assert buffer.pixelColor(39, 0).getRgb()[:3] == BLUE
+    canvas.set_mode("after")
+    assert buffer.pixelColor(0, 0).getRgb()[:3] == RED
+    assert canvas.mode() == "after"
+
+
+def test_canvas_zoom_is_clamped_and_fit(qapp: QApplication) -> None:
+    """Zoom is clamped to the supported range and zoom_fit stays within it."""
+    canvas = PreviewCanvas()
+    canvas.set_zoom(1.0)
+    assert canvas.zoom() == pytest.approx(1.0)
+    canvas.set_zoom(1e6)
+    assert canvas.zoom() == pytest.approx(32.0)
+    canvas.set_zoom(-1.0)
+    assert canvas.zoom() == pytest.approx(0.01)
+    canvas.set_image(_solid(100, 200, RED))
+    canvas.set_zoom(1.0)
+    canvas.zoom_fit()
+    assert 0.01 <= canvas.zoom() <= 32.0
+    with pytest.raises(ValueError):
+        canvas.set_mode("diagonal")
+
+
+# --- accept: Looks grid (thumbnails on the current image) --------------------------
+
+
+def test_look_gallery_cells_and_names(gallery: LookGallery, looks: list[Look]) -> None:
+    """set_looks creates one cell per look, in order."""
+    gallery.set_looks(looks)
+    assert [cell.look_id for cell in gallery.cells()] == ["bw", "pixel"]
+    assert [cell.name_label.text() for cell in gallery.cells()] == ["Black & white", "Pixel"]
+
+
+def test_look_gallery_renders_thumbnails_on_the_current_image(
+    gallery: LookGallery, looks: list[Look], monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """Thumbnails render on the image that is loaded, never a fixed test image."""
+    seen: list[tuple[int, ...]] = []
+    real = looks_module.render
+
+    def spy(src, spec: PipelineSpec, **kwargs) -> RGB8:
+        seen.append(src.shape)
+        return real(src, spec, **kwargs)
+
+    monkeypatch.setattr(looks_module, "render", spy)
+    gallery.set_looks(looks)
+    first = _ramp(400, 900)
+    gallery.set_source(first)
+    _pump(lambda: all(cell.has_thumbnail() for cell in gallery.cells()))
+    assert len(seen) == 2
+    assert all(max(shape[:2]) <= 512 for shape in seen)
+    expected = preview_proxy(first, 512).shape
+    assert all(shape == expected for shape in seen)
+    second = _ramp(300, 600)
+    gallery.set_source(second)
+    _pump(lambda: all(cell.has_thumbnail() for cell in gallery.cells()))
+    assert len(seen) == 4
+    expected = preview_proxy(second, 512).shape
+    assert all(shape == expected for shape in seen[2:])
+
+
+def test_look_gallery_without_source_keeps_placeholders(
+    gallery: LookGallery, looks: list[Look], monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """Without an image no thumbnail is rendered and every cell shows a placeholder."""
+    calls: list[object] = []
+    monkeypatch.setattr(looks_module, "render", lambda *a, **k: calls.append(a))
+    gallery.set_looks(looks)
+    gallery.set_source(None)
+    QApplication.processEvents()
+    assert calls == []
+    assert not any(cell.has_thumbnail() for cell in gallery.cells())
+
+
+def test_look_cell_click_emits_its_id(gallery: LookGallery, looks: list[Look]) -> None:
+    """Clicking a cell reports the look id through the gallery signal."""
+    gallery.set_looks(looks)
+    chosen: list[str] = []
+    gallery.look_chosen.connect(chosen.append)
+    QTest.mouseClick(gallery.cells()[1], Qt.MouseButton.LeftButton)
+    assert chosen == ["pixel"]
+
+
+# --- accept: bridge status dot ------------------------------------------------------
+
+
+def _stub_discover(result):
+    """Return a Discover callable answering with result for any host."""
+
+    def discover(host, port=None):
+        return result
+
+    return discover
+
+
+def test_bridge_dot_starts_unknown_and_validates_states(qapp: QApplication) -> None:
+    """The dot starts unknown; a state must be one of the three known states."""
+    dot = BridgeStatusDot()
+    assert dot.state() == "unknown"
+    dot.set_state("connected")
+    assert dot.state() == "connected"
+    dot.set_state("disconnected")
+    assert dot.state() == "disconnected"
+    with pytest.raises(ValueError):
+        dot.set_state("half-open")
+    dot.stop()
+
+
+def test_bridge_dot_reports_connected_and_disconnected(qapp: QApplication) -> None:
+    """A live probe turns the dot green; a refused host turns it red."""
+    dot = BridgeStatusDot(discover=_stub_discover(object()))
+    dot.check()
+    _pump(lambda: dot.state() != "unknown")
+    assert dot.state() == "connected"
+    dot.stop()
+    dot = BridgeStatusDot(discover=_stub_discover(None))
+    dot.check()
+    _pump(lambda: dot.state() != "unknown")
+    assert dot.state() == "disconnected"
+    dot.stop()
+
+
+def test_bridge_dot_probe_error_is_a_normal_disconnect(qapp: QApplication) -> None:
+    """A discovery exception must never crash; the dot just reports disconnected."""
+
+    def broken(host, port=None):
+        raise OSError("connection refused")
+
+    dot = BridgeStatusDot(discover=broken)
+    dot.check()
+    _pump(lambda: dot.state() != "unknown")
+    assert dot.state() == "disconnected"
+    dot.stop()
+    with pytest.raises(ValueError):
+        BridgeStatusDot(host="hologram")
+
+
+# --- accept: empty state -------------------------------------------------------------
+
+
+def test_empty_state_message_and_visibility(qapp: QApplication) -> None:
+    """The empty state carries guidance text and shows it as a widget."""
+    state = EmptyState()
+    assert state.message() == "Open an image to start."
+    state.set_message("Drop an image here.")
+    assert state.message() == "Drop an image here."
+    state.show()
+    QApplication.processEvents()
+    assert state.isVisible()
+    state.close()
+
+
+# --- accept: preset indicator honest, live, image-gated ------------------------------
+
+
+def test_preset_indicator_is_hidden_without_an_image(qapp: QApplication) -> None:
+    """Without an image the indicator is not shown, whatever the preset state."""
+    indicator = PresetIndicator()
+    assert indicator.isHidden()
+    indicator.show()
+    QApplication.processEvents()
+    assert indicator.isVisible()
+    indicator.set_image_loaded(False)
+    QApplication.processEvents()
+    assert not indicator.isVisible()
+    indicator.set_image_loaded(True)
+    QApplication.processEvents()
+    assert indicator.isVisible()
+
+
+def test_preset_indicator_shows_the_applied_preset_and_tracks_changes(
+    qapp: QApplication,
+) -> None:
+    """The indicator names the applied preset and marks every pipeline drift."""
+    indicator = PresetIndicator()
+    assert indicator.indicator_text() == "Custom"
+    indicator.set_preset("01_gameboy.json")
+    assert indicator.preset_name() == "01_gameboy.json"
+    assert indicator.indicator_text() == "01_gameboy.json"
+    assert not indicator.is_modified()
+    indicator.pipeline_changed()
+    assert indicator.is_modified()
+    assert indicator.indicator_text() == "01_gameboy.json (modified)"
+    indicator.pipeline_changed()
+    assert indicator.indicator_text() == "01_gameboy.json (modified)"
+    indicator.set_preset("02_neon.json")
+    assert not indicator.is_modified()
+    assert indicator.indicator_text() == "02_neon.json"
+    indicator.set_preset(None)
+    assert indicator.indicator_text() == "Custom"
+    assert indicator.preset_name() is None
+
+
+# --- accept: one full-resolution export dialog ---------------------------------------
+
+
+def _export_settings(tmp_path: Path) -> QSettings:
+    """Return an isolated QSettings so the dialog never touches user settings."""
+    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
+
+
+def test_export_dialog_renders_at_full_resolution(
+    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """The dialog renders the full source with no max_side, never the preview proxy."""
+    source = _ramp(700, 1400)
+    spec = PipelineSpec()
+    full = render(source, spec)
+    proxy = render(source, spec, max_side=PREVIEW_MAX_SIDE)
+    assert full.shape != proxy.shape
+    calls: list[tuple[tuple[int, ...], PipelineSpec, object]] = []
+
+    def spy(src, s: PipelineSpec, *, max_side: int | None = None):
+        calls.append((src.shape, s, max_side))
+        return render(src, s, max_side=max_side)
+
+    monkeypatch.setattr(export_module, "render", spy)
+    target = tmp_path / "out.png"
+    dialog = ExportDialog(source, spec, settings=_export_settings(tmp_path))
+    dialog.path_edit.setText(str(target))
+    written = dialog.export_now()
+    assert written == [target]
+    shape, _, max_side = calls[-1]
+    assert max_side is None
+    assert shape == source.shape
+    from PIL import Image as PILImage
+
+    with PILImage.open(target) as image:
+        assert image.size == (full.shape[1], full.shape[0])
+    assert (proxy.shape[1], proxy.shape[0]) != (full.shape[1], full.shape[0])
+
+
+@pytest.mark.parametrize("format_key", ["png", "svg", "gif"])
+def test_export_file_matches_the_pipeline_output_size(
+    qapp: QApplication, tmp_path: Path, format_key: str
+) -> None:
+    """Every format writes a file of exactly the full-resolution pipeline size."""
+    source = _ramp(90, 130)
+    spec = PipelineSpec(pixel_size=3)
+    expected = render(source, spec)
+    target = tmp_path / f"out.{format_key}"
+    dialog = ExportDialog(source, spec, settings=_export_settings(tmp_path))
+    dialog.format_box.setCurrentIndex(dialog.format_box.findData(format_key))
+    if format_key == "svg":
+        dialog.cell.setValue(2)
+    dialog.path_edit.setText(str(target))
+    (written,) = dialog.export_now()
+    assert written == target
+    if format_key == "svg":
+        text = target.read_text(encoding="utf-8")
+        assert f'width="{expected.shape[1] * 2}"' in text
+        assert f'height="{expected.shape[0] * 2}"' in text
+    else:
+        from PIL import Image as PILImage
+
+        with PILImage.open(target) as image:
+            assert image.size == (expected.shape[1], expected.shape[0])
+
+
+def test_export_dialog_requires_a_path_and_reports_render_failures(
+    qapp: QApplication, tmp_path: Path
+) -> None:
+    """Export without a path raises; a failing render is reported, never raised."""
+    source = _ramp(48, 64)
+    dialog = ExportDialog(source, PipelineSpec(), settings=_export_settings(tmp_path))
+    dialog.path_edit.clear()
+    with pytest.raises(ExportError):
+        dialog.export_now()
+
+    def broken(spec):
+        raise ValueError("render exploded")
+
+    dialog = ExportDialog(
+        source, PipelineSpec(), render_full=broken, settings=_export_settings(tmp_path)
+    )
+    target = tmp_path / "out.png"
+    dialog.path_edit.setText(str(target))
+    dialog._on_export()
+    assert not target.exists()
+    assert "render exploded" in dialog.report.text()
+
+
+# --- accept: each widget consumed by a smoke test -------------------------------------
+
+
+def test_shared_widgets_smoke(qapp: QApplication, tmp_path: Path) -> None:
+    """Every shared widget instantiates, shows and shuts down cleanly offscreen."""
+    source = _ramp(120, 160)
+    spec = PipelineSpec(pixel_size=4)
+    canvas = PreviewCanvas()
+    canvas.set_original(color.to_rgb8(source))
+    canvas.set_image(render(source, spec, max_side=256))
+    canvas.set_mode("split")
+    worker = RenderWorker()
+    worker.set_source(source)
+    gallery = LookGallery()
+    gallery.set_looks([Look("bw", "B&W", spec)])
+    gallery.set_source(source)
+    dialog = ExportDialog(source, spec, settings=_export_settings(tmp_path))
+    dot = BridgeStatusDot()
+    empty = EmptyState()
+    indicator = PresetIndicator()
+    indicator.set_preset("smoke.json")
+    indicator.set_image_loaded(True)
+    for widget in (canvas, gallery, dialog, dot, empty, indicator):
+        widget.show()
+    QApplication.processEvents()
+    _pump(lambda: gallery.cells()[0].has_thumbnail())
+    gallery.shutdown()
+    dot.stop()
+    for widget in (canvas, gallery, dialog, dot, empty, indicator):
+        widget.close()
+    QApplication.processEvents()

CODER NOTES AND DEVIATIONS (L-UI, attempt 1)
- E1 ×5 (contrat silencieux) : export GIF = image unique pleine résolution (séquences animées =
  L-LOOP) ; export synchrone par défaut (l'app peut injecter render_full worker) ; SVG = repli
  pixel §11 rects-runs (le SVG piloté par layout() des renderers glyphes est le périmètre L11 —
  aucun renderer n'a layout() aujourd'hui) ; PresetIndicator sans index/total + textes en
  anglais (i18n tr() = app-side) ; proxy source vignettes Looks = 512 px (déterministe).
- E8/E9 : clean — aucun import d'app, découverte hôte en thread, hôte absent = état normal.
- PySide6 confiné à lattice_core/ui (extra [ui]) ; rien sur le chemin CLI.
