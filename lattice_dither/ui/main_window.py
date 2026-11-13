"""Main window: toolbar, preview canvas, panel dock, status bar and render worker."""

from __future__ import annotations

import copy
import logging
import warnings
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QThread, Signal, SignalInstance
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
)
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

import lattice_dither.algorithms  # noqa: F401  (importing the package registers every algorithm)
import lattice_dither.effects  # noqa: F401  (importing the package registers every effect)
from lattice_dither.bridge.photocraft import TESTED_PHOTOCRAFT_VERSION
from lattice_dither.core import color
from lattice_dither.core.pipeline import PipelineSpec
from lattice_dither.core.presets import is_within, shipped_preset_dir, user_preset_dir
from lattice_dither.core.types import RGB8, Image
from lattice_dither.i18n import tr
from lattice_dither.preprocess import descreen, detect_grid, snap_to_grid
from lattice_dither.ui.algorithm_panel import AlgorithmPanel
from lattice_dither.ui.canvas import PreviewCanvas
from lattice_dither.ui.commands import CommandController
from lattice_dither.ui.effects_panel import EffectsPanel
from lattice_dither.ui.gallery import AlgorithmGallery
from lattice_dither.ui.palette_panel import PalettePanel
from lattice_dither.ui.preset_browser import PresetController
from lattice_dither.ui.worker import PreviewResult, RenderResult, RenderWorker

LOGGER = logging.getLogger(__name__)

PANEL_TABS: tuple[str, ...] = ("Algorithm", "Palette", "Effects")
DOCK_MIN_WIDTH = 320
GALLERY_MIN_WIDTH = 240
SETTINGS_NAME = "LatticeDither"
GEOMETRY_KEY = "geometry"
PRESET_DIR = shipped_preset_dir()
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
PNG_FILTER = "PNG images (*.png);;All files (*)"
STATUS_MS = 5000
WORKER_STOP_MS = 5000
# §23: below this confidence the pre-pass must leave the image untouched.
MIN_GRID_CONFIDENCE = 0.5
GRID_FOUND = "Grid: {cell_w}×{cell_h} px, confidence {confidence:.2f}"
GRID_MISSING = "No grid found (confidence {confidence:.2f}); the source is left untouched"
UNTESTED_WARNING = (
    "PhotoCraft {version} not tested with Lattice Dither (tested: {tested}). "
    "Run tools/smoke_photocraft.py."
)


def _disconnect(signal: SignalInstance, slot: object) -> None:
    """Disconnect one slot from a signal, ignoring a connection that is already gone."""
    with warnings.catch_warnings():
        # PySide reports a missing connection as a RuntimeWarning, not an exception.
        warnings.simplefilter("ignore", RuntimeWarning)
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            LOGGER.debug("a signal was already disconnected")


