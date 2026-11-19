"""Preset panel of the Lattice Glyph shell, from the shared core widget.

The list, the two tiers and the error vocabulary live in ``lattice_core.ui.preset_panel``.
This module only binds the app's preset tools and, where the window wants it, the conversion
from a read ``Preset`` to what the window carries.
"""

from __future__ import annotations

from PySide6.QtCore import Signal  # noqa: F401  (GUI module: the panel is a widget)
from PySide6.QtWidgets import QWidget

from lattice_core.ui.preset_panel import (
    DEFAULT_NAME,
    EMPTY_HINT,
    NO_SELECTION,
    PRESET_FILTER,
    READ_ONLY_SUFFIX,
    TIER_HINT,
)
from lattice_core.ui.preset_panel import PresetPanel as _PresetPanel
from lattice_glyph import presets as preset_tools


class PresetPanel(_PresetPanel):
    """The shared preset list bound to this app's preset tools."""

    def __init__(self, directories=None, parent: QWidget | None = None) -> None:
        """Build the list with this app's tiers and conversion."""
        super().__init__(directories, parent,
    convert=preset_tools.spec_of,
                         tools=preset_tools)


__all__ = [
    "PresetPanel", "DEFAULT_NAME", "EMPTY_HINT", "NO_SELECTION",
    "PRESET_FILTER", "READ_ONLY_SUFFIX", "TIER_HINT",
]
