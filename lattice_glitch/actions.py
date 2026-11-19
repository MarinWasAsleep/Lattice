"""Actions and toolbar of the Lattice Glitch shell, from the shared table.

The table, the mode group, the toolbar grouping and the drag-and-drop helpers live in
``lattice_core.ui.actions``. Glitch contributes its own second-group action: rerolling the
seed, which Glyph does not have.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QKeySequence

from lattice_core.ui.actions import (
    EXTRA_TOOLBAR_GROUPS,
    IMAGE_SUFFIXES,
    MAIN_TOOLBAR,
    MODES,
    add_action,
    dropped_images,
    handle_drag_enter,
    handle_drop,
)
from lattice_core.ui.actions import (
    build_actions as _build_actions,
)
from lattice_core.ui.actions import (
    build_toolbar as _build_toolbar,
)

if TYPE_CHECKING:
    from lattice_glitch.window import MainWindow

EXTRA_KEY = "reroll"


def _extra(window: MainWindow) -> tuple[str, str, Callable[..., None], QKeySequence | None]:
    """Return Glitch's own action: reroll the seed."""
    return (EXTRA_KEY, "Reroll seed", window.reroll, QKeySequence("R"))


def build_actions(window: MainWindow) -> dict[str, QAction]:
    """Create every action of the shell, Glitch's reroll included."""
    return _build_actions(window, _extra(window))


def build_toolbar(window, actions: dict[str, QAction]):
    """Create the main toolbar, with reroll in the second group."""
    return _build_toolbar(window, actions, EXTRA_KEY)


__all__ = [
    "EXTRA_KEY", "EXTRA_TOOLBAR_GROUPS", "IMAGE_SUFFIXES", "MAIN_TOOLBAR", "MODES",
    "add_action", "build_actions", "build_toolbar", "dropped_images",
    "handle_drag_enter", "handle_drop",
]
