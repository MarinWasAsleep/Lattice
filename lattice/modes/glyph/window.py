"""Main window of Lattice Glyph: selector, live preview, palette, presets and bridge.

The window owns the only ``PipelineSpec`` and hands every job to a controller:

- previews go to the shared ``RenderWorker`` on a helper thread;
- exports go to ``ExportController``, which calls the same functions the CLI calls, so the
  CLI and the GUI cannot produce different bytes for the same preset (G9);
- host work goes to ``BridgeController``, and an absent host is a status-bar message.

The shared widgets of ``lattice.ui`` are consumed, never reimplemented: canvas, worker,
export dialog, preset indicator, empty state, bridge dot and the glyph browser.
"""

from __future__ import annotations

import copy
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

import lattice.dither  # noqa: F401  (registers every algorithm)
import lattice.effects  # noqa: F401  (registers every effect)
import lattice.renderers  # noqa: F401  (registers every renderer)
from lattice.modes.glyph import APP_NAME
from lattice.modes.glyph import presets as preset_tools
from lattice.modes.glyph.actions import build_actions, build_toolbar, dropped_images
from lattice.modes.glyph.bridge_actions import DEFAULT_HOST
from lattice.modes.glyph.bridge_controller import BridgeController
from lattice.modes.glyph.document import DocumentError, load_image
from lattice.modes.glyph.export_actions import ExportController
from lattice.modes.glyph.palette_panel import PalettePanel
from lattice.modes.glyph.preset_panel import PresetPanel
from lattice.modes.glyph.renderer_panel import RendererPanel
from lattice.pipeline import PipelineSpec
from lattice.types import Image
from lattice.ui import (
    BridgeStatusDot,
    EmptyState,
    PresetIndicator,
    PreviewCanvas,
    RenderWorker,
    oversize_message,
    preview_proxy,
)
from lattice.ui.geometry import PANEL_WIDTH
from lattice.ui.glyph_browser import GlyphBrowser

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
        self.bridge.absent.connect(self.status)
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
        self.dock.setMinimumWidth(PANEL_WIDTH)
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
        """Return the spec the panels describe, keeping every field they do not show."""
        spec = copy.deepcopy(self.spec)
        spec.renderer = self.renderer_panel.current()
        spec.renderer_style = self.renderer_panel.style_options()
        if spec.palette is not None:  # a continuous spec keeps its null palette (§3)
            spec.palette = self.palette_panel.spec()
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
        """Place the current render in the bridge host; an absent host is a status line.

        The render runs on the bridge worker through the CLI's own function (G9), so a
        full-resolution send never freezes the window and a missing host is ``absent`` —
        one status-bar message, never a modal dialog (§7, E9).
        """
        if self.source is None:
            self.report(NO_SOURCE)
            return
        self.bridge.push(self.source, self.spec)

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
