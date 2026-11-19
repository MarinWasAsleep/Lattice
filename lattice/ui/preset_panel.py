"""Preset browser shared by the Lattice shells: the shipped and user tiers, load, save.

Glitch and Glyph carried copies of this panel that differed by one line: what `loaded`
emits. Glitch hands the window the whole ``Preset`` (spec, stack, masks and seed travel
together); Glyph hands it only the ``PipelineSpec``. That choice is the `convert` argument,
so the list, the two tiers, the read-only suffix and the error vocabulary live in one place.

The list never renders anything: it reads v3 presets in this app's context and hands the
window the whole ``Preset`` — spec, stack, masks and seed travel together. Saving is asked
from the window, which owns the document; the panel only offers a path in the user tier.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PRESET_FILTER = "Presets (*.json);;All files (*)"
DEFAULT_NAME = "preset.json"
READ_ONLY_SUFFIX = "  (read-only)"
EMPTY_HINT = "No preset found in the shipped or user tier."
TIER_HINT = "Saved presets go to the user tier; shipped ones are read-only."
NO_SELECTION = "Select a preset first."


class PresetPanel(QWidget):
    """Preset list of both tiers, with load, save and refresh."""

    loaded = Signal(object)
    save_requested = Signal(str)
    failed = Signal(str)

    def __init__(self, directories: tuple[Path, ...] | None = None,
                 parent: QWidget | None = None,
                 convert: Callable[[object], object] | None = None,
                 tools: Any = None) -> None:
        """Build the list and its three buttons, then read the tiers.

        `convert` turns a read ``Preset`` into whatever the window wants: the preset itself,
        or its ``PipelineSpec``. None means "hand over the preset as read". `tools` is the
        app's preset module: the two shells validate presets differently (Glitch checks
        masks, Glyph checks the renderer), so it stays with the app.
        """
        super().__init__(parent)
        self._convert = convert
        self._tools: Any = tools
        self.setObjectName("preset_panel")
        self._directories = directories
        self.list = QListWidget(self)
        self.list.setObjectName("preset_list")
        self.hint = QLabel("", self)
        self.hint.setObjectName("preset_hint")
        self.hint.setWordWrap(True)
        row = QHBoxLayout()
        self.load_button = QPushButton("Load", self)
        self.load_button.setObjectName("preset_load")
        self.save_button = QPushButton("Save…", self)
        self.save_button.setObjectName("preset_save")
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.setObjectName("preset_refresh")
        for button in (self.load_button, self.save_button, self.refresh_button):
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel("Presets", self))
        layout.addWidget(self.list, 1)
        layout.addWidget(self.hint)
        layout.addLayout(row)
        self.list.itemActivated.connect(lambda _item: self.load_selected())
        self.load_button.clicked.connect(self.load_selected)
        self.save_button.clicked.connect(self._ask_path)
        self.refresh_button.clicked.connect(self.refresh)
        self._entries: list[Any] = []
        self.refresh()

    def refresh(self) -> None:
        """Reload the preset tiers into the list, shipped entries marked read-only."""
        self._entries = self._tools.available(self._directories)  # type: ignore[attr-defined]
        self.list.clear()
        for entry in self._entries:
            label = entry.name + (READ_ONLY_SUFFIX if entry.read_only else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            self.list.addItem(item)
        self.hint.setText(TIER_HINT if self._entries else EMPTY_HINT)

    def entries(self) -> list[Any]:
        """Return the entries currently listed."""
        return list(self._entries)

    def user_dir(self) -> Path:
        """Return the directory a new preset is offered in: the user tier."""
        if self._directories:
            return self._directories[-1]
        return self._tools.user_preset_dir()  # type: ignore[attr-defined]

    def selected_path(self) -> Path | None:
        """Return the path of the selected entry, or None when nothing is selected."""
        item = self.list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return None if data is None else Path(str(data))

    def select_name(self, name: str) -> bool:
        """Select the listed preset called name; return True when it was found."""
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None and Path(str(item.data(Qt.ItemDataRole.UserRole))).name == name:
                self.list.setCurrentItem(item)
                return True
        return False

    def load_selected(self) -> None:
        """Read the selected preset and emit it, or report why it cannot be read."""
        path = self.selected_path()
        if path is None:
            self.failed.emit(NO_SELECTION)
            return
        try:
            preset = self._tools.read_preset(path)  # type: ignore[attr-defined]
            self.loaded.emit(preset if self._convert is None else self._convert(preset))
        except (OSError, ValueError, KeyError) as exc:
            self.failed.emit(f"Cannot read {path.name}: {exc}")

    def _ask_path(self) -> None:
        """Ask for a path in the user tier and emit it for the window to write."""
        target, _ = QFileDialog.getSaveFileName(
            self, "Save preset", str(self.user_dir() / DEFAULT_NAME), PRESET_FILTER
        )
        if target:
            self.save_requested.emit(target)


__all__ = ["DEFAULT_NAME", "PresetPanel"]
