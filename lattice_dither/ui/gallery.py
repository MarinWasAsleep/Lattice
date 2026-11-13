"""Algorithm gallery: a grid of cached 96x96 thumbnails with a search box.

Thumbnails render on a helper thread through the same worker pattern as ``ui/worker.py``:
the worker only emits signals and every widget update happens in a slot on the GUI thread.
The cache lives in ``%LOCALAPPDATA%/LatticeDither/thumbs/``, keyed by
``(algorithm_id, params_hash, palette_hash)``, so a changed key regenerates the image.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import unicodedata
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from lattice_dither.core import color
from lattice_dither.core.pipeline import PaletteSpec, PipelineSpec, render
from lattice_dither.core.registry import AlgorithmInfo, list_algorithms
from lattice_dither.core.types import RGB8, Image
from lattice_dither.i18n import tr

LOGGER = logging.getLogger(__name__)

THUMB_SIZE = 96
THUMB_COLUMNS = 4
APP_DIR_NAME = "LatticeDither"
THUMB_DIR_NAME = "thumbs"
CACHE_SUFFIX = ".png"
DEFAULT_PALETTE = "pico8"
TEST_IMAGE_SIZE = 200
HASH_LENGTH = 12
PLACEHOLDER_COLOR = "#2a2a30"
JOIN_MS = 2000
CELL_TIP = "{name} ({family})"
FAILED_TIP = "{name}: {message}"


def thumbs_dir() -> Path:
    """Return %LOCALAPPDATA%/LatticeDither/thumbs, the thumbnail cache directory."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / APP_DIR_NAME / THUMB_DIR_NAME


