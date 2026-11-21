"""Actions and toolbar shared by the Lattice shells, built from one table.

Glitch and Glyph carried near-identical copies. They differed by one action — Glitch offers
"Reroll seed" (R), Glyph offers "Export text…" — so that entry is a parameter and the rest of
the table, the mode group, the toolbar grouping and the drag-and-drop helpers live here.
Everything is built from one table so nothing is half-wired: an action that exists but is not
in a toolbar group is a bug this shape cannot produce.

Each entry pairs an object name with its label, its slot and its shortcut; the toolbar
reads the same table, in the same order, so an action that exists is on the toolbar and an
action on the toolbar has a real slot behind it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar

if TYPE_CHECKING:
    from typing import Protocol

    class MainWindow(Protocol):
        """The window API the table relies on; both shells satisfy it."""

        canvas: object
        mode_group: object

        def open_dialog(self) -> None: ...
        def get_from_host(self) -> None: ...
        def send_to_host(self) -> None: ...
        def export_dialog(self) -> None: ...
        def open_path(self, path: Path) -> None: ...
        def set_mode(self, mode: str) -> None: ...
        def status(self, text: str) -> None: ...

MODES: tuple[tuple[str, str, str], ...] = (
    ("mode_before", "Before", "before"),
    ("mode_after", "After", "after"),
    ("mode_split", "Split", "split"),
)
# The extra action of the second toolbar group is the one thing the two shells do not share:
# Glitch rerolls the seed, Glyph exports its text. It arrives as `extra` and is placed by key.
EXTRA_TOOLBAR_GROUPS: tuple[tuple[str, ...], ...] = (
    ("open_image", "get_from_host", "send_to_host"),
    ("export_image", "@extra"),
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


def build_actions(window: MainWindow,
                  extra: tuple[str, str, Callable[..., None], QKeySequence | None] | None = None,
                  ) -> dict[str, QAction]:
    """Create every action of the shell and return them keyed by object name.

    `extra` is the shell's own action: (key, text, slot, shortcut). It is placed in the
    toolbar by the ``@extra`` marker of ``EXTRA_TOOLBAR_GROUPS``.
    """
    std = QKeySequence.StandardKey
    actions: dict[str, QAction] = {}
    table: tuple[tuple[str, str, Callable[..., None], QKeySequence | None], ...] = (
        ("open_image", "Open image", window.open_dialog, std.Open),
        ("get_from_host", "Get from host", window.get_from_host, None),
        ("send_to_host", "Send to host", window.send_to_host, None),
        ("export_image", "Export…", window.export_dialog, std.Save),
        *((extra,) if extra is not None else ()),
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


def build_toolbar(window: QMainWindow, actions: dict[str, QAction],
                  extra_key: str | None = None) -> QToolBar:
    """Create the main toolbar, one separator between the groups of the table.

    `extra_key` is the key of the shell's own action, placed where ``@extra`` sits.
    """
    toolbar = QToolBar("Main", window)
    toolbar.setObjectName(MAIN_TOOLBAR)
    toolbar.setMovable(False)
    window.addToolBar(toolbar)
    for index, keys in enumerate(EXTRA_TOOLBAR_GROUPS):
        if index:
            toolbar.addSeparator()
        for key in keys:
            if key == "@extra":
                continue
            toolbar.addAction(actions[key])
        if "@extra" in keys and extra_key is not None:
            toolbar.addAction(actions[extra_key])
    return toolbar


def dropped_images(mime: QMimeData) -> list[Path]:
    """Return the local image files carried by mime, in drop order."""
    if not mime.hasUrls():
        return []
    paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
    return [path for path in paths if path.suffix.lower() in IMAGE_SUFFIXES]


def handle_drag_enter(window: MainWindow, event: QDragEnterEvent) -> None:
    """Accept a drag carrying at least one local image file, ignore the rest."""
    if dropped_images(event.mimeData()):
        event.acceptProposedAction()
    else:
        event.ignore()


def handle_drop(window: MainWindow, event: QDropEvent) -> None:
    """Open the first image of a drop, or report that the drop was ignored."""
    images = dropped_images(event.mimeData())
    if not images:
        window.status("Ignored: no image in the drop")
        event.ignore()
        return
    event.acceptProposedAction()
    window.open_path(images[0])


def connect_shutdown(window: MainWindow) -> None:
    """Stop the window's helper threads when the application quits."""
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(window.shutdown)


__all__ = [
    "IMAGE_SUFFIXES",
    "MAIN_TOOLBAR",
    "EXTRA_TOOLBAR_GROUPS",
    "add_action",
    "build_actions",
    "build_toolbar",
    "connect_shutdown",
    "dropped_images",
    "handle_drag_enter",
    "handle_drop",
]