class MainWindow(QMainWindow):
    """Application window owning the pipeline spec and the render worker."""

    preview_requested = Signal(object)
    export_requested = Signal(object)
    send_requested = Signal(object)
    get_requested = Signal()
    source_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Lattice Dither"))
        self.resize(1280, 800)
        self.spec = PipelineSpec()
        self.source: Image | None = None
        self.prepared_source: Image | None = None
        self.worker: RenderWorker | None = None
        self.thread: QThread | None = None
        self._settings = QSettings(SETTINGS_NAME, SETTINGS_NAME)
        self._applied_job = -1
        self._export_path: Path | None = None
        self._version_warned = False
        self._last_image: RGB8 | None = None
        self.canvas = PreviewCanvas(self)
        self.canvas.setAcceptDrops(False)
        self.canvas.viewport().setAcceptDrops(False)
        self.setCentralWidget(self.canvas)
        self.actions: dict[str, QAction] = {}
        self._build_actions()
        self._build_toolbar()
        self.commands = CommandController(self)
        self._build_dock()
        self._build_gallery()
        self._build_status_bar()
        geometry = self._settings.value(GEOMETRY_KEY)
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
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        """Create every toolbar action of the contract and connect its slot."""
        std = QKeySequence.StandardKey
        self._add_action("open_image", tr("Open image"), self._on_open_image, std.Open)
        self._add_action(
            "get_from_photocraft", tr("Get from PhotoCraft"), self._on_get_from_photocraft
        )
        self._add_action(
            "send_to_photocraft", tr("Send to PhotoCraft"), self._on_send_to_photocraft
        )
        self._add_action("export_png", tr("Export PNG"), self._on_export_png, std.Save)
        self.mode_group = QActionGroup(self)
        for key, text, mode in (
            ("mode_before", "Before", "before"),
            ("mode_after", "After", "after"),
            ("mode_split", "Split", "split"),
        ):
            action = self._add_action(key, tr(text), lambda _c=False, m=mode: self._on_mode(m))
            action.setCheckable(True)
            action.setChecked(mode == "after")
            self.mode_group.addAction(action)
        self._add_action("zoom_fit", tr("Zoom Fit"), self.canvas.zoom_fit)
        self._add_action("zoom_100", tr("100 %"), lambda: self.canvas.set_zoom(1.0))
        self._add_action("zoom_200", tr("200 %"), lambda: self.canvas.set_zoom(2.0))
        self._add_action("zoom_400", tr("400 %"), lambda: self.canvas.set_zoom(4.0))
        for key, text in (("prepare_source", "Prepare source"), ("descreen", "Descreen")):
            action = self._add_action(key, tr(text), self._on_prepare_toggled)
            action.setCheckable(True)
            action.setChecked(False)
        self.presets = PresetController(self)

    def _build_toolbar(self) -> None:
        """Create the main toolbar with the actions in contract order."""
        self.toolbar = QToolBar(tr("Main"), self)
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        groups = (
            ("open_image", "get_from_photocraft", "send_to_photocraft", "export_png"),
            ("preset_prev", "load_preset", "save_preset", "preset_next"),
            ("mode_before", "mode_after", "mode_split"),
            ("zoom_fit", "zoom_100", "zoom_200", "zoom_400"),
            ("prepare_source", "descreen"),
        )
        for index, keys in enumerate(groups):
            if index:
                self.toolbar.addSeparator()
            for key in keys:
                self.toolbar.addAction(self.actions[key])

    def _build_dock(self) -> None:
        """Create the right dock holding the algorithm, palette and effects panels."""
        self.dock = QDockWidget(tr("Panels"), self)
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
            self.tabs.addTab(panel, tr(name))
            panel.changed.connect(self.commands.on_panels_changed)
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumWidth(DOCK_MIN_WIDTH)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _build_gallery(self) -> None:
        """Create the algorithm gallery in its own dock and connect its choice signal."""
        self.gallery = AlgorithmGallery(self)
        self.gallery_dock = QDockWidget(tr("Gallery"), self)
        self.gallery_dock.setObjectName("gallery_dock")
        self.gallery_dock.setWidget(self.gallery)
        self.gallery_dock.setMinimumWidth(GALLERY_MIN_WIDTH)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.gallery_dock)
        self.gallery.algorithm_chosen.connect(self._on_algorithm_chosen)

    def _build_status_bar(self) -> None:
        """Create the status bar with the connection state, render time and grid labels."""
        bar = self.statusBar()
        self.connection_label = QLabel(tr("PhotoCraft: unknown"), self)
        self.connection_label.setObjectName("connection_label")
        self.render_time_label = QLabel(tr("Render: -"), self)
        self.render_time_label.setObjectName("render_time_label")
        self.grid_label = QLabel(self)
        self.grid_label.setObjectName("grid_label")
        self.version_label = QLabel(self)
        self.version_label.setObjectName("version_warning")
        labels = (
            self.connection_label,
            self.render_time_label,
            self.grid_label,
            self.presets.label,
        )
        for label in (*labels, self.version_label):
            bar.addPermanentWidget(label)
        bar.showMessage(tr("Ready"))

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
        """Stop the render worker and the gallery threads; safe to call more than once."""
        if self.thread is not None:
            thread = self.thread
            if self.worker is not None:
                self.worker.stop_probing()
            thread.quit()
            if not thread.wait(WORKER_STOP_MS):
                LOGGER.warning("the render worker did not stop within %d ms", WORKER_STOP_MS)
                thread.wait()
            self.thread = self.worker = None
        self.gallery.shutdown()
        self._release_hooks()

    def _release_hooks(self) -> None:
        """Detach the application-wide hooks this window installed.

        The preset controller is an application-wide event filter and ``aboutToQuit``
        keeps a reference to the window, so without this every closed window stays
        registered and every later event is filtered by one more dead controller. The
        window itself is deliberately left reachable: PySide never calls ``__del__`` on a
        widget, so a window that is collected without ``close()`` would take a running
        ``QThread`` with it and corrupt the heap.
        """
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self.presets)
            _disconnect(app.aboutToQuit, self.shutdown)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Remember the window geometry and stop the worker thread."""
        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        self.shutdown()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept a drag that carries at least one image file."""
        self.commands.drag_enter(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Open the first image of a drop, ignoring anything else."""
        self.commands.drop(event)

    def tab_index(self, name: str) -> int:
        """Return the index of the panel tab called name, or -1."""
        wanted = tr(name)
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == wanted:
                return index
        return -1

    def replace_tab(self, name: str, widget: QWidget) -> None:
        """Replace the tab called name with widget."""
        index = self.tab_index(name)
        if index < 0:
            raise KeyError(f"unknown tab {name!r}")
        old = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, tr(name))
        self.placeholder_tabs.pop(name, None)
        if old is not None:
            old.deleteLater()

    def set_connection_state(self, state: str) -> None:
        """Show the PhotoCraft connection state in the status bar."""
        self.connection_label.setText(tr("PhotoCraft: {state}", state=tr(state)))

    def set_render_time(self, seconds: float | None) -> None:
        """Show the last render time in the status bar."""
        if seconds is None:
            text = tr("Render: -")
        else:
            text = tr("Render: {ms} ms", ms=f"{seconds * 1000.0:.0f}")
        self.render_time_label.setText(text)

    def _load_spec(self, spec: PipelineSpec, *, record: bool = True) -> None:
        """Adopt spec as the current pipeline and show it in every panel."""
        self.spec = spec
        for panel in self.panels.values():
            panel.load_from(spec)
        if record:
            self.commands.record(spec, coalesce=False)
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
            self._error(tr("Load an image first."))
            return
        self._rebuild_spec()
        self.statusBar().showMessage(message)
        signal.emit(copy.deepcopy(self.spec))

    def _set_source(self, image: Image) -> None:
        """Adopt image as the pipeline source and refresh the preview."""
        self.source = np.ascontiguousarray(image, dtype=np.float32)
        self._refresh_source()

    def _refresh_source(self) -> None:
        """Recompute the prepared source and hand it to the palette panel and the worker."""
        prepared = self._prepare_source(self.source)
        self.prepared_source = prepared
        if prepared is not None:
            self.palette_panel.set_source_image(prepared)
        self.source_changed.emit(prepared)
        self._request_preview()

    def _prepare_source(self, image: Image | None) -> Image | None:
        """Run the optional §23 pre-pass, reporting the grid before it is applied."""
        if image is None:
            return None
        prepare = self.actions["prepare_source"].isChecked()
        screen = self.actions["descreen"].isChecked()
        if not prepare and not screen:
            self.grid_label.clear()
            return image
        cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(image)
        self.grid_label.setText(self._grid_report(cell_w, cell_h, confidence))
        if confidence < MIN_GRID_CONFIDENCE:
            return image
        out = snap_to_grid(image, (cell_w, cell_h, offset_x, offset_y)) if prepare else image
        if screen:
            out = descreen(out)
        return np.ascontiguousarray(out, dtype=np.float32)

    def _grid_report(self, cell_w: int, cell_h: int, confidence: float) -> str:
        """Return the status text describing the detected lattice and its confidence."""
        if confidence < MIN_GRID_CONFIDENCE:
            return tr(GRID_MISSING, confidence=confidence)
        return tr(GRID_FOUND, cell_w=cell_w, cell_h=cell_h, confidence=confidence)

    def _on_prepare_toggled(self, _checked: bool = False) -> None:
        """Re-run the pre-pass on the current source after a toggle changed."""
        if self.source is not None:
            self._refresh_source()

    def _on_algorithm_chosen(self, algorithm_id: str) -> None:
        """Select the algorithm picked in the gallery, exactly as the combo would."""
        combo = self.algorithm_panel.algorithm_combo
        index = combo.findData(algorithm_id)
        if index < 0:
            LOGGER.warning("the gallery chose an unknown algorithm %r", algorithm_id)
            return
        combo.setCurrentIndex(index)

    def _on_preview_ready(self, result: PreviewResult) -> None:
        """Show a finished preview, dropping results older than the last one shown."""
        if result.job < self._applied_job:
            return
        self._applied_job = result.job
        self._last_image = result.image
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
            self._error(tr("Cannot write {path}: {error}", path=repr(str(path)), error=str(exc)))
            return
        self.statusBar().showMessage(tr("Exported {name}", name=path.name), STATUS_MS)

    def _on_send_finished(self, layer: int) -> None:
        """Report the layer created by Send to PhotoCraft."""
        message = tr("Sent to PhotoCraft as layer {layer}", layer=layer)
        self.statusBar().showMessage(message, STATUS_MS)

    def _on_version_status(self, status: str, installed: str | None) -> None:
        """Warn once per launch when the installed PhotoCraft version is untested."""
        if status != "untested" or self._version_warned:
            return
        self._version_warned = True
        version = installed or tr("unknown version")
        self.version_label.setText(
            tr(UNTESTED_WARNING, version=version, tested=TESTED_PHOTOCRAFT_VERSION)
        )

    def _on_open_image(self) -> None:
        """Ask for an image file and load it as the pipeline source."""
        path = self._ask_path(tr("Open image"), "image_dir", "", tr(IMAGE_FILTER), save=False)
        if path is not None:
            self.commands.open_path(path)

    def _on_get_from_photocraft(self) -> None:
        """Fetch the visible PhotoCraft document as the pipeline source."""
        self.get_requested.emit()

    def _on_send_to_photocraft(self) -> None:
        """Render at full resolution and place the result as a new PhotoCraft layer."""
        self._emit_full_render(self.send_requested, tr("Rendering for PhotoCraft…"))

    def _on_export_png(self) -> None:
        """Ask for a PNG path and export the full-resolution render there."""
        if self.source is None:
            self._error(tr("Load an image before exporting."))
            return
        path = self._ask_path(tr("Export PNG"), "export_dir", "", tr(PNG_FILTER), save=True)
        if path is None:
            return
        self._export_path = Path(path)
        self._emit_full_render(self.export_requested, tr("Rendering for export…"))

    def _preset_dirs(self) -> tuple[Path, ...]:
        """Return the preset search order: the shipped presets first, then the user ones."""
        return (PRESET_DIR, user_preset_dir())

    def _preset_dir(self) -> Path:
        """Return the directory presets are saved to: the user one, never the shipped one."""
        return user_preset_dir()

    def _on_mode(self, mode: str) -> None:
        """Switch the preview canvas to the given mode."""
        self.canvas.set_mode(mode)

    def _error(self, message: str) -> None:
        """Show a modal error box and mirror the message in the status bar."""
        LOGGER.warning("%s", message)
        self.statusBar().showMessage(message, STATUS_MS)
        QMessageBox.critical(self, tr("Lattice Dither"), message)

    def _ask_path(self, title: str, key: str, name: str, filters: str, *, save: bool) -> str | None:
        """Ask for a file path, remember its directory and return it, or None."""
        base = self._dialog_dir(key)
        dialog = QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName
        path, _ = dialog(self, title, str(Path(base) / name) if name else str(base), filters)
        if path:
            self._settings.setValue(key, str(Path(path).parent))
        return path or None

    def _dialog_dir(self, key: str) -> Path:
        """Return the directory a file dialog opens in, keeping presets out of the shipped tier."""
        stored = self._settings.value(key)
        if key == "preset_dir":
            if stored and not is_within(str(stored), PRESET_DIR):
                return Path(stored)
            user = self._preset_dir()
            return user if user.is_dir() else PRESET_DIR
        return Path(stored) if stored else Path.home()
