"""Palette panel: built-in, extracted and custom palettes with import and export."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dithercraft.core.pipeline import PipelineSpec
from dithercraft.core.types import Image
from dithercraft.palettes.builtin import builtin_names, get_builtin
from dithercraft.palettes.extract import MAX_K, MIN_K, extract_palette
from dithercraft.palettes.io import (
    MAX_COLORS,
    MIN_COLORS,
    from_hex_list,
    hex_list,
    load_palette,
    save_palette,
)

LOGGER = logging.getLogger(__name__)

SOURCES: tuple[str, ...] = ("builtin", "extracted", "custom")
SOURCE_LABELS: dict[str, str] = {
    "builtin": "Built-in",
    "extracted": "Extracted",
    "custom": "Custom",
}
METHODS: tuple[str, ...] = ("kmeans", "median_cut")
PALETTE_FILTER = "Palettes (*.hex *.gpl);;All files (*)"
DEFAULT_BUILTIN, DEFAULT_K, NEW_COLOR = "bw", 8, "#000000"
SWATCH_SIZE, GRID_COLUMNS, ICON_WIDTH, ICON_HEIGHT = 22, 8, 64, 16


def _normalise_colors(values: list[str]) -> list[str]:
    """Return the colours as uppercase "#RRGGBB", dropping unparsable entries and extras."""
    colors: list[str] = []
    for value in values:
        try:
            colors.append(hex_list(from_hex_list([str(value)]))[0])
        except ValueError:
            continue
    return colors[:MAX_COLORS]


def _swatch_pixmap(colors: list[str]) -> QPixmap:
    """Return a pixmap of vertical colour stripes, one per palette entry."""
    pixmap = QPixmap(ICON_WIDTH, ICON_HEIGHT)
    pixmap.fill(QColor(0, 0, 0))
    if not colors:
        return pixmap
    count = len(colors)
    with QPainter(pixmap) as painter:
        for index, color in enumerate(colors):
            left = index * ICON_WIDTH // count
            right = (index + 1) * ICON_WIDTH // count
            painter.fillRect(left, 0, max(1, right - left), ICON_HEIGHT, QColor(color))
    return pixmap


class SwatchButton(QPushButton):
    """Colour square: a left click edits the colour, a right click removes it."""

    remove_requested = Signal()

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.setToolTip(f"{color} (click to edit, right click to remove)")
        self.setStyleSheet(f"background-color: {color}; border: 1px solid #141414;")

    def color(self) -> str:
        """Return the colour shown by this swatch."""
        return self._color

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit remove_requested on a right click and behave normally otherwise."""
        if event.button() == Qt.MouseButton.RightButton:
            self.remove_requested.emit()
            return
        super().mousePressEvent(event)


