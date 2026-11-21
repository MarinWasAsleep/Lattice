"""Bridge work of the Lattice Glyph shell, from the shared worker.

The pull/push logic, the absent answer and the disconnect discipline live in
``lattice.ui.bridge_worker``. Glyph has no masks or per-slot streams, so it ignores the
render context the shared signal carries and renders straight from the spec.
"""

from __future__ import annotations

from PySide6.QtCore import Slot  # noqa: F401  (GUI module: the worker runs on its thread)

from lattice.modes.glyph.document import DocumentError, render_rgb8
from lattice.modes.glyph.hosts import discover
from lattice.ui.bridge_worker import BridgeWorker as _BridgeWorker

DEFAULT_HOST = "photocraft"
DEFAULT_NAME = "Lattice Glyph"
NOT_RUNNING = "{host} is not running: Lattice Glyph works standalone"


class BridgeWorker(_BridgeWorker):
    """The shared worker bound to the Glyph render function."""

    def __init__(self) -> None:
        """Bind Glyph's render path, which takes no render context."""
        super().__init__(
            render=lambda image, spec, context: render_rgb8(image, spec),
            app_name="Lattice Glyph",
            document_error=DocumentError,
            default_name=DEFAULT_NAME,
            discover=discover,
        )


__all__ = ["BridgeWorker", "DEFAULT_HOST", "NOT_RUNNING"]
