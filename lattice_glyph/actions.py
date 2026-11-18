"""Actions and toolbar of the Glyph shell, built from one table so nothing is half-wired.

Each entry pairs an object name with its label, its slot and its shortcut; the toolbar
reads the same table, in the same order, so an action that exists is on the toolbar and an
action on the toolbar has a real slot behind it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar

if TYPE_CHECKING:
    from lattice_glyph.window import MainWindow

MODES: tuple[tuple[str, str, str], ...] = (
    ("mode_before", "Before", "before"),
    ("mode_after", "After", "after"),
    ("mode_split", "Split", "split"),
)
TOOLBAR_GROUPS: tuple[tuple[str, ...], ...] = (
    ("open_image", "get_from_host", "send_to_host"),
    ("export_image", "export_text"),
    ("mode_before", "mode_after", "mode_split"),
    ("zoom_fit", "zoom_100", "zoom_200", "zoom_400"),
)
MAIN_TOOLBAR = "main_toolbar"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})


def add_action(window: QMainWindow, key: str, text: str, slot: Callable[..., None],
               shortcut: QKeySequence | None = None) -> QAction:
    """Create one action on window, register it under key and connect it to slot."""
    action = QAction(text, window)
    action.setObjectName(key)
    if shortcut is not None:
        action.setShortcut(shortcut)
    action.triggered.connect(slot)
    window.addAction(action)
    return action


def build_actions(window: MainWindow) -> dict[str, QAction]:
    """Create every action of the shell and return them keyed by object name."""
    std = QKeySequence.StandardKey
    actions: dict[str, QAction] = {}
    table: tuple[tuple[str, str, Callable[..., None], QKeySequence | None], ...] = (
        ("open_image", "Open image", window.open_dialog, std.Open),
        ("get_from_host", "Get from host", window.get_from_host, None),
        ("send_to_host", "Send to host", window.send_to_host, None),
        ("export_image", "Export…", window.export_dialog, std.Save),
        ("export_text", "Export text…", window.export_text, None),
        ("zoom_fit", "Zoom Fit", window.canvas.zoom_fit, None),
        ("zoom_100", "100 %", lambda: window.canvas.set_zoom(1.0), None),
        ("zoom_200", "200 %", lambda: window.canvas.set_zoom(2.0), None),
        ("zoom_400", "400 %", lambda: window.canvas.set_zoom(4.0), None),
    )
    for key, text, slot, shortcut in table:
        actions[key] = add_action(window, key, text, slot, shortcut)
    group = QActionGroup(window)
    for key, text, mode in MODES:
        action = add_action(window, key, text,
                            lambda _checked=False, m=mode: window.set_mode(m))
        action.setCheckable(True)
        action.setChecked(mode == "after")
        group.addAction(action)
        actions[key] = action
    window.mode_group = group
    return actions


def build_toolbar(window: QMainWindow, actions: dict[str, QAction]) -> QToolBar:
    """Create the main toolbar, one separator between the groups of the table."""
    toolbar = QToolBar("Main", window)
    toolbar.setObjectName(MAIN_TOOLBAR)
    toolbar.setMovable(False)
    window.addToolBar(toolbar)
    for index, keys in enumerate(TOOLBAR_GROUPS):
        if index:
            toolbar.addSeparator()
        for key in keys:
            toolbar.addAction(actions[key])
    return toolbar


def dropped_images(mime) -> list[Path]:
    """Return the local image files carried by mime, in drop order."""
    if not mime.hasUrls():
        return []
    paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
    return [path for path in paths if path.suffix.lower() in IMAGE_SUFFIXES]


def connect_shutdown(window: MainWindow) -> None:
    """Stop the window's helper threads when the application quits."""
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(window.shutdown)


__all__ = [
    "IMAGE_SUFFIXES",
    "MAIN_TOOLBAR",
    "TOOLBAR_GROUPS",
    "add_action",
    "build_actions",
    "build_toolbar",
    "connect_shutdown",
    "dropped_images",
]
