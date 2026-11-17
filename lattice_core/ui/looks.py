"""Shared Looks grid: one thumbnail per look, rendered on the current image.

A "look" is a named pipeline variant. Thumbnails are rendered on a helper
thread from the current source, so every thumbnail shows what that look does to
the image that is actually loaded. The gallery keeps an in-memory cache keyed
by look id, cleared whenever the source changes.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from lattice_core import color
from lattice_core.pipeline import PipelineSpec, render
from lattice_core.types import RGB8, Image
from lattice_core.ui.worker import _downscale_strips, proxy_factor

LOGGER = logging.getLogger(__name__)

THUMB_SIZE = 96
THUMB_COLUMNS = 4
THUMB_SOURCE_SIDE = 512
PLACEHOLDER_COLOR = "#2a2a30"
JOIN_MS = 2000
FAILED_TIP = "{name}: {message}"


@dataclass(frozen=True)
class Look:
    """One named pipeline variant shown in the Looks grid."""

    id: str
    name: str
    spec: PipelineSpec


def _resize(rgb8: RGB8, size: int) -> RGB8:
    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
    if rgb8.shape[:2] == (size, size):
        return np.ascontiguousarray(rgb8, dtype=np.uint8)
    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))


def render_look_thumbnail(look: Look, source: Image, size: int = THUMB_SIZE) -> RGB8:
    """Render look on the source proxy and return a size×size thumbnail."""
    proxy = color.to_rgb8(_downscale_strips(source, proxy_factor(source, THUMB_SOURCE_SIDE)))
    return _resize(color.to_rgb8(render(proxy, look.spec)), size)


def _pixmap(rgb8: RGB8) -> QPixmap:
    """Return a QPixmap copy of a uint8 RGB array."""
    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
    # QImage wraps the buffer instead of copying it, so the bytes must outlive the image.
    buffer = data.tobytes()
    image = QImage(buffer, data.shape[1], data.shape[0], QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


class LookThumbnailWorker(QObject):
    """Renders look thumbnails on a helper thread and reports them by signal."""

    thumbnail_ready = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, size: int = THUMB_SIZE) -> None:
        super().__init__()
        self._size = int(size)

    @Slot(str, object, object)
    def build(self, look_id: str, spec: PipelineSpec, source: Image) -> None:
        """Render one thumbnail and emit it; this slot never touches a widget."""
        try:
            rgb8 = render_look_thumbnail(Look(look_id, "", spec), source, self._size)
        except Exception as exc:  # noqa: BLE001 - one broken look must not stop the rest
            LOGGER.exception("look %s failed", look_id)
            self.failed.emit(look_id, str(exc))
            return
        self.thumbnail_ready.emit(look_id, rgb8)


_ACTIVE_WORKERS: set[LookThumbnailWorker] = set()
# A QThread that outlived its join timeout must not be destroyed while it still runs.
_ORPHAN_THREADS: set[QThread] = set()


def _release_worker(gallery: LookGallery, worker: LookThumbnailWorker) -> None:
    """Drop every reference the gallery and this module keep to a stopped worker.

    Without this the worker stays in ``_ACTIVE_WORKERS`` and its signal
    connections keep the gallery, and through it the whole window, alive.
    """
    worker.thumbnail_ready.disconnect(gallery._on_thumbnail_ready)
    worker.failed.disconnect(gallery._on_thumbnail_failed)
    gallery._request.disconnect(worker.build)
    _ACTIVE_WORKERS.discard(worker)


class LookCell(QWidget):
    """One gallery cell: a thumbnail above the look name."""

    clicked = Signal(str)

    def __init__(self, look: Look, size: int = THUMB_SIZE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.look_id = look.id
        self.setObjectName(f"look_cell_{look.id}")
        self.setToolTip(look.name)
        self.image_label = QLabel(self)
        self.image_label.setObjectName("look_thumb")
        self.image_label.setFixedSize(size, size)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel(look.name, self)
        self.name_label.setObjectName("look_name")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)
        self._placeholder = QPixmap(size, size)
        self._placeholder.fill(QColor(PLACEHOLDER_COLOR))
        self._ready = False
        self.show_placeholder()

    def has_thumbnail(self) -> bool:
        """Return True once a rendered thumbnail has replaced the placeholder."""
        return self._ready

    def show_placeholder(self) -> None:
        """Show the neutral placeholder instead of a thumbnail."""
        self.image_label.setPixmap(self._placeholder)
        self._ready = False

    def set_thumbnail(self, rgb8: RGB8) -> None:
        """Show rgb8 as this cell's thumbnail; call it from the GUI thread only."""
        self.image_label.setPixmap(_pixmap(rgb8))
        self._ready = True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Report the look of the cell when it is clicked."""
        self.clicked.emit(self.look_id)
        super().mousePressEvent(event)


class LookGallery(QWidget):
    """Grid of look thumbnails rendered on the current image."""

    look_chosen = Signal(str)
    _request = Signal(str, object, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        size: int = THUMB_SIZE,
        columns: int = THUMB_COLUMNS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("look_gallery")
        self._size = int(size)
        self._columns = max(1, int(columns))
        self._looks: dict[str, Look] = {}
        self._cells: list[LookCell] = []
        self._cache: dict[str, RGB8] = {}
        self._source: Image | None = None
        self._thread: QThread | None = None
        self._worker: LookThumbnailWorker | None = None
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addLayout(self.grid)
        outer.addStretch(1)
        self._apply_layout("")

    def cells(self) -> list[LookCell]:
        """Return every cell of the gallery, in the order the looks were set."""
        return list(self._cells)

    def looks(self) -> list[Look]:
        """Return the looks of the gallery, in display order."""
        return [self._looks[cell.look_id] for cell in self._cells]

    def set_looks(self, looks: Sequence[Look]) -> None:
        """Replace the gallery with looks, in order, and re-queue every thumbnail."""
        self._clear_cells()
        for look in looks:
            self._looks[look.id] = look
            cell = LookCell(look, self._size, self)
            cell.clicked.connect(self.look_chosen)
            self._cells.append(cell)
        self._apply_layout("")
        self._queue_thumbnails()

    def set_source(self, image: Image | None) -> None:
        """Set the current image; every thumbnail is re-rendered on it."""
        self._source = None if image is None else np.ascontiguousarray(image, dtype=np.float32)
        self._cache.clear()
        for cell in self._cells:
            cell.show_placeholder()
        self._queue_thumbnails()

    def shutdown(self) -> None:
        """Stop the helper thread and release its worker; safe to call more than once."""
        thread, worker = self._thread, self._worker
        self._thread = self._worker = None
        if thread is None:
            return
        if worker is not None:
            _release_worker(self, worker)
        thread.quit()
        if not thread.wait(JOIN_MS):
            LOGGER.warning("the look thread did not stop within %d ms", JOIN_MS)
            _ORPHAN_THREADS.add(thread)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the helper thread before the widget goes away."""
        self.shutdown()
        super().closeEvent(event)

    def _clear_cells(self) -> None:
        """Delete every cell and empty the grid."""
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._cells.clear()
        self._looks.clear()
        self._cache.clear()

    def _apply_layout(self, _filter: str) -> None:
        """Place the cells in the grid, columns per row."""
        while self.grid.count():
            self.grid.takeAt(0)
        for index, cell in enumerate(self._cells):
            self.grid.addWidget(cell, index // self._columns, index % self._columns)

    def _ensure_worker(self) -> LookThumbnailWorker:
        """Create the helper thread and its worker on first use."""
        if self._worker is not None:
            return self._worker
        thread = QThread()
        worker = LookThumbnailWorker(self._size)
        worker.moveToThread(thread)
        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        worker.failed.connect(self._on_thumbnail_failed)
        self._request.connect(worker.build)
        _ACTIVE_WORKERS.add(worker)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: _ACTIVE_WORKERS.discard(worker))
        thread.start()
        self._thread, self._worker = thread, worker
        return worker

    def _queue_thumbnails(self) -> None:
        """Ask the worker for every cell's thumbnail, cache hits included."""
        source = self._source
        if not self._cells or source is None:
            return
        self._ensure_worker()
        for cell in self._cells:
            if cell.look_id in self._cache:
                cell.set_thumbnail(self._cache[cell.look_id])
                continue
            self._request.emit(cell.look_id, self._looks[cell.look_id].spec, source)

    @Slot(str, object)
    def _on_thumbnail_ready(self, look_id: str, rgb8: object) -> None:
        """Show a finished thumbnail; this slot runs on the GUI thread."""
        cell = next((cell for cell in self._cells if cell.look_id == look_id), None)
        if cell is None:
            return
        image = np.ascontiguousarray(np.asarray(rgb8, dtype=np.uint8))
        self._cache[look_id] = image
        cell.set_thumbnail(image)

    @Slot(str, str)
    def _on_thumbnail_failed(self, look_id: str, message: str) -> None:
        """Keep the placeholder of a cell whose thumbnail could not be rendered."""
        cell = next((cell for cell in self._cells if cell.look_id == look_id), None)
        if cell is not None:
            cell.setToolTip(FAILED_TIP.format(name=cell.look_id, message=message))


__all__ = ["Look", "LookCell", "LookGallery", "render_look_thumbnail", "THUMB_SIZE"]
