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

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from lattice import APP_NAME, __version__
from lattice.app import RESOURCES
from lattice.ui.geometry import WINDOW_MIN_HEIGHT
from lattice.ui.screen import clamp_to_area

LOGGER = logging.getLogger(__name__)

SETTINGS_NAME = "Lattice"
GEOMETRY_KEY = "window/geometry"
FULLSCREEN_KEY = "window/fullscreen"

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
        # No fixed size: a 1440x900 default is taller than a 1366x768 laptop screen and put the
        # status bar out of reach. The height floor is explicit and small; the width is left to
        # the layout, which needs more room than a fixed floor would allow for Dither.
        self.setMinimumHeight(WINDOW_MIN_HEIGHT)
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
        self._build_view_menu()
        self._restore_tab()
        self._restore_window()

    def current_mode(self) -> str:
        """Return the mode of the visible tab."""
        return MODES[self.tabs.currentIndex()]

    def show_mode(self, mode: str) -> None:
        """Bring one mode's tab to the front, by name."""
        if mode not in self.windows:
            raise ValueError(f"unknown mode: {mode!r}")
        self.tabs.setCurrentIndex(MODES.index(mode))

    # --- window size, fullscreen ------------------------------------------------------

    def _build_view_menu(self) -> None:
        """Add View: fullscreen, a shortcut per mode, and nothing that duplicates the modes."""
        view = self.menuBar().addMenu("&View")
        self.fullscreen_action = QAction("&Fullscreen", self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self.fullscreen_action)
        view.addAction(self.fullscreen_action)

        # Escape leaves fullscreen only while in it, so it keeps working as a field shortcut the
        # rest of the time. Disabled outside fullscreen is what expresses that.
        self.leave_fullscreen = QAction(self)
        self.leave_fullscreen.setShortcut(QKeySequence("Esc"))
        self.leave_fullscreen.setEnabled(False)
        self.leave_fullscreen.triggered.connect(lambda: self.set_fullscreen(False))
        self.addAction(self.leave_fullscreen)

        view.addSeparator()
        for index, mode in enumerate(MODES):
            action = QAction(mode_title(mode), self)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(lambda _checked=False, name=mode: self.show_mode(name))
            self.addAction(action)
            view.addAction(action)

    def set_fullscreen(self, on: bool) -> None:
        """Enter or leave fullscreen, keeping the check state in step with reality."""
        if on == self.isFullScreen():
            return
        if on:
            self.showFullScreen()
        else:
            self.showNormal()
        self.fullscreen_action.setChecked(on)
        self.leave_fullscreen.setEnabled(on)

    def toggle_fullscreen(self) -> None:
        """Flip between fullscreen and normal."""
        self.set_fullscreen(not self.isFullScreen())

    def available_area(self):
        """Return the screen area this window may use, margins excluded.

        The screen the window sits on is preferred; at startup, before any move, that is the
        primary screen.
        """
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry()

    def _restore_window(self) -> None:
        """Open at the size of the screen, or at the saved size if the screen can hold it."""
        area = self.available_area()
        stored = self._settings.value(GEOMETRY_KEY)
        if isinstance(stored, QByteArray) and not stored.isEmpty():
            # restoreGeometry first, then corrected: a rectangle saved on a bigger screen would
            # otherwise reopen taller than this display, its bottom edge off the screen and out
            # of reach.
            self.restoreGeometry(stored)
            self.setGeometry(clamp_to_area(self.geometry(), area))
        else:
            self.resize(area.size())
        if self._settings.value(FULLSCREEN_KEY, False, type=bool):
            self.set_fullscreen(True)

    def _remember_window(self) -> None:
        """Persist the geometry to come back to, and whether the window was fullscreen.

        Saved through ``saveGeometry`` because that is the only form ``restoreGeometry`` accepts;
        while fullscreen it records the normal geometry, which is the size to come back to.
        """
        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        self._settings.setValue(FULLSCREEN_KEY, self.isFullScreen())

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
        """Remember the window size, then stop every mode before closing."""
        self._remember_window()
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
