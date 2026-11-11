"""Main window: toolbar, preview canvas, panel dock, status bar and render worker."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import QSettings, Qt, QThread, Signal, SignalInstance
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QWidget,
)

import dithercraft.algorithms  # noqa: F401  (importing the package registers every algorithm)
import dithercraft.effects  # noqa: F401  (importing the package registers every effect)
from dithercraft.bridge.photocraft import TESTED_PHOTOCRAFT_VERSION
from dithercraft.core import color
from dithercraft.core.pipeline import PipelineSpec
from dithercraft.core.types import Image
from dithercraft.ui.algorithm_panel import AlgorithmPanel
from dithercraft.ui.canvas import PreviewCanvas
from dithercraft.ui.effects_panel import EffectsPanel
from dithercraft.ui.palette_panel import PalettePanel
from dithercraft.ui.preset_browser import PresetController
from dithercraft.ui.worker import PreviewResult, RenderResult, RenderWorker

LOGGER = logging.getLogger(__name__)

PANEL_TABS: tuple[str, ...] = ("Algorithm", "Palette", "Effects")
DOCK_MIN_WIDTH = 320
SETTINGS_NAME = "DitherCraft"
PRESET_DIR = Path(__file__).resolve().parents[2] / "presets"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
PNG_FILTER = "PNG images (*.png);;All files (*)"
STATUS_MS = 5000
WORKER_STOP_MS = 5000
UNTESTED_WARNING = (
    "PhotoCraft {version} not tested with DitherCraft (tested: {tested}). "
    "Run tools/smoke_photocraft.py."
)


class MainWindow(QMainWindow):
    """Application window owning the pipeline spec and the render worker."""

    preview_requested = Signal(object)
    export_requested = Signal(object)
    send_requested = Signal(object)
    get_requested = Signal()
    source_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DitherCraft")
        self.resize(1280, 800)
        self.spec = PipelineSpec()
        self.source: Image | None = None
        self.worker: RenderWorker | None = None
        self.thread: QThread | None = None
        self._settings = QSettings(SETTINGS_NAME, SETTINGS_NAME)
        self._applied_job = -1
        self._export_path: Path | None = None
        self._version_warned = False
        self.canvas = PreviewCanvas(self)
        self.setCentralWidget(self.canvas)
        self.actions: dict[str, QAction] = {}
        self._build_actions()
        self._build_toolbar()
        self._build_dock()
        self._build_status_bar()
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self._start_worker()
        self._load_spec(self.spec)

    def _add_action(
        self, key: str, text: str, slot: Callable[..., None], shortcut: QKeySequence | None = None
    ) -> QAction:
        """Create one action, register it under key and connect it to slot."""
        action = QAction(text, self)
        action.setObjectName(key)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        self.actions[key] = action
        return action

    def _build_actions(self) -> None:
        """Create every toolbar action of the contract and connect its slot."""
        self._add_action(
            "open_image", "Open image", self._on_open_image, QKeySequence.StandardKey.Open
        )
        self._add_action("get_from_photocraft", "Get from PhotoCraft", self._on_get_from_photocraft)
        self._add_action("send_to_photocraft", "Send to PhotoCraft", self._on_send_to_photocraft)
        self._add_action(
            "export_png", "Export PNG", self._on_export_png, QKeySequence.StandardKey.Save
        )
        self.mode_group = QActionGroup(self)
        for key, text, mode in (
            ("mode_before", "Before", "before"),
            ("mode_after", "After", "after"),
            ("mode_split", "Split", "split"),
        ):
            action = self._add_action(key, text, lambda _c=False, m=mode: self._on_mode(m))
            action.setCheckable(True)
            action.setChecked(mode == "after")
            self.mode_group.addAction(action)
        self._add_action("zoom_fit", "Zoom Fit", self.canvas.zoom_fit)
        self._add_action("zoom_100", "100 %", lambda: self.canvas.set_zoom(1.0))
        self._add_action("zoom_200", "200 %", lambda: self.canvas.set_zoom(2.0))
        self._add_action("zoom_400", "400 %", lambda: self.canvas.set_zoom(4.0))
        self.presets = PresetController(self)

    def _build_toolbar(self) -> None:
        """Create the main toolbar with the actions in contract order."""
        self.toolbar = QToolBar("Main", self)
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        groups = (
            ("open_image", "get_from_photocraft", "send_to_photocraft", "export_png"),
            ("preset_prev", "load_preset", "save_preset", "preset_next"),
            ("mode_before", "mode_after", "mode_split"),
            ("zoom_fit", "zoom_100", "zoom_200", "zoom_400"),
        )
        for index, keys in enumerate(groups):
            if index:
                self.toolbar.addSeparator()
            for key in keys:
                self.toolbar.addAction(self.actions[key])

    def _build_dock(self) -> None:
        """Create the right dock holding the algorithm, palette and effects panels."""
        self.dock = QDockWidget("Panels", self)
        self.dock.setObjectName("panel_dock")
        areas = Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        self.dock.setAllowedAreas(areas)
        self.tabs = QTabWidget(self.dock)
        self.tabs.setObjectName("panel_tabs")
        self.placeholder_tabs: dict[str, QLabel] = {}
        self.algorithm_panel = AlgorithmPanel(self.tabs)
        self.palette_panel = PalettePanel(self.tabs)
        self.effects_panel = EffectsPanel(self.tabs)
        panels = (self.algorithm_panel, self.palette_panel, self.effects_panel)
        self.panels: dict[str, QWidget] = dict(zip(PANEL_TABS, panels, strict=True))
        for name, panel in self.panels.items():
            self.tabs.addTab(panel, name)
            panel.changed.connect(self._request_preview)
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumWidth(DOCK_MIN_WIDTH)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _build_status_bar(self) -> None:
        """Create the status bar with the connection state and render time labels."""
        bar = self.statusBar()
        self.connection_label = QLabel("PhotoCraft: unknown", self)
        self.connection_label.setObjectName("connection_label")
        self.render_time_label = QLabel("Render: -", self)
        self.render_time_label.setObjectName("render_time_label")
        self.version_label = QLabel("", self)
        self.version_label.setObjectName("version_warning")
        labels = (self.connection_label, self.render_time_label, self.presets.label)
        for label in (*labels, self.version_label):
            bar.addPermanentWidget(label)
        bar.showMessage("Ready")

    def _start_worker(self) -> None:
        """Create the render worker in its own thread and connect every signal."""
        self.thread = QThread(self)
        self.worker = RenderWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.thread.finished.connect(self.worker.deleteLater)
        self.preview_requested.connect(self.worker.request_preview)
        self.export_requested.connect(self.worker.request_export)
        self.send_requested.connect(self.worker.request_send)
        self.get_requested.connect(self.worker.request_get)
        self.source_changed.connect(self.worker.set_source)
        self.worker.preview_ready.connect(self._on_preview_ready)
        self.worker.export_ready.connect(self._on_export_ready)
        self.worker.image_ready.connect(self._set_source)
        self.worker.send_finished.connect(self._on_send_finished)
        self.worker.failed.connect(self._error)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.connection_state.connect(self.set_connection_state)
        self.worker.version_status_ready.connect(self._on_version_status)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.thread.start()

    def shutdown(self) -> None:
        """Stop the render worker thread; safe to call more than once."""
        if self.thread is None:
            return
        thread = self.thread
        if self.worker is not None:
            self.worker.stop_probing()
        thread.quit()
        if not thread.wait(WORKER_STOP_MS):
            LOGGER.warning("the render worker did not stop within %d ms", WORKER_STOP_MS)
            thread.wait()
        self.thread = self.worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """Remember the window geometry and stop the worker thread."""
        self._settings.setValue("geometry", self.saveGeometry())
        self.shutdown()
        super().closeEvent(event)

    def tab_index(self, name: str) -> int:
        """Return the index of the panel tab called name, or -1."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                return index
        return -1

    def replace_tab(self, name: str, widget: QWidget) -> None:
        """Replace the tab called name with widget."""
        index = self.tab_index(name)
        if index < 0:
            raise KeyError(f"unknown tab {name!r}")
        old = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, name)
        self.placeholder_tabs.pop(name, None)
        if old is not None:
            old.deleteLater()

    def set_connection_state(self, state: str) -> None:
        """Show the PhotoCraft connection state in the status bar."""
        self.connection_label.setText(f"PhotoCraft: {state}")

    def set_render_time(self, seconds: float | None) -> None:
        """Show the last render time in the status bar."""
        text = "Render: -" if seconds is None else f"Render: {seconds * 1000.0:.0f} ms"
        self.render_time_label.setText(text)

    def _load_spec(self, spec: PipelineSpec) -> None:
        """Adopt spec as the current pipeline and show it in every panel."""
        self.spec = spec
        for panel in self.panels.values():
            panel.load_from(spec)
        self._request_preview()

    def _rebuild_spec(self) -> None:
        """Write every panel field into the spec owned by the window."""
        for panel in self.panels.values():
            panel.apply_to(self.spec)

    def _request_preview(self) -> None:
        """Hand a copy of the current spec to the worker for a debounced preview."""
        if self.source is None or self.worker is None:
            return
        self._rebuild_spec()
        self.preview_requested.emit(copy.deepcopy(self.spec))

    def _emit_full_render(self, signal: SignalInstance, message: str) -> None:
        """Rebuild the spec and hand a copy to the worker for a full-resolution render."""
        if self.source is None:
            self._error("Load an image first.")
            return
        self._rebuild_spec()
        self.statusBar().showMessage(message)
        signal.emit(copy.deepcopy(self.spec))

    def _set_source(self, image: Image) -> None:
        """Adopt image as the pipeline source and refresh the preview."""
        self.source = np.ascontiguousarray(image, dtype=np.float32)
        self.palette_panel.set_source_image(self.source)
        self.source_changed.emit(self.source)
        self._request_preview()

    def _on_preview_ready(self, result: PreviewResult) -> None:
        """Show a finished preview, dropping results older than the last one shown."""
        if result.job < self._applied_job:
            return
        self._applied_job = result.job
        self.canvas.set_original(result.original)
        self.canvas.set_image(result.image)
        self.set_render_time(result.seconds)

    def _on_export_ready(self, result: RenderResult) -> None:
        """Write a finished full-resolution render to the chosen PNG path."""
        path, self._export_path = self._export_path, None
        if path is None:
            return
        try:
            color.to_pil(result.image).save(path, format="PNG")
        except OSError as exc:
            self._error(f"Cannot write {str(path)!r}: {exc}")
            return
        self.statusBar().showMessage(f"Exported {path.name}", STATUS_MS)

    def _on_send_finished(self, layer: int) -> None:
        """Report the layer created by Send to PhotoCraft."""
        self.statusBar().showMessage(f"Sent to PhotoCraft as layer {layer}", STATUS_MS)

    def _on_version_status(self, status: str, installed: str | None) -> None:
        """Warn once per launch when the installed PhotoCraft version is untested."""
        if status != "untested" or self._version_warned:
            return
        self._version_warned = True
        version = installed or "unknown version"
        self.version_label.setText(
            UNTESTED_WARNING.format(version=version, tested=TESTED_PHOTOCRAFT_VERSION)
        )

    def _on_open_image(self) -> None:
        """Ask for an image file and load it as the pipeline source."""
        path = self._ask_path("Open image", "image_dir", "", IMAGE_FILTER, save=False)
        if path is None:
            return
        try:
            with PILImage.open(path) as handle:
                image = handle.copy()
        except (OSError, ValueError) as exc:
            self._error(f"Cannot open {path!r}: {exc}")
            return
        self._set_source(color.to_float(image))
        self.statusBar().showMessage(f"Loaded {Path(path).name}", STATUS_MS)

    def _on_get_from_photocraft(self) -> None:
        """Fetch the visible PhotoCraft document as the pipeline source."""
        self.get_requested.emit()

    def _on_send_to_photocraft(self) -> None:
        """Render at full resolution and place the result as a new PhotoCraft layer."""
        self._emit_full_render(self.send_requested, "Rendering for PhotoCraft…")

    def _on_export_png(self) -> None:
        """Ask for a PNG path and export the full-resolution render there."""
        if self.source is None:
            self._error("Load an image before exporting.")
            return
        path = self._ask_path("Export PNG", "export_dir", "", PNG_FILTER, save=True)
        if path is None:
            return
        self._export_path = Path(path)
        self._emit_full_render(self.export_requested, "Rendering for export…")

    def _preset_dir(self) -> Path:
        """Return the remembered preset directory, or the project default."""
        stored = self._settings.value("preset_dir")
        return Path(stored) if stored else PRESET_DIR

    def _on_mode(self, mode: str) -> None:
        """Switch the preview canvas to the given mode."""
        self.canvas.set_mode(mode)

    def _error(self, message: str) -> None:
        """Show a modal error box and mirror the message in the status bar."""
        LOGGER.warning("%s", message)
        self.statusBar().showMessage(message, STATUS_MS)
        QMessageBox.critical(self, "DitherCraft", message)

    def _ask_path(
        self, title: str, key: str, name: str, filters: str, *, save: bool
    ) -> str | None:
        """Ask for a file path, remember its directory and return it, or None."""
        base = self._settings.value(key) or (PRESET_DIR if key == "preset_dir" else Path.home())
        dialog = QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName
        path, _ = dialog(self, title, str(Path(base) / name) if name else str(base), filters)
        if path:
            self._settings.setValue(key, str(Path(path).parent))
        return path or None
