"""Preset browsing: scan a directory, step through it, and bind the arrow keys."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabBar,
    QTextEdit,
)

from lattice_dither.core.presets import load_preset, save_preset

if TYPE_CHECKING:
    from lattice_dither.ui.main_window import MainWindow

PRESET_SUFFIX = ".json"
PRESET_FILTER = "Presets (*.json);;All files (*)"
STATUS_MS = 5000
ARROW_CONSUMERS = (
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTabBar,
    QTextEdit,
)


class PresetBrowser:
    """Ordered list of preset files with a current position."""

    def __init__(self, directory: Path) -> None:
        """Scan directory and select its first preset."""
        self.directory = Path(directory)
        self.paths: list[Path] = []
        self.index = -1
        self.refresh()

    def refresh(self) -> None:
        """Rescan the directory, keeping the current preset selected when it still exists."""
        current = self.current()
        try:
            found = sorted(p for p in self.directory.glob(f"*{PRESET_SUFFIX}") if p.is_file())
        except OSError:
            found = []
        self.paths = found
        if current is not None and current in found:
            self.index = found.index(current)
        elif found:
            self.index = min(max(self.index, 0), len(found) - 1)
        else:
            self.index = -1

    def current(self) -> Path | None:
        """Return the selected preset path, or None when the list is empty."""
        if 0 <= self.index < len(self.paths):
            return self.paths[self.index]
        return None

    def step(self, delta: int) -> Path | None:
        """Move delta places through the list, wrapping around, and return the new preset."""
        if not self.paths:
            return None
        self.index = (self.index + delta) % len(self.paths)
        return self.paths[self.index]

    def select(self, path: Path) -> None:
        """Select path when the list contains it."""
        path = Path(path)
        if path in self.paths:
            self.index = self.paths.index(path)

    def label(self) -> str:
        """Return a short status text such as 'Preset 3/12: gameboy.json'."""
        current = self.current()
        if current is None:
            return "Preset: none"
        return f"Preset {self.index + 1}/{len(self.paths)}: {current.name}"


class PresetController(QObject):
    """Preset actions, status label and arrow-key navigation for one main window."""

    def __init__(self, window: MainWindow) -> None:
        """Create the four preset actions and the status label, and install the arrow filter."""
        super().__init__(window)
        self.window = window
        self.browser = PresetBrowser(window._preset_dir())
        self.label = QLabel("Preset: none", window)
        self.label.setObjectName("preset_label")
        self.label.setText(self.browser.label())
        self.prev_action = window._add_action("preset_prev", "\u25c0", lambda: self.step(-1))
        self.load_action = window._add_action("load_preset", "Load preset", self.load_dialog)
        self.save_action = window._add_action("save_preset", "Save preset", self.save_dialog)
        self.next_action = window._add_action("preset_next", "\u25b6", lambda: self.step(1))
        self.prev_action.setToolTip("Previous preset (Left arrow)")
        self.next_action.setToolTip("Next preset (Right arrow)")
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def step(self, delta: int) -> None:
        """Load the preset delta places away in the preset directory."""
        path = self.browser.step(delta)
        if path is None:
            self.window.statusBar().showMessage(
                f"No presets in {self.browser.directory}", STATUS_MS
            )
            return
        self.apply(path)

    def apply(self, path: Path) -> None:
        """Load one preset file and adopt it as the current pipeline."""
        try:
            spec = load_preset(path)
        except (OSError, ValueError) as exc:
            self.window._error(f"Cannot load preset {path.name!r}: {exc}")
            return
        self.browser.select(path)
        self.window._load_spec(spec)
        self.label.setText(self.browser.label())
        self.window.statusBar().showMessage(f"Loaded preset {path.name}", STATUS_MS)

    def load_dialog(self) -> None:
        """Ask for a preset file and adopt it."""
        path = self.window._ask_path("Load preset", "preset_dir", "", PRESET_FILTER, save=False)
        if path is None:
            return
        self.browser.refresh()
        self.apply(Path(path))

    def save_dialog(self) -> None:
        """Ask for a preset path and write the current pipeline there."""
        self.window._rebuild_spec()
        path = self.window._ask_path(
            "Save preset", "preset_dir", "preset.json", PRESET_FILTER, save=True
        )
        if path is None:
            return
        try:
            save_preset(path, self.window.spec)
        except (OSError, ValueError) as exc:
            self.window._error(f"Cannot save preset {Path(path).name!r}: {exc}")
            return
        self.browser.refresh()
        self.browser.select(Path(path))
        self.label.setText(self.browser.label())
        self.window.statusBar().showMessage(f"Saved preset {Path(path).name}", STATUS_MS)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Step the preset on Left/Right, except where arrows already mean something."""
        if event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        if key not in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            return False
        if event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
            return False
        if QApplication.activeModalWidget() is not None:
            return False
        focus = QApplication.focusWidget()
        if focus is None or isinstance(focus, ARROW_CONSUMERS):
            return False
        self.step(-1 if key == Qt.Key.Key_Left else 1)
        return True
