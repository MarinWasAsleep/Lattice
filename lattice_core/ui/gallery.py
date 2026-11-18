"""Shared reference gallery widget: every registered algorithm and renderer, side by side.

One cell per algorithm and per renderer of the core registries, rendered on the current
source (the deterministic reference image when none is loaded) on a helper thread, plus
a Save PNG button that writes the single contact sheet through ``lattice_core.gallery``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lattice_core import color
from lattice_core.gallery import (
    DEFAULT_PALETTE,
    GalleryEntry,
    gallery_entries,
    reference_image,
    save_gallery,
    square_proxy,
)
from lattice_core.pipeline import PipelineSpec, render
from lattice_core.types import RGB8, Image

LOGGER = logging.getLogger(__name__)

THUMB_SIZE = 96
THUMB_COLUMNS = 6
PLACEHOLDER_COLOR = "#2a2a30"
JOIN_MS = 2000
FAILED_TIP = "{name}: {message}"
SAVE_FILTER = "PNG image (*.png)"
SAVE_DEFAULT_NAME = "gallery.png"


def render_entry_thumbnail(spec: PipelineSpec, source: Image, size: int = THUMB_SIZE) -> RGB8:
    """Render one gallery entry on a square proxy of the source and return size×size."""
    proxy = square_proxy(source, size * 2)
    return _resize(render(proxy, spec), size)


def _resize(rgb8: RGB8, size: int) -> RGB8:
    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
    if rgb8.shape[:2] == (size, size):
        return np.ascontiguousarray(rgb8, dtype=np.uint8)
    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))


def _pixmap(rgb8: RGB8) -> QPixmap:
    """Return a QPixmap copy of a uint8 RGB array."""
    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
    # QImage wraps the buffer instead of copying it, so the bytes must outlive the image.
    buffer = data.tobytes()
    image = QImage(buffer, data.shape[1], data.shape[0], QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


class GalleryWorker(QObject):
    """Renders gallery thumbnails on a helper thread and reports them by signal."""

    thumbnail_ready = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, size: int = THUMB_SIZE) -> None:
        super().__init__()
        self._size = int(size)

    @Slot(str, object, object)
    def build(self, entry_id: str, spec: PipelineSpec, source: Image) -> None:
        """Render one thumbnail and emit it; this slot never touches a widget."""
        try:
            rgb8 = render_entry_thumbnail(spec, source, self._size)
        except Exception as exc:  # noqa: BLE001 - one broken entry must not stop the rest
            LOGGER.exception("gallery entry %s failed", entry_id)
            self.failed.emit(entry_id, str(exc))
            return
        self.thumbnail_ready.emit(entry_id, rgb8)


_ACTIVE_WORKERS: set[GalleryWorker] = set()
# A QThread that outlived its join timeout must not be destroyed while it still runs.
_ORPHAN_THREADS: set[QThread] = set()


def _release_worker(gallery: ReferenceGallery, worker: GalleryWorker) -> None:
    """Drop every reference the gallery and this module keep to a stopped worker."""
    worker.thumbnail_ready.disconnect(gallery._on_thumbnail_ready)
    worker.failed.disconnect(gallery._on_thumbnail_failed)
    gallery._request.disconnect(worker.build)
    _ACTIVE_WORKERS.discard(worker)


class GalleryCell(QWidget):
    """One gallery cell: a thumbnail above the entry label."""

    clicked = Signal(str)

    def __init__(self, entry: GalleryEntry, size: int = THUMB_SIZE,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry_id = entry.id
        self.setObjectName(f"gallery_cell_{entry.id.replace(':', '_')}")
        self.setToolTip(entry.label)
        self.image_label = QLabel(self)
        self.image_label.setObjectName("gallery_thumb")
        self.image_label.setFixedSize(size, size)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel(entry.label, self)
        self.name_label.setObjectName("gallery_name")
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
        """Report the entry of the cell when it is clicked."""
        self.clicked.emit(self.entry_id)
        super().mousePressEvent(event)


class ReferenceGallery(QWidget):
    """Grid of every registered algorithm and renderer on one reference image."""

    cell_chosen = Signal(str)
    _request = Signal(str, object, object)

    def __init__(self, parent: QWidget | None = None, *, size: int = THUMB_SIZE,
                 columns: int = THUMB_COLUMNS, palette: str = DEFAULT_PALETTE) -> None:
        super().__init__(parent)
        self.setObjectName("reference_gallery")
        self._size = int(size)
        self._columns = max(1, int(columns))
        self._entries: dict[str, GalleryEntry] = {}
        self._cells: list[GalleryCell] = []
        self._cache: dict[str, RGB8] = {}
        self._source: Image = reference_image()
        self._thread: QThread | None = None
        self._worker: GalleryWorker | None = None
        self.save_button = QPushButton("Save PNG…", self)
        self.save_button.setObjectName("gallery_save")
        self.save_button.clicked.connect(self._ask_save)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Reference gallery", self))
        toolbar.addStretch(1)
        toolbar.addWidget(self.save_button)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addLayout(toolbar)
        outer.addLayout(self.grid)
        outer.addStretch(1)
        self._build_cells(gallery_entries(palette=palette))
        self._queue_thumbnails()

    def cells(self) -> list[GalleryCell]:
        """Return every cell of the gallery, in display order."""
        return list(self._cells)

    def entries(self) -> list[GalleryEntry]:
        """Return the gallery entries, in display order."""
        return [self._entries[cell.entry_id] for cell in self._cells]

    def set_source(self, image: Image | None) -> None:
        """Set the current image; None restores the reference image and re-renders all."""
        self._source = (reference_image() if image is None
                        else np.ascontiguousarray(image, dtype=np.float32))
        self._cache.clear()
        for cell in self._cells:
            cell.show_placeholder()
        self._queue_thumbnails()

    def save_png(self, path: str | Path) -> Path:
        """Write the whole gallery as one contact-sheet PNG under 4 MB."""
        return save_gallery(path, self._source)

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
            LOGGER.warning("the gallery thread did not stop within %d ms", JOIN_MS)
            _ORPHAN_THREADS.add(thread)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the helper thread before the widget goes away."""
        self.shutdown()
        super().closeEvent(event)

    def _build_cells(self, entries: list[GalleryEntry]) -> None:
        """Create one cell per entry and place them in the grid, columns per row."""
        for index, entry in enumerate(entries):
            self._entries[entry.id] = entry
            cell = GalleryCell(entry, self._size, self)
            cell.clicked.connect(self.cell_chosen)
            self._cells.append(cell)
            self.grid.addWidget(cell, index // self._columns, index % self._columns)

    def _ask_save(self) -> None:
        """Ask for a PNG path and write the contact sheet there."""
        path, _filter = QFileDialog.getSaveFileName(self, "Save gallery", SAVE_DEFAULT_NAME,
                                                    SAVE_FILTER)
        if path:
            self.save_png(path)

    def _ensure_worker(self) -> GalleryWorker:
        """Create the helper thread and its worker on first use."""
        if self._worker is not None:
            return self._worker
        thread = QThread()
        worker = GalleryWorker(self._size)
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
        if not self._cells:
            return
        self._ensure_worker()
        for cell in self._cells:
            if cell.entry_id in self._cache:
                cell.set_thumbnail(self._cache[cell.entry_id])
                continue
            self._request.emit(cell.entry_id, self._entries[cell.entry_id].spec, self._source)

    @Slot(str, object)
    def _on_thumbnail_ready(self, entry_id: str, rgb8: object) -> None:
        """Show a finished thumbnail; this slot runs on the GUI thread."""
        cell = next((cell for cell in self._cells if cell.entry_id == entry_id), None)
        if cell is None:
            return
        image = np.ascontiguousarray(np.asarray(rgb8, dtype=np.uint8))
        self._cache[entry_id] = image
        cell.set_thumbnail(image)

    @Slot(str, str)
    def _on_thumbnail_failed(self, entry_id: str, message: str) -> None:
        """Keep the placeholder of a cell whose thumbnail could not be rendered."""
        cell = next((cell for cell in self._cells if cell.entry_id == entry_id), None)
        if cell is not None:
            cell.setToolTip(FAILED_TIP.format(name=entry_id, message=message))


__all__ = [
    "THUMB_SIZE",
    "GalleryCell",
    "GalleryWorker",
    "ReferenceGallery",
    "render_entry_thumbnail",
]
