"""Main window of Lattice Glitch: effect stack, live preview, seeds, masks, presets, bridge.

The window owns the spec, the stack, the mask planes and the SeedController. Previews go
to the GlitchWorker with an immutable context snapshot; exports call the CLI's own
render function (G9); an absent host is a status-bar message. Shared lattice.ui
widgets are consumed, never reimplemented.
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

import lattice.effects  # noqa: F401  (registers every effect)
from lattice.modes.glitch import APP_NAME
from lattice.modes.glitch import presets as preset_tools
from lattice.modes.glitch.actions import (
    build_actions,
    build_toolbar,
    handle_drag_enter,
    handle_drop,
)
from lattice.modes.glitch.bridge_actions import DEFAULT_HOST
from lattice.modes.glitch.bridge_controller import BridgeController
from lattice.modes.glitch.document import DocumentError, RenderContext, load_image
from lattice.modes.glitch.effects_panel import EffectsPanel
from lattice.modes.glitch.export_actions import ExportController
from lattice.modes.glitch.mask_panel import MaskPanel
from lattice.modes.glitch.preset_panel import PresetPanel
from lattice.modes.glitch.seed_panel import SeedPanel
from lattice.modes.glitch.stack import EffectStack
from lattice.modes.glitch.window_bridge import BridgeMixin
from lattice.modes.glitch.worker import GlitchWorker
from lattice.pipeline import PipelineSpec
from lattice.preset import Preset
from lattice.seed import SeedController
from lattice.types import RGB8, Image
from lattice.ui import (
    BridgeStatusDot,
    EmptyState,
    PresetIndicator,
    PreviewCanvas,
    PreviewResult,
    oversize_message,
    preview_proxy,
)
from lattice.ui.geometry import PANEL_WIDTH

LOGGER = logging.getLogger(__name__)
SETTINGS_NAME = "LatticeGlitch"
GEOMETRY_KEY = "geometry"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
PANEL_TABS = ("Effects", "Seed", "Masks", "Presets")
STATUS_MS = 5000
STOP_MS = 5000
EMPTY_TEXT = "Open an image, or drop one here, to start glitching."


class MainWindow(BridgeMixin, QMainWindow):
    """Application window owning the spec, the stack, the seeds, the masks and the bridge."""

    preview_requested = Signal(object)
    source_changed = Signal(object)
    context_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None, *,
                 preset_dirs: tuple[Path, ...] | None = None) -> None:
        """Build the canvas, the docks, the status bar and the helper threads."""
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.spec: PipelineSpec = preset_tools.default_spec()
        self.effect_stack = EffectStack()
        self.controller = SeedController(self.spec.seed)
        self._fixed_streams: dict[int, int] = {}
        self.source: Image | None = None
        self.source_path: Path | None = None
        self.worker: GlitchWorker | None = None
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
        self.bridge.absent.connect(lambda _msg: self.check_bridge())
        self.bridge.failed.connect(lambda _msg: self.check_bridge())
        self.check_bridge()
        self.effects_panel.load(self.effect_stack, self.mask_panel.mask_ids())
        self.refresh_seed_panel()

    def _build_dock(self, preset_dirs: tuple[Path, ...] | None) -> None:
        """Create the right dock with the effects, seed, mask and preset panels."""
        self.dock = QDockWidget("Panels", self)
        self.dock.setObjectName("panel_dock")
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.tabs = QTabWidget(self.dock)
        self.tabs.setObjectName("panel_tabs")
        self.effects_panel = EffectsPanel(self.tabs)
        self.seed_panel = SeedPanel(self.tabs)
        self.mask_panel = MaskPanel(self.tabs)
        self.preset_panel = PresetPanel(preset_dirs, self.tabs)
        self.panels: dict[str, QWidget] = dict(zip(
            PANEL_TABS, (self.effects_panel, self.seed_panel, self.mask_panel,
                         self.preset_panel), strict=True,
        ))
        for name, panel in self.panels.items():
            self.tabs.addTab(panel, name)
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumWidth(PANEL_WIDTH)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.effects_panel.changed.connect(self.on_panels_changed)
        self.seed_panel.seed_changed.connect(self.set_seed)
        self.seed_panel.reroll_requested.connect(self.reroll)
        self.seed_panel.lock_changed.connect(self.toggle_lock)
        self.mask_panel.masks_changed.connect(self.on_masks_changed)
        self.mask_panel.mask_painted.connect(lambda _id: self.on_masks_changed())
        self.mask_panel.failed.connect(self.report)
        self.preset_panel.loaded.connect(self.load_preset)
        self.preset_panel.save_requested.connect(self.save_preset_to)
        self.preset_panel.failed.connect(self.report)

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
        """Create the glitch render worker in its own thread and connect its signals."""
        thread = QThread(self)
        worker = GlitchWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        thread.finished.connect(worker.deleteLater)
        self.context_changed.connect(worker.set_context)
        self.preview_requested.connect(worker.request_preview)
        self.source_changed.connect(worker.set_source)
        worker.preview_ready.connect(self._on_preview)
        worker.failed.connect(self.report)
        self.render_thread, self.worker = thread, worker
        thread.start()

    def shutdown(self) -> None:
        """Stop the helper threads and the bridge probe; safe to call more than once.

        The worker reference is released only once its thread has stopped: freeing a
        worker a running thread is still executing is a hard crash, not an exception.
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

    # --- spec, stack, seeds and preview --------------------------------------------

    def settings(self) -> QSettings:
        """Return the settings object the export dialog remembers its directory in."""
        return self._settings

    def render_context(self) -> RenderContext:
        """Return the immutable render snapshot: mask ids, copied planes and stream seeds."""
        count = len(self.effect_stack)
        streams = tuple(self._fixed_streams.get(i, self.controller.module_seed_for(i))
                        for i in range(count))
        return RenderContext(mask_ids=self.effect_stack.mask_ids(),
                             masks={k: v.copy() for k, v in self.mask_panel.planes().items()},
                             streams=streams)

    def sync_spec(self) -> None:
        """Mirror the stack and the controller into the spec the renderers read."""
        self.spec.post_effects = self.effect_stack.instances()
        self.spec.seed = self.controller.seed

    def refresh_seed_panel(self) -> None:
        """Show the current seed and one lock checkbox per stack position."""
        labels = [slot.instance.effect_id for slot in self.effect_stack.slots()]
        self.seed_panel.set_seed(self.controller.seed)
        self.seed_panel.set_modules(labels, self.controller.locked())

    def on_panels_changed(self) -> None:
        """Adopt the stack edits, mark the preset modified and request a preview."""
        self.sync_spec()
        self.refresh_seed_panel()
        self.indicator.pipeline_changed()
        self._request_preview()

    def on_masks_changed(self) -> None:
        """Offer the current mask ids to the stack and request a preview."""
        self.effects_panel.set_mask_ids(self.mask_panel.mask_ids())
        self.sync_spec()
        self._request_preview()

    def reroll(self) -> None:
        """Reroll the global seed; locked modules keep their streams (§18)."""
        self.controller.reroll()
        self.sync_spec()
        self.seed_panel.set_seed(self.controller.seed)
        self.indicator.pipeline_changed()
        self._request_preview()
        self.status(f"Seed {self.controller.seed}")

    def set_seed(self, seed: int) -> None:
        """Adopt an explicit global seed, keeping the current locks."""
        self.controller.reroll(int(seed))
        self.sync_spec()
        self.indicator.pipeline_changed()
        self._request_preview()

    def toggle_lock(self, module: int, locked: bool) -> None:
        """Freeze or release one module's stream and request a preview."""
        if locked:
            self.controller.lock(module)
        else:
            self.controller.unlock(module)
            self._fixed_streams.pop(module, None)
        self._request_preview()

    def apply_preset(self, preset: Preset, announce: bool = True) -> None:
        """Adopt a whole preset: spec, stack, masks and seed, then request a preview."""
        try:
            spec = preset_tools.spec_of(preset)
            stack = preset_tools.stack_of(preset)
            planes = preset_tools.masks_of(preset)
            fixed = preset_tools.locked_streams_of(preset)
        except (OSError, ValueError, KeyError) as exc:
            self.report(f"Cannot apply preset: {exc}")
            return
        self.spec = spec
        self.effect_stack = stack
        self.controller = SeedController(preset.seed)
        self._fixed_streams = fixed
        for module in fixed:
            self.controller.lock(module)
        self.mask_panel.set_planes(planes)
        self.effects_panel.load(self.effect_stack, self.mask_panel.mask_ids())
        self.sync_spec()
        self.refresh_seed_panel()
        if announce:
            self.indicator.pipeline_changed()
        self._request_preview()

    def load_preset(self, preset: Preset) -> None:
        """Load a preset from the browser; the indicator names it as freshly applied."""
        self.apply_preset(preset, announce=False)
        path = self.preset_panel.selected_path()
        self.indicator.set_preset(None if path is None else path.name)
        self.indicator.set_image_loaded(self.source is not None)

    def _request_preview(self) -> None:
        """Ask the worker for a preview of the current document, when an image is loaded."""
        if self.source is not None:
            self.context_changed.emit(self.render_context())
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
        self.mask_panel.set_source(image)
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

    def _on_preview(self, result: PreviewResult) -> None:
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

    def export_dialog(self) -> None:
        """Open the shared full-resolution export dialog."""
        self.exporter.dialog()

    def export_to(self, path: str | Path) -> dict:
        """Write the current render to path as PNG."""
        return self.exporter.to(path)

    def save_preset_to(self, path: str | Path) -> None:
        """Write the current document as a v3 preset and remember it as the applied one."""
        self.exporter.save_preset(str(path))

    def render_full(self, image: Image, spec: PipelineSpec) -> RGB8:
        """Render spec on image through the function the CLI calls (G9)."""
        return self.exporter.render_full(image, spec)

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
        handle_drag_enter(self, event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Open the first image of a drop, or report that the drop was ignored."""
        handle_drop(self, event)


__all__ = ["MainWindow", "PANEL_TABS"]
