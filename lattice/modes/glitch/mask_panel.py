"""Mask panel of the Glitch shell: paint, generate, import and export §18 masks.

A mask is a greyscale plane where 0 keeps the source and 1 keeps the effect. The painter
stamps a circular brush in mask coordinates; gradient and luminance-range generators
produce planes without a mouse. Planes are kept at the 8-bit precision of their PNG
storage, so the GUI render and a preset reload agree byte for byte (G9).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lattice import color, mask
from lattice.modes.glitch.document import fit_mask
from lattice.modes.glitch.mask_painter import DEFAULT_RADIUS, MaskPainter, quantize
from lattice.types import Image

MASK_FILTER = "Mask PNG (*.png);;All files (*)"
NO_SOURCE = "Load an image before creating or generating a mask."


class MaskPanel(QWidget):
    """Mask list, painter, generators and PNG import/export of one document."""

    masks_changed = Signal()
    mask_painted = Signal(str)
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the list, the painter and the tool rows over an empty mask set."""
        super().__init__(parent)
        self.setObjectName("mask_panel")
        self._masks: dict[str, Image] = {}
        self._active: str | None = None
        self._source: Image | None = None
        self._loading = False
        self.list = QListWidget(self)
        self.list.setObjectName("mask_list")
        self.list.setMaximumHeight(96)
        self.new_button = QPushButton("New", self)
        self.import_button = QPushButton("Import…", self)
        self.export_button = QPushButton("Export…", self)
        self.delete_button = QPushButton("Delete", self)
        list_row = QHBoxLayout()
        for button in (self.new_button, self.import_button,
                       self.export_button, self.delete_button):
            list_row.addWidget(button)
        self.painter = MaskPainter(self)
        self.tool_box = QComboBox(self)
        self.tool_box.setObjectName("mask_tool")
        self.tool_box.addItem("Brush", 1.0)
        self.tool_box.addItem("Eraser", 0.0)
        self.radius_spin = QSpinBox(self)
        self.radius_spin.setObjectName("mask_radius")
        self.radius_spin.setRange(1, 256)
        self.radius_spin.setValue(DEFAULT_RADIUS)
        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Tool", self))
        tool_row.addWidget(self.tool_box)
        tool_row.addWidget(QLabel("Radius", self))
        tool_row.addWidget(self.radius_spin)
        self.clear_button = QPushButton("Clear", self)
        self.fill_button = QPushButton("Fill", self)
        self.gradient_box = QComboBox(self)
        self.gradient_box.addItem("Horizontal", "h")
        self.gradient_box.addItem("Vertical", "v")
        self.gradient_button = QPushButton("Gradient", self)
        self.lo_spin = QDoubleSpinBox(self)
        self.lo_spin.setRange(0.0, 1.0)
        self.lo_spin.setSingleStep(0.05)
        self.lo_spin.setValue(0.2)
        self.hi_spin = QDoubleSpinBox(self)
        self.hi_spin.setRange(0.0, 1.0)
        self.hi_spin.setSingleStep(0.05)
        self.hi_spin.setValue(0.8)
        self.luma_button = QPushButton("From luminance", self)
        gen_row, luma_row = self._build_generators()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.list)
        layout.addLayout(list_row)
        layout.addWidget(self.painter, 1)
        layout.addLayout(tool_row)
        layout.addLayout(gen_row)
        layout.addLayout(luma_row)
        self._connect()

    def _build_generators(self) -> tuple[QHBoxLayout, QHBoxLayout]:
        """Lay out the clear/fill/gradient row and the luminance-range row."""
        gen_row = QHBoxLayout()
        for widget in (self.clear_button, self.fill_button,
                       self.gradient_box, self.gradient_button):
            gen_row.addWidget(widget)
        luma_row = QHBoxLayout()
        luma_row.addWidget(QLabel("Lo", self))
        luma_row.addWidget(self.lo_spin)
        luma_row.addWidget(QLabel("Hi", self))
        luma_row.addWidget(self.hi_spin)
        luma_row.addWidget(self.luma_button)
        return gen_row, luma_row

    def _connect(self) -> None:
        """Wire every control to its slot."""
        self.list.currentRowChanged.connect(self._on_selection)
        self.new_button.clicked.connect(lambda: self.new_mask())
        self.import_button.clicked.connect(self.import_dialog)
        self.export_button.clicked.connect(self.export_dialog)
        self.delete_button.clicked.connect(self.delete_active)
        self.tool_box.currentIndexChanged.connect(self._sync_brush)
        self.radius_spin.valueChanged.connect(self._sync_brush)
        self.painter.painted.connect(self._on_painted)
        self.clear_button.clicked.connect(lambda: self.generate("clear"))
        self.fill_button.clicked.connect(lambda: self.generate("fill"))
        self.gradient_button.clicked.connect(
            lambda: self.generate(str(self.gradient_box.currentData())))
        self.luma_button.clicked.connect(lambda: self.generate("luma"))

    # --- state -------------------------------------------------------------------

    def planes(self) -> dict[str, Image]:
        """Return the mask planes of the document, keyed by id."""
        return self._masks

    def mask_ids(self) -> list[str]:
        """Return the mask ids in list order."""
        return list(self._masks)

    def active_id(self) -> str | None:
        """Return the id of the mask being painted, or None."""
        return self._active

    def set_source(self, source: Image | None) -> None:
        """Adopt the document source the generators read and new masks size from."""
        self._source = source

    def set_planes(self, planes: dict[str, Image]) -> None:
        """Adopt a whole mask set (quantized), rebuilding the list silently."""
        self._masks = {str(key): quantize(np.asarray(plane, dtype=np.float32))
                       for key, plane in planes.items()}
        self._refresh()
        self.masks_changed.emit()

    def _refresh(self) -> None:
        """Rebuild the list from the mask set, keeping the active id when possible."""
        self._loading = True
        try:
            self.list.clear()
            for mask_id in self._masks:
                self.list.addItem(mask_id)
            if self._active in self._masks:
                self.list.setCurrentRow(list(self._masks).index(self._active))
            elif self.list.count():
                self.list.setCurrentRow(0)
            else:
                self._active = None
                self.painter.set_plane(None)
        finally:
            self._loading = False
        self._on_selection(self.list.currentRow())

    def _on_selection(self, row: int) -> None:
        """Point the painter at the selected mask."""
        if self._loading:
            return
        ids = list(self._masks)
        self._active = ids[row] if 0 <= row < len(ids) else None
        self.painter.set_plane(None if self._active is None else self._masks[self._active])
        self._sync_brush()

    def _sync_brush(self, *_args: object) -> None:
        """Mirror the tool combo and radius spin into the painter."""
        self.painter.set_brush(float(self.tool_box.currentData()), self.radius_spin.value())

    def _on_painted(self) -> None:
        """Quantize the painted plane in place and announce the content change."""
        if self._active is None:
            return
        plane = self._masks[self._active]
        plane[:] = quantize(plane)
        self.painter.update()
        self.mask_painted.emit(self._active)

    # --- operations --------------------------------------------------------------

    def _next_id(self) -> str:
        """Return the first unused mask_N id."""
        index = 1
        while f"mask_{index}" in self._masks:
            index += 1
        return f"mask_{index}"

    def new_mask(self, mask_id: str | None = None) -> str | None:
        """Create a black mask at the source size; without a source, report and stop."""
        if self._source is None:
            self.failed.emit(NO_SOURCE)
            return None
        name = mask_id or self._next_id()
        height, width = self._source.shape[:2]
        self._masks[name] = np.zeros((height, width), dtype=np.float32)
        self._active = name
        self._refresh()
        self.masks_changed.emit()
        return name

    def import_dialog(self) -> None:
        """Ask for a PNG mask and import it."""
        path, _ = QFileDialog.getOpenFileName(self, "Import mask", str(Path.home()), MASK_FILTER)
        if path:
            self.import_png(Path(path))

    def import_png(self, path: str | Path, mask_id: str | None = None) -> str | None:
        """Read a PNG mask, fit it to the source when one is loaded, and adopt it."""
        try:
            plane = mask.import_png(path)
        except (OSError, ValueError) as exc:
            self.failed.emit(f"Cannot read mask {path}: {exc}")
            return None
        if self._source is not None:
            plane = fit_mask(plane, self._source.shape[:2])
        name = mask_id or Path(path).stem or self._next_id()
        self._masks[name] = quantize(plane)
        self._active = name
        self._refresh()
        self.masks_changed.emit()
        return name

    def export_dialog(self) -> None:
        """Ask for a path and export the active mask as PNG."""
        if self._active is None:
            self.failed.emit("Select a mask first.")
            return
        target = str(Path.home() / f"{self._active}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Export mask", target, MASK_FILTER)
        if path:
            self.export_png(Path(path))

    def export_png(self, path: str | Path) -> Path | None:
        """Write the active mask as an 8-bit greyscale PNG."""
        if self._active is None:
            self.failed.emit("Select a mask first.")
            return None
        return mask.export_png(self._masks[self._active], path)

    def delete_active(self) -> None:
        """Drop the active mask from the document."""
        if self._active is None:
            return
        del self._masks[self._active]
        self._active = None
        self._refresh()
        self.masks_changed.emit()

    def generate(self, kind: str) -> None:
        """Replace the active plane with clear, fill, a gradient or a luminance range."""
        if self._active is None:
            self.failed.emit("Create or select a mask first.")
            return
        plane = self._masks[self._active]
        height, width = plane.shape
        if kind == "clear":
            plane[:] = 0.0
        elif kind == "fill":
            plane[:] = 1.0
        elif kind == "h":
            plane[:] = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
        elif kind == "v":
            plane[:] = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
        elif kind == "luma":
            self._generate_luma(plane)
            return
        else:
            self.failed.emit(f"Unknown mask generator {kind!r}.")
            return
        plane[:] = quantize(plane)
        self.painter.update()
        self.mask_painted.emit(self._active)

    def _generate_luma(self, plane: Image) -> None:
        """Fill plane from the source luminance between the lo and hi spins."""
        if self._source is None:
            self.failed.emit(NO_SOURCE)
            return
        lo, hi = self.lo_spin.value(), self.hi_spin.value()
        if hi <= lo:
            self.failed.emit("The luminance range needs hi > lo.")
            return
        lum = color.luminance(self._source)
        plane[:] = quantize(np.clip((lum - lo) / (hi - lo), 0.0, 1.0))
        self.painter.update()
        self.mask_painted.emit(self._active)


__all__ = ["MASK_FILTER", "MaskPanel"]