def test_image() -> Image:
    """Build the fixed synthetic test image: gradients, discs and a checkerboard."""
    size = TEST_IMAGE_SIZE
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    u = xs / (size - 1)
    v = ys / (size - 1)
    img = np.empty((size, size, 3), dtype=np.float32)
    img[:, :, 0] = 0.15 + 0.8 * u
    img[:, :, 1] = 0.15 + 0.8 * v
    img[:, :, 2] = 0.15 + 0.7 * (1.0 - u) * (1.0 - v)
    for cx, cy, radius, colour in (
        (0.28, 0.30, 0.16, (1.0, 0.95, 0.2)),
        (0.72, 0.34, 0.13, (0.1, 0.9, 1.0)),
        (0.50, 0.74, 0.19, (1.0, 0.25, 0.55)),
    ):
        mask = (u - cx) ** 2 + (v - cy) ** 2 < radius * radius
        for channel in range(3):
            img[:, :, channel] = np.where(mask, colour[channel], img[:, :, channel])
    checker = ((xs // 12 + ys // 12) % 2).astype(np.float32)
    band = (v > 0.86) & (v < 0.96)
    for channel in range(3):
        img[:, :, channel] = np.where(band, checker * 0.9 + 0.05, img[:, :, channel])
    return np.ascontiguousarray(np.clip(img, 0.0, 1.0).astype(np.float32))


def _digest(payload: object) -> str:
    """Return a short stable hex digest of a JSON-serialisable payload."""
    text = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha1(text).hexdigest()[:HASH_LENGTH]


def params_hash(params: dict) -> str:
    """Return the stable hash of an algorithm parameter mapping."""
    return _digest(dict(params))


def palette_hash(palette: PaletteSpec) -> str:
    """Return the stable hash of every field of a palette spec."""
    return _digest(asdict(palette))


def cache_key(algorithm_id: str, params: dict, palette: PaletteSpec) -> str:
    """Return the cache key of one thumbnail: algorithm id, params hash and palette hash."""
    return f"{algorithm_id}-{params_hash(params)}-{palette_hash(palette)}"


def family_label(family: str) -> str:
    """Return the human-readable form of a registry family name."""
    return family.replace("_", " ")


def fold(text: str) -> str:
    """Return text lowercased and stripped of accents, for accent-insensitive search."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _resize(rgb8: RGB8, size: int) -> RGB8:
    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
    if rgb8.shape[:2] == (size, size):
        return np.ascontiguousarray(rgb8, dtype=np.uint8)
    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))


def render_thumbnail(
    algorithm_id: str, params: dict, palette: PaletteSpec, size: int = THUMB_SIZE
) -> RGB8:
    """Render the fixed test image with one algorithm and return a size×size thumbnail."""
    spec = PipelineSpec()
    spec.algorithm_id = algorithm_id
    spec.algorithm_params = dict(params)
    spec.palette = palette
    spec.pixel_size = 1
    return _resize(color.to_rgb8(render(test_image(), spec)), size)


def _read_thumbnail(path: Path, size: int) -> RGB8 | None:
    """Return the cached thumbnail at path, or None when it is missing or unreadable."""
    if not path.is_file():
        return None
    try:
        with PILImage.open(path) as image:
            return _resize(np.asarray(image.convert("RGB"), dtype=np.uint8), size)
    except (OSError, ValueError):
        LOGGER.warning("ignoring the unreadable thumbnail cache file %s", path)
        return None


def _write_thumbnail(path: Path, rgb8: RGB8) -> None:
    """Write rgb8 to path as a PNG, ignoring a cache directory that cannot be written."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        color.to_pil(rgb8).save(path, format="PNG")
    except OSError:
        LOGGER.warning("cannot write the thumbnail cache file %s", path, exc_info=True)


def thumbnail_for(
    key: str,
    algorithm_id: str,
    params: dict,
    palette: PaletteSpec,
    cache_dir: Path,
    size: int = THUMB_SIZE,
) -> RGB8:
    """Return the cached thumbnail for key, rendering and caching it when it is absent."""
    path = Path(cache_dir) / f"{key}{CACHE_SUFFIX}"
    cached = _read_thumbnail(path, size)
    if cached is not None:
        return cached
    rgb8 = render_thumbnail(algorithm_id, params, palette, size)
    _write_thumbnail(path, rgb8)
    return rgb8


def _pixmap(rgb8: RGB8) -> QPixmap:
    """Return a QPixmap copy of a uint8 RGB array."""
    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
    # QImage wraps the buffer instead of copying it, so the bytes must outlive the image.
    buffer = data.tobytes()
    image = QImage(buffer, data.shape[1], data.shape[0], QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


class ThumbnailWorker(QObject):
    """Renders gallery thumbnails on a helper thread and reports them by signal."""

    thumbnail_ready = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, cache_dir: Path, size: int = THUMB_SIZE) -> None:
        super().__init__()
        self._cache_dir = Path(cache_dir)
        self._size = int(size)

    @Slot(str, str, object, object)
    def build(self, key: str, algorithm_id: str, params: dict, palette: PaletteSpec) -> None:
        """Load or render one thumbnail and emit it; this slot never touches a widget."""
        try:
            rgb8 = thumbnail_for(key, algorithm_id, params, palette, self._cache_dir, self._size)
        except Exception as exc:  # noqa: BLE001 - one broken thumbnail must not stop the rest
            LOGGER.exception("thumbnail %s failed", key)
            self.failed.emit(key, str(exc))
            return
        self.thumbnail_ready.emit(key, rgb8)


_ACTIVE_WORKERS: set[ThumbnailWorker] = set()
# A QThread that outlived its join timeout must not be destroyed while it still runs, so
# the module keeps it alive instead. Destroying a running QThread corrupts the heap.
_ORPHAN_THREADS: set[QThread] = set()


def _release_worker(gallery: AlgorithmGallery, worker: ThumbnailWorker) -> None:
    """Drop every reference the gallery and this module keep to a stopped worker.

    Without this the worker stays in ``_ACTIVE_WORKERS`` and its signal connections keep
    the gallery, and through it the whole window, alive after the window is closed.
    """
    for signal, slot in (
        (worker.thumbnail_ready, gallery._on_thumbnail_ready),
        (worker.failed, gallery._on_thumbnail_failed),
    ):
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            LOGGER.debug("a thumbnail signal was already disconnected")
    try:
        gallery._request.disconnect(worker.build)
    except (RuntimeError, TypeError):
        LOGGER.debug("the thumbnail request signal was already disconnected")
    _ACTIVE_WORKERS.discard(worker)


class ThumbnailCell(QWidget):
    """One gallery cell: a thumbnail above the algorithm name."""

    clicked = Signal(str)

    def __init__(
        self, info: AlgorithmInfo, size: int = THUMB_SIZE, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.algorithm_id = info.id
        self.family = info.family
        self.name = info.name
        self.haystack = fold(f"{info.name} {info.family} {info.family.replace('_', ' ')}")
        self.setObjectName(f"gallery_cell_{info.id}")
        self.setToolTip(tr(CELL_TIP, name=tr(info.name), family=tr(family_label(info.family))))
        self.image_label = QLabel(self)
        self.image_label.setObjectName("gallery_thumb")
        self.image_label.setFixedSize(size, size)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel(tr(info.name), self)
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
        """Report the algorithm of the cell when it is clicked."""
        self.clicked.emit(self.algorithm_id)
        super().mousePressEvent(event)


class AlgorithmGallery(QWidget):
    """Grid of algorithm thumbnails with a search box filtering by name and family."""

    algorithm_chosen = Signal(str)
    _request = Signal(str, str, object, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        cache_dir: Path | None = None,
        palette: PaletteSpec | None = None,
        size: int = THUMB_SIZE,
        columns: int = THUMB_COLUMNS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("algorithm_gallery")
        self._cache_dir = Path(cache_dir) if cache_dir is not None else thumbs_dir()
        self._palette = palette or PaletteSpec(source="builtin", name=DEFAULT_PALETTE)
        self._size = int(size)
        self._columns = max(1, int(columns))
        self._cells: list[ThumbnailCell] = []
        self._visible: list[ThumbnailCell] = []
        self._by_key: dict[str, ThumbnailCell] = {}
        self._query = ""
        self._thread: QThread | None = None
        self._worker: ThumbnailWorker | None = None
        self.search_box = QLineEdit(self)
        self.search_box.setObjectName("gallery_search")
        self.search_box.setPlaceholderText(tr("Search algorithms"))
        self.search_box.setClearButtonEnabled(True)
        self.empty_label = QLabel(tr("No algorithm matches the search."), self)
        self.empty_label.setObjectName("gallery_empty")
        self.empty_label.setVisible(False)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(self.search_box)
        outer.addLayout(self.grid)
        outer.addWidget(self.empty_label)
        outer.addStretch(1)
        self.search_box.textChanged.connect(self.set_search)
        self.refresh()

    def cells(self) -> list[ThumbnailCell]:
        """Return every cell of the gallery, in registry order."""
        return list(self._cells)

    def visible_cells(self) -> list[ThumbnailCell]:
        """Return the cells the current search lets through, in reading order."""
        return list(self._visible)

    def refresh(self) -> None:
        """Rebuild the cells from the registry and queue every thumbnail."""
        self._clear_cells()
        for info in list_algorithms():
            cell = ThumbnailCell(info, self._size, self)
            cell.clicked.connect(self.algorithm_chosen)
            self._cells.append(cell)
            self._by_key[cache_key(info.id, {}, self._palette)] = cell
        self._apply_filter()
        self._queue_thumbnails()

    def set_search(self, text: str) -> None:
        """Filter the grid to the algorithms matching text by name or family."""
        self._query = fold(text)
        self._apply_filter()

    def shutdown(self) -> None:
        """Stop the helper thread and release its worker; safe to call more than once."""
        thread, worker = self._thread, self._worker
        self._thread = self._worker = None
        if thread is None:
            return
        if worker is not None:
            # Disconnect first: a queued request must not start a new render after the
            # quit below, and the worker must be gone before its thread is destroyed.
            _release_worker(self, worker)
        thread.quit()
        if not thread.wait(JOIN_MS):
            LOGGER.warning("the thumbnail thread did not stop within %d ms", JOIN_MS)
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
        self._by_key.clear()

    def _apply_filter(self) -> None:
        """Show the matching cells in reading order and hide the others."""
        self._visible = [cell for cell in self._cells if self._query in cell.haystack]
        for cell in self._cells:
            cell.setVisible(self._query in cell.haystack)
        self._reflow()
        self.empty_label.setVisible(not self._visible)

    def _reflow(self) -> None:
        """Place the visible cells in the grid, columns per row."""
        while self.grid.count():
            self.grid.takeAt(0)
        for index, cell in enumerate(self._visible):
            self.grid.addWidget(cell, index // self._columns, index % self._columns)

    def _ensure_worker(self) -> ThumbnailWorker:
        """Create the helper thread and its worker on first use."""
        if self._worker is not None:
            return self._worker
        thread = QThread()
        worker = ThumbnailWorker(self._cache_dir, self._size)
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
            key = cache_key(cell.algorithm_id, {}, self._palette)
            self._request.emit(key, cell.algorithm_id, {}, self._palette)

    @Slot(str, object)
    def _on_thumbnail_ready(self, key: str, rgb8: object) -> None:
        """Show a finished thumbnail; this slot runs on the GUI thread."""
        cell = self._by_key.get(key)
        if cell is None:
            return
        cell.set_thumbnail(np.asarray(rgb8, dtype=np.uint8))

    @Slot(str, str)
    def _on_thumbnail_failed(self, key: str, message: str) -> None:
        """Keep the placeholder of a cell whose thumbnail could not be rendered."""
        cell = self._by_key.get(key)
        if cell is not None:
            cell.setToolTip(tr(FAILED_TIP, name=tr(cell.name), message=message))
