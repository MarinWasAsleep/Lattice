"""The one Lattice window: Dither, Glyph and Glitch as three tabs of a single application.

Lattice shipped three separate programs, each its own ``QMainWindow`` with its own docks, its
own toolbar and its own process. A user who wanted to dither a photo and then run the result
through a glitch pass had to export, close, reopen, reimport. Version 1.0 puts the three modes
in one window, so an image can move from tab to tab without leaving the application.

The design keeps each mode intact rather than rewriting it. A mode is still the ``QMainWindow``
it always was — its docks, toolbar, spec, worker and bridge are untouched — but it is shown as
the *content of a tab* instead of as a top-level window. That is what the code below does, and
it is the whole of it: no mode knows it is a tab.

Why a tab holding a QMainWindow instead of merging the three into one window class: the three
windows differ in their docks, their panels and their controllers, but they share the engine
completely. Merging them would mean rewriting 1 500 lines and re-proving every behaviour; a
container proves the same coupling with none of that risk.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from lattice import APP_NAME, __version__
from lattice.app import RESOURCES

LOGGER = logging.getLogger(__name__)

SETTINGS_NAME = "Lattice"

# Order matters: the tabs are numbered, and Ctrl+1..3 walk them.
MODES: tuple[str, ...] = ("dither", "glyph", "glitch")


def mode_title(mode: str) -> str:
    """Return the tab label of one mode."""
    return {"dither": "Dither", "glyph": "Glyph", "glitch": "Glitch"}[mode]


def build_mode_window(mode: str, parent: QWidget | None = None) -> QMainWindow:
    """Return the main window of one mode, built on demand.

    Imported here rather than at module level: opening Lattice should not pay for the three
    mode windows, and a mode whose dependencies are missing must not take the others down.
    """
    import importlib

    if mode == "dither":
        module = importlib.import_module("lattice.modes.dither.ui.main_window")
        window = module.MainWindow(parent)
    else:
        module = importlib.import_module(f"lattice.modes.{mode}.window")
        window = module.MainWindow(parent)
    return window


class MainWindow(QMainWindow):
    """The Lattice window: a tab per mode, one settings object, one title."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the tab widget and open every mode inside it."""
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1440, 900)
        self._settings = QSettings(SETTINGS_NAME, SETTINGS_NAME)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        self.windows: dict[str, QMainWindow] = {}
        self.tabs.setObjectName("mode_tabs")
        self.tabs.tabBar().setObjectName("mode_tabbar")
        self.tabs.setIconSize(QSize(20, 20))
        for index, mode in enumerate(MODES):
            window = build_mode_window(mode, self.tabs)
            self.windows[mode] = window
            # The stylesheet colours each tab through this property, so the mode you are in is
            # readable from the tab bar alone.
            window.setProperty("mode", mode)
            icon = RESOURCES / f"icon-{mode}.svg"
            self.tabs.addTab(window, QIcon(str(icon)) if icon.is_file() else QIcon(),
                             mode_title(mode))
            self.tabs.setTabToolTip(index, f"{mode_title(mode)} — {mode}")
            # A QMainWindow used as tab content keeps its own Window flag, so QTabWidget adds
            # it but never shows it (the tab comes up blank) and never hides it either when
            # another tab is selected. Dropping that flag is all it takes: with it gone the
            # widget behaves exactly like the plain pages in the minimal reproduction.
            window.setWindowFlags(window.windowFlags() & ~Qt.WindowType.Window)

        self.tabs.currentChanged.connect(self._remember_tab)
        self._restore_tab()

    def current_mode(self) -> str:
        """Return the mode of the visible tab."""
        return MODES[self.tabs.currentIndex()]

    def show_mode(self, mode: str) -> None:
        """Bring one mode's tab to the front, by name."""
        if mode not in self.windows:
            raise ValueError(f"unknown mode: {mode!r}")
        self.tabs.setCurrentIndex(MODES.index(mode))

    def shutdown(self) -> None:
        """Stop the helper threads of every mode, not only the visible one.

        Each mode runs its own render worker on a thread; leaving two of them running would
        keep the process alive after the window closes.
        """
        for mode, window in self.windows.items():
            stopper = getattr(window, "shutdown", None)
            if stopper is None:
                LOGGER.warning("%s window has no shutdown()", mode)
                continue
            stopper()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        """Stop every mode before the window closes."""
        self.shutdown()
        super().closeEvent(event)

    def _remember_tab(self, index: int) -> None:
        """Persist the visible tab so Lattice reopens on the mode last used."""
        if 0 <= index < len(MODES):
            self._settings.setValue("window/mode", MODES[index])

    def _restore_tab(self) -> None:
        """Reopen on the last used tab, falling back to the first."""
        stored = self._settings.value("window/mode", MODES[0])
        if stored in self.windows:
            self.show_mode(str(stored))


def main(argv: list[str] | None = None) -> int:
    """Start the Lattice window and return the Qt exit code."""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    arguments = list(sys.argv[1:] if argv is None else argv)
    app = QApplication.instance() or QApplication(arguments)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    LOGGER.info("%s %s window shown", APP_NAME, __version__)
    return app.exec()


__all__ = ["MODES", "MainWindow", "build_mode_window", "main", "mode_title"]
