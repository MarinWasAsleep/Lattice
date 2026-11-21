"""Actions and toolbar of the Lattice Glyph shell, from the shared table.

The table, the mode group, the toolbar grouping and the drag-and-drop helpers live in
``lattice.ui.actions``. Glyph contributes its own second-group action: exporting the
text, which Glitch does not have.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QKeySequence

from lattice.ui.actions import (
    EXTRA_TOOLBAR_GROUPS,
    IMAGE_SUFFIXES,
    MAIN_TOOLBAR,
    MODES,
    add_action,
    connect_shutdown,
    dropped_images,
    handle_drag_enter,
    handle_drop,
)
from lattice.ui.actions import (
    build_actions as _build_actions,
)
from lattice.ui.actions import (
    build_toolbar as _build_toolbar,
)

if TYPE_CHECKING:
    from lattice.modes.glyph.window import MainWindow

EXTRA_KEY = "export_text"
TOOLBAR_GROUPS = EXTRA_TOOLBAR_GROUPS


def _extra(window: MainWindow) -> tuple[str, str, Callable[..., None], QKeySequence | None]:
    """Return Glyph's own action: export the rendered text."""
    return (EXTRA_KEY, "Export text…", window.export_text, None)


def build_actions(window: MainWindow) -> dict[str, QAction]:
    """Create every action of the shell, Glyph's text export included."""
    return _build_actions(window, _extra(window))


def build_toolbar(window, actions: dict[str, QAction]):
    """Create the main toolbar, with the text export in the second group."""
    return _build_toolbar(window, actions, EXTRA_KEY)


__all__ = [
    "EXTRA_KEY", "EXTRA_TOOLBAR_GROUPS", "IMAGE_SUFFIXES", "MAIN_TOOLBAR", "MODES",
    "TOOLBAR_GROUPS", "add_action", "build_actions", "build_toolbar",
    "connect_shutdown", "dropped_images",
    "handle_drag_enter", "handle_drop",
]