class PalettePanel(QWidget):
    """Palette editor implementing the panel interface of the contract."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._source = "builtin"
        self._builtin_name = DEFAULT_BUILTIN
        self._colors: list[str] = []
        self.swatches: list[SwatchButton] = []
        self._image: Image | None = None
        self._build_ui()
        self.load_from(PipelineSpec())

    def colors(self) -> list[str]:
        """Return the custom colours as uppercase "#RRGGBB" strings."""
        return list(self._colors)

    def set_source_image(self, img: Image) -> None:
        """Store the image used by Extract and enable the button."""
        array = np.asarray(img)
        if array.ndim != 3 or array.shape[2] != 3:
            raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
        self._image = np.ascontiguousarray(array, dtype=np.float32)
        self._update_enabled()

    def load_from(self, spec: PipelineSpec) -> None:
        """Show the palette of spec without emitting changed."""
        palette = spec.palette
        self._loading = True
        try:
            self._source = palette.source if palette.source in SOURCES else "builtin"
            known = palette.name in builtin_names()
            self._builtin_name = palette.name if known else DEFAULT_BUILTIN
            self._colors = _normalise_colors(list(palette.colors))
            self.extract_k.setValue(max(MIN_K, min(MAX_K, int(palette.extract_k))))
            index = self.extract_method.findText(str(palette.extract_method))
            self.extract_method.setCurrentIndex(max(0, index))
            self.source_buttons[self._source].setChecked(True)
            self._refresh()
        finally:
            self._loading = False

    def apply_to(self, spec: PipelineSpec) -> None:
        """Write the panel state into spec.palette."""
        palette = spec.palette
        palette.source = self._source
        palette.name = self._builtin_name
        palette.colors = list(self._colors)
        palette.extract_k = int(self.extract_k.value())
        palette.extract_method = str(self.extract_method.currentText())

    def extract_now(self) -> None:
        """Extract colours from the source image and switch the panel to Custom."""
        if self._image is None:
            self._set_error("Load an image before extracting a palette.")
            return
        method = str(self.extract_method.currentText())
        try:
            palette = extract_palette(self._image, int(self.extract_k.value()), method)
        except ValueError as exc:
            self._set_error(str(exc))
            return
        self._adopt_custom(hex_list(palette))

    def import_palette(self, path: Path) -> None:
        """Load a .hex or .gpl palette from path and switch the panel to Custom."""
        try:
            palette = load_palette(Path(path))
        except (ValueError, OSError) as exc:
            self._set_error(str(exc))
            return
        self._adopt_custom(hex_list(palette))

    def export_palette(self, path: Path) -> None:
        """Write the current palette to path as .hex or .gpl."""
        builtin = self._source == "builtin"
        colors = hex_list(get_builtin(self._builtin_name)) if builtin else list(self._colors)
        if len(colors) < MIN_COLORS:
            self._set_error("A palette needs at least two colours.")
            return
        name = self._builtin_name if builtin else "DitherCraft"
        try:
            save_palette(Path(path), from_hex_list(colors), name)
        except (ValueError, OSError) as exc:
            self._set_error(str(exc))
            return
        self._set_error()

    def _build_ui(self) -> None:
        """Create the source radios, built-in combo, extract controls, grid and file buttons."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(self._build_source_box())
        outer.addWidget(self._build_extract_box())
        outer.addWidget(self._build_custom_box())
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("palette_error")
        self.error_label.setWordWrap(True)
        outer.addWidget(self.error_label)
        outer.addStretch(1)

    def _build_source_box(self) -> QGroupBox:
        """Create the exclusive source radios and the built-in combo with swatch icons."""
        box = QGroupBox("Source", self)
        column = QVBoxLayout(box)
        row = QHBoxLayout()
        self.source_group = QButtonGroup(self)
        self.source_group.setExclusive(True)
        self.source_buttons: dict[str, QRadioButton] = {}
        for name in SOURCES:
            button = QRadioButton(SOURCE_LABELS[name], box)
            button.setObjectName(f"source_{name}")
            self.source_group.addButton(button)
            button.toggled.connect(lambda checked, key=name: self._on_source_toggled(key, checked))
            self.source_buttons[name] = button
            row.addWidget(button)
        column.addLayout(row)
        self.builtin_combo = QComboBox(box)
        self.builtin_combo.setObjectName("builtin_combo")
        self.builtin_combo.setIconSize(QPixmap(ICON_WIDTH, ICON_HEIGHT).size())
        for name in builtin_names():
            self.builtin_combo.addItem(_swatch_pixmap(hex_list(get_builtin(name))), name)
        self.builtin_combo.currentIndexChanged.connect(self._on_builtin_changed)
        column.addWidget(self.builtin_combo)
        return box

    def _build_extract_box(self) -> QGroupBox:
        """Create the k spinbox, the method combo and the Extract button."""
        box = QGroupBox("Extract from image", self)
        row = QHBoxLayout(box)
        self.extract_k = QSpinBox(box)
        self.extract_k.setObjectName("extract_k")
        self.extract_k.setRange(MIN_K, MAX_K)
        self.extract_k.setValue(DEFAULT_K)
        self.extract_method = QComboBox(box)
        self.extract_method.setObjectName("extract_method")
        self.extract_method.addItems(list(METHODS))
        self.extract_button = QPushButton("Extract", box)
        self.extract_button.setObjectName("extract_button")
        self.extract_button.clicked.connect(self.extract_now)
        row.addWidget(QLabel("Colours", box))
        row.addWidget(self.extract_k)
        row.addWidget(self.extract_method)
        row.addWidget(self.extract_button)
        return box

    def _build_custom_box(self) -> QGroupBox:
        """Create the swatch grid and the import/export buttons."""
        box = QGroupBox("Colours", self)
        column = QVBoxLayout(box)
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(2)
        self.add_button = QPushButton("+", box)
        self.add_button.setObjectName("add_swatch")
        self.add_button.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.add_button.clicked.connect(self._on_add_swatch)
        column.addLayout(self.grid_layout)
        row = QHBoxLayout()
        self.import_button = QPushButton("Import", box)
        self.import_button.setObjectName("import_palette")
        self.import_button.clicked.connect(lambda: self._on_file(False))
        self.export_button = QPushButton("Export", box)
        self.export_button.setObjectName("export_palette")
        self.export_button.clicked.connect(lambda: self._on_file(True))
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        row.addStretch(1)
        column.addLayout(row)
        return box

    def _adopt_custom(self, colors: list[str]) -> None:
        """Switch to the Custom source with colors and emit changed once."""
        self._loading = True
        try:
            self._colors = list(colors)
            self._source = "custom"
            self.source_buttons["custom"].setChecked(True)
            self._refresh()
        finally:
            self._loading = False
        self._set_error()
        self.changed.emit()

    def _on_source_toggled(self, name: str, checked: bool) -> None:
        """Switch the palette source when the user checks a radio button."""
        if self._loading or not checked:
            return
        self._source = name
        if name == "custom" and len(self._colors) < MIN_COLORS:
            self._colors = hex_list(get_builtin(self._builtin_name))
        self._refresh()
        self.changed.emit()

    def _on_builtin_changed(self, _index: int) -> None:
        """Adopt the built-in palette selected in the combo."""
        if self._loading:
            return
        self._builtin_name = str(self.builtin_combo.currentText())
        self._refresh()
        self.changed.emit()

    def _on_swatch_clicked(self, index: int) -> None:
        """Ask for a new colour for one swatch."""
        if self._loading or not 0 <= index < len(self._colors):
            return
        chosen = self._ask_color(self._colors[index])
        if chosen is None:
            return
        self._colors[index] = chosen
        self._set_error()
        self._refresh()
        self.changed.emit()

    def _on_swatch_removed(self, index: int) -> None:
        """Remove one swatch unless the palette would drop below two colours."""
        if self._loading or not 0 <= index < len(self._colors):
            return
        if len(self._colors) <= MIN_COLORS:
            self._set_error("A palette needs at least two colours.")
            return
        del self._colors[index]
        self._set_error()
        self._refresh()
        self.changed.emit()

    def _on_add_swatch(self) -> None:
        """Append a black swatch unless the palette already holds 256 colours."""
        if self._loading or len(self._colors) >= MAX_COLORS:
            return
        self._colors.append(NEW_COLOR)
        self._set_error()
        self._refresh()
        self.changed.emit()

    def _on_file(self, export: bool) -> None:
        """Ask for a palette file and import it, or ask for a target and export."""
        dialog = QFileDialog.getSaveFileName if export else QFileDialog.getOpenFileName
        title, start = ("Export palette", "palette.hex") if export else ("Import palette", "")
        path, _ = dialog(self, title, start, PALETTE_FILTER)
        if path:
            (self.export_palette if export else self.import_palette)(Path(path))

    def _ask_color(self, initial: str) -> str | None:
        """Open a colour dialog and return the chosen "#RRGGBB", or None when cancelled."""
        color = QColorDialog.getColor(QColor(initial), self, "Palette colour")
        return color.name().upper() if color.isValid() else None

    def _refresh(self) -> None:
        """Sync every widget with the panel state without emitting changed."""
        with QSignalBlocker(self.builtin_combo):
            self.builtin_combo.setCurrentIndex(
                max(0, self.builtin_combo.findText(self._builtin_name))
            )
            self._rebuild_grid()
        self._update_enabled()

    def _rebuild_grid(self) -> None:
        """Rebuild the swatch grid for the current custom colours."""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.add_button:
                widget.deleteLater()
        self.swatches = []
        for index, color in enumerate(self._colors):
            swatch = SwatchButton(color, self)
            swatch.clicked.connect(lambda _c=False, i=index: self._on_swatch_clicked(i))
            swatch.remove_requested.connect(lambda i=index: self._on_swatch_removed(i))
            self.grid_layout.addWidget(swatch, index // GRID_COLUMNS, index % GRID_COLUMNS)
            self.swatches.append(swatch)
        position = len(self._colors)
        self.grid_layout.addWidget(
            self.add_button, position // GRID_COLUMNS, position % GRID_COLUMNS
        )

    def _update_enabled(self) -> None:
        """Enable only the controls that belong to the selected source."""
        builtin, extracted = self._source == "builtin", self._source == "extracted"
        custom = self._source == "custom"
        self.builtin_combo.setEnabled(builtin)
        self.extract_k.setEnabled(extracted)
        self.extract_method.setEnabled(extracted)
        self.extract_button.setEnabled(extracted and self._image is not None)
        for swatch in self.swatches:
            swatch.setEnabled(custom)
        self.add_button.setEnabled(custom and len(self._colors) < MAX_COLORS)

    def _set_error(self, message: str = "") -> None:
        """Show message in the panel, or clear the message when it is empty."""
        if message:
            LOGGER.warning("palette panel: %s", message)
        self.error_label.setText(message)
