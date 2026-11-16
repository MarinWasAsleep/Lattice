"""Palette panel: built-in, extracted and custom palettes with import and export."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QMimeData, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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

from lattice_core.palettes.builtin import builtin_names, get_builtin
from lattice_core.palettes.extract import MAX_K, MIN_K
from lattice_core.palettes.io import (
    MAX_COLORS,
    MIN_COLORS,
    from_hex_list,
    hex_list,
    load_palette,
    save_palette,
)
from lattice_core.palettes.library import get_library, library_names
from lattice_core.pipeline import PipelineSpec
from lattice_core.types import Image
from lattice_dither.i18n import tr
from lattice_dither.ui.worker import PaletteExtraction

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
SWATCH_MIME = "application/x-lattice-swatch"
LOCK_BORDER = "3px solid #FFD166"
PLAIN_BORDER = "1px solid #141414"
SWATCH_STYLE = "background-color: {color}; border: {border};"
SWATCH_TIP = (
    "{color} ({state}; click to edit, right click to remove, "
    "middle click to lock, drag to reorder)"
)


def _normalise_colors(values: list[str]) -> list[str]:
    """Return the colours as uppercase "#RRGGBB", dropping unparsable entries and extras."""
    colors: list[str] = []
    for value in values:
        try:
            colors.append(hex_list(from_hex_list([str(value)]))[0])
        except ValueError:
            continue
    return colors[:MAX_COLORS]


def _normalise_locked(values: list[str]) -> list[str]:
    """Return the locked colours as unique uppercase "#RRGGBB", dropping unparsable entries."""
    locked: list[str] = []
    for value in values:
        try:
            text = hex_list(from_hex_list([str(value)]))[0]
        except ValueError:
            continue
        if text not in locked:
            locked.append(text)
    return locked


def _valid_order(order: list[int], size: int) -> list[int]:
    """Return order when it is a permutation of range(size), otherwise the natural order."""
    if sorted(order) == list(range(size)):
        return list(order)
    return []


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
    """Colour square: left click edits, right click removes, middle click locks.

    Dragging a swatch onto another one reorders the display order of the palette.
    """

    remove_requested = Signal()
    lock_toggled = Signal()
    dropped = Signal(int)

    def __init__(self, color: str, position: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self._position = position
        self._locked = False
        self._press: object | None = None
        self.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.setAcceptDrops(True)
        self._restyle()

    def color(self) -> str:
        """Return the colour shown by this swatch."""
        return self._color

    def position(self) -> int:
        """Return the display position of this swatch in the grid."""
        return self._position

    def is_locked(self) -> bool:
        """Return whether this swatch is locked against extraction."""
        return self._locked

    def set_locked(self, locked: bool) -> None:
        """Show or hide the lock marker."""
        self._locked = locked
        self._restyle()

    def _restyle(self) -> None:
        """Apply the colour and the lock marker to the widget."""
        border = LOCK_BORDER if self._locked else PLAIN_BORDER
        self.setStyleSheet(SWATCH_STYLE.format(color=self._color, border=border))
        state = tr("locked") if self._locked else tr("unlocked")
        self.setToolTip(tr(SWATCH_TIP, color=self._color, state=state))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Route the three buttons and remember where a drag would start."""
        if event.button() == Qt.MouseButton.RightButton:
            self.remove_requested.emit()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self.lock_toggled.emit()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Start a drag once the pointer has travelled far enough."""
        if self._press is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        travelled = (event.position().toPoint() - self._press).manhattanLength()
        if travelled < QApplication.startDragDistance():
            return
        self._press = None
        drag = QDrag(self)
        payload = QMimeData()
        payload.setData(SWATCH_MIME, str(self._position).encode())
        drag.setMimeData(payload)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event: object) -> None:
        """Accept a swatch dragged from another position."""
        if event.mimeData().hasFormat(SWATCH_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event: object) -> None:
        """Report the display position the dragged swatch came from."""
        if not event.mimeData().hasFormat(SWATCH_MIME):
            return
        source = int(bytes(event.mimeData().data(SWATCH_MIME)).decode())
        event.acceptProposedAction()
        self.dropped.emit(source)


class PalettePanel(QWidget):
    """Palette editor implementing the panel interface of the contract."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._source = "builtin"
        self._builtin_name = DEFAULT_BUILTIN
        self._colors: list[str] = []
        self._locked: list[str] = []
        self._order: list[int] = []
        self.swatches: list[SwatchButton] = []
        self._image: Image | None = None
        self._build_ui()
        self.load_from(PipelineSpec())

    def colors(self) -> list[str]:
        """Return the custom colours as uppercase "#RRGGBB" strings."""
        return list(self._colors)

    def locked(self) -> list[str]:
        """Return the colours locked against extraction, in the order they were locked."""
        return list(self._locked)

    def order(self) -> list[int]:
        """Return the display permutation, or an empty list for the natural order."""
        return list(self._order)

    def display_indices(self) -> list[int]:
        """Return the natural index shown at each grid position."""
        return list(self._order) if self._order else list(range(len(self._colors)))

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
            self._locked = _normalise_locked(list(palette.locked))
            self._order = _valid_order(palette.order, len(self._colors))
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
        palette.locked = list(self._locked)
        palette.order = list(self._order)
        palette.extract_k = int(self.extract_k.value())
        palette.extract_method = str(self.extract_method.currentText())

    def extract_now(self) -> None:
        """Extract colours from the source image on a helper thread."""
        if self._image is None:
            self._set_error(tr("Load an image before extracting a palette."))
            return
        job = PaletteExtraction(
            self._image, int(self.extract_k.value()), str(self.extract_method.currentText())
        )
        job.finished.connect(self._adopt_custom)
        job.failed.connect(self._set_error)
        job.start()

    def _emit_changed(self, _value: int = 0) -> None:
        """Emit changed for a user edit, unless a spec is being loaded."""
        if not self._loading:
            self.changed.emit()

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
            self._set_error(tr("A palette needs at least two colours."))
            return
        name = self._builtin_name if builtin else tr("Lattice Dither")
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
        for box in (self._build_source_box(), self._build_extract_box(), self._build_custom_box()):
            outer.addWidget(box)
        self.error_label = QLabel(self)
        self.error_label.setObjectName("palette_error")
        self.error_label.setWordWrap(True)
        outer.addWidget(self.error_label)
        outer.addStretch(1)

    def _build_source_box(self) -> QGroupBox:
        """Create the exclusive source radios and the built-in combo with swatch icons."""
        box = QGroupBox(tr("Source"), self)
        column = QVBoxLayout(box)
        row = QHBoxLayout()
        self.source_group = QButtonGroup(self)
        self.source_buttons: dict[str, QRadioButton] = {}
        for name in SOURCES:
            button = QRadioButton(tr(SOURCE_LABELS[name]), box)
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
        self.library_combo = QComboBox(box)
        self.library_combo.setObjectName("library_combo")
        self.library_combo.setIconSize(QPixmap(ICON_WIDTH, ICON_HEIGHT).size())
        self.library_combo.addItem(tr("Load from library..."), "")
        for name in library_names():
            self.library_combo.addItem(_swatch_pixmap(hex_list(get_library(name))), name, name)
        self.library_combo.activated.connect(self._on_library_chosen)
        column.addWidget(self.library_combo)
        return box

    def _build_extract_box(self) -> QGroupBox:
        """Create the k spinbox, the method combo and the Extract button."""
        box = QGroupBox(tr("Extract from image"), self)
        row = QHBoxLayout(box)
        self.extract_k = QSpinBox(box)
        self.extract_k.setObjectName("extract_k")
        self.extract_k.setRange(MIN_K, MAX_K)
        self.extract_k.setValue(DEFAULT_K)
        self.extract_method = QComboBox(box)
        self.extract_method.setObjectName("extract_method")
        self.extract_method.addItems(list(METHODS))
        self.extract_k.valueChanged.connect(self._emit_changed)
        self.extract_method.currentIndexChanged.connect(self._emit_changed)
        self.extract_button = QPushButton(tr("Extract"), box)
        self.extract_button.setObjectName("extract_button")
        self.extract_button.clicked.connect(self.extract_now)
        row.addWidget(QLabel(tr("Colours"), box))
        row.addWidget(self.extract_k)
        row.addWidget(self.extract_method)
        row.addWidget(self.extract_button)
        return box

    def _build_custom_box(self) -> QGroupBox:
        """Create the swatch grid and the import/export buttons."""
        box = QGroupBox(tr("Colours"), self)
        column = QVBoxLayout(box)
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(2)
        self.add_button = QPushButton(tr("+"), box)
        self.add_button.setObjectName("add_swatch")
        self.add_button.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.add_button.clicked.connect(self._on_add_swatch)
        column.addLayout(self.grid_layout)
        row = QHBoxLayout()
        self.import_button = QPushButton(tr("Import"), box)
        self.import_button.setObjectName("import_palette")
        self.import_button.clicked.connect(lambda: self._on_file(False))
        self.export_button = QPushButton(tr("Export"), box)
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
            self._locked = []
            self._order = []
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

    def _on_library_chosen(self, index: int) -> None:
        """Adopt the library palette picked in the combo, then reset the combo."""
        name = str(self.library_combo.itemData(index) or "")
        self.library_combo.setCurrentIndex(0)
        if not name:
            return
        self._adopt_custom(hex_list(get_library(name)))

    def _on_swatch_lock_toggled(self, index: int) -> None:
        """Toggle the lock of one swatch, keyed on its colour."""
        if self._loading or not 0 <= index < len(self._colors):
            return
        color = self._colors[index]
        if color in self._locked:
            self._locked.remove(color)
        else:
            self._locked.append(color)
        self._refresh()
        self.changed.emit()

    def _on_swatch_dropped(self, source: int, target: int) -> None:
        """Move the swatch at display position source to display position target."""
        if self._loading or source == target:
            return
        order = self.display_indices()
        if not 0 <= source < len(order) or not 0 <= target < len(order):
            return
        order.insert(target, order.pop(source))
        self._order = order
        self._refresh()
        self.changed.emit()

    def _on_swatch_clicked(self, index: int) -> None:
        """Ask for a new colour for one swatch."""
        if self._loading or not 0 <= index < len(self._colors):
            return
        chosen = self._ask_color(self._colors[index])
        if chosen is None:
            return
        previous = self._colors[index]
        self._colors[index] = chosen
        if previous in self._locked:
            self._locked = [chosen if color == previous else color for color in self._locked]
            self._locked = _normalise_locked(self._locked)
        self._set_error()
        self._refresh()
        self.changed.emit()

    def _on_swatch_removed(self, index: int) -> None:
        """Remove one swatch unless the palette would drop below two colours."""
        if self._loading or not 0 <= index < len(self._colors):
            return
        if len(self._colors) <= MIN_COLORS:
            self._set_error(tr("A palette needs at least two colours."))
            return
        del self._colors[index]
        self._locked = [color for color in self._locked if color in self._colors]
        self._order = []
        self._set_error()
        self._refresh()
        self.changed.emit()

    def _on_add_swatch(self) -> None:
        """Append a black swatch unless the palette already holds 256 colours."""
        if self._loading or len(self._colors) >= MAX_COLORS:
            return
        self._colors.append(NEW_COLOR)
        self._order = []
        self._set_error()
        self._refresh()
        self.changed.emit()

    def _on_file(self, export: bool) -> None:
        """Ask for a palette file and import it, or ask for a target and export."""
        dialog = QFileDialog.getSaveFileName if export else QFileDialog.getOpenFileName
        title = tr("Export palette") if export else tr("Import palette")
        start = "palette.hex" if export else ""
        path, _ = dialog(self, title, start, PALETTE_FILTER)
        if path:
            (self.export_palette if export else self.import_palette)(Path(path))

    def _ask_color(self, initial: str) -> str | None:
        """Open a colour dialog and return the chosen "#RRGGBB", or None when cancelled."""
        color = QColorDialog.getColor(QColor(initial), self, tr("Palette colour"))
        return color.name().upper() if color.isValid() else None

    def _refresh(self) -> None:
        """Sync every widget with the panel state without emitting changed."""
        with QSignalBlocker(self.builtin_combo):
            index = max(0, self.builtin_combo.findText(self._builtin_name))
            self.builtin_combo.setCurrentIndex(index)
            self._rebuild_grid()
        self._update_enabled()

    def _rebuild_grid(self) -> None:
        """Rebuild the swatch grid in display order."""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.add_button:
                widget.deleteLater()
        self.swatches = []
        for position, index in enumerate(self.display_indices()):
            swatch = SwatchButton(self._colors[index], position, self)
            swatch.set_locked(self._colors[index] in self._locked)
            swatch.clicked.connect(lambda _c=False, i=index: self._on_swatch_clicked(i))
            swatch.remove_requested.connect(lambda i=index: self._on_swatch_removed(i))
            swatch.lock_toggled.connect(lambda i=index: self._on_swatch_lock_toggled(i))
            swatch.dropped.connect(lambda s, t=position: self._on_swatch_dropped(s, t))
            self.grid_layout.addWidget(swatch, position // GRID_COLUMNS, position % GRID_COLUMNS)
            self.swatches.append(swatch)
        row, column = divmod(len(self._colors), GRID_COLUMNS)
        self.grid_layout.addWidget(self.add_button, row, column)

    def _update_enabled(self) -> None:
        """Enable only the controls that belong to the selected source."""
        builtin, extracted, custom = (self._source == name for name in SOURCES)
        self.builtin_combo.setEnabled(builtin)
        self.library_combo.setEnabled(True)
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
