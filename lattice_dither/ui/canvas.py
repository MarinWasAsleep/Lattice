"""Preview canvas with nearest-neighbour display and before/after/split modes."""

from __future__ import annotations

from typing import Literal

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget

from lattice_core.types import RGB8

Mode = Literal["after", "before", "split"]

MODES: tuple[str, ...] = ("after", "before", "split")
MIN_ZOOM = 0.01
MAX_ZOOM = 32.0
WHEEL_STEP = 1.25
FIT_MARGIN = 2.0


def _as_rgb8(rgb8: RGB8) -> RGB8:
    """Validate an RGB8 array and return it as a contiguous uint8 (H, W, 3) array."""
    array = np.asarray(rgb8)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) array, got shape {array.shape}")
    if array.dtype != np.uint8:
        if array.dtype.kind not in "iu":
            raise ValueError(f"expected a uint8 array, got dtype {array.dtype}")
        array = np.clip(array, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(array)


def _pixels(image: QImage) -> np.ndarray:
    """Return a writable (height, bytesPerLine) uint8 view of the image pixels."""
    height = image.height()
    return np.frombuffer(image.bits(), dtype=np.uint8).reshape(height, image.bytesPerLine())


class PreviewCanvas(QGraphicsView):
    """Zoomable, pannable preview of the rendered image with a split view."""

    zoom_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._scene.addItem(self._item)
        self._after: RGB8 | None = None
        self._before: RGB8 | None = None
        self._buffer: QImage | None = None
        self._mode: Mode = "after"
        self._zoom = 1.0
        self._fitted = True
        self._panning = False
        self._pan_origin = QPoint()
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(32, 32, 34))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def set_image(self, rgb8: RGB8) -> None:
        """Set the rendered (after) image and refresh the display."""
        previous = None if self._after is None else self._after.shape
        self._after = _as_rgb8(rgb8)
        self._refresh()
        if previous is None or (self._fitted and self._after.shape != previous):
            self.zoom_fit()

    def set_original(self, rgb8: RGB8 | None) -> None:
        """Set the source (before) image, or None to clear it."""
        self._before = None if rgb8 is None else _as_rgb8(rgb8)
        self._refresh()

    def set_mode(self, mode: Mode) -> None:
        """Switch the preview between the after, before and split views."""
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        self._mode = mode
        self._refresh()
        self.viewport().update()

    def mode(self) -> Mode:
        """Return the active preview mode."""
        return self._mode

    def qimage(self) -> QImage | None:
        """Return the QImage buffer the canvas displays, or None when it is empty."""
        return self._buffer

    def zoom(self) -> float:
        """Return the current zoom factor (1.0 is one image pixel per screen pixel)."""
        return self._zoom

    def set_zoom(self, f: float) -> None:
        """Set the zoom factor, clamped to the supported range."""
        factor = float(min(max(float(f), MIN_ZOOM), MAX_ZOOM))
        self._zoom = factor
        self._fitted = False
        self.setTransform(QTransform().scale(factor, factor))
        self.zoom_changed.emit(factor)

    def zoom_fit(self) -> None:
        """Scale the image so that it fits entirely inside the viewport."""
        rect = self._scene.sceneRect()
        if rect.isEmpty():
            return
        viewport = self.viewport().size()
        scale_x = (viewport.width() - FIT_MARGIN) / rect.width()
        scale_y = (viewport.height() - FIT_MARGIN) / rect.height()
        self.set_zoom(min(scale_x, scale_y))
        self._fitted = True

    def _refresh(self) -> None:
        """Rebuild the displayed pixmap from the current images and mode."""
        after = self._after
        if after is None:
            self._item.setPixmap(QPixmap())
            self._scene.setSceneRect(QRectF())
            return
        self._compose(after)
        pixmap = QPixmap.fromImage(self._buffer)
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

    def _compose(self, after: RGB8) -> None:
        """Write the image matching the current mode into the display buffer."""
        before = self._before
        paired = before is not None and before.shape == after.shape
        if paired and self._mode == "before":
            self._blit(before)
            return
        self._blit(after)
        if paired and self._mode == "split":
            self._blit_left(before)

    def _blit(self, rgb8: RGB8) -> None:
        """Copy rgb8 into the display buffer, reallocating it only when the shape changes."""
        height, width = rgb8.shape[:2]
        buffer = self._buffer
        if buffer is None or buffer.width() != width or buffer.height() != height:
            buffer = QImage(width, height, QImage.Format.Format_RGB888)
            self._buffer = buffer
        view = _pixels(buffer)
        view[:, : width * 3] = rgb8.reshape(height, width * 3)
        if view.shape[1] > width * 3:
            view[:, width * 3 :] = 0

    def _blit_left(self, rgb8: RGB8) -> None:
        """Copy the left half of rgb8 into the display buffer."""
        buffer = self._buffer
        if buffer is None:
            return
        height, width = rgb8.shape[:2]
        half = (width // 2) * 3
        _pixels(buffer)[:, :half] = rgb8.reshape(height, width * 3)[:, :half]

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom around the cursor with the mouse wheel."""
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = WHEEL_STEP if delta > 0 else 1.0 / WHEEL_STEP
        self.zoom_around(event.position(), self._zoom * factor)
        event.accept()

    def zoom_around(self, position: QPointF, f: float) -> None:
        """Set the zoom factor while keeping the scene point under position fixed."""
        anchor = self.mapToScene(position.toPoint())
        self.set_zoom(f)
        offset = self.mapFromScene(anchor) - position.toPoint()
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        horizontal.setValue(horizontal.value() + offset.x())
        vertical.setValue(vertical.value() + offset.y())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start panning on a left or middle button press."""
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._panning = True
            self._pan_origin = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Scroll the view while a pan drag is active."""
        if self._panning:
            position = event.position().toPoint()
            delta = position - self._pan_origin
            self._pan_origin = position
            horizontal = self.horizontalScrollBar()
            vertical = self.verticalScrollBar()
            horizontal.setValue(horizontal.value() - delta.x())
            vertical.setValue(vertical.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish panning when the drag button is released."""
        if self._panning and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        ):
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the divider line of the split view."""
        super().drawForeground(painter, rect)
        after = self._after
        before = self._before
        if self._mode != "split" or after is None or before is None:
            return
        if before.shape != after.shape:
            return
        x = float(after.shape[1] // 2)
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 180), 0))
        painter.drawLine(QPointF(x, 0.0), QPointF(x, float(after.shape[0])))
        painter.restore()
