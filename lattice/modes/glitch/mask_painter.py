"""Mask painter of the Glitch shell: a zoom-to-fit greyscale plane, paintable (§18).

The painter stamps a circular brush in mask coordinates; 0 keeps the source and 1 keeps
the effect. Planes are kept at the 8-bit precision of their PNG storage, so the GUI
render and a preset reload agree byte for byte (G9).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from lattice import mask
from lattice.types import Image

DEFAULT_RADIUS = 8


def quantize(plane: Image) -> Image:
    """Return the plane at the 8-bit precision of its PNG storage, in [0, 1]."""
    return mask.from_png(mask.to_png(plane))


class MaskPainter(QWidget):
    """Zoom-to-fit greyscale view of one mask plane, paintable with a circular brush."""

    painted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Start with no plane, a white brush and the default radius."""
        super().__init__(parent)
        self.setObjectName("mask_painter")
        self.setMinimumSize(220, 180)
        self._plane: Image | None = None
        self._value = 1.0
        self._radius = DEFAULT_RADIUS
        self._painting = False

    def set_plane(self, plane: Image | None) -> None:
        """Adopt a mask plane (or None) and repaint."""
        self._plane = plane
        self.update()

    def plane(self) -> Image | None:
        """Return the plane being painted, or None."""
        return self._plane

    def set_brush(self, value: float, radius: int) -> None:
        """Set the stamp value (1 brush, 0 eraser) and the radius in mask pixels."""
        self._value = float(value)
        self._radius = max(1, int(radius))

    def paint_at(self, x: int, y: int) -> None:
        """Stamp the brush at mask coordinates (x, y), clipping at the plane edges."""
        plane = self._plane
        if plane is None:
            return
        height, width = plane.shape
        radius = self._radius
        x0, x1 = max(0, x - radius), min(width, x + radius + 1)
        y0, y1 = max(0, y - radius), min(height, y + radius + 1)
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.ogrid[y0:y1, x0:x1]
        inside = (xx - x) ** 2 + (yy - y) ** 2 <= radius * radius
        plane[y0:y1, x0:x1][inside] = self._value
        self.update()
        self.painted.emit()

    def _geometry(self) -> tuple[float, float, float] | None:
        """Return the (scale, offset_x, offset_y) that fits the plane in the widget."""
        if self._plane is None:
            return None
        height, width = self._plane.shape
        scale = min(self.width() / width, self.height() / height)
        return scale, (self.width() - width * scale) / 2, (self.height() - height * scale) / 2

    def _to_mask(self, position: QPoint) -> tuple[int, int] | None:
        """Map a widget position to mask coordinates, or None outside the plane."""
        geometry = self._geometry()
        if geometry is None or self._plane is None:
            return None
        scale, ox, oy = geometry
        x, y = int((position.x() - ox) / scale), int((position.y() - oy) / scale)
        height, width = self._plane.shape
        if not (0 <= x < width and 0 <= y < height):
            return None
        return x, y

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the plane as greyscale, letterboxed on a dark background."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.darkGray)
        geometry = self._geometry()
        if geometry is not None and self._plane is not None:
            scale, ox, oy = geometry
            height, width = self._plane.shape
            data = np.ascontiguousarray((self._plane * 255.0).round().astype(np.uint8))
            image = QImage(data.data, width, height, width, QImage.Format.Format_Grayscale8)
            scaled = image.scaled(int(width * scale), int(height * scale),
                                  Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            painter.drawImage(int(ox), int(oy), scaled)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start painting on a left-button press inside the plane."""
        if event.button() == Qt.MouseButton.LeftButton:
            point = self._to_mask(event.position().toPoint())
            if point is not None:
                self._painting = True
                self.paint_at(*point)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Continue the stroke while the left button is held."""
        if self._painting:
            point = self._to_mask(event.position().toPoint())
            if point is not None:
                self.paint_at(*point)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish the stroke when the left button is released."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._painting = False


__all__ = ["DEFAULT_RADIUS", "MaskPainter", "quantize"]
