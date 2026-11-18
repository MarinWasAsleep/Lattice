"""Palette panel: a built-in palette, custom hex colours, or a palette extracted from the image.

Every source maps onto one ``PaletteSpec`` of §3, so the render path never carries a table
of its own. Library palettes are offered as a starting point for the custom list, which is
what a ``custom`` source actually renders.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QSpinBox, QWidget

from lattice_core.palettes.builtin import builtin_names
from lattice_core.palettes.io import from_hex_text, hex_list
from lattice_core.palettes.library import get_library, library_names
from lattice_core.pipeline import PaletteSpec

BUILTIN_SOURCE = "builtin"
CUSTOM_SOURCE = "custom"
EXTRACTED_SOURCE = "extracted"
PALETTE_KINDS = (
    (BUILTIN_SOURCE, "Built-in"),
    (CUSTOM_SOURCE, "Custom colours"),
    (EXTRACTED_SOURCE, "Extracted from image"),
)
EXTRACT_METHODS = ("kmeans", "median_cut")
MIN_K, MAX_K = 2, 32
COLOR_HINT = "#000000 #ffffff"


class PalettePanel(QWidget):
    """Palette source: built-in, custom hex colours, or extraction from the loaded image."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the kind selector, the name list, the hex field and the extraction row."""
        super().__init__(parent)
        self.setObjectName("palette_panel")
        self._loading = False
        self.kind = QComboBox(self)
        self.kind.setObjectName("palette_kind")
        for key, label in PALETTE_KINDS:
            self.kind.addItem(label, key)
        self.names = QComboBox(self)
        self.names.setObjectName("palette_name")
        for name in builtin_names():
            self.names.addItem(name, name)
        self.library = QComboBox(self)
        self.library.setObjectName("palette_library")
        self.library.addItem("Load a library palette…", "")
        for name in library_names():
            self.library.addItem(name, name)
        self.colors = QLineEdit(self)
        self.colors.setObjectName("palette_colors")
        self.colors.setPlaceholderText(COLOR_HINT)
        self.extract_k = QSpinBox(self)
        self.extract_k.setObjectName("palette_extract_k")
        self.extract_k.setRange(MIN_K, MAX_K)
        self.extract_k.setValue(8)
        self.method = QComboBox(self)
        self.method.setObjectName("palette_method")
        for name in EXTRACT_METHODS:
            self.method.addItem(name, name)
        form = QFormLayout(self)
        form.setContentsMargins(8, 8, 8, 8)
        form.addRow("Source", self.kind)
        form.addRow("Palette", self.names)
        form.addRow("Library", self.library)
        form.addRow("Colours", self.colors)
        form.addRow("Colours to extract", self.extract_k)
        form.addRow("Method", self.method)
        self.kind.currentIndexChanged.connect(self._on_kind)
        self.names.currentIndexChanged.connect(self._announce)
        self.library.activated.connect(self._on_library)
        self.colors.textChanged.connect(self._announce)
        self.extract_k.valueChanged.connect(self._announce)
        self.method.currentIndexChanged.connect(self._announce)
        self._sync_enabled()

    def source(self) -> str:
        """Return the palette source currently selected."""
        return str(self.kind.currentData())

    def spec(self) -> PaletteSpec:
        """Return the PaletteSpec the current widgets describe."""
        source = self.source()
        if source == CUSTOM_SOURCE:
            return PaletteSpec(source=CUSTOM_SOURCE, colors=_colours(self.colors.text()))
        if source == EXTRACTED_SOURCE:
            return PaletteSpec(
                source=EXTRACTED_SOURCE,
                extract_k=self.extract_k.value(),
                extract_method=str(self.method.currentData()),
            )
        return PaletteSpec(source=BUILTIN_SOURCE, name=str(self.names.currentData() or "bw"))

    def set_palette(self, spec: PaletteSpec) -> None:
        """Show spec in the widgets without announcing a change."""
        self._loading = True
        try:
            self.kind.setCurrentIndex(max(0, self.kind.findData(spec.source)))
            self.names.setCurrentIndex(max(0, self.names.findData(spec.name)))
            self.colors.setText(" ".join(spec.colors))
            self.extract_k.setValue(int(spec.extract_k))
            self.method.setCurrentIndex(max(0, self.method.findData(spec.extract_method)))
            self._sync_enabled()
        finally:
            self._loading = False

    def valid_colours(self) -> bool:
        """Return True when the custom colour field parses as a palette, or is not in use."""
        if self.source() != CUSTOM_SOURCE:
            return True
        try:
            _colours(self.colors.text())
            from_hex_text(self.colors.text())
        except ValueError:
            return False
        return True

    def _on_kind(self) -> None:
        """Enable the widgets the new source reads, then announce the change."""
        self._sync_enabled()
        self._announce()

    def _on_library(self, _index: int) -> None:
        """Copy a library palette into the custom colour list, switching to that source."""
        name = str(self.library.currentData() or "")
        if not name:
            return
        try:
            colours = " ".join(hex_list(get_library(name)))
        except KeyError:
            return
        self._loading = True
        try:
            self.colors.setText(colours)
            self.kind.setCurrentIndex(max(0, self.kind.findData(CUSTOM_SOURCE)))
            self._sync_enabled()
        finally:
            self._loading = False
        self._announce()

    def _sync_enabled(self) -> None:
        """Enable only the widgets the selected source actually reads."""
        source = self.source()
        self.names.setEnabled(source == BUILTIN_SOURCE)
        self.library.setEnabled(True)
        self.colors.setEnabled(source == CUSTOM_SOURCE)
        self.extract_k.setEnabled(source == EXTRACTED_SOURCE)
        self.method.setEnabled(source == EXTRACTED_SOURCE)

    def _announce(self) -> None:
        """Announce a user change, unless the panel is being loaded."""
        if not self._loading:
            self.changed.emit()


def _colours(text: str) -> list[str]:
    """Return the hex tokens of a whitespace-separated list, each with one leading '#'."""
    tokens = [token.strip() for token in text.replace(",", " ").split()]
    return [token if token.startswith("#") else f"#{token}" for token in tokens if token]


__all__ = ["PALETTE_KINDS", "PalettePanel"]
