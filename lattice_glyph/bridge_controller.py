"""Bridge controller of Lattice Glyph, from the shared core class.

The threading, the shutdown order and the signal vocabulary live in
``lattice_core.ui.bridge_controller``; this module only binds the app's own worker class
and layer name, so a fix to the worker lifetime reaches both shells at once.
"""

from __future__ import annotations

from PySide6.QtCore import QObject  # noqa: F401  (GUI module: the shell owns the thread)

from lattice_core.ui.bridge_controller import STOP_MS
from lattice_core.ui.bridge_controller import BridgeController as _BridgeController
from lattice_glyph.bridge_actions import DEFAULT_HOST, BridgeWorker

LAYER_NAME = "Lattice Glyph"


class BridgeController(_BridgeController):
    """The shared controller bound to this app's worker and default host."""

    def __init__(self, parent: QObject | None = None, host: str = DEFAULT_HOST) -> None:
        """Create the helper thread with this app's worker class."""
        super().__init__(parent, host=host, layer_name=LAYER_NAME, worker=BridgeWorker)


__all__ = ["BridgeController", "LAYER_NAME", "STOP_MS"]
