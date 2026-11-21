"""Bridge work of the Lattice Glitch shell, from the shared worker.

The pull/push logic, the absent answer and the disconnect discipline live in
``lattice.ui.bridge_worker``. Glitch only supplies what makes it Glitch: its render
function, which forwards the session render context so masks and per-slot streams travel.
"""

from __future__ import annotations

from PySide6.QtCore import Slot  # noqa: F401  (GUI module: the worker runs on its thread)

from lattice.modes.glitch.document import DocumentError, render_rgb8
from lattice.modes.glitch.hosts import discover
from lattice.ui.bridge_worker import BridgeWorker as _BridgeWorker

DEFAULT_HOST = "photocraft"
DEFAULT_NAME = "Lattice Glitch"
NOT_RUNNING = "{host} is not running: Lattice Glitch works standalone"


class BridgeWorker(_BridgeWorker):
    """The shared worker bound to the Glitch render function."""

    def __init__(self) -> None:
        """Bind Glitch's render path, which honours the session render context."""
        super().__init__(
            render=lambda image, spec, context: render_rgb8(image, spec, context=context),
            app_name="Lattice Glitch",
            document_error=DocumentError,
            default_name=DEFAULT_NAME,
            discover=discover,
        )


__all__ = ["BridgeWorker", "DEFAULT_HOST", "NOT_RUNNING"]
